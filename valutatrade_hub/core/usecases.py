from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import ApiRequestError, AuthError, ValidationError
from valutatrade_hub.core.models import Portfolio, User
from valutatrade_hub.core.utils import (
    format_amount,
    make_pair_key,
    validate_amount,
    validate_currency_code,
)
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader


# Функция для получения текущего времени в ISO 8601 (UTC)
def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# Функция для парсинга ISO-строки даты/времени и приведения к UTC
def _parse_iso_datetime(value: object) -> datetime | None:
    if value is None or not isinstance(value, str):
        return None
    try:
        v = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None

    # Приведение времени к timezone-aware формату и единой зоне UTC
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


# Структура для передачи информации о курсе без привязки к формату JSON-хранилища
@dataclass(frozen=True, slots=True)
class RateInfo:
    pair: str
    rate: float
    updated_at: str
    source: str


# Класс с бизнес-операциями (CLI здесь только вызывает методы и печатает результат)
class TradingUseCases:
    def __init__(self) -> None:
        self._db = DatabaseManager()
        self._settings = SettingsLoader()

    # Загрузка пользователей из users.json
    def _load_users(self) -> list[User]:
        raw = self._db.read_users()
        return [User.from_dict(item) for item in raw]

    # Сохранение пользователей в users.json
    def _save_users(self, users: list[User]) -> None:
        self._db.write_users([u.to_dict() for u in users])

    # Загрузка портфелей из portfolios.json
    def _load_portfolios(self) -> list[Portfolio]:
        raw = self._db.read_portfolios()
        return [Portfolio.from_dict(item) for item in raw]

    # Сохранение портфелей в portfolios.json
    def _save_portfolios(self, portfolios: list[Portfolio]) -> None:
        self._db.write_portfolios([p.to_dict() for p in portfolios])

    # Поиск пользователя по username в уже загруженном списке
    def _find_user_by_username(self, username: str, users: list[User]) -> User | None:
        for u in users:
            if u.username == username:
                return u
        return None

    # Поиск пользователя по user_id в уже загруженном списке
    def _find_user_by_id(self, user_id: int, users: list[User]) -> User | None:
        for u in users:
            if u.user_id == user_id:
                return u
        return None

    # Проверка user_id и получение пользователя (единая точка валидации)
    def _require_user(self, user_id: int) -> User:
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValidationError("Некорректный user_id")
        users = self._load_users()
        user = self._find_user_by_id(user_id, users)
        if user is None:
            raise ValidationError("Пользователь не найден")
        return user

    # Получение портфеля пользователя или создание пустого (если еще не создавался)
    def _get_or_create_portfolio(
        self,
        user_id: int,
        portfolios: list[Portfolio],
    ) -> Portfolio:
        for p in portfolios:
            if p.user == user_id:
                return p
        p = Portfolio.create_empty(user_id=user_id)
        portfolios.append(p)
        return p

    # Чтение снимка курсов из rates.json
    def _get_rates_snapshot(self) -> dict[str, Any]:
        return self._db.read_rates_snapshot()

    # Проверка актуальности кэша курсов по TTL из настроек
    def _is_rates_stale(self, snapshot: dict[str, Any]) -> bool:
        ttl_raw = self._settings.get("RATES_TTL_SECONDS", 3600)
        try:
            ttl = int(ttl_raw)
        except (TypeError, ValueError):
            ttl = 3600

        last_refresh = _parse_iso_datetime(snapshot.get("last_refresh"))
        if last_refresh is None:
            return True

        age_seconds = (datetime.now(UTC) - last_refresh).total_seconds()
        return age_seconds > ttl

    # Регистрация пользователя (создание записи в users.json и пустого портфеля)
    def register(self, username: str, password: str) -> dict[str, Any]:
        if not isinstance(username, str) or not username.strip():
            raise ValidationError("Имя пользователя не должно быть пустым")
        if not isinstance(password, str) or len(password) < 4:
            raise ValidationError("Пароль должен содержать минимум 4 символа")

        uname = username.strip()

        users = self._load_users()
        if self._find_user_by_username(uname, users) is not None:
            raise ValidationError("Пользователь с таким именем уже существует")

        next_id = 1 + max((u.user_id for u in users), default=0)
        user = User.create(user_id=next_id, username=uname, password=password)

        portfolios = self._load_portfolios()
        portfolio = self._get_or_create_portfolio(user.user_id, portfolios)

        # Добавление стартового USD-баланса
        usd_wallet = portfolio.add_currency("USD")
        if usd_wallet.balance == 0:
            usd_wallet.deposit(10000.0)

        users.append(user)
        self._save_users(users)
        self._save_portfolios(portfolios)

        return {"user": user.get_user_info(), "demo_usd_balance": 10000.0}

    # Авторизация пользователя (проверка пароля и возврат его id)
    def login(self, username: str, password: str) -> dict[str, Any]:
        if not isinstance(username, str) or not username.strip():
            raise ValidationError("Имя пользователя не должно быть пустым")
        if not isinstance(password, str) or len(password) < 4:
            raise ValidationError("Пароль должен содержать минимум 4 символа")

        uname = username.strip()

        users = self._load_users()
        user = self._find_user_by_username(uname, users)
        if user is None or not user.verify_password(password):
            raise AuthError("Неверное имя пользователя или пароль")

        return {"user_id": user.user_id, "username": user.username}

    # Получение курса из кэша rates.json с учетом TTL
    def get_rate(self, from_code: str, to_code: str) -> RateInfo:
        from_norm = validate_currency_code(from_code)
        to_norm = validate_currency_code(to_code)

        # Проверка наличия валют в реестре 
        get_currency(from_norm)
        get_currency(to_norm)

        snapshot = self._get_rates_snapshot()
        if self._is_rates_stale(snapshot):
            raise ApiRequestError(
                "Кэш курсов устарел. Запустите команду update-rates для обновления."
            )

        pairs = snapshot.get("pairs", {})
        if not isinstance(pairs, dict):
            raise ValidationError("Некорректная структура rates.json: pairs")

        direct_pair = make_pair_key(from_norm, to_norm)
        inverse_pair = make_pair_key(to_norm, from_norm)

        entry = pairs.get(direct_pair)
        inverse_entry = pairs.get(inverse_pair)

        rate: float | None = None
        updated_at: str | None = None
        source: str | None = None
        pair_used = direct_pair

        # Сначала пробуем прямой курс, затем обратный с инверсией
        if isinstance(entry, dict) and "rate" in entry:
            pair_used = direct_pair
            try:
                rate = float(entry["rate"])
            except (TypeError, ValueError) as exc:
                raise ValidationError("Некорректное значение курса в кэше") from exc
            updated_at = str(entry.get("updated_at") or "")
            source = str(entry.get("source") or "")
        elif isinstance(inverse_entry, dict) and "rate" in inverse_entry:
            pair_used = direct_pair
            try:
                inv = float(inverse_entry["rate"])
            except (TypeError, ValueError) as exc:
                raise ValidationError("Некорректное значение курса в кэше") from exc
            if inv == 0:
                raise ValidationError("Некорректное значение курса в кэше")
            rate = 1.0 / inv
            updated_at = str(inverse_entry.get("updated_at") or "")
            source = str(inverse_entry.get("source") or "")

        if rate is None:
            raise ValidationError(
                f"Курс {direct_pair} не найден в кэше. "
                "Запустите update-rates или попробуйте другую пару."
            )

        # Если метаданные не заполнены, то берется last_refresh
        if not updated_at:
            updated_at = str(snapshot.get("last_refresh") or _utc_now_iso())
        if not source:
            source = "cache"

        return RateInfo(pair=pair_used, rate=rate, updated_at=updated_at, source=source)

    # Подготовка данных портфеля для вывода в CLI (таблица + итог)
    def show_portfolio(self, user_id: int, base: str = "USD") -> dict[str, Any]:
        user = self._require_user(user_id)

        base_code = validate_currency_code(base)
        get_currency(base_code)

        portfolios = self._load_portfolios()
        portfolio = self._get_or_create_portfolio(user.user_id, portfolios)

        snapshot = self._get_rates_snapshot()
        total = portfolio.get_total_value(base=base_code, rates_snapshot=snapshot)

        rows: list[dict[str, Any]] = []
        for code, wallet in sorted(portfolio.wallets.items(), key=lambda x: x[0]):
            rows.append(
                {
                    "currency": code,
                    "balance": wallet.balance,
                    "balance_display": format_amount(code, wallet.balance),
                }
            )

        return {
            "user_id": user.user_id, 
            "base": base_code, 
            "rows": rows, 
            "total": total
        }

    # Снимок балансов кошельков для verbose-логирования в @log_action
    def _wallets_snapshot(self, portfolio: Portfolio) -> dict[str, str]:
        snap: dict[str, str] = {}
        for code, wallet in portfolio.wallets.items():
            snap[code] = format_amount(code, wallet.balance)
        return snap

    # Покупка валюты за USD: списание USD и зачисление купленной валюты
    @log_action(action="buy", verbose=True)
    def buy(self, user_id: int, currency_code: str, amount: float) -> dict[str, Any]:
        user = self._require_user(user_id)

        code = validate_currency_code(currency_code)
        amt = validate_amount(amount)
        get_currency(code)

        portfolios = self._load_portfolios()
        portfolio = self._get_or_create_portfolio(user.user_id, portfolios)

        before = self._wallets_snapshot(portfolio)

        usd_wallet = portfolio.add_currency("USD")
        target_wallet = portfolio.add_currency(code)

        rate_info = self.get_rate(from_code=code, to_code="USD")
        cost_usd = amt * rate_info.rate

        usd_wallet.withdraw(cost_usd)
        target_wallet.deposit(amt)

        self._save_portfolios(portfolios)

        after = self._wallets_snapshot(portfolio)

        return {
            "user_id": user.user_id,
            "username": user.username,
            "currency_code": code,
            "amount": amt,
            "rate": rate_info.rate,
            "base": "USD",
            "cost_usd": cost_usd,
            "wallets_before": before,
            "wallets_after": after,
        }

    # Продажа валюты за USD: списание валюты и зачисление выручки в USD
    @log_action(action="sell", verbose=True)
    def sell(self, user_id: int, currency_code: str, amount: float) -> dict[str, Any]:
        user = self._require_user(user_id)

        code = validate_currency_code(currency_code)
        amt = validate_amount(amount)
        get_currency(code)

        portfolios = self._load_portfolios()
        portfolio = self._get_or_create_portfolio(user.user_id, portfolios)

        before = self._wallets_snapshot(portfolio)

        usd_wallet = portfolio.add_currency("USD")
        target_wallet = portfolio.get_wallet(code)
        if target_wallet is None:
            raise ValidationError(f"Кошелек {code} отсутствует в портфеле")

        rate_info = self.get_rate(from_code=code, to_code="USD")
        revenue_usd = amt * rate_info.rate

        target_wallet.withdraw(amt)
        usd_wallet.deposit(revenue_usd)

        self._save_portfolios(portfolios)

        after = self._wallets_snapshot(portfolio)

        return {
            "user_id": user.user_id,
            "username": user.username,
            "currency_code": code,
            "amount": amt,
            "rate": rate_info.rate,
            "base": "USD",
            "revenue_usd": revenue_usd,
            "wallets_before": before,
            "wallets_after": after,
        }
