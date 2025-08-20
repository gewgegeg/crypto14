from __future__ import annotations

import os
from typing import Optional

import aiohttp

from .utils import get_logger

logger = get_logger("notify")


class Notifier:
    def __init__(self) -> None:
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    async def send(self, message: str) -> None:
        logger.info("NOTIFY: %s", message)
        if self.telegram_token and self.telegram_chat_id:
            await self._send_telegram(message)

    async def _send_telegram(self, message: str) -> None:
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": message,
            "disable_web_page_preview": True,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status >= 300:
                        logger.warning("Telegram send failed: %s", await resp.text())
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram send exception: %s", exc)