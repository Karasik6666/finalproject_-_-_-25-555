from __future__ import annotations


class ValutaTradeError(Exception):
    pass

class ValidationError(ValutaTradeError):
    pass


class AuthError(ValutaTradeError):
    pass


class NotLoggedInError(ValutaTradeError):
    pass


class InsufficientFundsError(ValutaTradeError):
    def __init__(self, available: float, required: float, code: str) -> None:
        self.available = available
        self.required = required
        self.code = code

        message = (
            f"Недостаточно средств: доступно {available} {code}, "
            f"требуется {required} {code}"
        )
        super().__init__(message)


class CurrencyNotFoundError(ValutaTradeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Неизвестная валюта '{code}'")


class ApiRequestError(ValutaTradeError):

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Ошибка при обращении к внешнему API: {reason}")
