from djitellopy import TelloSwarm
import time

# Инициализация дронов
swarm = TelloSwarm.fromIps(['192.168.0.120', '192.168.0.121'])

# Подключение к дронам
swarm.connect()

# Взлет дронов
swarm.takeoff()

# Дрон 1 выполняет сальто
swarm.tello[0].flip('f')  # 'f' - вперед
time.sleep(2)

# Дрон 2 выполняет сальто
swarm.tello[1].flip('b')  # 'b' - назад
time.sleep(2)

# Приземление дронов
swarm.land()