import logging
import os
import requests
import sys
import time
from logging import StreamHandler

from dotenv import load_dotenv
import telegram

from exceptions import (
    ServerError,
    KeysNotFoundExeption,
    StatusKeysException,
    UnknownStatusException
)

load_dotenv()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(name)s - %(message)s')
handler = StreamHandler(stream=sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверяет доступность переменных окружения."""
    if not all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
        logger.critical(
            'Отсутствуют обязательные переменные окружения. Завершаю работу!'
        )
        sys.exit(1)


def send_message(bot, message):
    """Отправляет сообщение в Телеграмм-чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'Удачная отправка сообщения в Телеграм: {message}')
    except telegram.TelegramError as error:
        logger.error(f'Сбой при отправке сообщения в Телеграмм: {error}')


def get_api_answer(timestamp):
    """Делает запрос к эндпойнту API-сервиса."""
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp})
    except requests.RequestException as error:
        raise ServerError(f'Непредвиденная ошибка при доступе к API: {error}')
    if response.status_code != 200:
        raise ServerError(f'Непредвиденная ошибка при доступе к API '
                          f'Практикума. Статус.код: {response.status_code}')
    return response.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError(f'Неверный тип ответа от API. '
                        f'Тип полученного ответа: {type(response)}, '
                        f'должен быть dict')
    if not {'current_date', 'homeworks'}.issubset(set(response.keys())):
        raise KeysNotFoundExeption(
            'Отсутствуют необходимые ключи в ответе API')
    homework = response.get('homeworks')
    if not isinstance(homework, list):
        raise TypeError(f'Неверный тип домашней работы.'
                        f' Тип полученной домашней работы: {type(homework)}, '
                        f'должен быть list')
    return homework


def parse_status(homework):
    """Извлекает статус домашней работы."""
    homework_name = homework.get('homework_name')
    verdict = homework.get('status')
    if not all([homework_name, verdict]):
        raise StatusKeysException('Ответ от API несодержит необходимых ключей:'
                                  ' "homework_name"  и "status"')
    if verdict in HOMEWORK_VERDICTS:
        homework_name = homework['homework_name']
        verdict = HOMEWORK_VERDICTS.get(homework['status'])
        return f'Изменился статус проверки работы "{homework_name}". {verdict}'
    raise UnknownStatusException(f'Неизвестный статус добашней работы '
                                 f'в ответе API: {verdict}')


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    send_message(bot, 'Бот включен!')
    logger.debug('Бот Включен.')
    timestamp = int(time.time())
    current_message = ''
    previous_message = ''

    while True:
        try:
            response = get_api_answer(timestamp)
            new_homework = check_response(response)
            if not new_homework:
                current_message = 'Новые статусы в домашней работе отсутствуют'
                logger.debug(current_message)
            else:
                current_message = parse_status(new_homework[0])
                if current_message != previous_message:
                    send_message(bot, current_message)

        except Exception as error:
            current_message = f'Сбой в работе программы: {error}'
            logger.error(current_message)
            if current_message != previous_message:
                send_message(bot, current_message)

        finally:
            previous_message = current_message
            time.sleep(RETRY_PERIOD)
            timestamp = int(time.time())


if __name__ == '__main__':
    main()
