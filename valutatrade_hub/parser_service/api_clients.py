from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import requests
from requests import Response

from valutatrade_hub.core.exceptions import ApiRequestError, ValidationError
from valutatrade_hub.core.utils import make_pair_key, validate_currency_code
from valutatrade_hub.parser_service.config import ParserConfig


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# Жесткая интерпретация HTTP-статусов в прикладные ошибки для CLI/Core
def _raise_for_status_strict(resp: Response, source: str) -> None:
    status = resp.status_code
    if 200 <= status < 300:
        return

    if status in {401, 403}:
        raise ApiRequestError(f"{source}: доступ запрещен (HTTP {status})")
    if status == 429:
        raise ApiRequestError(f"{source}: превышен лимит запросов (HTTP 429)")
    if 500 <= status < 600:
        raise ApiRequestError(f"{source}: ошибка сервера (HTTP {status})")

    raise ApiRequestError(f"{source}: ошибка HTTP {status}")

# Функция для безопасного чтения JSON-ответа с проверкой ожидаемого формата
def _safe_json(resp: Response, source: str) -> dict[str, Any]:
    try:
        payload = resp.json()
    except ValueError as exc:
        raise ApiRequestError(f"{source}: не удалось разобрать JSON") from exc
    if not isinstance(payload, dict):
        raise ApiRequestError(f"{source}: неожиданный формат JSON (ожидался объект)")
    return payload

# Базовый контракт клиента внешнего API с единым форматом fetch_rates()
class BaseApiClient(ABC):

    SOURCE: str

    def __init__(self, config: ParserConfig) -> None:
        self._config = config

    @abstractmethod
    def fetch_rates(self) -> dict[str, dict[str, Any]]:
        raise NotImplementedError


# Клиент CoinGecko: получение crypto -> USD для валют из конфигурации
class CoinGeckoClient(BaseApiClient):

    SOURCE = "coingecko"

    def fetch_rates(self) -> dict[str, dict[str, Any]]:
        base = validate_currency_code(self._config.BASE_CURRENCY)
        if base != "USD":
            raise ValidationError(
                "CoinGeckoClient поддерживает только BASE_CURRENCY=USD"
            )

        ids: list[str] = []
        code_to_id: dict[str, str] = {}

        # Формирование списка идентификаторов CoinGecko по CRYPTO_ID_MAP
        for code in self._config.CRYPTO_CURRENCIES:
            c = validate_currency_code(code)
            raw_id = self._config.CRYPTO_ID_MAP.get(c)
            if not raw_id:
                continue
            ids.append(raw_id)
            code_to_id[c] = raw_id

        if not ids:
            raise ValidationError("Не задан список криптовалют для обновления")

        url = f"{self._config.COINGECKO_BASE_URL}/simple/price"
        params = {"ids": ",".join(ids), "vs_currencies": base.lower()}
        headers: dict[str, str] = {"Accept": "application/json"}

        # Измерение длительности запроса для meta.request_ms
        start = time.monotonic()
        try:
            resp = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=self._config.REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            reason = f"{self.SOURCE}: ошибка сети ({exc.__class__.__name__})"
            raise ApiRequestError(reason) from exc
        request_ms = int((time.monotonic() - start) * 1000)

        _raise_for_status_strict(resp, self.SOURCE)
        payload = _safe_json(resp, self.SOURCE)

        etag = resp.headers.get("ETag")
        updated_at = _utc_now_iso()

        results: dict[str, dict[str, Any]] = {}
        for code, raw_id in code_to_id.items():
            entry = payload.get(raw_id)
            if not isinstance(entry, dict):
                continue
            rate_val = entry.get(base.lower())
            if not isinstance(rate_val, int | float):
                continue

            pair_key = make_pair_key(code, base)
            results[pair_key] = {
                "rate": float(rate_val),
                "updated_at": updated_at,
                "source": self.SOURCE,
                "meta": {
                    "raw_id": raw_id,
                    "request_ms": request_ms,
                    "status_code": resp.status_code,
                    "etag": etag,
                },
            }

        if not results:
            raise ApiRequestError(
                f"{self.SOURCE}: не удалось получить курсы по ответу API"
            )

        return results


# Клиент ExchangeRate-API: получение FIAT-курсов и приведение к формату C -> BASE
class ExchangeRateApiClient(BaseApiClient):

    SOURCE = "exchangerate"

    def fetch_rates(self) -> dict[str, dict[str, Any]]:
        api_key = self._config.EXCHANGERATE_API_KEY
        if not api_key:
            raise ApiRequestError(
                "EXCHANGERATE_API_KEY не задан. "
                "Установите переменную окружения EXCHANGERATE_API_KEY."
            )

        base = validate_currency_code(self._config.BASE_CURRENCY)

        url = f"{self._config.EXCHANGERATE_BASE_URL}/{api_key}/latest/{base}"
        headers: dict[str, str] = {"Accept": "application/json"}

        start = time.monotonic()
        try:
            resp = requests.get(
                url, 
                headers=headers, 
                timeout=self._config.REQUEST_TIMEOUT
            )
        except requests.RequestException as exc:
            reason = f"{self.SOURCE}: ошибка сети ({exc.__class__.__name__})"
            raise ApiRequestError(reason) from exc
        request_ms = int((time.monotonic() - start) * 1000)

        _raise_for_status_strict(resp, self.SOURCE)
        payload = _safe_json(resp, self.SOURCE)

        # Выбор словаря курсов с учетом вариантов ключей (rates / conversion_rates)
        rates_map = payload.get("rates")
        if not isinstance(rates_map, dict):
            rates_map = payload.get("conversion_rates")
        if not isinstance(rates_map, dict):
            raise ApiRequestError(
                f"{self.SOURCE}: неожиданный формат ответа API (rates)"
            )

        # Фиксация updated_at в ISO; 
        # сохранение оригинальной временной строки в meta при наличии
        updated_at = _utc_now_iso()
        time_last_update_utc = payload.get("time_last_update_utc")
        if isinstance(time_last_update_utc, str) and time_last_update_utc.strip():
            pass

        etag = resp.headers.get("ETag")

        results: dict[str, dict[str, Any]] = {}
        for code in self._config.FIAT_CURRENCIES:
            c = validate_currency_code(code)
            if c == base:
                continue

            rate_val = rates_map.get(c)
            if not isinstance(rate_val, int | float):
                continue

            # Приведение BASE -> C к C -> BASE для совместимости с форматами Core
            direct = float(rate_val)
            if direct == 0:
                continue
            inverted = 1.0 / direct

            pair_key = make_pair_key(c, base)
            results[pair_key] = {
                "rate": inverted,
                "updated_at": updated_at,
                "source": self.SOURCE,
                "meta": {
                    "raw_id": c,
                    "request_ms": request_ms,
                    "status_code": resp.status_code,
                    "etag": etag,
                    "time_last_update_utc": time_last_update_utc,
                },
            }

        if not results:
            raise ApiRequestError(
                f"{self.SOURCE}: не удалось получить курсы по ответу API"
            )

        return results
