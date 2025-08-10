import logging
import json
import uvicorn

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from contextlib import asynccontextmanager

from database import DatabaseFacade
from database import CaseManager
from rabbit_manager import RabbitManager
import config
from dependencies import get_current_user, get_current_user_id
from payment_manager import PaymentManager, TonWalletRequest, TonWalletResponse, FanticsTransaction, TopUpTonRequest, TopUpStarsRequest
from withdrawal_manager import WithdrawalManager, WithdrawalRequestModel


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', force=True)
for logger in ["uvicorn.access", "uvicorn.error", "fastapi", "sqlalchemy", "aio_pika", "aiormq"]:
    logging.getLogger(logger).setLevel(logging.WARNING)


db_manager = DatabaseFacade(config.DATABASE_URL)
case_manager = db_manager.case_manager
rabbit_manager = RabbitManager(db_manager)
use_rabbitmq = rabbit_manager.initialize()
payment_manager = PaymentManager(db_manager, rabbit_manager)
withdrawal_manager = WithdrawalManager(db_manager)


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
            await rabbit_manager.setup_handlers_and_include_router(app)
        else:
            print("⚡ Прямые транзакции активны")
        
        print("✅ API сервер готов к работе")

    except Exception as e:
        print(f"❌ Критическая ошибка инициализации: {e}")
        raise  

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
    request: dict,  # Теперь принимаем payment_id, transaction_hash и sender_wallet
    current_user_id: int = Depends(get_current_user_id)
):
    """Подтверждение пополнения счета после успешной TON транзакции"""
    payment_id = request.get("payment_id")
    transaction_hash = request.get("transaction_hash")
    sender_wallet = request.get("sender_wallet")  # Новый параметр
    
    if not payment_id:
        raise HTTPException(status_code=400, detail="Требуется payment_id")
    if not transaction_hash:
        raise HTTPException(status_code=400, detail="Требуется transaction_hash")
    
    return await payment_manager.confirm_ton_payment(
        payment_id=payment_id,
        transaction_hash=transaction_hash,
        user_id=current_user_id,
        sender_wallet=sender_wallet
    )

@app.get("/payment/status/{payment_id}")
async def get_payment_status(
    payment_id: str,
    current_user_id: int = Depends(get_current_user_id)
):
    """Получение статуса платежа"""
    payment = await db_manager.get_pending_payment(payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Платеж не найден")
    
    if payment.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    return {
        "payment_id": payment.payment_id,
        "status": payment.status,
        "amount_fantics": payment.amount_fantics,
        "amount_ton": payment.amount_ton,
        "created_at": payment.created_at.isoformat(),
        "expires_at": payment.expires_at.isoformat(),
        "confirmed_at": payment.confirmed_at.isoformat() if payment.confirmed_at else None,
        "transaction_hash": payment.transaction_hash
    }


# ========== ЭНДПОИНТЫ ДЛЯ ВЫВОДА TON ==========

@app.post("/withdrawal/request")
async def create_withdrawal_request(
    request: WithdrawalRequestModel,
    current_user_id: int = Depends(get_current_user_id)
):
    """Создание запроса на вывод TON"""
    return await withdrawal_manager.create_withdrawal_request(request)

@app.get("/withdrawal/info")
async def get_withdrawal_info(current_user_id: int = Depends(get_current_user_id)):
    """Получение информации о выводе для пользователя"""
    return await withdrawal_manager.get_withdrawal_info(current_user_id)

@app.get("/withdrawal/history")
async def get_withdrawal_history(current_user_id: int = Depends(get_current_user_id)):
    """Получение истории выводов пользователя"""
    withdrawals = await db_manager.get_user_withdrawal_requests(current_user_id, limit=50)
    return [
        {
            "id": w.id,
            "amount_fantics": w.amount_fantics,
            "amount_ton": w.amount_ton,
            "fee_amount": w.fee_amount,
            "destination_address": w.destination_address,
            "status": w.status,
            "transaction_hash": w.transaction_hash,
            "error_message": w.error_message,
            "created_at": w.created_at.isoformat(),
            "processed_at": w.processed_at.isoformat() if w.processed_at else None
        }
        for w in withdrawals
    ]

@app.post("/withdrawal/process")
async def process_withdrawals(current_user_id: int = Depends(get_current_user_id)):
    """Обработка всех ожидающих выводов (только для админов)"""
    # Проверяем, является ли пользователь админом
    if current_user_id not in config.ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    return await withdrawal_manager.process_pending_withdrawals()

@app.get("/withdrawal/statistics")
async def get_withdrawal_statistics(current_user_id: int = Depends(get_current_user_id)):
    """Получение статистики выводов (только для админов)"""
    # Проверяем, является ли пользователь админом
    if current_user_id not in config.ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    return await db_manager.get_withdrawal_statistics()


if __name__ == "__main__":
  print(f"🌐 Запуск сервера на http://{config.API_HOST}:{config.API_PORT}")
  print(f"🗄️ База данных: {'Neon PostgreSQL' if 'neon' in config.DATABASE_URL else 'PostgreSQL' if 'postgresql' in config.DATABASE_URL else 'SQLite'}")
  print(f"🐰 RabbitMQ: {'Включен' if rabbit_manager.is_available else 'Отключен'}")
  uvicorn.run("main:app", host=config.API_HOST, port=config.API_PORT)

