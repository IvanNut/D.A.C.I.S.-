# drone_utils.py

import threading
import time

def keep_alive(drone):
    """
    Отправляет дрону команду rc 0 0 0 0 каждые 5 секунд,
    чтобы предотвратить его автоматическую посадку.
    Запускается в отдельном потоке.
    """
    def loop():
        while True:
            try:
                drone.send_control_command("rc 0 0 0 0")
                time.sleep(5)
            except Exception as e:
                print(f"⚠️ Ошибка поддержки активности: {e}")
                break  # Если дрон отключился — завершаем поток

    # Запускаем "сердцебиение" в отдельном фоновом потоке
    threading.Thread(target=loop, daemon=True).start()
