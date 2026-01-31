from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

T = TypeVar("T")

logger = logging.getLogger("valutatrade_hub.actions")


def _iso_utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def log_action(
    action: str,
    verbose: bool = False,
) -> Callable[[Callable[..., T]], Callable[..., T]]:

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # фиксация момента начала операции
            ts = _iso_utc_now()

            # извлечение идентификаторов пользователя и параметров операции
            user_id = kwargs.get("user_id")
            username = kwargs.get("username")
            currency_code: str | None = (
                kwargs.get("currency_code") 
                or kwargs.get("currency")
            )
            amount = kwargs.get("amount")
            rate = kwargs.get("rate")
            base = kwargs.get("base")

            # состояние кошельков до выполнения операции (verbose-режим)
            pre_state = kwargs.get("_pre_state") if verbose else None

            try:
                result = func(*args, **kwargs)

                # состояние кошельков после выполнения операции (verbose-режим)
                post_state = kwargs.get("_post_state") if verbose else None

                # формирование сообщения об успешном выполнении
                msg_parts = [
                    f"ts={ts}",
                    f"action={action}",
                    f"user_id={user_id}" if user_id is not None else "",
                    f"username={username}" if username else "",
                    f"currency={currency_code}" if currency_code else "",
                    f"amount={amount}" if amount is not None else "",
                    f"rate={rate}" if rate is not None else "",
                    f"base={base}" if base else "",
                    "result=OK",
                ]

                if verbose and pre_state is not None and post_state is not None:
                    msg_parts.append(f"wallets_before={pre_state}")
                    msg_parts.append(f"wallets_after={post_state}")

                logger.info(" ".join(part for part in msg_parts if part))
                return result

            except Exception as exc:
                # формирование сообщения об ошибке выполнения операции
                msg_parts = [
                    f"ts={ts}",
                    f"action={action}",
                    f"user_id={user_id}" if user_id is not None else "",
                    f"username={username}" if username else "",
                    f"currency={currency_code}" if currency_code else "",
                    f"amount={amount}" if amount is not None else "",
                    f"rate={rate}" if rate is not None else "",
                    f"base={base}" if base else "",
                    "result=ERROR",
                    f"error_type={type(exc).__name__}",
                    f"error_message={str(exc)}",
                ]

                logger.error(" ".join(part for part in msg_parts if part))
                raise

        return wrapper

    return decorator
