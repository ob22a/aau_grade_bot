import sys
import asyncio
import logging
from aiohttp import web
from config import BOT_TOKEN,PORT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def handle_health_check(request):
  return web.Response(status=204) # No content this is better to avoid unnecessary data transfer

async def main():
  if not BOT_TOKEN:
    logger.error("BOT_TOKEN is not set. Please set it in the .env file.")
    sys.exit(1)
  
  app = web.Application()
  app.router.add_get("/",handle_health_check)
  app.router.add_get("/health",handle_health_check)

  runner = web.AppRunner(app)
  await runner.setup()
  site = web.TCPSite(runner, '0.0.0.0',PORT)
  await site.start()

  await asyncio.Event().wait()

asyncio.run(main())