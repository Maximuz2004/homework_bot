import logging
import os
import sys
import time
from logging import StreamHandler
from logging.handlers import RotatingFileHandler

import requests
import telegram
from dotenv import load_dotenv

from exceptions import (
    SendMessageError,
    ServerAccessError,
    ServerResponseError,
)

load_dotenv()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s '
    '- %(levelname)s '
    '- %(name)s '
    '- имя функции: %(funcName)s '
    '- строка: %(lineno)d '
    '- %(message)s'
)
stream_handler = StreamHandler(stream=sys.stdout)
file_handler = RotatingFileHandler(
    __file__ + '.log',
    encoding='utf-8',
    maxBytes=50000000,
    backupCount=3
)
for handler in [stream_handler, file_handler]:
    handler.setFormatter(formatter)
    logger.addHandler(handler)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TOKENS_LIST = ['PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID']

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

TOKENS_ERROR = 'Нет доступа к токенам: {lost_tokens}. Завершаю работу!'
SEND_MESSAGE_ERROR = ('Сбой при отправке сообщения: "{message}" в Телеграмм '
                      '- {error}')
SUCCESSFUL_SENDING = 'Удачная отправка сообщения: "{message}" в Телеграм'
CONNECTION_ERROR = ('Непредвиденная ошибка при запросе к API Практикума. '
                    'Параметры запроса: {url}, {headers}, '
                    '{params}. Ошибка - {error}')
SERVER_ACCESS_ERROR = ('Ошибка доступа к API Практикума. Параметры запроса: '
                       '{url}, {headers}, {params}. Статус код: {status_code}')
SERVER_RESPONSE_ERROR = ('Отказ в обслуживании сервера Практикума. '
                         'Параметры запроса: {url}, {headers}, '
                         '{params}. Сообщение сервера: {message}')
RESPONSE_TYPE_ERROR = ('Некорректный ответ от API. Получен {response_type}, '
                       'ожидался dict')
NO_HOMEWORKS_ERROR = 'Отсутствует необходимый ключ "homeworks" в ответе API'
HOMEWORKS_TYPE_ERROR = ('Неверный тип домашней работы. Тип полученной '
                        'домашней работы: {received_type}, должен быть list')
NON_HOMEWORK_NAME_ERROR = 'В "homework" отсутствует ключ "homework_name"'
NON_HOMEWORK_STATUS = 'В "homework" отсутствует ключ "status"'
UNKNOWN_HOMEWORK_STATUS = 'Неизвестный статус домашней работы: {status}'
PROGRAM_CRASH_ERROR = 'Сбой в работе программы: {error}'
PARSE_STATUS = 'Изменился статус проверки работы "{homework_name}". {verdict}'
NO_NEW_STATUS_MESSAGE = 'Новые статусы в домашней работе отсутствуют'
ERROR_KEYS_LIST = ['error', 'code']


def check_tokens():
    """Проверяет доступность переменных окружения."""
    lost_tokens = [token for token in TOKENS_LIST if not globals()[token]]
    if lost_tokens:
        logger.critical(TOKENS_ERROR.format(lost_tokens=lost_tokens))
        raise ValueError(TOKENS_ERROR.format(lost_tokens=lost_tokens))


def send_message(bot, message):
    """Отправляет сообщение в Телеграмм-чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(SUCCESSFUL_SENDING.format(message=message))
    except telegram.TelegramError as error:
        logger.exception(SEND_MESSAGE_ERROR.format(
            message=message,
            error=error
        ))
        raise SendMessageError(error)


def get_api_answer(timestamp):
    """Делает запрос к эндпойнту API-сервиса."""
    timestamp = timestamp or int(time.time())
    request_params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp}
    }
    try:
        response = requests.get(**request_params)
    except requests.RequestException as error:
        raise ConnectionError(
            CONNECTION_ERROR.format(error=error, **request_params)
        )
    if response.status_code != 200:
        raise ServerAccessError(
            SERVER_ACCESS_ERROR.format(
                status_code=response.status_code, **request_params))
    response = response.json()
    for key in ERROR_KEYS_LIST:
        if key in response:
            raise ServerResponseError(SERVER_RESPONSE_ERROR.format(
                message=f'{key}:{response[key]}', **request_params
            ))
    return response


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError(
            RESPONSE_TYPE_ERROR.format(response_type=type(response)))
    if 'homeworks' not in response:
        raise KeyError(NO_HOMEWORKS_ERROR)
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError(HOMEWORKS_TYPE_ERROR.format(
            received_type=type(homeworks)))
    return homeworks


def parse_status(homework):
    """Извлекает статус домашней работы."""
    if 'homework_name' not in homework:
        raise KeyError(NON_HOMEWORK_NAME_ERROR)
    if 'status' not in homework:
        raise KeyError(NON_HOMEWORK_STATUS)
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(UNKNOWN_HOMEWORK_STATUS.format(status=status))
    return PARSE_STATUS.format(
        homework_name=homework['homework_name'],
        verdict=HOMEWORK_VERDICTS[status]
    )


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_message = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if not homeworks:
                message = NO_NEW_STATUS_MESSAGE
                logger.debug(message)
            else:
                message = parse_status(homeworks[0])
            if message != last_message:
                send_message(bot, message)
                timestamp = response.get('current_date', timestamp)
                last_message = message
        except SendMessageError as error:
            logger.error(PROGRAM_CRASH_ERROR.format(error=error))
        except Exception as error:
            message = PROGRAM_CRASH_ERROR.format(error=error)
            logger.error(message)
            if message != last_message:
                send_message(bot, message)
                last_message = message
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
