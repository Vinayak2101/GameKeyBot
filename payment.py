import aiohttp
import asyncio
import requests
from typing import Optional, Dict, List
from datetime import datetime
# Note: tronweb requires external library or direct HTTP calls; using mock for simplicity
# In production, install `tronpy` or similar and configure with private key

class PaymentProcessor:
    def __init__(self, tron_private_key: str, binance_pay_key: str):
        self.tron_private_key = tron_private_key
        self.binance_pay_key = binance_pay_key
        self.coingecko_url = "https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=usd"

    async def get_usdt_rate(self) -> float:
        async with aiohttp.ClientSession() as session:
            async with session.get(self.coingecko_url) as resp:
                if resp.status != 200:
                    return 1.0  # Fallback
                data = await resp.json()
                return data["tether"]["usd"]

    async def create_binance_pay_link(self, order_id: int, amount_usd: float) -> str:
        # Mock implementation; replace with real Binance Pay API
        # Requires merchant account and signed payload
        payload = {
            "merchantId": "your_merchant_id",
            "amount": amount_usd,
            "currency": "USDT",
            "orderNo": f"order_{order_id}",
            "description": f"GameKeyBot Order #{order_id}"
        }
        headers = {"Authorization": f"Bearer {self.binance_pay_key}"}
        # In production: POST to https://bpay.binanceapi.com/binancepay/openapi/v2/order
        return f"https://pay.binance.com/mock/order_{order_id}"

    async def check_binance_payment(self, order_id: int) -> bool:
        # Mock; replace with real API check
        return False  # Simulate unpaid for now

    async def generate_tron_address(self) -> str:
        # Mock; replace with TronWeb address generation
        return "TRON_ADDRESS_MOCK"

    async def check_tron_payment(self, address: str, amount_usdt: float) -> bool:
        # Mock; replace with TronWeb transaction check (2 confirmations)
        return False  # Simulate unpaid for now

    async def poll_payments(self, db, key_manager, logger, telegram):
        while True:
            orders = await db.get_pending_orders()
            for order in orders:
                now = datetime.utcnow()
                order_id = order["order_id"]
                user_id = order["user_id"]
                variant = order["variant"]
                payment_method = order["payment_method"]
                expires_at = order["expires_at"]
                price_usdt = order["price_usdt"]
                crypto_address = order["crypto_address"]
                binance_pay_link = order["binance_pay_link"]

                # Check expiry
                if expires_at < now and order["status"] == "Pending":
                    await db.update_order_status(order_id, "Expired")
                    await logger.log("OrderExpired", user_id, order_id, f"Order #{order_id} expired")
                    await telegram.send_message(
                        telegram.owner_id,
                        f"Order #{order_id} by user #{user_id} expired."
                    )
                    continue

                # Check payment
                paid = False
                if payment_method == "USDT":
                    paid = await self.check_tron_payment(crypto_address, price_usdt)
                elif payment_method == "BinancePay":
                    paid = await self.check_binance_payment(order_id)

                if paid:
                    key = await key_manager.allocate_key(variant, order_id)
                    if not key:
                        await logger.log("NoKey", user_id, order_id, f"No keys for {variant}")
                        await telegram.send_message(
                            telegram.owner_id,
                            f"No keys left for order #{order_id} ({variant})!"
                        )
                        continue
                    await db.update_order_status(order_id, "Confirmed", "NOW()")
                    await logger.log("PaymentReceived", user_id, order_id, f"Order #{order_id} paid")
                    await telegram.send_message(
                        user_id,
                        f"Nice! Order #{order_id} paid—here’s your {variant} key: `{key}`"
                    )
                    await telegram.send_message(
                        telegram.owner_id,
                        f"Order #{order_id} by user #{user_id} paid and key delivered."
                    )

                # Late payment check (up to 6 hours)
                if order["status"] == "Expired" and expires_at > now - timedelta(hours=6):
                    if payment_method == "USDT" and await self.check_tron_payment(crypto_address, price_usdt):
                        await logger.log("LatePayment", user_id, order_id, f"Late payment for #{order_id}")
                        await telegram.send_message(
                            telegram.owner_id,
                            f"Order #{order_id} expired, payment detected.",
                            {"inline_keyboard": [[
                                {"text": "Approve Key", "callback_data": f"approve_key_{order_id}"}
                            ]]}
                        )
                    elif payment_method == "BinancePay" and await self.check_binance_payment(order_id):
                        await logger.log("LatePayment", user_id, order_id, f"Late payment for #{order_id}")
                        await telegram.send_message(
                            telegram.owner_id,
                            f"Order #{order_id} expired, payment detected.",
                            {"inline_keyboard": [[
                                {"text": "Approve Key", "callback_data": f"approve_key_{order_id}"}
                            ]]}
                        )

                # 5-minute reminder
                if expires_at < now + timedelta(minutes=6) and expires_at > now + timedelta(minutes=4):
                    await telegram.send_message(
                        user_id,
                        f"Hurry, gamer! 5 minutes left for order #{order_id}!"
                    )

            await asyncio.sleep(10)  # Poll every 10 seconds
