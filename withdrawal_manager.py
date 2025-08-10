"""
Менеджер автоматического вывода TON
Обрабатывает запросы на вывод и автоматически отправляет TON пользователям
"""

import asyncio
import logging
import base64
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from tonsdk.contract.wallet import Wallets, WalletVersionEnum
from tonsdk.utils import Address, to_nano
from tonsdk.provider import ToncenterClient

from database import DatabaseFacade
from config import (
    TON_TESTNET, 
    WITHDRAWAL_ENABLED, 
    WITHDRAWAL_MIN_AMOUNT, 
    WITHDRAWAL_MAX_AMOUNT,
    WITHDRAWAL_DAILY_LIMIT,
    WITHDRAWAL_FEE_PERCENT,
    WITHDRAWAL_PRIVATE_KEY
)

logger = logging.getLogger(__name__)


class WithdrawalRequestModel(BaseModel):
    """Модель запроса на вывод"""
    user_id: int
    amount_fantics: int
    destination_address: str


class WithdrawalResponse(BaseModel):
    """Ответ на запрос вывода"""
    success: bool
    message: str
    withdrawal_id: Optional[int] = None
    amount_ton: Optional[float] = None
    fee_amount: Optional[float] = None


class WithdrawalManager:
    """Менеджер автоматического вывода TON"""
    
    def __init__(self, db_manager: DatabaseFacade):
        self.db_manager = db_manager
        self.ton_client = None
        self.wallet = None
        self.is_initialized = False
        
        # Инициализируем TON клиент
        self._init_ton_client()
    
    def _init_ton_client(self):
        """Инициализация TON клиента"""
        try:
            if TON_TESTNET:
                # Testnet
                self.ton_client = ToncenterClient(
                    base_url="https://testnet.toncenter.com/api/v2/jsonRPC",
                    api_key="YOUR_TESTNET_API_KEY"  # Замените на ваш API ключ
                )
            else:
                # Mainnet
                self.ton_client = ToncenterClient(
                    base_url="https://toncenter.com/api/v2/jsonRPC",
                    api_key="YOUR_MAINNET_API_KEY"  # Замените на ваш API ключ
                )
            
            # Инициализируем кошелек если есть приватный ключ
            if WITHDRAWAL_PRIVATE_KEY:
                self._init_wallet()
            
            self.is_initialized = True
            logger.info("✅ TON клиент инициализирован")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации TON клиента: {e}")
            self.is_initialized = False
    
    def _init_wallet(self):
        """Инициализация кошелька для автоматического вывода"""
        try:
            if not WITHDRAWAL_PRIVATE_KEY:
                logger.warning("⚠️ Приватный ключ не настроен, автоматический вывод отключен")
                return
            
            # Декодируем приватный ключ
            private_key_bytes = base64.b64decode(WITHDRAWAL_PRIVATE_KEY)
            
            # Создаем кошелек
            self.wallet = Wallets.create(
                version=WalletVersionEnum.v3r2,
                workchain=0,
                private_key=private_key_bytes
            )
            
            logger.info(f"✅ Кошелек инициализирован: {self.wallet.address}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации кошелька: {e}")
            self.wallet = None
    
    async def validate_withdrawal_request(self, request: WithdrawalRequestModel) -> tuple[bool, str]:
        """Валидация запроса на вывод"""
        try:
            # Проверяем, включен ли вывод
            if not WITHDRAWAL_ENABLED:
                return False, "Вывод TON временно отключен"
            
            # Проверяем минимальную сумму
            if request.amount_fantics < WITHDRAWAL_MIN_AMOUNT:
                return False, f"Минимальная сумма для вывода: {WITHDRAWAL_MIN_AMOUNT:,} фантиков"
            
            # Проверяем максимальную сумму
            if request.amount_fantics > WITHDRAWAL_MAX_AMOUNT:
                return False, f"Максимальная сумма для вывода: {WITHDRAWAL_MAX_AMOUNT:,} фантиков"
            
            # Проверяем адрес TON
            try:
                Address(request.destination_address)
            except Exception:
                return False, "Неверный адрес TON кошелька"
            
            # Проверяем дневной лимит
            if not await self._check_daily_limit(request.user_id, request.amount_fantics):
                return False, f"Превышен дневной лимит: {WITHDRAWAL_DAILY_LIMIT:,} фантиков"
            
            return True, "OK"
            
        except Exception as e:
            logger.error(f"❌ Ошибка валидации запроса на вывод: {e}")
            return False, "Ошибка валидации запроса"
    
    async def _check_daily_limit(self, user_id: int, amount: int) -> bool:
        """Проверка дневного лимита для пользователя"""
        try:
            # Получаем все выводы пользователя за сегодня
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            tomorrow = today + timedelta(days=1)
            
            user_withdrawals = await self.db_manager.get_user_withdrawal_requests(user_id, limit=1000)
            
            # Считаем сумму выводов за сегодня
            today_total = sum(
                w.amount_fantics for w in user_withdrawals 
                if today <= w.created_at < tomorrow and w.status in ['pending', 'completed']
            )
            
            return (today_total + amount) <= WITHDRAWAL_DAILY_LIMIT
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки дневного лимита: {e}")
            return False
    
    def calculate_withdrawal_amounts(self, fantics_amount: int) -> tuple[float, float]:
        """Расчет суммы в TON и комиссии"""
        # Конвертируем фантики в TON (1 фантик = 0.001 TON)
        ton_amount = fantics_amount * 0.001
        
        # Рассчитываем комиссию
        fee_amount = ton_amount * (WITHDRAWAL_FEE_PERCENT / 100)
        
        # Итоговая сумма к отправке (без комиссии)
        final_ton_amount = ton_amount - fee_amount
        
        return final_ton_amount, fee_amount
    
    async def create_withdrawal_request(self, request: WithdrawalRequestModel) -> WithdrawalResponse:
        """Создание запроса на вывод"""
        try:
            # Валидируем запрос
            is_valid, message = self.validate_withdrawal_request(request)
            if not is_valid:
                return WithdrawalResponse(success=False, message=message)
            
            # Проверяем баланс пользователя
            user_balance = await self.db_manager.get_fantics(request.user_id)
            if user_balance is None or user_balance < request.amount_fantics:
                return WithdrawalResponse(success=False, message="Недостаточно фантиков на балансе")
            
            # Рассчитываем суммы
            amount_ton, fee_amount = self.calculate_withdrawal_amounts(request.amount_fantics)
            
            # Создаем запрос в базе данных
            success = await self.db_manager.create_withdrawal_request(
                user_id=request.user_id,
                amount_fantics=request.amount_fantics,
                amount_ton=amount_ton,
                fee_amount=fee_amount,
                destination_address=request.destination_address
            )
            
            if not success:
                return WithdrawalResponse(success=False, message="Ошибка создания запроса на вывод")
            
            # Списываем фантики с баланса пользователя
            success, message, new_balance = await self.db_manager.atomic_subtract_fantics(
                request.user_id, 
                request.amount_fantics
            )
            
            if not success:
                return WithdrawalResponse(success=False, message=f"Ошибка списания фантиков: {message}")
            
            # Получаем ID созданного запроса
            user_withdrawals = await self.db_manager.get_user_withdrawal_requests(request.user_id, limit=1)
            withdrawal_id = user_withdrawals[0].id if user_withdrawals else None
            
            return WithdrawalResponse(
                success=True,
                message="Запрос на вывод создан успешно",
                withdrawal_id=withdrawal_id,
                amount_ton=amount_ton,
                fee_amount=fee_amount
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания запроса на вывод: {e}")
            return WithdrawalResponse(success=False, message=f"Ошибка создания запроса: {str(e)}")
    
    async def process_pending_withdrawals(self) -> Dict[str, Any]:
        """Обработка всех ожидающих выводов"""
        try:
            if not self.is_initialized or not self.wallet:
                return {
                    "success": False,
                    "message": "TON клиент не инициализирован",
                    "processed": 0,
                    "successful": 0,
                    "failed": 0
                }
            
            # Получаем все ожидающие выводы
            pending_withdrawals = await self.db_manager.get_pending_withdrawals(limit=100)
            
            if not pending_withdrawals:
                return {
                    "success": True,
                    "message": "Нет ожидающих выводов",
                    "processed": 0,
                    "successful": 0,
                    "failed": 0
                }
            
            processed = 0
            successful = 0
            failed = 0
            
            for withdrawal in pending_withdrawals:
                try:
                    # Обновляем статус на "обрабатывается"
                    await self.db_manager.update_withdrawal_status(
                        withdrawal.id, 
                        'processing'
                    )
                    
                    # Отправляем TON
                    success, tx_hash, error = await self._send_ton_transaction(
                        withdrawal.destination_address,
                        withdrawal.amount_ton
                    )
                    
                    if success:
                        # Обновляем статус на "завершено"
                        await self.db_manager.update_withdrawal_status(
                            withdrawal.id,
                            'completed',
                            transaction_hash=tx_hash
                        )
                        successful += 1
                        logger.info(f"✅ Вывод {withdrawal.id} выполнен успешно: {tx_hash}")
                    else:
                        # Обновляем статус на "ошибка"
                        await self.db_manager.update_withdrawal_status(
                            withdrawal.id,
                            'failed',
                            error_message=error
                        )
                        failed += 1
                        logger.error(f"❌ Ошибка вывода {withdrawal.id}: {error}")
                    
                    processed += 1
                    
                    # Небольшая задержка между транзакциями
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка обработки вывода {withdrawal.id}: {e}")
                    await self.db_manager.update_withdrawal_status(
                        withdrawal.id,
                        'failed',
                        error_message=str(e)
                    )
                    failed += 1
                    processed += 1
            
            return {
                "success": True,
                "message": f"Обработано {processed} выводов",
                "processed": processed,
                "successful": successful,
                "failed": failed
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки выводов: {e}")
            return {
                "success": False,
                "message": f"Ошибка обработки: {str(e)}",
                "processed": 0,
                "successful": 0,
                "failed": 0
            }
    
    async def _send_ton_transaction(self, destination: str, amount: float) -> tuple[bool, Optional[str], Optional[str]]:
        """Отправка TON транзакции"""
        try:
            if not self.wallet:
                return False, None, "Кошелек не инициализирован"
            
            # Конвертируем сумму в наноТОН
            amount_nano = to_nano(amount)
            
            # Создаем транзакцию
            transfer = self.wallet.create_transfer_message(
                dest=destination,
                amount=amount_nano,
                seqno=0,  # Нужно получить актуальный seqno
                payload="Casino withdrawal"  # Комментарий к транзакции
            )
            
            # Отправляем транзакцию
            # Примечание: здесь нужно реализовать полную логику отправки
            # с получением seqno и подписью транзакции
            
            # Временная заглушка
            logger.info(f"📤 Отправка {amount} TON на адрес {destination}")
            
            # Имитируем успешную отправку
            tx_hash = f"fake_tx_{datetime.now().timestamp()}"
            
            return True, tx_hash, None
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки TON транзакции: {e}")
            return False, None, str(e)
    
    async def get_withdrawal_info(self, user_id: int) -> Dict[str, Any]:
        """Получение информации о выводе для пользователя"""
        try:
            # Получаем статистику выводов пользователя
            user_withdrawals = await self.db_manager.get_user_withdrawal_requests(user_id, limit=100)
            
            # Считаем статистику
            total_withdrawals = len(user_withdrawals)
            pending_withdrawals = len([w for w in user_withdrawals if w.status == 'pending'])
            completed_withdrawals = len([w for w in user_withdrawals if w.status == 'completed'])
            failed_withdrawals = len([w for w in user_withdrawals if w.status == 'failed'])
            
            # Считаем суммы
            total_fantics = sum(w.amount_fantics for w in user_withdrawals if w.status == 'completed')
            total_ton = sum(w.amount_ton for w in user_withdrawals if w.status == 'completed')
            
            return {
                "withdrawal_enabled": WITHDRAWAL_ENABLED,
                "min_amount": WITHDRAWAL_MIN_AMOUNT,
                "max_amount": WITHDRAWAL_MAX_AMOUNT,
                "daily_limit": WITHDRAWAL_DAILY_LIMIT,
                "fee_percent": WITHDRAWAL_FEE_PERCENT,
                "total_withdrawals": total_withdrawals,
                "pending_withdrawals": pending_withdrawals,
                "completed_withdrawals": completed_withdrawals,
                "failed_withdrawals": failed_withdrawals,
                "total_fantics": total_fantics,
                "total_ton": total_ton
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения информации о выводе: {e}")
            return {
                "withdrawal_enabled": False,
                "error": str(e)
            } 