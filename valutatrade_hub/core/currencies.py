from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from valutatrade_hub.core.exceptions import CurrencyNotFoundError, ValidationError
from valutatrade_hub.core.utils import validate_currency_code


@dataclass(frozen=True, slots=True)
class Currency(ABC):

    name: str
    code: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValidationError("Название валюты не должно быть пустым")
        normalized_code = validate_currency_code(self.code)
        object.__setattr__(self, "code", normalized_code)

    @abstractmethod
    def get_display_info(self) -> str:
        raise NotImplementedError

# Фиатная валюта, выпускаемая государством или союзом государств
@dataclass(frozen=True, slots=True)
class FiatCurrency(Currency):
    issuing_country: str

    def __post_init__(self) -> None:
        Currency.__post_init__(self)
        if (
            not isinstance(self.issuing_country, str)
            or not self.issuing_country.strip()
        ):
            raise ValidationError("issuing_country не должен быть пустым")

    def get_display_info(self) -> str:
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"

# Криптовалюта, основанная на распределенном реестре
@dataclass(frozen=True, slots=True)
class CryptoCurrency(Currency):

    algorithm: str
    market_cap: float

    def __post_init__(self) -> None:
        Currency.__post_init__(self)
        if not isinstance(self.algorithm, str) or not self.algorithm.strip():
            raise ValidationError("algorithm не должен быть пустым")
        if not isinstance(self.market_cap, (int, float)) or self.market_cap <= 0:   # noqa: UP038
            raise ValidationError("market_cap должен быть положительным числом")

    def get_display_info(self) -> str:
        return (
            f"[CRYPTO] {self.code} — {self.name} "
            f"(Algo: {self.algorithm}, MCAP: {self.market_cap:.2e})"
        )


_CURRENCY_REGISTRY: dict[str, Currency] = {
    "USD": FiatCurrency(
        name="US Dollar", 
        code="USD", 
        issuing_country="United States"
    ),
    "EUR": FiatCurrency(
        name="Euro", 
        code="EUR", 
        issuing_country="European Union"
    ),
    "GBP": FiatCurrency(
        name="British Pound", 
        code="GBP", 
        issuing_country="United Kingdom"
    ),
    "RUB": FiatCurrency(
        name="Russian Ruble", 
        code="RUB", 
        issuing_country="Russia"
    ),
    "BTC": CryptoCurrency(
        name="Bitcoin", 
        code="BTC", 
        algorithm="SHA-256", 
        market_cap=1.12e12
    ),
    "ETH": CryptoCurrency(
        name="Ethereum", 
        code="ETH", 
        algorithm="Ethash", 
        market_cap=4.50e11),
    "SOL": CryptoCurrency(
        name="Solana", 
        code="SOL", 
        algorithm="PoH/PoS", 
        market_cap=7.50e10
    ),
}


def get_currency(code: str) -> Currency:
    normalized = validate_currency_code(code)
    currency = _CURRENCY_REGISTRY.get(normalized)
    if currency is None:
        raise CurrencyNotFoundError(normalized)
    return currency


def list_currencies() -> list[Currency]:
    return sorted(_CURRENCY_REGISTRY.values(), key=lambda c: c.code)
