class ServerAccessError(Exception):
    """Нет доступа API Практикума"""
    pass


class ServerResponseError(Exception):
    """Ошибки в ответе от API Практикума"""
    pass

class SendMessageError(Exception):
    """Ошибка при отправке сообщения в Телеграмм"""
    pass
