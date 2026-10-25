# api.py
import os
import json
import hmac
import hashlib
import logging
import asyncio
from datetime import datetime, timedelta
from urllib.parse import parse_qsl

from aiohttp import web
import aiohttp_cors
import jwt

from config import BOT, JWT, DB
from db import db
from bot import send_rental_to_admin, bot

# Logging sozlamalari
logger = logging.getLogger("API")
logging.basicConfig(level=logging.INFO)


# ============================================================
# YORDAMCHI FUNKSIYALAR
# ============================================================
def json_ser(obj):
    if isinstance(obj, datetime): return obj.isoformat()
    raise TypeError(f"{type(obj)}")


def jresp(data, status=200):
    return web.json_response(
        data, status=status,
        dumps=lambda x: json.dumps(x, default=json_ser, ensure_ascii=False)
    )


def parse_range_header(range_header: str, file_size: int):
    """Video qidirish (seek) uchun Range headerini tahlil qilish"""
    if not range_header or not range_header.startswith("bytes="):
        return None
    try:
        ranges = range_header.replace("bytes=", "").split(",")
        first = ranges[0].strip()
        if "-" not in first: return None
        parts = first.split("-", 1)
        start_str = parts[0].strip()
        end_str = parts[1].strip() if len(parts) > 1 else ""

        if not start_str:
            length = int(end_str)
            start = max(0, file_size - length)
            end = file_size - 1
        elif not end_str:
            start = int(start_str)
            end = file_size - 1
        else:
            start = int(start_str)
            end = int(end_str)

        if start > end or start >= file_size: return None
        end = min(end, file_size - 1)
        return (start, end)
    except Exception:
        return None


def validate_telegram_data(init_data: str):
    """Telegram WebApp dan kelgan ma'lumotlarni HMAC-SHA256 orqali tekshirish"""
    try:
        parsed_data = dict(parse_qsl(init_data))
        if "hash" not in parsed_data: return None

        hash_ = parsed_data.pop("hash")
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))

        secret_key = hmac.new(b"WebAppData", BOT.TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if calculated_hash == hash_:
            return json.loads(parsed_data["user"])
        return None
    except Exception as e:
        logger.error(f"Auth xato: {e}")
        return None


def create_jwt(tg_id: int, is_admin: bool) -> str:
    payload = {
        "tg_id": tg_id,
        "is_admin": is_admin,
        "exp": datetime.utcnow() + timedelta(minutes=JWT.ACCESS_MINUTES)
    }
    return jwt.encode(payload, JWT.SECRET, algorithm=JWT.ALGORITHM)


# ============================================================
# API CLASS
# ============================================================
class API:
    def __init__(self, bot_instance, userbot_instance):
        self.bot = bot_instance
        self.userbot = userbot_instance
        self.app = web.Application(client_max_size=200 * 1024 * 1024, middlewares=[self._err_mw])
        self._routes()

    @web.middleware
    async def _err_mw(self, request, handler):
        try:
            return await handler(request)
        except web.HTTPException as e:
            return jresp({"ok": False, "error": e.reason}, e.status)
        except Exception as e:
            logger.error(f"API error: {e}", exc_info=True)
            return jresp({"ok": False, "error": str(e)}, 500)

    def _routes(self):
        # CORS sozlamalari
        cors = aiohttp_cors.setup(self.app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True, expose_headers="*", allow_headers="*", allow_methods="*"
            )
        })

        r = [
            # Auth & User
            ("POST", "/api/auth", self.auth),
            ("GET", "/api/profile", self.get_profile),
            # Accounts & Rent
            ("GET", "/api/accounts", self.get_accounts),
            ("POST", "/api/rent", self.create_rental),
            ("GET", "/api/my-rentals", self.my_rentals),
            # Rating
            ("GET", "/api/rating", self.get_rating),
            # Topup
            ("POST", "/api/topup/request", self.topup_request),
            ("GET", "/api/topup/status", self.topup_status),
            # Admin
            ("GET", "/api/admin/stats", self.admin_stats),
            ("GET", "/api/admin/search", self.admin_search),
            ("POST", "/api/admin/save-passport", self.admin_save_passport),
        ]

        for method, path, handler in r:
            route = self.app.router.add_route(method, path, handler)
            cors.add(route)

        # Video Stream route (HEAD bilan birga, video qidirish uchun)
        video_route = self.app.router.add_get("/api/video/{acc_id}", self.stream_video, allow_head=True)
        cors.add(video_route)

        # WebApp statik fayllarini ulash
        if os.path.exists("webapp"):
            self.app.router.add_static('/webapp/', path='webapp', name='webapp')

    # ============================================================
    # AUTH & USER
    # ============================================================
    def verify_jwt(self, request):
        auth = request.headers.get("Authorization")
        if not auth or not auth.startswith("Bearer "):
            raise web.HTTPUnauthorized(text=json.dumps({"error": "Token yo'q"}))
        try:
            return jwt.decode(auth.split(" ")[1], JWT.SECRET, algorithms=[JWT.ALGORITHM])
        except jwt.ExpiredSignatureError:
            raise web.HTTPUnauthorized(text=json.dumps({"error": "Token muddati o'tgan"}))
        except jwt.InvalidTokenError:
            raise web.HTTPUnauthorized(text=json.dumps({"error": "Noto'g'ri token"}))

    async def auth(self, request):
        data = await request.json()
        init_data = data.get("initData")

        tg_user = validate_telegram_data(init_data)
        if not tg_user:
            return jresp({"ok": False, "error": "Telegram ma'lumotlari xato"}, 403)

        tg_id = tg_user['id']
        user = await db.get_user(tg_id)
        if not user:
            await db.create_user(tg_id, tg_user.get('first_name', ''), tg_user.get('username', ''))
            user = await db.get_user(tg_id)

        if user['is_blocked']:
            return jresp({"ok": False, "error": "Siz bloklangansiz"}, 403)

        is_admin = user['is_admin'] or (tg_id == BOT.ADMIN_ID)
        token = create_jwt(tg_id, is_admin)

        return jresp({
            "ok": True, "token": token,
            "user": {
                "tg_id": tg_id,
                "name": user['full_name'],
                "balance": user['balance'],
                "is_admin": is_admin,
                "is_verified": user['is_verified'],
                "checkmark": user['checkmark_type'],
                "has_passport": bool(user['passport_file_id'])
            }
        })

    async def get_profile(self, request):
        payload = self.verify_jwt(request)
        user = await db.get_user(payload['tg_id'])
        return jresp({"ok": True, "user": user})

    # ============================================================
    # AKKOUNTLAR VA ARENDA
    # ============================================================
    async def get_accounts(self, request):
        # Web App uchun faqat 'webapp' turidagi akkountlar chiqadi
        accounts = await db.get_accounts(acc_type="webapp")

        async with db.pool.acquire() as c:
            for acc in accounts:
                # Narxlarni JSON dan dict ga o'tkazish
                acc['prices'] = acc['prices_json'] if acc['prices_json'] else {}
                del acc['prices_json']  # Keraksiz maydonni o'chirish

                # Aktiv haridni qidirish
                active_rent = await c.fetchrow("""
                                               SELECT end_time
                                               FROM rentals
                                               WHERE account_id = $1
                                                 AND status = 'active'
                                                 AND end_time > NOW()
                                               ORDER BY end_time DESC LIMIT 1
                                               """, acc['id'])

                if active_rent:
                    acc['status'] = 'busy'
                    acc['busy_until'] = active_rent['end_time'].isoformat() + "Z"
                else:
                    acc['status'] = 'free'
                    acc['busy_until'] = None

        return jresp({"ok": True, "accounts": accounts})

    async def create_rental(self, request):
        payload = self.verify_jwt(request)
        data = await request.json()

        acc_id = int(data.get("account_id"))
        duration = str(data.get("duration"))  # "2", "6", "night"

        async with db.pool.acquire() as c:
            # 1. Akkountni va narxini tekshirish
            acc = await c.fetchrow("SELECT * FROM accounts WHERE id=$1", acc_id)
            if not acc: return jresp({"ok": False, "error": "Akkount topilmadi"})

            prices = acc['prices_json'] if acc['prices_json'] else {}
            if duration not in prices: return jresp({"ok": False, "error": "Vaqt xato"})

            price = prices[duration]

            # 2. Balansni tekshirish
            user = await db.get_user(payload['tg_id'])
            if user['balance'] < price:
                return jresp({"ok": False, "error": "Balansingizda yetarli mablag' yo'q"})

            # 3. Bandligini qayta tekshirish (race condition oldini olish)
            is_busy = await c.fetchval("""
                                       SELECT COUNT(*)
                                       FROM rentals
                                       WHERE account_id = $1
                                         AND status = 'active'
                                         AND end_time > NOW()
                                       """, acc_id)
            if is_busy:
                return jresp({"ok": False, "error": "Akkount hozir band"})

            # 4. Haridni yaratish va pulni yechish
            rid = await db.create_rental(payload['tg_id'], acc_id, duration, price)

            # 5. Adminga xabar yuborish
            await send_rental_to_admin(
                rental_id=rid,
                user_name=user['full_name'],
                acc_name=acc['acc_name'],
                duration=duration,
                price=price,
                is_first_time=(not user['is_verified'])  # Agar tasdiqlanmagan bo'lsa pasport so'raladi
            )

            return jresp({"ok": True, "message": "Harid admin tasdiqlashiga yuborildi", "rental_id": rid})

    async def my_rentals(self, request):
        payload = self.verify_jwt(request)
        async with db.pool.acquire() as c:
            rows = await c.fetch("""
                                 SELECT r.*, a.acc_name
                                 FROM rentals r
                                          JOIN accounts a ON a.id = r.account_id
                                          JOIN users u ON u.id = r.user_id
                                 WHERE u.tg_id = $1
                                 ORDER BY r.created_at DESC
                                 """, payload['tg_id'])

            rentals = [dict(r) for r in rows]
            return jresp({"ok": True, "rentals": rentals})

    # ============================================================
    # REYTING
    # ============================================================
    async def get_rating(self, request):
        timeframe = request.query.get("timeframe", "week")  # week, month, all_time
        top_50 = await db.get_top_rating(timeframe, limit=50)
        return jresp({"ok": True, "rating": top_50})

    # ============================================================
    # TO'LOV (BALANS TO'LDIRISH)
    # ============================================================
    async def topup_request(self, request):
        payload = self.verify_jwt(request)
        data = await request.json()
        amount = int(data.get("amount", 0))

        if amount < 5000:
            return jresp({"ok": False, "error": "Minimal 5,000 so'm"})

        # Foizlarni hisoblash
        bonus = 0
        if 100000 <= amount < 300000:
            bonus = int(amount * 0.10)
        elif 300000 <= amount < 500000:
            bonus = int(amount * 0.20)
        elif amount >= 500000:
            bonus = int(amount * 0.30)

        total_amount = amount + bonus

        async with db.pool.acquire() as c:
            # Bazadan aktiv kartani olish
            card = await c.fetchrow("SELECT value FROM settings WHERE key LIKE 'card_%' LIMIT 1")
            if not card: return jresp({"ok": False, "error": "To'lov kartasi topilmadi"})

            card_num = card['value']
            expires = datetime.now() + timedelta(minutes=10)

            # Eski kutayotgan so'rovlarni o'chirish
            await c.execute("""
                            UPDATE topup_requests
                            SET status='EXPIRED'
                            WHERE user_id = (SELECT id FROM users WHERE tg_id = $1)
                              AND status = 'WAITING'
                            """, payload['tg_id'])

            # Yangi so'rov yaratish
            req_id = await c.fetchval("""
                                      INSERT INTO topup_requests (user_id, amount, card_number, expires_at)
                                      VALUES ((SELECT id FROM users WHERE tg_id = $1), $2, $3, $4) RETURNING id
                                      """, payload['tg_id'], total_amount, card_num, expires)

            return jresp({
                "ok": True,
                "request_id": req_id,
                "amount": total_amount,
                "bonus": bonus,
                "card": card_num,
                "expires_at": expires.isoformat() + "Z"
            })

    async def topup_status(self, request):
        payload = self.verify_jwt(request)
        async with db.pool.acquire() as c:
            req = await c.fetchrow("""
                                   SELECT status, amount
                                   FROM topup_requests
                                   WHERE user_id = (SELECT id FROM users WHERE tg_id = $1)
                                   ORDER BY created_at DESC LIMIT 1
                                   """, payload['tg_id'])

            if not req: return jresp({"ok": True, "status": "none"})
            return jresp({"ok": True, "status": req['status'].lower(), "amount": req['amount']})

    # ============================================================
    # VIDEO STREAMING (Telethon orqali Telegramdan)
    # ============================================================
    async def stream_video(self, request):
        acc_id = int(request.match_info['acc_id'])
        is_head = (request.method == "HEAD")

        try:
            async with db.pool.acquire() as c:
                acc = await c.fetchrow("SELECT video_msg_id FROM accounts WHERE id=$1", acc_id)

            if not acc or not acc['video_msg_id']:
                return web.Response(status=404, text="Video topilmadi")

            msg_id = int(acc['video_msg_id'])

            if not self.userbot or not self.userbot.client:
                return web.Response(status=503, text="Userbot ulanmagan")

            msg = await self.userbot.client.get_messages(BOT.VIDEO_CHANNEL_ID, ids=msg_id)
            if not msg or not msg.media:
                return web.Response(status=404, text="Video topilmadi")

            file_size = getattr(msg.video or msg.document, 'size', 0)
            mime_type = getattr(msg.video or msg.document, 'mime_type', 'video/mp4')

            if is_head:
                resp = web.Response(status=200)
                resp.headers["Content-Type"] = mime_type
                resp.headers["Accept-Ranges"] = "bytes"
                resp.headers["Content-Length"] = str(file_size)
                return resp

            range_header = request.headers.get("Range")
            range_tuple = parse_range_header(range_header, file_size) if range_header else None

            if range_tuple:
                offset = range_tuple[0]
                limit = range_tuple[1] - range_tuple[0] + 1
                status_code = 206
            else:
                offset = 0
                limit = file_size
                status_code = 200

            resp = web.StreamResponse(status=status_code)
            resp.headers["Content-Type"] = mime_type
            resp.headers["Accept-Ranges"] = "bytes"
            resp.headers["Content-Disposition"] = "inline"
            resp.headers["Cache-Control"] = "public, max-age=3600"

            if range_tuple:
                s, e = range_tuple
                resp.headers["Content-Range"] = f"bytes {s}-{e}/{file_size}"
                resp.headers["Content-Length"] = str(limit)
            else:
                resp.headers["Content-Length"] = str(file_size)

            await resp.prepare(request)

            try:
                async for chunk in self.userbot.client.iter_download(
                        msg.media, offset=offset, limit=limit, chunk_size=512 * 1024
                ):
                    if chunk:
                        await resp.write(chunk)
                await resp.write_eof()
            except (ConnectionResetError, asyncio.CancelledError):
                pass

            return resp

        except Exception as e:
            logger.error(f"Stream xatosi: {e}")
            return web.Response(status=500, text="Server xatosi")

    # ============================================================
    # ADMIN (WebApp ichida)
    # ============================================================
    def check_admin(self, request):
        payload = self.verify_jwt(request)
        if not payload.get('is_admin'):
            raise web.HTTPForbidden(text=json.dumps({"error": "Ruxsat yo'q"}))
        return payload

    async def admin_stats(self, request):
        self.check_admin(request)
        stats = await db.get_admin_stats()
        return jresp({"ok": True, "stats": stats})

    async def admin_search(self, request):
        self.check_admin(request)
        query = request.query.get("q", "").strip()
        if not query: return jresp({"ok": False, "error": "Qidiruv so'zi bo'sh"})

        async with db.pool.acquire() as c:
            user = await c.fetchrow("""
                                    SELECT *
                                    FROM users
                                    WHERE tg_id::text = $1
                                       OR phone = $1
                                       OR full_name ILIKE $2
                                        LIMIT 1
                                    """, query, f"%{query}%")

            if not user: return jresp({"ok": False, "error": "Foydalanuvchi topilmadi"})
            return jresp({"ok": True, "user": dict(user)})

    async def admin_save_passport(self, request):
        self.check_admin(request)
        data = await request.json()
        tg_id = int(data.get("tg_id"))
        file_id = data.get("file_id")  # Telethon yoki Bot orqali yuklangan rasm ID

        await db.save_passport(tg_id, file_id)

        # Userga xabar yuborish
        try:
            await self.bot.send_message(tg_id, "✅ <b>Profilingiz admin tomonidan tasdiqlandi!</b>", parse_mode="HTML")
        except:
            pass

        return jresp({"ok": True})


# ============================================================
# SERVERNI ISHGA TUSHIRISH
# ============================================================
async def start_api(bot_instance, userbot_instance):
    api = API(bot_instance, userbot_instance)
    runner = web.AppRunner(api.app)
    await runner.setup()

    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🚀 API Server ishga tushdi: http://0.0.0.0:{port}")