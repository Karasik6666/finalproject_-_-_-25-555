from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from valutatrade_hub.core.exceptions import InsufficientFundsError, ValidationError
from valutatrade_hub.core.utils import (
    format_amount,
    validate_amount,
    validate_currency_code,
)


# Функция для возврата текущей временной метки в формате ISO 8601 (UTC)
def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# Функция для вычисления SHA-256 хэша от байтовой последовательности
def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# Функция для безопасного хэширования пароля с использованием соли
def _hash_password(password: str, salt: bytes) -> str:
    password_bytes = password.encode("utf-8")
    return _sha256_bytes(password_bytes + salt)


# Модель пользователя системы
@dataclass(slots=True)
class User:
    _user_id: int
    _username: str
    _hashed_password: str
    _salt: bytes
    _registration_date: str

    # Фабричный метод создания пользователя с полной валидацией входных данных
    @staticmethod
    def create(user_id: int, username: str, password: str) -> User:
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValidationError("user_id должен быть положительным целым числом")
        if not isinstance(username, str) or not username.strip():
            raise ValidationError("Имя пользователя не должно быть пустым")
        if not isinstance(password, str) or len(password) < 4:
            raise ValidationError("Пароль должен содержать минимум 4 символа")

        salt = os.urandom(16)
        hashed = _hash_password(password, salt)

        return User(
            _user_id=user_id,
            _username=username.strip(),
            _hashed_password=hashed,
            _salt=salt,
            _registration_date=_utc_now_iso(),
        )

    # Идентификатор пользователя
    @property
    def user_id(self) -> int:
        return self._user_id

    # Имя пользователя
    @property
    def username(self) -> str:
        return self._username

    # Дата регистрации пользователя
    @property
    def registration_date(self) -> str:
        return self._registration_date

    # Проверка корректности введенного пароля
    def verify_password(self, password: str) -> bool:
        if not isinstance(password, str):
            return False
        return _hash_password(password, self._salt) == self._hashed_password

    # Смена пароля после проверки текущего пароля
    def change_password(self, old_password: str, new_password: str) -> None:
        if not self.verify_password(old_password):
            raise ValidationError("Неверный текущий пароль")
        if not isinstance(new_password, str) or len(new_password) < 4:
            raise ValidationError("Новый пароль должен содержать минимум 4 символа")

        new_salt = os.urandom(16)
        self._salt = new_salt
        self._hashed_password = _hash_password(new_password, new_salt)

    # Получение публичной информации о пользователе (без пароля и соли)
    def get_user_info(self) -> dict[str, Any]:
        return {
            "user_id": self._user_id,
            "username": self._username,
            "registration_date": self._registration_date,
        }

    # Сериализация пользователя для хранения в users.json
    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self._user_id,
            "username": self._username,
            "hashed_password": self._hashed_password,
            "salt_hex": self._salt.hex(),
            "registration_date": self._registration_date,
        }

    # Восстановление пользователя из данных users.json
    @staticmethod
    def from_dict(data: dict[str, Any]) -> User:
        try:
            user_id = int(data["user_id"])
            username = str(data["username"])
            hashed_password = str(data["hashed_password"])
            salt_hex = str(data["salt_hex"])
            registration_date = str(data["registration_date"])
        except (KeyError, TypeError, ValueError) as exc:
            msg = "Некорректная структура пользователя в хранилище"
            raise ValidationError(msg) from exc

        if user_id <= 0 or not username.strip() or not hashed_password or not salt_hex:
            raise ValidationError("Некорректные данные пользователя в хранилище")

        # Проверка корректности формата даты регистрации (ISO 8601)
        try:
            datetime.fromisoformat(registration_date.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValidationError("Некорректная дата регистрации пользователя") from exc

        # Восстановление соли из hex-представления
        try:
            salt = bytes.fromhex(salt_hex)
        except ValueError as exc:
            raise ValidationError("Некорректная соль пользователя") from exc

        return User(
            _user_id=user_id,
            _username=username.strip(),
            _hashed_password=hashed_password,
            _salt=salt,
            _registration_date=registration_date,
        )


# Модель кошелька пользователя для одной валюты
@dataclass(slots=True)
class Wallet:
    currency_code: str
    _balance: float = 0.0

    # Инициализация кошелька с валидацией валюты и начального баланса
    def __post_init__(self) -> None:
        self.currency_code = validate_currency_code(self.currency_code)
        self.balance = self._balance

    # Текущий баланс кошелька
    @property
    def balance(self) -> float:
        return self._balance

    # Установка баланса с проверкой корректности значения
    @balance.setter
    def balance(self, value: object) -> None:
        try:
            amount = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ValidationError("Баланс должен быть числом") from exc
        if amount < 0:
            raise ValidationError("Баланс не может быть отрицательным")
        self._balance = amount

    # Пополнение баланса кошелька
    def deposit(self, amount: object) -> None:
        value = validate_amount(amount)
        self._balance += value

    # Списание средств с проверкой достаточности баланса
    def withdraw(self, amount: object) -> None:
        value = validate_amount(amount)
        if self._balance < value:
            raise InsufficientFundsError(
                available=round(self._balance, 8),
                required=round(value, 8),
                code=self.currency_code,
            )
        self._balance -= value

    # Человекочитаемое представление баланса кошелька
    def get_balance_info(self) -> str:
        formatted = format_amount(self.currency_code, self._balance)
        return f"{self.currency_code}: {formatted}"

    # Сериализация кошелька для хранения в portfolios.json
    def to_dict(self) -> dict[str, Any]:
        return {"currency_code": self.currency_code, "balance": self._balance}

    # Восстановление кошелька из данных portfolios.json
    @staticmethod
    def from_dict(data: dict[str, Any]) -> Wallet:
        try:
            code = str(data["currency_code"])
            bal = data.get("balance", 0.0)
        except (KeyError, TypeError) as exc:
            msg = "Некорректная структура кошелька в хранилище"
            raise ValidationError(msg) from exc

        wallet = Wallet(currency_code=code)
        wallet.balance = bal
        return wallet


# Модель портфеля пользователя
@dataclass(slots=True)
class Portfolio:
    _user_id: int
    _wallets: dict[str, Wallet]

    # Создание пустого портфеля для пользователя
    @staticmethod
    def create_empty(user_id: int) -> Portfolio:
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValidationError("user_id должен быть положительным целым числом")
        return Portfolio(_user_id=user_id, _wallets={})

    # Идентификатор владельца портфеля
    @property
    def user(self) -> int:
        return self._user_id

    # Копия словаря кошельков для предотвращения внешней модификации
    @property
    def wallets(self) -> dict[str, Wallet]:
        return dict(self._wallets)

    # Добавление валютного кошелька при его отсутствии
    def add_currency(self, code: str) -> Wallet:
        normalized = validate_currency_code(code)
        if normalized in self._wallets:
            return self._wallets[normalized]
        wallet = Wallet(currency_code=normalized, _balance=0.0)
        self._wallets[normalized] = wallet
        return wallet

    # Получение кошелька по коду валюты
    def get_wallet(self, code: str) -> Wallet | None:
        normalized = validate_currency_code(code)
        return self._wallets.get(normalized)

    # Сериализация портфеля для хранения в portfolios.json
    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self._user_id,
            "wallets": [w.to_dict() for w in self._wallets.values()],
        }

    # Восстановление портфеля из данных portfolios.json
    @staticmethod
    def from_dict(data: dict[str, Any]) -> Portfolio:
        try:
            user_id = int(data["user_id"])
            wallets_raw = list(data.get("wallets", []))
        except (KeyError, TypeError, ValueError) as exc:
            msg = "Некорректная структура портфеля в хранилище"
            raise ValidationError(msg) from exc

        wallets: dict[str, Wallet] = {}
        for item in wallets_raw:
            if not isinstance(item, dict):
                raise ValidationError("Некорректная структура кошельков в портфеле")
            wallet = Wallet.from_dict(item)
            if wallet.currency_code in wallets:
                raise ValidationError(
                    f"Дублирующийся кошелек '{wallet.currency_code}' "
                    "в портфеле пользователя"
                )
            wallets[wallet.currency_code] = wallet

        return Portfolio(_user_id=user_id, _wallets=wallets)

    # Расчет суммарной стоимости портфеля в базовой валюте
    def get_total_value(
        self,
        base: str = "USD",
        rates_snapshot: dict[str, Any] | None = None,
        fallback_rates: dict[str, float] | None = None,
    ) -> float:
        base_code = validate_currency_code(base)
        total = 0.0

        pairs: dict[str, Any] = {}
        if isinstance(rates_snapshot, dict):
            pairs_raw = rates_snapshot.get("pairs", {})
            if isinstance(pairs_raw, dict):
                pairs = pairs_raw

        for code, wallet in self._wallets.items():
            if wallet.balance == 0:
                continue

            if code == base_code:
                total += wallet.balance
                continue

            pair_key = f"{code}_{base_code}"
            rate: float | None = None

            entry = pairs.get(pair_key)
            if isinstance(entry, dict) and "rate" in entry:
                try:
                    rate = float(entry["rate"])
                except (TypeError, ValueError):
                    rate = None

            if rate is None and fallback_rates is not None:
                rate = fallback_rates.get(pair_key)

            if rate is None:
                raise ValidationError(
                    f"Нет курса для конвертации {code}->{base_code}. "
                    "Запустите update-rates или выберите другую базовую валюту."
                )

            total += wallet.balance * rate

        return total