from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import Final

from valutatrade_hub.core.exceptions import ValidationError

_CURRENCY_CODE_MIN_LEN: Final[int] = 2
_CURRENCY_CODE_MAX_LEN: Final[int] = 5

# Валидация и нормализация кода валюты
def validate_currency_code(code: str) -> str:
    """
    Валидирует и нормализует код валюты.

    Правила (ТЗ 3):
    - приведение к верхнему регистру;
    - длина от 2 до 5 символов;
    - отсутствие пробелов;
    - допустимы только буквенно-цифровые символы.
    """
    if not isinstance(code, str):
        raise ValidationError("Код валюты должен быть строкой")

    normalized = code.strip().upper()
    if " " in normalized:
        raise ValidationError("Код валюты не должен содержать пробелы")
    if not (_CURRENCY_CODE_MIN_LEN <= len(normalized) <= _CURRENCY_CODE_MAX_LEN):
        raise ValidationError("Код валюты должен содержать от 2 до 5 символов")
    if not normalized.isalnum():
        raise ValidationError("Код валюты должен содержать только буквы и цифры")
    return normalized

# Валидация числового значения суммы операции
def validate_amount(amount: object) -> float:
    try:
        value = float(amount)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValidationError("Сумма должна быть числом") from None

    if not math.isfinite(value):
        raise ValidationError("Сумма должна быть конечным числом")
    if value <= 0:
        raise ValidationError("Сумма должна быть больше 0")
    return value

# Форматирование суммы для пользовательского отображения
def format_amount(code: str, amount: float) -> str:
    code_norm = validate_currency_code(code)
    decimals = 4 if code_norm in {"BTC", "ETH", "SOL"} else 2
    q = Decimal("1." + ("0" * decimals))
    try:
        d = Decimal(str(amount)).quantize(q)
    except (InvalidOperation, ValueError):
        d = Decimal("0").quantize(q)
    return f"{d:.{decimals}f}"

# Формирование ключа валютной пары
def make_pair_key(from_code: str, to_code: str) -> str:
    """
    Формирует ключ валютной пары в формате FROM_TO.
    """
    f = validate_currency_code(from_code)
    t = validate_currency_code(to_code)
    return f"{f}_{t}"

# Возвращение инвертированного ключа валютной пары
def invert_pair_key(pair_key: str) -> str:
    parts = pair_key.split("_", maxsplit=1)
    if len(parts) != 2:
        raise ValidationError("Некорректный ключ пары валют")
    return make_pair_key(parts[1], parts[0])

# Возвращение обратного значения валютного курса
def invert_rate(rate: float) -> float:
    value = validate_amount(rate)
    if value == 0:
        raise ValidationError("Нельзя инвертировать нулевой курс")
    return 1.0 / value