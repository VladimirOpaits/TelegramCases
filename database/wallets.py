"""
TON wallet management module for Telegram Casino API

This module provides WalletManager class for:
- TON wallet CRUD operations
- Wallet activation/deactivation
- Wallet verification and management
"""

from sqlalchemy import select
from typing import Optional, List
from .models import TonWallet, User
from .manager import DatabaseManager


class WalletManager:
    """Менеджер для работы с TON кошельками"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.async_session = db_manager.async_session

    async def add_ton_wallet(
        self, 
        user_id: int, 
        wallet_address: str, 
        network: Optional[str] = None, 
        public_key: Optional[str] = None, 
        retry_count: int = 0
    ) -> bool:
        """
        Добавление TON кошелька для пользователя
        :param user_id: ID пользователя в Telegram
        :param wallet_address: Адрес кошелька в сети TON
        :param network: Сеть кошелька (например, "-239")
        :param public_key: Публичный ключ кошелька в hex формате
        :param retry_count: Счетчик повторных попыток (для предотвращения рекурсии)
        :return: True если успешно, False если ошибка
        """
        try:
            async with self.async_session() as session:
                # Проверяем существование пользователя
                user_stmt = select(User).where(User.user_id == user_id)
                user_result = await session.execute(user_stmt)
                user = user_result.scalar_one_or_none()
                
                if not user:
                    print(f"❌ Пользователь {user_id} не найден")
                    return False
                
                # Проверяем, не привязан ли уже этот кошелек
                wallet_stmt = select(TonWallet).where(
                    (TonWallet.wallet_address == wallet_address)
                )
                wallet_result = await session.execute(wallet_stmt)
                existing_wallet = wallet_result.scalar_one_or_none()
                
                if existing_wallet:
                    print(f"⚠️ Кошелек {wallet_address} уже привязан к пользователю {existing_wallet.user_id}")
                    return False
                
                # Создаем новый кошелек
                new_wallet = TonWallet(
                    user_id=user_id,
                    wallet_address=wallet_address,
                    network=network,
                    public_key=public_key
                )
                
                session.add(new_wallet)
                await session.commit()
                print(f"➕ Кошелек {wallet_address} успешно привязан к пользователю {user_id}")
                return True
                
        except Exception as e:
            print(f"❌ Ошибка при добавлении TON кошелька: {e}")
            
            # Проверяем, является ли это ошибкой кэша и не превышен ли лимит повторных попыток
            if ("InvalidCachedStatementError" in str(e) or "cached statement plan is invalid" in str(e)) and retry_count < 1:
                print("🔄 Обнаружена ошибка кэша SQLAlchemy, очищаем кэш...")
                try:
                    await self.db_manager.clear_cache_and_reconnect()
                    # Повторяем попытку после очистки кэша
                    return await self.add_ton_wallet(user_id, wallet_address, network, public_key, retry_count + 1)
                except Exception as retry_error:
                    print(f"❌ Ошибка при повторной попытке: {retry_error}")
                    return False
            
            return False

    async def get_user_ton_wallets(self, user_id: int) -> List[TonWallet]:
        """
        Получение всех TON кошельков пользователя
        :param user_id: ID пользователя в Telegram
        :return: Список кошельков или пустой список
        """
        try:
            async with self.async_session() as session:
                stmt = select(TonWallet).where(
                    (TonWallet.user_id == user_id) &
                    (TonWallet.is_active == True)
                )
                result = await session.execute(stmt)
                return list(result.scalars().all())
        except Exception as e:
            print(f"❌ Ошибка при получении TON кошельков: {e}")
            return []

    async def get_ton_wallet_by_address(self, wallet_address: str, retry_count: int = 0) -> Optional[TonWallet]:
        """
        Получение кошелька по адресу
        :param wallet_address: Адрес кошелька в сети TON
        :param retry_count: Счетчик повторных попыток (для предотвращения рекурсии)
        :return: Объект TonWallet или None
        """
        try:
            async with self.async_session() as session:
                stmt = select(TonWallet).where(
                    (TonWallet.wallet_address == wallet_address)
                )
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
        except Exception as e:
            print(f"❌ Ошибка при получении TON кошелька: {e}")
            
            # Проверяем, является ли это ошибкой кэша и не превышен ли лимит повторных попыток
            if ("InvalidCachedStatementError" in str(e) or "cached statement plan is invalid" in str(e)) and retry_count < 1:
                print("🔄 Обнаружена ошибка кэша SQLAlchemy, очищаем кэш...")
                try:
                    await self.db_manager.clear_cache_and_reconnect()
                    # Повторяем попытку после очистки кэша
                    return await self.get_ton_wallet_by_address(wallet_address, retry_count + 1)
                except Exception as retry_error:
                    print(f"❌ Ошибка при повторной попытке: {retry_error}")
                    return None
            
            return None

    async def deactivate_ton_wallet(self, wallet_address: str) -> bool:
        """
        Деактивация TON кошелька (мягкое удаление)
        :param wallet_address: Адрес кошелька в сети TON
        :return: True если успешно, False если ошибка
        """
        try:
            async with self.async_session() as session:
                stmt = select(TonWallet).where(
                    (TonWallet.wallet_address == wallet_address)
                )
                result = await session.execute(stmt)
                wallet = result.scalar_one_or_none()
                
                if wallet:
                    wallet.is_active = False
                    await session.commit()
                    print(f"➖ Кошелек {wallet_address} деактивирован")
                    return True
                else:
                    print(f"❌ Кошелек {wallet_address} не найден")
                    return False
        except Exception as e:
            print(f"❌ Ошибка при деактивации TON кошелька: {e}")
            return False

    async def reactivate_ton_wallet(self, wallet_address: str) -> bool:
        """
        Повторная активация TON кошелька
        :param wallet_address: Адрес кошелька в сети TON
        :return: True если успешно, False если ошибка
        """
        try:
            async with self.async_session() as session:
                stmt = select(TonWallet).where(
                    (TonWallet.wallet_address == wallet_address)
                )
                result = await session.execute(stmt)
                wallet = result.scalar_one_or_none()
                
                if wallet:
                    wallet.is_active = True
                    await session.commit()
                    print(f"🔄 Кошелек {wallet_address} реактивирован")
                    return True
                else:
                    print(f"❌ Кошелек {wallet_address} не найден")
                    return False
        except Exception as e:
            print(f"❌ Ошибка при реактивации TON кошелька: {e}")
            return False

    async def get_wallet_owner(self, wallet_address: str) -> Optional[int]:
        """
        Получение ID владельца кошелька
        :param wallet_address: Адрес кошелька в сети TON
        :return: ID пользователя или None
        """
        try:
            async with self.async_session() as session:
                stmt = select(TonWallet.user_id).where(
                    (TonWallet.wallet_address == wallet_address) &
                    (TonWallet.is_active == True)
                )
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
        except Exception as e:
            print(f"❌ Ошибка при получении владельца кошелька: {e}")
            return None

    async def is_wallet_active(self, wallet_address: str) -> bool:
        """
        Проверка активности кошелька
        :param wallet_address: Адрес кошелька в сети TON
        :return: True если кошелек активен, False в противном случае
        """
        try:
            async with self.async_session() as session:
                stmt = select(TonWallet.is_active).where(
                    TonWallet.wallet_address == wallet_address
                )
                result = await session.execute(stmt)
                is_active = result.scalar_one_or_none()
                return is_active is True
        except Exception as e:
            print(f"❌ Ошибка при проверке активности кошелька: {e}")
            return False 