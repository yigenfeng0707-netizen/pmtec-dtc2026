"""
WebSocket Server - real-time situation push for PMTEC.
Runs asyncio event loop in a daemon thread alongside the simulation.
Uses only standard library + websockets package (no GPU dependency).

P12-3 upgrades:
  - Max concurrent browser clients (default 10), overflow rejected with
    an error message + close code 1013 (try again later)
  - Pause / resume per client (paused clients stop receiving live pushes)
  - Replay / step-back: ring buffer of recent per-cycle snapshots, clients
    request {"cmd": "replay", "cycle": N} to receive a historical full state
  - Client command protocol: pause | resume | replay | live | status
  - Per ASDA cycle broadcast (engine pushes once per cycle via push_state)
"""

import asyncio
import json
import threading
import time
from collections import deque

try:
    import websockets
except ImportError:
    websockets = None

from .situation_serializer import SituationSerializer


class RealtimeServer:
    """WebSocket server that pushes real-time situation updates to browsers."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8765,
        max_clients: int = 10,
        history_size: int = 1200,
    ):
        self.host = host
        self.port = port
        self.max_clients = max_clients
        self.serializer = SituationSerializer()
        self._clients: dict = {}  # id(ws) -> {"ws", "paused", "replaying"}
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running = False
        self._state_queue: list = []
        self._events_queue: list = []
        self._lock = threading.Lock()
        self._full_push_needed = True
        self._stop_event = None
        self._last_state: dict | None = None
        self._last_events: list = []
        # P12-3: ring buffer of per-cycle snapshots for replay / step-back
        self._history: deque = deque(maxlen=history_size)
        self._rejected_total = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
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
        print(
            f"[Realtime] WebSocket server starting on ws://{self.host}:{self.port} "
            f"(max_clients={self.max_clients}, replay buffer={self._history.maxlen})"
        )
        return True

    def stop(self):
        """Stop the WebSocket server gracefully."""
        self._running = False
        if self._loop and not self._loop.is_closed() and self._stop_event:
            try:
                self._loop.call_soon_threadsafe(self._stop_event.set)
            except RuntimeError:
                pass
        if self._thread:
            self._thread.join(timeout=3)

    # ------------------------------------------------------------------
    # Producer API (called from the simulation thread, once per ASDA cycle)
    # ------------------------------------------------------------------
    def push_state(self, state: dict, events: list = None):
        """Push simulation state to all connected clients."""
        with self._lock:
            self._state_queue.append(state)
            if events:
                self._events_queue.extend(events)

    # ------------------------------------------------------------------
    # Async event loop
    # ------------------------------------------------------------------
    def _run_async(self):
        """Run the asyncio event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._stop_event = asyncio.Event()
        self._loop.run_until_complete(self._serve())

    async def _serve(self):
        """Serve WebSocket connections until stop() sets the stop event."""
        try:
            async with websockets.serve(
                self._handler, self.host, self.port, max_size=2**20
            ):
                while self._running:
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=0.5)
                        break  # stop requested
                    except asyncio.TimeoutError:
                        pass
                    await self._push_to_clients()
        except (RuntimeError, OSError):
            pass  # Server stopped or port unavailable

    # ------------------------------------------------------------------
    # Client session handling
    # ------------------------------------------------------------------
    async def _handler(self, websocket):
        """Handle a WebSocket connection (P12-3: limit + command protocol)."""
        # Max concurrent clients
        if len(self._clients) >= self.max_clients:
            self._rejected_total += 1
            try:
                await websocket.send(
                    json.dumps(
                        {
                            "type": "error",
                            "reason": "max_clients_reached",
                            "max_clients": self.max_clients,
                        }
                    )
                )
                await websocket.close(code=1013, reason="max clients reached")
            except Exception:
                pass
            return

        session = {"ws": websocket, "paused": False, "needs_full": True}
        self._clients[id(websocket)] = session
        try:
            # Initial full snapshot (latest state)
            await self._send_full(websocket, self._last_state, self._last_events)
            session["needs_full"] = False
            # Command loop
            async for message in websocket:
                await self._handle_command(session, message)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception:
            pass
        finally:
            self._clients.pop(id(websocket), None)

    async def _handle_command(self, session: dict, message):
        """P12-3 client commands: pause/resume/replay/live/status."""
        try:
            cmd = json.loads(message)
        except (ValueError, TypeError):
            return
        action = cmd.get("cmd")
        ws = session["ws"]

        if action == "pause":
            session["paused"] = True
            await self._safe_send(
                ws, json.dumps({"type": "paused", "timestamp": time.time()})
            )

        elif action == "resume":
            session["paused"] = False
            session["needs_full"] = True  # resync with a full snapshot

        elif action == "replay":
            cycle = int(cmd.get("cycle", 0))
            snap = self._find_history_snapshot(cycle)
            if snap is None:
                await self._safe_send(
                    ws,
                    json.dumps(
                        {
                            "type": "error",
                            "reason": "cycle_not_in_history",
                            "requested_cycle": cycle,
                            "history_range": self.history_range,
                        }
                    ),
                )
            else:
                state, events = snap
                await self._send_full(ws, state, events, replay=True)

        elif action == "live":
            session["paused"] = False
            session["needs_full"] = True

        elif action == "status":
            await self._safe_send(
                ws,
                json.dumps(
                    {
                        "type": "status",
                        "clients": len(self._clients),
                        "max_clients": self.max_clients,
                        "paused": session["paused"],
                        "history_cycles": self.history_range,
                        "rejected_total": self._rejected_total,
                        "server_time": time.time(),
                    }
                ),
            )

    # ------------------------------------------------------------------
    # Broadcast
    # ------------------------------------------------------------------
    async def _push_to_clients(self):
        """Push queued state updates to all live (non-paused) clients."""
        with self._lock:
            if self._state_queue:
                latest_state = self._state_queue[-1]
                latest_events = self._events_queue[-50:]
                # P12-3: archive EVERY queued snapshot so replay keeps
                # per-cycle granularity even under fast producers
                for st in self._state_queue:
                    self._archive(st, latest_events)
                self._state_queue.clear()
                self._last_state = latest_state
                self._last_events = latest_events
            else:
                return

        live = [
            s
            for s in self._clients.values()
            if not s["paused"] and not s["needs_full"]
        ]
        if not live:
            return

        if self._full_push_needed:
            msg = self.serializer.serialize_full(latest_state, latest_events)
            self._full_push_needed = False
        else:
            msg = self.serializer.serialize_delta(latest_state, latest_events)
        if not msg:
            return

        tasks = [self._safe_send(s["ws"], msg) for s in live]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Clients that requested resync get a fresh full snapshot afterwards
        for s in list(self._clients.values()):
            if s["needs_full"]:
                s["needs_full"] = False
                await self._send_full(s["ws"], latest_state, latest_events)

    async def _send_full(self, ws, state, events, replay: bool = False):
        """Send a full snapshot (re-serialized from a raw state dict)."""
        if state is None:
            await self._safe_send(
                ws, json.dumps({"type": "hello", "state": "no_data_yet"})
            )
            return
        msg = self.serializer.serialize_full(state, events)
        if replay:
            obj = json.loads(msg)
            obj["type"] = "replay"
            msg = json.dumps(obj, ensure_ascii=False, default=str)
        await self._safe_send(ws, msg)

    async def _safe_send(self, client, msg: str):
        """Send message to a client, handling disconnections."""
        try:
            await client.send(msg)
        except Exception:
            self._clients.pop(id(client), None)

    # ------------------------------------------------------------------
    # Replay history (P12-3)
    # ------------------------------------------------------------------
    def _archive(self, state: dict, events: list):
        """Store a per-cycle snapshot in the ring buffer."""
        try:
            cycle = int(state.get("asda_cycle", 0) or 0)
        except (TypeError, ValueError):
            cycle = len(self._history)
        self._history.append((cycle, state, list(events or [])[-20:]))

    def _find_history_snapshot(self, cycle: int):
        """Latest snapshot with asda_cycle <= requested (for step-back)."""
        best = None
        for c, state, events in self._history:
            if c <= cycle:
                best = (state, events)
        return best

    @property
    def history_range(self) -> list:
        """[min_cycle, max_cycle] currently buffered (empty list if none)."""
        if not self._history:
            return []
        cycles = [c for c, _, _ in self._history]
        return [min(cycles), max(cycles)]

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------
    @property
    def url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    @property
    def client_count(self) -> int:
        return len(self._clients)
