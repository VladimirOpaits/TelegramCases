import logging
import base64
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from database import DatabaseManager
from Cases import CaseManager
from rabbit_manager import RabbitManager
from config import DATABASE_URL, CORS_ORIGINS, API_HOST, API_PORT, RABBITMQ_URL, DEV_MODE, TON_WALLET_ADDRESS
from pydantic import BaseModel
import uvicorn
import os
import json
from contextlib import asynccontextmanager
from dependencies import get_current_user, get_current_user_id
from pytonconnect import TonConnect
from ton_wallet_manager import TonWalletManager, TonWalletRequest, TonWalletResponse
from typing import Optional, List

logging.basicConfig(
  level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True  
)
print("🔧 Логирование настроено в DEBUG режиме")

# Инициализация RabbitMQ менеджера
rabbit_manager = RabbitManager()
use_rabbitmq = rabbit_manager.initialize()


@asynccontextmanager
async def lifespan(app: FastAPI):
  print("🚀 Запуск API сервера...")
  try:
    await db_manager.init_db()
    await case_manager.initialize()
    print("✅ База данных инициализирована")

    if use_rabbitmq:
      await rabbit_manager.connect()

    if rabbit_manager.is_ready:
      print("🐰 RabbitMQ готов к работе")
    else:
      print("⚡ Прямые транзакции активны")

  except Exception as e:
    print(f"❌ Ошибка инициализации: {e}")

  yield

  if rabbit_manager.is_ready:
    await rabbit_manager.disconnect()
  await db_manager.close()
  print("🔌 API сервер остановлен")


app = FastAPI(title="Telegram Casino API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],  # Временно
  allow_credentials=True,
  allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
  allow_headers=["*"],
  expose_headers=["*"]
)

db_manager = DatabaseManager(DATABASE_URL)
case_manager = CaseManager(db_manager)
ton_wallet_manager = TonWalletManager(db_manager)


class FanticsTransaction(BaseModel):
  user_id: int
  amount: int

class TopUpTonRequest(BaseModel):
  amount: int  # Количество фантиков для пополнения

class TopUpStarsRequest(BaseModel):
  amount: int  # Количество фантиков для пополнения

class TopUpRequest(BaseModel):
  amount: int  # Количество фантиков для пополнения
  payment_method: str  # "ton" или "telegram_stars"

class TopUpPayload(BaseModel):
  amount: float  # Количество TON для отправки
  destination: str  # Адрес кошелька для получения
  payload: str  # Текстовый комментарий для транзакции
  comment: str  # Комментарий к транзакции


@app.get("/")
async def root():
  return {
    "message": "Telegram Casino API",
    "status": "running",
    "dev_mode": DEV_MODE,
    "database": "PostgreSQL" if "postgresql" in DATABASE_URL else "SQLite",
    "rabbitmq": {
      "available": rabbit_manager.is_available,
      "connected": rabbit_manager.is_connected,
      "ready": rabbit_manager.is_ready
    },
    "environment": "production" if not DEV_MODE else "development",
    "cors_origins": CORS_ORIGINS,
    "payment_methods": ["ton", "telegram_stars"]
  }


@app.options("/{path:path}")
async def options_handler(path: str):
  return {"message": "CORS preflight OK"}


@app.get("/cases")
async def get_cases():
  """Получить все доступные кейсы"""
  try:
    cases = await case_manager.repository.get_all_cases()

    cases_list = [{
      "id": case.id,
      "name": case.name,
      "cost": case.cost,
      "presents": [{"cost": p.cost, "probability": prob}
                   for p, prob in case.presents_with_probabilities],
      "created_at": case.created_at.isoformat() if case.created_at else None,
      "updated_at": case.updated_at.isoformat() if case.updated_at else None
    } for case in cases.values()]

    return cases_list
  except Exception as e:
    print(f"❌ Ошибка получения кейсов: {e}")
    raise HTTPException(status_code=500, detail=f"Ошибка получения кейсов: {str(e)}")


@app.get("/case/{case_id}")
async def get_case(case_id: int):
  """Получить информацию о конкретном кейсе"""
  try:
    case = await case_manager.repository.get_case(case_id=case_id)
    if not case:
      raise HTTPException(status_code=404, detail="Не нашли кейс, лол")
    return {
      "id": case.id,
      "name": case.name,
      "cost": case.cost,
      "presents": [{"cost": p.cost, "probability": prob}
                   for p, prob in case.presents_with_probabilities],
      "created_at": case.created_at.isoformat() if case.created_at else None,
      "updated_at": case.updated_at.isoformat() if case.updated_at else None
    }
  except ValueError as e:
    raise HTTPException(status_code=404, detail=str(e))


@app.post("/open_case/{case_id}")
async def open_case(case_id: int, user_id: int = Depends(get_current_user_id)):
  """Открыть кейс (требует оплаты фантиками) - БЕЗОПАСНАЯ АТОМАРНАЯ ВЕРСИЯ"""
  try:
    case = await case_manager.repository.get_case(case_id)
    if not case:
      raise HTTPException(status_code=404, detail="Нема такого кейсика")
    
    case_cost = case.cost
    
    # Генерируем выигрыш ДО выполнения транзакции
    gift = case.get_random_present()
    prize_amount = gift.cost

    # Выполняем АТОМАРНУЮ транзакцию
    success, message, new_balance = await db_manager.atomic_case_transaction(
        user_id=user_id,
        case_cost=case_cost,
        prize_amount=prize_amount
    )

    if not success:
      raise HTTPException(status_code=400, detail=message)

    # Если используется RabbitMQ, отправляем уведомления (но НЕ изменяем баланс)
    if rabbit_manager.is_ready:
      await rabbit_manager.send_case_notification(user_id, case_id, case_cost, prize_amount)

    print(f"🎰 Пользователь {user_id} открыл кейс {case_id}: потратил {case_cost}, выиграл {prize_amount}, баланс: {new_balance}")

    return {
      "gift": prize_amount,
      "case_id": case_id,
      "spent": case_cost,
      "profit": prize_amount - case_cost,
      "new_balance": new_balance,
      "message": message
    }
  except ValueError as e:
    raise HTTPException(status_code=404, detail=str(e))
  except HTTPException:
    raise
  except Exception as e:
    print(f"❌ Неожиданная ошибка при открытии кейса: {e}")
    raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@app.post("/fantics/add")
async def add_fantics(
  transaction: FanticsTransaction,
  current_user_id: int = Depends(get_current_user_id)
):
  """Добавить фантики пользователю (только для себя) - АТОМАРНАЯ ВЕРСИЯ"""
  if transaction.user_id != current_user_id:
    raise HTTPException(
      status_code=403,
      detail="Вы можете добавлять фантики только себе"
    )

  if transaction.amount <= 0:
    raise HTTPException(
      status_code=400,
      detail="Сумма должна быть положительной"
    )

  if transaction.amount > 100000:  # Лимит для ручного добавления
    raise HTTPException(
      status_code=400,
      detail="Сумма слишком большая для ручного добавления"
    )

  if rabbit_manager.is_ready:
    await rabbit_manager.send_fantics_transaction(
      user_id=transaction.user_id,
      amount=transaction.amount,
      action="add",
      reason="manual_deposit",
      initiator=current_user_id
    )
    message = f"Запрос на добавление {transaction.amount} фантиков отправлен в очередь"
    print(f"🐰 {message}")
    
    return {
      "status": "ok",
      "message": message,
      "user_id": transaction.user_id,
      "amount": transaction.amount
    }
  else:
    # Используем атомарную операцию
    success, message, new_balance = await db_manager.atomic_add_fantics(transaction.user_id, transaction.amount)
    
    if not success:
      raise HTTPException(status_code=400, detail=message)
    
    print(f"⚡ {message}")
    return {
      "status": "ok",
      "message": message,
      "user_id": transaction.user_id,
      "amount": transaction.amount,
      "new_balance": new_balance
    }


@app.get("/fantics/{user_id}")
async def get_user_fantics(
  user_id: int,
  current_user_id: int = Depends(get_current_user_id)
):
  """Получить баланс фантиков (только свой)"""
  if user_id != current_user_id:
    raise HTTPException(
      status_code=403,
      detail="Вы можете просматривать только свой баланс"
    )

  fantics = await db_manager.get_fantics(user_id)
  if fantics is None:
    raise HTTPException(
      status_code=404,
      detail="Пользователь не найден в системе"
    )

  print(f"У {user_id} {fantics} ебанных фантиков")
  return {"user_id": user_id, "fantics": fantics}

@app.middleware("http")           # Фигня для логирования
async def log_requests(request: Request, call_next):
    if request.url.path == "/ton/connect" and request.method == "POST":
        body = await request.body()
        try:
            body_json = json.loads(body.decode())
            print("=== ВХОДЯЩИЙ ЗАПРОС ===")
            print(f"Headers: {dict(request.headers)}")
            print(f"Body: {json.dumps(body_json, indent=2)}")
        except Exception as e:
            print(f"Ошибка парсинга body: {e}")
            print(f"Raw body: {body}")
        
        async def receive():
            return {"type": "http.request", "body": body}
        request._receive = receive
    
    response = await call_next(request)
    return response

@app.get("/ton/wallets", response_model=List[TonWalletResponse])
async def get_user_ton_wallets(current_user_id: int = Depends(get_current_user_id)):
    """Получение всех TON кошельков пользователя"""
    try:
        return await ton_wallet_manager.get_user_wallets(current_user_id, current_user_id)
    except HTTPException as e:
        print(f"HTTPException: {e.status_code} - {e.detail}")
        raise
    except Exception as e:
        print(f"Неожиданная ошибка: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ton/connect", response_model=TonWalletResponse)
async def connect_ton_wallet(
    wallet_data: TonWalletRequest,  
    current_user_id: int = Depends(get_current_user_id)
):
    print("=== ОБРАБОТКА TON CONNECT ===")
    print(f"Parsed wallet_data: {wallet_data}")
    print(f"Current user ID: {current_user_id}")
    
    try:
        result = await ton_wallet_manager.connect_wallet(wallet_data, current_user_id)
        print(f"Успешный результат: {result}")
        return result
    except HTTPException as e:
        print(f"HTTPException: {e.status_code} - {e.detail}")
        raise
    except Exception as e:
        print(f"Неожиданная ошибка: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/topup/stars")
async def topup_with_stars(
    request: TopUpStarsRequest,
    current_user_id: int = Depends(get_current_user_id)
):
    """Пополнение счета через Telegram Stars"""
    try:
        # Валидация суммы пополнения
        if request.amount <= 0:
            raise HTTPException(status_code=400, detail="Сумма пополнения должна быть больше 0")
        
        if request.amount > 1000000:  # Лимит на пополнение
            raise HTTPException(status_code=400, detail="Сумма пополнения слишком большая")
        
        # Отправляем запрос в телеграм бота через RabbitMQ
        if rabbit_manager.is_ready:
            success = await rabbit_manager.send_stars_payment_request(current_user_id, request.amount)
            
            if success:
                return {
                    "success": True,
                    "message": f"Запрос на пополнение {request.amount} фантиков через Telegram Stars отправлен",
                    "amount": request.amount,
                    "payment_method": "telegram_stars",
                    "status": "pending"
                }
            else:
                raise HTTPException(status_code=500, detail="Ошибка отправки запроса на оплату звездочками")
        else:
            raise HTTPException(status_code=503, detail="Сервис пополнения через звездочки временно недоступен")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Ошибка при пополнении через звездочки: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

@app.post("/topup/ton/create_payload")
async def create_ton_topup_payload(
    request: TopUpTonRequest,
    current_user_id: int = Depends(get_current_user_id)
):
    """Создание payload для пополнения счета через TON"""
    try:
        # Валидация суммы пополнения
        if request.amount <= 0:
            raise HTTPException(status_code=400, detail="Сумма пополнения должна быть больше 0")
        
        if request.amount > 1000000:  # Лимит на пополнение
            raise HTTPException(status_code=400, detail="Сумма пополнения слишком большая")
        
        # Конвертируем фантики в TON (1 TON = 1000 фантиков)
        ton_amount = request.amount / 1000.0
        
        # Адрес кошелька для получения платежей (из конфигурации)
        destination_wallet = TON_WALLET_ADDRESS
        
        # Создаем короткий комментарий для транзакции (TON имеет ограничения на длину)
        comment = f"Fantics {request.amount} ID:{current_user_id}"
        
        # Проверяем длину комментария (TON рекомендует до 127 символов)
        if len(comment) > 127:
            comment = f"Fantics {request.amount}"
        
        return TopUpPayload(
            amount=ton_amount,
            destination=destination_wallet,
            payload=comment,  # Используем короткий текстовый payload
            comment=comment
        )
        
    except Exception as e:
        print(f"❌ Ошибка при создании TON payload: {e}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")

@app.post("/topup/ton/confirm")
async def confirm_ton_topup(
    request: TopUpTonRequest,
    current_user_id: int = Depends(get_current_user_id)
):
    """Подтверждение пополнения счета после успешной TON транзакции"""
    try:
        # ВНИМАНИЕ: Здесь КРИТИЧЕСКИ ВАЖНО добавить проверку транзакции в блокчейне!
        # Пока что используем атомарное добавление фантиков
        
        # Валидация суммы пополнения
        if request.amount <= 0:
            raise HTTPException(status_code=400, detail="Сумма пополнения должна быть больше 0")
        
        if request.amount > 1000000:  # Лимит на пополнение
            raise HTTPException(status_code=400, detail="Сумма пополнения слишком большая")
        
        success, message, new_balance = await db_manager.atomic_add_fantics(current_user_id, request.amount)
        
        if success:
            print(f"✅ TON пополнение: пользователь {current_user_id} получил {request.amount} фантиков, баланс: {new_balance}")
            return {
                "success": True, 
                "message": message,
                "new_balance": new_balance,
                "added_amount": request.amount,
                "payment_method": "ton"
            }
        else:
            raise HTTPException(status_code=400, detail=message)
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Ошибка при подтверждении TON пополнения: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

# Оставляем старые эндпоинты для обратной совместимости
@app.post("/topup/create_payload")
async def create_topup_payload(
    request: TopUpRequest,
    current_user_id: int = Depends(get_current_user_id)
):
    """Создание payload для пополнения счета (старый эндпоинт для обратной совместимости)"""
    try:
        # Проверяем, что пользователь выбрал TON как метод оплаты
        if request.payment_method != "ton":
            raise HTTPException(status_code=400, detail="Используйте /topup/stars для оплаты звездочками")
        
        # Переадресуем на новый эндпоинт
        ton_request = TopUpTonRequest(amount=request.amount)
        return await create_ton_topup_payload(ton_request, current_user_id)
        
    except Exception as e:
        print(f"❌ Ошибка в старом эндпоинте: {e}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")

@app.post("/topup/confirm")
async def confirm_topup(
    request: TopUpRequest,
    current_user_id: int = Depends(get_current_user_id)
):
    """Подтверждение пополнения счета (старый эндпоинт для обратной совместимости)"""
    try:
        # Переадресуем на новый эндпоинт для TON
        ton_request = TopUpTonRequest(amount=request.amount)
        return await confirm_ton_topup(ton_request, current_user_id)
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Ошибка в старом эндпоинте подтверждения: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")



# Подключаем RabbitMQ роутер, если он доступен
rabbit_router = rabbit_manager.get_router()
if rabbit_router:
  @rabbit_router.subscriber("transactions")
  async def handle_transaction(message: dict):
    """Обработчик транзакций фантиков"""
    try:
      user_id = message["user_id"]
      amount = message["amount"]
      action = message["action"]
      reason = message.get("reason", "unknown")

      print(f"🐰 Обработка транзакции: {action} {amount} фантиков для пользователя {user_id}, причина: {reason}")

      if action == "add":
        success = await db_manager.add_fantics(user_id, amount)
        if success:
          print(f"✅ Добавлено {amount} фантиков пользователю {user_id}")
        else:
          print(f"❌ Ошибка добавления {amount} фантиков пользователю {user_id}")
      elif action == "spend":
        success = await db_manager.subtract_fantics(user_id, amount)
        if success:
          print(f"✅ Списано {amount} фантиков у пользователя {user_id}")
        else:
          print(f"❌ Ошибка списания {amount} фантиков у пользователя {user_id}")

    except Exception as e:
      print(f"❌ Ошибка обработки транзакции: {e}")

  @rabbit_router.subscriber("telegram_payments")
  async def handle_telegram_payment(message: dict):
    """Обработчик платежей через телеграм (звездочки)"""
    try:
      user_id = message["user_id"]
      amount = message["amount"]
      action = message["action"]
      payment_method = message.get("payment_method", "unknown")
      
      print(f"🌟 Обработка платежа: {action} на {amount} фантиков для пользователя {user_id} через {payment_method}")
      
      if action == "request_stars_payment":
        # Здесь будет логика взаимодействия с телеграм ботом для оплаты звездочками
        print(f"📤 Отправка запроса на оплату звездочками для пользователя {user_id}, сумма: {amount} фантиков")
        # TODO: Реализовать отправку сообщения в телеграм бота
        
    except Exception as e:
      print(f"❌ Ошибка обработки платежа через телеграм: {e}")

  app.include_router(rabbit_router)

if __name__ == "__main__":
  print(f"🌐 Запуск сервера на http://{API_HOST}:{API_PORT}")
  print(f"🗄️ База данных: {'Neon PostgreSQL' if 'neon' in DATABASE_URL else 'PostgreSQL' if 'postgresql' in DATABASE_URL else 'SQLite'}")
  print(f"🐰 RabbitMQ: {'Включен' if rabbit_manager.is_available else 'Отключен'}")
  uvicorn.run("main:app", host=API_HOST, port=API_PORT)

