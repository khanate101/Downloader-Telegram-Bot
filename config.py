import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    admin_id: int
    download_dir: str = "downloads"

def load_settings():
    token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
    admin=os.getenv("ADMIN_ID","").strip()
    if not token: raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
    if not admin.isdigit(): raise RuntimeError("ADMIN_ID must be numeric")
    return Settings(token,int(admin))
