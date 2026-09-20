#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P13 REST /api/v1/analysis 端到端验证：
1. 启动仿真 (子进程)
2. 等待 REST 就绪 -> GET /analysis (应 not_generated)
3. POST /analysis 触发实时 LLM 分析，期间并发 GET /health 验证多线程不阻塞
4. GET /analysis (应返回缓存的分析结果)
结果写 output/rest_analysis_test_result.json
"""
import json
import os
import subprocess
import sys
import threading
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "http://localhost:8080/api/v1"
OUT = os.path.join(ROOT, "output", "rest_analysis_test_result.json")

results = {"steps": []}


def log(msg):
    print(msg, flush=True)
    results["steps"].append(msg)


def main():
    log("[1] 启动仿真子进程 (duration=600, --no-grpc)")
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", "main.py", "--duration", "600",
         "--no-grpc", "--seed", "42"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        # 等 REST 就绪
        ready = False
        for _ in range(60):
            try:
                requests.get(f"{BASE}/health", timeout=3)
                ready = True
                break
            except requests.RequestException:
                time.sleep(1)
        log(f"[2] REST 就绪: {ready}")
        if not ready:
            return

        r = requests.get(f"{BASE}/analysis", timeout=10)
        log(f"[3] GET /analysis (初始): {r.json().get('status')}")

        # POST 触发分析，同时并发测 health 延迟
        health_latencies = []
        stop = threading.Event()

        def probe():
            while not stop.is_set():
                try:
                    t0 = time.time()
                    requests.get(f"{BASE}/health", timeout=10)
                    health_latencies.append(round((time.time() - t0) * 1000, 1))
                except requests.RequestException:
                    health_latencies.append(-1)
                time.sleep(1)

        probe_thread = threading.Thread(target=probe, daemon=True)
        probe_thread.start()

        t0 = time.time()
        r = requests.post(f"{BASE}/analysis", json={}, timeout=300)
        elapsed = time.time() - t0
        stop.set()
        probe_thread.join(timeout=2)

        body = r.json()
        log(f"[4] POST /analysis: HTTP {r.status_code}, 耗时 {elapsed:.1f}s, "
            f"model={body.get('model')}, "
            f"usage={body.get('usage', {}).get('prompt_tokens')}/"
            f"{body.get('usage', {}).get('completion_tokens')}")
        md = body.get("markdown", "")
        log(f"[5] 分析报告前 200 字: {md[:200]}")

        r2 = requests.get(f"{BASE}/analysis", timeout=10)
        cached = r2.json()
        log(f"[6] GET /analysis (缓存): status={cached.get('status')}, "
            f"generated_at={cached.get('generated_at')}")

        blocked = [x for x in health_latencies if x > 5000]
        log(f"[7] 并发 health 探测: {len(health_latencies)} 次, "
            f"最大延迟 {max(health_latencies) if health_latencies else 0}ms, "
            f"阻塞(>5s)次数 {len(blocked)} (多线程验证)")

        results["ok"] = (
            r.status_code == 200
            and cached.get("status") == "generated"
            and len(blocked) == 0
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log("[8] 仿真子进程已终止")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(f"\n{'PASS' if results.get('ok') else 'FAIL'} -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
