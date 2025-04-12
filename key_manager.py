from cryptography.fernet import Fernet
from typing import Optional

class KeyManager:
    def __init__(self, fernet_key: str, db):
        self.fernet = Fernet(fernet_key.encode())
        self.db = db

    async def add_key(self, variant: str, raw_key: str):
        encrypted_key = self.fernet.encrypt(raw_key.encode()).decode()
        await self.db.add_key(variant, encrypted_key)
        key_count = await self.db.get_key_count(variant)
        if key_count <= 2:
            await self.db.log_event("LowKey", details=f"Only {key_count} {variant} keys left")

    async def allocate_key(self, variant: str, order_id: int) -> Optional[str]:
        encrypted_key = await self.db.allocate_key(variant, order_id)
        if not encrypted_key:
            return None
        raw_key = self.fernet.decrypt(encrypted_key.encode()).decode()
        return raw_key
