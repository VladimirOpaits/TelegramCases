from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from database import DatabaseManager
from Cases import CaseManager
from config import DATABASE_URL, CORS_ORIGINS, API_HOST, API_PORT, RABBITMQ_URL, DEV_MODE
from pydantic import BaseModel
import uvicorn
import os
from contextlib import asynccontextmanager
from dependencies import get_current_user, get_current_user_id

try:
  from faststream.rabbit.fastapi import RabbitRouter

  RABBITMQ_AVAILABLE = True
except ImportError:
  RABBITMQ_AVAILABLE = False
  print("⚠️ FastStream не установлен, RabbitMQ отключен")

use_rabbitmq = False
router = None
broker = None

if RABBITMQ_AVAILABLE and RABBITMQ_URL and not DEV_MODE:
  print("🐰 Подключение к RabbitMQ:", RABBITMQ_URL.split('@')[1] if '@' in RABBITMQ_URL else RABBITMQ_URL)
  try:
    router = RabbitRouter(RABBITMQ_URL)
    use_rabbitmq = True
    print("✅ RabbitMQ подключен")
  except Exception as e:
    print(f"❌ Ошибка подключения к RabbitMQ: {e}")
    use_rabbitmq = False
else:
  print("📝 RabbitMQ отключен (режим разработки или недоступен)")


@asynccontextmanager
async def lifespan(app: FastAPI):
  print("🚀 Запуск API сервера...")
  try:
    await db_manager.init_db()
    await case_manager.initialize()
    print("✅ База данных инициализирована")

    if use_rabbitmq and router:
      await router.broker.connect()
      print("🐰 RabbitMQ брокер подключен")

    if DEV_MODE:
      await db_manager.add_user(123456, "demo_user")
      await db_manager.set_fantics(123456, 50000)
      print("🎮 Демо пользователь создан с 50000 фантиков")

    if use_rabbitmq:
      print("🐰 RabbitMQ готов к работе")
    else:
      print("⚡ Прямые транзакции активны")

  except Exception as e:
    print(f"❌ Ошибка инициализации: {e}")

  yield

  if use_rabbitmq and router:
    await router.broker.close()
    print("🐰 RabbitMQ брокер отключен")
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

try:
  app.mount("/static", StaticFiles(directory="static"), name="static")
  print("📁 Статические файлы подключены")
except Exception as e:
  print(f"⚠️ Статические файлы не найдены: {e}")

db_manager = DatabaseManager(DATABASE_URL)
case_manager = CaseManager(db_manager)


class FanticsTransaction(BaseModel):
  user_id: int
  amount: int


@app.get("/")
async def root():
  return {
    "message": "Telegram Casino API",
    "status": "running",
    "dev_mode": DEV_MODE,
    "database": "PostgreSQL" if "postgresql" in DATABASE_URL else "SQLite",
    "rabbitmq": use_rabbitmq,
    "environment": "production" if not DEV_MODE else "development",
    "cors_origins": CORS_ORIGINS
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
  """Открыть кейс (требует оплаты фантиками)"""
  try:
    case = await case_manager.repository.get_case(case_id)
    if not case:
      raise HTTPException(status_code=404, detail="Нема такого кейсика")
    case_cost = case.cost

    current_balance = await db_manager.get_fantics(user_id) or 0

    if current_balance < case_cost:
      raise HTTPException(
        status_code=400,
        detail=f"Недостаточно фантиков. Требуется: {case_cost}, доступно: {current_balance}"
      )

    gift = case.get_random_present()

    # --- ИЗМЕНЕННАЯ ЛОГИКА ЗДЕСЬ ---
    if use_rabbitmq and router:
      # Если RabbitMQ используется, отправляем транзакции в очередь
      await router.broker.publish(
        {
          "user_id": user_id,
          "amount": case_cost,
          "action": "spend",
          "reason": f"open_case_cost_{case_id}" # Более конкретная причина
        },
        queue="transactions",
      )

      await router.broker.publish(
        {
          "user_id": user_id,
          "amount": gift.cost,
          "action": "add",
          "reason": f"case_win_gift_{case_id}" # Более конкретная причина
        },
        queue="transactions",
      )
      print(f"🐰 Транзакции отправлены в RabbitMQ для пользователя {user_id}")
    else:
      # Если RabbitMQ НЕ используется, обновляем базу данных напрямую
      await db_manager.subtract_fantics(user_id, case_cost)
      await db_manager.add_fantics(user_id, gift.cost)
      print(f"⚡ Прямые транзакции выполнены для пользователя {user_id}")

    print(f"🎰 Пользователь {user_id} открыл кейс {case_id}: потратил {case_cost}, выиграл {gift.cost}")

    return {
      "gift": gift.cost,
      "case_id": case_id,
      "spent": case_cost,
      "profit": gift.cost - case_cost
    }
  except ValueError as e:
    raise HTTPException(status_code=404, detail=str(e))
  except HTTPException:
    raise
  except Exception as e:
    print(f"❌ Ошибка открытия кейса: {e}")
    raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")


@app.post("/fantics/add")
async def add_fantics(
  transaction: FanticsTransaction,
  current_user_id: int = Depends(get_current_user_id)
):
  """Добавить фантики пользователю (только для себя)"""
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

  user = await db_manager.get_user(transaction.user_id)
  if not user:
    await db_manager.add_user(transaction.user_id)

  if use_rabbitmq and router:
    await router.broker.publish(
      {
        "user_id": transaction.user_id,
        "amount": transaction.amount,
        "action": "add",
        "reason": "manual_deposit",
        "initiator": current_user_id
      },
      queue="transactions",
    )
    message = f"Запрос на добавление {transaction.amount} фантиков отправлен в очередь"
    print(f"🐰 {message}")
  else:
    success = await db_manager.add_fantics(transaction.user_id, transaction.amount)
    message = f"Добавлено {transaction.amount} фантиков" if success else "Ошибка добавления фантиков"
    print(f"⚡ {message}")

  return {
    "status": "ok",
    "message": message,
    "user_id": transaction.user_id,
    "amount": transaction.amount
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
    await db_manager.add_user(user_id)
    fantics = 0

  print(f"У {user_id} {fantics} ебанных фантиков")
  return {"user_id": user_id, "fantics": fantics}


if use_rabbitmq and router:
  @router.subscriber("transactions")
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


  app.include_router(router)

if __name__ == "__main__":
  print(f"🌐 Запуск сервера на http://{API_HOST}:{API_PORT}")
  print(f"🔧 Режим: {'Продакшн' if not DEV_MODE else 'Разработка'}")
  print(
    f"🗄️ База данных: {'Neon PostgreSQL' if 'neon' in DATABASE_URL else 'PostgreSQL' if 'postgresql' in DATABASE_URL else 'SQLite'}")
  print(f"🐰 RabbitMQ: {'Включен' if use_rabbitmq else 'Отключен'}")

  if not DEV_MODE:
    uvicorn.run("main:app", host=API_HOST, port=API_PORT)
  else:
    uvicorn.run(app, host=API_HOST, port=API_PORT, reload=True)
