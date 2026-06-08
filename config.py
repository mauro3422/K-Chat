from dotenv import load_dotenv
import os

load_dotenv()

OPENCODE_ZEN_API_KEY = os.getenv('OPENCODE_ZEN_API_KEY')
if not OPENCODE_ZEN_API_KEY:
    raise ValueError("OPENCODE_ZEN_API_KEY no está configurado en .env")

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_OWNER_ID = os.getenv('TELEGRAM_OWNER_ID')
if TELEGRAM_OWNER_ID:
    TELEGRAM_OWNER_ID = int(TELEGRAM_OWNER_ID)

MEMORY_DB_PATH = os.getenv('MEMORY_DB_PATH', 'memory/kairos_memory.db')
