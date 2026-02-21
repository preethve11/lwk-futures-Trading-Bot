"""Telegram notifications. Never log token or chat_id."""

from __future__ import annotations
import logging
from typing import Optional

import requests

logger = logging.getLogger("trading_bot.utils.telegram")


def send_telegram(text: str, bot_token: str = "", chat_id: str = "") -> bool:
    """Send message to Telegram. Returns True on success. Uses empty strings if not configured."""
    if not bot_token or not chat_id:
        logger.debug("Telegram not configured, skipping message (len=%d)", len(text))
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            logger.warning("Telegram send failed: %s %s", r.status_code, r.text[:200])
            return False
        return True
    except Exception as e:
        logger.exception("Telegram error: %s", e)
        return False
