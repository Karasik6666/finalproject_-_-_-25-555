from __future__ import annotations

import logging
import time

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.updater import RatesUpdater

logger = logging.getLogger("valutatrade_hub.parser.scheduler")


def run_periodic_with_updater(updater: RatesUpdater, interval_seconds: int) -> None:

    if not isinstance(interval_seconds, int) or interval_seconds <= 0:
        raise ValueError("interval_seconds должен быть положительным целым числом")

    # Запуск цикла периодического обновления с интервалом sleep
    logger.info("Starting periodic rates update: interval=%s", interval_seconds)
    try:
        while True:
            try:
                updater.run_update()
            except ApiRequestError as exc:
                # Логирование ошибки обновления без остановки цикла
                logger.error("Periodic update error: %s", str(exc))
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        # Завершение цикла по прерыванию с понятной записью в лог
        logger.info("Periodic rates update stopped by user")


# Явная ошибка при вызове без подготовленного RatesUpdater 
# (создание делается в CLI/entrypoint)
def run_periodic(interval_seconds: int) -> None:
    raise RuntimeError(
        "run_periodic(interval_seconds) требует создания RatesUpdater. "
        "Используйте run_periodic_with_updater(updater, interval_seconds)."
    )
