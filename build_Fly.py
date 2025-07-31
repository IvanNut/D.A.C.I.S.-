import time
import math
import threading
from djitellopy import Tello, TelloException
from drone_utils import keep_alive

# === НАСТРОЙКИ ШОУ ===
FORMATION_PARAMS = {
    "base_distance": 50,  # Расстояние между крайними дронами (основание V), см
    "angle_deg": 30,  # Угол при вершине V, градусов
    "move_speed": 50,  # Скорость перемещения дронов, см/с
    "hover_after_takeoff": 3,  # Задержка после взлёта, секунд
    "hover_after_land": 3,  # Задержка перед посадкой, секунд
    "spread_direction": "backward"  # Направление разлёта боковых дронов: "forward" или "backward"
}


# === ОСНОВНЫЕ ФУНКЦИИ ===

def connect_all(drones_dict):
    """
    Проверка подключения всех дронов и вывод уровня батареи.
    """
    for ip, drone_data in drones_dict.items():
        drone = drone_data["tello"]
        try:
            battery = drone.get_battery()
            print(f"[OK] Дрон {ip} подключён, батарея: {battery}%")
        except TelloException as e:
            print(f"[Ошибка] Проблема с дроном {ip}: {e}")
        except AttributeError:
            print(f"[Ошибка] Объект Tello для {ip} не найден.")


def takeoff_all(drones_dict):
    """
    Одновременный взлет всех дронов с использованием многопоточности.
    """
    threads = []
    for name, drone_data in drones_dict.items():
        ip = drone_data["ip"]
        drone = drone_data["tello"]
        thread = threading.Thread(target=try_takeoff, args=(ip, drone))
        thread.start()
        threads.append(thread)
    for t in threads:
        t.join()
    time.sleep(FORMATION_PARAMS["hover_after_takeoff"])


def try_takeoff(ip, drone):
    try:
        print(f"Дрон {ip} взлетает...")
        drone.takeoff()
    except TelloException as e:
        print(f"[Ошибка] Дрон {ip} не смог взлететь: {e}")


def land_all(drones_dict):
    """
    Одновременная посадка всех дронов.
    """
    time.sleep(5)
    time.sleep(FORMATION_PARAMS["hover_after_land"])
    threads = []
    for name, drone_data in drones_dict.items():
        ip = drone_data["ip"]
        drone = drone_data["tello"]
        thread = threading.Thread(target=try_land, args=(ip, drone))
        thread.start()
        threads.append(thread)
    for t in threads:
        t.join()


def try_land(ip, drone):
    try:
        print(f"Дрон {ip} садится...")
        drone.land()
    except TelloException as e:
        print(f"[Ошибка] Дрон {ip} не смог приземлиться: {e}")


def send_all_to_v_formation(drones_dict):
    """
    Разлёт дронов в V-образную формацию согласно параметрам из FORMATION_PARAMS.
    """
    distance = FORMATION_PARAMS["base_distance"]
    angle_deg = FORMATION_PARAMS["angle_deg"]
    move_speed = FORMATION_PARAMS["move_speed"]
    spread_dir = FORMATION_PARAMS["spread_direction"].lower()

    angle_rad = math.radians(angle_deg)
    half_base = distance / 2

    # Вычисляем высоту (расстояние по оси X) от центрального дрона до боковых
    height = half_base / math.tan(angle_rad / 2)

    # Определяем направление по оси X (вперёд или назад)
    x_dir = 1 if spread_dir == "forward" else -1

    drone_names_ordered = list(drones_dict.keys())
    if len(drone_names_ordered) != 3:
        print("[Ошибка] Для V-формации требуется ровно 3 дрона!")
        return

    # Вычисляем итоговое расстояние между боковыми дронами после разлёта
    # По формуле расстояния между двумя точками (x1,y1) и (x2,y2)
    left_pos = (x_dir * height, -half_base, 0)
    right_pos = (x_dir * height, +half_base, 0)
    dist_after = math.sqrt((right_pos[0] - left_pos[0]) ** 2 + (right_pos[1] - left_pos[1]) ** 2)

    # Позиции дронов: центральный остаётся (0,0,0)
    positions = {
        drone_names_ordered[0]: (0, 0, 0),  # Центральный
        drone_names_ordered[1]: left_pos,  # Левый
        drone_names_ordered[2]: right_pos,  # Правый
    }

    threads = []
    for i, name in enumerate(drone_names_ordered):
        drone_data = drones_dict[name]
        drone = drone_data["tello"]
        ip = drone_data["ip"]



        x, y, z = positions[name]



        def move(drone_obj, x_coord, y_coord, z_coord, drone_ip):
            try:
                if i == 0:
                    drone_obj.go_xyz_speed(int(1), int(1), int(1), 1)
                print(f"Дрон {drone_ip} перемещается к x={int(x_coord)}, y={int(y_coord)}, z={int(z_coord)}")
                drone_obj.go_xyz_speed(int(x_coord), int(y_coord), int(z_coord), move_speed)
            except TelloException as e:
                print(f"[Ошибка] Дрон {drone_ip} не смог переместиться: {e}")

        thread = threading.Thread(target=move, args=(drone, x, y, z, ip))
        thread.start()
        threads.append(thread)

    for t in threads:
        t.join()

    print(
        f"V-формация завершена: угол {angle_deg}°, основание {distance} см, расстояние между боковыми после разлёта {dist_after:.1f} см, направление: {spread_dir}")


# === УПРАВЛЯЮЩИЕ ФУНКЦИИ ===

def build_formation(drones_dict):
    """
    Подключение, взлёт и построение V-образной формации.
    """
    print("Подключаем дроны и взлетаем...")
    connect_all(drones_dict)
    takeoff_all(drones_dict)
    print("Формируем V-образную формацию...")
    send_all_to_v_formation(drones_dict)


def land_all_drones(drones_dict):
    """
    Посадка всех дронов.
    """
    print("Посадка всех дронов...")
    land_all(drones_dict)
