from ultralytics import YOLO
import cv2
import numpy as np
import threading
from obstacle_avoidance import ObstacleAvoidance

# YOLO модель
model = YOLO("yolov8n.pt")

spiral_counter = 0
spiral_shift_every = 7
initial_spiral_forward = 30  # Начальное расстояние движения вперед
radius_increment = 10  # Величина увеличения радиуса с каждым циклом
spiral_yaw = 40  # Угловое вращение между витками спирали


def findPerson(img, target_class_id):
    results = model(img)
    bottle_data = results[0].boxes.data.cpu().numpy()

    myBottleListC = []
    myBottleListArea = []

    for *box, conf, cls in bottle_data:
        if int(cls) == target_class_id:  # Объект
            x1, y1, x2, y2 = map(int, box)
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            area = (x2 - x1) * (y2 - y1)
            myBottleListArea.append(area)
            myBottleListC.append([cx, cy])

    if len(myBottleListArea) != 0:
        i = myBottleListArea.index(max(myBottleListArea))
        return img, [myBottleListC[i], myBottleListArea[i]]
    else:
        return img, [[0, 0], 0]


def calculate_distance(area):
    a = 2500
    b = 10
    if area == 0:
        return float('inf')
    return a / (area ** 0.5) + b


def trackPerson(myDrone, info, w, h, pid, pError, inner_area, outer_area):
    global spiral_counter, initial_spiral_forward, radius_increment

    x, y = info[0]
    area = info[1]

    distance = calculate_distance(area)
    print(f"Дистанция до объекта: {distance:.2f} см" if distance != float('inf') else "Объект не обнаружен")

    if area == 0:
        # Объект не найден - начинаем спиральный поиск
        spiral_counter += 1
        left_right_velocity = 0
        for_back_velocity = 0
        up_down_velocity = 0
        yaw_velocity = spiral_yaw

        current_spiral_forward = initial_spiral_forward + radius_increment * (spiral_counter // spiral_shift_every)

        if spiral_counter % spiral_shift_every == 0:
            for_back_velocity = current_spiral_forward
            print(f"🌀 Спиральный сдвиг вперёд ({current_spiral_forward})")

        if myDrone.send_rc_control:
            myDrone.send_rc_control(left_right_velocity,
                                    for_back_velocity,
                                    up_down_velocity,
                                    yaw_velocity)
        return pError, False, None

    else:
        spiral_counter = 0

        error_x = x - w // 2
        speed_horizontal = pid[0] * error_x + pid[1] * (error_x - pError[0])
        speed_horizontal = int(np.clip(speed_horizontal, -100, 100))

        if area > outer_area:
            for_back_velocity = -20
        elif area < inner_area:
            for_back_velocity = 20
        else:
            for_back_velocity = 0

        # Поворот для центрирования
        if speed_horizontal > 20:
            yaw_velocity = 20
        elif speed_horizontal < -20:
            yaw_velocity = -20
        else:
            yaw_velocity = 0

        left_right_velocity = 0
        up_down_velocity = 0

        if myDrone.send_rc_control:
            myDrone.send_rc_control(left_right_velocity,
                                    for_back_velocity,
                                    up_down_velocity,
                                    yaw_velocity)

        reached_target = inner_area <= area <= outer_area
        return [error_x, speed_horizontal], reached_target, (x, y)


def process_frame(myDrone, w, h, pid, pError, inner_area, outer_area, target_class_id):
    while True:
        img = myDrone.get_frame_read().frame
        img = cv2.resize(img, (w, h))
        img, info = findPerson(img, target_class_id)
        pError, reached_target, coords = trackPerson(myDrone, info, w, h, pid, pError, inner_area, outer_area)

        if reached_target:
            print(f"🚩 Цель достигнута! Координаты объекта в кадре: {coords}")
            print("🛬 Выполняю посадку...")
            myDrone.land()
            break  # Выходим из цикла обработки кадров после посадки

        cv2.imshow("Image", img)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break


def obstacle_loop(detector):
    while detector._running:
        detector.process()


def start_bottle_tracking(drone, frame_reader, target_class_id=39):
    from time import sleep
    print("🚀 Начинаю слежение за объектом")

    w, h = 640, 480
    pid = [0.5, 0.5, 0]
    pError = [0, 0]
    inner_area = 5000
    outer_area = 10000

    detector = ObstacleAvoidance(drone, frame_reader)
    detector.set_active(True)

    frame_thread = threading.Thread(
        target=process_frame,
        args=(drone, w, h, pid, pError, inner_area, outer_area, target_class_id)
    )
    obstacle_thread = threading.Thread(
        target=lambda: obstacle_loop(detector)
    )

    frame_thread.start()
    obstacle_thread.start()

    frame_thread.join()
    detector.stop()
    obstacle_thread.join()