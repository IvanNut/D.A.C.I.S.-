#Централизованное управление всеми дронами.
#Этот модуль инкапсулирует логику подключения, отключения и выполнения команд для дронов.

from djitellopy import Tello
from drone_utils import keep_alive
import threading
import config
from rich import print
from bottle_tracker import start_bottle_tracking

drones = {}

#Списки дронов
DRONE_IPS = {
    'первый': '192.168.0.120',
    #'второй': '192.168.0.121',
    #'третий': '192.168.0.158'
    #'четвертый': '192.168.0.184'
}

#Списки классов объектов
CLASS_NAMES = {
    "бутылку": 39,
    "человека": 0,   # 0 – человек в COCO
    "кошку": 15,     # пример
    "собаку": 16,    # пример
}

# Функция для инициализации подключений к дронам
def initialize_drones():
    for name, ip in DRONE_IPS.items():
        print(f"\n🔄 Подключаю {name} по IP {ip}...")
        try:
            tello = Tello(host=ip)
            tello.connect()
            print(f"✅ {name} подключен успешно.")
            drones[name] = {
                "tello": tello,
                "frame_reader": None,
                "streaming": False,
                "ip": ip
            }
        except Exception as e:
            print(f"❌ {name} не удалось подключить: {e}")

# Функция для инициализации видео потока
def start_video_stream(drone_name):
    drone_data = drones.get(drone_name)
    if not drone_data:
        print(f"❌ Дрон {drone_name} не найден.")
        return

    if drone_data["streaming"]:
        print(f"⚠️ Видеопоток у {drone_name} уже активен.")
        return

    tello = drone_data["tello"]
    tello.streamon()
    drone_data["frame_reader"] = tello.get_frame_read()
    drone_data["streaming"] = True
    print(f"📹 Видеопоток у {drone_name} запущен.")

# Функция для остановки видео потока
def stop_video_stream(drone_name):
    drone_data = drones.get(drone_name)
    if not drone_data:
        print(f"❌ Дрон {drone_name} не найден.")
        return

    if not drone_data["streaming"]:
        print(f"⚠️ Видеопоток у {drone_name} уже отключён.")
        return

    tello = drone_data["tello"]
    tello.streamoff()
    drone_data["streaming"] = False
    drone_data["frame_reader"] = None
    print(f"⛔ Видеопоток у {drone_name} остановлен.")

#Функция для принудительной остановки активного процесса отслеживания
def stop_tracking():
    global tracking_stop_event, tracking_thread
    tracking_stop_event.set()
    if tracking_thread and tracking_thread.is_alive():
        tracking_thread.join()
    tracking_thread = None

#Выполнение команд дрона
def execute_drone_command(drone_name, command):
    if drone_name not in drones:
        return "Дрон не найден."

    drone_data = drones[drone_name]
    tello = drone_data["tello"]
    frame_reader = drone_data["frame_reader"]

    # 👉 Проверка: это команда слежения?
    for word, class_id in CLASS_NAMES.items():
        if f"найди {word}" in command:
            print(f"🎯 Команда: найди {word} (class_id: {class_id})")
            threading.Thread(
                target=start_bottle_tracking,
                args=(tello, frame_reader),
                kwargs={"target_class_id": class_id},
                daemon=True
            ).start()
            return

    # 👉 Обычные команды — через поток
    def run_command():
        try:
            if command == 'включи поток':
                start_video_stream(drone_name)
            elif command == 'отключи поток':
                stop_video_stream(drone_name)
            elif command == 'наверх':
                tello.takeoff()
                keep_alive(tello)
            elif command == 'стоп':
                tello.land()
            elif command == 'вперёд':
                tello.move_forward(30)
            elif command == 'поворот':
                tello.rotate_clockwise(90)
            else:
                print("⚠️ Неизвестная команда")
        except Exception as e:
            print(f"Ошибка при выполнении команды '{command}': {e}")

    threading.Thread(target=run_command, daemon=True).start()