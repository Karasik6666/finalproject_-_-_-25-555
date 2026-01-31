from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from valutatrade_hub.core.exceptions import ValidationError
from valutatrade_hub.infra.settings import SettingsLoader


@dataclass(slots=True, frozen=True)
class ParserConfig:

    EXCHANGERATE_API_KEY: str | None
    COINGECKO_BASE_URL: str
    EXCHANGERATE_BASE_URL: str

    BASE_CURRENCY: str
    FIAT_CURRENCIES: tuple[str, ...]
    CRYPTO_CURRENCIES: tuple[str, ...]
    CRYPTO_ID_MAP: dict[str, str]

    RATES_PATH: Path
    EXCHANGE_RATES_PATH: Path

    REQUEST_TIMEOUT: int

    @staticmethod
    def load() -> ParserConfig:
        settings = SettingsLoader()

        # Получение путей из настроек Core/Infra (единая конфигурация для всего проекта)
        rates_path = settings.get("RATES_PATH")
        history_path = settings.get("EXCHANGE_RATES_PATH")
        if not isinstance(rates_path, str) or not rates_path.strip():
            raise ValidationError("В настройках не задан RATES_PATH")
        if not isinstance(history_path, str) or not history_path.strip():
            raise ValidationError("В настройках не задан EXCHANGE_RATES_PATH")

        return ParserConfig(
            # Чтение ключа API только из окружения, 
            # чтобы исключить хранение в репозитории
            EXCHANGERATE_API_KEY=os.getenv("EXCHANGERATE_API_KEY"),
            COINGECKO_BASE_URL="https://api.coingecko.com/api/v3",
            EXCHANGERATE_BASE_URL="https://v6.exchangerate-api.com/v6",
            # Фиксация базовой валюты и поддерживаемых наборов валют 
            # для обновления курсов
            BASE_CURRENCY="USD",
            FIAT_CURRENCIES=("EUR", "GBP", "RUB"),
            CRYPTO_CURRENCIES=("BTC", "ETH", "SOL"),
            # Сопоставление кодов валют внутренним идентификаторам CoinGecko
            CRYPTO_ID_MAP={
                "BTC": "bitcoin",
                "ETH": "ethereum",
                "SOL": "solana",
            },
            # Привязка хранилищ snapshot/history к путям из SettingsLoader
            RATES_PATH=Path(rates_path),
            EXCHANGE_RATES_PATH=Path(history_path),
            REQUEST_TIMEOUT=10,
        )
