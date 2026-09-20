#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P13.3 并发修复验证：复现 live_demo6 竞态场景（T+36777s 崩溃根因）

背景：
    REST 网关多线程化（ThreadingHTTPServer）后，REST/Prometheus/监控线程
    与仿真主线程（ASDA Sense 阶段 fuse_tracks / TrackManager.update 增删
    共享字典）并发读写，Python 层迭代 dict 中途变更抛出
    RuntimeError: dictionary changed size during iteration。

修复（P13.3-fix）：
    get_state_dict / active_tracks / top_twins / summary 中对共享字典
    的迭代改为 list(...) 原子快照（CPython 中 list(d.values()) 单次
    C 层调用完成，不会在迭代中途释放 GIL）。

验证：
    A [对照组] 旧写法（裸 .values() 迭代）在写线程并发下必然抛错
    B [修复组] 新写法（list() 快照）在同等压力下 0 异常
    C [真实模块] TrackManager.active_tracks / TwinSyncManager.top_twins
      与 summary 在写线程高频增删下 0 异常

Run: python -X utf8 scripts/verify_p13_3_concurrency.py
"""
import os
import sys
import threading
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

DURATION_S = 5.0


class StubKalmanTrack:
    def __init__(self, i):
        self.status = "confirmed" if i % 3 else "tentative"

    def to_dict(self):
        return {"status": self.status, "lat": 1.0, "lon": 2.0}


class StubTwin:
    def __init__(self, i):
        self.twin_id = f"TWIN-{i}"
        self.name = f"twin-{i}"
        self.kind = ["base", "threat", "scenario"][i % 3]
        self.fidelity = 0.9 + (i % 10) / 100
        self.mean_deviation = 0.01
        self.sync_count = i

    def to_dict(self):
        return {"twin_id": self.twin_id, "kind": self.kind}


def main():
    stop = threading.Event()
    errors = {"A": 0, "B": 0, "C": 0}
    iters = {"A": 0, "B": 0, "C": 0}
    lock = threading.Lock()

    # ---- 共享状态（写线程 vs 读线程）----
    kalman_a = {}  # 对照组：旧写法读
    kalman_b = {}  # 修复组：新写法读
    seq = [0]

    # ---- 真实模块（修复组 C）----
    from models.track import TrackManager
    from dt_platform.twin_sync import TwinSyncManager

    track_mgr = TrackManager()
    tsm = TwinSyncManager(registry=None)

    # ============ 写线程（模拟仿真主线程 ASDA 循环）============
    def writer():
        i = 0
        while not stop.is_set():
            with lock:
                seq[0] += 1
                n = seq[0]
            # 模拟 fuse_tracks：新增 + 删除 kalman 字典
            for d in (kalman_a, kalman_b):
                d[n] = StubKalmanTrack(n)
                if n % 2 == 0:
                    d.pop(n // 2, None)
                if len(d) > 50:
                    d.clear()
            # 模拟 TrackManager.fuse：观测进 → 融合 → 删 stale
            track_mgr.add_observation(
                lat=35.0 + (i % 10) * 0.01,
                lon=139.0 + (i % 7) * 0.01,
                heading=i % 360,
                speed=800,
                classification="missile",
                source="AN/TPY-2",
            )
            track_mgr.fuse()
            # 模拟 twin_sync.sync()：增删孪生体
            tsm.twins[f"TWIN-{n}"] = StubTwin(n)
            if n % 3 == 0:
                tsm.twins.pop(f"TWIN-{n - 1}", None)
                tsm.twins[f"HIST-TWIN-{n}"] = StubTwin(n)
            i += 1

    # ============ 读线程 A：旧写法（预期抛错，对照组）============
    def reader_old():
        while not stop.is_set():
            try:
                _ = [
                    t.to_dict()
                    for t in kalman_a.values()
                    if t.status in ("tentative", "confirmed")
                ]
                with lock:
                    iters["A"] += 1
            except RuntimeError:
                with lock:
                    errors["A"] += 1

    # ============ 读线程 B：新写法（修复后 get_state_dict 逻辑）============
    def reader_fixed():
        while not stop.is_set():
            try:
                _ = [
                    t.to_dict()
                    for t in list(kalman_b.values())
                    if t.status in ("tentative", "confirmed")
                ]
                with lock:
                    iters["B"] += 1
            except RuntimeError:
                with lock:
                    errors["B"] += 1

    # ============ 读线程 C：真实模块（REST/Prometheus/监控并发）============
    def reader_modules():
        while not stop.is_set():
            try:
                _ = [t.to_dict() for t in track_mgr.active_tracks]
                _ = tsm.top_twins(limit=8)
                _ = tsm.summary()
                with lock:
                    iters["C"] += 1
            except RuntimeError:
                with lock:
                    errors["C"] += 1

    threads = [threading.Thread(target=writer)]
    for _ in range(3):
        threads.append(threading.Thread(target=reader_old))
        threads.append(threading.Thread(target=reader_fixed))
        threads.append(threading.Thread(target=reader_modules))

    print(f"[P13.3] 并发压力验证：1 写线程 + 9 读线程 x {DURATION_S:.0f}s")
    for t in threads:
        t.start()
    time.sleep(DURATION_S)
    stop.set()
    for t in threads:
        t.join()

    print(
        f"  A 旧写法(裸 .values() 迭代): {iters['A']:>6} 次读取, "
        f"RuntimeError {errors['A']} 次  <- 修复前的崩溃路径"
    )
    print(
        f"  B 新写法(list() 原子快照): {iters['B']:>6} 次读取, "
        f"RuntimeError {errors['B']} 次"
    )
    print(
        f"  C 真实模块(active_tracks/top_twins/summary): {iters['C']:>6} 组读取, "
        f"RuntimeError {errors['C']} 次"
    )

    ok = (
        errors["B"] == 0
        and errors["C"] == 0
        and errors["A"] > 0  # 对照组必须暴露竞态，否则本次压力无效
        and iters["B"] > 1000
        and iters["C"] > 100
    )
    print(
        "\n[FAIL] 修复路径仍出现并发异常"
        if not ok
        else "\n[OK] 修复路径 0 异常 — 对照组旧写法如预期暴露竞态, P13.3 原子快照修复有效"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
