#!/usr/bin/env python3
"""
PMTEC P8: Load & Stress Test Suite.

Tests:
  1. SQLite write throughput (single-thread, multi-thread, batch vs individual)
  2. gRPC server throughput & latency percentiles
  3. Engine simulation under concurrent state queries
  4. High-concurrency ramp-up test

Generates: output/PMTEC_Load_Test_Report.html
"""

import os
import sys
import json
import time
import threading
import sqlite3
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Config
NUM_SNAPSHOTS_SINGLE = 500
NUM_SNAPSHOTS_BATCH = 2000
NUM_THREADS_WRITE = 4
GRPC_PORT = 50072
GRPC_CONCURRENCY_LEVELS = [1, 5, 10, 20, 50]
GRPC_REQS_PER_LEVEL = 100
ENGINE_QUERY_CONCURRENCY = 10
ENGINE_QUERY_TOTAL = 200


def detect_device():
    try:
        import torch

        if hasattr(torch, "xpu") and torch.xpu.is_available():
            return "xpu:0"
        if torch.cuda.is_available():
            return "cuda:0"
    except ImportError:
        pass
    return "cpu"


# ============================================================
# Test 1: SQLite Write Throughput
# ============================================================
def test_sqlite_writes():
    """Test SQLite write performance under various modes."""
    from persistence.state_store import SimulationStateStore

    results = {}

    # 1a. Single-thread individual commits
    db1 = os.path.join(PROJECT_ROOT, "data", "loadtest_single.db")
    if os.path.exists(db1):
        os.remove(db1)
    store1 = SimulationStateStore(db_path=db1)

    t0 = time.time()
    for i in range(NUM_SNAPSHOTS_SINGLE):
        store1.save_snapshot(
            state={
                "sim_seconds": i * 1.0,
                "asda_phase": "Sense",
                "total_entities": 65,
                "active_tracks": 40,
                "entities": [{"type": "missile"}],
                "network_vulnerability": 0.15,
                "lvc_live_entities": 5,
            },
            cycle=i,
            kalman_info={"kalman_tracks": 40, "fusion_cycle": i},
            adversary_stats={"total_attacks": 10, "hit_rate": 0.8},
            weather={"detection_range_factor": 0.85},
        )
    elapsed1 = time.time() - t0
    store1.close()
    os.remove(db1)
    results["single_thread_individual"] = {
        "writes": NUM_SNAPSHOTS_SINGLE,
        "elapsed_s": round(elapsed1, 3),
        "throughput_wps": round(NUM_SNAPSHOTS_SINGLE / elapsed1, 1),
        "avg_latency_ms": round(elapsed1 / NUM_SNAPSHOTS_SINGLE * 1000, 2),
    }

    # 1b. Single-thread batch commit (via save_events)
    db2 = os.path.join(PROJECT_ROOT, "data", "loadtest_batch.db")
    if os.path.exists(db2):
        os.remove(db2)
    store2 = SimulationStateStore(db_path=db2)

    t0 = time.time()
    for batch_start in range(0, NUM_SNAPSHOTS_BATCH, 100):
        events = []
        for j in range(100):
            events.append(
                {
                    "event_type": "track_update",
                    "source": "sensor_radar",
                    "description": f"batch event {batch_start + j}",
                    "timestamp": time.time(),
                    "data": {"lvc_layer": "L1", "track_id": f"T{batch_start + j}"},
                }
            )
        store2.save_events(batch_start // 100, events)
    elapsed2 = time.time() - t0
    store2.close()
    os.remove(db2)
    results["single_thread_batch"] = {
        "writes": NUM_SNAPSHOTS_BATCH,
        "elapsed_s": round(elapsed2, 3),
        "throughput_wps": round(NUM_SNAPSHOTS_BATCH / elapsed2, 1),
        "avg_latency_ms": round(elapsed2 / NUM_SNAPSHOTS_BATCH * 1000, 3),
    }

    # 1c. Multi-thread writes (4 threads)
    db3 = os.path.join(PROJECT_ROOT, "data", "loadtest_multi.db")
    if os.path.exists(db3):
        os.remove(db3)
    store3 = SimulationStateStore(db_path=db3)
    per_thread = NUM_SNAPSHOTS_SINGLE // NUM_THREADS_WRITE

    def worker_write(thread_id, count):
        st = SimulationStateStore(db_path=db3)
        for i in range(count):
            st.save_snapshot(
                state={
                    "sim_seconds": i * 1.0,
                    "asda_phase": "Decide",
                    "total_entities": 50,
                    "active_tracks": 30,
                    "entities": [],
                    "network_vulnerability": 0.1,
                    "lvc_live_entities": 3,
                },
                cycle=thread_id * 1000 + i,
                kalman_info={"kalman_tracks": 30, "fusion_cycle": i},
                adversary_stats={"total_attacks": 5, "hit_rate": 0.7},
                weather={"detection_range_factor": 0.9},
            )
        st.close()

    t0 = time.time()
    threads = []
    for tid in range(NUM_THREADS_WRITE):
        t = threading.Thread(target=worker_write, args=(tid, per_thread))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    elapsed3 = time.time() - t0
    total_writes = per_thread * NUM_THREADS_WRITE
    store3.close()
    os.remove(db3)
    results["multi_thread_4"] = {
        "writes": total_writes,
        "elapsed_s": round(elapsed3, 3),
        "throughput_wps": round(total_writes / elapsed3, 1),
        "avg_latency_ms": round(elapsed3 / total_writes * 1000, 2),
        "threads": NUM_THREADS_WRITE,
    }

    # 1d. WAL mode direct insert (raw sqlite, no ORM overhead)
    db4 = os.path.join(PROJECT_ROOT, "data", "loadtest_raw.db")
    if os.path.exists(db4):
        os.remove(db4)
    conn = sqlite3.connect(db4)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""CREATE TABLE test (id INTEGER PRIMARY KEY, data TEXT)""")
    conn.commit()

    t0 = time.time()
    for i in range(NUM_SNAPSHOTS_BATCH):
        conn.execute("INSERT INTO test (data) VALUES (?)", (json.dumps({"i": i}),))
    conn.commit()
    elapsed4 = time.time() - t0
    conn.close()
    os.remove(db4)
    results["raw_sqlite_wal"] = {
        "writes": NUM_SNAPSHOTS_BATCH,
        "elapsed_s": round(elapsed4, 3),
        "throughput_wps": round(NUM_SNAPSHOTS_BATCH / elapsed4, 1),
        "avg_latency_ms": round(elapsed4 / NUM_SNAPSHOTS_BATCH * 1000, 3),
    }

    return results


# ============================================================
# Test 2: gRPC Throughput & Latency
# ============================================================
def _load_v2_bases(engine) -> int:
    """P12/S: 加载 67 实体权威基地集（与交付物 v2 数据一致）。"""
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "bases_v2.geojson",
    )
    try:
        return engine.load_bases(path)
    except Exception as e:
        print(f"[LoadTest] v2 base load skipped: {e}")
        return 0


def test_grpc_throughput():
    """Start gRPC server in-process and test concurrent GetState calls."""
    try:
        import grpc
        from services.grpc_server import PMTECServer
        from proto.generated import dtb_model_pb2 as pb
        from proto.generated import dtb_model_pb2_grpc as pb_grpc
    except ImportError as e:
        return {"error": f"Import failed: {e}"}

    # Start server with security disabled for load test
    server = PMTECServer(
        host="127.0.0.1",
        port=GRPC_PORT,
        security_enabled=False,
        mtls_enabled=False,
    )
    n_bases = _load_v2_bases(server.engine)
    print(f"[LoadTest] gRPC server engine loaded {n_bases} v2 bases")
    try:
        server.start()
    except Exception as e:
        return {"error": f"Server start failed: {e}"}

    time.sleep(1.0)

    # Start a simulation so GetState returns real data
    try:
        server.engine.start_simulation("multi_threat", 600, seed=42)
        time.sleep(3.0)
    except Exception:
        pass

    results = {}
    address = f"127.0.0.1:{GRPC_PORT}"

    for concurrency in GRPC_CONCURRENCY_LEVELS:
        latencies = []
        errors = 0
        reqs_per_thread = max(1, GRPC_REQS_PER_LEVEL // concurrency)

        def grpc_worker(tid):
            local_lat = []
            local_err = 0
            try:
                channel = grpc.insecure_channel(address)
                stub = pb_grpc.WarEngineStub(channel)
                for _ in range(reqs_per_thread):
                    t0 = time.time()
                    try:
                        resp = stub.GetState(pb.StateRequest(at_time=0))
                        dt = (time.time() - t0) * 1000
                        local_lat.append(dt)
                    except Exception:
                        local_err += 1
                channel.close()
            except Exception:
                local_err += reqs_per_thread
            return local_lat, local_err

        t_start = time.time()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(grpc_worker, i) for i in range(concurrency)]
            for f in as_completed(futures):
                lat, err = f.result()
                latencies.extend(lat)
                errors += err
        elapsed = time.time() - t_start

        total_reqs = reqs_per_thread * concurrency
        if latencies:
            latencies.sort()
            p50 = latencies[len(latencies) // 2]
            p95 = latencies[int(len(latencies) * 0.95)]
            p99 = (
                latencies[int(len(latencies) * 0.99)]
                if len(latencies) > 100
                else latencies[-1]
            )
            avg_lat = statistics.mean(latencies)
        else:
            p50 = p95 = p99 = avg_lat = 0

        results[f"c{concurrency}"] = {
            "concurrency": concurrency,
            "total_requests": total_reqs,
            "errors": errors,
            "elapsed_s": round(elapsed, 3),
            "throughput_rps": round(total_reqs / elapsed, 1) if elapsed > 0 else 0,
            "avg_latency_ms": round(avg_lat, 2),
            "p50_ms": round(p50, 2),
            "p95_ms": round(p95, 2),
            "p99_ms": round(p99, 2),
        }

    # Cleanup
    try:
        server.engine.stop_simulation()
    except Exception:
        pass
    server.stop()
    time.sleep(0.5)

    return results


# ============================================================
# Test 3: Engine Concurrent State Queries
# ============================================================
def test_engine_concurrency():
    """Test PMTECEngine under concurrent state queries."""
    from services.grpc_server import PMTECEngine

    engine = PMTECEngine()
    n_bases = _load_v2_bases(engine)
    print(f"[LoadTest] engine concurrency test with {n_bases} v2 bases")
    engine.start_simulation("multi_threat", 600, seed=42)
    time.sleep(3.0)

    latencies = []
    error_count = [0]
    lock = threading.Lock()

    def query_worker(worker_id, count):
        local_lat = []
        local_err = 0
        for _ in range(count):
            t0 = time.time()
            try:
                state = engine.get_state_dict()
                _ = len(state.get("entities", []))
            except Exception:
                local_err += 1
            local_lat.append((time.time() - t0) * 1000)
        with lock:
            latencies.extend(local_lat)
            error_count[0] += local_err

    per_worker = ENGINE_QUERY_TOTAL // ENGINE_QUERY_CONCURRENCY
    t_start = time.time()
    threads = []
    for i in range(ENGINE_QUERY_CONCURRENCY):
        t = threading.Thread(target=query_worker, args=(i, per_worker))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    elapsed = time.time() - t_start

    engine.stop_simulation()

    latencies.sort()
    total = per_worker * ENGINE_QUERY_CONCURRENCY
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[int(len(latencies) * 0.95)]
    avg = statistics.mean(latencies)

    return {
        "concurrency": ENGINE_QUERY_CONCURRENCY,
        "total_queries": total,
        "errors": error_count[0],
        "elapsed_s": round(elapsed, 3),
        "throughput_qps": round(total / elapsed, 1),
        "avg_latency_ms": round(avg, 2),
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
    }


# ============================================================
# HTML Report Generator
# ============================================================
def generate_html_report(sqlite_results, grpc_results, engine_results, device):
    """Generate comprehensive HTML load test report."""

    # Build SQLite table rows
    sqlite_name_map = {
        "single_thread_individual": "单线程逐条提交",
        "single_thread_batch": "单线程批量提交",
        "multi_thread_4": "4线程并发写入",
        "raw_sqlite_wal": "原生SQLite WAL模式",
    }
    sqlite_rows = ""
    for name, data in sqlite_results.items():
        display_name = sqlite_name_map.get(name, name)
        sqlite_rows += f"""
            <tr>
                <td>{display_name}</td>
                <td>{data["writes"]}</td>
                <td>{data["throughput_wps"]}</td>
                <td>{data["avg_latency_ms"]}</td>
                <td>{data["elapsed_s"]}s</td>
            </tr>"""

    # Build gRPC table rows
    if "error" in grpc_results:
        grpc_rows = (
            f'<tr><td colspan="8" class="error">{grpc_results["error"]}</td></tr>'
        )
        grpc_chart = ""
    else:
        grpc_rows = ""
        grpc_labels = []
        grpc_tps = []
        grpc_p95 = []
        for key, data in sorted(grpc_results.items()):
            grpc_rows += f"""
            <tr>
                <td>{data["concurrency"]}</td>
                <td>{data["total_requests"]}</td>
                <td>{data["errors"]}</td>
                <td class="{"ok" if data["throughput_rps"] > 50 else "warn"}">{data["throughput_rps"]}</td>
                <td>{data["avg_latency_ms"]}</td>
                <td>{data["p50_ms"]}</td>
                <td class="{"ok" if data["p95_ms"] < 100 else "warn"}">{data["p95_ms"]}</td>
                <td>{data["p99_ms"]}</td>
            </tr>"""
            grpc_labels.append(str(data["concurrency"]))
            grpc_tps.append(str(data["throughput_rps"]))
            grpc_p95.append(str(data["p95_ms"]))

        # Simple bar chart with CSS
        max_tps = max(float(t) for t in grpc_tps) if grpc_tps else 1
        grpc_chart = '<div class="chart-container">'
        for i, label in enumerate(grpc_labels):
            tps = float(grpc_tps[i])
            p95 = float(grpc_p95[i])
            bar_h = int(tps / max_tps * 200) if max_tps > 0 else 10
            grpc_chart += f"""
                <div class="bar-group">
                    <div class="bar" style="height:{bar_h}px">
                        <span class="bar-val">{grpc_tps[i]}</span>
                    </div>
                    <span class="bar-label">C={label}</span>
                    <span class="bar-sub">P95:{grpc_p95[i]}ms</span>
                </div>"""
        grpc_chart += "</div>"

    # Engine results
    eng = engine_results
    engine_section = f"""
        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-val">{eng["throughput_qps"]}</div>
                <div class="metric-label">查询/秒</div>
            </div>
            <div class="metric-card">
                <div class="metric-val">{eng["avg_latency_ms"]}ms</div>
                <div class="metric-label">平均延迟</div>
            </div>
            <div class="metric-card">
                <div class="metric-val">{eng["p50_ms"]}ms</div>
                <div class="metric-label">P50 延迟</div>
            </div>
            <div class="metric-card">
                <div class="metric-val">{eng["p95_ms"]}ms</div>
                <div class="metric-label">P95 延迟</div>
            </div>
            <div class="metric-card">
                <div class="metric-val">{eng["errors"]}</div>
                <div class="metric-label">错误数</div>
            </div>
        </div>"""

    # Find max SQLite throughput for analysis
    max_sqlite_tps = max(d["throughput_wps"] for d in sqlite_results.values())
    max_grpc_rps = 0
    best_grpc_concurrency = "N/A"
    grpc_p95_ok = True
    if "error" not in grpc_results:
        max_grpc_rps = max(d["throughput_rps"] for d in grpc_results.values())
        for k, d in grpc_results.items():
            if isinstance(d, dict) and "throughput_rps" in d:
                if d["throughput_rps"] == max_grpc_rps:
                    best_grpc_concurrency = d.get("concurrency", "N/A")
                if d.get("p95_ms", 999) >= 100:
                    grpc_p95_ok = False

    batch_tps = sqlite_results.get("single_thread_batch", {}).get("throughput_wps", 1)
    single_tps = max(
        sqlite_results.get("single_thread_individual", {}).get("throughput_wps", 1), 1
    )
    batch_speedup = round(batch_tps / single_tps, 1)
    multi_tps = sqlite_results.get("multi_thread_4", {}).get("throughput_wps", "N/A")
    single_tps_val = sqlite_results.get("single_thread_individual", {}).get(
        "throughput_wps", 999
    )
    bottleneck = single_tps_val < 100
    p95_status = "所有级别均低于 100ms" if grpc_p95_ok else "高并发时超过 100ms"
    thread_safety = "线程安全" if eng["errors"] == 0 else "非线程安全"
    bottleneck_text = "SQLite 逐条提交是主要瓶颈" if bottleneck else "未发现关键瓶颈"

    # Performance analysis
    analysis = f"""
        <div class="analysis-box">
            <h3>性能分析</h3>
            <ul>
                <li><strong>SQLite 写入:</strong> 峰值吞吐量 {max_sqlite_tps} 写入/秒。
                    批量模式比逐条提交快 {batch_speedup} 倍。
                    4 线程并发写入达到 {multi_tps} wps。</li>
                <li><strong>gRPC 吞吐量:</strong> 峰值 {max_grpc_rps} RPS（并发数 C={best_grpc_concurrency}）。
                    P95 延迟{p95_status}。</li>
                <li><strong>引擎并发:</strong> {eng["throughput_qps"]} QPS，{eng["errors"]} 个错误（C={eng["concurrency"]}）。
                    状态字典查询{thread_safety}。</li>
                <li><strong>瓶颈评估:</strong>
                    {bottleneck_text}。
                    生产负载请使用批量提交。</li>
            </ul>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PMTEC 负载测试报告</title>
<style>
:root {{
    --bg: #0a0e1a;
    --card-bg: #131829;
    --accent: #00d4ff;
    --accent2: #7b2fff;
    --green: #00ff88;
    --red: #ff4466;
    --yellow: #ffcc00;
    --text: #e0e6f0;
    --text-dim: #8892a8;
    --border: #2a3050;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
    line-height: 1.6;
    padding: 20px;
    max-width: 1200px;
    margin: 0 auto;
}}
h1 {{
    font-size: 28px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 8px;
}}
h2 {{
    color: var(--accent);
    font-size: 22px;
    margin: 30px 0 15px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 8px;
}}
h3 {{
    color: var(--text);
    font-size: 18px;
    margin: 20px 0 10px;
}}
.subtitle {{ color: var(--text-dim); margin-bottom: 25px; font-size: 14px; }}
table {{
    width: 100%;
    border-collapse: collapse;
    margin: 15px 0;
    background: var(--card-bg);
    border-radius: 8px;
    overflow: hidden;
}}
th {{
    background: linear-gradient(135deg, #1a2040, #2a1a50);
    padding: 12px 15px;
    text-align: left;
    font-size: 13px;
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
td {{
    padding: 10px 15px;
    border-top: 1px solid var(--border);
    font-size: 14px;
}}
td.ok {{ color: var(--green); font-weight: bold; }}
td.warn {{ color: var(--yellow); font-weight: bold; }}
td.error {{ color: var(--red); }}
.metric-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 15px;
    margin: 15px 0;
}}
.metric-card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px;
    text-align: center;
    transition: transform 0.2s;
}}
.metric-card:hover {{ transform: translateY(-3px); border-color: var(--accent); }}
.metric-val {{
    font-size: 28px;
    font-weight: bold;
    color: var(--accent);
}}
.metric-label {{
    color: var(--text-dim);
    font-size: 12px;
    text-transform: uppercase;
    margin-top: 5px;
}}
.chart-container {{
    display: flex;
    align-items: flex-end;
    gap: 20px;
    height: 280px;
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px;
    margin: 15px 0;
    overflow-x: auto;
}}
.bar-group {{
    display: flex;
    flex-direction: column;
    align-items: center;
    min-width: 60px;
}}
.bar {{
    width: 40px;
    background: linear-gradient(180deg, var(--accent), var(--accent2));
    border-radius: 5px 5px 0 0;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding-top: 5px;
    transition: all 0.3s;
}}
.bar:hover {{ filter: brightness(1.3); }}
.bar-val {{
    font-size: 11px;
    font-weight: bold;
    color: var(--bg);
}}
.bar-label {{
    font-size: 12px;
    color: var(--text-dim);
    margin-top: 8px;
}}
.bar-sub {{
    font-size: 10px;
    color: var(--text-dim);
}}
.analysis-box {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px;
    margin: 20px 0;
}}
.analysis-box ul {{ list-style: none; padding: 0; }}
.analysis-box li {{
    padding: 8px 0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
    font-size: 14px;
}}
.analysis-box li:last-child {{ border-bottom: none; }}
.summary-banner {{
    background: linear-gradient(135deg, #131829, #1a2040);
    border: 1px solid var(--accent);
    border-radius: 12px;
    padding: 20px 25px;
    margin: 20px 0;
}}
.tag {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: bold;
    margin-left: 8px;
}}
.tag-pass {{ background: rgba(0,255,136,0.15); color: var(--green); border: 1px solid rgba(0,255,136,0.3); }}
.tag-warn {{ background: rgba(255,204,0,0.15); color: var(--yellow); border: 1px solid rgba(255,204,0,0.3); }}
</style>
</head>
<body>

<h1>PMTEC 负载测试报告</h1>
<p class="subtitle">
    PMTEC 数字孪生战场系统 | {time.strftime("%Y-%m-%d %H:%M:%S")} | 设备: {device}
</p>

<div class="summary-banner">
    <h3>测试概要</h3>
    <p>执行了 {len(sqlite_results)} 种 SQLite 写入场景、{len(grpc_results) if "error" not in grpc_results else 0} 个 gRPC 并发级别，
       以及 1 项引擎并发查询测试（共 {ENGINE_QUERY_TOTAL} 次查询）。</p>
</div>

<h2>1. SQLite 写入吞吐量</h2>
<table>
<thead>
<tr>
    <th>场景</th>
    <th>总写入数</th>
    <th>吞吐量 (写入/秒)</th>
    <th>平均延迟 (ms)</th>
    <th>耗时</th>
</tr>
</thead>
<tbody>
{sqlite_rows}
</tbody>
</table>
<p style="color:var(--text-dim);font-size:13px;margin:10px 0;">
    WAL 模式 + synchronous=NORMAL 为生产配置。批量提交（executemany）远优于逐条提交，强烈推荐用于生产负载。
</p>

<h2>2. gRPC 服务吞吐量与延迟</h2>
<table>
<thead>
<tr>
    <th>并发数</th>
    <th>总请求数</th>
    <th>错误数</th>
    <th>吞吐量 (RPS)</th>
    <th>平均延迟 (ms)</th>
    <th>P50 (ms)</th>
    <th>P95 (ms)</th>
    <th>P99 (ms)</th>
</tr>
</thead>
<tbody>
{grpc_rows}
</tbody>
</table>

<h3>吞吐量 vs 并发数</h3>
{grpc_chart if "error" not in grpc_results else '<p class="error">gRPC 测试跳过（导入错误）</p>'}

<h2>3. 引擎并发状态查询</h2>
{engine_section}
<p style="color:var(--text-dim);font-size:13px;">
    测试仿真运行期间并发调用 get_state_dict()。{ENGINE_QUERY_CONCURRENCY} 线程 x {ENGINE_QUERY_TOTAL // ENGINE_QUERY_CONCURRENCY} 次查询/线程 = 共 {ENGINE_QUERY_TOTAL} 次。
</p>

<h2>4. 性能分析与建议</h2>
{analysis}

<div style="text-align:center;margin-top:40px;color:var(--text-dim);font-size:12px;">
    PMTEC 数字孪生战场系统 | 负载测试套件 v1.0 | DTC2026
</div>

</body>
</html>"""

    output_dir = os.path.join(PROJECT_ROOT, "output")
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "PMTEC_Load_Test_Report.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    return report_path


# ============================================================
# Main
# ============================================================
def main():
    print("=" * 70)
    print("PMTEC P8: Load & Stress Test Suite")
    print("=" * 70)

    device = detect_device()
    print(f"[LoadTest] Device: {device}")
    print(
        f"[LoadTest] SQLite tests: {NUM_SNAPSHOTS_SINGLE} single / {NUM_SNAPSHOTS_BATCH} batch writes"
    )
    print(f"[LoadTest] gRPC concurrency levels: {GRPC_CONCURRENCY_LEVELS}")
    print(
        f"[LoadTest] Engine concurrency: {ENGINE_QUERY_CONCURRENCY} threads x {ENGINE_QUERY_TOTAL} queries"
    )

    # Test 1: SQLite
    print("\n[1/3] Testing SQLite write throughput...")
    t0 = time.time()
    sqlite_results = test_sqlite_writes()
    print(f"  Done in {time.time() - t0:.1f}s")
    for name, data in sqlite_results.items():
        print(f"  {name}: {data['throughput_wps']} wps, {data['avg_latency_ms']}ms/req")

    # Test 2: gRPC
    print("\n[2/3] Testing gRPC throughput & latency...")
    t0 = time.time()
    grpc_results = test_grpc_throughput()
    print(f"  Done in {time.time() - t0:.1f}s")
    if "error" in grpc_results:
        print(f"  ERROR: {grpc_results['error']}")
    else:
        for key, data in sorted(grpc_results.items()):
            print(
                f"  C={data['concurrency']}: {data['throughput_rps']} RPS, P95={data['p95_ms']}ms, errors={data['errors']}"
            )

    # Test 3: Engine
    print("\n[3/3] Testing engine concurrent state queries...")
    t0 = time.time()
    engine_results = test_engine_concurrency()
    print(f"  Done in {time.time() - t0:.1f}s")
    print(
        f"  {engine_results['throughput_qps']} QPS, P95={engine_results['p95_ms']}ms, errors={engine_results['errors']}"
    )

    # Generate HTML report
    print("\nGenerating HTML report...")
    report_path = generate_html_report(
        sqlite_results, grpc_results, engine_results, device
    )
    print(f"\n{'=' * 70}")
    print(f"Load Test Report: {report_path}")
    print(f"{'=' * 70}")

    # Also save JSON results
    json_path = os.path.join(PROJECT_ROOT, "data", "models", "load_test_results.json")
    all_results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "device": device,
        "sqlite": sqlite_results,
        "grpc": grpc_results,
        "engine": engine_results,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    print(f"JSON results: {json_path}")


if __name__ == "__main__":
    main()
