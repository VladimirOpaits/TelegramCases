import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from faststream.rabbit import RabbitBroker
from database import DatabaseManager
from config import BOT_TOKEN, DATABASE_URL, WEB_APP_URL

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
broker = RabbitBroker("amqp://guest:guest@localhost:5672/")
db_manager = DatabaseManager(DATABASE_URL)

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    """Обработчик команды /start"""
    if message.from_user:
        user_id = message.from_user.id
        username = message.from_user.username
        
        success = await db_manager.add_user(user_id, username)
        if success:
            logger.info(f"Пользователь {user_id} ({username}) зарегистрирован")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎰 Открыть Casino App",
            web_app=WebAppInfo(url=f"{WEB_APP_URL}")
        )],
        [InlineKeyboardButton(
            text="📋 Пользовательское соглашение",
            web_app=WebAppInfo(url=f"{WEB_APP_URL}?page=terms")
        )]
    ])
    
    await message.answer(
        "🎰 Добро пожаловать в Casino App!\n\n"
        "Нажмите кнопку ниже, чтобы начать играть:",
        reply_markup=keyboard
    )

@broker.subscriber("transactions")
async def handle_transaction(data):
    """Обработчик транзакций из очереди"""
    try:
        logger.info(f"Получена транзакция из RabbitMQ: {data}")
        
        if isinstance(data, dict):
            user_id = data.get('user_id')
            amount = data.get('amount')
            action = data.get('action', 'add')
            
            if not user_id or amount is None:
                logger.error(f"Неверный формат данных: {data}")
                return
            
            if action == 'add':
                new_balance = await db_manager.add_fantics(user_id, amount)
                if new_balance is not None:
                    message_text = f"✅ Пользователю {user_id} добавлено {amount} фантиков.\nНовый баланс: {new_balance}"
                else:
                    message_text = f"❌ Ошибка добавления фантиков пользователю {user_id}"
            
            elif action == 'spend':
                new_balance = await db_manager.spend_fantics(user_id, amount)
                if new_balance is not None:
                    message_text = f"💸 У пользователя {user_id} списано {amount} фантиков.\nНовый баланс: {new_balance}"
                else:
                    message_text = f"❌ Ошибка списания фантиков у пользователя {user_id}"
            
            else:
                message_text = f"❌ Неизвестное действие: {action}"
            
            await bot.send_message(
                chat_id=1943755838,
                text=message_text
            )
            
        else:
            logger.error(f"Неверный формат данных. Ожидается dict, получено: {type(data)}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки транзакции: {e}", exc_info=True)

async def run_services():
    """Запуск всех сервисов"""
    async with broker:
        logger.info("✅ RabbitMQ брокер активен")
        
        await broker.start()
        
        await dp.start_polling(bot)

async def main():
    """Главная функция"""
    logger.info("Запуск Casino Bot")
    
    await db_manager.init_db()
    logger.info(f"Web App URL: {WEB_APP_URL}")
    
    try:
        await run_services()
    finally:
        await bot.session.close()
        await db_manager.close()
        logger.info("Работа завершена")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Программа остановлена пользователем")