import os
from dataclasses import dataclass
from typing import List, Tuple, Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    exchanges: Tuple[str, ...] = tuple(
        os.getenv("EXCHANGES", "binance,kucoin").replace(" ", "").split(",")
    )

    # Arbitrage scanning defaults
    min_profit_pct: float = float(os.getenv("MIN_PROFIT_PCT", "0.5"))  # percent
    min_notional_usd: float = float(os.getenv("MIN_NOTIONAL_USD", "100"))
    orderbook_limit: int = int(os.getenv("ORDERBOOK_LIMIT", "50"))
    orderbook_ttl_seconds: int = int(os.getenv("ORDERBOOK_TTL", "5"))
    markets_ttl_seconds: int = int(os.getenv("MARKETS_TTL", "86400"))  # 1 day
    concurrency: int = int(os.getenv("CONCURRENCY", "16"))

    # Cache
    cache_db_path: str = os.getenv("CACHE_DB_PATH", "/workspace/.cache/arbitrage_cache.sqlite3")

    # Preferred quote assets for simple two-exchange scanning (treat ~USD)
    preferred_quotes: Tuple[str, ...] = tuple(
        os.getenv("PREFERRED_QUOTES", "USDT,USDC").replace(" ", "").split(",")
    )

    # Network preferences for transfers, comma-separated, most preferred first
    network_priority: Tuple[str, ...] = tuple(
        os.getenv("NETWORK_PRIORITY", "TRC20,ERC20,BEP20,Arbitrum,BSC").replace(" ", "").split(",")
    )

    # Optional API keys for future private endpoints (not required for public data)
    binance_key: Optional[str] = os.getenv("BINANCE_API_KEY")
    binance_secret: Optional[str] = os.getenv("BINANCE_API_SECRET")
    kucoin_key: Optional[str] = os.getenv("KUCOIN_API_KEY")
    kucoin_secret: Optional[str] = os.getenv("KUCOIN_API_SECRET")
    kucoin_password: Optional[str] = os.getenv("KUCOIN_API_PASSPHRASE")


settings = Settings()