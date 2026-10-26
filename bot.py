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

from config import BOT
from db import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CardinalBot")

# ============================================================
# PREMIUM EMOJILAR (Bot.py ichida)
# ============================================================
PREMIUM_EMOJI = {
    "✔️": "5206607081334906820",
    "❌": "5210952531676504517",
    "⌛️": "5296482716567495148",
    "⚠️": "5447644880824181073",
    "1️⃣": "5382322671679708881",
    "2️⃣": "5381990043642502553",
    "3️⃣": "5381879959335738545",
    "4️⃣": "5382054253403577563",
    "✨": "5325547803936572038",
    "🚫": "5240241223632954241",
    "🟢": "5832572966721818453",
    "🔴": "5411225014148014586",
    "▶️": "5348125953090403204",
    "⏳": "5368380585066665290",
    "⛔️": "5370675038200541160",
    "👤": "5879770735999717115",
    "👥": "5372926953978341366",
    "🔤": "5841276284155467413",
    "🧾": "5444856076954520455",
    "🖥": "5282843764451195532",
    "📱": "5355116622250026900",
    "📞": "5467539229468793355",
    "📲": "5406809207947142040",
    "🔗": "5271604874419647061",
    "❤️": "5354817009626425681",
    "👑": "5217822164362739968",
    "👋": "5413694143601842851",
    "🎮": "5361741454685256344",
    "📌": "5397782960512444700",
    "🌐": "5447410659077661506",
    "📢": "5278256077954105203",
    "💳": "5445353829304387411",
    "ℹ️": "5334544901428229844",
    "🛡": "5251203410396458957",
    "🤖": "5287684458881756303",
    "🗓": "5413879192267805083",
    "📁": "5336899419679792193",
    "📊": "5231200819986047254",
    "💰": "5224257782013769471",
    "💸": "5231449120635370684",
    "💵": "5409048419211682843",
    "➕": "5397916757333654639",
    "🎬": "5375464961822695044",
    "🛒": "5312361253610475399",
    "🏆": "5226431245918942763",
    "🎯": "5256131095094652290",
    "🚗": "5233638613358486264",
    "🔫": "5192724084881892602",
    "💎": "5427168083074628963",
    "📍": "5391032818111363540",
    "🏠": "5416041192905265756",
    "⚡️": "5456140674028019486",
    "✅": "5895628223407984747",
}

_EMOJI_KEYS = sorted(PREMIUM_EMOJI.keys(), key=len, reverse=True)
_EMOJI_PATTERN = re.compile("|".join(re.escape(e) for e in _EMOJI_KEYS))

def pe(text: str) -> str:
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

# ============================================================
# FSM STATES
# ============================================================
class AdminStates(StatesGroup):
    add_acc_name = State()
    add_acc_video = State()
    add_acc_text = State()
    add_acc_prices = State()
    upload_passport = State()

# ============================================================
# ASOSIY MENYU
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
# ADMIN PANEL
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
        [InlineKeyboardButton(text="🎮 Akkount qo'shish (Bot orqali)", callback_data="admin_add_acc")],
        [InlineKeyboardButton(text="📊 Statistika (WebApp)", web_app=WebAppInfo(url=BOT.WEBAPP_URL + "?admin=1"))],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_menu")]
    ])
    
    await cb.message.edit_text(pe(text), reply_markup=kb)

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(cb: types.CallbackQuery):
    await cb.message.delete()
    await show_main_menu(cb.message)

# --- Admin: Akkount Qo'shish (FSM) ---
@dp.callback_query(F.data == "admin_add_acc")
async def admin_add_acc(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer(pe("🎮 <b>Yangi Akkount Qo'shish</b>\n\nAkkount nomini kiriting (Masalan: #1 yoki #3 Cardinal VIP):"))
    await state.set_state(AdminStates.add_acc_name)

@dp.message(AdminStates.add_acc_name)
async def process_acc_name(message: types.Message, state: FSMContext):
    await state.update_data(acc_name=message.text)
    await message.answer(pe("🎬 Endi akkount uchun <b>VIDEO</b> yuboring:"))
    await state.set_state(AdminStates.add_acc_video)

@dp.message(AdminStates.add_acc_video, F.video)
async def process_acc_video(message: types.Message, state: FSMContext):
    # Videoni kanalga saqlash
    try:
        saved_msg = await message.forward(BOT.VIDEO_CHANNEL_ID)
        await state.update_data(video_msg_id=saved_msg.message_id)
    except Exception as e:
        return await message.answer(pe(f"❌ Videoni kanalga saqlashda xato: {e}\nIltimos qayta yuboring."))

    await message.answer(pe("📝 Endi akkount ma'lumotlarini yozing (Premium emojilar bilan yozishingiz mumkin):\n\nMasalan:\n75 KOLLEKSIYA\n230 TA MIFIK\nFARAON - 7 LVL"))
    await state.set_state(AdminStates.add_acc_text)

@dp.message(AdminStates.add_acc_text)
async def process_acc_text(message: types.Message, state: FSMContext):
    await state.update_data(details_text=message.html_text) # Premium emojilarni saqlash uchun html_text
    await message.answer(pe("💰 Endi narxlarni kiriting:\n\nMasalan:\n2 - 25000\n6 - 49000\nnight - 50000"))
    await state.set_state(AdminStates.add_acc_prices)

@dp.message(AdminStates.add_acc_prices)
async def process_acc_prices(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    # Narxlarni parse qilish
    prices = {}
    lines = message.text.split("\n")
    for line in lines:
        if "-" in line:
            parts = line.split("-")
            key = parts[0].strip().lower()
            val = int(re.sub(r'\D', '', parts[1]))
            prices[key] = val

    await db.create_account(
        acc_name=data['acc_name'],
        acc_type="bot",
        video_msg_id=str(data['video_msg_id']),
        image_url=None,
        details_text=data['details_text'],
        prices_json=prices
    )
    
    await message.answer(pe(f"✅ <b>Akkount qo'shildi!</b>\n\n🎮 {data['acc_name']}\n💰 Narxlar: {len(prices)} ta"))
    await state.clear()
    await show_main_menu(message)


# ============================================================
# HARIDNI TASDIQLASH (Admin uchun Callback)
# ============================================================
async def send_rental_to_admin(rental_id, user_id, user_name, acc_name, duration, price, is_first_time):
    text = (
        f"🆕 <b>YANGI HARID!</b>\n\n"
        f"👤 Foydalanuvchi: <b>{user_name}</b> (ID: {user_id})\n"
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
    
    await db.approve_rental(rental_id, start_time=now)
    
    await cb.message.edit_text(pe("✅ <b>Akkount ulab berildi!</b>\n\nVaqt avtomatik boshlandi."))
    
    # Foydalanuvchiga xabar
    async with db.pool.acquire() as conn:
        r = await conn.fetchrow("SELECT u.tg_id, a.acc_name FROM rentals r JOIN users u ON u.id=r.user_id JOIN accounts a ON a.id=r.account_id WHERE r.id=$1", rental_id)
        if r:
            await bot.send_message(r['tg_id'], pe(f"🎉 <b>Akkountingiz ulab berildi!</b>\n\n🎮 {r['acc_name']}"))

@dp.callback_query(F.data.startswith("verify_user_"))
async def admin_verify_user(cb: types.CallbackQuery, state: FSMContext):
    rental_id = int(cb.data.split("_")[-1])
    await state.update_data(verify_rental_id=rental_id)
    await cb.message.answer(pe("👤 <b>Foydalanuvchi pasportini yuklang!</b>\n\nRasm ko'rinishida yuboring:"))
    await state.set_state(AdminStates.upload_passport)

@dp.message(AdminStates.upload_passport, F.photo)
async def process_passport(message: types.Message, state: FSMContext):
    data = await state.get_data()
    rental_id = data.get('verify_rental_id')
    
    photo_id = message.photo[-1].file_id
    
    async with db.pool.acquire() as conn:
        # User ID ni topish
        r = await conn.fetchrow("SELECT user_id FROM rentals WHERE id=$1", rental_id)
        if r:
            await conn.execute("UPDATE users SET passport_file_id=$1, is_verified=TRUE, checkmark_type='blue' WHERE id=$2", photo_id, r['user_id'])
            
            # Foydalanuvchiga xabar
            u = await conn.fetchrow("SELECT tg_id FROM users WHERE id=$1", r['user_id'])
            if u:
                await bot.send_message(u['tg_id'], pe("✅ <b>Profilingiz admin tomonidan tasdiqlandi!</b>\nSizga ko'k galichka berildi."))

    await message.answer(pe("✅ Pasport saqlandi va foydalanuvchi tasdiqlandi!"))
    await state.clear()


# ============================================================
# BOTNI ISHGA TUSHIRISH (main.py dan chaqiriladi)
# ============================================================
async def start_bot():
    logger.info("🚀 Bot ishga tushdi...")
    await dp.start_polling(bot)
