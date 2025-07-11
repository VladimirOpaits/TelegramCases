from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from database import DatabaseManager
from Cases import get_random_gift, get_case_info, get_all_cases_info, CaseRepository
from config import DATABASE_URL, CORS_ORIGINS, API_HOST, API_PORT, RABBITMQ_URL, DEV_MODE
from pydantic import BaseModel
import uvicorn
import os
from contextlib import asynccontextmanager

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
    print(f"🔒 CORS настройки: {CORS_ORIGINS}")
    try:
        await db_manager.init_db()
        print("✅ База данных инициализирована")
        
        if use_rabbitmq and router:
            await router.broker.connect()
            print("🐰 RabbitMQ брокер подключен")
        
        if DEV_MODE:
            await db_manager.add_user(123456, "demo_user")
            await db_manager.set_fantics(123456, 50000)
            print("🎮 Демо пользователь создан с 50000 фантиков")
            
        print(f"📊 Доступно кейсов: {len(CaseRepository.get_all_cases())}")
        
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

@app.get("/health")
async def health_check():
  try:
      count = await db_manager.get_users_count()
      return {
          "status": "healthy", 
          "database": "connected", 
          "users_count": count,
          "cases_count": len(CaseRepository.get_all_cases()),
          "dev_mode": DEV_MODE,
          "rabbitmq": use_rabbitmq,
          "cors_test": "OK"
      }
  except Exception as e:
      return {"status": "error", "database": "disconnected", "error": str(e)}

@app.options("/{path:path}")
async def options_handler(path: str):
  return {"message": "CORS preflight OK"}


@app.get("/cases")
async def get_cases():
  """Получить все доступные кейсы"""
  try:
      cases = get_all_cases_info()
      print(f"📦 Отправлено {len(cases)} кейсов")
      return cases
  except Exception as e:
      print(f"❌ Ошибка получения кейсов: {e}")
      raise HTTPException(status_code=500, detail=f"Ошибка получения кейсов: {str(e)}")

@app.get("/case/{case_id}")
async def get_case(case_id: int):
  """Получить информацию о конкретном кейсе"""
  try:
      case_info = get_case_info(case_id)
      return case_info
  except ValueError as e:
      raise HTTPException(status_code=404, detail=str(e))



@app.post("/open_case/{case_id}")
async def open_case(case_id: int, user_id: int):
    """Открыть кейс (требует оплаты фантиками)"""
    try:
        case_info = get_case_info(case_id)
        case_cost = case_info["cost"]

        current_balance = await db_manager.get_fantics(user_id)
        if current_balance is None:
            await db_manager.add_user(user_id)
            current_balance = 0

        if current_balance < case_cost:
            raise HTTPException(
                status_code=400,
                detail=f"Недостаточно фантиков. Требуется: {case_cost}, доступно: {current_balance}"
            )

        gift = get_random_gift(case_id)

        await db_manager.subtract_fantics(user_id, case_cost)
        await db_manager.add_fantics(user_id, gift.cost)

        if use_rabbitmq and router:
            await router.broker.publish(
                {
                    "user_id": user_id,
                    "amount": case_cost,
                    "action": "spend",
                    "reason": f"open_case_{case_id}"
                },
                queue="transactions",
            )
            
            await router.broker.publish(
                {
                    "user_id": user_id,
                    "amount": gift.cost,
                    "action": "add",
                    "reason": f"case_win_{case_id}"
                },
                queue="transactions",
            )
            print(f"🐰 Транзакции отправлены в RabbitMQ для пользователя {user_id}")

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
async def add_fantics(transaction: FanticsTransaction):
  """Добавить фантики пользователю"""
  if transaction.amount <= 0:
      raise HTTPException(status_code=400, detail="Сумма должна быть положительной")

  user_id = transaction.user_id
  
  user = await db_manager.get_user(user_id)
  if not user:
      await db_manager.add_user(user_id)

  if use_rabbitmq and router:
      await router.broker.publish(
          {
              "user_id": user_id,
              "amount": transaction.amount,
              "action": "add",
              "reason": "manual_deposit"
          },
          queue="transactions",
      )
      message = f"Запрос на добавление {transaction.amount} фантиков отправлен в очередь"
      print(f"🐰 {message}")
  else:
      success = await db_manager.add_fantics(user_id, transaction.amount)
      message = f"Добавлено {transaction.amount} фантиков" if success else "Ошибка добавления фантиков"
      print(f"⚡ {message}")
  
  return {
      "status": "ok",
      "message": message
  }

@app.get("/fantics/{user_id}")
async def get_user_fantics(user_id: int):
  """Получить баланс фантиков пользователя"""
  fantics = await db_manager.get_fantics(user_id)
  if fantics is None:
      await db_manager.add_user(user_id)
      fantics = 0
  
  print(f"💎 Баланс пользователя {user_id}: {fantics}")
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
  print(f"🗄️ База данных: {'Neon PostgreSQL' if 'neon' in DATABASE_URL else 'PostgreSQL' if 'postgresql' in DATABASE_URL else 'SQLite'}")
  print(f"🐰 RabbitMQ: {'Включен' if use_rabbitmq else 'Отключен'}")
 
  if not DEV_MODE:
      uvicorn.run("main:app", host=API_HOST, port=API_PORT)
  else:
      uvicorn.run(app, host=API_HOST, port=API_PORT, reload=True)
