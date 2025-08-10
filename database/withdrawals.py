"""
Withdrawal management module for Telegram Casino API

This module provides WithdrawalManager class for:
- Withdrawal request management
- Withdrawal status updates
- Withdrawal statistics and history
- TonKeeper integration for TON withdrawals
"""

import asyncio
import sys
import os
from sqlalchemy import select, func
from datetime import datetime
from typing import Optional, List, Dict, Any
from .models import WithdrawalRequest
from .manager import DatabaseManager

# Добавляем путь к корневой директории для импорта ton_keeper_manager
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ton_keeper_manager import tonkeeper_manager


class WithdrawalManager:
    """Менеджер для работы с запросами на вывод средств"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.async_session = db_manager.async_session
        self.tonkeeper = tonkeeper_manager

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
            # Валидация TON адреса через TonKeeper
            if not self.tonkeeper.validate_ton_address(destination_address):
                print(f"❌ Неверный TON адрес: {destination_address}")
                return False
            
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
                
                print(f"✅ Запрос на вывод создан: {amount_ton} TON -> {destination_address}")
                return True
                
        except Exception as e:
            print(f"❌ Ошибка создания запроса на вывод: {e}")
            return False
    
    async def create_withdrawal_qr(
        self, 
        withdrawal_id: int,
        comment: str = ""
    ) -> Optional[Dict[str, Any]]:
        """Создание QR-кода для вывода TON через TonKeeper"""
        try:
            # Получаем данные о выводе
            withdrawal = await self.get_withdrawal_request(withdrawal_id)
            if not withdrawal:
                print(f"❌ Запрос на вывод {withdrawal_id} не найден")
                return None
            
            if withdrawal.status != 'pending':
                print(f"❌ Запрос на вывод {withdrawal_id} уже обработан (статус: {withdrawal.status})")
                return None
            
            # Создаем QR-код через TonKeeper
            qr_result = self.tonkeeper.create_withdrawal_qr(
                amount_ton=withdrawal.amount_ton,
                destination_address=withdrawal.destination_address,
                withdrawal_id=withdrawal_id,
                comment=comment
            )
            
            if qr_result["success"]:
                print(f"✅ QR-код для вывода {withdrawal_id} создан успешно")
                return qr_result
            else:
                print(f"❌ Ошибка создания QR-кода: {qr_result['error']}")
                return None
                
        except Exception as e:
            print(f"❌ Ошибка создания QR-кода: {e}")
            return None
    
    async def get_withdrawal_instructions(
        self, 
        withdrawal_id: int
    ) -> Optional[str]:
        """Получение инструкций по выводу TON"""
        try:
            withdrawal = await self.get_withdrawal_request(withdrawal_id)
            if not withdrawal:
                return None
            
            # Создаем сводку по выводу
            summary = self.tonkeeper.create_withdrawal_summary(
                withdrawal_id=withdrawal_id,
                amount_ton=withdrawal.amount_ton,
                destination_address=withdrawal.destination_address,
                fee_ton=withdrawal.fee_amount
            )
            
            return summary
            
        except Exception as e:
            print(f"❌ Ошибка получения инструкций: {e}")
            return None
    
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
    
    async def get_ton_network_info(self) -> Dict[str, Any]:
        """Получение информации о сети TON"""
        return self.tonkeeper.get_ton_network_info()
    
    def estimate_ton_fee(self) -> float:
        """Оценка комиссии за транзакцию TON"""
        return self.tonkeeper.estimate_transaction_fee() 