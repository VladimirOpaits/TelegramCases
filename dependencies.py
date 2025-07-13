from fastapi import Depends, Header, HTTPException, Request
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
    
    #разные способы передачи initData
    if authorization and authorization.startswith("tgWebAppData "):
        init_data = authorization.replace("tgWebAppData ", "", 1)
    elif x_telegram_init_data:
        init_data = x_telegram_init_data
    else:
        # Проверяем query параметры и тело запроса
        init_data = request.query_params.get("initData")
        if not init_data and request.method == "POST":
            form_data = await request.form()
            init_data = form_data.get("initData")
    
    if not init_data:
        raise HTTPException(
            status_code=401,
            detail="Telegram initData required. Pass it in Authorization header (tgWebAppData <initData>), X-Telegram-InitData header, initData query param or form data"
        )
    
    try:
        user_data = telegram_auth.validate_init_data(init_data)
        if not user_data.get('user_id'):
            raise HTTPException(status_code=401, detail="Invalid user data")
        return user_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid Telegram authentication: {str(e)}"
        )

async def get_current_user_id(user_data: dict = Depends(get_current_user)) -> int:
    """Получает только user_id текущего пользователя"""
    return user_data['user_id']
