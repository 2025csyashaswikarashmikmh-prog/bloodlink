"""WebSocket hub. Channels: request:<id>, donor:<user_id>, admin."""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict

from fastapi import WebSocket


class Hub:
    def __init__(self):
        self.channels: dict[str, set[WebSocket]] = defaultdict(set)
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, ws: WebSocket, channels: list[str]):
        await ws.accept()
        for c in channels:
            self.channels[c].add(ws)

    def disconnect(self, ws: WebSocket):
        for subs in self.channels.values():
            subs.discard(ws)

    async def _send(self, channel: str, message: dict):
        dead = []
        for ws in list(self.channels.get(channel, ())):
            try:
                await ws.send_text(json.dumps(message, default=str))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def publish(self, channel: str, message: dict):
        """Thread-safe fire-and-forget publish (works from sync route handlers)."""
        if not self.loop:
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self.loop:
            self.loop.create_task(self._send(channel, message))
        else:
            asyncio.run_coroutine_threadsafe(self._send(channel, message), self.loop)


hub = Hub()
