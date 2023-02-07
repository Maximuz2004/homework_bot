class ServerAccessError(Exception):
    """Нет доступа API Практикума"""
    pass


class ServerResponseError(Exception):
    """Ошибки в ответе от API Практикума"""
    pass

