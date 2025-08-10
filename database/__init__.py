from .models import Base, User, TonWallet, Case, Present, CasePresent, PendingPayment, SuccessfulPayment, WithdrawalRequest
from .manager import DatabaseManager
from .users import UserManager
from .wallets import WalletManager
from .payments import PaymentManager
from .withdrawals import WithdrawalManager
from .cases import CaseManager
from typing import Optional


class DatabaseFacade:
    """
    Фасадный класс для обеспечения совместимости с существующим кодом.
    Объединяет все модули в единый интерфейс.
    """
    
    def __init__(self, database_url: str):
        self.db_manager = DatabaseManager(database_url)
        self.user_manager = UserManager(self.db_manager)
        self.wallet_manager = WalletManager(self.db_manager)
        self.payment_manager = PaymentManager(self.db_manager)
        self.withdrawal_manager = WithdrawalManager(self.db_manager)
        self.case_manager = CaseManager(self.db_manager)

        self.async_session = self.db_manager.async_session
        self.engine = self.db_manager.engine

    
    async def init_db(self):
        """Инициализация базы данных"""
        await self.db_manager.init_db()
        await self.case_manager.initialize()
    
    async def close(self):
        """Закрытие соединения"""
        await self.db_manager.close()
    
    async def clear_cache_and_reconnect(self):
        """Очистка кэша и переподключение"""
        await self.db_manager.clear_cache_and_reconnect()
    
    # Делегирование методов пользователей
    async def add_user(self, user_id: int, username: Optional[str] = None) -> bool:
        return await self.user_manager.add_user(user_id, username)
    
    async def get_user(self, user_id: int):
        return await self.user_manager.get_user(user_id)
    
    async def get_all_users(self):
        return await self.user_manager.get_all_users()
    
    async def get_users_count(self) -> int:
        return await self.user_manager.get_users_count()
    
    # Делегирование методов фантиков
    async def get_fantics(self, user_id: int):
        return await self.user_manager.get_fantics(user_id)
    
    async def add_fantics(self, user_id: int, amount: int) -> bool:
        return await self.user_manager.add_fantics(user_id, amount)
    
    async def subtract_fantics(self, user_id: int, amount: int) -> bool:
        return await self.user_manager.subtract_fantics(user_id, amount)
    
    async def set_fantics(self, user_id: int, amount: int) -> bool:
        return await self.user_manager.set_fantics(user_id, amount)
    
    # Делегирование атомарных операций
    async def atomic_case_transaction(self, user_id: int, case_cost: int, prize_amount: int):
        return await self.user_manager.atomic_case_transaction(user_id, case_cost, prize_amount)
    
    async def atomic_subtract_fantics(self, user_id: int, amount: int):
        return await self.user_manager.atomic_subtract_fantics(user_id, amount)
    
    async def atomic_add_fantics(self, user_id: int, amount: int):
        return await self.user_manager.atomic_add_fantics(user_id, amount)
    
    # Делегирование методов кошельков
    async def add_ton_wallet(self, user_id: int, wallet_address: str, network=None, public_key=None, retry_count=0):
        return await self.wallet_manager.add_ton_wallet(user_id, wallet_address, network, public_key, retry_count)
    
    async def get_user_ton_wallets(self, user_id: int):
        return await self.wallet_manager.get_user_ton_wallets(user_id)
    
    async def get_ton_wallet_by_address(self, wallet_address: str, retry_count=0):
        return await self.wallet_manager.get_ton_wallet_by_address(wallet_address, retry_count)
    
    async def deactivate_ton_wallet(self, wallet_address: str) -> bool:
        return await self.wallet_manager.deactivate_ton_wallet(wallet_address)
    
    async def reactivate_ton_wallet(self, wallet_address: str) -> bool:
        return await self.wallet_manager.reactivate_ton_wallet(wallet_address)
    
    async def get_wallet_owner(self, wallet_address: str):
        return await self.wallet_manager.get_wallet_owner(wallet_address)
    
    async def is_wallet_active(self, wallet_address: str) -> bool:
        return await self.wallet_manager.is_wallet_active(wallet_address)
    
    # Делегирование методов платежей
    async def create_pending_payment(self, payment_id: str, user_id: int, amount_fantics: int, 
                                   amount_ton: float, payment_method: str, destination_address: str, 
                                   comment: str, expires_in_minutes: int = 30):
        return await self.payment_manager.create_pending_payment(
            payment_id, user_id, amount_fantics, amount_ton, payment_method, 
            destination_address, comment, expires_in_minutes
        )
    
    async def get_pending_payment(self, payment_id: str):
        return await self.payment_manager.get_pending_payment(payment_id)
    
    async def update_payment_status(self, payment_id: str, status: str, transaction_hash=None):
        return await self.payment_manager.update_payment_status(payment_id, status, transaction_hash)
    
    async def add_successful_payment(self, user_id: int, payment_method: str, amount_fantics: int,
                                   amount_paid: float, sender_wallet=None, transaction_hash=None, payment_id=None):
        return await self.payment_manager.add_successful_payment(
            user_id, payment_method, amount_fantics, amount_paid, sender_wallet, transaction_hash, payment_id
        )
    
    # Делегирование методов выводов
    async def create_withdrawal_request(self, user_id: int, amount_fantics: int, amount_ton: float,
                                      fee_amount: float, destination_address: str):
        return await self.withdrawal_manager.create_withdrawal_request(
            user_id, amount_fantics, amount_ton, fee_amount, destination_address
        )
    
    async def get_user_withdrawal_requests(self, user_id: int, limit: int = 50):
        return await self.withdrawal_manager.get_user_withdrawal_requests(user_id, limit)
    
    async def get_pending_withdrawals(self, limit: int = 50):
        return await self.withdrawal_manager.get_pending_withdrawals(limit)
    
    async def update_withdrawal_status(self, request_id: int, status: str, transaction_hash=None, error_message=None):
        return await self.withdrawal_manager.update_withdrawal_status(request_id, status, transaction_hash, error_message)
    
    async def get_withdrawal_statistics(self):
        return await self.withdrawal_manager.get_withdrawal_statistics()


__all__ = [
    'Base',
    'User', 
    'TonWallet',
    'Case',
    'Present',
    'CasePresent',
    'PendingPayment',
    'SuccessfulPayment',
    'WithdrawalRequest',
    
    'DatabaseManager',
    'UserManager',
    'WalletManager', 
    'PaymentManager',
    'WithdrawalManager',
    'CaseManager',
    
    'DatabaseFacade'
] 