import hmac
import hashlib
import time
from urllib.parse import parse_qs
from fastapi import HTTPException, Header
from typing import Optional, Dict

class TelegramAuth:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
    
    def validate_init_data(self, init_data: str) -> Dict:
        """Валидация и парсинг initData от Telegram"""
        try:
            parsed_data = parse_qs(init_data)
            
            received_hash = parsed_data.get('hash', [None])[0]
            if not received_hash:
                raise ValueError("Hash not found")
            
            data_check_arr = []
            for key, values in parsed_data.items():
                if key != 'hash':
                    data_check_arr.append(f"{key}={values[0]}")
            
            data_check_arr.sort()
            data_check_string = '\n'.join(data_check_arr)
            
            secret_key = hmac.new(
                b"WebAppData",
                self.bot_token.encode(),
                hashlib.sha256
            ).digest()
            
            calculated_hash = hmac.new(
                secret_key,
                data_check_string.encode(),
                hashlib.sha256
            ).hexdigest()
            
            if calculated_hash != received_hash:
                raise ValueError("Invalid hash")
            
            auth_date = int(parsed_data.get('auth_date', [0])[0])
            if time.time() - auth_date > 86400: 
                raise ValueError("Data is too old")
            
            import json
            user_data = json.loads(parsed_data.get('user', ['{}'])[0])
            
            return {
                'user_id': user_data.get('id'),
                'username': user_data.get('username'),
                'first_name': user_data.get('first_name'),
                'last_name': user_data.get('last_name'),
                'auth_date': auth_date
            }
            
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Invalid authorization: {str(e)}")