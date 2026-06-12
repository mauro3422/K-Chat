from dotenv import load_dotenv
import os

load_dotenv()

OPENCODE_ZEN_API_KEY = os.getenv('OPENCODE_ZEN_API_KEY')
OPENCODE_ZEN_API_KEY_FALLBACK = os.getenv('OPENCODE_ZEN_API_KEY_FALLBACK')

if not OPENCODE_ZEN_API_KEY and OPENCODE_ZEN_API_KEY_FALLBACK:
    OPENCODE_ZEN_API_KEY = OPENCODE_ZEN_API_KEY_FALLBACK

if not OPENCODE_ZEN_API_KEY:
    raise ValueError("OPENCODE_ZEN_API_KEY no está configurado en .env")

MEMORY_DB_PATH = os.path.abspath(
    os.getenv('MEMORY_DB_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'memory', 'kairos_memory.db'))
)
