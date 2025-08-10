"""
TonKeeper Integration Manager

Простая интеграция с TonKeeper для:
- Создания QR-кодов для вывода TON
- Генерации deep links для TonKeeper
- Валидации TON адресов
"""

import qrcode
import json
from typing import Optional, Dict, Any
from datetime import datetime
import os


class TonKeeperManager:
    """Менеджер для интеграции с TonKeeper"""
    
    def __init__(self):
        self.network = "mainnet"  # или testnet для тестирования
    
    def create_withdrawal_qr(
        self, 
        amount_ton: float, 
        destination_address: str, 
        withdrawal_id: int,
        comment: str = ""
    ) -> Dict[str, Any]:
        """
        Создание QR-кода для вывода TON через TonKeeper
        
        Args:
            amount_ton: Сумма в TON
            destination_address: Адрес получателя
            withdrawal_id: ID запроса на вывод
            comment: Комментарий к транзакции
            
        Returns:
            Dict с данными для QR-кода и deep link
        """
        try:
            # Формируем комментарий
            full_comment = f"Withdrawal #{withdrawal_id}"
            if comment:
                full_comment += f": {comment}"
            
            # Создаем deep link для TonKeeper
            deep_link = self._create_tonkeeper_deep_link(
                amount_ton, 
                destination_address, 
                full_comment
            )
            
            # Создаем QR-код
            qr_data = self._create_qr_code(deep_link)
            
            # Данные для TonKeeper
            tonkeeper_data = {
                "amount": amount_ton,
                "destination": destination_address,
                "comment": full_comment,
                "network": self.network,
                "withdrawal_id": withdrawal_id
            }
            
            return {
                "success": True,
                "qr_code": qr_data,
                "deep_link": deep_link,
                "tonkeeper_data": tonkeeper_data,
                "instructions": self._get_instructions(amount_ton, destination_address)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Ошибка создания QR-кода: {str(e)}"
            }
    
    def _create_tonkeeper_deep_link(
        self, 
        amount_ton: float, 
        destination_address: str, 
        comment: str
    ) -> str:
        """Создание deep link для TonKeeper"""
        # Формат: ton://transfer/{address}?amount={amount}&text={comment}
        deep_link = f"ton://transfer/{destination_address}"
        
        # Добавляем параметры
        params = []
        if amount_ton > 0:
            # Конвертируем в наноТОН (1 TON = 1,000,000,000 наноТОН)
            amount_nano = int(amount_ton * 1_000_000_000)
            params.append(f"amount={amount_nano}")
        
        if comment:
            params.append(f"text={comment}")
        
        if params:
            deep_link += "?" + "&".join(params)
        
        return deep_link
    
    def _create_qr_code(self, data: str) -> Dict[str, Any]:
        """Создание QR-кода"""
        try:
            # Создаем QR-код
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(data)
            qr.make(fit=True)
            
            # Создаем изображение
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Сохраняем во временный файл
            filename = f"withdrawal_qr_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            filepath = os.path.join("temp", filename)
            
            # Создаем папку temp если её нет
            os.makedirs("temp", exist_ok=True)
            
            img.save(filepath)
            
            return {
                "filepath": filepath,
                "filename": filename,
                "data": data
            }
            
        except Exception as e:
            return {
                "filepath": None,
                "filename": None,
                "data": data,
                "error": str(e)
            }
    
    def _get_instructions(self, amount_ton: float, destination_address: str) -> str:
        """Получение инструкций для пользователя"""
        return f"""
📱 Для вывода {amount_ton} TON на адрес {destination_address}:

1️⃣ Откройте TonKeeper на вашем телефоне
2️⃣ Нажмите на кнопку "Отправить" или "Send"
3️⃣ Отсканируйте QR-код или скопируйте адрес
4️⃣ Проверьте сумму и адрес получателя
5️⃣ Подтвердите транзакцию
6️⃣ Дождитесь подтверждения в блокчейне

⚠️ Внимание: Транзакции в TON необратимы!
🔗 Адрес получателя: {destination_address}
💰 Сумма: {amount_ton} TON
        """.strip()
    
    def validate_ton_address(self, address: str) -> bool:
        """Валидация TON адреса"""
        try:
            # Базовая проверка формата TON адреса
            if not address.startswith('EQ') or len(address) != 48:
                return False
            
            # Проверка на валидные символы (base64)
            valid_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-')
            return all(char in valid_chars for char in address)
            
        except Exception:
            return False
    
    def get_ton_network_info(self) -> Dict[str, Any]:
        """Получение информации о сети TON"""
        return {
            "network": self.network,
            "name": "The Open Network",
            "currency": "TON",
            "decimals": 9,
            "explorer": "https://tonscan.org" if self.network == "mainnet" else "https://testnet.tonscan.org",
            "faucet": None if self.network == "mainnet" else "https://t.me/testgiver_ton_bot"
        }
    
    def estimate_transaction_fee(self) -> float:
        """Оценка комиссии за транзакцию TON"""
        # Базовая комиссия TON (обычно 0.01-0.05 TON)
        return 0.01
    
    def create_withdrawal_summary(
        self, 
        withdrawal_id: int, 
        amount_ton: float, 
        destination_address: str,
        fee_ton: float = None
    ) -> str:
        """Создание сводки по выводу для пользователя"""
        if fee_ton is None:
            fee_ton = self.estimate_transaction_fee()
        
        total_cost = amount_ton + fee_ton
        
        summary = f"""
💳 Сводка по выводу #{withdrawal_id}

💰 Сумма к выводу: {amount_ton} TON
💸 Комиссия сети: {fee_ton} TON
💵 Итого списано: {total_cost} TON

📍 Адрес получателя: {destination_address}
🌐 Сеть: {self.network.upper()}

📱 Для завершения вывода используйте TonKeeper
⏱️ Время обработки: 1-5 секунд
        """.strip()
        
        return summary


# Создание глобального экземпляра
tonkeeper_manager = TonKeeperManager()


def test_tonkeeper_integration():
    """Тестирование интеграции с TonKeeper"""
    print("🧪 Тестирование TonKeeper интеграции...")
    
    # Тест валидации адреса
    test_address = "EQD4FPq-PRDieyQKkizFTRtSDyucUIqrj0v_zXJmqaDp6_0t"
    is_valid = tonkeeper_manager.validate_ton_address(test_address)
    print(f"📍 Валидация адреса {test_address}: {'✅' if is_valid else '❌'}")
    
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
    else:
        print(f"❌ Ошибка создания QR: {result['error']}")
    
    # Тест сводки
    summary = tonkeeper_manager.create_withdrawal_summary(123, 0.5, test_address)
    print(f"\n📋 Сводка по выводу:\n{summary}")
    
    print("\n✅ Тестирование завершено")


if __name__ == "__main__":
    test_tonkeeper_integration() 