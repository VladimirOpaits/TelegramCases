from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from .models import Base


class DatabaseManager:
    """Основной менеджер для работы с базой данных"""
    
    def __init__(self, database_url: str):
        """Инициализация менеджера базы данных"""
        if "postgresql" in database_url:
            self.engine = create_async_engine(
                database_url, 
                echo=False, 
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=3600,
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
            await self.engine.dispose()
            print("🔄 Кэш SQLAlchemy очищен")

            if "postgresql" in self.engine.url:
                self.engine = create_async_engine(
                    self.engine.url, 
                    echo=False, 
                    pool_size=10,
                    max_overflow=20,
                    pool_pre_ping=True,
                    pool_recycle=3600,
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

    async def close(self):
        """Закрытие соединения с базой данных"""
        await self.engine.dispose()
        print("🔌 Соединение с базой данных закрыто") 