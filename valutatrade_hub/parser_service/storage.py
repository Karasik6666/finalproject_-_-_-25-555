from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from valutatrade_hub.core.exceptions import ValidationError
from valutatrade_hub.infra.database import DatabaseManager


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# Нормализация входной временной метки к ISO 8601 (UTC) с fallback на текущее время
def _ensure_iso_utc(value: object) -> str:
    if isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC).replace(microsecond=0).isoformat()
        except ValueError:
            return _utc_now_iso()
    return _utc_now_iso()


class RatesStorage:

    def __init__(self) -> None:
        self._db = DatabaseManager()

    # Получение актуального snapshot из rates.json (пары + last_refresh)
    def load_snapshot(self) -> dict[str, Any]:
        return self._db.read_rates_snapshot()

     # Формирование и сохранение snapshot в rates.json 
     # (атомарная запись реализована в DatabaseManager)
    def save_snapshot(self, pairs: dict[str, dict[str, Any]]) -> None:
        if not isinstance(pairs, dict):
            raise ValidationError("pairs должен быть словарем")

        snapshot = {
            "pairs": pairs,
            "last_refresh": _utc_now_iso(),
        }
        self._db.write_rates_snapshot(snapshot)

    # Получение истории обновлений из exchange_rates.json
    def load_history(self) -> list[dict[str, Any]]:
        return self._db.read_exchange_rates_history()

    # Добавление записей в историю с дедупликацией по id и 
    # минимальной структурной проверкой
    def append_history(self, records: list[dict[str, Any]]) -> None:
        if not isinstance(records, list):
            raise ValidationError("records должен быть списком")

        history = self.load_history()
        existing_ids = {
            item.get("id")
            for item in history
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }

        for record in records:
            if not isinstance(record, dict):
                continue

            record_id = record.get("id")
            if not isinstance(record_id, str) or not record_id.strip():
                continue

            if record_id in existing_ids:
                continue

             # Проверка наличия ключевых полей записи history
            required = {
                "from_currency", 
                "to_currency", 
                "rate", 
                "timestamp", 
                "source", 
                "meta"
            }
            if not required.issubset(record.keys()):
                raise ValidationError("Некорректная структура записи history")

            meta = record.get("meta")
            if not isinstance(meta, dict):
                raise ValidationError("meta должен быть словарем")

            history.append(record)
            existing_ids.add(record_id)

        self._db.write_exchange_rates_history(history)

    @staticmethod
    def build_history_record(
        *,
        from_currency: str,
        to_currency: str,
        rate: float,
        timestamp: object,
        source: str,
        meta: dict[str, Any] | None,
    ) -> dict[str, Any]:
        ts = _ensure_iso_utc(timestamp)
        # Формирование id как ключа дедупликации по паре и моменту фиксации курса
        record_id = f"{from_currency}_{to_currency}_{ts}"

        safe_meta: dict[str, Any] = {}
        if isinstance(meta, dict):
            safe_meta = dict(meta)

        # Нормализация meta до минимально ожидаемого набора полей для проверок/дебага
        safe_meta.setdefault("raw_id", None)
        safe_meta.setdefault("request_ms", None)
        safe_meta.setdefault("status_code", None)
        safe_meta.setdefault("etag", None)

        return {
            "id": record_id,
            "from_currency": from_currency,
            "to_currency": to_currency,
            "rate": float(rate),
            "timestamp": ts,
            "source": source,
            "meta": safe_meta,
        }
