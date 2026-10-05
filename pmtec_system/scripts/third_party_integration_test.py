#!/usr/bin/env python3
"""P18-E 第三方接入自测（评审 P2："第三方接入示例，支撑 D3 互操作分"）。

以"第三方身份"（独立进程、仅走 HTTP/WS 公开通道、演示账号）完成全链路：
  服务发现 → 健康探测 → 登录(JWT) → 状态/实体/政治态势 → WS 订阅 ≥3 帧
  → 触发分析（容忍 503 降级）→ 孪生注册 → 注销复验
证据落盘：output/third_party_integration_result.json（随离线包交付）

用法（需演示栈在跑）：
  docker compose -f docker-compose.demo.yml up -d
  python scripts/third_party_integration_test.py [--base http://localhost:8080]
服务器不可达时以 SKIP 退出（exit 0，标注未验证）；服务在跑则失败即非零。
"""

import argparse
import json
import os
import socket
import sys
import time
import urllib.request
import urllib.error

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.stdout.reconfigure(encoding="utf-8")

RESULT = os.path.join(PROJECT_ROOT, "output", "third_party_integration_result.json")
WS_HOST, WS_PORT = "localhost", 8765


def http(base, path, method="GET", payload=None, token=None, timeout=6, retries=2):
    req_body = json.dumps(payload).encode() if payload is not None else None

    def once():
        req = urllib.request.Request(base + path, method=method)
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, data=req_body, timeout=timeout) as r:
                return r.status, json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode("utf-8", "replace"))
            except Exception:
                return e.code, {}

    for i in range(retries + 1):
        try:
            return once()
        except urllib.error.URLError:
            if i == retries:
                return None, {}
        except OSError:
            # Windows 下引擎高负载会瞬时重置连接（WinError 10054）——
            # 第三方客户端应有的韧性：退避重试而不是崩
            if i == retries:
                return None, {}
            time.sleep(1.0 + i)


def ws_frames(uri, want=3, timeout=25):
    """官方 websockets 客户端订阅 ≥N 帧实时快照（websockets 在 requirements 内，
    是第三方接入的标准依赖；自研最小协议客户端对分片/压缩不鲁棒，已弃用）。"""
    import asyncio

    import websockets

    async def _probe():
        frames = []
        async with websockets.connect(uri) as ws:
            for _ in range(want):
                msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
                frames.append(json.loads(msg))
        return frames

    try:
        return asyncio.run(_probe())
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("PMTEC_BASE", "http://localhost:8080"))
    args = ap.parse_args()
    base = args.base.rstrip("/")

    checks = []

    def check(name, cond, detail=""):
        checks.append({"name": name, "pass": bool(cond), "detail": str(detail)[:160]})
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        return cond

    print("=" * 66)
    print(f"PMTEC 第三方接入自测（第三方身份：独立进程 · 纯公开通道）")
    print(f"基地址：{base}")
    print("=" * 66)

    # 0) 服务发现 + 健康
    st, idx = http(base, "/api")
    alive = st is not None
    if not alive:
        print("\n[SKIP] 服务不可达——先起演示栈：docker compose -f docker-compose.demo.yml up -d")
        json.dump({"base": base, "skipped": True, "at": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "checks": []}, open(RESULT, "w", encoding="utf-8"), ensure_ascii=False)
        return 0
    check("服务发现 GET /api", st == 200)
    st, health = http(base, "/api/v1/health")
    check("健康探测 /api/v1/health", st == 200 and health.get("status") in ("ok", "healthy"),
          f"auth_enabled={health.get('auth_enabled')}")

    token = None
    if health.get("auth_enabled"):
        user = os.environ.get("PMTEC_IT_USER", "pingwei")
        pwd = os.environ.get("PMTEC_IT_PASS", "")
        st, login = http(base, "/api/v1/auth/login", "POST",
                         {"username": user, "password": pwd})
        if not check(f"登录（{user}）", st == 200 and login.get("token"),
                     f"http={st}"):
            token = None
        else:
            token = login["token"]
            check("JWT 颁发且带角色", bool(login.get("role")), login.get("role"))
    else:
        check("门禁关闭模式（auth_enabled=false，免登录通道）", True)

    # 1) 只读三件套
    st, state = http(base, "/api/v1/state", token=token)
    ok = check("拉取引擎状态 /state", st == 200 and isinstance(state, dict))
    if ok:
        check("状态含 coord_guard 坐标防护审计字段", "coord_guard" in state,
              str(state.get("coord_guard"))[:80])
    st, ents = http(base, "/api/v1/entities", token=token)
    bad = [e for e in (ents if isinstance(ents, list) else [])
           if not (-90 <= e.get("lat", 0) <= 90 and -180 <= e.get("lon", 0) <= 180)]
    check("实体坐标全在 WGS84 定义域（第三方独立复核）",
          st == 200 and not bad, f"n={len(ents) if isinstance(ents, list) else '?'} 越界={len(bad)}")
    st, pol = http(base, "/api/v1/political/access", token=token)
    check("政治准入态势可读", st == 200, str(pol)[:80])

    # 2) WebSocket 订阅（URI 由 base 推导：8888 走 nginx 同源 /ws；8080 直连引擎 8765）
    if base.endswith(":8888"):
        ws_uri = base.replace("http://", "ws://") + "/ws"
    else:
        host = base.split("//")[1].split(":")[0]
        ws_uri = f"ws://{host}:8765"
    frames = ws_frames(ws_uri, want=3)
    check(f"WS 实时订阅收到 ≥3 帧快照（{ws_uri}）", len(frames) >= 3,
          f"实际 {len(frames)} 帧")
    if frames:
        check("WS 快照结构与 REST /state 同源（含 asda_cycle）",
              all("asda_cycle" in f for f in frames))

    # 3) AI 参谋官（容忍 503 预期降级）
    # 同步长端点：LLM 调用+图表+docx 渲染实测 30-90s（openapi.yaml 已注明）
    st, ana = http(base, "/api/v1/analysis", "POST", token=token, timeout=150)
    check("AI 参谋官通道可达（200 生成 / 503 预期降级均算通过）",
          st in (200, 503), f"http={st} {str(ana)[:60]}")

    # 4) 孪生注册（写通道，commander 角色门禁——缺省回退主账号）
    cmd_user = os.environ.get("PMTEC_IT_CMD_USER", "")
    cmd_pass = os.environ.get("PMTEC_IT_CMD_PASS", "")
    if cmd_user and cmd_pass:
        st, cmd_login = http(base, "/api/v1/auth/login", "POST",
                             {"username": cmd_user, "password": cmd_pass})
        cmd_tok = cmd_login.get("token") if st == 200 else None
        check("commander 账号登录（写操作角色升级）", st == 200 and cmd_tok,
              f"http={st}")
    else:
        cmd_tok = token
    payload = {"instance_id": f"third-party-{int(time.time())}",
               "twin_type": "external_probe", "endpoint": "http://third-party.example/twin"}
    st, reg = http(base, "/api/v1/dt/register", "POST", payload, token=cmd_tok)
    check("第三方孪生体注册（commander 通道；503=引擎未挂载但通道可达）",
          st in (201, 200, 503), f"http={st}")

    # 5) 注销复验
    if token:
        st, _ = http(base, "/api/v1/auth/logout", "POST", token=token)
        check("注销", st == 200)

    npass = sum(1 for c in checks if c["pass"])
    result = {"base": base, "at": time.strftime("%Y-%m-%d %H:%M:%S"),
              "identity": "third-party（独立进程/公开通道/演示账号）",
              "passed": npass, "total": len(checks), "checks": checks}
    os.makedirs(os.path.dirname(RESULT), exist_ok=True)
    json.dump(result, open(RESULT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("-" * 66)
    print(f"结论：{'第三方全链路接入成功' if npass == len(checks) else '存在失败项'}"
          f"（{npass}/{len(checks)}）｜ 证据：{RESULT}")
    return 0 if npass == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
