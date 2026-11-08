"""
Cardinal Arenda - Database Manager v1.0
=======================================
Ushbu fayl PostgreSQL ma'lumotlar bazasi bilan ishlash uchun xizmat qiladi.
Tizimning barcha jadvallari, CRUD amallari va murakkab mantiqiy so'rovlar shu yerda.
"""

import asyncpg
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
from config import DB, LIMITS, DEFAULT_AD_DAYS

logger = logging.getLogger("Database")

class Database:
    """
    Asosiy ma'lumotlar bazasi klassi.
    Barcha jadvallar bilan ishlash uchun yagona nuqta.
    """
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    # ============================================================
    # ULANISH VA YOPISH (CONNECTION MANAGEMENT)
    # ============================================================
    async def connect(self):
        """
        PostgreSQL bazasiga ulanish poolini yaratish.
        Railway uchun maxsus sozlamalar bilan.
        """
        try:
            self.pool = await asyncpg.create_pool(
                host=DB.HOST,
                port=DB.PORT,
                database=DB.NAME,
                user=DB.USER,
                password=DB.PASSWORD,
                min_size=5,
                max_size=50,
                command_timeout=60,
            )
            logger.info("✅ PostgreSQL muvaffaqiyatli ulandi")
        except Exception as e:
            logger.error(f"❌ PostgreSQL ulanish xatosi: {e}")
            raise e

    async def close(self):
        """Bazadan uzilish va resurslarni bo'shatish."""
        if self.pool:
            await self.pool.close()
            logger.info("🔌 PostgreSQL ulanishi yopildi")

    # ============================================================
    # JADVALLARNI YARATISH (TABLE CREATION & MIGRATIONS)
    # ============================================================
    async def create_tables(self):
        """
        Barcha kerakli jadvallarni yaratish va mavjudlarini yangilash (migratsiya).
        Bu funksiya bot ishga tushganda 1 marta chaqiriladi.
        """
        logger.info("⏳ Jadvallar tekshirilmoqda va yaratilmoqda...")
        async with self.pool.acquire() as c:

            # 1. USERS (Foydalanuvchilar) jadvali
            await c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    username VARCHAR(255), 
                    first_name VARCHAR(255), 
                    last_name VARCHAR(255),
                    phone VARCHAR(20), 
                    password_hash VARCHAR(255),
                    balance BIGINT DEFAULT 0, 
                    total_spent BIGINT DEFAULT 0,
                    avatar TEXT, 
                    is_registered BOOLEAN DEFAULT FALSE,
                    is_admin BOOLEAN DEFAULT FALSE, 
                    is_blocked BOOLEAN DEFAULT FALSE,
                    passport_img TEXT, 
                    is_verified BOOLEAN DEFAULT FALSE,
                    badge VARCHAR(20) DEFAULT 'none',
                    created_at TIMESTAMP DEFAULT NOW(), 
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """)

            # 2. ACCOUNTS (Arendaga beriladigan PUBG akkauntlari)
            await c.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id SERIAL PRIMARY KEY,
                    account_no INTEGER UNIQUE NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    description TEXT,
                    video_id TEXT,
                    photo_id TEXT,
                    prices JSONB DEFAULT '{}'::jsonb,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """)

            # 3. RENTALS (Arenda tarixi va faol arendalar)
            await c.execute("""
                CREATE TABLE IF NOT EXISTS rentals (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP NOT NULL,
                    price BIGINT NOT NULL,
                    status VARCHAR(20) DEFAULT 'PENDING', 
                    passport_img TEXT, 
                    reject_reason TEXT,
                    admin_note TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """)

            # 4. TOPUPS (Balans to'ldirish so'rovlari)
            await c.execute("""
                CREATE TABLE IF NOT EXISTS topups (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    amount BIGINT NOT NULL,
                    card_number VARCHAR(20) NOT NULL,
                    card_holder VARCHAR(100),
                    status VARCHAR(30) DEFAULT 'WAITING', 
                    receipt_img TEXT, 
                    expires_at TIMESTAMP NOT NULL,
                    matched_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    reject_reason TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)

            # 5. SETTINGS (Admin sozlamalari)
            await c.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key VARCHAR(100) PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """)

            # 6. ADMIN_CONTACTS (Yordam uchun adminlar)
            await c.execute("""
                CREATE TABLE IF NOT EXISTS admin_contacts (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT UNIQUE NOT NULL,
                    username VARCHAR(255), 
                    first_name VARCHAR(255), 
                    last_name VARCHAR(255),
                    role VARCHAR(100) DEFAULT 'Admin',
                    info TEXT, 
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)

            # 7. CARDS (To'lov uchun plastik kartalar)
            await c.execute("""
                CREATE TABLE IF NOT EXISTS cards (
                    id SERIAL PRIMARY KEY,
                    number VARCHAR(20) UNIQUE NOT NULL,
                    holder VARCHAR(100),
                    is_active BOOLEAN DEFAULT TRUE,
                    total_received BIGINT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)

            # 8. USERBOT_SESSIONS (Telethon sessiyasi)
            await c.execute("""
                CREATE TABLE IF NOT EXISTS userbot_sessions (
                    id SERIAL PRIMARY KEY,
                    phone VARCHAR(20) NOT NULL,
                    session_string TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)

        # Migratsiyalarni ishga tushirish (agar eski jadval bo'lsa, yangi ustunlar qo'shish)
        await self._run_migrations()
        await self._seed_default_settings()
        logger.info("✅ Barcha jadvallar tayyor!")

    async def _run_migrations(self):
        """Eski bazalarni yangilash uchun xavfsiz migratsiyalar"""
        migrations = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS badge VARCHAR(20) DEFAULT 'none'",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS passport_img TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE",
            "ALTER TABLE rentals ADD COLUMN IF NOT EXISTS passport_img TEXT",
            "ALTER TABLE topups ADD COLUMN IF NOT EXISTS receipt_img TEXT",
        ]
        async with self.pool.acquire() as c:
            for sql in migrations:
                try:
                    await c.execute(sql)
                except Exception as e:
                    logger.warning(f"Migration o'tkazib yuborildi: {e}")

    async def _seed_default_settings(self):
        """Standart sozlamalarni bazaga yozish"""
        async with self.pool.acquire() as c:
            await c.execute("""
                INSERT INTO settings (key, value) VALUES ('rent_days_limit', '30')
                ON CONFLICT (key) DO NOTHING
            """)
            await c.execute("""
                INSERT INTO settings (key, value) VALUES ('payment_timeout', '10')
                ON CONFLICT (key) DO NOTHING
            """)

    # ============================================================
    # SOZLAMALAR BILAN ISHLASH (SETTINGS)
    # ============================================================
    async def get_setting(self, key: str, default: Any = None) -> Any:
        """Bazadan bitta sozlamani olish"""
        async with self.pool.acquire() as c:
            r = await c.fetchrow("SELECT value FROM settings WHERE key=$1", key)
            return r["value"] if r else default

    async def set_setting(self, key: str, value: Any) -> bool:
        """Bazaga sozlama yozish yoki yangilash"""
        async with self.pool.acquire() as c:
            await c.execute("""
                INSERT INTO settings (key, value) VALUES ($1, $2)
                ON CONFLICT (key) DO UPDATE SET value=$2, updated_at=NOW()
            """, key, str(value))
            return True

    # ============================================================
    # FOYDALANUVCHILAR (USERS)
    # ============================================================
    async def get_or_create_user(self, telegram_id: int, username: str = None, first_name: str = None, last_name: str = None) -> Dict:
        """Foydalanuvchini topish yoki yangisini yaratish"""
        async with self.pool.acquire() as c:
            u = await c.fetchrow("SELECT * FROM users WHERE telegram_id=$1", telegram_id)
            if not u:
                # Agar foydalanuvchi bo'lmasa, yaratamiz
                is_admin = (telegram_id == 7038296036) # Asosiy admin
                u = await c.fetchrow("""
                    INSERT INTO users (telegram_id, username, first_name, last_name, is_admin)
                    VALUES ($1, $2, $3, $4, $5) RETURNING *
                """, telegram_id, username, first_name, last_name, is_admin)
            else:
                # Agar bo'lsa, ma'lumotlarini yangilaymiz
                await c.execute("""
                    UPDATE users SET username=$1, first_name=$2, last_name=$3, updated_at=NOW() 
                    WHERE telegram_id=$4
                """, username, first_name, last_name, telegram_id)
            return dict(u)

    async def get_user(self, telegram_id: int) -> Optional[Dict]:
        """Telegram ID orqali foydalanuvchini olish"""
        async with self.pool.acquire() as c:
            u = await c.fetchrow("SELECT * FROM users WHERE telegram_id=$1", telegram_id)
            return dict(u) if u else None

    async def update_user_phone(self, telegram_id: int, phone: str) -> bool:
        """Foydalanuvchining telefon raqamini saqlash"""
        async with self.pool.acquire() as c:
            await c.execute("""
                UPDATE users SET phone=$1, is_registered=TRUE, updated_at=NOW() 
                WHERE telegram_id=$2
            """, phone, telegram_id)
            return True

    async def update_balance(self, telegram_id: int, amount: int, action: str = "add") -> int:
        """
        Balansni yangilash.
        action = 'add' (qo'shish) yoki 'subtract' (ayirish)
        """
        async with self.pool.acquire() as c:
            if action == "add":
                await c.execute("UPDATE users SET balance=balance+$1 WHERE telegram_id=$2", amount, telegram_id)
            elif action == "subtract":
                await c.execute("UPDATE users SET balance=balance-$1, total_spent=total_spent+$1 WHERE telegram_id=$2", amount, telegram_id)

            # Yangi balansni qaytaramiz
            res = await c.fetchrow("SELECT balance FROM users WHERE telegram_id=$1", telegram_id)
            return res["balance"] if res else 0

    async def update_user_badge(self, telegram_id: int, badge: str) -> bool:
        """Foydalanuvchiga galichka (badge) berish: 'blue', 'yellow', 'black'"""
        async with self.pool.acquire() as c:
            await c.execute("UPDATE users SET badge=$1 WHERE telegram_id=$2", badge, telegram_id)
            return True

    async def verify_user_passport(self, telegram_id: int, passport_img: str) -> bool:
        """Foydalanuvchi pasportini tasdiqlash (Ko'k galichka uchun)"""
        async with self.pool.acquire() as c:
            await c.execute("""
                UPDATE users SET passport_img=$1, is_verified=TRUE, badge='blue' 
                WHERE telegram_id=$2
            """, passport_img, telegram_id)
            return True

    # ============================================================
    # AKKOUNTLAR (PUBG ACCOUNTS)
    # ============================================================
    async def add_account(self, account_no: int, title: str, description: str, video_id: str, prices: Dict) -> int:
        """Yangi PUBG akkauntini arendaga qo'shish"""
        async with self.pool.acquire() as c:
            prices_json = json.dumps(prices, ensure_ascii=False)
            acc_id = await c.fetchval("""
                INSERT INTO accounts (account_no, title, description, video_id, prices)
                VALUES ($1, $2, $3, $4, $5::jsonb) RETURNING id
            """, account_no, title, description, video_id, prices_json)
            return acc_id

    async def get_all_accounts(self) -> List[Dict]:
        """Barcha arendagi akkauntlarni olish"""
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT * FROM accounts WHERE is_active=TRUE ORDER BY account_no")
            return [dict(r) for r in rows]

    async def get_account(self, account_id: int) -> Optional[Dict]:
        """Bitta akkaunt ma'lumotlarini olish"""
        async with self.pool.acquire() as c:
            r = await c.fetchrow("SELECT * FROM accounts WHERE id=$1", account_id)
            if r:
                d = dict(r)
                d["prices"] = json.loads(d["prices"]) if isinstance(d["prices"], str) else d["prices"]
                return d
            return None

    async def check_account_availability(self, account_id: int, start_time: datetime, end_time: datetime) -> bool:
        """
        Akkaunt aynan shu vaqt oralig'ida bo'shligini tekshirish.
        Agar band bo'lsa False qaytaradi.
        """
        async with self.pool.acquire() as c:
            # Vaqtlar kesishishini tekshirish formulasi: (StartA <= EndB) and (EndA >= StartB)
            conflict = await c.fetchval("""
                SELECT COUNT(*) FROM rentals 
                WHERE account_id=$1 
                  AND status IN ('ACTIVE', 'PENDING')
                  AND (start_time <= $3 AND end_time >= $2)
            """, account_id, start_time, end_time)
            return conflict == 0

    # ============================================================
    # ARENDA (RENTALS)
    # ============================================================
    async def create_rental_request(self, telegram_id: int, account_id: int, start_time: datetime, end_time: datetime, price: int) -> int:
        """Arenda so'rovini yaratish (Admin tasdiqlashini kutadi)"""
        async with self.pool.acquire() as c:
            user = await self.get_user(telegram_id)
            if not user: return 0

            rental_id = await c.fetchval("""
                INSERT INTO rentals (user_id, account_id, start_time, end_time, price, status)
                VALUES ($1, $2, $3, $4, $5, 'PENDING') RETURNING id
            """, user["id"], account_id, start_time, end_time, price)
            return rental_id

    async def get_user_rentals(self, telegram_id: int) -> List[Dict]:
        """Foydalanuvchining barcha arendalari tarixi"""
        async with self.pool.acquire() as c:
            user = await self.get_user(telegram_id)
            if not user: return []
            rows = await c.fetch("""
                SELECT r.*, a.account_no, a.title as account_title 
                FROM rentals r
                JOIN accounts a ON a.id = r.account_id
                WHERE r.user_id=$1 ORDER BY r.created_at DESC
            """, user["id"])
            return [dict(r) for r in rows]

    async def get_pending_rentals(self) -> List[Dict]:
        """Admin tasdiqlashi kerak bo'lgan barcha arendalar"""
        async with self.pool.acquire() as c:
            rows = await c.fetch("""
                SELECT r.*, u.telegram_id, u.first_name, u.phone, a.account_no
                FROM rentals r
                JOIN users u ON u.id = r.user_id
                JOIN accounts a ON a.id = r.account_id
                WHERE r.status='PENDING' ORDER BY r.created_at ASC
            """)
            return [dict(r) for r in rows]

    async def approve_rental(self, rental_id: int) -> bool:
        """Admin arendani tasdiqlaydi"""
        async with self.pool.acquire() as c:
            await c.execute("UPDATE rentals SET status='ACTIVE', updated_at=NOW() WHERE id=$1", rental_id)
            return True

    async def reject_rental(self, rental_id: int, reason: str) -> bool:
        """Admin arendani rad etadi va pulni qaytaradi"""
        async with self.pool.acquire() as c:
            async with c.transaction():
                # 1. Arendani rad etish
                rental = await c.fetchrow("SELECT * FROM rentals WHERE id=$1", rental_id)
                if not rental: return False

                await c.execute("UPDATE rentals SET status='REJECTED', reject_reason=$1 WHERE id=$2", reason, rental_id)

                # 2. Pulni foydalanuvchi balansiga qaytarish
                await c.execute("UPDATE users SET balance=balance+$1 WHERE id=$2", rental["price"], rental["user_id"])
            return True

    async def get_active_rentals(self) -> List[Dict]:
        """Hozirgi vaqtda faol bo'lgan barcha arendalar (Tugash vaqti kelganini aniqlash uchun)"""
        async with self.pool.acquire() as c:
            rows = await c.fetch("""
                SELECT r.*, u.telegram_id, a.account_no
                FROM rentals r
                JOIN users u ON u.id = r.user_id
                JOIN accounts a ON a.id = r.account_id
                WHERE r.status='ACTIVE' AND r.end_time <= NOW()
            """)
            return [dict(r) for r in rows]

    async def complete_rental(self, rental_id: int) -> bool:
        """Arenda vaqti tugaganda statusni COMPLETED ga o'zgartirish"""
        async with self.pool.acquire() as c:
            await c.execute("UPDATE rentals SET status='COMPLETED', updated_at=NOW() WHERE id=$1", rental_id)
            return True

    # ============================================================
    # TO'LOVLAR (TOPUPS & USERBOT LOGIC)
    # ============================================================
    async def create_topup(self, telegram_id: int, amount: int, card_number: str, card_holder: str, timeout_min: int = 10) -> int:
        """To'lov so'rovini yaratish (10 daqiqalik taymer bilan)"""
        async with self.pool.acquire() as c:
            user = await self.get_user(telegram_id)
            if not user: return 0

            # Eski kutayotgan to'lovlarni bekor qilamiz
            await c.execute("""
                UPDATE topups SET status='CANCELLED' 
                WHERE user_id=$1 AND status IN ('WAITING', 'RECEIPT_UPLOADED')
            """, user["id"])

            expires = datetime.now() + timedelta(minutes=timeout_min)
            topup_id = await c.fetchval("""
                INSERT INTO topups (user_id, amount, card_number, card_holder, expires_at, status)
                VALUES ($1, $2, $3, $4, $5, 'WAITING') RETURNING id
            """, user["id"], amount, card_number, card_holder, expires)
            return topup_id

    async def match_payment(self, amount: int, card_last4: str) -> Dict:
        """
        Userbot tomonidan chaqiriladi. Karta oxirgi 4 raqami va summaga qarab to'lovni topadi.
        """
        async with self.pool.acquire() as c:
            req = await c.fetchrow("""
                SELECT * FROM topups
                WHERE amount=$1 AND status='WAITING' AND expires_at > NOW()
                  AND RIGHT (card_number, 4) = $2
                ORDER BY created_at ASC LIMIT 1
            """, amount, card_last4)

            if not req:
                return {"ok": False, "reason": "no_match"}

            # Topildi! Statusni MATCHED ga o'zgartiramiz
            await c.execute("UPDATE topups SET status='MATCHED', matched_at=NOW() WHERE id=$1", req["id"])

            # Foydalanuvchi ma'lumotlarini olamiz
            u = await c.fetchrow("SELECT * FROM users WHERE id=$1", req["user_id"])

            return {
                "ok": True,
                "topup_id": req["id"],
                "user_tg": u["telegram_id"],
                "amount": amount
            }

    async def submit_receipt(self, topup_id: int, receipt_img: str) -> bool:
        """Foydalanuvchi chekni yuklaganda"""
        async with self.pool.acquire() as c:
            await c.execute("""
                UPDATE topups SET receipt_img=$1,status='RECEIPT_UPLOADED' 
                WHERE id=$2 AND status IN ('WAITING', 'MATCHED')
            """, receipt_img, topup_id)
            return True

    async def approve_topup(self, topup_id: int) -> bool:
        """Admin chekni tasdiqlaydi va balansga qo'shadi"""
        async with self.pool.acquire() as c:
            async with c.transaction():
                topup = await c.fetchrow("SELECT * FROM topups WHERE id=$1", topup_id)
                if not topup or topup["status"] == "COMPLETED":
                    return False

                # 1. Statusni COMPLETED qilish
                await c.execute("UPDATE topups SET status='COMPLETED', completed_at=NOW() WHERE id=$1", topup_id)

                # 2. Balansga qo'shish
                await c.execute("UPDATE users SET balance=balance+$1 WHERE id=$2", topup["amount"], topup["user_id"])

                # 3. Karta hisobiga qo'shish
                await c.execute("""
                    UPDATE cards SET total_received=total_received+$1 
                    WHERE RIGHT(number, 4) = RIGHT($2, 4)
                """, topup["amount"], topup["card_number"])
            return True

    async def cancel_topup(self, telegram_id: int) -> bool:
        """Foydalanuvchi to'lovni bekor qilganda"""
        async with self.pool.acquire() as c:
            user = await self.get_user(telegram_id)
            if not user: return False
            await c.execute("""
                UPDATE topups SET status='CANCELLED' 
                WHERE user_id=$1 AND status IN ('WAITING', 'MATCHED', 'RECEIPT_UPLOADED')
            """, user["id"])
            return True

    # ============================================================
    # REYTING VA STATISTIKA
    # ============================================================
    async def get_top_users(self, period: str = "all", limit: int = 50) -> List[Dict]:
        """
        Reyting uchun eng ko'p pul to'ldirgan foydalanuvchilar.
        period: 'week', 'month', 'all'
        """
        async with self.pool.acquire() as c:
            if period == "week":
                time_cond = "AND t.completed_at >= NOW() - INTERVAL '7 days'"
            elif period == "month":
                time_cond = "AND t.completed_at >= NOW() - INTERVAL '30 days'"
            else:
                time_cond = ""

            query = f"""
                SELECT u.telegram_id, u.first_name, u.username, u.badge,
                       SUM(t.amount) as total_amount
                FROM topups t
                JOIN users u ON u.id = t.user_id
                WHERE t.status='COMPLETED' {time_cond}
                GROUP BY u.id
                ORDER BY total_amount DESC
                LIMIT $1
            """
            rows = await c.fetch(query, limit)
            return [dict(r) for r in rows]

    async def get_stats(self) -> Dict:
        """Admin panel uchun umumiy statistika"""
        async with self.pool.acquire() as c:
            return {
                "users": await c.fetchval("SELECT COUNT(*) FROM users"),
                "accounts": await c.fetchval("SELECT COUNT(*) FROM accounts WHERE is_active=TRUE"),
                "active_rentals": await c.fetchval("SELECT COUNT(*) FROM rentals WHERE status='ACTIVE'"),
                "pending_rentals": await c.fetchval("SELECT COUNT(*) FROM rentals WHERE status='PENDING'"),
                "total_balance": await c.fetchval("SELECT COALESCE(SUM(balance),0) FROM users"),
            }