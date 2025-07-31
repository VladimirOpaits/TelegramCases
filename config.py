import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///casino.db")

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

RABBITMQ_URL = os.getenv("RABBITMQ_URL")

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("PORT", os.getenv("API_PORT", "8000")))

BOT_TOKEN = os.getenv("BOT_TOKEN")
if BOT_TOKEN is not None:
    BOT_TOKEN = str(BOT_TOKEN)
WEB_APP_URL = os.getenv("WEB_APP_URL")

TON_TESTNET = os.getenv("TON_TESTNET", "true").lower() == "true"

# TON кошельки для получения платежей
TON_WALLET_TESTNET = os.getenv("TON_WALLET_TESTNET", "EQD4FPq-PRDieyQKkizFTRtSDyucUIqrj0v_zXJmqaDp6_0t")
TON_WALLET_MAINNET = os.getenv("TON_WALLET_MAINNET", "EQD4FPq-PRDieyQKkizFTRtSDyucUIqrj0v_zXJmqaDp6_0t")  # Замените на ваш основной адрес

# Выбираем адрес в зависимости от сети
TON_WALLET_ADDRESS = TON_WALLET_TESTNET if TON_TESTNET else TON_WALLET_MAINNET

print(f"🔧 Режим разработки: {DEV_MODE}")
print(f"🌐 Web App URL: {WEB_APP_URL}")
print(f"🔒 CORS Origins: {CORS_ORIGINS}")
print(f"🗄️ Database: {'Neon' if 'neon' in str(DATABASE_URL) else 'PostgreSQL' if 'postgresql' in str(DATABASE_URL) else 'SQLite'}")
print(f"🐰 RabbitMQ: {'CloudAMQP' if RABBITMQ_URL and 'cloudamqp' in RABBITMQ_URL else 'Local' if RABBITMQ_URL else 'Отключен'}")
print(f"🌐 TON Network: {'TESTNET' if TON_TESTNET else 'MAINNET'}")
print(f"💰 TON Wallet: {TON_WALLET_ADDRESS[:10]}...{TON_WALLET_ADDRESS[-10:]}")
