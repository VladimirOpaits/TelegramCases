"""
User management module for Telegram Casino API

This module provides UserManager class for:
- User CRUD operations
- Balance management (fantics)
- Atomic transactions for balance operations
"""

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import Optional, List, Tuple
from .models import User
from .manager import DatabaseManager


class UserManager:
    """Менеджер для работы с пользователями и их балансами"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.async_session = db_manager.async_session

    # ========== МЕТОДЫ ДЛЯ РАБОТЫ С ПОЛЬЗОВАТЕЛЯМИ ==========
    
    async def add_user(self, user_id: int, username: Optional[str] = None) -> bool:
        """Добавление пользователя в базу данных"""
        try:
            async with self.async_session() as session:
                stmt = select(User).where(User.user_id == user_id)
                result = await session.execute(stmt)
                existing_user = result.scalar_one_or_none()

                if existing_user:
                    if username and existing_user.username != username:
                        existing_user.username = username
                        await session.commit()
                        print(f"🔄 Username пользователя {user_id} обновлен на {username}")
                    return True

                new_user = User(
                    user_id=user_id,
                    username=username,
                    registration_date=datetime.now()
                )

                session.add(new_user)
                await session.commit()
                print(f"➕ Пользователь {user_id} успешно добавлен в базу")
                return True

        except Exception as e:
            print(f"❌ Ошибка при добавлении пользователя в БД: {e}")
            return False

    async def get_user(self, user_id: int) -> Optional[User]:
        """Получение пользователя из базы данных"""
        try:
            async with self.async_session() as session:
                stmt = select(User).where(User.user_id == user_id)
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
        except Exception as e:
            print(f"❌ Ошибка при получении пользователя из БД: {e}")
            return None

    async def get_all_users(self) -> List[User]:
        """Получение всех пользователей из базы данных"""
        try:
            async with self.async_session() as session:
                stmt = select(User)
                result = await session.execute(stmt)
                return list(result.scalars().all())
        except Exception as e:
            print(f"❌ Ошибка при получении всех пользователей из БД: {e}")
            return []

    async def update_user_username(self, user_id: int, new_username: str) -> bool:
        """Обновление username пользователя"""
        try:
            async with self.async_session() as session:
                stmt = select(User).where(User.user_id == user_id)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()

                if user:
                    user.username = new_username
                    await session.commit()
                    print(f"🔄 Username пользователя {user_id} обновлен")
                    return True
                else:
                    print(f"❌ Пользователь {user_id} не найден")
                    return False

        except Exception as e:
            print(f"❌ Ошибка при обновлении username пользователя: {e}")
            return False

    async def delete_user(self, user_id: int) -> bool:
        """Удаление пользователя из базы данных"""
        try:
            async with self.async_session() as session:
                stmt = select(User).where(User.user_id == user_id)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()

                if user:
                    await session.delete(user)
                    await session.commit()
                    print(f"🗑️ Пользователь {user_id} удален из базы")
                    return True
                else:
                    print(f"❌ Пользователь {user_id} не найден")
                    return False

        except Exception as e:
            print(f"❌ Ошибка при удалении пользователя: {e}")
            return False

    async def get_users_count(self) -> int:
        """Получение количества пользователей"""
        try:
            async with self.async_session() as session:
                stmt = select(func.count(User.id))
                result = await session.execute(stmt)
                return result.scalar() or 0
        except Exception as e:
            print(f"❌ Ошибка при подсчете пользователей: {e}")
            return 0

    # ========== МЕТОДЫ ДЛЯ РАБОТЫ С ФАНТИКАМИ ==========

    async def get_fantics(self, user_id: int) -> Optional[int]:
        """Получить количество фантиков пользователя"""
        try:
            async with self.async_session() as session:
                stmt = select(User.fantics).where(User.user_id == user_id)
                result = await session.execute(stmt)
                fantics = result.scalar_one_or_none()
                return fantics if fantics is not None else 0
        except Exception as e:
            print(f"❌ Ошибка при получении фантиков: {e}")
            return None

    async def add_fantics(self, user_id: int, amount: int) -> bool:
        """Добавить фантики пользователю"""
        try:
            async with self.async_session() as session:
                stmt = select(User).where(User.user_id == user_id)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()

                if user:
                    user.fantics += amount
                    await session.commit()
                    print(f"➕ Добавлено {amount} фантиков пользователю {user_id} (итого: {user.fantics})")
                    return True
                else:
                    print(f"❌ Пользователь {user_id} не найден")
                    return False
        except Exception as e:
            print(f"❌ Ошибка при добавлении фантиков: {e}")
            return False

    async def subtract_fantics(self, user_id: int, amount: int) -> bool:
        """Списать фантики у пользователя"""
        try:
            async with self.async_session() as session:
                stmt = select(User).where(User.user_id == user_id)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()

                if user and user.fantics >= amount:
                    user.fantics -= amount
                    await session.commit()
                    print(f"➖ Списано {amount} фантиков у пользователя {user_id} (осталось: {user.fantics})")
                    return True
                else:
                    if user:
                        print(f"❌ Недостаточно фантиков у пользователя {user_id}: есть {user.fantics}, нужно {amount}")
                    else:
                        print(f"❌ Пользователь {user_id} не найден")
                    return False
        except Exception as e:
            print(f"❌ Ошибка при списании фантиков: {e}")
            return False

    async def set_fantics(self, user_id: int, amount: int) -> bool:
        """Установить точное количество фантиков пользователю"""
        try:
            async with self.async_session() as session:
                stmt = select(User).where(User.user_id == user_id)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()

                if user:
                    user.fantics = max(0, amount)  # Не позволяем отрицательные значения
                    await session.commit()
                    print(f"🔄 Установлено {amount} фантиков пользователю {user_id}")
                    return True
                else:
                    print(f"❌ Пользователь {user_id} не найден")
                    return False
        except Exception as e:
            print(f"❌ Ошибка при установке фантиков: {e}")
            return False

    # ========== АТОМАРНЫЕ ОПЕРАЦИИ ДЛЯ БЕЗОПАСНОСТИ ==========

    async def atomic_case_transaction(self, user_id: int, case_cost: int, prize_amount: int) -> Tuple[bool, str, int]:
        """
        Атомарная транзакция для открытия кейса:
        1. Проверяет существование пользователя
        2. Проверяет баланс
        3. Списывает стоимость кейса
        4. Добавляет выигрыш
        
        Возвращает: (успех, сообщение, новый_баланс)
        """
        try:
            async with self.async_session() as session:
                # Начинаем транзакцию с блокировкой строки пользователя
                stmt = select(User).where(User.user_id == user_id).with_for_update()
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()

                if not user:
                    return False, "Пользователь не найден в системе", 0

                # Проверяем достаточность средств
                if user.fantics < case_cost:
                    return False, f"Недостаточно фантиков. Требуется: {case_cost}, доступно: {user.fantics}", user.fantics

                # Выполняем атомарную операцию
                old_balance = user.fantics
                user.fantics = user.fantics - case_cost + prize_amount
                new_balance = user.fantics

                # Фиксируем транзакцию
                await session.commit()
                
                print(f"💎 Атомарная транзакция кейса: пользователь {user_id}, баланс {old_balance} -> {new_balance}")
                return True, f"Кейс открыт! Потрачено: {case_cost}, выиграно: {prize_amount}", new_balance

        except Exception as e:
            print(f"❌ Ошибка в атомарной транзакции кейса: {e}")
            return False, f"Ошибка транзакции: {str(e)}", 0

    async def atomic_subtract_fantics(self, user_id: int, amount: int) -> Tuple[bool, str, int]:
        """
        Атомарное списание фантиков с проверкой баланса
        
        Возвращает: (успех, сообщение, новый_баланс)
        """
        try:
            async with self.async_session() as session:
                # Блокируем строку пользователя для чтения и изменения
                stmt = select(User).where(User.user_id == user_id).with_for_update()
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()

                if not user:
                    return False, "Пользователь не найден", 0

                # Проверяем достаточность средств
                if user.fantics < amount:
                    return False, f"Недостаточно фантиков. Требуется: {amount}, доступно: {user.fantics}", user.fantics

                # Списываем средства
                old_balance = user.fantics
                user.fantics -= amount
                new_balance = user.fantics

                await session.commit()
                
                print(f"➖ Атомарное списание: пользователь {user_id}, {old_balance} -> {new_balance}")
                return True, f"Списано {amount} фантиков", new_balance

        except Exception as e:
            print(f"❌ Ошибка в атомарном списании: {e}")
            return False, f"Ошибка списания: {str(e)}", 0

    async def atomic_add_fantics(self, user_id: int, amount: int) -> Tuple[bool, str, int]:
        """
        Атомарное добавление фантиков
        
        Возвращает: (успех, сообщение, новый_баланс)
        """
        try:
            async with self.async_session() as session:
                # Блокируем строку пользователя
                stmt = select(User).where(User.user_id == user_id).with_for_update()
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()

                if not user:
                    return False, "Пользователь не найден в системе", 0

                # Добавляем средства
                old_balance = user.fantics
                user.fantics += amount
                new_balance = user.fantics

                await session.commit()
                
                print(f"➕ Атомарное добавление: пользователь {user_id}, {old_balance} -> {new_balance}")
                return True, f"Добавлено {amount} фантиков", new_balance

        except Exception as e:
            print(f"❌ Ошибка в атомарном добавлении: {e}")
            return False, f"Ошибка добавления: {str(e)}", 0 