import sys
import os
import asyncio
import logging
from aiohttp import web

# Inject src into Python path to fix module imports when run directly
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from config import load_settings
from bootstrap import build_http_app, build_application_services, build_dispatcher
from aiogram import Bot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    settings = load_settings()
    if not settings.bot_token:
        logger.critical("BOT_TOKEN is not set. Please set it in the .env file. Exiting program")
        sys.exit(1)
        
    # 1. Initialize Bot
    bot = Bot(token=settings.bot_token)
    
    # 2. Build Services and Dispatcher
    services = build_application_services(settings, bot)
    dp = build_dispatcher(settings, services)
    
    # 3. Build Web App
    app = build_http_app(settings, services)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', settings.port)
    await site.start()
    
    logger.info(f"Web server started on port {settings.port}")
    
    # 4. Start Polling
    logger.info("Starting Telegram bot polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())