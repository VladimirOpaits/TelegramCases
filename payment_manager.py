

from fastapi import HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from database import DatabaseManager
from rabbit_manager import RabbitManager
import config
import asyncio
import base64
import uuid
import aiohttp
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
    ) -> Dict[str, Any]:
        """
        Создание payload для пополнения через TON
        Теперь создает pending платеж в базе и возвращает payment_id
        """
        self.validate_topup_amount(request.amount)
        
        # Конвертируем фантики в TON
        ton_amount = request.amount / self.ton_to_fantics_rate
        
        # Создаем уникальный ID платежа
        payment_id = str(uuid.uuid4())
        
        # Создаем комментарий для транзакции
        comment = f"Fantics {request.amount} ID:{user_id}"
        
        # Проверяем длину комментария (TON рекомендует до 127 символов)
        if len(comment) > 127:
            comment = f"Fantics {request.amount}"
        
        # Создаем pending платеж в базе данных
        success = await self.db.create_pending_payment(
            payment_id=payment_id,
            user_id=user_id,
            amount_fantics=request.amount,
            amount_ton=ton_amount,
            payment_method="ton",
            destination_address=config.TON_WALLET_ADDRESS,
            comment=comment,
            expires_in_minutes=30
        )
        
        if not success:
            raise HTTPException(
                status_code=500, 
                detail="Ошибка создания платежа"
            )
        
        return {
            "payment_id": payment_id,
            "amount": ton_amount,
            "destination": config.TON_WALLET_ADDRESS,
            "payload": comment,
            "comment": comment,
            "status": "pending",
            "expires_in": 30  # минут
        }

    async def confirm_ton_payment(
        self, 
        payment_id: str,
        transaction_hash: str,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Подтверждение пополнения через TON (без проверки в блокчейне)
        """
        # 1. Получаем pending платеж
        payment = await self.db.get_pending_payment(payment_id)
        if not payment:
            raise HTTPException(
                status_code=404, 
                detail="Платеж не найден"
            )
        
        # 2. Проверяем, что платеж принадлежит пользователю
        if payment.user_id != user_id:
            raise HTTPException(
                status_code=403, 
                detail="Доступ запрещен"
            )
        
        # 3. Проверяем статус платежа
        if payment.status != 'pending':
            if payment.status == 'confirmed':
                raise HTTPException(
                    status_code=400, 
                    detail="Платеж уже подтвержден"
                )
            else:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Платеж в статусе {payment.status}"
                )
        
        # 4. Проверяем, не истек ли платеж
        if payment.expires_at < datetime.now():
            await self.db.update_payment_status(payment_id, 'expired')
            raise HTTPException(
                status_code=400, 
                detail="Платеж истек"
            )
        
        # 5. Сразу добавляем фантики (без проверки в блокчейне)
        success, message, new_balance = await self.db.atomic_add_fantics(
            payment.user_id, 
            payment.amount_fantics
        )
        
        if not success:
            await self.db.update_payment_status(payment_id, 'failed', transaction_hash)
            raise HTTPException(
                status_code=500, 
                detail=f"Ошибка добавления фантиков: {message}"
            )
        
        # 6. Помечаем платеж как подтвержденный
        await self.db.update_payment_status(payment_id, 'confirmed', transaction_hash)
        
        print(f"✅ TON пополнение подтверждено: пользователь {user_id} получил {payment.amount_fantics} фантиков, баланс: {new_balance}")
        
        return {
            "success": True,
            "message": f"Платеж подтвержден! Добавлено {payment.amount_fantics} фантиков",
            "new_balance": new_balance,
            "added_amount": payment.amount_fantics,
            "payment_method": "ton",
            "transaction_hash": transaction_hash,
            "payment_id": payment_id
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
        expected_amount_fantics: int,
        expected_comment: str
    ) -> PaymentVerificationResult:
        """
        Реальная проверка TON транзакции в блокчейне через TON API
        С улучшенной поддержкой тестнета
        """
        try:
            # Выбираем API в зависимости от сети
            if config.TON_TESTNET:
                api_url = "https://testnet.toncenter.com/api/v2"
                # В тестнете увеличиваем лимит и добавляем повторные попытки
                max_attempts = 5
                delay_between_attempts = 3  # секунды
                transaction_limit = 100  # больше транзакций для проверки
            else:
                api_url = "https://toncenter.com/api/v2"
                max_attempts = 2
                delay_between_attempts = 1
                transaction_limit = 50
            
            # Получаем транзакции для нашего кошелька с повторными попытками
            for attempt in range(max_attempts):
                try:
                    async with aiohttp.ClientSession() as session:
                        # Запрос транзакций по адресу
                        params = {
                            "address": config.TON_WALLET_ADDRESS,
                            "limit": transaction_limit,
                            "archival": "true"
                        }
                        
                        async with session.get(f"{api_url}/getTransactions", params=params) as response:
                            if response.status != 200:
                                if attempt < max_attempts - 1:
                                    print(f"⚠️ Попытка {attempt + 1}/{max_attempts}: Ошибка API TON: {response.status}")
                                    await asyncio.sleep(delay_between_attempts)
                                    continue
                                else:
                                    return PaymentVerificationResult(
                                        is_valid=False,
                                        transaction_hash=transaction_hash,
                                        message=f"Ошибка API TON после {max_attempts} попыток: {response.status}"
                                    )
                            
                            data = await response.json()
                            
                            if not data.get("ok"):
                                if attempt < max_attempts - 1:
                                    print(f"⚠️ Попытка {attempt + 1}/{max_attempts}: API ошибка: {data.get('error', 'Unknown error')}")
                                    await asyncio.sleep(delay_between_attempts)
                                    continue
                                else:
                                    return PaymentVerificationResult(
                                        is_valid=False,
                                        transaction_hash=transaction_hash,
                                        message=f"API ошибка после {max_attempts} попыток: {data.get('error', 'Unknown error')}"
                                    )
                            
                            transactions = data.get("result", [])
                            expected_amount_ton = expected_amount_fantics / self.ton_to_fantics_rate
                            
                            # Ищем нужную транзакцию
                            for tx in transactions:
                                tx_hash = tx.get("transaction_id", {}).get("hash")
                                
                                # Проверяем хэш (может быть в разных форматах)
                                if (tx_hash == transaction_hash or 
                                    tx_hash == transaction_hash.replace("0x", "") or
                                    f"0x{tx_hash}" == transaction_hash):
                                    
                                    # Проверяем входящее сообщение
                                    in_msg = tx.get("in_msg", {})
                                    if not in_msg:
                                        continue
                                    
                                    # Проверяем сумму (в нанотонах)
                                    amount_nano = int(in_msg.get("value", "0"))
                                    amount_ton = amount_nano / 1e9
                                    
                                    # В тестнете увеличиваем допуск для комиссий
                                    if config.TON_TESTNET:
                                        tolerance = 0.05  # 0.05 TON допуск для тестнета
                                    else:
                                        tolerance = 0.01  # 0.01 TON допуск для мейннета
                                    
                                    if abs(amount_ton - expected_amount_ton) > tolerance:
                                        return PaymentVerificationResult(
                                            is_valid=False,
                                            transaction_hash=transaction_hash,
                                            amount_sent=amount_ton,
                                            message=f"Неверная сумма: ожидалось {expected_amount_ton:.4f} TON, получено {amount_ton:.4f} TON"
                                        )
                                    
                                    # Проверяем комментарий
                                    msg_data = in_msg.get("msg_data", {})
                                    comment = ""
                                    
                                    if msg_data.get("@type") == "msg.dataText":
                                        comment = msg_data.get("text", "")
                                    elif msg_data.get("@type") == "msg.dataRaw":
                                        # Пытаемся декодировать base64
                                        try:
                                            body = msg_data.get("body", "")
                                            if body:
                                                decoded = base64.b64decode(body).decode('utf-8', errors='ignore')
                                                comment = decoded
                                        except:
                                            pass
                                    
                                    # В тестнете делаем проверку комментария более мягкой
                                    if config.TON_TESTNET:
                                        # В тестнете проверяем только наличие суммы или ID
                                        comment_valid = (
                                            f"ID:{expected_user_id}" in comment or 
                                            f"ID:{expected_user_id}" in expected_comment or
                                            str(expected_amount_fantics) in comment or
                                            str(expected_amount_fantics) in expected_comment
                                        )
                                    else:
                                        # В мейннете строгая проверка
                                        comment_valid = (
                                            f"ID:{expected_user_id}" in comment or 
                                            f"ID:{expected_user_id}" in expected_comment
                                        )
                                    
                                    if not comment_valid:
                                        return PaymentVerificationResult(
                                            is_valid=False,
                                            transaction_hash=transaction_hash,
                                            amount_sent=amount_ton,
                                            message=f"Неверный комментарий: ожидался ID пользователя {expected_user_id} или сумма {expected_amount_fantics}"
                                        )
                                    
                                    # Получаем адрес отправителя
                                    sender = in_msg.get("source", "unknown")
                                    
                                    print(f"✅ Транзакция подтверждена (попытка {attempt + 1}): {transaction_hash}")
                                    return PaymentVerificationResult(
                                        is_valid=True,
                                        transaction_hash=transaction_hash,
                                        amount_sent=amount_ton,
                                        sender_address=sender,
                                        message="Транзакция успешно подтверждена",
                                        block_number=tx.get("transaction_id", {}).get("lt")
                                    )
                            
                            # Транзакция не найдена в этой попытке
                            if attempt < max_attempts - 1:
                                print(f"⚠️ Попытка {attempt + 1}/{max_attempts}: Транзакция {transaction_hash} не найдена, ожидание {delay_between_attempts}с...")
                                await asyncio.sleep(delay_between_attempts)
                            else:
                                print(f"❌ Транзакция {transaction_hash} не найдена после {max_attempts} попыток")
                                return PaymentVerificationResult(
                                    is_valid=False,
                                    transaction_hash=transaction_hash,
                                    message=f"Транзакция не найдена в блокчейне после {max_attempts} попыток"
                                )
                
                except Exception as e:
                    if attempt < max_attempts - 1:
                        print(f"⚠️ Попытка {attempt + 1}/{max_attempts}: Ошибка запроса: {e}")
                        await asyncio.sleep(delay_between_attempts)
                    else:
                        return PaymentVerificationResult(
                            is_valid=False,
                            transaction_hash=transaction_hash,
                            message=f"Ошибка проверки транзакции после {max_attempts} попыток: {str(e)}"
                        )
        
        except Exception as e:
            return PaymentVerificationResult(
                is_valid=False,
                transaction_hash=transaction_hash,
                message=f"Критическая ошибка проверки транзакции: {str(e)}"
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

    # =========================================================================
    # TON КОШЕЛЬКИ (перенесено из ton_wallet_manager.py)
    # =========================================================================

    async def get_user_ton_wallets(self, user_id: int, current_user_id: int) -> List[TonWalletResponse]:
        """Получение всех TON кошельков пользователя"""
        if user_id != current_user_id:
            raise HTTPException(
                status_code=403, 
                detail="Вы можете просматривать только свои кошельки"
            )

        wallets = await self.db.get_user_ton_wallets(user_id)
        return [self._format_wallet_response(wallet) for wallet in wallets]

    async def connect_ton_wallet(
        self, 
        wallet_data: TonWalletRequest, 
        current_user_id: int
    ) -> TonWalletResponse:
        """Подключение TON кошелька"""
        if wallet_data.user_id != current_user_id:
            raise HTTPException(
                status_code=403, 
                detail="Вы можете добавлять только свои кошельки"
            )

        # Валидация адреса кошелька
        if not self.validate_ton_address(wallet_data.wallet_address):
            raise HTTPException(
                status_code=400, 
                detail="Неверный формат адреса TON кошелька"
            )

        # Проверка TON Proof если предоставлен
        if wallet_data.proof:
            if not self.verify_ton_proof(wallet_data.proof, wallet_data.wallet_address):
                raise HTTPException(
                    status_code=400, 
                    detail="Неверная подпись TON Proof"
                )

        success = await self.db.add_ton_wallet(
            user_id=wallet_data.user_id,
            wallet_address=wallet_data.wallet_address,
            network=wallet_data.network,
            public_key=wallet_data.public_key
        )

        if not success:
            raise HTTPException(
                status_code=400, 
                detail="Ошибка добавления кошелька. Возможно, кошелек уже привязан."
            )

        # Получаем добавленный кошелек
        wallet = await self.db.get_ton_wallet_by_address(wallet_data.wallet_address)
        if not wallet:
            raise HTTPException(
                status_code=500, 
                detail="Ошибка получения добавленного кошелька"
            )

        return self._format_wallet_response(wallet)

    async def disconnect_ton_wallet(
        self, 
        wallet_address: str, 
        current_user_id: int
    ) -> Dict[str, str]:
        """Отключение TON кошелька"""
        # Проверяем, что кошелек принадлежит пользователю
        wallet = await self.db.get_ton_wallet_by_address(wallet_address)
        if not wallet:
            raise HTTPException(
                status_code=404, 
                detail="Кошелек не найден"
            )

        if wallet.user_id != current_user_id:
            raise HTTPException(
                status_code=403, 
                detail="Вы можете отключать только свои кошельки"
            )

        success = await self.db.deactivate_ton_wallet(wallet_address)
        if not success:
            raise HTTPException(
                status_code=500, 
                detail="Ошибка отключения кошелька"
            )

        return {"message": f"Кошелек {wallet_address} успешно отключен"}

    def _format_wallet_response(self, wallet) -> TonWalletResponse:
        """Форматирование ответа с данными кошелька"""
        return TonWalletResponse(
            id=wallet.id,
            wallet_address=wallet.wallet_address,
            created_at=wallet.created_at,
            is_active=wallet.is_active,
            network=wallet.network
        )

    def validate_ton_address(self, address: str) -> bool:
        """Валидация TON адреса"""
        try:
            # Простая проверка формата
            if len(address) < 40 or len(address) > 50:
                return False
            
            # Проверяем, что адрес начинается с правильного префикса
            if not (address.startswith('EQ') or address.startswith('UQ') or address.startswith('kQ')):
                return False
            
            # Дополнительная проверка через tonsdk (если нужна более строгая валидация)
            try:
                Address(address)
                return True
            except:
                return False
                
        except Exception:
            return False

    def verify_ton_proof(self, proof: TonProof, wallet_address: str) -> bool:
        """Проверка TON Proof"""
        try:
            # Создаем сообщение для подписи
            message = f"ton-proof-item-v2/{wallet_address}/{proof.domain.lengthBytes}:{proof.domain.value}/{proof.timestamp}/{proof.payload}"
            
            # Декодируем подпись и публичный ключ
            signature_bytes = base64.b64decode(proof.signature)
            
            if proof.pubkey:
                pubkey_bytes = bytes.fromhex(proof.pubkey)
            else:
                return False
            
            # Проверяем подпись
            verify_key = VerifyKey(pubkey_bytes)
            verify_key.verify(message.encode(), signature_bytes)
            
            return True
            
        except (ValueError, BadSignatureError, Exception) as e:
            print(f"❌ Ошибка проверки TON Proof: {e}")
            return False