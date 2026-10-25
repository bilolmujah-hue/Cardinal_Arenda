# db.py
import asyncpg
import json
import logging
import os
from datetime import datetime, timedelta
from config import DB

logger = logging.getLogger("DB")


class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        # Railway avtomatik beradigan DATABASE_URL ni tekshiramiz
        db_url = os.getenv("DATABASE_URL")

        # Agar Railway'da bo'lsa, shu orqali ulanadi (xatosiz usul)
        if db_url:
            # asyncpg ba'zan postgres:// ni tushunmaydi, postgresql:// ga o'zgartiramiz
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql://", 1)

            logger.info("🌐 Railway DATABASE_URL orqali ulanmoqda...")
            self.pool = await asyncpg.create_pool(
                dsn=db_url,
                min_size=5, max_size=20
            )
        else:
            # O'z kompyuterda test qilish uchun config.py dan oladi
            logger.info("💻 Lokal config.py orqali ulanmoqda...")
            self.pool = await asyncpg.create_pool(
                host=DB.HOST, port=DB.PORT, database=DB.NAME,
                user=DB.USER, password=DB.PASSWORD,
                min_size=5, max_size=20
            )

        logger.info("✅ PostgreSQL ulandi!")
        await self.create_tables()

    async def close(self):
        if self.pool:
            await self.pool.close()

    # ============================================================
    # JADVALLARNI YARATISH
    # ============================================================
    async def create_tables(self):
        async with self.pool.acquire() as c:
            # 1. FOYDALANUVCHILAR
            await c.execute("""
                            CREATE TABLE IF NOT EXISTS users
                            (
                                id
                                SERIAL
                                PRIMARY
                                KEY,
                                tg_id
                                BIGINT
                                UNIQUE
                                NOT
                                NULL,
                                full_name
                                VARCHAR
                            (
                                255
                            ),
                                username VARCHAR
                            (
                                255
                            ),
                                phone VARCHAR
                            (
                                20
                            ),
                                balance BIGINT DEFAULT 0,
                                is_admin BOOLEAN DEFAULT FALSE,
                                is_verified BOOLEAN DEFAULT FALSE,
                                checkmark_type VARCHAR
                            (
                                20
                            ) DEFAULT 'none',
                                passport_file_id TEXT,
                                is_blocked BOOLEAN DEFAULT FALSE,
                                created_at TIMESTAMP DEFAULT NOW
                            (
                            )
                                );
                            """)

            # 2. AKKOUNTLAR
            await c.execute("""
                            CREATE TABLE IF NOT EXISTS accounts
                            (
                                id
                                SERIAL
                                PRIMARY
                                KEY,
                                acc_name
                                VARCHAR
                            (
                                50
                            ) UNIQUE NOT NULL,
                                account_type VARCHAR
                            (
                                20
                            ) DEFAULT 'webapp',
                                video_msg_id TEXT,
                                image_url TEXT,
                                details_text TEXT,
                                prices_json JSONB DEFAULT '{}'::jsonb,
                                is_active BOOLEAN DEFAULT TRUE,
                                created_at TIMESTAMP DEFAULT NOW
                            (
                            )
                                );
                            """)

            # 3. HARIDLAR (RENTALS)
            await c.execute("""
                            CREATE TABLE IF NOT EXISTS rentals
                            (
                                id
                                SERIAL
                                PRIMARY
                                KEY,
                                user_id
                                INTEGER
                                REFERENCES
                                users
                            (
                                id
                            ) ON DELETE CASCADE,
                                account_id INTEGER REFERENCES accounts
                            (
                                id
                            )
                              ON DELETE CASCADE,
                                duration_type VARCHAR
                            (
                                20
                            ),
                                price BIGINT NOT NULL,
                                start_time TIMESTAMP,
                                end_time TIMESTAMP,
                                status VARCHAR
                            (
                                20
                            ) DEFAULT 'pending',
                                reject_reason TEXT,
                                created_at TIMESTAMP DEFAULT NOW
                            (
                            )
                                );
                            """)

            # 4. TRANZAKSIYALAR
            await c.execute("""
                            CREATE TABLE IF NOT EXISTS transactions
                            (
                                id
                                SERIAL
                                PRIMARY
                                KEY,
                                user_id
                                INTEGER
                                REFERENCES
                                users
                            (
                                id
                            ) ON DELETE CASCADE,
                                amount BIGINT NOT NULL,
                                type VARCHAR
                            (
                                20
                            ) NOT NULL,
                                description TEXT,
                                status VARCHAR
                            (
                                20
                            ) DEFAULT 'success',
                                created_at TIMESTAMP DEFAULT NOW
                            (
                            )
                                );
                            """)

            # 5. TO'LOV SO'ROVLARI
            await c.execute("""
                            CREATE TABLE IF NOT EXISTS topup_requests
                            (
                                id
                                SERIAL
                                PRIMARY
                                KEY,
                                user_id
                                INTEGER
                                REFERENCES
                                users
                            (
                                id
                            ) ON DELETE CASCADE,
                                amount BIGINT NOT NULL,
                                card_number VARCHAR
                            (
                                20
                            ),
                                status VARCHAR
                            (
                                30
                            ) DEFAULT 'WAITING',
                                expires_at TIMESTAMP NOT NULL,
                                receipt_url TEXT,
                                created_at TIMESTAMP DEFAULT NOW
                            (
                            )
                                );
                            """)

            # 6. REYTING
            await c.execute("""
                            CREATE TABLE IF NOT EXISTS ratings
                            (
                                id
                                SERIAL
                                PRIMARY
                                KEY,
                                user_id
                                INTEGER
                                REFERENCES
                                users
                            (
                                id
                            ) ON DELETE CASCADE,
                                timeframe VARCHAR
                            (
                                20
                            ),
                                score BIGINT DEFAULT 0,
                                updated_at TIMESTAMP DEFAULT NOW
                            (
                            ),
                                UNIQUE
                            (
                                user_id,
                                timeframe
                            )
                                );
                            """)

            # 7. SOZLAMALAR
            await c.execute("""
                            CREATE TABLE IF NOT EXISTS settings
                            (
                                key
                                VARCHAR
                            (
                                100
                            ) PRIMARY KEY,
                                value TEXT
                                );
                            """)

    # ============================================================
    # FOYDALANUVCHILAR
    # ============================================================
    async def get_user(self, tg_id: int):
        async with self.pool.acquire() as c:
            u = await c.fetchrow("SELECT * FROM users WHERE tg_id=$1", tg_id)
            return dict(u) if u else None

    async def create_user(self, tg_id, full_name, username):
        async with self.pool.acquire() as c:
            await c.execute("""
                            INSERT INTO users (tg_id, full_name, username)
                            VALUES ($1, $2, $3) ON CONFLICT (tg_id) DO NOTHING
                            """, tg_id, full_name, username)

    async def update_balance(self, tg_id, amount, tx_type, desc):
        async with self.pool.acquire() as c:
            async with c.transaction():
                if tx_type == "topup":
                    await c.execute("UPDATE users SET balance = balance + $1 WHERE tg_id=$2", amount, tg_id)
                else:
                    await c.execute("UPDATE users SET balance = balance - $1 WHERE tg_id=$2", amount, tg_id)

                u = await c.fetchrow("SELECT id FROM users WHERE tg_id=$1", tg_id)
                await c.execute("""
                                INSERT INTO transactions (user_id, amount, type, description)
                                VALUES ($1, $2, $3, $4)
                                """, u['id'], amount, tx_type, desc)

                if tx_type == "topup":
                    await self._update_rating(c, u['id'], amount)

    async def _update_rating(self, conn, user_id, amount):
        for tf in ['week', 'month', 'all_time']:
            await conn.execute("""
                               INSERT INTO ratings (user_id, timeframe, score)
                               VALUES ($1, $2, $3) ON CONFLICT (user_id, timeframe) DO
                               UPDATE SET score = ratings.score + $3
                               """, user_id, tf, amount)

    async def set_checkmark(self, tg_id, mark_type):
        async with self.pool.acquire() as c:
            await c.execute("UPDATE users SET checkmark_type=$1, is_verified=TRUE WHERE tg_id=$2", mark_type, tg_id)

    async def save_passport(self, tg_id, file_id):
        async with self.pool.acquire() as c:
            await c.execute("UPDATE users SET passport_file_id=$1, is_verified=TRUE WHERE tg_id=$2", file_id, tg_id)

    # ============================================================
    # AKKOUNTLAR
    # ============================================================
    async def get_accounts(self, acc_type="webapp"):
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT * FROM accounts WHERE is_active=TRUE AND account_type=$1", acc_type)
            return [dict(r) for r in rows]

    async def create_account(self, acc_name, acc_type, video_msg_id, image_url, details_text, prices_json):
        async with self.pool.acquire() as c:
            await c.execute("""
                            INSERT INTO accounts (acc_name, account_type, video_msg_id, image_url, details_text,
                                                  prices_json)
                            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                            """, acc_name, acc_type, video_msg_id, image_url, details_text, json.dumps(prices_json))

    # ============================================================
    # HARIDLAR
    # ============================================================
    async def create_rental(self, tg_id, account_id, duration_type, price):
        async with self.pool.acquire() as c:
            async with c.transaction():
                u = await c.fetchrow("SELECT id FROM users WHERE tg_id=$1", tg_id)
                await c.execute("UPDATE users SET balance = balance - $1 WHERE id=$2", price, u['id'])
                await c.execute("""
                                INSERT INTO transactions (user_id, amount, type, description)
                                VALUES ($1, $2, 'rent', 'Arenda to''lovi')
                                """, u['id'], price)

                rid = await c.fetchval("""
                                       INSERT INTO rentals (user_id, account_id, duration_type, price, status)
                                       VALUES ($1, $2, $3, $4, 'pending') RETURNING id
                                       """, u['id'], account_id, duration_type, price)
                return rid

    async def approve_rental(self, rental_id, start_time):
        async with self.pool.acquire() as c:
            r = await c.fetchrow("SELECT duration_type FROM rentals WHERE id=$1", rental_id)
            hours = 24 if r['duration_type'] == 'night' else int(r['duration_type'])

            if r['duration_type'] == 'night':
                end_time = start_time + timedelta(hours=11)
            else:
                end_time = start_time + timedelta(hours=hours)

            await c.execute("""
                            UPDATE rentals
                            SET status='active',
                                start_time=$1,
                                end_time=$2
                            WHERE id = $3
                            """, start_time, end_time, rental_id)

    async def reject_rental(self, rental_id, reason):
        async with self.pool.acquire() as c:
            async with c.transaction():
                r = await c.fetchrow("SELECT user_id, price FROM rentals WHERE id=$1", rental_id)
                await c.execute("UPDATE users SET balance = balance + $1 WHERE id=$2", r['price'], r['user_id'])
                await c.execute("""
                                INSERT INTO transactions (user_id, amount, type, description)
                                VALUES ($1, $2, 'refund', 'Arenda rad etildi')
                                """, r['user_id'], r['price'])

                await c.execute("UPDATE rentals SET status='rejected', reject_reason=$1 WHERE id=$2", reason, rental_id)

    # ============================================================
    # STATISTIKA VA REYTING
    # ============================================================
    async def get_top_rating(self, timeframe, limit=50):
        async with self.pool.acquire() as c:
            rows = await c.fetch("""
                                 SELECT r.score, u.full_name, u.username, u.checkmark_type, u.is_verified
                                 FROM ratings r
                                          JOIN users u ON u.id = r.user_id
                                 WHERE r.timeframe = $1
                                 ORDER BY r.score DESC LIMIT $2
                                 """, timeframe, limit)
            return [dict(r) for r in rows]

    async def get_admin_stats(self):
        async with self.pool.acquire() as c:
            users = await c.fetchval("SELECT COUNT(*) FROM users")
            active_rentals = await c.fetchval("SELECT COUNT(*) FROM rentals WHERE status='active'")
            total_income = await c.fetchval("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='rent'")
            return {"users": users, "active_rentals": active_rentals, "total_income": total_income}


# Baza obyekti
db = Database()