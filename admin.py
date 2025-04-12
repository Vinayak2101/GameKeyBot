from typing import Dict

class Admin:
    def __init__(self, telegram, db, key_manager, logger):
        self.telegram = telegram
        self.db = db
        self.key_manager = key_manager
        self.logger = logger
        self.admin_states = {}  # {user_id: {"step": str, "data": dict}}

    async def handle(self, chat_id: int, user_id: int, message: Dict, callback: Dict):
        branding = await self.db.get_branding()
        bot_name = branding["bot_name"]

        # Handle callback
        if callback:
            data = callback.get("data", "")
            state = self.admin_states.get(user_id, {"step": None, "data": {}})

            if data == "admin_menu":
                self.admin_states[user_id] = {"step": None, "data": {}}
                await self.show_admin_menu(chat_id)
            elif data == "add_keys":
                self.admin_states[user_id] = {"step": "select_variant_keys", "data": {}}
                await self.show_variants(chat_id, "Select variant to add keys:")
            elif data.startswith("variant_keys_"):
                variant = data.split("_")[2]
                self.admin_states[user_id] = {"step": "enter_keys", "data": {"variant": variant}}
                await self.telegram.send_message(
                    chat_id,
                    f"Enter keys for {variant} (one per line):"
                )
            elif data == "assign_role":
                self.admin_states[user_id] = {"step": "enter_user_id_role", "data": {}}
                await self.telegram.send_message(
                    chat_id,
                    "Enter user ID to assign role:"
                )
            elif data.startswith("role_"):
                role = data.split("_")[1]
                user_id_to_assign = state["data"].get("user_id")
                if user_id_to_assign:
                    await self.db.update_user_role(user_id_to_assign, role)
                    await self.logger.log("RoleAssigned", user_id_to_assign, details=f"Assigned {role}")
                    await self.telegram.send_message(
                        chat_id,
                        f"User #{user_id_to_assign} is now {role}."
                    )
                    self.admin_states.pop(user_id, None)
            elif data == "adjust_balance":
                self.admin_states[user_id] = {"step": "enter_user_id_balance", "data": {}}
                await self.telegram.send_message(
                    chat_id,
                    "Enter user ID to adjust balance:"
                )
            elif data == "set_branding":
                self.admin_states[user_id] = {"step": "enter_bot_name", "data": {}}
                await self.telegram.send_message(
                    chat_id,
                    "Enter new bot name:"
                )
            elif data == "view_logs":
                logs = await self.db.get_logs()
                log_text = "\n".join([f"[{l['timestamp']}] {l['event_type']}: {l['details']}" for l in logs])
                await self.telegram.send_message(
                    chat_id,
                    f"Recent logs:\n{log_text or 'No logs.'}",
                    {"inline_keyboard": [[{"text": "Back", "callback_data": "admin_menu"}]]}
                )
            elif data == "test_order":
                variant = "Pro"
                order_id = await self.db.create_order(
                    user_id, variant, 99.0, 99.0, "Test", crypto_address="TEST"
                )
                key = await self.key_manager.allocate_key(variant, order_id)
                await self.db.update_order_status(order_id, "Confirmed", "NOW()")
                await self.logger.log("TestOrder", user_id, order_id, f"Test order #{order_id}")
                await self.telegram.send_message(
                    chat_id,
                    f"Test order #{order_id} complete! Dummy key: {key or 'TEST-1234'}"
                )
            elif data.startswith("approve_key_"):
                order_id = int(data.split("_")[2])
                order = await self.db.get_order(order_id)
                if not order:
                    return
                variant = order["variant"]
                key = await self.key_manager.allocate_key(variant, order_id)
                if not key:
                    await self.telegram.send_message(
                        chat_id,
                        f"No keys left for {variant}!"
                    )
                    return
                await self.db.update_order_status(order_id, "Confirmed", "NOW()")
                await self.logger.log("LatePaymentApproved", order["user_id"], order_id, f"Key delivered")
                await self.telegram.send_message(
                    order["user_id"],
                    f"Order #{order_id} approved! Your {variant} key: `{key}`"
                )
                await self.telegram.send_message(
                    chat_id,
                    f"Key delivered for order #{order_id}."
                )
            return

        # Handle text input
        text = message.get("text", "").strip()
        state = self.admin_states.get(user_id, {"step": None, "data": {}})

        if state["step"] == "enter_keys" and text:
            variant = state["data"]["variant"]
            keys = text.strip().split("\n")
            for key in keys:
                await self.key_manager.add_key(variant, key.strip())
            await self.logger.log("KeysAdded", details=f"Added {len(keys)} {variant} keys")
            await self.telegram.send_message(
                chat_id,
                f"Added {len(keys)} keys for {variant}.",
                {"inline_keyboard": [[{"text": "Back", "callback_data": "admin_menu"}]]}
            )
            self.admin_states.pop(user_id, None)
            return
        elif state["step"] == "enter_user_id_role" and text:
            try:
                user_id_to_assign = int(text)
                self.admin_states[user_id] = {
                    "step": "select_role",
                    "data": {"user_id": user_id_to_assign}
                }
                await self.telegram.send_message(
                    chat_id,
                    f"Select role for user #{user_id_to_assign}:",
                    {"inline_keyboard": [[
                        {"text": "Normal", "callback_data": "role_Normal"},
                        {"text": "Reseller", "callback_data": "role_Reseller"}
                    ]]}
                )
            except ValueError:
                await self.telegram.send_message(chat_id, "Invalid user ID!")
            return
        elif state["step"] == "enter_user_id_balance" and text:
            try:
                user_id_to_adjust = int(text)
                self.admin_states[user_id] = {
                    "step": "enter_balance_amount",
                    "data": {"user_id": user_id_to_adjust}
                }
                await self.telegram.send_message(
                    chat_id,
                    f"Enter amount to adjust for user #{user_id_to_adjust} (positive or negative):"
                )
            except ValueError:
                await self.telegram.send_message(chat_id, "Invalid user ID!")
            return
        elif state["step"] == "enter_balance_amount" and text:
            try:
                amount = float(text)
                user_id_to_adjust = state["data"]["user_id"]
                await self.db.update_balance(user_id_to_adjust, amount)
                await self.logger.log("BalanceAdjusted", user_id_to_adjust, details=f"Adjusted by ${amount}")
                await self.telegram.send_message(
                    chat_id,
                    f"Balance for user #{user_id_to_adjust} adjusted by ${amount:.2f}.",
                    {"inline_keyboard": [[{"text": "Back", "callback_data": "admin_menu"}]]}
                )
                self.admin_states.pop(user_id, None)
            except ValueError:
                await self.telegram.send_message(chat_id, "Invalid amount!")
            return
        elif state["step"] == "enter_bot_name" and text:
            self.admin_states[user_id] = {
                "step": "enter_welcome_message",
                "data": {"bot_name": text}
            }
            await self.telegram.send_message(
                chat_id,
                "Enter new welcome message:"
            )
            return
        elif state["step"] == "enter_welcome_message" and text:
            bot_name = state["data"]["bot_name"]
            await self.db.update_branding(bot_name, text)
            await self.logger.log("BrandingUpdated", details=f"Set bot_name={bot_name}")
            await self.telegram.send_message(
                chat_id,
                f"Branding updated: {bot_name}, '{text}'.",
                {"inline_keyboard": [[{"text": "Back", "callback_data": "admin_menu"}]]}
            )
            self.admin_states.pop(user_id, None)
            return

        # Default: Show admin menu
        await self.show_admin_menu(chat_id)

    async def show_admin_menu(self, chat_id: int):
        await self.telegram.send_message(
            chat_id,
            "Admin Menu:",
            {"inline_keyboard": [
                [{"text": "Add Keys", "callback_data": "add_keys"}],
                [{"text": "Assign Role", "callback_data": "assign_role"}],
                [{"text": "Adjust Balance", "callback_data": "adjust_balance"}],
                [{"text": "Set Branding", "callback_data": "set_branding"}],
                [{"text": "View Logs", "callback_data": "view_logs"}],
                [{"text": "Test Order", "callback_data": "test_order"}]
            ]}
        )

    async def show_variants(self, chat_id: int, text: str):
        products = await self.db.get_products()
        buttons = [[{"text": p["variant"], "callback_data": f"variant_keys_{p['variant']}"}]
                   for p in products]
        await self.telegram.send_message(
            chat_id,
            text,
            {"inline_keyboard": buttons}
        )
