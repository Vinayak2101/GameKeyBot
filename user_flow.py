from typing import Dict, Optional
from datetime import datetime, timedelta

class UserFlow:
    def __init__(self, telegram, db, payment, key_manager, logger):
        self.telegram = telegram
        self.db = db
        self.payment = payment
        self.key_manager = key_manager
        self.logger = logger
        self.user_states = {}  # {user_id: {"step": str, "data": dict}}

    async def handle(self, chat_id: int, user_id: int, message: Dict, callback: Dict):
        # Initialize user
        user = await self.db.get_user(user_id)
        if not user:
            await self.db.create_user(user_id)
            user = await self.db.get_user(user_id)

        branding = await self.db.get_branding()
        bot_name = branding["bot_name"]
        welcome_message = branding["welcome_message"]

        # Handle callback (button clicks)
        if callback:
            data = callback.get("data", "")
            state = self.user_states.get(user_id, {"step": None, "data": {}})
            
            if data == "browse":
                self.user_states[user_id] = {"step": "select_variant", "data": {}}
                await self.show_products(chat_id)
            elif data.startswith("variant_"):
                variant = data.split("_")[1]
                products = await self.db.get_products()
                product = next((p for p in products if p["variant"] == variant), None)
                if not product:
                    return
                price_usd = product["price_usd"] * (0.8 if user["role"] == "Reseller" else 1.0)
                self.user_states[user_id] = {
                    "step": "select_payment",
                    "data": {"variant": variant, "price_usd": price_usd}
                }
                await self.telegram.send_message(
                    chat_id,
                    f"Selected {variant} for ${price_usd:.2f}. How would you like to pay?",
                    {"inline_keyboard": [[
                        {"text": "USDT", "callback_data": "pay_usdt"},
                        {"text": "Binance Pay", "callback_data": "pay_binance"}
                    ]]}
                )
            elif data == "pay_usdt":
                state_data = state["data"]
                variant = state_data["variant"]
                price_usd = state_data["price_usd"]
                price_usdt = price_usd / (await self.payment.get_usdt_rate())
                address = await self.payment.generate_tron_address()
                order_id = await self.db.create_order(
                    user_id, variant, price_usd, price_usdt, "USDT", crypto_address=address
                )
                await self.logger.log("OrderCreated", user_id, order_id, f"Order #{order_id} for {variant}")
                await self.telegram.send_message(
                    self.telegram.owner_id,
                    f"Order #{order_id} created by user #{user_id} for {variant}."
                )
                await self.telegram.send_message(
                    chat_id,
                    f"Order #{order_id} created! Pay `{price_usdt:.2f} USDT` to `{address}`.",
                    {"inline_keyboard": [[{"text": "Copy Address", "callback_data": "copy_address"}]]}
                )
                self.user_states.pop(user_id, None)
            elif data == "pay_binance":
                state_data = state["data"]
                variant = state_data["variant"]
                price_usd = state_data["price_usd"]
                price_usdt = price_usd / (await self.payment.get_usdt_rate())
                link = await self.payment.create_binance_pay_link(order_id=0, amount_usd=price_usd)
                order_id = await self.db.create_order(
                    user_id, variant, price_usd, price_usdt, "BinancePay", binance_pay_link=link
                )
                await self.logger.log("OrderCreated", user_id, order_id, f"Order #{order_id} for {variant}")
                await self.telegram.send_message(
                    self.telegram.owner_id,
                    f"Order #{order_id} created by user #{user_id} for {variant}."
                )
                await self.telegram.send_message(
                    chat_id,
                    f"Order #{order_id} created! Pay ${price_usd:.2f} via [Binance Pay]({link}).",
                    {"inline_keyboard": [[{"text": "Open Binance Pay", "url": link}]]}
                )
                self.user_states.pop(user_id, None)
            elif data == "balance":
                await self.telegram.send_message(
                    chat_id,
                    f"Your balance: ${user['balance']:.2f}",
                    {"inline_keyboard": [[{"text": "Top Up $50+", "callback_data": "topup"}]]}
                )
            elif data == "topup":
                self.user_states[user_id] = {"step": "enter_topup", "data": {}}
                await self.telegram.send_message(
                    chat_id,
                    "Enter top-up amount ($50 minimum):"
                )
            return

        # Handle text input
        text = message.get("text", "").strip()
        state = self.user_states.get(user_id, {"step": None, "data": {}})

        if state["step"] == "enter_topup" and text:
            try:
                amount = float(text)
                if amount < 50:
                    await self.telegram.send_message(chat_id, "Minimum top-up is $50!")
                    return
                price_usdt = amount / (await self.payment.get_usdt_rate())
                address = await self.payment.generate_tron_address()
                order_id = await self.db.create_order(
                    user_id, "TopUp", amount, price_usdt, "USDT", crypto_address=address
                )
                await self.logger.log("OrderCreated", user_id, order_id, f"Top-up order #{order_id}")
                await self.telegram.send_message(
                    self.telegram.owner_id,
                    f"Top-up order #{order_id} for ${amount} by user #{user_id}."
                )
                await self.telegram.send_message(
                    chat_id,
                    f"Top-up order #{order_id} created! Pay `{price_usdt:.2f} USDT` to `{address}`.",
                    {"inline_keyboard": [[{"text": "Copy Address", "callback_data": "copy_address"}]]}
                )
                self.user_states.pop(user_id, None)
            except ValueError:
                await self.telegram.send_message(chat_id, "Please enter a valid number!")
            return

        # Default: Show welcome
        await self.telegram.send_message(
            chat_id,
            f"{welcome_message}",
            {"inline_keyboard": [
                [{"text": "Browse Licenses", "callback_data": "browse"}],
                [{"text": "Check Balance", "callback_data": "balance"}]
            ]}
        )

    async def show_products(self, chat_id: int):
        products = await self.db.get_products()
        buttons = [[{"text": f"{p['variant']} ${p['price_usd']:.2f}", "callback_data": f"variant_{p['variant']}"}]
                   for p in products]
        await self.telegram.send_message(
            chat_id,
            "Choose your license, gamer!",
            {"inline_keyboard": buttons}
        )
