# ValutaTrade Hub

## Описание проекта

ValutaTrade Hub - платформа для отслеживания курсов валют и симуляции торговли ими.  

## Основные возможности

- Регистрация и вход пользователя (session в `data/.session.json`)
- Портфель пользователя (кошельки по валютам)
- Операции:
  - `buy` — покупка валюты за USD по курсу `CUR->USD`
  - `sell` — продажа валюты с начислением USD по курсу `CUR->USD`
- Получение курса из локального кэша (`get-rate`)
- Обновление курсов из внешних API (`update-rates`)
- Просмотр кэша курсов (`show-rates`)
- Логирование операций в `logs/actions.log` (RotatingFileHandler)

---

## Архитектура проекта

### Core (`valutatrade_hub/core`)

Содержит доменную модель и бизнес-логику:

- `models.py` - модели `User`, `Wallet`, `Portfolio`, их валидация и сериализация;
- `usecases.py` - сценарии использования (register, login, buy, sell, show-portfolio, get-rate);
- `currencies.py` - реестр поддерживаемых валют (FIAT и CRYPTO);
- `exceptions.py` - доменные исключения, используемые во всех слоях;
- `utils.py` - вспомогательные функции (валидация, форматирование, работа с валютными парами).

Core не зависит от CLI и Parser Service.

---

### Infra (`valutatrade_hub/infra`)

Инфраструктурный слой:

- `settings.py` - загрузка конфигурации из `pyproject.toml` и переменных окружения (Singleton);
- `database.py` - работа с JSON-хранилищем (`users.json`, `portfolios.json`, `rates.json`),
  атомарная запись файлов и базовая валидация структуры.

---

### Parser Service (`valutatrade_hub/parser_service`)

Сервис получения и хранения курсов валют:

- `api_clients.py` - клиенты внешних API:
  - CoinGecko (криптовалюты),
  - ExchangeRate-API (фиатные валюты);
- `updater.py` - оркестрация обновления курсов и отказоустойчивость;
- `storage.py` - запись snapshot курсов и истории обновлений;
- `scheduler.py` - периодическое обновление курсов;
- `config.py` - конфигурация Parser Service.

---

### CLI (`valutatrade_hub/cli`)

- `interface.py` - CLI-интерфейс на базе `argparse`,
  отображение результатов и дружелюбных сообщений об ошибках.

---

## Установка проекта

### Требования

- Python **3.10+**
- Poetry

### Установка зависимостей

```bash
make install
```

---

## Запуск проекта

```bash
make project
```

или

```bash
poetry run project
```

---

## Команды CLI

### Регистрация

```bash
poetry run project register --username alice --password 1234
```

При регистрации автоматически создается портфель со стартовым балансом 10000.00 USD
(demo-mode).

### Вход

```bash
poetry run project login --username alice --password 1234
```

### Показ портфеля

```bash
poetry run project show-portfolio --base USD
```

### Покупка валюты

```bash
poetry run project buy --currency BTC --amount 0.05
```

### Продажа валюты

```bash
poetry run project sell --currency BTC --amount 0.01
```

### Получение курса

```bash
poetry run project get-rate --from BTC --to USD
```

### Обновление курсов

```bash
poetry run project update-rates
```

### Просмотр курсов

```bash
poetry run project show-rates
```

### Logout (очистка сессии)

```bash
poetry run project logout
```

---

## Кэш курсов и TTL

Курсы валют хранятся в файле `data/rates.json`.

Срок актуальности задается параметром `RATES_TTL_SECONDS` в `pyproject.toml` (по умолчанию 3600 секунд).
При устаревании кэша необходимо выполнить команду `update-rates`.

---

## Parser Service и API-ключ

Для фиатных валют используется ExchangeRate-API.
Ключ задается через переменную окружения:

```bash
export EXCHANGERATE_API_KEY="ВАШ_КЛЮЧ"
```

После этого можно запускать:

```bash
poetry run project update-rates
```
---

## Логи

Логи приложения записываются в каталог `logs/`.
Там фиксируются операции (buy/sell и другие действия), статус OK/ERROR и детали ошибки при исключениях.


