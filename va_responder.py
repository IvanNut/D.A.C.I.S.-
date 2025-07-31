#Обработка голосовых команд, распознавание команд и выполнение соответствующих действий.

import subprocess
import time
import os
from fuzzywuzzy import fuzz
from rich import print
import sys
import re

class VAResponder:
    def __init__(self, va_cmd_list, va_alias, va_tbr, gpt_integration, audio_manager, tts_module, drone_manager_module, build_fly_module):
        self.CDIR = os.getcwd()
        self.VA_CMD_LIST = va_cmd_list
        self.VA_ALIAS = va_alias
        self.VA_TBR = va_tbr
        self.gpt_integration = gpt_integration
        self.audio_manager = audio_manager
        self.tts = tts_module
        self.drone_manager = drone_manager_module
        self.build_fly = build_fly_module

    def extract_and_clean_python_code(self, response_text):
        """
        Извлекает блок Python-кода из текста и удаляет из него комментарии.
        """
        # Ищем блок кода, который начинается с ```python и заканчивается на ```
        match = re.search(r"```python\n(.*?)```", response_text, re.DOTALL)
        if match:
            python_code = match.group(1)
            # Удаляем однострочные комментарии (# ...)
            cleaned_code = re.sub(r"#.*$", "", python_code, flags=re.MULTILINE)
            # Удаляем многострочные комментарии/docstrings ("""...""" или '''...''')
            cleaned_code = re.sub(r'("""[^"]*"""|\'\'\'[^\']*\'\'\')', '', cleaned_code, flags=re.DOTALL)
            # Удаляем пустые строки, которые могли появиться после удаления комментариев
            cleaned_code = "\n".join([line for line in cleaned_code.splitlines() if line.strip()])
            return cleaned_code
        return ""  # Возвращаем пустую строку, если блок кода не найден

    def respond(self, voice: str) -> bool:
        print(f"Распознано: {voice}")

        voice = voice.lower().strip()
        if not voice:
            return False

        # Команды для дронов
        if fuzz.ratio(voice, "дроны запуск") > 75:
            self.drone_manager.initialize_drones()
            self.tts.va_speak("Дроны инициализированы и готовы к работе.")
            return True

        for drone_name in self.drone_manager.DRONE_IPS.keys():
            if fuzz.token_set_ratio(voice, drone_name) > 75:
                command = voice.replace(drone_name, "").strip()
                print(f'Распознана команда для дрона {drone_name}: {command}')
                response = self.drone_manager.execute_drone_command(drone_name, command)
                if response:
                    self.tts.va_speak(response)
                return True

        # Генерация и выполнение Python-кода через GPT
        words = voice.split()
        if words and fuzz.ratio(words[0], "выполни") > 75:
            self.gpt_integration.add_message("user", f"Только код на Python(Без использования ```python) для управления с двумя дронами дроном Tello (В коде ты обязательно прописываешь библиотеки которые используются), используй библиотеку from djitellopy import TelloSwarm: {voice}. используй swarm = TelloSwarm.fromIps(['192.168.0.120','192.168.0.121']). Ответ без ```.")
            response = self.gpt_integration.get_answer()
            print(f"GPT Raw Response:\n{response}")
            script_path = "tello_command.py"
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(response)
            subprocess.run([sys.executable, script_path]) # Используем sys.executable для запуска
            self.tts.va_speak("Код сгенерирован и запущен")
            time.sleep(0.5)
            return True # Важно, чтобы после выполнения кода мы вернулись в режим ожидания

        # Стандартные команды голосового ассистента
        filtered_cmd = self._filter_cmd(voice)
        recognized_cmd = self._recognize_cmd(filtered_cmd)

        if recognized_cmd['percent'] > 60:
            self._execute_cmd(recognized_cmd['cmd'], voice)
            return True

        return False

    def _filter_cmd(self, raw_voice: str) -> str:
        cmd = raw_voice
        for x in self.VA_ALIAS:
            cmd = cmd.replace(x, "").strip()
        for x in self.VA_TBR:
            cmd = cmd.replace(x, "").strip()
        return cmd

    def _recognize_cmd(self, cmd: str) -> dict:
        rc = {'cmd': '', 'percent': 0}
        for c, v_list in self.VA_CMD_LIST.items():
            for x in v_list:
                vrt = fuzz.ratio(cmd, x)
                if vrt > rc['percent']:
                    rc['cmd'] = c
                    rc['percent'] = vrt
        return rc

    def _execute_cmd(self, cmd: str, voice: str):
        if cmd == 'connect_drones':
            ssid = "drone"
            password = "12345678"
            subprocess.run(["python", "skynet.py", "-s", ssid, "-p", password])
            self.audio_manager.play_sound("ok")
        elif cmd == 'build_drones':
            self.build_fly.build_formation(self.drone_manager.drones)
        elif cmd == 'down_drones':
            self.build_fly.land_all_drones(self.drone_manager.drones)
        elif cmd == 'sound_off':
            self.audio_manager.play_sound("ok", True)
            self.audio_manager.set_volume_mute(True)
        elif cmd == 'sound_on':
            self.audio_manager.set_volume_mute(False)
            self.audio_manager.play_sound("ok")
        elif cmd == 'thanks':
            self.audio_manager.play_sound("thanks")
        elif cmd == 'stupid':
            self.audio_manager.play_sound("stupid")
        elif cmd == 'switch_to_headphones':
            self.audio_manager.play_sound("ok")
            subprocess.check_call([f'{self.CDIR}\\custom-commands\\Switch to headphones.exe'])
            time.sleep(0.5)
            self.audio_manager.play_sound("ready")
        elif cmd == 'switch_to_dynamics':
            self.audio_manager.play_sound("ok")
            subprocess.check_call([f'{self.CDIR}\\custom-commands\\Switch to dynamics.exe'])
            time.sleep(0.5)
            self.audio_manager.play_sound("ready")
        elif cmd == 'off':
            self.audio_manager.play_sound("off", True)
            self.audio_manager.stop_recorder()
            exit(0)