"""
Cardinal Arenda - Userbot (Telethon) v3.0
=========================================
Admin panel orqali raqam va kod kiritib ulanadigan, to'lovlarni ushlab qoluvchi tizim.
"""
import asyncio
import logging
import re
from typing import Optional, Callable, Awaitable, Dict, Any

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.network import ConnectionTcpAbridged
from telethon.errors import (
    AuthKeyNotFound, AuthKeyDuplicatedError, SessionRevokedError,
    SessionPasswordNeededError, PhoneCodeInvalidError,
    PhoneCodeExpiredError, PasswordHashInvalidError,
)

from config import USERBOT
from db import Database

logger = logging.getLogger("Userbot")


class PaymentWatcher:
    def __init__(self, db: Database, on_payment: Callable[[int, str], Awaitable[dict]]):
        self.db = db
        self.on_payment = on_payment  # To'lov topilganda chaqiriladigan funksiya (main.py dan)
        self.client: Optional[TelegramClient] = None
        self._task: Optional[asyncio.Task] = None
        self._pending: Dict[str, Dict[str, Any]] = {}

    async def start(self):
        """Bot ishga tushganda bazadagi sessiyani yuklash"""
        session_str = await self.db.get_userbot_session()
        if not session_str:
            logger.warning("⚠️ Bazada Userbot sessiyasi yo'q. Admin panel orqali ulang.")
            return
        await self._connect_with_session(session_str)

    async def _connect_with_session(self, session_str: str):
        """Sessiya orqali Telegramga ulanish"""
        try:
            self.client = TelegramClient(
                StringSession(session_str),
                USERBOT.API_ID,
                USERBOT.API_HASH,
                device_model="Cardinal Arenda",
                system_version="1.0",
                app_version="8.0",
                connection=ConnectionTcpAbridged,
            )

            # @CardXabarBot dan keladigan xabarlarni ushlash
            @self.client.on(events.NewMessage(incoming=True))
            async def handler(event):
                await self._on_message(event)

            await self.client.start()
            me = await self.client.get_me()
            logger.info(f"✅ Userbot ishga tushdi: @{me.username or me.id}")
            self._task = asyncio.create_task(self.client.run_until_disconnected())
        except Exception as e:
            logger.error(f"❌ Userbot ulanish xatosi: {e}")
            self.client = None

    # ============================================================
    # ADMIN PANEL UCHUN METODLAR (Web App dan chaqiriladi)
    # ============================================================
    async def send_code(self, phone: str) -> dict:
        """Admin panelda raqam kiritilganda kod yuborish"""
        try:
            phone = phone.strip()
            if not phone.startswith("+"): phone = "+" + phone

            # Eskisini o'chirish
            if phone in self._pending:
                try:
                    await self._pending[phone]["client"].disconnect()
                except:
                    pass
                del self._pending[phone]

            client = TelegramClient(StringSession(), USERBOT.API_ID, USERBOT.API_HASH)
            await client.connect()
            result = await client.send_code_request(phone)

            self._pending[phone] = {
                "client": client,
                "hash": result.phone_code_hash,
            }
            return {"ok": True, "phone": phone}
        except Exception as e:
            logger.error(f"send_code: {e}")
            return {"ok": False, "error": str(e)}

    async def verify_code(self, phone: str, code: str) -> dict:
        """Kodni tasdiqlash"""
        try:
            phone = phone.strip()
            if not phone.startswith("+"): phone = "+" + phone

            p = self._pending.get(phone)
            if not p: return {"ok": False, "error": "Avval kod yuboring"}

            client = p["client"]
            code = code.strip().replace(" ", "")

            try:
                await client.sign_in(phone, code, phone_code_hash=p["hash"])
            except SessionPasswordNeededError:
                return {"ok": True, "need_2fa": True}
            except PhoneCodeInvalidError:
                return {"ok": False, "error": "Kod xato"}

            session_str = client.session.save()
            await self._save_and_start(session_str, phone)
            return {"ok": True, "need_2fa": False}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def verify_2fa(self, phone: str, password: str) -> dict:
        """2FA parolni tasdiqlash"""
        try:
            phone = phone.strip()
            if not phone.startswith("+"): phone = "+" + phone

            p = self._pending.get(phone)
            if not p: return {"ok": False, "error": "Avval kod yuboring"}

            client = p["client"]
            try:
                await client.sign_in(password=password)
            except PasswordHashInvalidError:
                return {"ok": False, "error": "Parol xato"}

            session_str = client.session.save()
            await self._save_and_start(session_str, phone)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _save_and_start(self, session_str: str, phone: str):
        """Sessiyani bazaga saqlash va qayta ulanish"""
        if phone in self._pending:
            try:
                await self._pending[phone]["client"].disconnect()
            except:
                pass
            del self._pending[phone]

        if self.client:
            try:
                await self.client.disconnect()
            except:
                pass
            self.client = None

        await self.db.save_userbot_session(phone, session_str)
        await self._connect_with_session(session_str)

    async def logout(self) -> dict:
        """Userbotni o'chirish"""
        try:
            if self.client:
                try:
                    await self.client.log_out()
                except:
                    pass
                try:
                    await self.client.disconnect()
                except:
                    pass
                self.client = None
            if self._task:
                self._task.cancel()
                self._task = None
            await self.db.delete_userbot_session()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ============================================================
    # TO'LOVLARNI USHLASH (Message Handler)
    # ============================================================
    async def _on_message(self, event):
        try:
            sender = await event.get_sender()
            if not sender: return

            sender_username = (getattr(sender, "username", "") or "").lower()
            target = USERBOT.WATCH_BOT.lower()

            if sender_username != target: return

            text = event.raw_text or ""
            if not text: return

            logger.info(f"📥 CardXabarBot: {text[:100].replace(chr(10), ' | ')}")

            parsed = self._parse(text)
            if not parsed: return

            amount, last4 = parsed
            result = await self.on_payment(amount, last4)

            if result and result.get("ok"):
                logger.info(f"✅ To'lov aniqlandi: {amount} so'm (***{last4})")

        except Exception as e:
            logger.error(f"❌ Handler xato: {e}")

    @staticmethod
    def _parse(text: str) -> Optional[tuple]:
        """Matndan summa va karta oxirgi 4 raqamini ajratish"""
        if not text: return None
        text_low = text.lower()

        # Chiqimlarni (spisaniye) tashlab yuborish
        if any(kw in text_low for kw in ["spisanie", "platezh", "➖", "🔴", "снятие", "списание"]): return None

        # Kirim ekanligini tekshirish
        is_income = any(
            kw in text_low for kw in ["➕", "🟢", "perevod na kartu", "popolnenie", "перевод на карту", "пополнение"])
        if not is_income:
            if not re.search(r"[➕+]\s*[\d\s.,]+\s*(UZS|so'm|сум)", text, re.IGNORECASE): return None

        # Summani ajratish
        amount = None
        m = re.search(r"[➕+]?\s*([\d]{1,3}(?:[\s,]\d{3})*(?:\.\d{1,2})?)\s*(UZS|so'm|сум)", text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(" ", "").replace(",", "")
            try:
                amount = int(float(raw))
            except:
                pass

        if amount is None or amount <= 0: return None

        # Karta oxirgi 4 raqamini ajratish
        last4 = None
        m2 = re.search(r"\*{2,}\s*(\d{4})\b", text)
        if m2:
            last4 = m2.group(1)
        else:
            m3 = re.search(r"(?:karta|card|карта)[^\d]{0,15}(\d{4})\b", text, re.IGNORECASE)
            if m3: last4 = m3.group(1)

        if not last4: return None

        return amount, last4