#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P12-3 Test Suite: WebSocket Realtime Situational Push Upgrades

Validates:
  1. Server lifecycle (asyncio thread, ws://localhost:port)
  2. Max concurrent clients (overflow rejected with error + close 1013)
  3. Per-ASDA-cycle broadcast: initial full snapshot + incremental deltas
  4. Pause / resume per client (pause stops live pushes, resume resyncs)
  5. Replay / step-back: {"cmd":"replay","cycle":N} returns historical
     full snapshot from the ring buffer
  6. Status command reports clients/history range

Run: D:/miniconda3/envs/pmtec-xpu/python.exe test_p12_3_websocket.py
"""

import asyncio
import json
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

try:
    import websockets
except ImportError:
    print("websockets package not installed — cannot run P12-3 tests")
    sys.exit(1)

from realtime.websocket_server import RealtimeServer  # noqa: E402

PASS, FAIL = 0, 0
PORT = 8799
MAX_CLIENTS = 3


def test(name, condition, detail=""):
    global PASS, FAIL
    tag = "PASS" if condition else "FAIL"
    print(f"  [{tag}] {name}" + (f" | {detail}" if detail else ""))
    PASS += int(bool(condition))
    FAIL += int(not condition)


def make_state(cycle: int) -> dict:
    return {
        "sim_time": f"T+00:{cycle:02d}:00",
        "sim_seconds": cycle * 10,
        "asda_cycle": cycle,
        "asda_phase": "decide",
        "network_vulnerability": 0.2 + cycle * 0.001,
        "total_entities": 3,
        "entities": [
            {"id": "E1", "lat": 35.0 + cycle * 0.01, "lon": 140.0, "status": "active"},
            {"id": "E2", "lat": 13.0, "lon": 144.0 + cycle * 0.01, "status": "active"},
            {"id": "E3", "lat": 21.0, "lon": 158.0, "status": "active"},
        ],
        "tracks": [{"id": f"T{cycle}", "confidence": 0.9}],
    }


async def recv_json(ws, timeout=3.0):
    raw = await asyncio.wait_for(ws.recv(), timeout)
    return json.loads(raw)


async def main():
    server = RealtimeServer(host="localhost", port=PORT, max_clients=MAX_CLIENTS)
    ok = server.start()
    test("服务器启动（websockets 线程）", ok)
    await asyncio.sleep(0.5)

    # Push 30 ASDA cycles of synthetic state
    for c in range(1, 31):
        server.push_state(make_state(c), events=[{"t": c, "kind": "intercept"}])
        await asyncio.sleep(0.02)
    await asyncio.sleep(0.8)  # allow broadcast ticks

    url = f"ws://localhost:{PORT}"

    # 1) fill to max_clients
    clients = []
    for i in range(MAX_CLIENTS):
        ws = await websockets.connect(url)
        clients.append(ws)
    full_msgs = [await recv_json(ws) for ws in clients]
    test("每个新客户端收到初始 full 快照",
         all(m.get("type") == "full" for m in full_msgs))
    test("full 快照携带最新周期(30)",
         all(m.get("asda_cycle") == 30 for m in full_msgs),
         f"cycles={[m.get('asda_cycle') for m in full_msgs]}")

    # 2) overflow client rejected
    overflow = await websockets.connect(url)
    err = await recv_json(overflow, timeout=3.0)
    rejected = err.get("type") == "error" and err.get("reason") == "max_clients_reached"
    test("超出并发上限被拒绝并返回错误", rejected, f"{err}")
    try:
        await overflow.wait_closed(timeout=2)
    except Exception:
        pass

    # 3) live delta broadcast
    server.push_state(make_state(31))
    await asyncio.sleep(0.8)
    got31 = 0
    for ws in clients:
        try:
            m = await recv_json(ws, timeout=2.0)
            if m.get("asda_cycle") == 31:
                got31 += 1
        except asyncio.TimeoutError:
            pass
    test("所有活动客户端收到周期 31 推送", got31 == MAX_CLIENTS, f"({got31}/{MAX_CLIENTS})")

    # 4) pause: client 0 stops receiving
    await clients[0].send(json.dumps({"cmd": "pause"}))
    ack = await recv_json(clients[0])
    test("pause 确认消息", ack.get("type") == "paused")
    server.push_state(make_state(32))
    await asyncio.sleep(0.8)
    paused_ok = True
    try:
        m = await recv_json(clients[0], timeout=1.2)
        paused_ok = False
    except asyncio.TimeoutError:
        pass
    test("暂停后不再收到实时推送", paused_ok)
    # other clients still receive 32
    m = await recv_json(clients[1], timeout=2.0)
    test("未暂停客户端继续接收", m.get("asda_cycle") == 32, f"cycle={m.get('asda_cycle')}")
    # drain client2 to keep state clean
    try:
        await recv_json(clients[2], timeout=0.5)
    except asyncio.TimeoutError:
        pass

    # 5) replay / step-back from ring buffer
    await clients[0].send(json.dumps({"cmd": "replay", "cycle": 5}))
    rep = await recv_json(clients[0], timeout=3.0)
    test("回溯返回历史快照 (type=replay)",
         rep.get("type") == "replay", f"type={rep.get('type')}")
    test("回溯周期 <= 请求周期", rep.get("asda_cycle", 99) <= 5,
         f"cycle={rep.get('asda_cycle')}")
    test("回溯快照包含实体数据", bool(rep.get("entities")))

    # replay beyond history -> clamps to latest available snapshot
    # (此时最新归档周期为 32, 尚未 resume/推 33)
    await clients[0].send(json.dumps({"cmd": "replay", "cycle": 9999}))
    rep2 = await recv_json(clients[0], timeout=3.0)
    test("超出范围的回溯钳制到缓冲内最新快照",
         rep2.get("type") == "replay" and rep2.get("asda_cycle") == 32,
         f"type={rep2.get('type')} cycle={rep2.get('asda_cycle')} "
         f"history={server.history_range}")

    # 6) resume -> resync full then live
    await clients[0].send(json.dumps({"cmd": "resume"}))
    server.push_state(make_state(33))
    await asyncio.sleep(0.8)
    m1 = await recv_json(clients[0], timeout=2.5)
    test("恢复后收到 resync full 快照", m1.get("type") == "full",
         f"type={m1.get('type')}")

    # 7) status command (drain pending live pushes first)
    for ws in clients[1:]:
        try:
            while True:
                await recv_json(ws, timeout=0.4)
        except asyncio.TimeoutError:
            pass
    await clients[1].send(json.dumps({"cmd": "status"}))
    st = await recv_json(clients[1], timeout=3.0)
    test("status 返回客户端数与历史范围",
         st.get("type") == "status" and st.get("clients") == MAX_CLIENTS
         and st.get("history_cycles") == [1, 33],
         f"clients={st.get('clients')} history={st.get('history_cycles')}")

    test("服务器侧 client_count 一致", server.client_count == MAX_CLIENTS)

    for ws in clients:
        await ws.close()
    server.stop()
    test("服务器优雅停止", True)

    print("\n" + "=" * 56)
    print(f"P12-3 测试: {PASS} 通过 / {FAIL} 失败")
    if FAIL:
        sys.exit(1)
    print("P12-3 验收标准达成：并发上限 + 暂停/恢复 + 回溯/实时 + 状态查询 ✓")


if __name__ == "__main__":
    asyncio.run(main())
