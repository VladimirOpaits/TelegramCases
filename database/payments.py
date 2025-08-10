"""
Payment management module for Telegram Casino API

This module provides PaymentManager class for:
- Pending payment management
- Successful payment recording
- Payment statistics and verification
"""

from sqlalchemy import select, func
from datetime import datetime, timedelta
from typing import Optional, List
from .models import PendingPayment, SuccessfulPayment
from .manager import DatabaseManager


class PaymentManager:
    """Менеджер для работы с платежами"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.async_session = db_manager.async_session

    # ========== МЕТОДЫ ДЛЯ РАБОТЫ С PENDING ПЛАТЕЖАМИ ==========
    
    async def create_pending_payment(
        self, 
        payment_id: str,
        user_id: int,
        amount_fantics: int,
        amount_ton: float,
        payment_method: str,
        destination_address: str,
        comment: str,
        expires_in_minutes: int = 30
    ) -> bool:
        """Создание записи о pending платеже"""
        try:
            async with self.async_session() as session:
                expires_at = datetime.now() + timedelta(minutes=expires_in_minutes)
                
                payment = PendingPayment(
                    payment_id=payment_id,
                    user_id=user_id,
                    amount_fantics=amount_fantics,
                    amount_ton=amount_ton,
                    payment_method=payment_method,
                    status='pending',
                    destination_address=destination_address,
                    comment=comment,
                    expires_at=expires_at
                )
                
                session.add(payment)
                await session.commit()
                
                print(f"💰 Создан pending платеж {payment_id} для пользователя {user_id} на {amount_fantics} фантиков")
                return True
                
        except Exception as e:
            print(f"❌ Ошибка создания pending платежа: {e}")
            return False
    
    async def get_pending_payment(self, payment_id: str) -> Optional[PendingPayment]:
        """Получение pending платежа по ID"""
        try:
            async with self.async_session() as session:
                stmt = select(PendingPayment).where(PendingPayment.payment_id == payment_id)
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
        except Exception as e:
            print(f"❌ Ошибка получения pending платежа: {e}")
            return None
    
    async def update_payment_status(
        self, 
        payment_id: str, 
        status: str, 
        transaction_hash: Optional[str] = None
    ) -> bool:
        """Обновление статуса платежа"""
        try:
            async with self.async_session() as session:
                stmt = select(PendingPayment).where(PendingPayment.payment_id == payment_id)
                result = await session.execute(stmt)
                payment = result.scalar_one_or_none()
                
                if not payment:
                    print(f"❌ Pending платеж {payment_id} не найден")
                    return False
                
                payment.status = status
                if transaction_hash:
                    payment.transaction_hash = transaction_hash
                if status == 'confirmed':
                    payment.confirmed_at = datetime.now()
                
                await session.commit()
                print(f"✅ Статус платежа {payment_id} обновлен на '{status}'")
                return True
                
        except Exception as e:
            print(f"❌ Ошибка обновления статуса платежа: {e}")
            return False
    
    async def get_pending_payments_for_verification(self, limit: int = 50) -> List[PendingPayment]:
        """Получение pending платежей для проверки"""
        try:
            async with self.async_session() as session:
                stmt = select(PendingPayment).where(
                    PendingPayment.status == 'pending',
                    PendingPayment.expires_at > datetime.now()
                ).limit(limit)
                result = await session.execute(stmt)
                return result.scalars().all()
        except Exception as e:
            print(f"❌ Ошибка получения pending платежей: {e}")
            return []
    
    async def expire_old_payments(self) -> int:
        """Помечает истекшие платежи как expired"""
        try:
            async with self.async_session() as session:
                stmt = select(PendingPayment).where(
                    PendingPayment.status == 'pending',
                    PendingPayment.expires_at <= datetime.now()
                )
                result = await session.execute(stmt)
                expired_payments = result.scalars().all()
                
                count = 0
                for payment in expired_payments:
                    payment.status = 'expired'
                    count += 1
                
                await session.commit()
                if count > 0:
                    print(f"⏰ Помечено {count} платежей как истекшие")
                return count
                
        except Exception as e:
            print(f"❌ Ошибка при истечении платежей: {e}")
            return 0

    # ========== МЕТОДЫ ДЛЯ РАБОТЫ С УСПЕШНЫМИ ПЛАТЕЖАМИ ==========
    
    async def add_successful_payment(
        self,
        user_id: int,
        payment_method: str,
        amount_fantics: int,
        amount_paid: float,
        sender_wallet: Optional[str] = None,
        transaction_hash: Optional[str] = None,
        payment_id: Optional[str] = None
    ) -> bool:
        """Добавление успешного платежа в базу данных"""
        try:
            async with self.async_session() as session:
                payment = SuccessfulPayment(
                    user_id=user_id,
                    payment_method=payment_method,
                    amount_fantics=amount_fantics,
                    amount_paid=amount_paid,
                    sender_wallet=sender_wallet,
                    transaction_hash=transaction_hash,
                    payment_id=payment_id
                )
                
                session.add(payment)
                await session.commit()
                
                print(f"✅ Успешный платеж записан: пользователь {user_id}, метод {payment_method}, {amount_fantics} фантиков за {amount_paid}")
                return True
                
        except Exception as e:
            print(f"❌ Ошибка записи успешного платежа: {e}")
            return False
    
    async def get_user_successful_payments(
        self, 
        user_id: int, 
        limit: int = 50
    ) -> List[SuccessfulPayment]:
        """Получение истории успешных платежей пользователя"""
        try:
            async with self.async_session() as session:
                stmt = select(SuccessfulPayment).where(
                    SuccessfulPayment.user_id == user_id
                ).order_by(SuccessfulPayment.created_at.desc()).limit(limit)
                
                result = await session.execute(stmt)
                return result.scalars().all()
                
        except Exception as e:
            print(f"❌ Ошибка получения истории платежей: {e}")
            return []
    
    async def get_all_successful_payments(
        self, 
        limit: int = 100
    ) -> List[SuccessfulPayment]:
        """Получение всех успешных платежей (для админа)"""
        try:
            async with self.async_session() as session:
                stmt = select(SuccessfulPayment).order_by(
                    SuccessfulPayment.created_at.desc()
                ).limit(limit)
                
                result = await session.execute(stmt)
                return result.scalars().all()
                
        except Exception as e:
            print(f"❌ Ошибка получения всех платежей: {e}")
            return []
    
    async def get_payment_statistics(self) -> dict:
        """Получение статистики платежей"""
        try:
            async with self.async_session() as session:
                # Общая статистика
                total_payments = await session.scalar(
                    select(func.count(SuccessfulPayment.id))
                )
                
                # Статистика по методам оплаты
                ton_payments = await session.scalar(
                    select(func.count(SuccessfulPayment.id)).where(
                        SuccessfulPayment.payment_method == 'ton'
                    )
                )
                
                stars_payments = await session.scalar(
                    select(func.count(SuccessfulPayment.id)).where(
                        SuccessfulPayment.payment_method == 'stars'
                    )
                )
                
                # Общая сумма фантиков
                total_fantics = await session.scalar(
                    select(func.sum(SuccessfulPayment.amount_fantics))
                ) or 0
                
                # Общая сумма в TON
                total_ton = await session.scalar(
                    select(func.sum(SuccessfulPayment.amount_paid)).where(
                        SuccessfulPayment.payment_method == 'ton'
                    )
                ) or 0
                
                return {
                    "total_payments": total_payments,
                    "ton_payments": ton_payments,
                    "stars_payments": stars_payments,
                    "total_fantics": total_fantics,
                    "total_ton": total_ton
                }
                
        except Exception as e:
            print(f"❌ Ошибка получения статистики платежей: {e}")
            return {
                "total_payments": 0,
                "ton_payments": 0,
                "stars_payments": 0,
                "total_fantics": 0,
                "total_ton": 0
            }

    async def get_pending_payment_by_user(self, user_id: int, limit: int = 10) -> List[PendingPayment]:
        """Получение pending платежей пользователя"""
        try:
            async with self.async_session() as session:
                stmt = select(PendingPayment).where(
                    PendingPayment.user_id == user_id
                ).order_by(PendingPayment.created_at.desc()).limit(limit)
                
                result = await session.execute(stmt)
                return result.scalars().all()
                
        except Exception as e:
            print(f"❌ Ошибка получения pending платежей пользователя: {e}")
            return []

    async def get_payment_by_transaction_hash(self, transaction_hash: str) -> Optional[PendingPayment]:
        """Получение платежа по хэшу транзакции"""
        try:
            async with self.async_session() as session:
                stmt = select(PendingPayment).where(
                    PendingPayment.transaction_hash == transaction_hash
                )
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
                
        except Exception as e:
            print(f"❌ Ошибка получения платежа по хэшу: {e}")
            return None 