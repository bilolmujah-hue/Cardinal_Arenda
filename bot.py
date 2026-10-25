# bot.py
import asyncio
import logging
import re
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup,
    InlineKeyboardButton, WebAppInfo
)

from config import BOT, PREMIUM_EMOJI
from db import db
from userbot import CardXabarWatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CardinalBot")

# ============================================================
# PREMIUM EMOJI PARSER
# ============================================================
_EMOJI_KEYS = sorted(PREMIUM_EMOJI.keys(), key=len, reverse=True)
_EMOJI_PATTERN = re.compile("|".join(re.escape(e) for e in _EMOJI_KEYS))


def pe(text: str) -> str:
    """Matndagi emojilarni Premium Emojiga aylantiradi"""
    if not text: return text

    def repl(m):
        emoji = m.group(0)
        eid = PREMIUM_EMOJI.get(emoji)
        if eid:
            return f'<tg-emoji emoji-id="{eid}">{emoji}</tg-emoji>'
        return emoji

    return _EMOJI_PATTERN.sub(repl, text)


# ============================================================
# BOT & DISPATCHER
# ============================================================
bot = Bot(token=BOT.TOKEN, parse_mode="HTML")
dp = Dispatcher()

# Userbotni ishga tushirish (To'lovlarni tutish uchun)
userbot = CardXabarWatcher(db=db, bot=bot)


# ============================================================
# FSM STATES
# ============================================================
class AdminStates(StatesGroup):
    add_card_num = State()
    add_card_holder = State()
    add_acc_name = State()
    add_acc_video = State()
    add_acc_details = State()
    add_acc_prices = State()


# ============================================================
# START & ASOSIY MENYU
# ============================================================
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    u = message.from_user
    user = await db.get_user(u.id)

    if not user:
        await db.create_user(u.id, u.full_name, u.username)
        user = await db.get_user(u.id)

    if user['is_blocked']:
        return await message.answer(pe("🚫 <b>Siz bloklangansiz!</b>"))

    # Telefon raqam so'rash (agar yo'q bo'lsa)
    if not user['phone']:
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📞 Raqamni yuborish", request_contact=True)]],
            resize_keyboard=True, one_time_keyboard=True
        )
        return await message.answer(
            pe("👋 <b>Assalomu alaykum!</b>\n\n"
               "Cardinal Arenda botiga xush kelibsiz.\n"
               "Davom etish uchun telefon raqamingizni yuboring:"),
            reply_markup=kb
        )

    # Asosiy menyu
    await show_main_menu(message)


@dp.message(F.contact)
async def handle_contact(message: types.Message):
    phone = message.contact.phone_number.replace("+", "")
    if phone.startswith("998"): phone = phone[3:]
    await db.pool.execute("UPDATE users SET phone=$1 WHERE tg_id=$2", phone, message.from_user.id)
    await message.answer(pe("✅ <b>Telefon raqam saqlandi!</b>"), reply_markup=types.ReplyKeyboardRemove())
    await show_main_menu(message)


async def show_main_menu(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Web App ochish", web_app=WebAppInfo(url=BOT.WEBAPP_URL))],
        [InlineKeyboardButton(text="🎮 Akkountlar", callback_data="acc_list"),
         InlineKeyboardButton(text="💳 Tranzaksiya", callback_data="transactions")],
        [InlineKeyboardButton(text="👤 Profilim", callback_data="profile"),
         InlineKeyboardButton(text="🏆 Reyting", callback_data="rating")]
    ])

    # Admin bo'lsa qo'shimcha tugma
    user = await db.get_user(message.from_user.id)
    if user['is_admin'] or message.from_user.id == BOT.ADMIN_ID:
        kb.inline_keyboard.append([InlineKeyboardButton(text="🛡 Admin Panel", callback_data="admin_panel")])

    await message.answer(
        pe(f"👋 <b>Salom, {message.from_user.first_name}!</b>\n\n"
           "🎮 <b>Cardinal Arenda</b> — PUBG akkountlarini arendaga olish tizimi.\n"
           "Kerakli bo'limni tanlang:"),
        reply_markup=kb
    )


# ============================================================
# ADMIN PANEL (Bot ichida)
# ============================================================
@dp.callback_query(F.data == "admin_panel")
async def admin_panel(cb: types.CallbackQuery):
    if cb.from_user.id != BOT.ADMIN_ID:
        return await cb.answer("Ruxsat yo'q!", show_alert=True)

    stats = await db.get_admin_stats()
    text = (
        f"🛡 <b>ADMIN PANEL</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{stats['users']}</b> ta\n"
        f"🎮 Aktiv Arendalar: <b>{stats['active_rentals']}</b> ta\n"
        f"💰 Umumiy Tushum: <b>{stats['total_income']:,} so'm</b>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Karta qo'shish", callback_data="admin_add_card"),
         InlineKeyboardButton(text="🎮 Akkount qo'shish", callback_data="admin_add_acc")],
        [InlineKeyboardButton(text="📊 Statistika (WebApp)", web_app=WebAppInfo(url=BOT.WEBAPP_URL + "?admin=1"))],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_menu")]
    ])

    await cb.message.edit_text(pe(text), reply_markup=kb)


@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(cb: types.CallbackQuery):
    await cb.message.delete()
    await show_main_menu(cb.message)


# --- Admin: Karta Qo'shish ---
@dp.callback_query(F.data == "admin_add_card")
async def admin_add_card(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer(pe("💳 <b>Yangi karta qo'shish</b>\n\n16 xonali karta raqamini kiriting:"))
    await state.set_state(AdminStates.add_card_num)


@dp.message(AdminStates.add_card_num)
async def process_card_num(message: types.Message, state: FSMContext):
    card_num = message.text.replace(" ", "")
    if len(card_num) != 16 or not card_num.isdigit():
        return await message.answer("❌ Xato! 16 xonali raqam kiriting:")

    await state.update_data(card_num=card_num)
    await message.answer(pe("👤 Endi karta egasining ism-familiyasini kiriting (Masalan: CARDINAL ADMIN):"))
    await state.set_state(AdminStates.add_card_holder)


@dp.message(AdminStates.add_card_holder)
async def process_card_holder(message: types.Message, state: FSMContext):
    holder = message.text.upper()
    data = await state.get_data()

    # Bazaga saqlash (settings jadvaliga yoki alohida cards jadvaliga)
    await db.pool.execute("""
                          INSERT INTO settings (key, value)
                          VALUES ($1, $2) ON CONFLICT (key) DO
                          UPDATE SET value = EXCLUDED.value
                          """, f"card_{data['card_num']}", holder)

    await message.answer(pe(f"✅ <b>Karta saqlandi!</b>\n\n💳 {data['card_num']}\n👤 {holder}"))
    await state.clear()


# --- Admin: Akkount Qo'shish (Bot orqali) ---
@dp.callback_query(F.data == "admin_add_acc")
async def admin_add_acc(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer(
        pe("🎮 <b>Yangi Akkount Qo'shish</b>\n\nAkkount nomini kiriting (Masalan: #1 yoki #3 Cardinal VIP):"))
    await state.set_state(AdminStates.add_acc_name)


@dp.message(AdminStates.add_acc_name)
async def process_acc_name(message: types.Message, state: FSMContext):
    await state.update_data(acc_name=message.text)
    await message.answer(pe("🎬 Endi akkount uchun <b>VIDEO</b> yuboring:"))
    await state.set_state(AdminStates.add_acc_video)


@dp.message(AdminStates.add_acc_video, F.video)
async def process_acc_video(message: types.Message, state: FSMContext):
    # Videoni saqlash (keyinchalik userbot orqali kanalga yuboramiz)
    await state.update_data(video_id=message.video.file_id)
    await message.answer(
        pe("📝 Endi akkount ma'lumotlarini yozing (qatorma-qator):\n\nMasalan:\n75 KOLLEKSIYA\n230 TA MIFIK\nFARAON - 7 LVL"))
    await state.set_state(AdminStates.add_acc_details)


@dp.message(AdminStates.add_acc_details)
async def process_acc_details(message: types.Message, state: FSMContext):
    await state.update_data(details=message.text)
    await message.answer(
        pe("💰 Endi narxlarni kiriting (JSON formatida emas, oddiy matnda):\n\nMasalan:\n1 soat - 25000\n6 soat - 49000\n12 soat - 70000\n24 soat - 99000\nTungi paket - 50000"))
    await state.set_state(AdminStates.add_acc_prices)


@dp.message(AdminStates.add_acc_prices)
async def process_acc_prices(message: types.Message, state: FSMContext):
    data = await state.get_data()

    # Narxlarni parse qilish (regex orqali)
    prices = {}
    lines = message.text.split("\n")
    for line in lines:
        if "soat" in line.lower():
            match = re.search(r'(\d+)\s*soat.*?(\d+)', line)
            if match:
                prices[match.group(1)] = int(match.group(2))
        elif "tungi" in line.lower():
            match = re.search(r'(\d+)', line)
            if match:
                prices["night"] = int(match.group(1))

    await db.create_account(
        acc_name=data['acc_name'],
        acc_type="bot",
        video_msg_id=data['video_id'],
        image_url=None,
        details_text=data['details'],
        prices_json=prices
    )

    await message.answer(pe(f"✅ <b>Akkount qo'shildi!</b>\n\n🎮 {data['acc_name']}\n💰 Narxlar: {len(prices)} ta"))
    await state.clear()


# ============================================================
# HARIDNI TASDIQLASH (Admin uchun Callback)
# ============================================================
# Bu funksiya api.py dan chaqiriladi, foydalanuvchi WebApp da harid qilganda
async def send_rental_to_admin(rental_id, user_name, acc_name, duration, price, is_first_time):
    text = (
        f"🆕 <b>YANGI HARID!</b>\n\n"
        f"👤 Foydalanuvchi: <b>{user_name}</b>\n"
        f"🎮 Akkount: <b>{acc_name}</b>\n"
        f"⏳ Vaqt: <b>{duration}</b>\n"
        f"💰 Summa: <b>{price:,} so'm</b>\n\n"
        f"Holat: ⏳ Tasdiqlash kutilmoqda"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_rent_{rental_id}"),
         InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_rent_{rental_id}")]
    ])

    await bot.send_message(BOT.ADMIN_ID, pe(text), reply_markup=kb)


@dp.callback_query(F.data.startswith("approve_rent_"))
async def admin_approve_rent(cb: types.CallbackQuery):
    rental_id = int(cb.data.split("_")[-1])

    # 2-qadam: Akkountni ulab berdim va User tasdiqlash
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Akkount ulab berdim", callback_data=f"linked_acc_{rental_id}")],
        [InlineKeyboardButton(text="👤 User tasdiqlash (Pasport)", callback_data=f"verify_user_{rental_id}")]
    ])

    await cb.message.edit_text(pe("✅ <b>Harid tasdiqlandi!</b>\n\nEndi quyidagi amallarni bajaring:"), reply_markup=kb)


@dp.callback_query(F.data.startswith("linked_acc_"))
async def admin_linked_acc(cb: types.CallbackQuery):
    rental_id = int(cb.data.split("_")[-1])
    now = datetime.now()

    # Bazada vaqtni boshlash
    await db.approve_rental(rental_id, start_time=now)

    await cb.message.edit_text(pe("✅ <b>Akkount ulab berildi!</b>\n\nVaqt avtomatik boshlandi."))

    # Foydalanuvchiga xabar yuborish
    # (Bu qismda foydalanuvchi ID sini olib, unga xabar yuboramiz)
    # await bot.send_message(user_id, "Akkount sizga ulab berildi...")


@dp.callback_query(F.data.startswith("verify_user_"))
async def admin_verify_user(cb: types.CallbackQuery, state: FSMContext):
    rental_id = int(cb.data.split("_")[-1])
    await cb.message.answer(pe("👤 <b>Foydalanuvchi pasportini yuklang!</b>\n\nRasm yoki fayl ko'rinishida yuboring:"))
    # Bu yerda FSM orqali pasport rasmini qabul qilamiz va db.save_passport() qilamiz


# ============================================================
# START BOT
# ============================================================
async def main():
    # Bazaga ulanish
    await db.connect()

    # Userbotni ishga tushirish (Telethon)
    await userbot.start()

    # Botni ishga tushirish
    logger.info("🚀 Bot ishga tushdi...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())