import time
import threading
import cv2

class ObstacleAvoidance:
    def __init__(self, tello, frame_read):
        self.tello = tello
        self.frame_read = frame_read

        self.CANNY_THRESHOLD1 = 50
        self.CANNY_THRESHOLD2 = 150
        self.MIN_CONTOUR_AREA = 5000
        self.FRAME_WIDTH = 960
        self.FRAME_HEIGHT = 720
        self.AVOID_SPEED = 20

        self.DANGER_DISTANCE_THRESHOLD = 60  # Чем меньше — тем ближе объект
        self.turning = False

        self.tello_vx = 0
        self.tello_vy = 0
        self.tello_vz = 0
        self.tello_yaw = 0
        self.send_rc_commands = False
        self.auto_avoidance_active = False
        self.control_thread = threading.Thread(target=self.drone_control_thread)
        self.control_thread.daemon = True
        self.control_thread.start()
        self._running = False

        # Для усреднения и фильтрации ложных срабатываний
        self.wall_detection_history = []
        self.HISTORY_LENGTH = 5  # Количество кадров для усреднения
        self.WALL_DETECTION_THRESHOLD = 3  # Срабатывание при 3 и более подтверждениях

    def is_in_central_zone(self, bbox, zone_ratio=0.5):
        """Проверяет, находится ли объект в центральной зоне кадра"""
        x, y, w, h = bbox
        center_x = x + w / 2
        center_y = y + h / 2
        zone_x_min = self.FRAME_WIDTH * (0.5 - zone_ratio / 2)
        zone_x_max = self.FRAME_WIDTH * (0.5 + zone_ratio / 2)
        zone_y_min = self.FRAME_HEIGHT * (0.5 - zone_ratio / 2)
        zone_y_max = self.FRAME_HEIGHT * (0.5 + zone_ratio / 2)
        return zone_x_min <= center_x <= zone_x_max and zone_y_min <= center_y <= zone_y_max

    def estimate_distance(self, contour):
        _, _, w, h = cv2.boundingRect(contour)
        if w * h == 0:
            return float('inf')
        return 1000 / (w * h)

    def process(self):
        frame = self.frame_read.frame
        if frame is None:
            return

        frame = cv2.resize(frame, (self.FRAME_WIDTH, self.FRAME_HEIGHT))
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, self.CANNY_THRESHOLD1, self.CANNY_THRESHOLD2)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        obstacles = [cnt for cnt in contours if cv2.contourArea(cnt) > self.MIN_CONTOUR_AREA]

        print(f"[DEBUG] Кол-во препятствий: {len(obstacles)}")

        if self.turning:
            print("[INFO] В процессе разворота — команды движения не отправляются")
            return

        wall_detected_this_frame = False

        for cnt in obstacles:
            x, y, w, h = cv2.boundingRect(cnt)
            distance = self.estimate_distance(cnt)

            # Фильтруем объекты: только достаточно большие и в центре кадра считаем стеной
            if distance < self.DANGER_DISTANCE_THRESHOLD and self.is_in_central_zone((x, y, w, h)):
                print(f"🧱 Обнаружена глухая стена — выполняем разворот")
                wall_detected_this_frame = True

                # Нарисуем на кадре прямоугольник (для отладки)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
                break

        # Добавляем результат в историю и усредняем
        self.wall_detection_history.append(wall_detected_this_frame)
        if len(self.wall_detection_history) > self.HISTORY_LENGTH:
            self.wall_detection_history.pop(0)

        wall_detections_count = sum(self.wall_detection_history)

        if wall_detections_count >= self.WALL_DETECTION_THRESHOLD:
            # Подтверждена стена — разворот
            self.turning = True
            self.tello.rotate_clockwise(180)
            time.sleep(2)
            self.turning = False
            self.wall_detection_history.clear()
            print("[INFO] Разворот выполнен.")
            return

        # Если стены нет — отправляем команды остановки (можно доработать логику движения)
        self.tello.send_rc_control(0, 0, 0, 0)
        print("✅ Препятствий нет — остаёмся на месте.")

        # Показываем кадр с отладочной разметкой (по желанию)
        #cv2.imshow("Obstacle Avoidance Debug", frame)
        #cv2.waitKey(1)

    def drone_control_thread(self):
        while True:
            if self.send_rc_commands:
                self.tello.send_rc_control(
                    self.tello_vx,
                    self.tello_vy,
                    self.tello_vz,
                    self.tello_yaw
                )
            time.sleep(0.05)

    def start(self):
        self._running = True

    def stop(self):
        self._running = False
        self.send_rc_commands = False
        self.tello.send_rc_control(0, 0, 0, 0)

    def set_active(self, active: bool):
        self.auto_avoidance_active = active
