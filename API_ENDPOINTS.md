# API Эндпоинты для пополнения

## Обзор изменений

Работа с RabbitMQ вынесена в отдельный модуль `rabbit_manager.py`. Созданы отдельные эндпоинты для пополнения через TON и Telegram Stars.

## Новые эндпоинты

### 1. Пополнение через Telegram Stars

**POST** `/topup/stars`

Отправляет запрос в телеграм бота для оплаты звездочками.

```json
{
  "amount": 1000
}
```

**Ответ:**
```json
{
  "success": true,
  "message": "Запрос на пополнение 1000 фантиков через Telegram Stars отправлен",
  "amount": 1000,
  "payment_method": "telegram_stars",
  "status": "pending"
}
```

### 2. Пополнение через TON - создание payload

**POST** `/topup/ton/create_payload`

Создает данные для TON транзакции.

```json
{
  "amount": 1000
}
```

**Ответ:**
```json
{
  "amount": 1.0,
  "destination": "EQD4FPq-PRDieyQKkizFTRtSDyucUIqrj0v_zXJmqaDp6_0t",
  "payload": "Fantics 1000 ID:123456",
  "comment": "Fantics 1000 ID:123456"
}
```

### 3. Пополнение через TON - подтверждение

**POST** `/topup/ton/confirm`

Подтверждает успешную TON транзакцию и начисляет фантики.

```json
{
  "amount": 1000
}
```

**Ответ:**
```json
{
  "success": true,
  "message": "Фантики успешно добавлены",
  "new_balance": 15000,
  "added_amount": 1000,
  "payment_method": "ton"
}
```

## Старые эндпоинты (для обратной совместимости)

Эндпоинты `/topup/create_payload` и `/topup/confirm` сохранены, но теперь перенаправляют на соответствующие TON эндпоинты.

## RabbitMQ очереди

### Очередь: `telegram_payments`
Для запросов на оплату звездочками:
```json
{
  "user_id": 123456,
  "amount": 1000,
  "action": "request_stars_payment",
  "payment_method": "telegram_stars",
  "reason": "fantics_topup_stars_1000"
}
```

### Очередь: `transactions`
Для общих транзакций с фантиками:
```json
{
  "user_id": 123456,
  "amount": 1000,
  "action": "add",
  "reason": "manual_deposit"
}
```

## Проверка статуса системы

**GET** `/`

Возвращает информацию о статусе системы, включая состояние RabbitMQ:

```json
{
  "message": "Telegram Casino API",
  "status": "running",
  "rabbitmq": {
    "available": true,
    "connected": true,
    "ready": true
  },
  "payment_methods": ["ton", "telegram_stars"]
}
```

## Использование RabbitManager

Новый модуль `rabbit_manager.py` предоставляет централизованное управление RabbitMQ:

```python
from rabbit_manager import RabbitManager

# Инициализация
rabbit_manager = RabbitManager()
rabbit_manager.initialize()

# Подключение
await rabbit_manager.connect()

# Отправка запроса на звездочки
await rabbit_manager.send_stars_payment_request(user_id, amount)

# Отправка обычной транзакции
await rabbit_manager.send_fantics_transaction(user_id, amount, "add", "topup")

# Проверка готовности
if rabbit_manager.is_ready:
    # RabbitMQ готов к работе
```

## Конвертация валют

- **TON → Фантики**: 1 TON = 1000 фантиков
- **Telegram Stars → Фантики**: 1:1 (настраивается в телеграм боте)