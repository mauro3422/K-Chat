"""Generate minimal silent MP3 placeholders to silence 404 errors."""
import base64
from pathlib import Path

# Minimal valid MP3 frame (100 bytes, silent)
SILENT_MP3 = base64.b64decode(
    b"/+MYxAAAAANIAAAAABpZAtZGEgAAAAAAAABQIEhAREAAREAAREAQwSTxDBJMAwS"
)

sounds_dir = Path(__file__).parent.parent / "web" / "static" / "sounds"
sounds_dir.mkdir(parents=True, exist_ok=True)

for name in ["send", "message", "error", "notification", "connect"]:
    (sounds_dir / f"{name}.mp3").write_bytes(SILENT_MP3)

print(f"Created {len(list(sounds_dir.glob('*.mp3')))} silent MP3 files in {sounds_dir}")
