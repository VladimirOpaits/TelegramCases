from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import BigInteger, String, DateTime, select, func, Integer, CheckConstraint, Float, ForeignKey, UniqueConstraint
from datetime import datetime, timedelta
import os
from typing import Optional, List


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=True)
    registration_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    fantics: Mapped[int] = mapped_column(Integer,
                                       nullable=False,
                                       default=0,
                                       server_default="0")

    __table_args__ = (
        CheckConstraint('fantics >= 0', name='check_fantics_positive'),
    )

    ton_wallets: Mapped[List["TonWallet"]] = relationship(
        back_populates="user", 
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<User(id={self.id}, user_id={self.user_id}, username='{self.username}', fantics='{self.fantics}')>"


class TonWallet(Base):
    __tablename__ = "ton_wallets"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"))
    wallet_address: Mapped[str] = mapped_column(String(67), nullable=False, unique=True)
    network: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # -239, 0, etc.
    public_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # Public key в hex
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    is_active: Mapped[bool] = mapped_column(default=True)
    
    user: Mapped["User"] = relationship(back_populates="ton_wallets")

    __table_args__ = (
        UniqueConstraint('user_id', 'wallet_address', name='_user_wallet_uc'),
    )

    def __repr__(self):
        return f"<TonWallet(id={self.id}, user_id={self.user_id}, address='{self.wallet_address}', network='{self.network}')>"


class Case(Base):
    __tablename__ = "cases"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    cost: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    case_presents: Mapped[List["CasePresent"]] = relationship(
        back_populates="case", 
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Case(id={self.id}, name='{self.name}', cost={self.cost})>"


class Present(Base):
    __tablename__ = "presents"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cost: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    
    case_presents: Mapped[List["CasePresent"]] = relationship(back_populates="present")

    def __repr__(self):
        return f"<Present(id={self.id}, cost={self.cost})>"


class PendingPayment(Base):
    __tablename__ = "pending_payments"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    payment_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_fantics: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_ton: Mapped[float] = mapped_column(Float, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(50), nullable=False)  # 'ton' или 'stars'
    status: Mapped[str] = mapped_column(String(50), nullable=False, default='pending')  # pending, confirmed, failed, expired
    transaction_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    destination_address: Mapped[str] = mapped_column(String(255), nullable=False)
    comment: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    
    def __repr__(self):
        return f"<PendingPayment(id={self.id}, payment_id='{self.payment_id}', user_id={self.user_id}, status='{self.status}')>"


class SuccessfulPayment(Base):
    __tablename__ = "successful_payments"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(50), nullable=False)  # 'ton' или 'stars'
    amount_fantics: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_paid: Mapped[float] = mapped_column(Float, nullable=False)  # сумма в TON или звездочках
    sender_wallet: Mapped[Optional[str]] = mapped_column(String(67), nullable=True)  # адрес кошелька отправителя (для TON)
    transaction_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # хэш транзакции (для TON)
    payment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # ID платежа из pending_payments
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    
    def __repr__(self):
        return f"<SuccessfulPayment(id={self.id}, user_id={self.user_id}, method='{self.payment_method}', amount_fantics={self.amount_fantics}, amount_paid={self.amount_paid})>"


class CasePresent(Base):
    __tablename__ = "case_presents"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"))
    present_id: Mapped[int] = mapped_column(ForeignKey("presents.id"))
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    
    case: Mapped["Case"] = relationship(back_populates="case_presents")
    present: Mapped["Present"] = relationship(back_populates="case_presents")
    
    __table_args__ = (
        UniqueConstraint('case_id', 'present_id', name='_case_present_uc'),
        CheckConstraint('probability > 0 AND probability <= 100', name='check_probability_range'),
    )

    def __repr__(self):
        return f"<CasePresent(case_id={self.case_id}, present_id={self.present_id}, probability={self.probability})>"





class DatabaseManager:
    def __init__(self, database_url: str):
        if "postgresql" in database_url:
            self.engine = create_async_engine(
                database_url, 
                echo=False, 
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=3600,
                # Отключаем логирование SQL запросов
                logging_name=None
            )
        else:
            self.engine = create_async_engine(database_url, echo=True)
            
        self.async_session = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

    async def init_db(self):
        """Инициализация базы данных и создание таблиц"""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            print("✅ База данных инициализирована")
        except Exception as e:
            print(f"❌ Ошибка инициализации БД: {e}")
            raise

    async def clear_cache_and_reconnect(self):
        """Принудительная очистка кэша и пересоздание подключения"""
        try:
            # Закрываем все соединения
            await self.engine.dispose()
            print("🔄 Кэш SQLAlchemy очищен")
            
            # Пересоздаем engine
            if "postgresql" in self.engine.url:
                self.engine = create_async_engine(
                    self.engine.url, 
                    echo=False, 
                    pool_size=10,
                    max_overflow=20,
                    pool_pre_ping=True,
                    pool_recycle=3600,
                    # Отключаем логирование SQL запросов
                    logging_name=None
                )
            else:
                self.engine = create_async_engine(self.engine.url, echo=True)
                
            self.async_session = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            print("✅ Подключение к базе данных пересоздано")
        except Exception as e:
            print(f"❌ Ошибка при очистке кэша: {e}")
            raise

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

    async def get_all_users(self) -> list[User]:
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

    async def atomic_case_transaction(self, user_id: int, case_cost: int, prize_amount: int) -> tuple[bool, str, int]:
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

    async def atomic_subtract_fantics(self, user_id: int, amount: int) -> tuple[bool, str, int]:
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

    async def atomic_add_fantics(self, user_id: int, amount: int) -> tuple[bool, str, int]:
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
        
    # ========== МЕТОДЫ ДЛЯ РАБОТЫ С TON КОШЕЛЬКАМИ ==========
    async def add_ton_wallet(self, user_id: int, wallet_address: str, network: Optional[str] = None, public_key: Optional[str] = None, retry_count: int = 0) -> bool:
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
                user = await self.get_user(user_id)
                if not user:
                    print(f"❌ Пользователь {user_id} не найден")
                    return False
                
                # Проверяем, не привязан ли уже этот кошелек
                stmt = select(TonWallet).where(
                    (TonWallet.wallet_address == wallet_address)
                )
                result = await session.execute(stmt)
                existing_wallet = result.scalar_one_or_none()
                
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
                    await self.clear_cache_and_reconnect()
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
                    await self.clear_cache_and_reconnect()
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
    
    async def get_pending_payment(self, payment_id: str) -> Optional['PendingPayment']:
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
    
    async def get_pending_payments_for_verification(self, limit: int = 50) -> List['PendingPayment']:
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

    async def close(self):
        """Закрытие соединения с базой данных"""
        await self.engine.dispose()
        print("🔌 Соединение с базой данных закрыто")


