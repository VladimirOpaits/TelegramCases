import os
from dotenv import load_dotenv

load_dotenv()

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///casino.db")

# Development mode - только если явно указано
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"

# CORS settings - для продакшена разрешаем GitHub Pages
CORS_ORIGINS = [
    "https://mtkache09.github.io",
    "https://mtkache09.github.io/*",
    "http://localhost:3000",  # Для локальной разработки фронтенда
    "http://localhost:8080",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8080"
]

# RabbitMQ - используем в продакшене
RABBITMQ_URL = os.getenv("RABBITMQ_URL")

# API Settings
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("PORT", os.getenv("API_PORT", "8000")))

# Bot settings
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEB_APP_URL = os.getenv("WEB_APP_URL")

print(f"🔧 Режим разработки: {DEV_MODE}")
print(f"🌐 Web App URL: {WEB_APP_URL}")
print(f"🔒 CORS Origins: {CORS_ORIGINS}")
print(f"🗄️ Database: {'Neon' if 'neon' in str(DATABASE_URL) else 'PostgreSQL' if 'postgresql' in str(DATABASE_URL) else 'SQLite'}")
print(f"🐰 RabbitMQ: {'CloudAMQP' if RABBITMQ_URL and 'cloudamqp' in RABBITMQ_URL else 'Local' if RABBITMQ_URL else 'Отключен'}")
