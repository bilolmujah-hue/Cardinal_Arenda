# main.py
import asyncio
import logging
from bot import dp, bot, userbot
from db import db
from api import start_api

logging.basicConfig(level=logging.INFO)

async def main():
    print("⏳ Bazaga ulanmoqda...")
    await db.connect()
    
    print("⏳ Userbot ishga tushmoqda...")
    await userbot.start()
    
    print("⏳ API Server ishga tushmoqda...")
    await start_api() # Endi xato bermaydi
    
    print("🚀 Bot ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot to'xtatildi")
