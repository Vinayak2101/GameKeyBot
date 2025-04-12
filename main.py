import asyncio
import os
from dotenv import load_dotenv
from telegram_handler import TelegramHandler
from database import Database
from payment import PaymentProcessor
from key_manager import KeyManager
from user_flow import UserFlow
from admin import Admin
from logger import Logger

load_dotenv()

async def main():
    # Initialize components
    db = Database(os.getenv("DATABASE_URL"))
    await db.init()
    
    logger = Logger(db)
    payment = PaymentProcessor(
        tron_private_key=os.getenv("TRONWEB_PRIVATE_KEY"),
        binance_pay_key=os.getenv("BINANCE_PAY_API_KEY")
    )
    key_manager = KeyManager(os.getenv("FERNET_KEY"), db)
    
    telegram = TelegramHandler(
        token=os.getenv("TELEGRAM_TOKEN"),
        owner_id=int(os.getenv("OWNER_ID")),
        db=db,
        payment=payment,
        key_manager=key_manager,
        logger=logger
    )
    
    user_flow = UserFlow(telegram, db, payment, key_manager, logger)
    admin = Admin(telegram, db, key_manager, logger)
    
    # Register handlers
    telegram.register_user_handler(user_flow.handle)
    telegram.register_admin_handler(admin.handle)
    
    # Start polling and payment checks
    await asyncio.gather(
        telegram.start_polling(),
        payment.poll_payments(db, key_manager, logger, telegram)
    )

if __name__ == "__main__":
    asyncio.run(main())
