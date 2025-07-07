import os
from typing import Final
from dotenv import load_dotenv

load_dotenv()

def get_required_env(name: str) -> str:
    """Получает переменную окружения и гарантирует её наличие."""
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Required environment variable {name} is missing or empty")
    return value

BOT_TOKEN: Final[str] = get_required_env("BOT_TOKEN")
DATABASE_URL: Final[str] = get_required_env("DATABASE_URL")
WEB_APP_URL: Final[str] = get_required_env("WEB_APP_URL")

__all__ = ['BOT_TOKEN', 'DATABASE_URL', 'WEB_APP_URL']