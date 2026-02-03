import asyncio
import os
import logging
from aiogram import Bot, Dispatcher
from bot.handlers import router
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.error("BOT_TOKEN not found!")
        return

    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(router)

    webhook_url = os.getenv("WEBHOOK_URL")
    if webhook_url:
        from aiogram.webhook.axum import SimpleRequestHandler
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
        from aiohttp import web

        logger.info(f"Setting webhook to {webhook_url}")
        await bot.set_webhook(url=webhook_url)
        
        app = web.Application()
        SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
        
        async def health_check(request):
            return web.Response(text="OK", status=200)
        app.router.add_get("/health", health_check)
        app.router.add_get("/", health_check) # Default route for some health checkers
        
        setup_application(app, dp, bot=bot)
        
        port = int(os.getenv("PORT", 8000))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        
        logger.info(f"Bot started on port {port} with Webhook")
        # Keep running
        await asyncio.Event().wait()
    else:
        logger.info("Bot starting with Polling...")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
