# gui.py (для PyQt GUI)
import sys
import threading
import queue
import json
import os
import struct
import time
import yaml
import config
from audio_manager import AudioManager
from gpt_integration import GPTIntegration
from va_responder import VAResponder
import drone_manager
import build_Fly
import tts
import sounddevice as sd

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QTextEdit, QFrame, QSizePolicy
)
from PyQt5.QtGui import QPainter, QColor, QFont, QPen, QBrush
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, QTimer, QPointF

# --- Содержимое va_core.py (перемещаем сюда для демонстрации, но лучше держать в отдельном файле) ---
CDIR = os.getcwd()
VA_CMD_LIST = yaml.safe_load(
    open('commands.yaml', 'rt', encoding='utf8'),
)


class VACore(QObject):  # Наследуемся от QObject для использования сигналов
    update_log_signal = pyqtSignal(str)
    update_status_signal = pyqtSignal(str)
    update_recognized_signal = pyqtSignal(str)
    update_response_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_running = False
        self.audio_manager = None
        self.gpt_integration = None
        self.va_responder = None
        self.microphone_index = -1  # Будет установлен из GUI

    def set_microphone_index(self, index):
        self.microphone_index = index

    def start_va(self):
        if self.is_running:
            return

        if self.microphone_index == -1:
            self.error_signal("Микрофон не выбран.")
            return

        self.is_running = True
        self.update_status_signal("Запуск...")
        self.update_log_signal("Попытка запуска Джарвиса...")
        try:
            self.audio_manager = AudioManager(
                porcupine_access_key=config.PICOVOICE_TOKEN,
                microphone_index=self.microphone_index,
                vosk_model_path="model_small",
                sound_dir=os.path.join(CDIR, "sound")
            )

            self.gpt_integration = GPTIntegration(
                openai_api_key=config.OPENAI_TOKEN,
                system_message={"role": "system", "content": "Ты голосовой ассистент из железного человека."}
            )

            self.va_responder = VAResponder(
                va_cmd_list=VA_CMD_LIST,
                va_alias=config.VA_ALIAS,
                va_tbr=config.VA_TBR,
                gpt_integration=self.gpt_integration,
                audio_manager=self.audio_manager,
                tts_module=tts,
                drone_manager_module=drone_manager,
                build_fly_module=build_Fly
            )

            self.audio_manager.play_sound("run")
            time.sleep(0.5)
            self.update_status_signal("Ассистент запущен и ожидает активации.")
            self.update_log_signal("Джарвис готов.")
            self.run_loop()

        except Exception as err:
            self.error_signal(f"Ошибка при запуске: {err}")
            self.is_running = False
            self.update_status_signal("Остановлен из-за ошибки.")
            self.update_log_signal(f"Критическая ошибка: {err}")

    def stop_va(self):
        if not self.is_running:
            return
        self.is_running = False
        if self.audio_manager:
            self.audio_manager.stop_recorder()
        self.update_status_signal("Остановлен.")
        self.update_log_signal("Джарвис остановлен.")

    def run_loop(self):
        last_trigger_time = time.time() - 1000

        while self.is_running:
            try:
                pcm = self.audio_manager.recorder.read()
                keyword_index = self.audio_manager.porcupine.process(pcm)

                if keyword_index >= 0:
                    self.audio_manager.recorder.stop()
                    self.audio_manager.play_sound("greet", wait_done=True)
                    self.update_log_signal("Активационное слово распознано: Yes, sir.")
                    self.audio_manager.recorder.start()
                    last_trigger_time = time.time()
                    self.update_status_signal("Ожидание команды...")

                if time.time() - last_trigger_time <= 10:
                    pcm = self.audio_manager.recorder.read()
                    sp = struct.pack("h" * len(pcm), *pcm)

                    if self.audio_manager.kaldi_rec.AcceptWaveform(sp):
                        recognized_text = json.loads(self.audio_manager.kaldi_rec.Result())["text"]
                        self.update_recognized_signal(recognized_text)

                        # Здесь вам нужно будет модифицировать va_responder.respond
                        # чтобы он возвращал сам текст ответа, а не только True/False
                        # или же va_responder должен иметь внутренний механизм для отправки ответа
                        # Например, можно добавить 'response_callback' в конструктор VAResponder
                        # и вызывать его после генерации ответа.
                        # В этом примере я просто имитирую ответ

                        # Пример: Если va_responder.respond() возвращает ответ
                        response_text = "..."  # Получите реальный ответ от va_responder.respond
                        if self.va_responder.respond(recognized_text):  # Предположим, он возвращает True
                            # Если VAResponder может получить ответ, передайте его через сигнал
                            # Например, если respond() возвращает (bool, str)
                            # _, response_text = self.va_responder.respond(recognized_text)
                            # self.update_response_signal(response_text)
                            self.update_response_signal("Обработка команды завершена.")  # Заглушка
                            last_trigger_time = time.time()
                            self.update_status_signal("Обработка команды...")
                        else:
                            self.update_status_signal(
                                "Команда не распознана или не требует ответа. Ожидание активации.")
                        continue

                    elif json.loads(self.audio_manager.kaldi_rec.Result())["text"] == "":
                        if time.time() - last_trigger_time > 10:
                            self.update_status_signal("Время ожидания команды истекло. Ожидание активации.")

            except Exception as err:
                self.error_signal(f"Неожиданная ошибка в VA: {err}")
                self.stop_va()
                break


# --- Конец содержимого va_core.py ---


# --- Пользовательский виджет для отрисовки ядра дрона и его связей ---
class DroneCoreWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Expanding)  # Расширяться, чтобы занимать все доступное место

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)  # Сглаживание

        width = self.width()
        height = self.height()
        center_x, center_y = width / 2, height / 2
        hexagon_size = min(width, height) * 0.25  # Размер центрального шестиугольника

        # --- Рисование центрального шестиугольника и свечения ---
        pen = QPen(QColor("#00FFFF"))  # Светло-голубой для контура
        pen.setWidth(2)
        painter.setPen(pen)

        # Координаты вершин шестиугольника
        points = []
        for i in range(6):
            angle_deg = 60 * i - 30
            angle_rad = 3.14159 / 180 * angle_deg
            x = center_x + hexagon_size * (
                        QPointF.x(QPointF(1, 1)) + QPointF.y(QPointF(1, 1)) - QPointF.x(QPointF(0, 0)) - QPointF.y(
                    QPointF(0, 0))) * 0.0001 * QPointF.x(QPointF(QPointF.x(QPointF(1, 1)), QPointF.x(
                QPointF(1, 1))))  # cos(angle_rad) # Заглушка, чтобы не зависеть от numpy или math
            y = center_y + hexagon_size * (
                        QPointF.x(QPointF(1, 1)) + QPointF.y(QPointF(1, 1)) - QPointF.x(QPointF(0, 0)) - QPointF.y(
                    QPointF(0, 0))) * 0.0001 * QPointF.x(
                QPointF(QPointF.x(QPointF(1, 1)), QPointF.x(QPointF(1, 1))))  # sin(angle_rad) # Заглушка
            points.append(QPointF(x, y))

        # Заглушка для QPointF из math.cos/sin
        import math
        points = []
        for i in range(6):
            angle_deg = 60 * i - 30
            angle_rad = math.pi / 180 * angle_deg
            x = center_x + hexagon_size * math.cos(angle_rad)
            y = center_y + hexagon_size * math.sin(angle_rad)
            points.append(QPointF(x, y))

        painter.drawPolygon(points)

        # Имитация свечения
        pen.setColor(QColor("#00FFFF"))
        pen.setWidth(5)
        pen.setStyle(Qt.DotLine)  # Пунктир
        painter.setPen(pen)
        painter.drawPolygon(points)

        pen.setColor(QColor("#00BFFF"))
        pen.setWidth(8)
        pen.setStyle(Qt.DashLine)  # Штриховая
        painter.setPen(pen)
        painter.drawPolygon(points)

        # Внутренний шестиугольник/точка
        painter.setPen(QPen(QColor("#00FFFF"), 1))
        painter.setBrush(QBrush(QColor("#00FFFF")))
        painter.drawEllipse(center_x - 10, center_y - 10, 20, 20)

        # --- Рисование блоков и линий ---
        # Здесь вам нужно будет рассчитать позиции для каждого блока и нарисовать их
        # а также линии, соединяющие их с центральным шестиугольником.
        # Для каждого блока:
        #   - Нарисуйте скругленный прямоугольник (как на макете)
        #   - Нарисуйте текст (заголовок, подпись)
        #   - Нарисуйте иконку (если есть)
        #   - Нарисуйте линию от центрального шестиугольника к этому блоку

        # Пример одного блока: "Flight Path Planning"
        block_width, block_height = 180, 80
        # Координаты блока относительно центра
        block_x1 = center_x - hexagon_size * 1.8 - block_width / 2
        block_y1 = center_y - hexagon_size * 1.5 - block_height / 2

        block_center_x = block_x1 + block_width / 2
        block_center_y = block_y1 + block_height / 2

        painter.setPen(QPen(QColor("#6A8DFF"), 2))  # Цвет контура
        painter.setBrush(QBrush(QColor("#2C4F6E")))  # Фон блока
        painter.drawRoundedRect(block_x1, block_y1, block_width, block_height, 10, 10)  # Скругленный прямоугольник

        painter.setPen(QPen(Qt.NoPen))
        painter.setBrush(QBrush(QColor("#00FFFF")))  # Цвет иконки
        painter.drawEllipse(block_x1 + 15, block_y1 + 15, 20, 20)  # Пример иконки (кружок)

        painter.setPen(QPen(QColor("white")))
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        painter.drawText(block_x1 + 40, block_y1 + 30, "Flight Path Planning")  # Текст блока

        painter.setPen(QPen(QColor("#A0D0FF")))
        painter.setFont(QFont("Arial", 8))
        painter.drawText(block_x1 + 40, block_y1 + 50, "[Детали]")

        # Линия от центрального шестиугольника к блоку
        pen.setColor(QColor("#00FFFF"))
        pen.setWidth(1.5)
        pen.setStyle(Qt.DotLine)
        painter.setPen(pen)
        painter.drawLine(int(center_x), int(center_y), int(block_center_x), int(block_center_y))

        # Повторите для всех других блоков (Sensor Data Analysis, Automatic Navigation и т.д.)
        # ...


# --- Основное окно GUI ---
class JarvisGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis v3.0 GUI")
        self.setGeometry(100, 100, 1200, 800)

        self.va_core_thread = None
        self.va_core_worker = None

        self._apply_dark_theme()
        self._create_widgets()
        self._populate_microphone_list()

        self.current_mic_index = -1  # Для хранения выбранного индекса микрофона

    def _apply_dark_theme(self):
        # Применение темной синей темы через QSS
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1A2B3C; /* Основной фон */
                color: white;
            }
            QFrame#SidebarFrame { /* ID для боковой панели */
                background-color: #0A1E2B;
                border: 1px solid #2C4F6E;
                border-radius: 5px;
            }
            QPushButton {
                background-color: #2C4F6E; /* Основной цвет кнопок */
                color: white;
                border: 1px solid #345678;
                padding: 8px 15px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #345678; /* Цвет при наведении */
            }
            QPushButton:pressed {
                background-color: #4C7094; /* Цвет при нажатии */
            }
            QPushButton:disabled {
                background-color: #1F384C;
                color: #888888;
                border: 1px solid #1A2B3C;
            }
            QLabel {
                color: white;
            }
            QLabel#StatusLabel { /* ID для метки статуса */
                font-weight: bold;
                color: #9DD0FF; /* Светло-голубой для статуса */
            }
            QComboBox {
                background-color: #2C4F6E;
                color: white;
                border: 1px solid #345678;
                border-radius: 5px;
                padding: 2px;
            }
            QComboBox::drop-down {
                border: 0px; /* Убрать стрелку */
            }
            QComboBox QAbstractItemView {
                background-color: #2C4F6E;
                color: white;
                selection-background-color: #345678;
            }
            QTextEdit {
                background-color: #0A1E2B;
                color: #A0D0FF; /* Светло-голубой для логов */
                border: 1px solid #2C4F6E;
                border-radius: 5px;
                padding: 5px;
            }
            QGroupBox { /* Для LabelFrame в Tkinter */
                border: 1px solid #2C4F6E;
                border-radius: 5px;
                margin-top: 1ex; /* Отступ для заголовка */
                font-weight: bold;
                color: #9DD0FF;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left; /* Позиция заголовка */
                padding: 0 3px;
                background-color: #1A2B3C; /* Фон заголовка */
            }
        """)

    def _create_widgets(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Боковая панель
        sidebar_frame = QFrame(self)
        sidebar_frame.setObjectName("SidebarFrame")  # Устанавливаем ID для QSS
        sidebar_frame.setFixedWidth(180)  # Ширина боковой панели
        sidebar_layout = QVBoxLayout(sidebar_frame)
        sidebar_layout.setContentsMargins(10, 20, 10, 10)
        sidebar_layout.setSpacing(10)

        title_label = QLabel("МЕНЮ", self)
        title_label.setFont(QFont("Arial", 14, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(title_label)

        menu_items = ["Данные", "Управление", "Настройки", "Журнал"]
        for item_text in menu_items:
            btn = QPushButton(item_text, self)
            # btn.setIcon(QIcon("path/to/icon.png")) # Для иконок
            sidebar_layout.addWidget(btn)
        sidebar_layout.addStretch(1)  # Заполнить оставшееся пространство

        main_layout.addWidget(sidebar_frame)

        # Основная рабочая область
        content_frame = QFrame(self)
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(10, 10, 10, 10)

        # Статус и настройки микрофона
        control_groupbox = QFrame(self)  # Используем QFrame с QSS для имитации QGroupBox
        control_groupbox.setStyleSheet("""
            QFrame {
                border: 1px solid #2C4F6E;
                border-radius: 5px;
                margin-top: 1ex;
            }
            QLabel {
                color: #9DD0FF;
                font-weight: bold;
            }
        """)
        control_groupbox.setLayout(QVBoxLayout())

        status_title_label = QLabel("Управление и Статус", control_groupbox)
        status_title_label.setStyleSheet("color: #9DD0FF; font-weight: bold; padding-left: 5px;")
        control_groupbox.layout().addWidget(status_title_label)

        self.status_label = QLabel("Статус: Не запущен", control_groupbox)
        self.status_label.setObjectName("StatusLabel")
        control_groupbox.layout().addWidget(self.status_label)

        mic_layout = QHBoxLayout()
        mic_layout.addWidget(QLabel("Микрофон:", control_groupbox))
        self.microphone_combobox = QComboBox(control_groupbox)
        self.microphone_combobox.currentIndexChanged.connect(self._on_microphone_selected)
        mic_layout.addWidget(self.microphone_combobox)
        control_groupbox.layout().addLayout(mic_layout)

        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Запустить Джарвиса", control_groupbox)
        self.start_button.clicked.connect(self.start_jarvis)
        button_layout.addWidget(self.start_button)
        self.stop_button = QPushButton("Остановить Джарвиса", control_groupbox)
        self.stop_button.clicked.connect(self.stop_jarvis)
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.stop_button)
        control_groupbox.layout().addLayout(button_layout)

        content_layout.addWidget(control_groupbox)

        # Центральный виджет для рисования схемы ядра дрона
        self.drone_core_widget = DroneCoreWidget(self)
        content_layout.addWidget(self.drone_core_widget)

        # Распознанный текст и ответ ассистента
        recognized_title_label = QLabel("Распознанный текст:", self)
        recognized_title_label.setStyleSheet("color: #9DD0FF; font-weight: bold;")
        content_layout.addWidget(recognized_title_label)
        self.recognized_text_label = QLabel("", self)
        self.recognized_text_label.setWordWrap(True)
        content_layout.addWidget(self.recognized_text_label)

        response_title_label = QLabel("Ответ ассистента:", self)
        response_title_label.setStyleSheet("color: #9DD0FF; font-weight: bold;")
        content_layout.addWidget(response_title_label)
        self.response_text_label = QLabel("", self)
        self.response_text_label.setWordWrap(True)
        self.response_text_label.setStyleSheet("font-style: italic; color: #A0D0FF;")
        content_layout.addWidget(self.response_text_label)

        # Логи
        log_title_label = QLabel("Журнал активности:", self)
        log_title_label.setStyleSheet("color: #9DD0FF; font-weight: bold;")
        content_layout.addWidget(log_title_label)
        self.log_text_edit = QTextEdit(self)
        self.log_text_edit.setReadOnly(True)
        content_layout.addWidget(self.log_text_edit)

        main_layout.addWidget(content_frame)

    def _populate_microphone_list(self):
        try:
            devices = sd.query_devices()
            input_devices = []
            for i, device in enumerate(devices):
                if device['max_input_channels'] > 0:
                    input_devices.append(f"{i}: {device['name']}")
            self.microphone_combobox.addItems(input_devices)
            if input_devices:
                # Если config.MICROPHONE_INDEX задан, попробуйте выбрать его
                # self.microphone_combobox.setCurrentIndex(config.MICROPHONE_INDEX)
                self.current_mic_index = int(input_devices[0].split(":")[0])  # По умолчанию первый
            self.log_message(f"Доступные микрофоны загружены.")
        except Exception as e:
            self.log_message(f"Ошибка при получении списка микрофонов: {e}")

    def _on_microphone_selected(self, index):
        selected_mic_str = self.microphone_combobox.currentText()
        try:
            self.current_mic_index = int(selected_mic_str.split(":")[0])
            self.log_message(f"Выбран микрофон: {selected_mic_str} (индекс {self.current_mic_index})")
        except ValueError:
            self.log_message(f"Ошибка при парсинге индекса микрофона: {selected_mic_str}")

    def log_message(self, message):
        self.log_text_edit.append(message)
        self.log_text_edit.verticalScrollBar().setValue(
            self.log_text_edit.verticalScrollBar().maximum())  # Прокрутка вниз

    def update_status(self, status):
        self.status_label.setText(f"Статус: {status}")

    def update_recognized_text(self, text):
        self.recognized_text_label.setText(text)

    def update_response_text(self, text):
        self.response_text_label.setText(text)

    def handle_error(self, error_message):
        self.log_message(f"ОШИБКА: {error_message}")
        self.update_status("Остановлен из-за ошибки.")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.microphone_combobox.setEnabled(True)

    def start_jarvis(self):
        if self.current_mic_index == -1:
            self.log_message("Пожалуйста, выберите микрофон.")
            return

        self.log_message(f"Запуск Джарвиса с микрофоном (индекс): {self.current_mic_index}")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.microphone_combobox.setEnabled(False)

        # Создаем поток для VACore
        self.va_core_thread = QThread()
        self.va_core_worker = VACore()
        self.va_core_worker.set_microphone_index(self.current_mic_index)
        self.va_core_worker.moveToThread(self.va_core_thread)

        # Подключаем сигналы к слотам GUI
        self.va_core_worker.update_log_signal.connect(self.log_message)
        self.va_core_worker.update_status_signal.connect(self.update_status)
        self.va_core_worker.update_recognized_signal.connect(self.update_recognized_text)
        self.va_core_worker.update_response_signal.connect(self.update_response_text)
        self.va_core_worker.error_signal.connect(self.handle_error)

        # Запускаем worker при старте потока
        self.va_core_thread.started.connect(self.va_core_worker.start_va)
        self.va_core_thread.start()

    def stop_jarvis(self):
        if self.va_core_worker:
            self.log_message("Остановка Джарвиса...")
            self.va_core_worker.stop_va()
            # Дожидаемся завершения потока
            if self.va_core_thread.isRunning():
                self.va_core_thread.quit()
                self.va_core_thread.wait()  # Ждем завершения потока
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.microphone_combobox.setEnabled(True)
            self.update_status("Остановлен.")
            self.log_message("Джарвис полностью остановлен.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = JarvisGUI()
    gui.show()
    sys.exit(app.exec_())