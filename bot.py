"""
Cardinal Arenda - Telegram Bot (MUKAMMAL VA XATOSIZ)
=====================================================
Aiogram 3.7.0+ uchun moslashtirilgan.
Premium emojilar, Admin panel, Web App va to'liq mantiq.
"""

import asyncio
import logging
import json
import re
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramAPIError

from config import BOT, USERBOT
from db import Database
from userbot import PaymentWatcher

logger = logging.getLogger("CardinalBot")

# ============================================================
# PREMIUM EMOJILAR (MUKAMMAL TO'PLAM)
# ============================================================
PREMIUM_EMOJI = {
    "✔️": "5206607081334906820",
    "❌": "5210952531676504517",
    "⏳": "5368380585066665290",
    "⚠️": "5447644880824181073",
    "🚀": "5188481279963715781",
    "🎮": "5361741454685256344",
    "💰": "5224257782013769471",
    "📱": "5406809207947142040",
    "👤": "5879770735999717115",
    "🛡": "5251203410396458957",
    "💎": "5427168083074628963",
    "👑": "5217822164362739968",
    "🔥": "5104947635603952248",
    "⭐": "5438496463044752972",
    "💳": "5445353829304387411",
    "📊": "5231200819986047254",
    "🤖": "5287684458881756303",
    "📢": "5278256077954105203",
    "🔗": "5271604874419647061",
    "🔒": "5253742260054409879",
    "⚙️": "5456140674028019486",
}

def pe(text: str) -> str:
    """Matndagi oddiy emojilarni Premium emojilarga almashtirish"""
    if not text:
        return text
    for emoji, emoji_id in PREMIUM_EMOJI.items():
        text = text.replace(emoji, f'<tg-emoji emoji-id="{emoji_id}">{emoji}</tg-emoji>')
    return text

# ============================================================
# HELPERS
# ============================================================
def num(n) -> str:
    try:
        return f"{int(n):,}".replace(",", " ")
    except Exception:
        return "0"

def status_emoji(status: str) -> str:
    return {
        "ACTIVE": "✔️",
        "PENDING": "⏳",
        "REJECTED": "❌",
        "COMPLETED": "✔️",
    }.get(status, "⚪")

def get_sub_keyboard(not_subscribed):
    """Majburiy obuna uchun tugmalar"""
    buttons = []
    for ch in not_subscribed:
        buttons.append([InlineKeyboardButton(text=f"📢 {ch['name']}", url=f"https://t.me/{ch['username'].replace('@', '')}")])
    buttons.append([InlineKeyboardButton(text="✔️ Tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_main_keyboard():
    """Asosiy menyu tugmalari"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎮 Akkauntlar (Web App)", web_app=WebAppInfo(url=BOT.WEB_APP_URL))],
            [KeyboardButton(text="👤 Profilim"), KeyboardButton(text="💰 Hisobni to'ldirish")]
        ],
        resize_keyboard=True
    )

# ============================================================
# ASOSIY BOT KLASSI
# ============================================================
class CardinalBot:
    def __init__(self, db: Database):
        # Aiogram 3.7.0+ uchun to'g'ri ishga tushirish
        self.bot = Bot(
            token=BOT.TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        self.dp = Dispatcher()
        self.db = db

        # Userbotni ulash (To'lovlarni ushlash uchun)
        self.userbot = PaymentWatcher(
            db=self.db,
            on_payment=self._on_payment_received
        )

        # Handlerlarni ro'yxatdan o'tkazish
        self._register_handlers()
        self._register_callbacks()

    async def _on_payment_received(self, amount: int, card_last4: str) -> dict:
        """Userbot to'lovni ushlaganda ishga tushadi"""
        result = await self.db.match_payment(amount, card_last4)
        if result and result.get("ok"):
            await self.db.approve_topup(result["topup_id"])
            try:
                await self.bot.send_message(
                    result["user_tg"],
                    pe(f"✔️ <b>To'lov qabul qilindi!</b>\n\n💰 Summa: <b>{num(amount)} so'm</b>\nHisobingizga muvaffaqiyatli qo'shildi."),
                )
            except Exception as e:
                logger.warning(f"Xabar yuborishda xato: {e}")
        return result

    def _register_handlers(self):
        """Buyruqlar va xabarlarni ushlash"""
        self.dp.message.register(self.cmd_start, CommandStart())
        self.dp.message.register(self.cmd_admin, Command("admin"))
        self.dp.message.register(self.cmd_stats, Command("stats"))
        self.dp.message.register(self.cmd_id, Command("id"))

        self.dp.message.register(self.handle_contact, F.contact)
        self.dp.message.register(self.handle_webapp_data, F.web_app_data)

        self.dp.message.register(self.handle_profile, F.text == "👤 Profilim")
        self.dp.message.register(self.handle_topup, F.text == "💰 Hisobni to'ldirish")
        self.dp.message.register(self.handle_admin_btn, F.text == "🛡 Admin Panel")

        self.dp.message.register(self.handle_other, F.text)

    def _register_callbacks(self):
        """Inline tugmalarni ushlash"""
        @self.dp.callback_query(F.data == "check_sub")
        async def check_sub(cb: CallbackQuery):
            not_sub = await self._check_subscription(cb.from_user.id)
            if not_sub:
                await cb.answer("❌ Hali obuna bo'lmagansiz!", show_alert=True)
                await cb.message.edit_reply_markup(reply_markup=get_sub_keyboard(not_sub))
            else:
                await cb.answer("✔️ Obuna tasdiqlandi!")
                try: await cb.message.delete()
                except: pass
                await self._show_main_menu(cb.message)

    # ============================================================
    # ASOSIY HANDLERLAR
    # ============================================================
    async def cmd_start(self, message: Message):
        u = message.from_user
        user = await self.db.get_or_create_user(
            telegram_id=u.id, username=u.username,
            first_name=u.first_name, last_name=u.last_name
        )

        if user.get("is_blocked"):
            await message.answer(pe("❌ <b>Siz botdan bloklangansiz!</b>\nAdmin bilan bog'laning."))
            return

        # Majburiy obuna tekshiruvi
        not_sub = await self._check_subscription(u.id)
        if not_sub:
            text = (
                "📢 <b>KANALLARGA OBUNA BO'LING</b>\n\n"
                "Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:\n\n"
                + "\n".join(f"  {i+1}. {c['name']}" for i, c in enumerate(not_sub))
                + "\n\n✔️ Obuna bo'lgach, <b>Tekshirish</b> tugmasini bosing."
            )
            await message.answer(pe(text), reply_markup=get_sub_keyboard(not_sub))
            return

        # Telefon raqami tekshiruvi
        if not user.get("phone"):
            kb = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)]],
                resize_keyboard=True, one_time_keyboard=True
            )
            await message.answer(
                pe("👋 <b>Assalomu alaykum!</b>\n\n"
                   "🎮 <b>CARDINAL ARENDA</b> botiga xush kelibsiz!\n"
                   "Ro'yxatdan o'tish uchun pastdagi tugma orqali telefon raqamingizni yuboring."),
                reply_markup=kb
            )
            return

        await self._show_main_menu(message, user)

    async def _show_main_menu(self, message: Message, user: dict = None):
        if not user:
            user = await self.db.get_user(message.from_user.id)

        name = user.get("first_name", "Foydalanuvchi")
        balance = user.get("balance", 0)

        text = (
            f"👋 <b>Xush kelibsiz, {name}!</b>\n\n"
            f"💰 <b>Balansingiz:</b> {num(balance)} so'm\n"
            f"🎮 <b>Arenda tizimi:</b> PUBG Mobile akkauntlarini ijaraga oling.\n\n"
            f"👇 Akkauntlarni ko'rish uchun pastdagi <b>Web App</b> tugmasini bosing."
        )

        inline_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Web App'ni ochish", web_app=WebAppInfo(url=BOT.WEB_APP_URL))]
        ])

        await message.answer(pe(text), reply_markup=inline_kb)

        # Admin bo'lsa, admin tugmasini qo'shamiz
        if user.get("is_admin"):
            admin_kb = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="🎮 Akkauntlar (Web App)", web_app=WebAppInfo(url=BOT.WEB_APP_URL))],
                    [KeyboardButton(text="👤 Profilim"), KeyboardButton(text="💰 Hisobni to'ldirish")],
                    [KeyboardButton(text="🛡 Admin Panel")]
                ],
                resize_keyboard=True
            )
            await message.answer("Menyu:", reply_markup=admin_kb)
        else:
            await message.answer("Menyu:", reply_markup=get_main_keyboard())

    async def handle_contact(self, message: Message):
        c = message.contact
        phone = c.phone_number.replace("+", "").replace(" ", "")
        if phone.startswith("998"): phone = phone[3:]

        await self.db.update_user_phone(message.from_user.id, phone)

        user = await self.db.get_user(message.from_user.id)
        await message.answer(pe("✔️ <b>Ro'yxatdan muvaffaqiyatli o'tdingiz!</b>"))
        await self._show_main_menu(message, user)

    async def handle_profile(self, message: Message):
        user = await self.db.get_user(message.from_user.id)

        badge_text = "Yo'q"
        if user.get("badge") == "blue": badge_text = "✔️ Ko'k galichka"
        elif user.get("badge") == "yellow": badge_text = "⭐ Sariq galichka"
        elif user.get("badge") == "black": badge_text = "👑 Qora galichka"

        text = (
            f"👤 <b>PROFILINGIZ</b>\n\n"
            f"🆔 ID: <code>{user['telegram_id']}</code>\n"
            f"🧾 Ism: {user.get('first_name')}\n"
            f"📱 Tel: +998{user.get('phone')}\n"
            f"💰 Balans: <b>{num(user.get('balance', 0))} so'm</b>\n"
            f"🎖 Status: {badge_text}\n"
        )
        await message.answer(pe(text))

    async def handle_topup(self, message: Message):
        await message.answer(
            pe("💰 <b>Hisobni to'ldirish</b>\n\n"
               "Iltimos, to'lovni amalga oshirish uchun quyidagi tugma orqali Web App'ga kiring va <b>To'ldirish</b> bo'limini tanlang."),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🚀 Web App'ni ochish", web_app=WebAppInfo(url=BOT.WEB_APP_URL))]
            ])
        )

    async def handle_webapp_data(self, message: Message):
        try:
            data = json.loads(message.web_app_data.data)
            logger.info(f"WebApp Data: {data}")
        except Exception:
            pass

    async def handle_other(self, message: Message):
        await message.answer(pe("🎮 <b>Xush kelibsiz!</b>\n\nBoshlash uchun /start buyrug'ini bosing."))

    async def _check_subscription(self, user_id: int) -> list:
        not_sub = []
        for ch in BOT.REQUIRED_CHANNELS:
            try:
                m = await self.bot.get_chat_member(ch["username"], user_id)
                if m.status in ("left", "kicked", "banned"):
                    not_sub.append(ch)
            except Exception:
                not_sub.append(ch)
        return not_sub

    # ============================================================
    # ADMIN PANEL (BOT ICHIDA)
    # ============================================================
    async def cmd_admin(self, message: Message):
        if message.from_user.id != BOT.ADMIN_ID: return
        await self.show_admin_panel(message)

    async def handle_admin_btn(self, message: Message):
        if message.from_user.id != BOT.ADMIN_ID: return
        await self.show_admin_panel(message)

    async def show_admin_panel(self, message: Message):
        stats = await self.db.get_stats()

        text = (
            f"🛡 <b>ADMIN PANEL</b>\n\n"
            f"👥 Foydalanuvchilar: <b>{num(stats['users'])}</b>\n"
            f"🎮 Aktiv Akkauntlar: <b>{num(stats['accounts'])}</b>\n"
            f"🟢 Aktiv Arendalar: <b>{num(stats['active_rentals'])}</b>\n"
            f"⏳ Kutilayotgan Arendalar: <b>{num(stats['pending_rentals'])}</b>\n"
            f"💰 Tizimdagi jami balans: <b>{num(stats['total_balance'])} so'm</b>"
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Batafsil Statistika", callback_data="admin_stats")],
            [InlineKeyboardButton(text="📢 Xabar Yuborish (Broadcast)", callback_data="admin_broadcast")]
        ])

        await message.answer(pe(text), reply_markup=kb)

    async def cmd_stats(self, message: Message):
        if message.from_user.id != BOT.ADMIN_ID: return
        stats = await self.db.get_stats()
        text = json.dumps(stats, indent=2, ensure_ascii=False)
        await message.answer(f"<pre>{text}</pre>")

    async def cmd_id(self, message: Message):
        await message.answer(pe(f"🆔 <b>Chat ID:</b> <code>{message.chat.id}</code>"))

    # ============================================================
    # START / STOP
    # ============================================================
    async def start(self):
        logger.info("🤖 Bot Polling rejimida ishga tushmoqda...")
        await self.userbot.start() # Userbotni ham ishga tushiramiz
        await self.dp.start_polling(self.bot)

    async def stop(self):
        logger.info("🛑 Bot to'xtatilmoqda...")
        await self.userbot.stop()
        await self.bot.session.close()