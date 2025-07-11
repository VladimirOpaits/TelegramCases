from fastapi import Depends, Header, HTTPException
from typing import Optional
from auth import TelegramAuth
from config import BOT_TOKEN


telegram_auth = TelegramAuth(BOT_TOKEN)

async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """Получает текущего пользователя из Telegram initData"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    
    if not authorization.startswith("tgWebAppData "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    
    init_data = authorization.replace("tgWebAppData ", "", 1)
    user_data = telegram_auth.validate_init_data(init_data)
    
    return user_data

async def get_current_user_id(user_data: dict = Depends(get_current_user)) -> int:
    """Получает только user_id текущего пользователя"""
    return user_data['user_id']