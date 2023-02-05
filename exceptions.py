class ServerError(Exception):
    """Нет ответа от API Практикума"""
    pass

class KeysNotFoundExeption(Exception):
    """Отсутствуют необходимые ключи в ответе от API"""
    pass

class StatusKeysException(Exception):
    """Отстствуют верные ключи в домашнем задании"""
    pass

class UnknownStatusException(Exception):
    """Получен неизвестный статус в домашней работе"""
    pass