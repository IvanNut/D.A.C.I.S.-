import json
import os
import struct
import time
from rich import print
import yaml
import config
from audio_manager import AudioManager
from gpt_integration import GPTIntegration
from va_responder import VAResponder
import drone_manager
import build_Fly
import tts

CDIR = os.getcwd()
VA_CMD_LIST = yaml.safe_load(
    open('commands.yaml', 'rt', encoding='utf8'),
)

def main():
    print(f"Jarvis (v3.0) начал свою работу ...")

    audio_manager = AudioManager(
        porcupine_access_key=config.PICOVOICE_TOKEN,
        microphone_index=config.MICROPHONE_INDEX,
        vosk_model_path="model_small",
        sound_dir=os.path.join(CDIR, "sound")
    )

    gpt_integration = GPTIntegration(
        openai_api_key=config.OPENAI_TOKEN,
        system_message={"role": "system", "content": "Ты голосовой ассистент из железного человека."}
    )

    va_responder = VAResponder(
        va_cmd_list=VA_CMD_LIST,
        va_alias=config.VA_ALIAS,
        va_tbr=config.VA_TBR,
        gpt_integration=gpt_integration,
        audio_manager=audio_manager,
        tts_module=tts,
        drone_manager_module=drone_manager,
        build_fly_module=build_Fly
    )

    audio_manager.play_sound("run")
    time.sleep(0.5)

    last_trigger_time = time.time() - 1000  # Время последнего срабатывания активационного слова

    while True:
        try:
            pcm = audio_manager.recorder.read()
            keyword_index = audio_manager.porcupine.process(pcm)

            if keyword_index >= 0:
                audio_manager.recorder.stop()
                audio_manager.play_sound("greet", wait_done=True)
                print("Yes, sir.")
                audio_manager.recorder.start()  # Предотвращаем самозапись
                last_trigger_time = time.time()

            # Слушаем команды в течение 10 секунд после активации
            while time.time() - last_trigger_time <= 10:
                pcm = audio_manager.recorder.read()
                sp = struct.pack("h" * len(pcm), *pcm)

                if audio_manager.kaldi_rec.AcceptWaveform(sp):
                    recognized_text = json.loads(audio_manager.kaldi_rec.Result())["text"]
                    if va_responder.respond(recognized_text):
                        last_trigger_time = time.time()  # Обновляем время, если команда распознана

                    break  # Выходим из внутреннего цикла после обработки команды или тишины

        except Exception as err:
            print(f"Неожиданная ошибка: {err=}, {type(err)=}")
            audio_manager.stop_recorder()
            raise


if __name__ == "__main__":
    main()