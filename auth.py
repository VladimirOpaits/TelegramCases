import hmac
import hashlib
import time
from urllib.parse import parse_qs
from fastapi import HTTPException
import json

class TelegramAuth:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
    
    def validate_init_data(self, init_data: str) -> dict:
        """Валидация Telegram WebApp initData"""
        try:
            parsed = parse_qs(init_data)
            hash_str = parsed.get('hash', [None])[0]
            
            if not hash_str:
                raise ValueError("Missing hash")
            
            data_check = []
            for key in sorted(parsed.keys()):
                if key != 'hash':
                    data_check.append(f"{key}={parsed[key][0]}")
            
            secret_key = hmac.new(
                b"WebAppData",
                self.bot_token.encode(),
                hashlib.sha256
            ).digest()
            
            calculated_hash = hmac.new(
                secret_key,
                '\n'.join(data_check).encode(),
                hashlib.sha256
            ).hexdigest()
            
            if calculated_hash != hash_str:
                raise ValueError("Invalid hash")
            
            if time.time() - int(parsed['auth_date'][0]) > 86400:
                raise ValueError("Data expired")
            
            return json.loads(parsed['user'][0])
            
        except Exception as e:
            raise HTTPException(status_code=401, detail=str(e))
