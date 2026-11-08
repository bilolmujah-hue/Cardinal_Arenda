"""
Cardinal Arenda - Database Manager (TO'LIQ VA MUKAMMAL v4.0)
===========================================================
Ushbu fayl barcha ma'lumotlar bazasi amallarini bajaradi.
Railway'ning DATABASE_URL manzilini to'g'ri o'qiydi va barcha jadvallarni yaratadi.
"""

import asyncpg
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

# Loggingni sozlash
logger = logging.getLogger("Database")


class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    # ============================================================
    # 1. ULANISH VA YOPISH (CONNECTION)
    # ============================================================
    async def connect(self):
        """
        PostgreSQL bazasiga ulanish.
        Railway bergan DATABASE_URL ni avtomatik o'qiydi va formatlaydi.
        """
        try:
            # Railway beradigan manzilni olamiz
            db_url = os.getenv("DATABASE_URL")

            if not db_url:
                raise ValueError("❌ DATABASE_URL topilmadi! Railway'da Variables bo'limini tekshiring.")

            # Boshidagi va oxiridagi bo'sh joylarni tozalaymiz
            db_url = db_url.strip()

            # asyncpg "postgres://" ni tushunmaydi, shuning uchun almashtiramiz
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql://", 1)

            # Ulanishni yaratamiz
            self.pool = await asyncpg.create_pool(
                dsn=db_url,
                min_size=2,
                max_size=20,
                command_timeout=60
            )
            logger.info("✅ PostgreSQL bazasiga muvaffaqiyatli ulandi! (DATABASE_URL orqali)")

        except Exception as e:
            logger.error(f"❌ PostgreSQL ulanish xatosi: {e}")
            raise e

    async def close(self):
        """Bazadan uzilish."""
        if self.pool:
            await self.pool.close()
            logger.info("🔌 PostgreSQL ulanishi yopildi.")

    # ============================================================
    # 2. JADVALLARNI YARATISH (TABLES)
    # ============================================================
    async def create_tables(self):
        """Barcha kerakli jadvallarni yaratish."""
        logger.info("⏳ Jadvallar tekshirilmoqda...")
        async with self.pool.acquire() as c:
            # FOYDALANUVCHILAR (USERS)
            await c.execute("""
                            CREATE TABLE IF NOT EXISTS users
                            (
                                id
                                SERIAL
                                PRIMARY
                                KEY,
                                telegram_id
                                BIGINT
                                UNIQUE
                                NOT
                                NULL,
                                username
                                VARCHAR
                            (
                                255
                            ),
                                first_name VARCHAR
                            (
                                255
                            ),
                                last_name VARCHAR
                            (
                                255
                            ),
                                phone VARCHAR
                            (
                                20
                            ),
                                balance BIGINT DEFAULT 0,
                                total_spent BIGINT DEFAULT 0,
                                avatar TEXT,
                                is_registered BOOLEAN DEFAULT FALSE,
                                is_admin BOOLEAN DEFAULT FALSE,
                                is_blocked BOOLEAN DEFAULT FALSE,
                                passport_img TEXT,
                                is_verified BOOLEAN DEFAULT FALSE,
                                badge VARCHAR
                            (
                                20
                            ) DEFAULT 'none',
                                created_at TIMESTAMP DEFAULT NOW
                            (
                            ),
                                updated_at TIMESTAMP DEFAULT NOW
                            (
                            )
                                );
                            """)

            # AKKOUNTLAR (ACCOUNTS)
            await c.execute("""
                            CREATE TABLE IF NOT EXISTS accounts
                            (
                                id
                                SERIAL
                                PRIMARY
                                KEY,
                                account_no
                                INTEGER
                                UNIQUE
                                NOT
                                NULL,
                                title
                                VARCHAR
                            (
                                255
                            ) NOT NULL,
                                description TEXT,
                                video_id TEXT,
                                photo_id TEXT,
                                prices JSONB DEFAULT '{}'::jsonb,
                                is_active BOOLEAN DEFAULT TRUE,
                                created_at TIMESTAMP DEFAULT NOW
                            (
                            ),
                                updated_at TIMESTAMP DEFAULT NOW
                            (
                            )
                                );
                            """)

            # ARENDALAR (RENTALS)
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
                                start_time TIMESTAMP NOT NULL,
                                end_time TIMESTAMP NOT NULL,
                                price BIGINT NOT NULL,
                                status VARCHAR
                            (
                                20
                            ) DEFAULT 'PENDING',
                                reject_reason TEXT,
                                created_at TIMESTAMP DEFAULT NOW
                            (
                            ),
                                updated_at TIMESTAMP DEFAULT NOW
                            (
                            )
                                );
                            """)

            # TO'LOVLAR (TOPUPS)
            await c.execute("""
                            CREATE TABLE IF NOT EXISTS topups
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
                            ) NOT NULL,
                                card_holder VARCHAR
                            (
                                100
                            ),
                                status VARCHAR
                            (
                                30
                            ) DEFAULT 'WAITING',
                                receipt_img TEXT,
                                expires_at TIMESTAMP NOT NULL,
                                matched_at TIMESTAMP,
                                completed_at TIMESTAMP,
                                reject_reason TEXT,
                                created_at TIMESTAMP DEFAULT NOW
                            (
                            )
                                );
                            """)

            # SOZLAMALAR (SETTINGS)
            await c.execute("""
                            CREATE TABLE IF NOT EXISTS settings
                            (
                                key
                                VARCHAR
                            (
                                100
                            ) PRIMARY KEY,
                                value TEXT,
                                updated_at TIMESTAMP DEFAULT NOW
                            (
                            )
                                );
                            """)

            # KARTALAR (CARDS)
            await c.execute("""
                            CREATE TABLE IF NOT EXISTS cards
                            (
                                id
                                SERIAL
                                PRIMARY
                                KEY,
                                number
                                VARCHAR
                            (
                                20
                            ) UNIQUE NOT NULL,
                                holder VARCHAR
                            (
                                100
                            ),
                                total_received BIGINT DEFAULT 0,
                                created_at TIMESTAMP DEFAULT NOW
                            (
                            )
                                );
                            """)

            # USERBOT SESSIYASI
            await c.execute("""
                            CREATE TABLE IF NOT EXISTS userbot_sessions
                            (
                                id
                                SERIAL
                                PRIMARY
                                KEY,
                                phone
                                VARCHAR
                            (
                                20
                            ) NOT NULL,
                                session_string TEXT NOT NULL,
                                is_active BOOLEAN DEFAULT TRUE,
                                created_at TIMESTAMP DEFAULT NOW
                            (
                            )
                                );
                            """)

        await self._seed_default_settings()
        logger.info("✅ Barcha jadvallar muvaffaqiyatli yaratildi!")

    async def _seed_default_settings(self):
        """Boshlang'ich sozlamalarni yozish."""
        async with self.pool.acquire() as c:
            await c.execute(
                "INSERT INTO settings (key, value) VALUES ('rent_days_limit', '30') ON CONFLICT (key) DO NOTHING;")

    # ============================================================
    # 3. SOZLAMALAR (SETTINGS)
    # ============================================================
    async def get_setting(self, key: str, default: Any = None) -> Any:
        async with self.pool.acquire() as c:
            r = await c.fetchrow("SELECT value FROM settings WHERE key=$1", key)
            return r["value"] if r else default

    async def set_setting(self, key: str, value: Any) -> bool:
        async with self.pool.acquire() as c:
            await c.execute("""
                            INSERT INTO settings (key, value)
                            VALUES ($1, $2) ON CONFLICT (key) DO
                            UPDATE SET value =$2, updated_at=NOW()
                            """, key, str(value))
            return True

    # ============================================================
    # 4. FOYDALANUVCHILAR (USERS)
    # ============================================================
    async def get_or_create_user(self, telegram_id: int, username: str = None, first_name: str = None,
                                 last_name: str = None) -> Dict:
        async with self.pool.acquire() as c:
            u = await c.fetchrow("SELECT * FROM users WHERE telegram_id=$1", telegram_id)
            if not u:
                is_admin = (telegram_id == 7038296036)  # Asosiy admin ID
                u = await c.fetchrow("""
                                     INSERT INTO users (telegram_id, username, first_name, last_name, is_admin)
                                     VALUES ($1, $2, $3, $4, $5) RETURNING *
                                     """, telegram_id, username, first_name, last_name, is_admin)
            else:
                await c.execute("""
                                UPDATE users
                                SET username=$1,
                                    first_name=$2,
                                    last_name=$3,
                                    updated_at=NOW()
                                WHERE telegram_id = $4
                                """, username, first_name, last_name, telegram_id)
            return dict(u)

    async def get_user(self, telegram_id: int) -> Optional[Dict]:
        async with self.pool.acquire() as c:
            u = await c.fetchrow("SELECT * FROM users WHERE telegram_id=$1", telegram_id)
            return dict(u) if u else None

    async def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        async with self.pool.acquire() as c:
            u = await c.fetchrow("SELECT * FROM users WHERE id=$1", user_id)
            return dict(u) if u else None

    async def update_user_phone(self, telegram_id: int, phone: str) -> bool:
        async with self.pool.acquire() as c:
            await c.execute("""
                            UPDATE users
                            SET phone=$1,
                                is_registered= TRUE,
                                updated_at=NOW()
                            WHERE telegram_id = $2
                            """, phone, telegram_id)
            return True

    async def update_balance(self, telegram_id: int, amount: int, action: str = "add") -> int:
        """Balansni yangilash: 'add' (qo'shish) yoki 'subtract' (ayirish)"""
        async with self.pool.acquire() as c:
            if action == "add":
                await c.execute("UPDATE users SET balance=balance+$1 WHERE telegram_id=$2", amount, telegram_id)
            elif action == "subtract":
                await c.execute("UPDATE users SET balance=balance-$1, total_spent=total_spent+$1 WHERE telegram_id=$2",
                                amount, telegram_id)

            res = await c.fetchrow("SELECT balance FROM users WHERE telegram_id=$1", telegram_id)
            return res["balance"] if res else 0

    async def update_user_badge(self, telegram_id: int, badge: str) -> bool:
        """Galichka berish (blue, yellow, black, none)"""
        async with self.pool.acquire() as c:
            await c.execute("UPDATE users SET badge=$1 WHERE telegram_id=$2", badge, telegram_id)
            return True

    async def verify_user_passport(self, telegram_id: int, passport_img: str) -> bool:
        async with self.pool.acquire() as c:
            await c.execute("""
                            UPDATE users
                            SET passport_img=$1,
                                is_verified= TRUE,
                                badge='blue'
                            WHERE telegram_id = $2
                            """, passport_img, telegram_id)
            return True

    async def get_all_users(self) -> List[Dict]:
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT * FROM users ORDER BY created_at DESC")
            return [dict(r) for r in rows]

    async def block_user(self, telegram_id: int, reason: str = None):
        async with self.pool.acquire() as c:
            await c.execute("UPDATE users SET is_blocked=TRUE WHERE telegram_id=$1", telegram_id)

    async def unblock_user(self, telegram_id: int):
        async with self.pool.acquire() as c:
            await c.execute("UPDATE users SET is_blocked=FALSE WHERE telegram_id=$1", telegram_id)

    # ============================================================
    # 5. AKKOUNTLAR (ACCOUNTS)
    # ============================================================
    async def add_account(self, account_no: int, title: str, description: str, video_id: str, prices: Dict) -> int:
        async with self.pool.acquire() as c:
            prices_json = json.dumps(prices, ensure_ascii=False)
            acc_id = await c.fetchval("""
                                      INSERT INTO accounts (account_no, title, description, video_id, prices)
                                      VALUES ($1, $2, $3, $4, $5::jsonb) RETURNING id
                                      """, account_no, title, description, video_id, prices_json)
            return acc_id

    async def update_account(self, account_id: int, title: str, description: str, prices: Dict) -> bool:
        async with self.pool.acquire() as c:
            prices_json = json.dumps(prices, ensure_ascii=False)
            await c.execute("""
                            UPDATE accounts
                            SET title=$1,
                                description=$2,
                                prices=$3::jsonb, updated_at=NOW()
                            WHERE id=$4
                            """, title, description, prices_json, account_id)
            return True

    async def get_all_accounts(self) -> List[Dict]:
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT * FROM accounts WHERE is_active=TRUE ORDER BY account_no")
            return [dict(r) for r in rows]

    async def get_account(self, account_id: int) -> Optional[Dict]:
        async with self.pool.acquire() as c:
            r = await c.fetchrow("SELECT * FROM accounts WHERE id=$1", account_id)
            if r:
                d = dict(r)
                if isinstance(d["prices"], str):
                    d["prices"] = json.loads(d["prices"])
                return d
            return None

    async def check_account_availability(self, account_id: int, start_time: datetime, end_time: datetime) -> bool:
        """Akkaunt shu vaqtda bo'shligini tekshirish."""
        async with self.pool.acquire() as c:
            conflict = await c.fetchval("""
                                        SELECT COUNT(*)
                                        FROM rentals
                                        WHERE account_id = $1
                                          AND status IN ('ACTIVE', 'PENDING')
                                          AND (start_time <= $3 AND end_time >= $2)
                                        """, account_id, start_time, end_time)
            return conflict == 0

    # ============================================================
    # 6. ARENDALAR (RENTALS)
    # ============================================================
    async def create_rental_request(self, telegram_id: int, account_id: int, start_time: datetime, end_time: datetime,
                                    price: int) -> int:
        async with self.pool.acquire() as c:
            user = await self.get_user(telegram_id)
            if not user: return 0

            rental_id = await c.fetchval("""
                                         INSERT INTO rentals (user_id, account_id, start_time, end_time, price, status)
                                         VALUES ($1, $2, $3, $4, $5, 'PENDING') RETURNING id
                                         """, user["id"], account_id, start_time, end_time, price)
            return rental_id

    async def get_user_rentals(self, telegram_id: int) -> List[Dict]:
        async with self.pool.acquire() as c:
            user = await self.get_user(telegram_id)
            if not user: return []
            rows = await c.fetch("""
                                 SELECT r.*, a.account_no, a.title as account_title
                                 FROM rentals r
                                          JOIN accounts a ON a.id = r.account_id
                                 WHERE r.user_id = $1
                                 ORDER BY r.created_at DESC
                                 """, user["id"])
            return [dict(r) for r in rows]

    async def get_pending_rentals(self) -> List[Dict]:
        async with self.pool.acquire() as c:
            rows = await c.fetch("""
                                 SELECT r.*, u.telegram_id, u.first_name, u.phone, a.account_no
                                 FROM rentals r
                                          JOIN users u ON u.id = r.user_id
                                          JOIN accounts a ON a.id = r.account_id
                                 WHERE r.status = 'PENDING'
                                 ORDER BY r.created_at ASC
                                 """)
            return [dict(r) for r in rows]

    async def approve_rental(self, rental_id: int) -> bool:
        async with self.pool.acquire() as c:
            await c.execute("UPDATE rentals SET status='ACTIVE', updated_at=NOW() WHERE id=$1", rental_id)
            return True

    async def reject_rental(self, rental_id: int, reason: str) -> bool:
        async with self.pool.acquire() as c:
            async with c.transaction():
                rental = await c.fetchrow("SELECT * FROM rentals WHERE id=$1", rental_id)
                if not rental: return False

                await c.execute("UPDATE rentals SET status='REJECTED', reject_reason=$1 WHERE id=$2", reason, rental_id)
                # Pulni qaytarish
                await c.execute("UPDATE users SET balance=balance+$1 WHERE id=$2", rental["price"], rental["user_id"])
            return True

    # ============================================================
    # 7. TO'LOVLAR (TOPUPS)
    # ============================================================
    async def create_topup(self, telegram_id: int, amount: int, card_number: str, card_holder: str,
                           timeout_min: int = 10) -> int:
        async with self.pool.acquire() as c:
            user = await self.get_user(telegram_id)
            if not user: return 0

            # Eskilarni bekor qilish
            await c.execute("""
                            UPDATE topups
                            SET status='CANCELLED'
                            WHERE user_id = $1
                              AND status IN ('WAITING', 'RECEIPT_UPLOADED')
                            """, user["id"])

            expires = datetime.now() + timedelta(minutes=timeout_min)
            topup_id = await c.fetchval("""
                                        INSERT INTO topups (user_id, amount, card_number, card_holder, expires_at, status)
                                        VALUES ($1, $2, $3, $4, $5, 'WAITING') RETURNING id
                                        """, user["id"], amount, card_number, card_holder, expires)
            return topup_id

    async def match_payment(self, amount: int, card_last4: str) -> Dict:
        """Userbot tomonidan chaqiriladi."""
        async with self.pool.acquire() as c:
            req = await c.fetchrow("""
                                   SELECT *
                                   FROM topups
                                   WHERE amount = $1
                                     AND status = 'WAITING'
                                     AND expires_at > NOW()
                                     AND RIGHT (card_number
                                       , 4) = $2
                                   ORDER BY created_at ASC LIMIT 1
                                   """, amount, card_last4)

            if not req:
                return {"ok": False, "reason": "no_match"}

            await c.execute("UPDATE topups SET status='MATCHED', matched_at=NOW() WHERE id=$1", req["id"])
            u = await c.fetchrow("SELECT * FROM users WHERE id=$1", req["user_id"])

            return {
                "ok": True,
                "topup_id": req["id"],
                "user_tg": u["telegram_id"],
                "amount": amount
            }

    async def submit_receipt(self, topup_id: int, receipt_img: str) -> bool:
        async with self.pool.acquire() as c:
            await c.execute("""
                            UPDATE topups
                            SET receipt_img=$1,
                                status='RECEIPT_UPLOADED'
                            WHERE id = $2
                              AND status IN ('WAITING', 'MATCHED')
                            """, receipt_img, topup_id)
            return True

    async def approve_topup(self, topup_id: int) -> bool:
        async with self.pool.acquire() as c:
            async with c.transaction():
                topup = await c.fetchrow("SELECT * FROM topups WHERE id=$1", topup_id)
                if not topup or topup["status"] == "COMPLETED":
                    return False

                await c.execute("UPDATE topups SET status='COMPLETED', completed_at=NOW() WHERE id=$1", topup_id)
                await c.execute("UPDATE users SET balance=balance+$1 WHERE id=$2", topup["amount"], topup["user_id"])
                await c.execute("""
                                UPDATE cards
                                SET total_received=total_received + $1
                                WHERE RIGHT (number, 4) = RIGHT ($2, 4)
                                """, topup["amount"], topup["card_number"])
            return True

    async def cancel_topup(self, telegram_id: int) -> bool:
        async with self.pool.acquire() as c:
            user = await self.get_user(telegram_id)
            if not user: return False
            await c.execute("""
                            UPDATE topups
                            SET status='CANCELLED'
                            WHERE user_id = $1
                              AND status IN ('WAITING', 'MATCHED', 'RECEIPT_UPLOADED')
                            """, user["id"])
            return True

    async def get_pending_topups(self) -> List[Dict]:
        async with self.pool.acquire() as c:
            rows = await c.fetch("""
                                 SELECT t.*, u.first_name, u.telegram_id
                                 FROM topups t
                                          JOIN users u ON u.id = t.user_id
                                 WHERE t.status = 'RECEIPT_UPLOADED'
                                 ORDER BY t.created_at ASC
                                 """)
            return [dict(r) for r in rows]

    # ============================================================
    # 8. KARTALAR (CARDS)
    # ============================================================
    async def add_card(self, number: str, holder: str) -> bool:
        async with self.pool.acquire() as c:
            await c.execute("""
                            INSERT INTO cards (number, holder)
                            VALUES ($1, $2) ON CONFLICT (number) DO
                            UPDATE SET holder=$2
                            """, number, holder)
            return True

    async def remove_card(self, card_id: int) -> bool:
        async with self.pool.acquire() as c:
            await c.execute("DELETE FROM cards WHERE id=$1", card_id)
            return True

    async def get_cards(self) -> List[Dict]:
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT * FROM cards ORDER BY created_at DESC")
            return [dict(r) for r in rows]

    # ============================================================
    # 9. USERBOT SESSIYASI
    # ============================================================
    async def save_userbot_session(self, phone: str, session_string: str) -> bool:
        async with self.pool.acquire() as c:
            async with c.transaction():
                await c.execute("DELETE FROM userbot_sessions")
                await c.execute(
                    "INSERT INTO userbot_sessions (phone, session_string, is_active) VALUES ($1,$2,TRUE)",
                    phone, session_string
                )
        return True

    async def get_userbot_session(self) -> Optional[str]:
        async with self.pool.acquire() as c:
            r = await c.fetchrow(
                "SELECT session_string FROM userbot_sessions WHERE is_active=TRUE ORDER BY id DESC LIMIT 1")
            return r["session_string"] if r else None

    async def delete_userbot_session(self) -> bool:
        async with self.pool.acquire() as c:
            await c.execute("DELETE FROM userbot_sessions")
        return True

    # ============================================================
    # 10. STATISTIKA VA REYTING
    # ============================================================
    async def get_top_users(self, period: str = "all", limit: int = 50) -> List[Dict]:
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
        async with self.pool.acquire() as c:
            return {
                "users": await c.fetchval("SELECT COUNT(*) FROM users"),
                "accounts": await c.fetchval("SELECT COUNT(*) FROM accounts WHERE is_active=TRUE"),
                "active_rentals": await c.fetchval("SELECT COUNT(*) FROM rentals WHERE status='ACTIVE'"),
                "pending_rentals": await c.fetchval("SELECT COUNT(*) FROM rentals WHERE status='PENDING'"),
                "total_balance": await c.fetchval("SELECT COALESCE(SUM(balance),0) FROM users"),
            }