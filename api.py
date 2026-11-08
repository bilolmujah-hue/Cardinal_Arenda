"""
Cardinal Arenda - API Server v2.0 (MUKAMMAL)
=============================================
Ushbu fayl Web App (Frontend) dan keladigan barcha HTTP so'rovlarni qabul qiladi.
Arenda olish, to'lovlar, reyting, foydalanuvchi profili va Admin panel mantiqlari.
"""

import logging
import json
import base64
import random
from datetime import datetime, timedelta
from aiohttp import web
import aiohttp_cors
import jwt

from config import BOT, JWT, LIMITS, CARDS, USERBOT
from db import Database

logger = logging.getLogger("API")

# ============================================================
# YORDAMCHI FUNKSIYALAR
# ============================================================
def jresp(data, status=200):
    """JSON formatida javob qaytarish (Datetime va Decimal larni to'g'ri o'giradi)"""
    def json_serial(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return str(obj)

    return web.json_response(
        data, status=status,
        dumps=lambda x: json.dumps(x, default=json_serial, ensure_ascii=False)
    )

def create_access_token(user_id: int, telegram_id: int, is_admin: bool = False) -> str:
    """Foydalanuvchi uchun JWT (Xavfsizlik tokeni) yaratish"""
    payload = {
        "sub": str(user_id),
        "tg": telegram_id,
        "adm": is_admin,
        "type": "access",
        "exp": datetime.utcnow() + timedelta(minutes=JWT.ACCESS_MINUTES),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT.SECRET, algorithm=JWT.ALGORITHM)

def decode_token(token: str):
    """Tokenni tekshirish va ichidagi ma'lumotlarni olish"""
    try:
        return jwt.decode(token, JWT.SECRET, algorithms=[JWT.ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ============================================================
# ASOSIY API KLASSI
# ============================================================
class API:
    def __init__(self, db: Database, bot_app):
        self.db = db
        self.bot_app = bot_app # bot.py dagi CardinalBot (xabar yuborish va userbot uchun)

        # aiohttp ilovasini yaratish (Rasm yuklash uchun limit 20MB)
        self.app = web.Application(
            client_max_size=20 * 1024 * 1024,
            middlewares=[self._error_middleware, self._auth_middleware]
        )

        self._setup_routes()

    # ============================================================
    # MIDDLEWARE (Xatolarni va Authni ushlash)
    # ============================================================
    @web.middleware
    async def _error_middleware(self, request, handler):
        """Har qanday kutilmagan xatolikni ushlab, foydalanuvchiga chiroyli qaytarish"""
        try:
            return await handler(request)
        except web.HTTPException as e:
            return jresp({"ok": False, "error": f"HTTP {e.status}: {e.reason}"}, e.status)
        except Exception as e:
            logger.error(f"API Xatosi: {e}", exc_info=True)
            return jresp({"ok": False, "error": "Serverda ichki xatolik yuz berdi"}, 500)

    @web.middleware
    async def _auth_middleware(self, request, handler):
        """JWT tokenni tekshirish (Ochiq yo'llardan tashqari)"""
        if request.method == "OPTIONS":
            return await handler(request)

        path = request.path

        # Ochiq (Public) yo'llar - Token talab qilinmaydi (Kirish va Web App yuklanishi)
        public_paths = (
            "/",
            "/api/auth/telegram",
            "/api/public/accounts",
            "/favicon.ico"
        )
        if path in public_paths:
            return await handler(request)

        # Qolgan barcha yo'llar uchun token majburiy
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jresp({"ok": False, "error": "Avtorizatsiyadan o'tilmagan. Iltimos Web App'ni qayta oching."}, 401)

        payload = decode_token(auth[7:])
        if not payload or payload.get("type") != "access":
            return jresp({"ok": False, "error": "Token yaroqsiz yoki muddati o'tgan"}, 401)

        request["user"] = payload

        # Admin yo'llari - Faqat adminlar kira oladi
        if path.startswith("/api/admin/"):
            if not payload.get("adm"):
                return jresp({"ok": False, "error": "Sizda admin huquqi yo'q!"}, 403)

        return await handler(request)

    # ============================================================
    # ROUTING (Yo'nalishlarni sozlash)
    # ============================================================
    def _setup_routes(self):
        cors = aiohttp_cors.setup(self.app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods="*",
            )
        })

        routes = [
            # --- Auth ---
            ("POST", "/api/auth/telegram", self.auth_telegram),

            # --- User Profile ---
            ("GET",  "/api/user/me", self.get_my_profile),
            ("POST", "/api/user/update", self.update_profile),
            ("POST", "/api/user/passport", self.upload_passport),

            # --- Accounts (Akkauntlar) ---
            ("GET",  "/api/accounts", self.get_accounts),
            ("GET",  "/api/account/{id}", self.get_account_detail),
            ("GET",  "/api/account/{id}/busy", self.get_account_busy_times),

            # --- Rentals (Arenda) ---
            ("POST", "/api/rentals/create", self.create_rental),
            ("GET",  "/api/rentals/my", self.get_my_rentals),

            # --- Topups (Balans To'ldirish) ---
            ("POST", "/api/topups/create", self.create_topup),
            ("POST", "/api/topups/receipt", self.upload_receipt),
            ("GET",  "/api/topups/status", self.check_topup_status),
            ("POST", "/api/topups/cancel", self.cancel_topup),

            # --- Leaderboard (Reyting) ---
            ("GET",  "/api/leaderboard", self.get_leaderboard),

            # --- ADMIN PANEL: Umumiy ---
            ("GET",  "/api/admin/stats", self.admin_get_stats),

            # --- ADMIN PANEL: Arendalar ---
            ("GET",  "/api/admin/rentals/pending", self.admin_pending_rentals),
            ("POST", "/api/admin/rentals/approve", self.admin_approve_rental),
            ("POST", "/api/admin/rentals/reject", self.admin_reject_rental),

            # --- ADMIN PANEL: Userlar va Galichkalar ---
            ("GET",  "/api/admin/users", self.admin_get_users),
            ("POST", "/api/admin/user/badge", self.admin_set_badge),
            ("POST", "/api/admin/user/balance", self.admin_change_balance),

            # --- ADMIN PANEL: Akkauntlar ---
            ("POST", "/api/admin/accounts/add", self.admin_add_account),
            ("POST", "/api/admin/accounts/edit", self.admin_edit_account),

            # --- ADMIN PANEL: To'lovlar ---
            ("GET",  "/api/admin/topups/pending", self.admin_pending_topups),
            ("POST", "/api/admin/topups/approve", self.admin_approve_topup),

            # --- ADMIN PANEL: Userbot Boshqaruvi (Web App ichida) ---
            ("POST", "/api/admin/userbot/send-code", self.admin_userbot_send_code),
            ("POST", "/api/admin/userbot/verify-code", self.admin_userbot_verify_code),
            ("POST", "/api/admin/userbot/verify-2fa", self.admin_userbot_verify_2fa),
            ("GET",  "/api/admin/userbot/status", self.admin_userbot_status),
            ("POST", "/api/admin/userbot/logout", self.admin_userbot_logout),
        ]

        for method, path, handler in routes:
            try:
                route = self.app.router.add_route(method, path, handler)
                cors.add(route)
            except Exception as e:
                logger.warning(f"Route qo'shishda xato: {method} {path} -> {e}")

    # ============================================================
    # AUTH (Avtorizatsiya)
    # ============================================================
    async def auth_telegram(self, req):
        """Telegram WebApp dan kelgan ma'lumotlar asosida tizimga kirish"""
        try:
            data = await req.json()
            user_data = data.get("user")
            if not user_data or not user_data.get("id"):
                return jresp({"ok": False, "error": "Foydalanuvchi ma'lumoti yo'q"}, 400)

            tg_id = int(user_data["id"])
            user = await self.db.get_or_create_user(
                telegram_id=tg_id,
                username=user_data.get("username"),
                first_name=user_data.get("first_name"),
                last_name=user_data.get("last_name")
            )

            if user.get("is_blocked"):
                return jresp({"ok": False, "error": "Siz bloklangansiz! Admin bilan bog'laning."}, 403)

            token = create_access_token(user["id"], tg_id, user.get("is_admin", False))

            return jresp({
                "ok": True,
                "token": token,
                "user": {
                    "id": user["id"],
                    "telegram_id": tg_id,
                    "first_name": user.get("first_name"),
                    "balance": user.get("balance", 0),
                    "is_admin": user.get("is_admin", False),
                    "badge": user.get("badge", "none"),
                    "is_verified": user.get("is_verified", False)
                }
            })
        except Exception as e:
            logger.error(f"Auth xatosi: {e}")
            return jresp({"ok": False, "error": "Kirishda xatolik yuz berdi"}, 400)

    # ============================================================
    # USER PROFILE (Foydalanuvchi)
    # ============================================================
    async def get_my_profile(self, req):
        """Foydalanuvchining to'liq profilini olish"""
        tg_id = req["user"]["tg"]
        user = await self.db.get_user(tg_id)
        if not user:
            return jresp({"ok": False, "error": "Topilmadi"}, 404)

        user.pop("password_hash", None) # Maxfiy qismini o'chiramiz
        return jresp({"ok": True, "user": user})

    async def update_profile(self, req):
        """Ism-familiyani yangilash"""
        tg_id = req["user"]["tg"]
        data = await req.json()
        first_name = data.get("first_name", "").strip()

        if not first_name:
            return jresp({"ok": False, "error": "Ism bo'sh bo'lishi mumkin emas"}, 400)

        async with self.db.pool.acquire() as c:
            await c.execute("UPDATE users SET first_name=$1 WHERE telegram_id=$2", first_name, tg_id)

        return jresp({"ok": True, "message": "Profil yangilandi"})

    async def upload_passport(self, req):
        """Pasport rasmini yuklash (Ko'k galichka olish uchun)"""
        tg_id = req["user"]["tg"]
        data = await req.json()
        passport_b64 = data.get("passport_img")

        if not passport_b64 or not passport_b64.startswith("data:image/"):
            return jresp({"ok": False, "error": "Rasm noto'g'ri formatda"}, 400)

        await self.db.verify_user_passport(tg_id, passport_b64)

        # Adminga xabar yuborish
        try:
            msg = f"🆔 <b>Yangi Pasport Yuklandi!</b>\n\nUser: <code>{tg_id}</code>\nAdmin panelda tasdiqlang."
            await self.bot_app.bot.send_message(BOT.ADMIN_ID, msg, parse_mode="HTML")
        except: pass

        return jresp({"ok": True, "message": "Pasport yuborildi, admin tasdiqlashini kuting."})

    # ============================================================
    # ACCOUNTS (Akkauntlar Ro'yxati)
    # ============================================================
    async def get_accounts(self, req):
        """Barcha arendagi akkauntlar"""
        accounts = await self.db.get_all_accounts()
        return jresp({"ok": True, "accounts": accounts})

    async def get_account_detail(self, req):
        """Bitta akkaunt haqida ma'lumot"""
        account_id = int(req.match_info["id"])
        account = await self.db.get_account(account_id)
        if not account:
            return jresp({"ok": False, "error": "Akkaunt topilmadi"}, 404)
        return jresp({"ok": True, "account": account})

    async def get_account_busy_times(self, req):
        """Akkaunt qachon bandligini ko'rsatish (Frontend kalendar uchun)"""
        account_id = int(req.match_info["id"])

        async with self.db.pool.acquire() as c:
            rows = await c.fetch("""
                SELECT start_time, end_time FROM rentals
                WHERE account_id=$1 AND status IN ('ACTIVE', 'PENDING')
                  AND end_time > NOW()
                ORDER BY start_time ASC
            """, account_id)

            busy_times = [{"start": r["start_time"], "end": r["end_time"]} for r in rows]
            return jresp({"ok": True, "busy_times": busy_times})

    # ============================================================
    # RENTALS (Arenda Olish)
    # ============================================================
    async def create_rental(self, req):
        """
        Arenda qilish. Foydalanuvchi vaqtni tanlaydi, puli yechiladi va
        Admin tasdiqlashi kutib turiladi (PENDING).
        """
        tg_id = req["user"]["tg"]
        data = await req.json()

        account_id = int(data.get("account_id"))
        hours = float(data.get("hours")) # Masalan 2, 4, 12, 24, 48
        price = int(data.get("price"))
        start_time_str = data.get("start_time") # "2026-11-07T14:00:00" formatida

        if not all([account_id, hours, price]):
            return jresp({"ok": False, "error": "Ma'lumotlar to'liq emas"}, 400)

        try:
            start_time = datetime.fromisoformat(start_time_str) if start_time_str else datetime.now()
            end_time = start_time + timedelta(hours=hours)
        except ValueError:
            return jresp({"ok": False, "error": "Vaqt formati xato"}, 400)

        # 1. Akkaunt bo'shligini tekshirish
        is_free = await self.db.check_account_availability(account_id, start_time, end_time)
        if not is_free:
            return jresp({"ok": False, "error": "Bu vaqtda akkaunt allaqachon band! Boshqa vaqt tanlang."}, 400)

        # 2. Balansni tekshirish
        user = await self.db.get_user(tg_id)
        if user["balance"] < price:
            return jresp({"ok": False, "error": "Balansingizda mablag' yetarli emas. Hisobni to'ldiring."}, 400)

        # 3. Pulni yechish va so'rov yaratish
        new_balance = await self.db.update_balance(tg_id, price, "subtract")
        rental_id = await self.db.create_rental_request(tg_id, account_id, start_time, end_time, price)

        # 4. Adminga xabar
        try:
            acc = await self.db.get_account(account_id)
            msg = (
                f"🔔 <b>Yangi Arenda So'rovi!</b>\n\n"
                f"👤 User: <a href='tg://user?id={tg_id}'>{user['first_name']}</a>\n"
                f"🎮 Akkaunt: #{acc['account_no']} ({acc['title']})\n"
                f"⏰ Vaqt: {start_time.strftime('%d.%m %H:%M')} dan {end_time.strftime('%d.%m %H:%M')} gacha\n"
                f"💰 To'lov: {price:,} so'm\n\n"
                f"Admin panelda tasdiqlang!"
            )
            await self.bot_app.bot.send_message(BOT.ADMIN_ID, msg, parse_mode="HTML")
        except: pass

        return jresp({
            "ok": True,
            "message": "So'rov yuborildi. Admin tasdiqlashini kuting.",
            "rental_id": rental_id,
            "new_balance": new_balance
        })

    async def get_my_rentals(self, req):
        """Foydalanuvchi arenda tarixi"""
        tg_id = req["user"]["tg"]
        rentals = await self.db.get_user_rentals(tg_id)
        return jresp({"ok": True, "rentals": rentals})

    # ============================================================
    # TOPUPS (Balans To'ldirish)
    # ============================================================
    async def create_topup(self, req):
        """Balans to'ldirishni boshlash (10 daqiqalik taymer)"""
        tg_id = req["user"]["tg"]
        data = await req.json()
        amount = int(data.get("amount", 0))

        if amount < LIMITS.MIN_TOPUP:
            return jresp({"ok": False, "error": f"Minimal to'ldirish {LIMITS.MIN_TOPUP:,} so'm"}, 400)

        # Tasodifiy karta tanlash (Siz aytgan 2 ta karta tizimi)
        card = random.choice(CARDS.LIST)

        topup_id = await self.db.create_topup(
            tg_id, amount, card["number"], card["holder"], LIMITS.PAYMENT_TIMEOUT_MIN
        )

        return jresp({
            "ok": True,
            "topup_id": topup_id,
            "card_number": card["number"],
            "card_holder": card["holder"],
            "amount": amount,
            "timeout_min": LIMITS.PAYMENT_TIMEOUT_MIN
        })

    async def upload_receipt(self, req):
        """To'lov chekini yuklash"""
        data = await req.json()
        topup_id = int(data.get("topup_id"))
        receipt_img = data.get("receipt_img")

        if not receipt_img:
            return jresp({"ok": False, "error": "Chek rasmi yuborilmadi"}, 400)

        await self.db.submit_receipt(topup_id, receipt_img)

        # Adminga xabar
        try:
            await self.bot_app.bot.send_photo(
                BOT.ADMIN_ID,
                photo=receipt_img,
                caption=f"🧾 <b>Yangi Chek Yuklandi!</b>\n\nTopup ID: {topup_id}\nAdmin panelda tasdiqlang."
            )
        except: pass

        return jresp({"ok": True, "message": "Chek qabul qilindi. Tasdiqlanmoqda..."})

    async def check_topup_status(self, req):
        """Frontend taymer va holatni tekshirishi uchun"""
        tg_id = req["user"]["tg"]
        user = await self.db.get_user(tg_id)

        async with self.db.pool.acquire() as c:
            topup = await c.fetchrow("""
                SELECT * FROM topups 
                WHERE user_id=$1 AND status IN ('WAITING', 'MATCHED', 'RECEIPT_UPLOADED')
                ORDER BY created_at DESC LIMIT 1
            """, user["id"])

            if not topup:
                return jresp({"ok": True, "status": "none", "balance": user["balance"]})

            left_sec = max(0, int((topup["expires_at"] - datetime.now()).total_seconds()))

            return jresp({
                "ok": True,
                "status": topup["status"],
                "topup_id": topup["id"],
                "left_seconds": left_sec,
                "balance": user["balance"]
            })

    async def cancel_topup(self, req):
        """To'lovni bekor qilish"""
        tg_id = req["user"]["tg"]
        await self.db.cancel_topup(tg_id)
        return jresp({"ok": True, "message": "To'lov bekor qilindi"})

    # ============================================================
    # LEADERBOARD (Reyting)
    # ============================================================
    async def get_leaderboard(self, req):
        """Top foydalanuvchilar (Haftalik, Oylik, Umumiy)"""
        period = req.query.get("period", "all")
        top_users = await self.db.get_top_users(period=period, limit=50)

        # Galichkalarni belgilash
        for i, u in enumerate(top_users):
            if i == 0: u["badge"] = "black"
            elif i == 1: u["badge"] = "yellow"

        return jresp({"ok": True, "leaderboard": top_users})

    # ============================================================
    # ADMIN PANEL API
    # ============================================================
    async def admin_get_stats(self, req):
        stats = await self.db.get_stats()
        return jresp({"ok": True, "stats": stats})

    async def admin_pending_rentals(self, req):
        rentals = await self.db.get_pending_rentals()
        return jresp({"ok": True, "rentals": rentals})

    async def admin_approve_rental(self, req):
        data = await req.json()
        rental_id = int(data.get("rental_id"))

        await self.db.approve_rental(rental_id)

        async with self.db.pool.acquire() as c:
            r = await c.fetchrow("""
                SELECT r.*, u.telegram_id, a.account_no 
                FROM rentals r JOIN users u ON u.id=r.user_id JOIN accounts a ON a.id=r.account_id
                WHERE r.id=$1
            """, rental_id)

            if r:
                try:
                    await self.bot_app.bot.send_message(
                        r["telegram_id"],
                        f"✅ <b>Arendangiz tasdiqlandi!</b>\n🎮 Akkaunt: #{r['account_no']}\nAdmin tez orada sizga akkaunt ma'lumotlarini yuboradi.",
                        parse_mode="HTML"
                    )
                except: pass

        return jresp({"ok": True, "message": "Arenda tasdiqlandi"})

    async def admin_reject_rental(self, req):
        data = await req.json()
        rental_id = int(data.get("rental_id"))
        reason = data.get("reason", "Admin rad etdi")

        await self.db.reject_rental(rental_id, reason)

        async with self.db.pool.acquire() as c:
            r = await c.fetchrow("SELECT r.*, u.telegram_id FROM rentals r JOIN users u ON u.id=r.user_id WHERE r.id=$1", rental_id)
            if r:
                try:
                    await self.bot_app.bot.send_message(
                        r["telegram_id"],
                        f"❌ <b>Arendangiz rad etildi!</b>\nSabab: {reason}\n💰 Pulingiz balansga qaytarildi.",
                        parse_mode="HTML"
                    )
                except: pass

        return jresp({"ok": True, "message": "Rad etildi va pul qaytarildi"})

    async def admin_get_users(self, req):
        async with self.db.pool.acquire() as c:
            rows = await c.fetch("SELECT * FROM users ORDER BY created_at DESC LIMIT 200")
            users = []
            for r in rows:
                d = dict(r)
                d.pop("password_hash", None)
                users.append(d)
        return jresp({"ok": True, "users": users})

    async def admin_set_badge(self, req):
        """Galichka berish (Ko'k, Sariq, Qora)"""
        data = await req.json()
        tg_id = int(data.get("telegram_id"))
        badge = data.get("badge")

        await self.db.update_user_badge(tg_id, badge)
        return jresp({"ok": True, "message": f"Galichka o'zgartirildi: {badge}"})

    async def admin_change_balance(self, req):
        """Admin tomonidan balans qo'shish yoki ayirish"""
        data = await req.json()
        tg_id = int(data.get("telegram_id"))
        amount = int(data.get("amount")) # Musbat yoki manfiy

        if amount > 0:
            new_bal = await self.db.update_balance(tg_id, amount, "add")
            msg = f"✅ Admin sizga {amount:,} so'm qo'shdi. Balans: {new_bal:,} so'm"
        else:
            new_bal = await self.db.update_balance(tg_id, abs(amount), "subtract")
            msg = f"⚠️ Admin balansingizdan {abs(amount):,} so'm ayirdi. Balans: {new_bal:,} so'm"

        try:
            await self.bot_app.bot.send_message(tg_id, msg)
        except: pass

        return jresp({"ok": True, "new_balance": new_bal})

    async def admin_add_account(self, req):
        """Yangi PUBG akkauntini qo'shish"""
        data = await req.json()
        try:
            acc_id = await self.db.add_account(
                account_no=int(data.get("account_no")),
                title=data.get("title"),
                description=data.get("description"),
                video_id=data.get("video_id"),
                prices=data.get("prices", {})
            )
            return jresp({"ok": True, "account_id": acc_id})
        except Exception as e:
            return jresp({"ok": False, "error": f"Bunday raqam bor yoki xatolik: {e}"}, 400)

    async def admin_edit_account(self, req):
        """Akkaunt narxlari va ma'lumotlarini o'zgartirish"""
        data = await req.json()
        acc_id = int(data.get("account_id"))

        async with self.db.pool.acquire() as c:
            await c.execute("""
                UPDATE accounts SET title=$1, description=$2, prices=$3::jsonb 
                WHERE id=$4
            """, data.get("title"), data.get("description"), json.dumps(data.get("prices", {})), acc_id)

        return jresp({"ok": True, "message": "Akkaunt yangilandi"})

    async def admin_pending_topups(self, req):
        """Admin tekshirishi kerak bo'lgan to'lovlar (Cheklar)"""
        async with self.db.pool.acquire() as c:
            rows = await c.fetch("""
                SELECT t.*, u.first_name, u.telegram_id 
                FROM topups t JOIN users u ON u.id = t.user_id
                WHERE t.status='RECEIPT_UPLOADED' ORDER BY t.created_at ASC
            """)
            return jresp({"ok": True, "topups": [dict(r) for r in rows]})

    async def admin_approve_topup(self, req):
        """Chekni tasdiqlash va balansga qo'shish (Agar Userbot ushlamagan bo'lsa)"""
        data = await req.json()
        topup_id = int(data.get("topup_id"))

        success = await self.db.approve_topup(topup_id)
        if success:
            return jresp({"ok": True, "message": "Tasdiqlandi va balansga qo'shildi"})
        return jresp({"ok": False, "error": "Xatolik yoki allaqachon tasdiqlangan"}, 400)

    # ============================================================
    # ADMIN USERBOT BOSHQARUVI (Web App Ichida)
    # ============================================================
    async def admin_userbot_send_code(self, req):
        data = await req.json()
        phone = data.get("phone", "").strip()
        if not phone: return jresp({"ok": False, "error": "Telefon kiriting"}, 400)
        res = await self.bot_app.userbot.send_code(phone)
        return jresp(res)

    async def admin_userbot_verify_code(self, req):
        data = await req.json()
        phone = data.get("phone", "").strip()
        code = data.get("code", "").strip()
        res = await self.bot_app.userbot.verify_code(phone, code)
        return jresp(res)

    async def admin_userbot_verify_2fa(self, req):
        data = await req.json()
        phone = data.get("phone", "").strip()
        password = data.get("password", "").strip()
        res = await self.bot_app.userbot.verify_2fa(phone, password)
        return jresp(res)

    async def admin_userbot_status(self, req):
        if not self.bot_app.userbot.client:
            return jresp({"ok": True, "connected": False})
        try:
            me = await self.bot_app.userbot.client.get_me()
            return jresp({"ok": True, "connected": True, "username": me.username, "phone": me.phone})
        except:
            return jresp({"ok": True, "connected": False})

    async def admin_userbot_logout(self, req):
        res = await self.bot_app.userbot.logout()
        return jresp(res)

    # ============================================================
    # SERVERNI ISHGA TUSHIRISH
    # ============================================================
    async def start(self):
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", 8080)
        await site.start()
        logger.info("🚀 API Server 8080-portda ishga tushdi")