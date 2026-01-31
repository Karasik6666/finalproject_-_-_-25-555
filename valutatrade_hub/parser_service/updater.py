from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from valutatrade_hub.core.exceptions import ApiRequestError, ValidationError
from valutatrade_hub.parser_service.storage import RatesStorage

logger = logging.getLogger("valutatrade_hub.parser.updater")


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# Нормализация фильтра источника для единообразного выбора клиента
def _normalize_source_filter(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.strip().lower()
    if v in {"coingecko", "coin-gecko"}:
        return "coingecko"
    if v in {"exchangerate", "exchange-rate", "exchangerate-api", "exchangerateapi"}:
        return "exchangerate"
    return v


class RatesUpdater:

    def __init__(self, clients: Iterable[Any], storage: RatesStorage) -> None:
        self._clients = list(clients)
        self._storage = storage

    def run_update(self, source: str | None = None) -> None:
        src_filter = _normalize_source_filter(source)

        logger.info("Starting rates update")
        pairs: dict[str, dict[str, Any]] = {}
        history_records: list[dict[str, Any]] = []

        for client in self._clients:
            client_source = getattr(client, "SOURCE", client.__class__.__name__)
            client_source_norm = str(client_source).strip().lower()

            # Применение фильтра источника при точечном обновлении
            if src_filter is not None and client_source_norm != src_filter:
                continue

            try:
                results = client.fetch_rates()
            except ApiRequestError as exc:
                # Локализация ошибки на уровне конкретного клиента 
                # без остановки общего обновления
                logger.error(
                    "Rates update failed for source=%s: %s",
                    client_source_norm,
                    str(exc),
                )
                continue

            if not isinstance(results, dict):
                logger.error("Client %s returned invalid format", client_source_norm)
                continue

            for pair_key, payload in results.items():
                # Отсечение некорректных ключей и payload 
                # до формирования snapshot/history
                if not isinstance(pair_key, str) or "_" not in pair_key:
                    continue
                if not isinstance(payload, dict) or "rate" not in payload:
                    continue

                parts = pair_key.split("_")
                if len(parts) != 2:
                    continue
                from_cur, to_cur = parts[0], parts[1]

                try:
                    rate = float(payload["rate"])
                except (TypeError, ValueError):
                    continue

                updated_at = payload.get("updated_at") or _utc_now_iso()
                source_name = payload.get("source") or client_source_norm

                # Формирование записи snapshot в формате, 
                # который читает Core (usecases.get_rate)
                pairs[pair_key] = {
                    "rate": rate,
                    "updated_at": updated_at,
                    "source": source_name,
                }

                meta = payload.get("meta")
                if meta is not None and not isinstance(meta, dict):
                    raise ValidationError("meta должен быть словарем")

                history_records.append(
                    self._storage.build_history_record(
                        from_currency=from_cur,
                        to_currency=to_cur,
                        rate=rate,
                        timestamp=updated_at,
                        source=str(source_name),
                        meta=meta if isinstance(meta, dict) else None,
                    )
                )

        # Контроль "пустого" результата, чтобы CLI получил понятную ошибку
        if not pairs:
            raise ApiRequestError("Не удалось обновить ни один курс")

        self._storage.save_snapshot(pairs)
        self._storage.append_history(history_records)

        logger.info("Rates update completed successfully: %d pairs", len(pairs))
