import asyncio
import json
import logging
import os
from typing import Any, Iterable, List


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        level = os.getenv("LOG_LEVEL", "INFO").upper()
        logger.setLevel(level)
        handler = logging.StreamHandler()
        fmt = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    return logger


class AsyncLimiter:
    def __init__(self, max_concurrency: int):
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def __aenter__(self):
        await self._semaphore.acquire()

    async def __aexit__(self, exc_type, exc, tb):
        self._semaphore.release()


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def json_dumps(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def chunked(items: Iterable[Any], chunk_size: int) -> List[List[Any]]:
    chunk: List[Any] = []
    out: List[List[Any]] = []
    for item in items:
        chunk.append(item)
        if len(chunk) >= chunk_size:
            out.append(chunk)
            chunk = []
    if chunk:
        out.append(chunk)
    return out