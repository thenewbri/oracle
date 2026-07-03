# Loads environment variables and exposes typed config constants used across the app

from dotenv import load_dotenv
import os

load_dotenv()

# API credentials
ANTHROPIC_API_KEY: str = os.environ["ANTHROPIC_API_KEY"]
TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID: str = os.environ["TELEGRAM_CHAT_ID"]

PELOSI_SUPABASE_URL: str = os.environ["PELOSI_SUPABASE_URL"]
PELOSI_SUPABASE_KEY: str = os.environ["PELOSI_SUPABASE_KEY"]

WOLF_SUPABASE_URL: str = os.environ["WOLF_SUPABASE_URL"]
WOLF_SUPABASE_KEY: str = os.environ["WOLF_SUPABASE_KEY"]

ORACLE_SUPABASE_URL: str = os.environ["ORACLE_SUPABASE_URL"]
ORACLE_SUPABASE_KEY: str = os.environ["ORACLE_SUPABASE_KEY"]

# Sector priority tiers
SECTOR_PRIORITY: dict[str, list[str]] = {
    "high": ["consumer discretionary", "retail", "airlines", "biotech", "pharma", "semiconductors"],
    "medium": ["financials", "real estate"],
    "watchlist": ["defence", "aerospace"],
    "deprioritise": ["energy", "utilities"],
}

# Signal filters
MIN_MARKET_CAP: int = 5_000_000_000
MIN_OPEN_INTEREST: int = 500
MAX_SIGNAL_COUNT: int = 15
PELOSI_MIN_TRADE_SIZE: int = 1_000_000
WOLF_MIN_POSITION_PCT: float = 15.0
MACRO_REFRESH_DAY: str = "monday"
BRIEFING_HOUR: int = 7
