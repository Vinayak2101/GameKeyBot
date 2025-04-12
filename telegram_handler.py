import aiohttp
import asyncio
import json
from typing import Callable, Optional

class TelegramHandler:
    def __init__(self, token: str, owner_id: int, db, payment, key_manager, logger):
        self.token = token
        self.owner_id = owner_id
        self.db = db
        self.payment = payment
        self.key_manager = key_manager
        self.logger = logger
        self.api_url = f"https://api.telegram.org/bot{token}/"
        self.user_handler: Optional[Callable] = None
        self.admin_handler: Optional[Callable] = None
        self.queue = asyncio.Queue()
        self.rate_limit = 1.0  # 1 message/second per chat

    def register_user_handler(self, handler: Callable):
        self.user_handler = handler

    def register_admin_handler(self, handler: Callable):
        self.admin_handler = handler

    async def send_message(self, chat_id: int, text: str, reply_markup: dict = None):
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        await self.queue.put(("sendMessage", payload))

    async def process_queue(self):
        async with aiohttp.ClientSession() as session:
            while True:
                method, payload = await self.queue.get()
                for attempt in range(3):
                    try:
                        async with session.post(f"{self.api_url}{method}", json=payload) as resp:
                            if resp.status == 200:
                                break
                            elif resp.status == 429:  # Rate limit
                                retry_after = (await resp.json()).get("parameters", {}).get("retry_after", 1)
                                await asyncio.sleep(retry_after)
                            else:
                                await self.logger.log("system", f"Telegram API error: {resp.status}")
                                break
                    except Exception as e:
                        await self.logger.log("system", f"Telegram request failed: {e}")
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                await asyncio.sleep(self.rate_limit)
                self.queue.task_done()

    async def start_polling(self):
        asyncio.create_task(self.process_queue())
        offset = 0
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    async with session.get(f"{self.api_url}getUpdates?offset={offset}&timeout=30") as resp:
                        if resp.status != 200:
                            await asyncio.sleep(5)
                            continue
                        data = await resp.json()
                        for update in data.get("result", []):
                            offset = update["update_id"] + 1
                            await self.handle_update(update)
                except Exception as e:
                    await self.logger.log("system", f"Polling error: {e}")
                    await asyncio.sleep(5)

    async def handle_update(self, update: dict):
        message = update.get("message", {})
        callback = update.get("callback_query", {})
        chat_id = message.get("chat", {}).get("id") or callback.get("message", {}).get("chat", {}).get("id")
        user_id = message.get("from", {}).get("id") or callback.get("from", {}).get("id")
        
        if not chat_id or not user_id:
            return

        if user_id == self.owner_id:
            if self.admin_handler:
                await self.admin_handler(chat_id, user_id, message, callback)
        else:
            if self.user_handler:
                await self.user_handler(chat_id, user_id, message, callback)
