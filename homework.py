import logging
import os
from functools import wraps

import requests
import sys
import time
from logging import StreamHandler
from logging.handlers import RotatingFileHandler

import telegram
from dotenv import load_dotenv

from exceptions import (
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

RETRY_PERIOD = 6
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

ERROR_MESSAGES = {
    'send_message': 'Сбой при отправке сообщения: "{message}" в Телеграмм '
                    '- {error}',
    'check_tokens': {
        'KeyError': 'Нет доступа к токенам: {lost_tokens}',
        'critical_error': '{error}. Завершаю работу!'
    },
    'get_api_answer': {
        'requests.ConnectionError': 'Непредвиденная ошибка при запросе к API '
                                    'Практикума. Параметры запроса: '
                                    'url={ENDPOINT}, headers={HEADERS}. '
                                    'Ошибка - {error}',
        'ServerAccessError': 'Ошибка доступа к API Практикума. '
                             'Параметры запроса: url={ENDPOINT}, '
                             'headers={HEADERS}. '
                             'Статус.код: {status_code}',
        'ServerResponseError': 'Отказ в обслуживании сервера Практикума. '
                               'Параметры запроса: url={ENDPOINT}, '
                               'headers={HEADERS}. '
                               'Сообщение сервера: {message}'
    },
    'check_response': {
        'KeyError': 'Отсутствует необходимый ключ "homeworks" в ответе API',
        'TypeError1': 'Ответ API не содержит словаря',
        'TypeError2': 'Неверный тип домашней работы. Тип полученной домашней '
                      'работы: {type_hw}, должен быть list'
    },
    'parse_status': {
        'KeyError1': 'В "homework" отсутствует ключ "homework_name"',
        'KeyError2': 'В "homework" отсутствует ключ "status"',
        'KeyError3': 'Неизвестный статус домашней работы: {status}'
    },
    'program_crash': 'Сбой в работе программы: {error}',
    'access_error': 'Ошибка доступа: {error}',
    'connection_problems': 'Неполадки соединения: {error}'
}
SUCCESSFUL_MESSAGES = {
    'send_message': 'Удачная отправка сообщения: "{message}" в Телеграм',
    'parse_status': 'Изменился статус проверки работы "{homework_name}". '
                    '{verdict}',
    'bot_init': 'Бот включен.',
    'no_new_status': 'Новые статусы в домашней работе отсутствуют'
}


def cache_mesage(func):
    """Декоратор для кэширования сообщений."""
    message_cache = []

    @wraps(func)
    def wrapper(bot, message):
        if message in message_cache:
            if len(message_cache) > 25:
                message_cache.clear()
        else:
            func(bot, message)
            message_cache.append(message)

    return wrapper


def check_tokens():
    """Проверяет доступность переменных окружения."""
    lost_tokens = []
    for name in ['PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID']:
        if not globals()[name]:
            lost_tokens.append(name)
    if lost_tokens:
        lost_tokens = ", ".join(lost_tokens)
        raise KeyError(ERROR_MESSAGES[check_tokens.__name__]['KeyError']
                       .format(lost_tokens=lost_tokens))


# @cache_mesage
def send_message(bot, message):
    """Отправляет сообщение в Телеграмм-чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(SUCCESSFUL_MESSAGES[send_message.__name__].format(
            message=message
        ))
    except telegram.TelegramError as error:
        logger.error(
            ERROR_MESSAGES[send_message.__name__].format(
                message=message,
                error=error
            ), exc_info=True)


def get_api_answer(timestamp):
    """Делает запрос к эндпойнту API-сервиса."""
    timestamp = timestamp or int(time.time())
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp})
    except requests.RequestException as error:
        raise ConnectionError(
            ERROR_MESSAGES[get_api_answer.__name__]['requests.ConnectionError']
            .format(ENDPOINT=ENDPOINT, HEADERS=HEADERS, error=error)
        )
    if response.status_code != 200:
        raise ServerAccessError(
            ERROR_MESSAGES[get_api_answer.__name__]['ServerAccessError']
            .format(ENDPOINT=ENDPOINT, HEADERS=HEADERS,
                    status_code=response.status_code))
    response = response.json()
    if 'error' in response.keys() or 'code' in response.keys():
        message = []
        for key, value in response.values():
            message.append(f'{key} - {value}')
        message = ', '.join(message)
        raise ServerResponseError(
            ERROR_MESSAGES[get_api_answer.__name__]['ServerResponseError']
            .format(ENDPOINT=ENDPOINT, HEADERS=HEADERS, message=message))
    return response


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError(ERROR_MESSAGES[check_response.__name__]['TypeError1'])
    if 'homeworks' not in response.keys():
        raise KeyError(ERROR_MESSAGES[check_response.__name__]['KeyError'])
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        type_hw = type(homeworks)
        raise TypeError(
            ERROR_MESSAGES[check_response.__name__]['TypeError2']
            .format(type_hw=type_hw))
    return homeworks


def parse_status(homework):
    """Извлекает статус домашней работы."""
    if 'homework_name' not in homework:
        raise KeyError(ERROR_MESSAGES[parse_status.__name__]['KeyError1'])
    if 'status' not in homework:
        raise KeyError(ERROR_MESSAGES[parse_status.__name__]['KeyError2'])
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise KeyError(ERROR_MESSAGES[parse_status.__name__]['KeyError3']
                       .format(status=status))
    homework_name = homework['homework_name']
    verdict = HOMEWORK_VERDICTS[status]
    return (SUCCESSFUL_MESSAGES[parse_status.__name__]
            .format(homework_name=homework_name, verdict=verdict))


def main():
    """Основная логика работы бота."""
    try:
        check_tokens()
    except KeyError as error:
        logger.critical(
            ERROR_MESSAGES[check_tokens.__name__]['critical_error']
            .format(error=error))
        sys.exit(1)
    try:
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
        send_message(bot, SUCCESSFUL_MESSAGES['bot_init'])
        logger.debug(SUCCESSFUL_MESSAGES['bot_init'])
    except telegram.TelegramError as error:
        logger.error(error, exc_info=True)
    timestamp = int(time.time())
    while True:
        try:
            response = get_api_answer(timestamp)
            new_homeworks = check_response(response)
            if not new_homeworks:
                current_message = SUCCESSFUL_MESSAGES['no_new_status']
                logger.debug(current_message)
            else:
                current_message = parse_status(new_homeworks[0])
            timestamp = response['current_date']
        except ConnectionError as error:
            current_message = ERROR_MESSAGES['connection_problems'].format(
                error=error)
            logger.error(current_message)
        except ServerAccessError as error:
            current_message = ERROR_MESSAGES['access_error'].format(
                error=error)
            logger.error(current_message)
        except ServerResponseError as error:
            current_message = ERROR_MESSAGES['programm_crash'].format(
                error=error)
            logger.error(current_message)
        except KeyError as error:
            current_message = ERROR_MESSAGES['programm_crash'].format(
                error=error)
            logger.error(current_message)
        except TypeError as error:
            current_message = ERROR_MESSAGES['programm_crash'].format(
                error=error)
            logger.error(current_message)
        except Exception as error:
            current_message = ERROR_MESSAGES['programm_crash'].format(
                error=error)
            logger.error(current_message)
        finally:
            send_message(bot, current_message)
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
