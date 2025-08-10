#!/usr/bin/env python3
"""
Тест TonKeeper интеграции

Проверяет:
- Валидацию TON адресов
- Создание QR-кодов
- Генерацию deep links
- Создание сводок по выводам
"""

import asyncio
import sys
import os

# Добавляем путь к корневой директории
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ton_keeper_manager import tonkeeper_manager
from database.withdrawals import WithdrawalManager
from database.manager import DatabaseManager


async def test_tonkeeper_basic():
    """Тест базовой функциональности TonKeeper"""
    print("🧪 Тест базовой функциональности TonKeeper...")
    
    # Тест валидации адреса
    test_address = "EQD4FPq-PRDieyQKkizFTRtSDyucUIqrj0v_zXJmqaDp6_0t"
    is_valid = tonkeeper_manager.validate_ton_address(test_address)
    print(f"📍 Валидация адреса {test_address}: {'✅' if is_valid else '❌'}")
    
    # Тест неверного адреса
    invalid_address = "EQinvalid"
    is_invalid = tonkeeper_manager.validate_ton_address(invalid_address)
    print(f"📍 Валидация неверного адреса {invalid_address}: {'❌' if not is_invalid else '⚠️'}")
    
    # Тест информации о сети
    network_info = tonkeeper_manager.get_ton_network_info()
    print(f"🌐 Сеть: {network_info['network']}")
    print(f"🔗 Explorer: {network_info['explorer']}")
    
    # Тест оценки комиссии
    fee = tonkeeper_manager.estimate_transaction_fee()
    print(f"💰 Оценка комиссии: {fee} TON")
    
    print("✅ Базовый тест завершен\n")


async def test_qr_code_creation():
    """Тест создания QR-кодов"""
    print("🧪 Тест создания QR-кодов...")
    
    test_address = "EQD4FPq-PRDieyQKkizFTRtSDyucUIqrj0v_zXJmqaDp6_0t"
    
    # Тест создания QR-кода
    result = tonkeeper_manager.create_withdrawal_qr(
        amount_ton=0.5,
        destination_address=test_address,
        withdrawal_id=123,
        comment="Test withdrawal"
    )
    
    if result["success"]:
        print("✅ QR-код создан успешно")
        print(f"🔗 Deep link: {result['deep_link']}")
        print(f"📁 Файл QR: {result['qr_code']['filepath']}")
        
        # Проверяем инструкции
        instructions = result['instructions']
        print(f"📋 Инструкции: {len(instructions)} символов")
        
        # Проверяем данные для TonKeeper
        tonkeeper_data = result['tonkeeper_data']
        print(f"📊 Данные для TonKeeper: {tonkeeper_data}")
        
    else:
        print(f"❌ Ошибка создания QR: {result['error']}")
    
    print("✅ Тест QR-кодов завершен\n")


async def test_withdrawal_summary():
    """Тест создания сводок по выводам"""
    print("🧪 Тест создания сводок по выводам...")
    
    test_address = "EQD4FPq-PRDieyQKkizFTRtSDyucUIqrj0v_zXJmqaDp6_0t"
    
    # Тест сводки
    summary = tonkeeper_manager.create_withdrawal_summary(
        withdrawal_id=123,
        amount_ton=0.5,
        destination_address=test_address,
        fee_ton=0.01
    )
    
    print(f"📋 Сводка по выводу:\n{summary}")
    print("✅ Тест сводок завершен\n")


async def test_database_integration():
    """Тест интеграции с базой данных"""
    print("🧪 Тест интеграции с базой данных...")
    
    try:
        # Инициализируем базу данных
        db_manager = DatabaseManager()
        await db_manager.initialize_database()
        
        # Создаем менеджер выводов
        withdrawal_manager = WithdrawalManager(db_manager)
        
        # Тест валидации адреса через менеджер
        test_address = "EQD4FPq-PRDieyQKkizFTRtSDyucUIqrj0v_zXJmqaDp6_0t"
        is_valid = withdrawal_manager.tonkeeper.validate_ton_address(test_address)
        print(f"📍 Валидация через менеджер: {'✅' if is_valid else '❌'}")
        
        # Тест получения информации о сети
        network_info = await withdrawal_manager.get_ton_network_info()
        print(f"🌐 Информация о сети: {network_info}")
        
        # Тест оценки комиссии
        fee = withdrawal_manager.estimate_ton_fee()
        print(f"💰 Комиссия через менеджер: {fee} TON")
        
        print("✅ Тест интеграции с БД завершен\n")
        
    except Exception as e:
        print(f"❌ Ошибка теста интеграции с БД: {e}")
        print("⚠️ Возможно, база данных не инициализирована")


async def main():
    """Основная функция тестирования"""
    print("🚀 Запуск тестов TonKeeper интеграции\n")
    
    # Запускаем все тесты
    await test_tonkeeper_basic()
    await test_qr_code_creation()
    await test_withdrawal_summary()
    await test_database_integration()
    
    print("🎉 Все тесты завершены!")


if __name__ == "__main__":
    asyncio.run(main()) 