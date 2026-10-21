# Nebus Payment Service

Асинхронный сервис обработки платежей на FastAPI, PostgreSQL и RabbitMQ.

## Технологии

- Python
- FastAPI и Pydantic v2
- SQLAlchemy 2 (Async)
- PostgreSQL
- RabbitMQ и FastStream
- Alembic
- Docker Compose
- Pytest

## Архитектура

Сервис состоит из нескольких компонентов:

- **API** — принимает запросы на создание платежей и получение их статуса.
- **PostgreSQL** — хранит платежи, их статусы и служебные данные.
- **Outbox Publisher** — публикует события из базы данных в RabbitMQ.
- **Payment Consumer** — асинхронно обрабатывает платежи и обновляет их статусы.
- **Webhook Worker** — отправляет уведомления о результатах обработки.
- **RabbitMQ** — обеспечивает обмен сообщениями между компонентами.

## Возможности

- Создание платежей с уникальным идентификатором UUID.
- Поддержка валют RUB, USD и EUR.
- Идемпотентность создания платежей через заголовок `Idempotency-Key`.
- Авторизация API через заголовок `X-API-Key`.
- Асинхронная обработка платежей.
- Статусы `pending`, `succeeded`, `failed`.
- Transactional Outbox для надёжной публикации событий.
- Повторные попытки обработки сообщений и Dead Letter Queue.
- Отправка webhook-уведомлений с повторными попытками.
- Контейнеризация через Docker Compose.
- Автоматические тесты.

## Быстрый запуск

### Требования

- Docker Desktop с Docker Compose
- Python 3.12

### 1. Настройка окружения

Скопируйте пример конфигурации:

```powershell
Copy-Item .env.example .env
```

Замените значения `change_me` и `replace_with_your_api_key` в файле `.env` на собственные.

Пароли PostgreSQL и RabbitMQ должны совпадать с паролями в соответствующих строках подключения.

### 2. Запуск инфраструктуры

```powershell
docker compose up -d postgres rabbitmq rabbitmq-init
```

### 3. Установка зависимостей

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 4. Применение миграций

```powershell
python -m alembic upgrade head
```

Alembic использует переменную `DATABASE_URL` из `.env`.

### 5. Запуск приложения

```powershell
docker compose up -d --build
```

API будет доступен по адресу `http://localhost:8000`.

### 6. Проверка контейнеров

```powershell
docker compose ps -a
```

Сервисы `api`, `consumer`, `publisher` и `webhook-worker` должны работать.

PostgreSQL и RabbitMQ должны иметь статус `healthy`.

Сервис `rabbitmq-init` выполняется однократно и может иметь статус `Exited (0)` — это нормально.

## API

Базовый адрес: `http://localhost:8000`

### Проверка работоспособности

```powershell
$headers = @{
    "X-API-Key" = "replace_with_your_api_key"
}

Invoke-RestMethod `
    -Uri "http://localhost:8000/health" `
    -Method Get `
    -Headers $headers
```

### Создание платежа

**POST** `/api/v1/payments`

Для создания платежа необходимы заголовки:

- `X-API-Key` — ключ доступа к API.
- `Idempotency-Key` — уникальный ключ запроса, предотвращающий повторное создание платежа при повторной отправке.

Пример для PowerShell:

```powershell
$headers = @{
    "X-API-Key" = "replace_with_your_api_key"
    "Idempotency-Key" = [guid]::NewGuid().ToString()
}

$body = @{
    amount = "1500.50"
    currency = "RUB"
    description = "Test payment"
    metadata = @{
        order_id = "ORDER-001"
    }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
    -Uri "http://localhost:8000/api/v1/payments" `
    -Method Post `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $body
```

Замените `replace_with_your_api_key` на значение `API_KEY` из `.env`.

При успешном создании платежа API возвращает HTTP `202 Accepted`. Платёж создаётся со статусом `pending` и далее обрабатывается асинхронно.

Поддерживаемые валюты: `RUB`, `USD`, `EUR`.

Поля `metadata` и `webhook_url` необязательны.

### Получение статуса платежа

**GET** `/api/v1/payments/{payment_id}`

Позволяет получить информацию о платеже по его UUID.

Пример для PowerShell:

```powershell
$paymentId = "replace_with_payment_uuid"

$headers = @{
    "X-API-Key" = "replace_with_your_api_key"
}

Invoke-RestMethod `
    -Uri "http://localhost:8000/api/v1/payments/$paymentId" `
    -Method Get `
    -Headers $headers
```

Замените `replace_with_payment_uuid` на идентификатор, полученный после создания платежа, а `replace_with_your_api_key` — на значение `API_KEY` из `.env`.

При успешном запросе API возвращает HTTP `200 OK`.

Возможные статусы платежа:

- `pending` — платёж ожидает завершения обработки.
- `succeeded` — платёж успешно обработан.
- `failed` — обработка платежа завершилась неудачей.

Обработка выполняется асинхронно, поэтому статус может измениться спустя несколько секунд после создания платежа.

## Надёжность обработки

### Transactional Outbox

При создании платежа информация о нём и событие для отправки в RabbitMQ сохраняются в PostgreSQL.

Отдельный Outbox Publisher публикует подготовленные события в очередь `payments.new`.

Такой подход снижает риск потери события при сбое между сохранением платежа и отправкой сообщения.

### Обработка платежей и Retry

Payment Consumer получает сообщения из RabbitMQ и запускает асинхронную обработку платежей.

При технической ошибке выполняется до трёх попыток обработки:

- Первая попытка — сразу.
- Вторая попытка — после задержки 2 секунды.
- Третья попытка — после задержки 4 секунды.

После исчерпания попыток Consumer отклоняет сообщение.

### Dead Letter Queue

RabbitMQ использует следующую конфигурацию:

- Основная очередь: `payments.new`.
- Dead Letter Exchange: `payments.dlx`.
- Очередь ошибок: `payments.failed`.
- Политика маршрутизации: `payments-dlx-policy`.

Отклонённые сообщения направляются через Dead Letter Exchange в `payments.failed`.

### Webhook Delivery

После обработки платежа отдельный Webhook Worker отвечает за отправку HTTP-уведомлений.

Worker проверяет ожидающие доставки задачи каждые 2 секунды и обрабатывает до 10 задач за проход.

При сетевых ошибках предусмотрено до трёх попыток доставки с задержками 2 и 4 секунды.

Состояние доставки и количество попыток сохраняются в PostgreSQL.

Возможные статусы доставки:

- `pending` — ожидает отправки или повторной попытки.
- `delivered` — уведомление успешно доставлено.
- `failed` — доставка завершилась ошибкой.

Некорректные webhook-адреса отклоняются без повторных попыток.

Для защиты от конкурентной обработки задач используется блокировка строк PostgreSQL `FOR UPDATE SKIP LOCKED`.

Webhook URL проходят проверку безопасности. Для использования реальных внешних адресов необходимо настроить разрешённые хосты в соответствии с конфигурацией приложения.

### Восстановление webhook-задач после сбоя

Для предотвращения одновременной обработки одной задачи несколькими экземплярами Webhook Worker используется механизм временного резервирования (lease).

При получении задачи Worker:

1. Выбирает доступную задачу с использованием PostgreSQL `FOR UPDATE SKIP LOCKED`.
2. Переводит её в статус `processing`.
3. Увеличивает счётчик `attempts`.
4. Создаёт уникальный `lease_token`.
5. Устанавливает `lease_expires_at` на 60 секунд вперёд.
6. Выполняет HTTP-запрос вне транзакции PostgreSQL.

После завершения запроса Worker проверяет `lease_token` перед обновлением результата доставки. Это предотвращает изменение состояния задачи экземпляром Worker, потерявшим право на её обработку.

Если Worker завершится аварийно, задача останется в статусе `processing`. После истечения `lease_expires_at` другой Worker сможет повторно зарезервировать её, если лимит попыток ещё не исчерпан.

После истечения резервирования при трёх использованных попытках задача переводится в `failed`.

Таким образом, сбой Worker не приводит к бесконечной блокировке webhook-задачи.

**Особенности реализации:**

- Для отправки webhook используется отдельный Worker, чтобы не задерживать обработку платежей.
- Разрешены только HTTPS-адреса с хостами из `WEBHOOK_ALLOWED_HOSTS`.
- HTTP-перенаправления отключены.
- Механизм доставки рассчитан на *at-least-once*: при сбое после успешной отправки, но до сохранения результата получатель может получить повторное уведомление.

## Тестирование

Проект содержит автоматические тесты API, обработки сообщений RabbitMQ, валидации webhook URL и работы Webhook Worker.

Для запуска тестов из корневой директории проекта:

```powershell
python -m pytest tests/ -v
```

Большинство автоматических тестов используют подмену внешних зависимостей и не выполняют реальные HTTP-запросы к внешним сервисам.

Интеграционный тест `tests/test_processing_concurrency.py` использует настоящую PostgreSQL для проверки конкурентной обработки одного платежа и отсутствия дублирующих webhook-задач.

Перед запуском полного набора тестов необходимо запустить PostgreSQL:

```powershell
docker compose up -d postgres
```

Также необходимо настроить переменную `DATABASE_URL` в файле `.env` и применить миграции:

```powershell
python -m alembic upgrade head
```

После этого можно выполнить:

```powershell
python -m pytest tests/ -v
```

Интеграционный тест создаёт временный платёж и удаляет его после завершения проверки. Для этого теста рекомендуется использовать отдельную тестовую базу данных.

Дополнительно механизмы восстановления webhook-задач и маршрутизации сообщений в Dead Letter Queue проверялись интеграционными сценариями с PostgreSQL и RabbitMQ.

Проверенные сценарии включают:

- Повторное резервирование webhook-задачи после истечения lease.
- Предотвращение обновления задачи с устаревшим `lease_token`.
- Перевод webhook-задачи в `failed` после исчерпания попыток.
- Перемещение сообщения из `payments.new` в `payments.failed` после трёх неудачных попыток обработки.