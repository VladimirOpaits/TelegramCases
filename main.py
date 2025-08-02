import logging
import json
import uvicorn

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from contextlib import asynccontextmanager

from database import DatabaseManager
from Cases import CaseManager
from rabbit_manager import RabbitManager
from config import DATABASE_URL, API_HOST, API_PORT, CORS_ORIGINS, DEV_MODE
from dependencies import get_current_user, get_current_user_id
from payment_manager import PaymentManager, TonWalletRequest, TonWalletResponse, FanticsTransaction, TopUpTonRequest, TopUpStarsRequest, TopUpPayload, TopUpRequest


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', force=True)
for logger in ["uvicorn.access", "uvicorn.error", "fastapi", "sqlalchemy", "aio_pika", "aiormq"]:
    logging.getLogger(logger).setLevel(logging.WARNING)


db_manager = DatabaseManager(DATABASE_URL)
case_manager = CaseManager(db_manager)
rabbit_manager = RabbitManager(db_manager)
use_rabbitmq = rabbit_manager.initialize()
payment_manager = PaymentManager(db_manager, rabbit_manager)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Запуск API сервера...")
    
    try:
        # Инициализация базы данных
        await db_manager.init_db()
        await case_manager.initialize()
        print("✅ База данных инициализирована")

        # Инициализация RabbitMQ
        if use_rabbitmq:
            await rabbit_manager.connect()

        if rabbit_manager.is_ready:
            print("🐰 RabbitMQ готов к работе")
            await rabbit_manager.setup_handlers_and_include_router(app)
        else:
            print("⚡ Прямые транзакции активны")
        
        print("✅ API сервер готов к работе")

    except Exception as e:
        print(f"❌ Критическая ошибка инициализации: {e}")
        raise  # Пробрасываем ошибку дальше

    yield
    print("🔌 Остановка API сервера...")
    try:
        if rabbit_manager.is_ready:
            await rabbit_manager.disconnect()
        await db_manager.close()
        print("✅ API сервер остановлен")
    except Exception as e:
        print(f"❌ Ошибка при остановке: {e}")


app = FastAPI(title="Telegram Casino API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],  # Временно
  allow_credentials=True,
  allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
  allow_headers=["*"],
  expose_headers=["*"]
)



@app.get("/cases")
async def get_cases():
  """Получить все доступные кейсы"""
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


@app.get("/case/{case_id}")
async def get_case(case_id: int):
  """Получить информацию о конкретном кейсе"""
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


@app.post("/open_case/{case_id}")
async def open_case(case_id: int, user_id: int = Depends(get_current_user_id)):
  """Открыть кейс (требует оплаты фантиками) - БЕЗОПАСНАЯ АТОМАРНАЯ ВЕРСИЯ"""
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


@app.post("/fantics/add")
async def add_fantics(
  transaction: FanticsTransaction,
  current_user_id: int = Depends(get_current_user_id)
):
  """Добавить фантики пользователю (только для себя)"""
  return await payment_manager.add_fantics_manual(transaction, current_user_id)


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

# Убрали middleware для логирования - он создавал лишний шум

@app.get("/ton/wallets", response_model=List[TonWalletResponse])
async def get_user_ton_wallets(current_user_id: int = Depends(get_current_user_id)):
    """Получение всех TON кошельков пользователя"""
    return await payment_manager.get_user_ton_wallets(current_user_id, current_user_id)

@app.post("/ton/connect", response_model=TonWalletResponse)
async def connect_ton_wallet(
    wallet_data: TonWalletRequest,  
    current_user_id: int = Depends(get_current_user_id)
):
    return await payment_manager.connect_ton_wallet(wallet_data, current_user_id)

@app.post("/topup/stars")
async def topup_with_stars(
    request: TopUpStarsRequest,
    current_user_id: int = Depends(get_current_user_id)
):
    """Пополнение счета через Telegram Stars"""
    return await payment_manager.create_stars_payment(request, current_user_id)

@app.post("/topup/ton/create_payload")
async def create_ton_topup_payload(
    request: TopUpTonRequest,
    current_user_id: int = Depends(get_current_user_id)
):
    """Создание payload для пополнения счета через TON"""
    return await payment_manager.create_ton_payment_payload(request, current_user_id)

@app.post("/topup/ton/confirm")
async def confirm_ton_topup(
    request: TopUpTonRequest,
    current_user_id: int = Depends(get_current_user_id)
):
    """Подтверждение пополнения счета после успешной TON транзакции"""
    return await payment_manager.confirm_ton_payment(request, current_user_id)

# Оставляем старые эндпоинты для обратной совместимости
@app.post("/topup/create_payload")
async def create_topup_payload(
    request: TopUpRequest,
    current_user_id: int = Depends(get_current_user_id)
):
    """Создание payload для пополнения счета (старый эндпоинт для обратной совместимости)"""
    # Проверяем, что пользователь выбрал TON как метод оплаты
    if request.payment_method != "ton":
        raise HTTPException(status_code=400, detail="Используйте /topup/stars для оплаты звездочками")
    
    # Переадресуем на новый эндпоинт
    ton_request = TopUpTonRequest(amount=request.amount)
    return await create_ton_topup_payload(ton_request, current_user_id)

@app.post("/topup/confirm")
async def confirm_topup(
    request: TopUpRequest,
    current_user_id: int = Depends(get_current_user_id)
):
    """Подтверждение пополнения счета (старый эндпоинт для обратной совместимости)"""
    # Переадресуем на новый эндпоинт для TON
    ton_request = TopUpTonRequest(amount=request.amount)
    return await confirm_ton_topup(ton_request, current_user_id)

if __name__ == "__main__":
  print(f"🌐 Запуск сервера на http://{API_HOST}:{API_PORT}")
  print(f"🗄️ База данных: {'Neon PostgreSQL' if 'neon' in DATABASE_URL else 'PostgreSQL' if 'postgresql' in DATABASE_URL else 'SQLite'}")
  print(f"🐰 RabbitMQ: {'Включен' if rabbit_manager.is_available else 'Отключен'}")
  uvicorn.run("main:app", host=API_HOST, port=API_PORT)

