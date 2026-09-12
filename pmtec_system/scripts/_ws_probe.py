# -*- coding: utf-8 -*-
"""WS 探针: 连接 8765, 收 3 条消息, 检查事件字段 (结果落盘)"""
import asyncio
import json
import sys

import websockets

OUT = r"d:\APPs\数字孪生挑战赛\_ws_probe_result.txt"
lines = []


async def main():
    async with websockets.connect("ws://localhost:8765") as ws:
        for i in range(3):
            raw = await asyncio.wait_for(ws.recv(), timeout=40)
            m = json.loads(raw)
            evs = m.get("events") if m.get("type") == "full" else m.get("new_events")
            lines.append(f"msg{i}: type={m.get('type')} cycle={m.get('asda_cycle')} "
                         f"phase={m.get('asda_phase')} events={len(evs) if evs else 0}")
            if evs:
                lines.append("  keys: " + str(list(evs[-1].keys())))
                lines.append("  sample: " + json.dumps(evs[-1], ensure_ascii=False)[:300])
            elif i == 0:
                lines.append("  top keys: " + str(list(m.keys())))

try:
    asyncio.run(main())
    lines.append("PROBE OK")
except Exception as e:
    lines.append(f"PROBE ERROR: {e}")
with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
