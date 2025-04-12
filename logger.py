class Logger:
    def __init__(self, db):
        self.db = db

    async def log(self, event_type: str, user_id: int = None, order_id: int = None, details: str = None):
        await self.db.log_event(event_type, user_id, order_id, details)
