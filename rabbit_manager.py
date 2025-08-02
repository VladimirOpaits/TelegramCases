import logging
from typing import Optional, Dict, Any
from faststream.rabbit.fastapi import RabbitRouter
from config import RABBITMQ_URL
from database import DatabaseManager

class RabbitManager:
    """Менеджер для работы с RabbitMQ"""
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.router: Optional[RabbitRouter] = None
        self.is_available: bool = False
        self.is_connected: bool = False
        self.db_manager = db_manager
        
    def initialize(self) -> bool:
        """Инициализация подключения к RabbitMQ"""
        try:
            if not RABBITMQ_URL:
                logging.info("📝 RabbitMQ отключен (нет URL в конфигурации)")
                return False
                
            print("🐰 Подключение к RabbitMQ:", RABBITMQ_URL.split('@')[1] if '@' in RABBITMQ_URL else RABBITMQ_URL)
            
            self.router = RabbitRouter(RABBITMQ_URL)
            self.is_available = True
            print("✅ RabbitMQ инициализирован")
            return True
            
        except ImportError:
            print("⚠️ FastStream не установлен, RabbitMQ отключен")
            return False
        except Exception as e:
            print(f"❌ Ошибка инициализации RabbitMQ: {e}")
            return False
    
    async def connect(self) -> bool:
        """Подключение к брокеру"""
        if not self.is_available or not self.router:
            return False
            
        try:
            await self.router.broker.connect()
            self.is_connected = True
            print("🐰 RabbitMQ брокер подключен")
            return True
        except Exception as e:
            print(f"❌ Ошибка подключения к RabbitMQ брокеру: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Отключение от брокера"""
        if self.is_connected and self.router:
            try:
                await self.router.broker.close()
                self.is_connected = False
                print("🐰 RabbitMQ брокер отключен")
            except Exception as e:
                print(f"❌ Ошибка отключения от RabbitMQ: {e}")
    
    async def send_stars_payment_request(self, user_id: int, amount: int) -> bool:
        """Отправка запроса на оплату звездочками в телеграм бота"""
        if not self.is_connected or not self.router:
            print("⚠️ RabbitMQ не подключен, нельзя отправить запрос на звездочки")
            return False
            
        try:
            message = {
                "user_id": user_id,
                "amount": amount,
                "action": "request_stars_payment",
                "payment_method": "telegram_stars",
                "reason": f"fantics_topup_stars_{amount}"
            }
            
            await self.router.broker.publish(
                message,
                queue="telegram_payments"
            )
            
            print(f"🌟 Запрос на оплату звездочками отправлен: пользователь {user_id}, сумма {amount} фантиков")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка отправки запроса на звездочки: {e}")
            return False
    
    async def send_fantics_transaction(self, user_id: int, amount: int, action: str, reason: str, **kwargs) -> bool:
        """Отправка общей транзакции с фантиками"""
        if not self.is_connected or not self.router:
            print("⚠️ RabbitMQ не подключен, нельзя отправить транзакцию")
            return False
            
        try:
            message = {
                "user_id": user_id,
                "amount": amount,
                "action": action,
                "reason": reason,
                **kwargs
            }
            
            await self.router.broker.publish(
                message,
                queue="transactions"
            )
            
            print(f"🐰 Транзакция отправлена: {action} {amount} фантиков для пользователя {user_id}")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка отправки транзакции: {e}")
            return False
    
    async def send_case_notification(self, user_id: int, case_id: int, case_cost: int, prize_amount: int) -> bool:
        """Отправка уведомления об открытии кейса"""
        if not self.is_connected or not self.router:
            return False
            
        try:
            message = {
                "user_id": user_id,
                "amount": case_cost,
                "action": "case_opened",
                "case_id": case_id,
                "prize": prize_amount,
                "reason": f"case_opened_{case_id}_prize_{prize_amount}"
            }
            
            await self.router.broker.publish(
                message,
                queue="transactions"
            )
            
            print(f"🎰 Уведомление о кейсе отправлено в RabbitMQ для пользователя {user_id}")
            return True
            
        except Exception as e:
            print(f"⚠️ Ошибка RabbitMQ (не критично): {e}")
            return False
    
    def get_router(self) -> Optional[RabbitRouter]:
        """Получение роутера для добавления в FastAPI"""
        return self.router if self.is_available else None
    
    @property
    def is_ready(self) -> bool:
        """Проверка готовности RabbitMQ к работе"""
        return self.is_available and self.is_connected

    # =========================================================================
    # ОБРАБОТЧИКИ СООБЩЕНИЙ
    # =========================================================================

    def setup_message_handlers(self) -> None:
        """Настройка обработчиков сообщений"""
        if not self.router:
            return
            
        @self.router.subscriber("transactions")
        async def handle_transaction(message: dict):
            """Обработчик транзакций фантиков"""
            try:
                user_id = message["user_id"]
                amount = message["amount"]
                action = message["action"]
                reason = message.get("reason", "unknown")

                print(f"🐰 Обработка транзакции: {action} {amount} фантиков для пользователя {user_id}, причина: {reason}")

                if not self.db_manager:
                    print("❌ DatabaseManager не доступен для обработки транзакции")
                    return

                if action == "add":
                    success = await self.db_manager.add_fantics(user_id, amount)
                    if success:
                        print(f"✅ Добавлено {amount} фантиков пользователю {user_id}")
                    else:
                        print(f"❌ Ошибка добавления {amount} фантиков пользователю {user_id}")
                elif action == "spend":
                    success = await self.db_manager.subtract_fantics(user_id, amount)
                    if success:
                        print(f"✅ Списано {amount} фантиков у пользователя {user_id}")
                    else:
                        print(f"❌ Ошибка списания {amount} фантиков у пользователя {user_id}")

            except Exception as e:
                print(f"❌ Ошибка обработки транзакции: {e}")

        @self.router.subscriber("telegram_payments")
        async def handle_telegram_payment(message: dict):
            """Обработчик платежей через телеграм (звездочки)"""
            try:
                user_id = message["user_id"]
                amount = message["amount"]
                action = message["action"]
                payment_method = message.get("payment_method", "unknown")
                
                print(f"🌟 Обработка платежа: {action} на {amount} фантиков для пользователя {user_id} через {payment_method}")
                
                if action == "request_stars_payment":
                    # Здесь будет логика взаимодействия с телеграм ботом для оплаты звездочками
                    print(f"📤 Отправка запроса на оплату звездочками для пользователя {user_id}, сумма: {amount} фантиков")
                    # TODO: Реализовать отправку сообщения в телеграм бота
                    
            except Exception as e:
                print(f"❌ Ошибка обработки платежа через телеграм: {e}")

    async def setup_handlers_and_include_router(self, app) -> None:
        """Настройка обработчиков и подключение роутера к приложению"""
        if not self.router:
            return
            
        # Настраиваем обработчики сообщений
        self.setup_message_handlers()
        
        # Подключаем роутер к приложению
        app.include_router(self.router)
        print("🐰 RabbitMQ обработчики настроены и подключены к приложению")