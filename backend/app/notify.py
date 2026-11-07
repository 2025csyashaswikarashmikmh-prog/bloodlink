"""Notification fan-out: in-app WebSocket (always) + Telegram (optional, real phone push)."""
from __future__ import annotations

import threading

import httpx

from .config import settings
from .models import User
from .realtime import hub


def _telegram(chat_id: str, text: str):
    if not settings.TELEGRAM_BOT_TOKEN or not chat_id:
        return
    try:
        httpx.post(
            f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=5,
        )
    except Exception as e:  # never break the flow because of a notification
        print(f"[notify] telegram failed: {e}")


def notify_user(user: User, kind: str, payload: dict, text: str = ""):
    hub.publish(f"donor:{user.id}", {"type": kind, **payload})
    if text and user.telegram_chat_id:
        threading.Thread(target=_telegram, args=(user.telegram_chat_id, text), daemon=True).start()
