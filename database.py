import asyncpg
import asyncio
from typing import List, Dict, Optional

class Database:
    def __init__(self, url: str):
        self.url = url
        self.pool = None

    async def init(self):
        self.pool = await asyncpg.create_pool(self.url)
        await self.create_tables()

    async def create_tables(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    role TEXT DEFAULT 'Normal',
                    balance DECIMAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS products (
                    product_id SERIAL PRIMARY KEY,
                    name TEXT,
                    variant TEXT,
                    price_usd DECIMAL
                );
                CREATE TABLE IF NOT EXISTS orders (
                    order_id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    variant TEXT,
                    price_usd DECIMAL,
                    price_usdt DECIMAL,
                    payment_method TEXT,
                    crypto_address TEXT,
                    binance_pay_link TEXT,
                    status TEXT DEFAULT 'Pending',
                    created_at TIMESTAMP DEFAULT NOW(),
                    expires_at TIMESTAMP,
                    paid_at TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS keys (
                    key_id SERIAL PRIMARY KEY,
                    variant TEXT,
                    key_value TEXT,
                    status TEXT DEFAULT 'Available',
                    order_id BIGINT,
                    allocated_at TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS logs (
                    log_id SERIAL PRIMARY KEY,
                    order_id BIGINT,
                    user_id BIGINT,
                    event_type TEXT,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS branding (
                    id SERIAL PRIMARY KEY,
                    bot_name TEXT DEFAULT 'GameKeyBot',
                    welcome_message TEXT DEFAULT 'Welcome, gamer! Ready to unlock your license?',
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """)
            # Seed products if empty
            count = await conn.fetchval("SELECT COUNT(*) FROM products")
            if count == 0:
                await conn.execute("""
                    INSERT INTO products (name, variant, price_usd) VALUES
                    ('License', 'Basic', 50.0),
                    ('License', 'Pro', 99.0),
                    ('License', 'Premium', 150.0);
                """)
            # Seed branding if empty
            count = await conn.fetchval("SELECT COUNT(*) FROM branding")
            if count == 0:
                await conn.execute("""
                    INSERT INTO branding (bot_name, welcome_message) VALUES
                    ('GameKeyBot', 'Welcome, gamer! Ready to unlock your license?');
                """)

    async def get_user(self, user_id: int) -> Optional[Dict]:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)

    async def create_user(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users (user_id, role, balance) VALUES ($1, 'Normal', 0.0) ON CONFLICT DO NOTHING",
                user_id
            )

    async def get_products(self) -> List[Dict]:
        async with self.pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM products")

    async def create_order(self, user_id: int, variant: str, price_usd: float, price_usdt: float,
                          payment_method: str, crypto_address: str = None, binance_pay_link: str = None) -> int:
        async with self.pool.acquire() as conn:
            expires_at = "NOW() + INTERVAL '30 minutes'"
            order_id = await conn.fetchval(
                """
                INSERT INTO orders (user_id, variant, price_usd, price_usdt, payment_method, crypto_address,
                                   binance_pay_link, status, created_at, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'Pending', NOW(), %s)
                RETURNING order_id
                """ % expires_at,
                user_id, variant, price_usd, price_usdt, payment_method, crypto_address, binance_pay_link
            )
            return order_id

    async def get_order(self, order_id: int) -> Optional[Dict]:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM orders WHERE order_id = $1", order_id)

    async def update_order_status(self, order_id: int, status: str, paid_at: str = None):
        async with self.pool.acquire() as conn:
            if paid_at:
                await conn.execute(
                    "UPDATE orders SET status = $1, paid_at = $2 WHERE order_id = $3",
                    status, paid_at, order_id
                )
            else:
                await conn.execute(
                    "UPDATE orders SET status = $1 WHERE order_id = $2",
                    status, order_id
                )

    async def get_pending_orders(self) -> List[Dict]:
        async with self.pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM orders WHERE status = 'Pending' OR status = 'Expired'")

    async def add_key(self, variant: str, key_value: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO keys (variant, key_value, status) VALUES ($1, $2, 'Available')",
                variant, key_value
            )

    async def allocate_key(self, variant: str, order_id: int) -> Optional[str]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                key = await conn.fetchrow(
                    """
                    SELECT key_id, key_value FROM keys
                    WHERE variant = $1 AND status = 'Available'
                    LIMIT 1 FOR UPDATE
                    """,
                    variant
                )
                if not key:
                    return None
                await conn.execute(
                    """
                    UPDATE keys SET status = 'Used', order_id = $1, allocated_at = NOW()
                    WHERE key_id = $2
                    """,
                    order_id, key["key_id"]
                )
                return key["key_value"]

    async def get_key_count(self, variant: str) -> int:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM keys WHERE variant = $1 AND status = 'Available'",
                variant
            )

    async def log_event(self, event_type: str, user_id: int = None, order_id: int = None, details: str = None):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO logs (event_type, user_id, order_id, details) VALUES ($1, $2, $3, $4)",
                event_type, user_id, order_id, details
            )

    async def get_logs(self, limit: int = 50) -> List[Dict]:
        async with self.pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM logs ORDER BY timestamp DESC LIMIT $1", limit)

    async def get_branding(self) -> Dict:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM branding LIMIT 1")

    async def update_branding(self, bot_name: str, welcome_message: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE branding SET bot_name = $1, welcome_message = $2, updated_at = NOW()
                WHERE id = (SELECT id FROM branding LIMIT 1)
                """,
                bot_name, welcome_message
            )

    async def update_balance(self, user_id: int, amount: float):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
                amount, user_id
            )

    async def get_users(self) -> List[Dict]:
        async with self.pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM users")
