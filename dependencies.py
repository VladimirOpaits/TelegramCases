from fastapi import Depends, HTTPException, Request, Header
from typing import Optional
from auth import TelegramAuth
from config import BOT_TOKEN, DEV_MODE
import logging

logger = logging.getLogger(__name__)
telegram_auth = TelegramAuth(BOT_TOKEN)

# Импортируем DatabaseManager для создания пользователей
from database import DatabaseManager
from config import DATABASE_URL

# Создаем инстанс менеджера БД для аутентификации
auth_db_manager = DatabaseManager(DATABASE_URL)

async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_telegram_init_data: Optional[str] = Header(None)
) -> dict:
    """Получает текущего пользователя из Telegram initData и создает его при первом заходе"""
    init_data = None
    
    if authorization and authorization.startswith("Bearer "):
        init_data = authorization.replace("Bearer ", "", 1)
    elif x_telegram_init_data:
        init_data = x_telegram_init_data

    if not init_data:
        init_data = request.query_params.get("initData")
    
    if not init_data:
        raise HTTPException(
            status_code=401,
            detail="Telegram initData required. Pass it in: Authorization header (Bearer <initData>), X-Telegram-InitData header, or initData query param"
        )
    
    try:
        user_data = telegram_auth.validate_init_data(init_data)
        user_id = user_data.get('id') or user_data.get('user', {}).get('id')
        username = user_data.get('username') or user_data.get('user', {}).get('username')
        
        # СОЗДАНИЕ ПОЛЬЗОВАТЕЛЯ ПРИ ПЕРВОМ ЗАХОДЕ
        try:
            existing_user = await auth_db_manager.get_user(user_id)
            if not existing_user:
                logger.info(f"👤 Создаем нового пользователя: ID = {user_id}, username = {username}")
                await auth_db_manager.add_user(user_id, username)
            else:
                # Обновляем username если изменился
                if username and existing_user.username != username:
                    await auth_db_manager.add_user(user_id, username)  # add_user обновляет username
        except Exception as db_error:
            logger.error(f"❌ Ошибка работы с БД при аутентификации: {db_error}")
            # Не блокируем аутентификацию из-за ошибок БД
        
        logger.info(f"🔐 User authenticated: ID = {user_id}")   
        return user_data
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Telegram auth: {str(e)}")

def get_current_user_id(user_data=Depends(get_current_user)):
  return user_data['id']
