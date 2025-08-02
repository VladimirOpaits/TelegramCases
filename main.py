import logging
import base64
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from database import DatabaseManager
from Cases import CaseManager
from rabbit_manager import RabbitManager
from config import DATABASE_URL, CORS_ORIGINS, API_HOST, API_PORT, RABBITMQ_URL, DEV_MODE
import config
from pydantic import BaseModel
import uvicorn
import os
import json
from contextlib import asynccontextmanager
from dependencies import get_current_user, get_current_user_id
from pytonconnect import TonConnect
from payment_manager import PaymentManager, TonWalletRequest, TonWalletResponse, FanticsTransaction, TopUpTonRequest, TopUpStarsRequest, TopUpPayload, TopUpRequest
from typing import Optional, List

logging.basicConfig(
  level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True  
)
print("🔧 Логирование настроено в DEBUG режиме")


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
      # Настройка RabbitMQ обработчиков
      await rabbit_manager.setup_handlers_and_include_router(app)
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
rabbit_manager = RabbitManager(db_manager)
use_rabbitmq = rabbit_manager.initialize()
payment_manager = PaymentManager(db_manager, rabbit_manager)


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
    
    gift = case.get_random_present()
    prize_amount = gift.cost

    success, message, new_balance = await db_manager.atomic_case_transaction(
        user_id=user_id,
        case_cost=case_cost,
        prize_amount=prize_amount
    )

    if not success:
      raise HTTPException(status_code=400, detail=message)


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
  """Добавить фантики пользователю (только для себя)"""
  try:
    return await payment_manager.add_fantics_manual(transaction, current_user_id)
  except HTTPException:
    raise
  except Exception as e:
    print(f"❌ Ошибка при добавлении фантиков: {e}")
    raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


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
        return await payment_manager.get_user_ton_wallets(current_user_id, current_user_id)
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
        result = await payment_manager.connect_ton_wallet(wallet_data, current_user_id)
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
        return await payment_manager.create_stars_payment(request, current_user_id)
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
        return await payment_manager.create_ton_payment_payload(request, current_user_id)
    except HTTPException:
        raise
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
        return await payment_manager.confirm_ton_payment(request, current_user_id)
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


@app.post("/test/stars_payment")
async def test_stars_payment(
    amount: int = 100,
    current_user_id: int = Depends(get_current_user_id)
):
    """Тестовый эндпоинт для проверки работы Telegram Stars платежей"""
    try:
        if rabbit_manager.is_ready:
            success = await rabbit_manager.send_stars_payment_request(current_user_id, amount)
            
            if success:
                return {
                    "success": True,
                    "message": f"Тестовый запрос на {amount} фантиков отправлен в Telegram бот",
                    "user_id": current_user_id,
                    "amount": amount,
                    "note": "Проверьте Telegram - должен прийти invoice для оплаты звездочками"
                }
            else:
                raise HTTPException(status_code=500, detail="Ошибка отправки тестового запроса")
        else:
            raise HTTPException(
                status_code=503, 
                detail="RabbitMQ не подключен. Убедитесь, что RabbitMQ запущен и доступен."
            )
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Ошибка тестового эндпоинта: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка тестирования: {str(e)}")




if __name__ == "__main__":
  print(f"🌐 Запуск сервера на http://{API_HOST}:{API_PORT}")
  print(f"🗄️ База данных: {'Neon PostgreSQL' if 'neon' in DATABASE_URL else 'PostgreSQL' if 'postgresql' in DATABASE_URL else 'SQLite'}")
  print(f"🐰 RabbitMQ: {'Включен' if rabbit_manager.is_available else 'Отключен'}")
  uvicorn.run("main:app", host=API_HOST, port=API_PORT)

