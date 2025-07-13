from fastapi import Depends, HTTPException, Request, Header
from typing import Optional
from auth import TelegramAuth
from config import BOT_TOKEN

telegram_auth = TelegramAuth(BOT_TOKEN)

async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_telegram_init_data: Optional[str] = Header(None)
) -> dict:
    """Получает текущего пользователя из Telegram initData"""
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
        return telegram_auth.validate_init_data(init_data)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Telegram auth: {str(e)}")

async def get_current_user_id(user_data: dict = Depends(get_current_user)) -> int:
    """Получает только user_id текущего пользователя"""
    return user_data['user_id']
