from fastapi import HTTPException, Depends
from datetime import datetime
from typing import List
from pydantic import BaseModel
from database import DatabaseManager
from dependencies import get_current_user_id

class TonWalletRequest(BaseModel):
    wallet_address: str
    user_id: int

class TonWalletResponse(BaseModel):
    id: int
    wallet_address: str
    created_at: datetime
    is_active: bool

class TonWalletManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def connect_wallet(
        self,
        wallet_data: TonWalletRequest,
        current_user_id: int
    ) -> TonWalletResponse:
        """
        Привязать TON кошелек к пользователю
        """
        if wallet_data.user_id != current_user_id:
            raise HTTPException(
                status_code=403,
                detail="Вы можете привязывать кошельки только к своему аккаунту"
            )

        if not self.validate_ton_address(wallet_data.wallet_address):
            raise HTTPException(
                status_code=400,
                detail="Неверный формат TON кошелька"
            )

        success = await self.db.add_ton_wallet(
            user_id=wallet_data.user_id,
            wallet_address=wallet_data.wallet_address
        )

        if not success:
            raise HTTPException(
                status_code=400,
                detail="Не удалось привязать кошелек"
            )

        wallet = await self.db.get_ton_wallet_by_address(wallet_data.wallet_address)
        return self._format_wallet_response(wallet)

    async def get_user_wallets(
        self,
        user_id: int,
        current_user_id: int
    ) -> List[TonWalletResponse]:
        """
        Получить все TON кошельки пользователя
        """
        if user_id != current_user_id:
            raise HTTPException(
                status_code=403,
                detail="Вы можете просматривать только свои кошельки"
            )

        wallets = await self.db.get_user_ton_wallets(user_id)
        return [self._format_wallet_response(w) for w in wallets]

    async def disconnect_wallet(
        self,
        wallet_address: str,
        current_user_id: int
    ) -> dict:
        """
        Отвязать TON кошелек от пользователя
        """
        wallet = await self.db.get_ton_wallet_by_address(wallet_address)
        if not wallet:
            raise HTTPException(status_code=404, detail="Кошелек не найден")

        if wallet.user_id != current_user_id:
            raise HTTPException(
                status_code=403,
                detail="Вы можете отвязывать только свои кошельки"
            )

        success = await self.db.deactivate_ton_wallet(wallet_address)
        if not success:
            raise HTTPException(
                status_code=400,
                detail="Не удалось отвязать кошелек"
            )

        return {"status": "success", "message": "Кошелек успешно отвязан"}

    @staticmethod
    def validate_ton_address(address: str) -> bool:
        """Базовая валидация формата TON адреса"""
        return (address.startswith(('EQ', 'UQ')) and 
                len(address) == 48 and
                all(c.isalnum() or c == '_' for c in address))

    @staticmethod
    def _format_wallet_response(wallet) -> TonWalletResponse:
        """Форматирование ответа с данными кошелька"""
        return TonWalletResponse(
            id=wallet.id,
            wallet_address=wallet.wallet_address,
            created_at=wallet.created_at,
            is_active=wallet.is_active
        )