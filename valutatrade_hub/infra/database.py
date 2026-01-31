from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from valutatrade_hub.core.exceptions import ValidationError
from valutatrade_hub.infra.settings import SettingsLoader


# Класс для работы с JSON-хранилищем проекта
class DatabaseManager:
    _instance: DatabaseManager | None = None

    # Singleton используется для согласованного доступа к файлам данных
    def __new__(cls) -> DatabaseManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._settings = SettingsLoader()
        return cls._instance

    # Универсальный метод чтения JSON-файлов с базовой проверкой структуры
    def _read_json(self, path: Path, expected_type: type) -> Any:
        if not path.exists():
            raise ValidationError(f"Файл данных не найден: {path}")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Ошибка чтения JSON-файла: {path}") from exc

        if not isinstance(data, expected_type):
            raise ValidationError(f"Некорректная структура данных в файле {path}")
        return data

    # Запись JSON-файла с использованием временного файла для атомарности
    def _write_json_atomic(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")

        try:
            tmp_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp_path, path)
        except OSError as exc:
            raise ValidationError(f"Ошибка записи данных в файл: {path}") from exc
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def _path_from_settings(self, key: str) -> Path:
        raw = self._settings.get(key)
        if not isinstance(raw, str) or not raw.strip():
            raise ValidationError(f"В настройках не задан путь: {key}")
        return Path(raw)

    def get_users_path(self) -> Path:
        return self._path_from_settings("USERS_PATH")

    def get_portfolios_path(self) -> Path:
        return self._path_from_settings("PORTFOLIOS_PATH")

    def get_rates_path(self) -> Path:
        return self._path_from_settings("RATES_PATH")

    def get_exchange_rates_path(self) -> Path:
        return self._path_from_settings("EXCHANGE_RATES_PATH")

    # Чтение списка пользователей с минимальной структурной проверкой
    def read_users(self) -> list[dict[str, Any]]:
        data = self._read_json(self.get_users_path(), list)
        for item in data:
            if not isinstance(item, dict):
                raise ValidationError("Некорректная структура users.json")

            # Проверка совместимости с User.from_dict()
            required_keys = {
                "user_id",
                "username",
                "hashed_password",
                "salt_hex",
                "registration_date",
            }
            if not required_keys.issubset(item.keys()):
                raise ValidationError("Некорректные данные пользователя в users.json")
        return data

    # Запись пользователей в users.json
    def write_users(self, users: list[dict[str, Any]]) -> None:
        if not isinstance(users, list):
            raise ValidationError("users должен быть списком")
        self._write_json_atomic(self.get_users_path(), users)

    # Чтение портфелей пользователей с минимальной структурной проверкой
    def read_portfolios(self) -> list[dict[str, Any]]:
        data = self._read_json(self.get_portfolios_path(), list)
        for item in data:
            if not isinstance(item, dict):
                raise ValidationError("Некорректная структура portfolios.json")

            # Проверка совместимости с Portfolio.from_dict()
            if "user_id" not in item or "wallets" not in item:
                raise ValidationError(
                    "Некорректная структура портфеля в portfolios.json"
                )
            if not isinstance(item["wallets"], list):
                raise ValidationError(
                    "Некорректная структура портфеля: wallets должен быть списком"
                )

            for w in item["wallets"]:
                if not isinstance(w, dict):
                    raise ValidationError(
                        "Некорректная структура кошелька в portfolios.json"
                    )
                if "currency_code" not in w:
                    raise ValidationError("Кошелек должен содержать currency_code")
        return data

    # Запись портфелей в portfolios.json
    def write_portfolios(self, portfolios: list[dict[str, Any]]) -> None:
        if not isinstance(portfolios, list):
            raise ValidationError("portfolios должен быть списком")
        for item in portfolios:
            if not isinstance(item, dict):
                raise ValidationError("Некорректная структура portfolios для записи")
        self._write_json_atomic(self.get_portfolios_path(), portfolios)

    # Чтение снимка курсов валют
    def read_rates_snapshot(self) -> dict[str, Any]:
        data = self._read_json(self.get_rates_path(), dict)
        if "pairs" not in data or "last_refresh" not in data:
            raise ValidationError(
                "Некорректная структура rates.json: ожидаются pairs и last_refresh"
            )
        if not isinstance(data["pairs"], dict):
            raise ValidationError(
                "Некорректная структура rates.json: pairs должен быть словарем"
            )
        return data

    # Запись снимка курсов валют
    def write_rates_snapshot(self, snapshot: dict[str, Any]) -> None:
        if not isinstance(snapshot, dict):
            raise ValidationError("snapshot должен быть словарем")
        if "pairs" not in snapshot or "last_refresh" not in snapshot:
            raise ValidationError("Некорректная структура snapshot для rates.json")
        if not isinstance(snapshot["pairs"], dict):
            raise ValidationError(
                "Некорректная структура snapshot: pairs должен быть словарем"
            )
        self._write_json_atomic(self.get_rates_path(), snapshot)

    # Чтение истории обновлений курсов
    def read_exchange_rates_history(self) -> list[dict[str, Any]]:
        data = self._read_json(self.get_exchange_rates_path(), list)
        for item in data:
            if not isinstance(item, dict):
                raise ValidationError("Некорректная структура exchange_rates.json")
            if "id" not in item:
                raise ValidationError(
                    "Некорректная структура записи history: отсутствует id"
                )
        return data

    # Запись истории обновлений курсов
    def write_exchange_rates_history(self, history: list[dict[str, Any]]) -> None:
        if not isinstance(history, list):
            raise ValidationError("history должен быть списком")
        for item in history:
            if not isinstance(item, dict):
                raise ValidationError("Некорректная структура history для записи")
        self._write_json_atomic(self.get_exchange_rates_path(), history)
