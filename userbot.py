# userbot.py
import asyncio
import logging
import re
from datetime import datetime
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from config import BOT

logger = logging.getLogger("Userbot")

# Telethon API ma'lumotlari
API_ID = 30030023
API_HASH = "a3a0b5d77ef12ec9ed208012844875c5"


class CardXabarWatcher:
    def __init__(self, db, bot):
        self.db = db
        self.bot = bot
        self.client = None

    async def start(self):
        # Sessiyani bazadan olish
        try:
            async with self.db.pool.acquire() as conn:
                session_str = await conn.fetchval("SELECT value FROM settings WHERE key='userbot_session'")
        except Exception:
            session_str = None

        if not session_str:
            logger.warning("⚠️ Userbot sessiyasi topilmadi. Admin paneldan qo'shing.")
            return

        self.client = TelegramClient(StringSession(session_str), API_ID, API_HASH)

        @self.client.on(events.NewMessage(incoming=True))
        async def handler(event):
            await self._on_message(event)

        await self.client.start()
        logger.info("✅ Userbot ishga tushdi va to'lovlarni kuzatmoqda...")

    async def _on_message(self, event):
        try:
            sender = await event.get_sender()
            if not sender or getattr(sender, 'username', '').lower() != BOT.USERBOT_WATCH.lower():
                return

            text = event.raw_text
            if not text: return

            # To'lovni tekshirish (Faqat kirim)
            if "Perevod na kartu" not in text and "Пополнение" not in text:
                if "+" not in text and "🟢" not in text:
                    return

            # Summani ajratib olish
            amount_match = re.search(r'([\d\s]+)\s*(?:UZS|so\'m)', text)
            if not amount_match: return

            amount = int(float(amount_match.group(1).replace(" ", "")))

            # Karta oxirgi 4 raqamini ajratib olish
            card_match = re.search(r'\*{3}\s*(\d{4})', text)
            if not card_match: return

            card_last4 = card_match.group(1)

            logger.info(f"💰 To'lov keldi: {amount:,} so'm | Karta: ***{card_last4}")

            # Bazadan kutayotgan to'lovni qidirish
            async with self.db.pool.acquire() as conn:
                req = await conn.fetchrow("""
                                          SELECT t.id, t.user_id, u.tg_id
                                          FROM topup_requests t
                                                   JOIN users u ON u.id = t.user_id
                                          WHERE t.amount = $1
                                            AND t.status = 'WAITING'
                                            AND t.expires_at > NOW()
                                            AND t.card_number LIKE $2
                                          ORDER BY t.created_at ASC LIMIT 1
                                          """, amount, f"%{card_last4}")

                if req:
                    # To'lovni tasdiqlash
                    async with conn.transaction():
                        await conn.execute("UPDATE topup_requests SET status='COMPLETED' WHERE id=$1", req['id'])
                        # Balansni qo'shish
                        await self.db.update_balance(
                            tg_id=req['tg_id'], amount=amount,
                            tx_type="topup", desc="CardXabarBot orqali avtomatik"
                        )

                    # Foydalanuvchiga xabar yuborish
                    try:
                        await self.bot.send_message(
                            req['tg_id'],
                            f"✅ <b>To'lov qabul qilindi!</b>\n\n"
                            f"💰 Summa: <b>{amount:,} so'm</b>\n"
                            f"Balansingizga qo'shildi."
                        )
                    except:
                        pass

                    logger.info(f"✅ Balans to'ldirildi! User ID: {req['tg_id']}")
        except Exception as e:
            logger.error(f"Userbot xatosi: {e}")

    async def stop(self):
        if self.client:
            await self.client.disconnect()