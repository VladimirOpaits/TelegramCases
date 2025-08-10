#!/usr/bin/env python3
"""
Пример использования TonKeeper интеграции

Демонстрирует:
- Создание запроса на вывод
- Генерацию QR-кода
- Создание инструкций для пользователя
"""

import asyncio
import sys
import os

# Добавляем путь к корневой директории
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ton_keeper_manager import tonkeeper_manager


async def example_withdrawal_process():
    """Пример процесса вывода TON через TonKeeper"""
    print("🚀 Пример процесса вывода TON через TonKeeper\n")
    
    # Данные для вывода
    user_id = 12345
    amount_fantics = 1000  # 1000 фантиков
    amount_ton = 1.0       # 1 TON
    fee_amount = 0.01      # Комиссия 0.01 TON
    destination_address = "EQD4FPq-PRDieyQKkizFTRtSDyucUIqrj0v_zXJmqaDp6_0t"
    withdrawal_id = 789
    
    print(f"👤 Пользователь ID: {user_id}")
    print(f"💰 Сумма: {amount_fantics} фантиков = {amount_ton} TON")
    print(f"💸 Комиссия: {fee_amount} TON")
    print(f"📍 Адрес получателя: {destination_address}")
    print(f"🆔 ID вывода: {withdrawal_id}\n")
    
    # Шаг 1: Валидация TON адреса
    print("🔍 Шаг 1: Валидация TON адреса...")
    if tonkeeper_manager.validate_ton_address(destination_address):
        print("✅ TON адрес валиден")
    else:
        print("❌ TON адрес невалиден")
        return
    
    # Шаг 2: Создание QR-кода для вывода
    print("\n📱 Шаг 2: Создание QR-кода для вывода...")
    qr_result = tonkeeper_manager.create_withdrawal_qr(
        amount_ton=amount_ton,
        destination_address=destination_address,
        withdrawal_id=withdrawal_id,
        comment="Casino withdrawal"
    )
    
    if qr_result["success"]:
        print("✅ QR-код создан успешно")
        print(f"🔗 Deep link: {qr_result['deep_link']}")
        print(f"📁 Файл QR: {qr_result['qr_code']['filepath']}")
        
        # Шаг 3: Создание сводки по выводу
        print("\n📋 Шаг 3: Создание сводки по выводу...")
        summary = tonkeeper_manager.create_withdrawal_summary(
            withdrawal_id=withdrawal_id,
            amount_ton=amount_ton,
            destination_address=destination_address,
            fee_ton=fee_amount
        )
        
        print("📊 Сводка по выводу:")
        print(summary)
        
        # Шаг 4: Инструкции для пользователя
        print("\n📱 Шаг 4: Инструкции для пользователя...")
        instructions = qr_result['instructions']
        print(instructions)
        
        # Шаг 5: Информация о сети
        print("\n🌐 Шаг 5: Информация о сети TON...")
        network_info = tonkeeper_manager.get_ton_network_info()
        print(f"Сеть: {network_info['network']}")
        print(f"Название: {network_info['name']}")
        print(f"Валюта: {network_info['currency']}")
        print(f"Explorer: {network_info['explorer']}")
        
        print("\n🎉 Процесс вывода настроен успешно!")
        print("👆 Пользователь может использовать QR-код или deep link для завершения вывода через TonKeeper")
        
    else:
        print(f"❌ Ошибка создания QR-кода: {qr_result['error']}")


async def example_multiple_withdrawals():
    """Пример обработки нескольких выводов"""
    print("\n" + "="*60)
    print("🔄 Пример обработки нескольких выводов")
    print("="*60)
    
    withdrawals = [
        {"id": 1, "amount": 0.5, "address": "EQD4FPq-PRDieyQKkizFTRtSDyucUIqrj0v_zXJmqaDp6_0t", "comment": "Small withdrawal"},
        {"id": 2, "amount": 2.0, "address": "EQD4FPq-PRDieyQKkizFTRtSDyucUIqrj0v_zXJmqaDp6_0t", "comment": "Large withdrawal"},
        {"id": 3, "amount": 0.1, "address": "EQD4FPq-PRDieyQKkizFTRtSDyucUIqrj0v_zXJmqaDp6_0t", "comment": "Test withdrawal"}
    ]
    
    for withdrawal in withdrawals:
        print(f"\n📤 Обработка вывода #{withdrawal['id']}")
        print(f"💰 Сумма: {withdrawal['amount']} TON")
        
        # Создаем QR-код
        qr_result = tonkeeper_manager.create_withdrawal_qr(
            amount_ton=withdrawal['amount'],
            destination_address=withdrawal['address'],
            withdrawal_id=withdrawal['id'],
            comment=withdrawal['comment']
        )
        
        if qr_result["success"]:
            print(f"✅ QR-код создан: {qr_result['qr_code']['filename']}")
            print(f"🔗 Deep link: {qr_result['deep_link'][:50]}...")
        else:
            print(f"❌ Ошибка: {qr_result['error']}")


def example_manual_tonkeeper_usage():
    """Пример ручного использования TonKeeper (без QR-кода)"""
    print("\n" + "="*60)
    print("📱 Пример ручного использования TonKeeper")
    print("="*60)
    
    amount_ton = 1.5
    destination_address = "EQD4FPq-PRDieyQKkizFTRtSDyucUIqrj0v_zXJmqaDp6_0t"
    
    print(f"💰 Сумма к выводу: {amount_ton} TON")
    print(f"📍 Адрес получателя: {destination_address}")
    
    # Создаем deep link для ручного ввода
    deep_link = tonkeeper_manager._create_tonkeeper_deep_link(
        amount_ton=amount_ton,
        destination_address=destination_address,
        comment="Manual withdrawal"
    )
    
    print(f"\n🔗 Deep link для TonKeeper:")
    print(deep_link)
    
    print(f"\n📋 Инструкции для пользователя:")
    print("1. Откройте TonKeeper")
    print("2. Нажмите 'Отправить'")
    print("3. Введите адрес получателя вручную")
    print("4. Введите сумму: 1.5 TON")
    print("5. Добавьте комментарий: Manual withdrawal")
    print("6. Подтвердите транзакцию")


async def main():
    """Основная функция"""
    print("🎰 Примеры использования TonKeeper интеграции\n")
    
    # Основной пример вывода
    await example_withdrawal_process()
    
    # Пример множественных выводов
    await example_multiple_withdrawals()
    
    # Пример ручного использования
    example_manual_tonkeeper_usage()
    
    print("\n" + "="*60)
    print("🎉 Все примеры завершены!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main()) 