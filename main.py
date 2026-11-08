"""
Cardinal Arenda - Asosiy Ishga Tushiruvchi (Main)
=================================================
Barcha komponentlarni (DB, Bot, API, Userbot) parallel ravishda ishga tushiradi.
"""
import asyncio
import logging
import os

from db import Database
from bot import CardinalBot
from api import API
from userbot import PaymentWatcher

# Loggingni chiroyli sozlash
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)-10s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("Main")

# ============================================================
# USERBOT TO'LOVNI USHLAGANDA ISHGA TUSHADIGAN FUNKSIYA
# ============================================================
async def on_payment_received(db: Database, bot_app: CardinalBot, amount: int, card_last4: str):
    """
    Userbot @CardXabarBot dan xabar kelganda avtomatik ishga tushadi.
    Bazadan mos to'lovni topib, tasdiqlaydi va balansga qo'shadi.
    """
    logger.info(f"💸 To'lov keldi: {amount:,} so'm (Karta: ***{card_last4})")

    # 1. Bazadan mos to'lovni qidirish
    result = await db.match_payment(amount, card_last4)

    if result and result.get("ok"):
        topup_id = result["topup_id"]
        tg_id = result["user_tg"]

        # 2. To'lovni avtomatik tasdiqlash
        success = await db.approve_topup(topup_id)

        if success:
            logger.info(f"✅ Topup #{topup_id} avtomatik tasdiqlandi (User: {tg_id})")

            # 3. Foydalanuvchiga xabar yuborish
            try:
                msg = (
                    f"✅ <b>To'lov qabul qilindi!</b>\n\n"
                    f"💰 Summa: <b>{amount:,} so'm</b>\n"
                    f"Hisobingizga muvaffaqiyatli qo'shildi.\n"
                    f"🎮 Akkauntlarni ijaraga olishingiz mumkin!"
                )
                await bot_app.bot.send_message(tg_id, msg, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"User {tg_id} ga xabar yuborib bo'lmadi: {e}")
        else:
            logger.error(f"❌ Topup #{topup_id} ni tasdiqlashda xato.")
    else:
        logger.info(f"ℹ️ Bu to'lov uchun kutayotgan so'rov topilmadi.")

# ============================================================
# ASOSIY FUNKSIYA
# ============================================================
async def main():
    logger.info("🚀 Cardinal Arenda tizimi ishga tushmoqda...")

    # 1. Ma'lumotlar bazasiga ulanish
    db = Database()
    await db.connect()
    await db.create_tables()

    # 2. Botni yaratish
    bot_app = CardinalBot(db)

    # 3. API Serverni yaratish
    api_app = API(db, bot_app)

    # 4. Userbotni yaratish (To'lovlarni ushlash funksiyasi bilan)
    # lambda orqali db va bot_app ni userbotga uzatamiz
    userbot = PaymentWatcher(
        db,
        on_payment=lambda amount, last4: on_payment_received(db, bot_app, amount, last4)
    )

    # Userbotni bot_app ga ulaymiz (Web App dan boshqarish uchun kerak)
    bot_app.userbot = userbot

    # 5. Hammasini parallel ravishda ishga tushirish
    try:
        await asyncio.gather(
            bot_app.start(),      # 1. Telegram Bot (Polling)
            api_app.start(),      # 2. API Server (Port 8080)
            userbot.start()       # 3. Userbot (To'lov kuzatuvchisi)
        )
    except KeyboardInterrupt:
        logger.info("🛑 Tizim foydalanuvchi tomonidan to'xtatildi.")
    except Exception as e:
        logger.error(f"❌ Kutilmagan global xatolik: {e}", exc_info=True)
    finally:
        await db.close()
        logger.info("🔌 Tizim to'liq to'xtatildi.")

if __name__ == "__main__":
    # Windows'da asyncio ba'zida xatolik berishini oldini olish
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())