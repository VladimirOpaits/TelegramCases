from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from faststream.rabbit.fastapi import RabbitRouter
from database import DatabaseManager
from Cases import get_random_gift, get_case_info, get_all_cases_info, CaseRepository
from config import DATABASE_URL
from pydantic import BaseModel

app = FastAPI()
router = RabbitRouter("amqp://guest:guest@localhost:5672/")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db_manager = DatabaseManager(DATABASE_URL)


class FanticsTransaction(BaseModel):
    user_id: int
    amount: int


@app.on_event("startup")
async def startup_event():
    await db_manager.init_db()


@app.get("/cases")
async def get_cases():
    return get_all_cases_info()


@app.get("/case/{case_id}")
async def get_case(case_id: int):
    try:
        return get_case_info(case_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/open_case/{case_id}")
async def open_case(case_id: int, user_id: int):
    """Открыть кейс (требует оплаты фантиками)"""
    try:
        case_info = get_case_info(case_id)
        case_cost = case_info["cost"]
        
        # Проверяем баланс пользователя
        current_balance = await db_manager.get_fantics(user_id)
        if current_balance is None:
            raise HTTPException(status_code=404, detail=f"Пользователь {user_id} не найден")
        
        if current_balance < case_cost:
            raise HTTPException(
                status_code=400, 
                detail=f"Недостаточно фантиков. Требуется: {case_cost}, доступно: {current_balance}"
            )
        
        # Списываем фантики через RabbitMQ
        await router.broker.publish(
            {
                "user_id": user_id,
                "amount": case_cost,
                "action": "spend",
                "reason": f"open_case_{case_id}"
            },
            queue="transactions",
        )
        
        # Получаем приз
        gift = get_random_gift(case_id)
        
        # Добавляем выигрыш через RabbitMQ
        await router.broker.publish(
            {
                "user_id": user_id,
                "amount": gift.cost,
                "action": "add",
                "reason": f"case_win_{case_id}"
            },
            queue="transactions",
        )
        
        return {
            "gift": gift.cost,
            "case_id": case_id,
            "spent": case_cost,
            "profit": gift.cost - case_cost
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/fantics/add")
async def add_fantics(transaction: FanticsTransaction):
    """Добавить фантики пользователю"""
    if transaction.amount <= 0:
        raise HTTPException(status_code=400, detail="Сумма должна быть положительной")
    
    await router.broker.publish(
        {
            "user_id": transaction.user_id,
            "amount": transaction.amount,
            "action": "add"
        },
        queue="transactions",
    )
    return {"status": "ok", "message": f"Запрос на добавление {transaction.amount} фантиков пользователю {transaction.user_id} отправлен"}


@router.post("/fantics/spend")
async def spend_fantics(transaction: FanticsTransaction):
    """Списать фантики у пользователя"""
    if transaction.amount <= 0:
        raise HTTPException(status_code=400, detail="Сумма должна быть положительной")
    
    # Проверяем баланс перед отправкой в очередь
    current_balance = await db_manager.get_fantics(transaction.user_id)
    
    if current_balance is None:
        raise HTTPException(status_code=404, detail=f"Пользователь {transaction.user_id} не найден")
    
    if current_balance < transaction.amount:
        raise HTTPException(
            status_code=400, 
            detail=f"Недостаточно фантиков. Доступно: {current_balance}, запрошено: {transaction.amount}"
        )
    
    await router.broker.publish(
        {
            "user_id": transaction.user_id,
            "amount": transaction.amount,
            "action": "spend"
        },
        queue="transactions",
    )
    return {"status": "ok", "message": f"Запрос на списание {transaction.amount} фантиков у пользователя {transaction.user_id} отправлен"}


@app.get("/fantics/{user_id}")
async def get_user_fantics(user_id: int):
    """Получить баланс фантиков пользователя"""
    fantics = await db_manager.get_fantics(user_id)
    if fantics is None:
        raise HTTPException(status_code=404, detail=f"Пользователь {user_id} не найден")
    return {"user_id": user_id, "fantics": fantics}


app.include_router(router)