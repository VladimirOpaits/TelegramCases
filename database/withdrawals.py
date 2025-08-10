"""
Withdrawal management module for Telegram Casino API

This module provides WithdrawalManager class for:
- Withdrawal request management
- Withdrawal status updates
- Withdrawal statistics and history
"""

from sqlalchemy import select, func
from datetime import datetime
from typing import Optional, List
from .models import WithdrawalRequest
from .manager import DatabaseManager


class WithdrawalManager:
    """Менеджер для работы с запросами на вывод средств"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.async_session = db_manager.async_session

    # ========== МЕТОДЫ ДЛЯ РАБОТЫ С ЗАПРОСАМИ НА ВЫВОД ==========
    
    async def create_withdrawal_request(
        self,
        user_id: int,
        amount_fantics: int,
        amount_ton: float,
        fee_amount: float,
        destination_address: str
    ) -> bool:
        """Создание запроса на вывод TON"""
        try:
            async with self.async_session() as session:
                withdrawal = WithdrawalRequest(
                    user_id=user_id,
                    amount_fantics=amount_fantics,
                    amount_ton=amount_ton,
                    fee_amount=fee_amount,
                    destination_address=destination_address,
                    status='pending'
                )
                session.add(withdrawal)
                await session.commit()
                return True
                
        except Exception as e:
            print(f"❌ Ошибка создания запроса на вывод: {e}")
            return False
    
    async def get_withdrawal_request(self, request_id: int) -> Optional[WithdrawalRequest]:
        """Получение запроса на вывод по ID"""
        try:
            async with self.async_session() as session:
                stmt = select(WithdrawalRequest).where(WithdrawalRequest.id == request_id)
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
                
        except Exception as e:
            print(f"❌ Ошибка получения запроса на вывод: {e}")
            return None
    
    async def get_user_withdrawal_requests(
        self, 
        user_id: int, 
        limit: int = 50
    ) -> List[WithdrawalRequest]:
        """Получение истории запросов на вывод пользователя"""
        try:
            async with self.async_session() as session:
                stmt = select(WithdrawalRequest).where(
                    WithdrawalRequest.user_id == user_id
                ).order_by(WithdrawalRequest.created_at.desc()).limit(limit)
                
                result = await session.execute(stmt)
                return result.scalars().all()
                
        except Exception as e:
            print(f"❌ Ошибка получения истории выводов: {e}")
            return []
    
    async def get_pending_withdrawals(self, limit: int = 50) -> List[WithdrawalRequest]:
        """Получение всех ожидающих обработки запросов на вывод"""
        try:
            async with self.async_session() as session:
                stmt = select(WithdrawalRequest).where(
                    WithdrawalRequest.status == 'pending'
                ).order_by(WithdrawalRequest.created_at.asc()).limit(limit)
                
                result = await session.execute(stmt)
                return result.scalars().all()
                
        except Exception as e:
            print(f"❌ Ошибка получения ожидающих выводов: {e}")
            return []
    
    async def update_withdrawal_status(
        self,
        request_id: int,
        status: str,
        transaction_hash: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """Обновление статуса запроса на вывод"""
        try:
            async with self.async_session() as session:
                stmt = select(WithdrawalRequest).where(WithdrawalRequest.id == request_id)
                result = await session.execute(stmt)
                withdrawal = result.scalar_one_or_none()
                
                if not withdrawal:
                    return False
                
                withdrawal.status = status
                if transaction_hash:
                    withdrawal.transaction_hash = transaction_hash
                if error_message:
                    withdrawal.error_message = error_message
                
                if status in ['completed', 'failed']:
                    withdrawal.processed_at = datetime.now()
                
                await session.commit()
                return True
                
        except Exception as e:
            print(f"❌ Ошибка обновления статуса вывода: {e}")
            return False
    
    async def get_withdrawal_statistics(self) -> dict:
        """Получение статистики выводов"""
        try:
            async with self.async_session() as session:
                # Общая статистика
                total_withdrawals = await session.scalar(
                    select(func.count(WithdrawalRequest.id))
                )
                
                # Статистика по статусам
                pending_withdrawals = await session.scalar(
                    select(func.count(WithdrawalRequest.id)).where(
                        WithdrawalRequest.status == 'pending'
                    )
                )
                
                completed_withdrawals = await session.scalar(
                    select(func.count(WithdrawalRequest.id)).where(
                        WithdrawalRequest.status == 'completed'
                    )
                )
                
                failed_withdrawals = await session.scalar(
                    select(func.count(WithdrawalRequest.id)).where(
                        WithdrawalRequest.status == 'failed'
                    )
                )
                
                # Общая сумма фантиков
                total_fantics = await session.scalar(
                    select(func.sum(WithdrawalRequest.amount_fantics))
                ) or 0
                
                # Общая сумма в TON
                total_ton = await session.scalar(
                    select(func.sum(WithdrawalRequest.amount_ton))
                ) or 0
                
                # Общая сумма комиссий
                total_fees = await session.scalar(
                    select(func.sum(WithdrawalRequest.fee_amount))
                ) or 0
                
                return {
                    "total_withdrawals": total_withdrawals,
                    "pending_withdrawals": pending_withdrawals,
                    "completed_withdrawals": completed_withdrawals,
                    "failed_withdrawals": failed_withdrawals,
                    "total_fantics": total_fantics,
                    "total_ton": total_ton,
                    "total_fees": total_fees
                }
                
        except Exception as e:
            print(f"❌ Ошибка получения статистики выводов: {e}")
            return {
                "total_withdrawals": 0,
                "pending_withdrawals": 0,
                "completed_withdrawals": 0,
                "failed_withdrawals": 0,
                "total_fantics": 0,
                "total_ton": 0,
                "total_fees": 0
            } 