from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from valutatrade_hub.infra.settings import SettingsLoader


def setup_logging(level: str | None = None) -> None:
    settings = SettingsLoader()

    # определение директории и файла логов из настроек
    log_dir = Path(str(settings.get("LOG_DIR", "logs")))
    log_file = Path(str(settings.get("LOG_FILE", str(log_dir / "actions.log"))))

    # определение уровня логирования (аргумент функции имеет приоритет)
    log_level_name = (level or str(settings.get("LOG_LEVEL", "INFO"))).upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    # Параметры ротации логов
    max_bytes = int(settings.get("LOG_MAX_BYTES", 1_048_576))
    backup_count = int(settings.get("LOG_BACKUP_COUNT", 3))

    # гарантированное создание директории логов
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # формат сообщений логирования
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    # конфигурация корневого логгера
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # очистка ранее зарегистрированных обработчиков
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    # файловый обработчик с ротацией
    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(log_file),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)

    # консольный обработчик
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    # регистрация обработчиков
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)