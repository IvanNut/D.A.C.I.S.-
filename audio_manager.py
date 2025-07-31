#Управление аудиовходом (PvRecorder, Porcupine, Vosk) и воспроизведением звуков (Simpleaudio, PyCaw).

import os
import queue
import random
import sys
import time
from ctypes import POINTER, cast

import pvporcupine
import simpleaudio as sa
import vosk
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from rich import print

# ИСПРАВЛЕНИЕ: Импортируем PvRecorder из pvrecorder
from pvrecorder import PvRecorder


class AudioManager:
    def __init__(self, porcupine_access_key, microphone_index, vosk_model_path, sound_dir):
        self.CDIR = os.getcwd()
        self.sound_dir = sound_dir

        # PORCUPINE
        self.porcupine = pvporcupine.create(
            access_key=porcupine_access_key,
            keywords=['jarvis'],
            sensitivities=[1]
        )

        # VOSK
        self.model = vosk.Model(vosk_model_path)
        self.samplerate = 16000
        self.q = queue.Queue()  # Очередь для vosk, если используется потоковая обработка
        self.kaldi_rec = vosk.KaldiRecognizer(self.model, self.samplerate)

        # PvRecorder
        # ИСПРАВЛЕНИЕ: Используем PvRecorder напрямую
        self.recorder = PvRecorder(device_index=microphone_index, frame_length=self.porcupine.frame_length)
        self.recorder.start()
        print('Using device: %s' % self.recorder.selected_device)

    def play_sound(self, phrase, wait_done=True):
        filename = os.path.join(self.sound_dir, "")

        if phrase == "greet":
            filename += f"greet{random.choice([1, 2, 3])}.wav"
        elif phrase == "ok":
            filename += f"ok{random.choice([1, 2, 3])}.wav"
        elif phrase == "not_found":
            filename += "not_found.wav"
        elif phrase == "thanks":
            filename += "thanks.wav"
        elif phrase == "run":
            filename += "run.wav"
        elif phrase == "stupid":
            filename += "stupid.wav"
        elif phrase == "ready":
            filename += "ready.wav"
        elif phrase == "off":
            filename += "off.wav"
        else:
            filename = phrase  # Если передается полный путь к файлу

        if wait_done:
            self.recorder.stop()

        try:
            wave_obj = sa.WaveObject.from_wave_file(filename)
            play_obj = wave_obj.play()

            if wait_done:
                play_obj.wait_done()
                self.recorder.start()
        except FileNotFoundError:
            print(f"Ошибка: Аудиофайл не найден: {filename}")
            if wait_done:
                self.recorder.start()  # Возобновить запись даже при ошибке

    def set_volume_mute(self, mute: bool):
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMute(1 if mute else 0, None)

    def stop_recorder(self):
        if self.recorder:
            self.recorder.delete()
        if self.porcupine:
            self.porcupine.delete()