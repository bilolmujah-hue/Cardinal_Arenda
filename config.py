"""
Cardinal Arenda - Konfiguratsiya Fayli
======================================
Ushbu faylda tizimning barcha sozlamalari, limitlari va maxfiy kalitlari saqlanadi.
"""
import os
from dotenv import load_dotenv

# .env faylidan o'zgaruvchilarni yuklash
load_dotenv()


class DB:
    """Ma'lumotlar bazasi sozlamalari"""
    HOST = os.getenv("PGHOST", "localhost")
    PORT = int(os.getenv("PGPORT", 5432))
    NAME = os.getenv("PGDATABASE", "railway")
    USER = os.getenv("PGUSER", "postgres")
    PASSWORD = os.getenv("PGPASSWORD", "root")


class BOT:
    """Telegram Bot sozlamalari"""
    TOKEN = os.getenv("BOT_TOKEN", "8661307249:AAH1d8VDMAR1uAcK5_2hzSPnf2QqNtEGtO8")  # Yangi tokenni qo'ying
    ADMIN_ID = int(os.getenv("ADMIN_ID", "7038296036"))
    WEB_APP_URL = os.getenv("WEB_APP_URL", "https://bilolmujah-hue.github.io/Cardinal_Arenda/")

    # Majburiy obuna kanallari (Hozircha bo'sh, keyin qo'shishingiz mumkin)
    REQUIRED_CHANNELS = [
        {"type": "username", "username": "@Cardinal_PUBG", "id": -1001365422917, "name": "Cardinal PUBG"},
    ]


class USERBOT:
    """To'lovlarni ushlab qoluvchi Userbot (Telethon) sozlamalari"""
    API_ID = int(os.getenv("USERBOT_API_ID", "30030023"))
    API_HASH = os.getenv("USERBOT_API_HASH", "a3a0b5d77ef12ec9ed208012844875c5")
    WATCH_BOT = "CardXabarBot"


class JWT:
    """Xavfsizlik (Web App uchun token) sozlamalari"""
    SECRET = os.getenv("JWT_SECRET", "cardinal-arenda-super-secret-2026")
    ALGORITHM = "HS256"
    ACCESS_MINUTES = 60
    REFRESH_DAYS = 7


class LIMITS:
    """Tizim limitlari"""
    MIN_TOPUP = 5000  # Minimal to'ldirish (so'm)
    PAYMENT_TIMEOUT_MIN = 10  # To'lov qilishga beriladigan vaqt (daqiqa)
    MAX_VIDEO_MB = 200  # Video hajmi


class CARDS:
    """To'lov uchun kartalar (Admin panelda o'zgartirish mumkin)"""
    # Karta raqamlari va ularning oxirgi 4 raqami bo'yicha userbot tekshiradi
    LIST = [
        {"number": "5614682110725894", "holder": "CARDINAL ADMIN"},
        {"number": "5614682513788143", "holder": "CARDINAL ADMIN"},
    ]
DEFAULT_AD_DAYS = 30