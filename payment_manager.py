
"""
Менеджер платежей и пополнений

Этот модуль объединяет всю логику работы с платежами:
- Модели для всех типов платежей и пополнений
- Интеграция с TON кошельками и Telegram Stars
- Логика создания и валидации платежей
- Проверка и подтверждение платежей
- Подготовка для проверки платежей в блокчейне
"""

from fastapi import HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from database import DatabaseManager
from rabbit_manager import RabbitManager
from config import TON_WALLET_ADDRESS, TON_TESTNET
import asyncio
import base64
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError
from tonsdk.contract.wallet import Wallets, WalletVersionEnum
from tonsdk.utils import Address


# =============================================================================
# МОДЕЛИ TON КОШЕЛЬКОВ И ПРОВЕРКИ
# =============================================================================

class TonProofDomain(BaseModel):
    """Домен для TON Proof"""
    lengthBytes: int
    value: str


class TonProof(BaseModel):
    """TON Proof для верификации кошелька"""
    timestamp: int
    domain: TonProofDomain
    signature: str = Field(..., description="base64 encoded signature")
    payload: str = Field(..., description="base64 encoded payload")
    pubkey: Optional[str] = None


class TonWalletRequest(BaseModel):
    """Запрос на подключение TON кошелька"""
    wallet_address: str
    user_id: int
    network: str = Field(default="-239", description="TON Network ID")
    proof: Optional[TonProof] = None
    public_key: Optional[str] = None


class TonWalletResponse(BaseModel):
    """Ответ с данными TON кошелька"""
    id: int
    wallet_address: str
    created_at: datetime
    is_active: bool
    network: Optional[str] = None


# =============================================================================
# МОДЕЛИ ПЛАТЕЖЕЙ И ПОПОЛНЕНИЙ
# =============================================================================

class FanticsTransaction(BaseModel):
    """Транзакция фантиков"""
    user_id: int
    amount: int


class TopUpTonRequest(BaseModel):
    """Запрос на пополнение через TON"""
    amount: int = Field(..., description="Количество фантиков для пополнения")


class TopUpStarsRequest(BaseModel):
    """Запрос на пополнение через Telegram Stars"""
    amount: int = Field(..., description="Количество фантиков для пополнения")


class TopUpRequest(BaseModel):
    """Общий запрос на пополнение"""
    amount: int = Field(..., description="Количество фантиков для пополнения")
    payment_method: str = Field(..., description="Метод оплаты: 'ton' или 'telegram_stars'")


class TopUpPayload(BaseModel):
    """Payload для TON транзакции"""
    amount: float = Field(..., description="Количество TON для отправки")
    destination: str = Field(..., description="Адрес кошелька для получения")
    payload: str = Field(..., description="Текстовый комментарий для транзакции")
    comment: str = Field(..., description="Комментарий к транзакции")


class PaymentStatus(BaseModel):
    """Статус платежа"""
    payment_id: str
    status: str  # pending, confirmed, failed, expired
    payment_method: str
    amount: int
    user_id: int
    created_at: datetime
    confirmed_at: Optional[datetime] = None
    transaction_hash: Optional[str] = None  # Хеш транзакции в блокчейне
    error_message: Optional[str] = None


class PaymentVerificationResult(BaseModel):
    """Результат проверки платежа"""
    is_valid: bool
    transaction_hash: Optional[str] = None
    amount_sent: Optional[float] = None
    sender_address: Optional[str] = None
    message: str
    block_number: Optional[int] = None


# =============================================================================
# МЕНЕДЖЕР ПЛАТЕЖЕЙ
# =============================================================================

class PaymentManager:
    """
    Менеджер платежей и пополнений
    
    Централизует всю логику работы с платежами:
    - Создание запросов на пополнение
    - Валидация платежных данных
    - Интеграция с различными методами оплаты
    - Проверка статуса платежей (планируется)
    """
    
    def __init__(self, db_manager: DatabaseManager, rabbit_manager: Optional[RabbitManager] = None):
        self.db = db_manager
        self.rabbit = rabbit_manager
        
        # Конфигурация лимитов
        self.max_topup_amount = 1000000  # Максимальная сумма пополнения
        self.min_topup_amount = 1        # Минимальная сумма пополнения
        self.ton_to_fantics_rate = 1000  # 1 TON = 1000 фантиков
        
        # TODO: В будущем добавить хранилище для отслеживания платежей
        self._pending_payments: Dict[str, PaymentStatus] = {}

    # =========================================================================
    # ВАЛИДАЦИЯ ПЛАТЕЖЕЙ
    # =========================================================================

    def validate_topup_amount(self, amount: int) -> None:
        """Валидация суммы пополнения"""
        if amount <= 0:
            raise HTTPException(
                status_code=400, 
                detail="Сумма пополнения должна быть больше 0"
            )
        
        if amount > self.max_topup_amount:
            raise HTTPException(
                status_code=400, 
                detail=f"Сумма пополнения слишком большая (максимум {self.max_topup_amount})"
            )

    def validate_fantics_amount(self, amount: int) -> None:
        """Валидация суммы фантиков для добавления"""
        if amount <= 0:
            raise HTTPException(
                status_code=400,
                detail="Сумма должна быть положительной"
            )
        
        if amount > 100000:  # Лимит для ручного добавления
            raise HTTPException(
                status_code=400,
                detail="Слишком большая сумма для ручного добавления"
            )

    # =========================================================================
    # ПОПОЛНЕНИЕ ЧЕРЕЗ TELEGRAM STARS
    # =========================================================================

    async def create_stars_payment(
        self, 
        request: TopUpStarsRequest, 
        user_id: int
    ) -> Dict[str, Any]:
        """
        Создание запроса на пополнение через Telegram Stars
        """
        self.validate_topup_amount(request.amount)
        
        if not self.rabbit or not self.rabbit.is_ready:
            raise HTTPException(
                status_code=503, 
                detail="Сервис пополнения через звездочки временно недоступен"
            )
        
        success = await self.rabbit.send_stars_payment_request(user_id, request.amount)
        
        if not success:
            raise HTTPException(
                status_code=500, 
                detail="Ошибка отправки запроса на оплату звездочками"
            )
        
        return {
            "success": True,
            "message": f"Запрос на пополнение {request.amount} фантиков через Telegram Stars отправлен",
            "amount": request.amount,
            "payment_method": "telegram_stars",
            "status": "pending"
        }

    # =========================================================================
    # ПОПОЛНЕНИЕ ЧЕРЕЗ TON
    # =========================================================================

    async def create_ton_payment_payload(
        self, 
        request: TopUpTonRequest, 
        user_id: int
    ) -> TopUpPayload:
        """
        Создание payload для пополнения через TON
        """
        self.validate_topup_amount(request.amount)
        
        # Конвертируем фантики в TON
        ton_amount = request.amount / self.ton_to_fantics_rate
        
        # Создаем комментарий для транзакции
        comment = f"Fantics {request.amount} ID:{user_id}"
        
        # Проверяем длину комментария (TON рекомендует до 127 символов)
        if len(comment) > 127:
            comment = f"Fantics {request.amount}"
        
        return TopUpPayload(
            amount=ton_amount,
            destination=TON_WALLET_ADDRESS,
            payload=comment,
            comment=comment
        )

    async def confirm_ton_payment(
        self, 
        request: TopUpTonRequest, 
        user_id: int,
        transaction_hash: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Подтверждение пополнения через TON
        
        ВНИМАНИЕ: В будущем здесь должна быть проверка транзакции в блокчейне!
        Пока что используем прямое добавление фантиков.
        """
        self.validate_topup_amount(request.amount)
        
        # TODO: Добавить проверку транзакции в блокчейне
        # result = await self.verify_ton_transaction(transaction_hash, user_id, request.amount)
        # if not result.is_valid:
        #     raise HTTPException(status_code=400, detail=f"Транзакция не подтверждена: {result.message}")
        
        success, message, new_balance = await self.db.atomic_add_fantics(user_id, request.amount)
        
        if not success:
            raise HTTPException(status_code=400, detail=message)
        
        print(f"✅ TON пополнение: пользователь {user_id} получил {request.amount} фантиков, баланс: {new_balance}")
        
        return {
            "success": True,
            "message": message,
            "new_balance": new_balance,
            "added_amount": request.amount,
            "payment_method": "ton",
            "transaction_hash": transaction_hash
        }

    # =========================================================================
    # РУЧНОЕ ДОБАВЛЕНИЕ ФАНТИКОВ
    # =========================================================================

    async def add_fantics_manual(
        self, 
        transaction: FanticsTransaction, 
        current_user_id: int
    ) -> Dict[str, Any]:
        """
        Ручное добавление фантиков пользователю
        """
        if transaction.user_id != current_user_id:
            raise HTTPException(
                status_code=403,
                detail="Вы можете добавлять фантики только себе"
            )
        
        self.validate_fantics_amount(transaction.amount)
        
        if self.rabbit and self.rabbit.is_ready:
            # Отправляем через RabbitMQ
            await self.rabbit.send_fantics_transaction(
                user_id=transaction.user_id,
                amount=transaction.amount,
                action="add",
                reason="manual_deposit",
                initiator=current_user_id
            )
            
            message = f"Запрос на добавление {transaction.amount} фантиков отправлен в очередь"
            print(f"🐰 {message}")
            
            return {
                "status": "ok",
                "message": message,
                "user_id": transaction.user_id,
                "amount": transaction.amount
            }
        else:
            # Прямое добавление в базу
            success, message, new_balance = await self.db.atomic_add_fantics(
                transaction.user_id, 
                transaction.amount
            )
            
            if not success:
                raise HTTPException(status_code=400, detail=message)
            
            print(f"⚡ {message}")
            return {
                "status": "ok",
                "message": message,
                "user_id": transaction.user_id,
                "amount": transaction.amount,
                "new_balance": new_balance
            }

    # =========================================================================
    # ПРОВЕРКА ПЛАТЕЖЕЙ (ЗАГОТОВКА ДЛЯ БУДУЩЕГО РАЗВИТИЯ)
    # =========================================================================

    async def verify_ton_transaction(
        self, 
        transaction_hash: str, 
        expected_user_id: int, 
        expected_amount: int
    ) -> PaymentVerificationResult:
        """
        Проверка TON транзакции в блокчейне
        
        TODO: Реализовать проверку транзакции через TON API
        - Проверить что транзакция существует и подтверждена
        - Проверить сумму и адрес получателя
        - Проверить комментарий на соответствие пользователю
        """
        # ЗАГЛУШКА - в будущем здесь будет реальная проверка
        await asyncio.sleep(0.1)  # Имитация запроса к API
        
        return PaymentVerificationResult(
            is_valid=True,  # TODO: реальная проверка
            transaction_hash=transaction_hash,
            amount_sent=expected_amount / self.ton_to_fantics_rate,
            sender_address="unknown",  # TODO: получить из блокчейна
            message="Проверка транзакции пока не реализована",
            block_number=None
        )

    async def verify_stars_payment(
        self, 
        payment_id: str, 
        expected_user_id: int, 
        expected_amount: int
    ) -> PaymentVerificationResult:
        """
        Проверка платежа через Telegram Stars
        
        TODO: Реализовать проверку через Telegram Bot API
        """
        # ЗАГЛУШКА - в будущем здесь будет реальная проверка
        await asyncio.sleep(0.1)  # Имитация запроса к API
        
        return PaymentVerificationResult(
            is_valid=True,  # TODO: реальная проверка
            transaction_hash=payment_id,
            amount_sent=expected_amount,
            sender_address=f"telegram_user_{expected_user_id}",
            message="Проверка Stars платежа пока не реализована"
        )

    async def get_payment_status(self, payment_id: str) -> Optional[PaymentStatus]:
        """
        Получение статуса платежа по ID
        
        TODO: Реализовать хранение и отслеживание статусов платежей
        """
        return self._pending_payments.get(payment_id)

    async def list_user_payments(
        self, 
        user_id: int, 
        limit: int = 50
    ) -> List[PaymentStatus]:
        """
        Получение истории платежей пользователя
        
        TODO: Реализовать хранение истории платежей в базе данных
        """
        # ЗАГЛУШКА - в будущем здесь будет запрос к базе данных
        user_payments = [
            payment for payment in self._pending_payments.values() 
            if payment.user_id == user_id
        ]
        return user_payments[:limit]

    # =========================================================================
    # УПРАВЛЕНИЕ TON КОШЕЛЬКАМИ
    # =========================================================================

    async def connect_ton_wallet(
        self,
        wallet_data: TonWalletRequest,
        current_user_id: int
    ) -> TonWalletResponse:
        """
        Привязать TON кошелек к пользователю с проверкой Proof
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

        # Проверяем, не существует ли уже этот кошелек
        existing_wallet = await self.db.get_ton_wallet_by_address(wallet_data.wallet_address)
        if existing_wallet:
            if existing_wallet.user_id == current_user_id:
                return self._format_wallet_response(existing_wallet)
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Этот кошелек уже подключен к другому пользователю"
                )

        # Проверка TON Proof (если передан)
        if wallet_data.proof:
            if not self.verify_ton_proof(wallet_data.wallet_address, wallet_data.proof, wallet_data.public_key):
                raise HTTPException(
                    status_code=400,
                    detail="TON Proof не прошёл проверку. Подключение кошелька невозможно."
                )

        # Запись в базу
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

    async def get_user_ton_wallets(
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

    async def disconnect_ton_wallet(
        self,
        wallet_address: str,
        current_user_id: int
    ) -> Dict[str, str]:
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

    # =========================================================================
    # ВАЛИДАЦИЯ TON
    # =========================================================================

    @staticmethod
    def validate_ton_address(address: str) -> bool:
        """Поддержка обоих форматов TON адресов: raw (0:) и user-friendly (EQ/UQ)"""
        if address.startswith('0:'):
            parts = address.split(':')
            return len(parts) == 2 and all(c.isalnum() or c == '_' for c in parts[1])

        return (address.startswith(('EQ', 'UQ')) 
            and len(address) == 48 
            and all(c.isalnum() or c in {'-', '_'} for c in address))

    @staticmethod
    def verify_ton_proof(wallet_address: str, proof: TonProof, public_key: Optional[str]) -> bool:
        """
        Проверка TON Proof (валидность подписи + public_key => wallet_address)
        """
        try:
            if not proof:
                print("TON Proof: proof не передан")
                return False
            
            # Проверяем обязательные поля proof
            if not proof.payload:
                print("TON Proof: payload отсутствует")
                return False
                
            if not proof.signature:
                print("TON Proof: signature отсутствует")
                return False
                
            if not proof.domain:
                print("TON Proof: domain отсутствует")
                return False
            
            # Получаем публичный ключ
            pubkey = proof.pubkey or public_key
            if not pubkey:
                print("TON Proof: не передан публичный ключ кошелька")
                return False

            # Декодируем payload и signature
            try:
                payload = base64.b64decode(proof.payload)
                signature = base64.b64decode(proof.signature)
            except Exception as e:
                print(f"TON Proof: Ошибка декодирования base64: {e}")
                return False

            # Проверяем подпись
            try:
                verify_key = VerifyKey(bytes.fromhex(pubkey))
                verify_key.verify(payload, signature)
            except BadSignatureError:
                print("TON Proof: Подпись неверна")
                return False
            except Exception as e:
                print(f"TON Proof: Ошибка проверки подписи: {e}")
                return False

            # Проверяем соответствие адреса публичному ключу
            try:
                wallet_cls = Wallets.ALL[WalletVersionEnum.v4r2]
                wallet = wallet_cls(bytes.fromhex(pubkey), 0)
                derived_address_obj = Address(wallet.get_address(testnet=TON_TESTNET))
                
                # TODO: добавить более строгую проверку соответствия адреса
                return True
            except Exception as e:
                print(f"TON Proof: Ошибка проверки адреса кошелька: {e}")
                return False

        except Exception as e:
            print(f"TON Proof: Неожиданная ошибка валидации: {e}")
            return False

    @staticmethod
    def _format_wallet_response(wallet) -> TonWalletResponse:
        """Форматирование ответа с данными кошелька"""
        return TonWalletResponse(
            id=wallet.id,
            wallet_address=wallet.wallet_address,
            created_at=wallet.created_at,
            is_active=wallet.is_active,
            network=wallet.network
        )

    # =========================================================================
    # УТИЛИТЫ
    # =========================================================================

    def convert_fantics_to_ton(self, fantics_amount: int) -> float:
        """Конвертация фантиков в TON"""
        return fantics_amount / self.ton_to_fantics_rate

    def convert_ton_to_fantics(self, ton_amount: float) -> int:
        """Конвертация TON в фантики"""
        return int(ton_amount * self.ton_to_fantics_rate)

    def format_payment_comment(self, user_id: int, amount: int) -> str:
        """Формирование комментария для платежа"""
        comment = f"Fantics {amount} ID:{user_id}"
        if len(comment) > 127:  # TON лимит
            comment = f"Fantics {amount}"
        return comment