"""
WebSocket Server - real-time situation push for PMTEC.
Runs asyncio event loop in a daemon thread alongside the simulation.
Uses only standard library + websockets package (no GPU dependency).
"""

import asyncio
import json
import threading
import time
import os
from typing import Optional

try:
    import websockets
except ImportError:
    websockets = None

from .situation_serializer import SituationSerializer


class RealtimeServer:
    """WebSocket server that pushes real-time situation updates to browsers."""

    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self.serializer = SituationSerializer()
        self._clients: set = set()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False
        self._state_queue: list = []
        self._events_queue: list = []
        self._lock = threading.Lock()
        self._full_push_needed = True

    def start(self) -> bool:
        """Start the WebSocket server in a background thread."""
        if self._running:
            return True
        if websockets is None:
            print("[Realtime] websockets package not installed, skipping")
            return False

        self._running = True
        self._thread = threading.Thread(target=self._run_async, daemon=True)
        self._thread.start()
        print(f"[Realtime] WebSocket server starting on ws://{self.host}:{self.port}")
        return True

    def stop(self):
        """Stop the WebSocket server gracefully."""
        self._running = False
        if self._loop and not self._loop.is_closed():
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except RuntimeError:
                pass
        if self._thread:
            self._thread.join(timeout=3)

    def push_state(self, state: dict, events: list = None):
        """Push simulation state to all connected clients."""
        with self._lock:
            self._state_queue.append(state)
            if events:
                self._events_queue.extend(events)

    def _run_async(self):
        """Run the asyncio event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())

    async def _serve(self):
        """Serve WebSocket connections."""
        try:
            async with websockets.serve(
                self._handler, self.host, self.port, max_size=2**20
            ):
                while self._running:
                    await self._push_to_clients()
                    await asyncio.sleep(0.5)
        except (RuntimeError, OSError):
            pass  # Server stopped or port unavailable

    async def _handler(self, websocket):
        """Handle a new WebSocket connection."""
        self._clients.add(websocket)
        self._full_push_needed = True
        try:
            async for message in websocket:
                pass
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)

    async def _push_to_clients(self):
        """Push queued state updates to all clients."""
        if not self._clients:
            return

        with self._lock:
            if not self._state_queue:
                return
            latest_state = self._state_queue[-1]
            latest_events = self._events_queue[-50:]
            self._state_queue.clear()

        if self._full_push_needed:
            msg = self.serializer.serialize_full(latest_state, latest_events)
            self._full_push_needed = False
        else:
            msg = self.serializer.serialize_delta(latest_state, latest_events)

        if msg:
            tasks = []
            for client in list(self._clients):
                tasks.append(self._safe_send(client, msg))
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_send(self, client, msg: str):
        """Send message to a client, handling disconnections."""
        try:
            await client.send(msg)
        except Exception:
            self._clients.discard(client)

    @property
    def url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    @property
    def client_count(self) -> int:
        return len(self._clients)
