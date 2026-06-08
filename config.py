from dotenv import load_dotenv
import os

load_dotenv()

OPENCODE_ZEN_API_KEY = os.getenv('OPENCODE_ZEN_API_KEY')
if not OPENCODE_ZEN_API_KEY:
    raise ValueError("OPENCODE_ZEN_API_KEY no está configurado en .env")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_DB_PATH = os.path.abspath(
    os.getenv('MEMORY_DB_PATH', os.path.join(BASE_DIR, 'memory', 'kairos_memory.db'))
)
