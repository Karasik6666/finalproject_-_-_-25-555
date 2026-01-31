from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from prettytable import PrettyTable

from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    AuthError,
    CurrencyNotFoundError,
    InsufficientFundsError,
    NotLoggedInError,
    ValidationError,
)
from valutatrade_hub.core.usecases import TradingUseCases
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.api_clients import (
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RatesStorage
from valutatrade_hub.parser_service.updater import RatesUpdater


# Получение пути до файла сессии из настроек проекта
def _session_path() -> Path:
    settings = SettingsLoader()
    raw = settings.get("SESSION_PATH", "data/.session.json")
    return Path(str(raw))


# Чтение данных сессии из файла (если файла нет или он битый - None)
def _load_session() -> dict[str, Any] | None:
    path = _session_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


# Сохранение сессии в файл (создание директории при необходимости)
def _save_session(data: dict[str, Any]) -> None:
    path = _session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# Очистка файла сессии (ошибка удаления не должна ломать работу CLI)
def _clear_session() -> None:
    path = _session_path()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


# Проверка наличия активной сессии перед командами, где нужен login
def _require_login() -> dict[str, Any]:
    session = _load_session()
    if not session or "user_id" not in session:
        raise NotLoggedInError("Сначала выполните login")
    return session


# Печать словаря в простом виде "ключ-значение"
def _print_kv(title: str, data: dict[str, Any]) -> None:
    print(title)
    for k, v in data.items():
        print(f"- {k}: {v}")


# Приведение типичных ошибок приложения к понятным сообщениям в CLI
def _handle_error(exc: Exception) -> int:
    if isinstance(exc, NotLoggedInError):
        print(str(exc))
        return 1

    if isinstance(exc, InsufficientFundsError):
        print(str(exc))
        return 1

    if isinstance(exc, CurrencyNotFoundError):
        print(f"{exc}. Проверьте код валюты.")
        return 1

    if isinstance(exc, ApiRequestError):
        print(f"{exc}. Попробуйте позже или запустите update-rates.")
        return 1

    if isinstance(exc, ValidationError | AuthError):
        print(str(exc))
        return 1

    print(f"Неожиданная ошибка: {exc.__class__.__name__}: {exc}")
    return 1

# Сборка argparse-парсера и определение всех CLI-команд
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="valutatrade",
        description="ValutaTrade Hub CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_register = sub.add_parser("register", help="Регистрация пользователя")
    p_register.add_argument("--username", required=True)
    p_register.add_argument("--password", required=True)

    p_login = sub.add_parser("login", help="Вход пользователя")
    p_login.add_argument("--username", required=True)
    p_login.add_argument("--password", required=True)

    sub.add_parser("logout", help="Выход (очистка сессии)")

    p_show = sub.add_parser("show-portfolio", help="Показать портфель")
    p_show.add_argument("--base", default="USD")

    p_buy = sub.add_parser("buy", help="Покупка валюты")
    p_buy.add_argument("--currency", required=True)
    p_buy.add_argument("--amount", required=True, type=float)

    p_sell = sub.add_parser("sell", help="Продажа валюты")
    p_sell.add_argument("--currency", required=True)
    p_sell.add_argument("--amount", required=True, type=float)

    p_rate = sub.add_parser("get-rate", help="Получить курс")
    p_rate.add_argument("--from", dest="from_code", required=True)
    p_rate.add_argument("--to", dest="to_code", required=True)

    p_update = sub.add_parser("update-rates", help="Обновить курсы")
    p_update.add_argument(
        "--source",
        choices=["coingecko", "exchangerate"],
        help="Ограничить обновление одним источником",
    )

    sub.add_parser("show-rates", help="Показать курсы из кэша")
    return parser


# Точка входа CLI: разбор аргументов и вызов нужного use-case
def main_cli() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    uc = TradingUseCases()

    try:
        if args.command == "register":
            res = uc.register(args.username, args.password)
            print("Пользователь зарегистрирован.")
            print(
                "Demo-mode: при регистрации создается USD-кошелек "
                "со стартовым балансом 10000.00 USD."
            )
            _print_kv("Данные:", res)

        elif args.command == "login":
            res = uc.login(args.username, args.password)
            _save_session(res)
            print(
                f"Вход выполнен: user_id={res['user_id']}, username={res['username']}"
            )

        elif args.command == "logout":
            _clear_session()
            print("Сессия очищена.")

        elif args.command == "show-portfolio":
            session = _require_login()
            res = uc.show_portfolio(session["user_id"], base=args.base)

            table = PrettyTable(["Currency", "Balance"])
            for row in res["rows"]:
                table.add_row([row["currency"], row["balance_display"]])

            print(table)
            print(f"TOTAL ({res['base']}): {res['total']:.2f}")

        elif args.command == "buy":
            session = _require_login()
            res = uc.buy(
                user_id=session["user_id"],
                currency_code=args.currency,
                amount=args.amount,
            )
            print("Покупка выполнена.")
            print(
                f"Списано: {res['cost_usd']:.2f} {res['base']} "
                f"по курсу {res['rate']:.8f}"
            )

        elif args.command == "sell":
            session = _require_login()
            res = uc.sell(
                user_id=session["user_id"],
                currency_code=args.currency,
                amount=args.amount,
            )
            print("Продажа выполнена.")
            print(
                f"Начислено: {res['revenue_usd']:.2f} {res['base']} "
                f"по курсу {res['rate']:.8f}"
            )

        elif args.command == "get-rate":
            info = uc.get_rate(args.from_code, args.to_code)
            print(
                f"{info.pair}: {info.rate} "
                f"(updated_at={info.updated_at}, source={info.source})"
            )

        elif args.command == "update-rates":
            # Инициализация Parser Service
            config = ParserConfig.load()
            storage = RatesStorage()
            clients = [CoinGeckoClient(config), ExchangeRateApiClient(config)]
            updater = RatesUpdater(clients, storage)
            updater.run_update(source=args.source)
            print("Курсы успешно обновлены.")

        elif args.command == "show-rates":
            storage = RatesStorage()
            snapshot = storage.load_snapshot()
            pairs = snapshot.get("pairs", {})
            last_refresh = snapshot.get("last_refresh")

            print(f"last_refresh: {last_refresh}")
            table = PrettyTable(["Pair", "Rate", "Source", "Updated at"])
            if isinstance(pairs, dict):
                for pair, entry in sorted(pairs.items(), key=lambda x: x[0]):
                    if not isinstance(entry, dict):
                        continue
                    table.add_row(
                        [
                            pair,
                            entry.get("rate"),
                            entry.get("source"),
                            entry.get("updated_at"),
                        ]
                    )
            print(table)

        else:
            raise ValidationError("Неизвестная команда")

    except Exception as exc:  # noqa: BLE001
        code = _handle_error(exc)
        sys.exit(code)