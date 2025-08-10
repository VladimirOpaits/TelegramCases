"""
Database models for Telegram Casino API

This module contains all SQLAlchemy model definitions for the database tables.
"""

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import BigInteger, String, DateTime, Integer, CheckConstraint, Float, ForeignKey, UniqueConstraint
from datetime import datetime
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


class WithdrawalRequest(Base):
    __tablename__ = "withdrawal_requests"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_fantics: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_ton: Mapped[float] = mapped_column(Float, nullable=False)
    fee_amount: Mapped[float] = mapped_column(Float, nullable=False)
    destination_address: Mapped[str] = mapped_column(String(67), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default='pending')  # pending, processing, completed, failed, cancelled
    transaction_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<WithdrawalRequest(id={self.id}, user_id={self.user_id}, amount_fantics={self.amount_fantics}, amount_ton={self.amount_ton}, status='{self.status}')>"


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