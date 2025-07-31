#Инициализация ЯМ

import openai
from openai import error
from rich import print

class GPTIntegration:
    def __init__(self, openai_api_key, system_message):
        openai.api_key = openai_api_key
        self.system_message = system_message
        self.message_log = [system_message]

    def get_answer(self):
        model_engine = "gpt-4o-mini"
        max_tokens = 256
        try:
            response = openai.ChatCompletion.create(
                model=model_engine,
                messages=self.message_log,
                max_tokens=max_tokens,
                temperature=0.7,
                top_p=1,
                stop=None
            )
        except (error.TryAgain, error.ServiceUnavailableError):
            return "ChatGPT перегружен!"
        except openai.OpenAIError as ex:
            if ex.code == "context_length_exceeded":
                self.message_log = [self.system_message, self.message_log[-1]]
                return self.get_answer() # Рекурсивный вызов с очищенным контекстом
            else:
                return "OpenAI токен не рабочий."

        for choice in response.choices:
            if "text" in choice:
                return choice.text

        return response.choices[0].message.content

    def add_message(self, role, content):
        self.message_log.append({"role": role, "content": content})

    def clear_message_log(self):
        self.message_log = [self.system_message]