"""
Cardinal Arenda - Konfiguratsiya Fayli (Mukammal v2.0)
======================================================
Barcha sozlamalar, maxfiy kalitlar va limitlar shu yerda.
"""
import os
from dotenv import load_dotenv

# .env faylini yuklash (lokal ishlatish uchun)
load_dotenv()

# ============================================================
# MA'LUMOTLAR BAZASI (DATABASE)
# ============================================================
class DB:
    # Railway avtomatik beradigan to'liq baza manzili
    URL = os.getenv("DATABASE_URL")

    # Lokal test uchun zaxira sozlamalar (Agar URL bo'lmasa ishlatiladi)
    HOST = os.getenv("PGHOST", "localhost")
    PORT = int(os.getenv("PGPORT", 5432))
    NAME = os.getenv("PGDATABASE", "railway")
    USER = os.getenv("PGUSER", "postgres")
    PASSWORD = os.getenv("PGPASSWORD", "root")

# ============================================================
# TELEGRAM BOT
# ============================================================
class BOT:
    TOKEN = os.getenv("BOT_TOKEN", "8661307249:AAH1d8VDMAR1uAcK5_2hzSPnf2QqNtEGtO8")
    ADMIN_ID = int(os.getenv("ADMIN_ID", "7038296036"))
    WEB_APP_URL = os.getenv("WEB_APP_URL", "https://bilolmujah-hue.github.io/Cardinal_Arenda/")

    # Majburiy obuna kanallari (Hozircha bo'sh, keyin qo'shishingiz mumkin)
    REQUIRED_CHANNELS = [
        # {"type": "username", "username": "@Cardinal_PUBG", "id": -1001365422917, "name": "Cardinal PUBG"},
    ]

# ============================================================
# TO'LOV UCHUN KARTALAR (Admin panelda ko'rinadi)
# ============================================================
class CARDS:
    LIST = [
        {"number": "5614682110725894", "holder": "CARDINAL ADMIN"},
        {"number": "5614682513788143", "holder": "CARDINAL ADMIN"},
    ]

# ============================================================
# USERBOT (TELETHON) - To'lov ushlagich
# ============================================================
class USERBOT:
    API_ID = int(os.getenv("USERBOT_API_ID", "123456"))
    API_HASH = os.getenv("USERBOT_API_HASH", "abcdef1234567890abcdef1234567890")
    WATCH_BOT = "CardXabarBot" # To'lov xabarlari keladigan bot

# ============================================================
# JWT (Xavfsizlik Tokenlari - Web App uchun)
# ============================================================
class JWT:
    SECRET = os.getenv("JWT_SECRET", "cardinal-arenda-super-secret-2026")
    ALGORITHM = "HS256"
    ACCESS_MINUTES = 60
    REFRESH_DAYS = 7

# ============================================================
# TIZIM LIMITLARI
# ============================================================
class LIMITS:
    MIN_TOPUP = 5000          # Minimal balans to'ldirish (so'm)
    PAYMENT_TIMEOUT_MIN = 10  # To'lov qilishga beriladigan vaqt (daqiqa)
    MAX_VIDEO_MB = 200        # Video hajmi (agar kerak bo'lsa)

# ============================================================
# QO'SHIMCHA SOZLAMALAR
# ============================================================
DEFAULT_AD_DAYS = 30  # Standart reklama/arenda muddati (kunlarda)