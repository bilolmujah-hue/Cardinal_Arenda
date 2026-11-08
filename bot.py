"""
Cardinal Arenda - Telegram Bot (Aiogram 3.x)
=============================================
Ushbu fayl foydalanuvchilar bilan bevosita muloqot qiladi.
Ro'yxatdan o'tish, obuna tekshirish va Web App'ni ochish vazifalarini bajaradi.
"""

import logging
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
)
from aiogram.enums import ParseMode

from config import BOT, LIMITS
from db import Database

logger = logging.getLogger("CardinalBot")

# ============================================================
# PREMIUM EMOJILAR (Tashqi ko'rinish uchun)
# ============================================================
PREMIUM_EMOJI = {
    "✔️": "5206607081334906820",
    "❌": "5210952531676504517",
    "⚠️": "5447644880824181073",
    "🚀": "5188481279963715781",
    "🎮": "5361741454685256344",
    "💰": "5224257782013769471",
    "📱": "5406809207947142040",
    "👤": "5879770735999717115",
    "🛡": "5251203410396458957",
    "💎": "5427168083074628963",
}


def pe(text: str) -> str:
    """Matndagi oddiy emojilarni Premium emojilarga almashtirish"""
    for emoji, emoji_id in PREMIUM_EMOJI.items():
        text = text.replace(emoji, f'<tg-emoji emoji-id="{emoji_id}">{emoji}</tg-emoji>')
    return text


class CardinalBot:
    def __init__(self, db: Database):
        self.bot = Bot(token=BOT.TOKEN, parse_mode=ParseMode.HTML)
        self.dp = Dispatcher()
        self.db = db

        # Handlerlarni ro'yxatdan o'tkazish
        self._register_handlers()

    def _register_handlers(self):
        """Barcha buyruq va tugmalarni ushlagichlarni ulash"""
        self.dp.message.register(self.cmd_start, CommandStart())
        self.dp.message.register(self.cmd_admin, Command("admin"))
        self.dp.message.register(self.handle_contact, F.contact)
        self.dp.callback_query.register(self.check_subscription, F.data == "check_sub")
        self.dp.message.register(self.handle_text, F.text)

    async def _check_user_subscription(self, user_id: int) -> list:
        """Foydalanuvchi majburiy kanallarga a'zo bo'lganligini tekshirish"""
        not_subscribed = []
        for channel in BOT.REQUIRED_CHANNELS:
            try:
                member = await self.bot.get_chat_member(chat_id=channel["username"], user_id=user_id)
                if member.status in ("left", "kicked", "banned"):
                    not_subscribed.append(channel)
            except Exception as e:
                logger.warning(f"Obunani tekshirishda xatolik ({channel['name']}): {e}")
                not_subscribed.append(channel)
        return not_subscribed

    def _get_sub_keyboard(self, not_subscribed: list) -> InlineKeyboardMarkup:
        """Obuna bo'lish uchun tugmalar"""
        buttons = []
        for ch in not_subscribed:
            buttons.append(
                [InlineKeyboardButton(text=f"📢 {ch['name']}", url=f"https://t.me/{ch['username'].replace('@', '')}")])

        buttons.append([InlineKeyboardButton(text="✔️ Tekshirish", callback_data="check_sub")])
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    def _get_main_keyboard(self) -> ReplyKeyboardMarkup:
        """Asosiy menyu tugmalari"""
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🎮 Akkauntlar (Web App)", web_app=WebAppInfo(url=BOT.WEB_APP_URL))],
                [KeyboardButton(text="👤 Profilim"), KeyboardButton(text="💰 Hisobni to'ldirish")]
            ],
            resize_keyboard=True
        )

    # ============================================================
    # HANDLERLAR (Buyruqlar va xabarlar)
    # ============================================================
    async def cmd_start(self, message: Message):
        """ /start buyrug'i bosilganda """
        user = message.from_user

        # Foydalanuvchini bazaga qo'shish yoki yangilash
        db_user = await self.db.get_or_create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )

        if db_user.get("is_blocked"):
            await message.answer(pe("🚫 <b>Siz botdan bloklangansiz!</b>\nAdmin bilan bog'laning."))
            return

        # Majburiy obunani tekshirish
        not_subscribed = await self._check_user_subscription(user.id)
        if not_subscribed:
            await message.answer(
                pe("📢 <b>Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:</b>"),
                reply_markup=self._get_sub_keyboard(not_subscribed)
            )
            return

        # Agar telefon raqami kiritilmagan bo'lsa, so'raymiz
        if not db_user.get("phone"):
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

        # Asosiy menyuni ko'rsatish
        await self._show_main_menu(message, db_user)

    async def _show_main_menu(self, message: Message, user: dict):
        """Asosiy menyuni chiqarish"""
        balance = user.get("balance", 0)
        name = user.get("first_name", "Foydalanuvchi")

        text = (
            f"👋 <b>Xush kelibsiz, {name}!</b>\n\n"
            f"💰 <b>Balansingiz:</b> {balance:,} so'm\n"
            f"🎮 <b>Arenda tizimi:</b> PUBG Mobile akkauntlarini ijaraga oling.\n\n"
            f"👇 Akkauntlarni ko'rish uchun pastdagi <b>Web App</b> tugmasini bosing."
        )

        # Web App tugmasi (Inline)
        inline_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Web App'ni ochish", web_app=WebAppInfo(url=BOT.WEB_APP_URL))]
        ])

        await message.answer(pe(text), reply_markup=inline_kb)
        await message.answer("Menyu:", reply_markup=self._get_main_keyboard())

    async def handle_contact(self, message: Message):
        """Telefon raqam yuborilganda"""
        contact = message.contact
        phone = contact.phone_number.replace("+", "").replace(" ", "")
        if phone.startswith("998"):
            phone = phone[3:]

        await self.db.update_user_phone(message.from_user.id, phone)

        # Yangilangan ma'lumotni olamiz
        user = await self.db.get_user(message.from_user.id)

        await message.answer(pe("✔️ <b>Ro'yxatdan muvaffaqiyatli o'tdingiz!</b>"))
        await self._show_main_menu(message, user)

    async def check_subscription(self, callback: CallbackQuery):
        """Obunani tekshirish tugmasi bosilganda"""
        not_subscribed = await self._check_user_subscription(callback.from_user.id)
        if not_subscribed:
            await callback.answer("❌ Hali barcha kanallarga obuna bo'lmadingiz!", show_alert=True)
            await callback.message.edit_reply_markup(reply_markup=self._get_sub_keyboard(not_subscribed))
        else:
            await callback.answer("✔️ Obuna tasdiqlandi!")
            await callback.message.delete()

            user = await self.db.get_user(callback.from_user.id)
            if not user.get("phone"):
                kb = ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)]],
                    resize_keyboard=True, one_time_keyboard=True
                )
                await callback.message.answer(pe("📱 Endi telefon raqamingizni yuboring:"), reply_markup=kb)
            else:
                await self._show_main_menu(callback.message, user)

    async def handle_text(self, message: Message):
        """Oddiy matnli xabarlar (Profil, To'lov)"""
        text = message.text

        if text == "👤 Profilim":
            user = await self.db.get_user(message.from_user.id)
            badge = "Ko'k galichka ✔️" if user.get("badge") == "blue" else (
                "Sariq galichka ⭐" if user.get("badge") == "yellow" else (
                    "Qora galichka 🖤" if user.get("badge") == "black" else "Yo'q"))

            msg = (
                f"👤 <b>PROFILINGIZ</b>\n\n"
                f"🆔 ID: <code>{user['telegram_id']}</code>\n"
                f"🧾 Ism: {user.get('first_name')}\n"
                f"📱 Tel: +998{user.get('phone')}\n"
                f"💰 Balans: <b>{user.get('balance', 0):,} so'm</b>\n"
                f"🎖 Status: {badge}\n"
            )
            await message.answer(pe(msg))

        elif text == "💰 Hisobni to'ldirish":
            # Web App orqali to'lov qilishni tavsiya qilamiz
            await message.answer(
                pe("💰 <b>Hisobni to'ldirish</b>\n\n"
                   "Iltimos, to'lovni amalga oshirish uchun quyidagi tugma orqali Web App'ga kiring va <b>To'ldirish</b> bo'limini tanlang."),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🚀 Web App'ni ochish", web_app=WebAppInfo(url=BOT.WEB_APP_URL))]
                ])
            )

        else:
            await message.answer(pe("Menyudan foydalaning yoki /start buyrug'ini bosing."))

    async def cmd_admin(self, message: Message):
        """Admin buyruqlari (Statistika)"""
        if message.from_user.id != BOT.ADMIN_ID:
            return

        stats = await self.db.get_stats()
        text = (
            f"🛡 <b>ADMIN STATISTIKA</b>\n\n"
            f"👥 Foydalanuvchilar: {stats['users']}\n"
            f"🎮 Akkauntlar: {stats['accounts']}\n"
            f"🟢 Aktiv Arendalar: {stats['active_rentals']}\n"
            f"⏳ Kutilayotgan Arendalar: {stats['pending_rentals']}\n"
            f"💰 Tizimdagi jami balans: {stats['total_balance']:,} so'm"
        )
        await message.answer(pe(text))

    async def start(self):
        """Botni ishga tushirish"""
        logger.info("🤖 Bot Polling rejimida ishga tushmoqda...")
        # Polling ni boshlash (boshqa tasklar bilan birga ishlashi uchun)
        await self.dp.start_polling(self.bot)