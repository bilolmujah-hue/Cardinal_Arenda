# main.py
import asyncio
import logging
from bot import dp, bot, userbot
from db import db
from api import start_api

logging.basicConfig(level=logging.INFO)


async def main():
    # 1. Bazaga ulanish
    print("⏳ Bazaga ulanmoqda...")
    await db.connect()

    # 2. Userbotni ishga tushirish (CardXabarBot)
    print("⏳ Userbot ishga tushmoqda...")
    await userbot.start()

    # 3. API serverni ishga tushirish
    print("⏳ API Server ishga tushmoqda...")
    await start_api()

    # 4. Botni ishga tushirish
    print("🚀 Bot ishga tushdi!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot to'xtatildi")