import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = os.getenv("PORT", 10000) 
DATABASE_URL = os.getenv("DATABASE_URL")