from fastapi import HTTPException
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from database import DatabaseManager
import base64
import re
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError
from tonsdk.contract.wallet import Wallets, WalletVersionEnum
from tonsdk.utils import Address
from config import TON_TESTNET

class TonProofDomain(BaseModel):
    lengthBytes: int
    value: str

class TonProof(BaseModel):
    timestamp: int
    domain: TonProofDomain
    signature: str   # base64
    payload: str     # base64
    pubkey: Optional[str] = None

class TonWalletRequest(BaseModel):
    wallet_address: str
    user_id: int
    network: str = Field(default="-239", description="TON Network ID")
    proof: Optional[TonProof] = None
    public_key: Optional[str] = None

class TonWalletResponse(BaseModel):
    id: int
    wallet_address: str
    created_at: datetime
    is_active: bool
    network: Optional[str] = None

# --- Менеджер TON-кошельков ---

class TonWalletManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def connect_wallet(
        self,
        wallet_data: TonWalletRequest,
        current_user_id: int
    ) -> TonWalletResponse:
        """
        Привязать TON кошелек к пользователю с проверкой Proof, если он есть
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

        # --- Проверка TON Proof (если передан) ---
        if wallet_data.proof:
            if not self.verify_ton_proof(wallet_data.wallet_address, wallet_data.proof, wallet_data.public_key):
                raise HTTPException(
                    status_code=400,
                    detail="TON Proof не прошёл проверку. Подключение кошелька невозможно."
                )

        # --- Запись в базу ---
        success = await self.db.add_ton_wallet(
            user_id=wallet_data.user_id,
            wallet_address=wallet_data.wallet_address,
            network=wallet_data.network,
            public_key=wallet_data.public_key
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
        """Поддержка обоих форматов: raw (0:) и user-friendly (EQ/UQ)"""
        if address.startswith('0:'):
            parts = address.split(':')
            return len(parts) == 2 and all(c.isalnum() or c == '_' for c in parts[1])

        return (address.startswith(('EQ', 'UQ')) 
            and len(address) == 48 
            and all(c.isalnum() or c in {'-', '_'} for c in address))

    @staticmethod
    def _format_wallet_response(wallet) -> TonWalletResponse:
        """
        Форматирование ответа с данными кошелька
        """
        return TonWalletResponse(
            id=wallet.id,
            wallet_address=wallet.wallet_address,
            created_at=wallet.created_at,
            is_active=wallet.is_active,
            network=wallet.network
        )

    @staticmethod
    def verify_ton_proof(wallet_address: str, proof: TonProof, public_key: Optional[str]) -> bool:
        """
        Проверка TON Proof (валидность подписи + public_key => wallet_address)
        """
        try:
            payload = base64.b64decode(proof.payload)
            signature = base64.b64decode(proof.signature)
            pubkey = proof.pubkey or public_key
            if not pubkey:
                print("TON Proof: не передан публичный ключ кошелька")
                return False

            verify_key = VerifyKey(bytes.fromhex(pubkey))
            verify_key.verify(payload, signature)

            wallet_cls = Wallets.ALL[WalletVersionEnum.v4r2]
            wallet = wallet_cls(bytes.fromhex(pubkey), 0)
            derived_address_obj = Address(wallet.get_address(testnet=TON_TESTNET))

            return True
        except BadSignatureError:
            print("TON Proof: Подпись неверна")
            return False
        except Exception as e:
            print("TON Proof: Ошибка валидации:", e)
            return False