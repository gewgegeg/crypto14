import json
import os
import sqlite3
import time
from typing import Any, Optional

from .utils import ensure_dir


class SqliteKVCache:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        parent = os.path.dirname(db_path)
        if parent:
            ensure_dir(parent)
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kv_store (
                    k TEXT PRIMARY KEY,
                    v TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def set_json(self, key: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        now = int(time.time())
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO kv_store(k, v, updated_at) VALUES(?, ?, ?)",
                (key, payload, now),
            )
            conn.commit()
        finally:
            conn.close()

    def get_json(self, key: str, ttl_seconds: Optional[int] = None) -> Optional[Any]:
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute(
                "SELECT v, updated_at FROM kv_store WHERE k = ? LIMIT 1", (key,)
            )
            row = cur.fetchone()
            if row is None:
                return None
            v, updated_at = row
            if ttl_seconds is not None:
                if int(time.time()) - int(updated_at) > ttl_seconds:
                    return None
            return json.loads(v)
        finally:
            conn.close()


class MarketCache:
    def __init__(self, db_path: str) -> None:
        self.kv = SqliteKVCache(db_path)

    def load_cached_markets(self, exchange_id: str, ttl_seconds: int) -> Optional[Any]:
        return self.kv.get_json(f"markets:{exchange_id}", ttl_seconds=ttl_seconds)

    def save_markets(self, exchange_id: str, markets: Any) -> None:
        self.kv.set_json(f"markets:{exchange_id}", markets)