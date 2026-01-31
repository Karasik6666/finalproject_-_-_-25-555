from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from valutatrade_hub.core.exceptions import ValidationError


# Класс для загрузки и хранения настроек проекта
class SettingsLoader:
    _instance: SettingsLoader | None = None

    # Singleton реализован через __new__, так как в приложении 
    # нужен один источник конфигурации
    def __new__(cls) -> SettingsLoader:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data = {}
            cls._instance._project_root = cls._instance._detect_project_root()
            cls._instance.reload()
        return cls._instance

    # Перезагрузка конфигурации из pyproject.toml с последующим наложением env-overrides
    def reload(self) -> None:
        self._data = self._load_from_pyproject()
        self._apply_env_overrides()
        self._normalize_path_settings()

    # Получение значения настройки по ключу с поддержкой default
    def get(self, key: str, default: Any = None) -> Any:
        if not isinstance(key, str) or not key.strip():
            raise ValidationError("Ключ настройки должен быть непустой строкой")
        return self._data.get(key, default)

    # Получение корневой директории проекта
    def get_project_root(self) -> Path:
        return self._project_root

    # Определение корня проекта относительно расположения текущего файла
    def _detect_project_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    # Функция загрузки настроек из секции [tool.valutatrade] в pyproject.toml
    def _load_from_pyproject(self) -> dict[str, Any]:
        pyproject_path = self._project_root / "pyproject.toml"
        if not pyproject_path.exists():
            raise ValidationError("Не найден pyproject.toml для загрузки настроек")

        try:
            parsed = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValidationError("Ошибка чтения pyproject.toml") from exc

        tool_section = parsed.get("tool")
        if not isinstance(tool_section, dict):
            raise ValidationError(
                "Некорректная структура pyproject.toml: отсутствует tool"
            )

        vt = tool_section.get("valutatrade")
        if not isinstance(vt, dict):
            raise ValidationError(
                "Некорректная структура pyproject.toml: tool.valutatrade"
            )

        return dict(vt)

    # Применение переменных окружения поверх конфигурации из pyproject
    def _apply_env_overrides(self) -> None:
        numeric_keys = {"RATES_TTL_SECONDS", "LOG_MAX_BYTES", "LOG_BACKUP_COUNT"}

        for key in list(self._data.keys()):
            env_val = os.getenv(key)
            if env_val is None:
                continue

            if key in numeric_keys:
                try:
                    self._data[key] = int(env_val)
                except ValueError as exc:
                    raise ValidationError(
                        f"Переменная окружения {key} должна быть целым числом"
                    ) from exc
                continue

            self._data[key] = env_val

    # Функция нормализации путей - относительные значения приводятся 
    # к абсолютным от корня проекта
    def _normalize_path_settings(self) -> None:
        path_keys = {
            "USERS_PATH",
            "PORTFOLIOS_PATH",
            "RATES_PATH",
            "EXCHANGE_RATES_PATH",
            "SESSION_PATH",
            "LOG_DIR",
            "LOG_FILE",
        }

        for key in path_keys:
            val = self._data.get(key)
            if val is None:
                continue
            if not isinstance(val, str) or not val.strip():
                raise ValidationError(f"Настройка {key} должна быть строкой пути")

            raw_path = Path(val)
            if raw_path.is_absolute():
                self._data[key] = str(raw_path)
            else:
                self._data[key] = str((self._project_root / raw_path).resolve())
