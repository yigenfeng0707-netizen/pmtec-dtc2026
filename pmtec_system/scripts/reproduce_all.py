#!/usr/bin/env python3
"""P18-C5 一键复现脚本（评审 P0："复现包（环境+依赖+脚本+端到端日志）"）。

评审/第三方拿到仓库后，跑这一个脚本即可完成端到端复现并留下完整日志：
  依赖体检 → 口径自检 → 数据字典再生 → 必答五问实跑 → 验收测试（快速档）

用法：
  python scripts/reproduce_all.py            # 快速档（约 3-5 分钟）
  python scripts/reproduce_all.py --full     # 全量 27 个测试文件（约 30-60 分钟）
日志：output/reproduce_log_<时间戳>.txt（随离线包交付，作为端到端日志样例）
"""

import argparse
import os
import subprocess
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(PROJECT_ROOT)
sys.path.insert(0, PROJECT_ROOT)
sys.stdout.reconfigure(encoding="utf-8")

CORE_DEPS = ["grpc", "websockets", "numpy", "scipy", "networkx",
             "rdflib", "pyshacl", "matplotlib", "requests", "jwt"]
OPTIONAL_DEPS = {"owlready2": "HermiT 一致性推理（需 JVM java≥8）；缺失时 P14 推理断言跳过",
                 "torch": "DQN 推理；缺失时回退规则基线",
                 "prometheus_client": "指标端点"}


class Logger:
    def __init__(self, path):
        self.path = path
        self.lines = []

    def __call__(self, msg):
        print(msg)
        self.lines.append(msg)

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(self.lines) + "\n")


def run_step(log, title, cmd, cwd=PROJECT_ROOT, timeout=1800, check=True):
    log(f"\n{'=' * 66}\n[步骤] {title}\n[命令] {' '.join(cmd)}\n{'-' * 66}")
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, encoding="utf-8", errors="replace")
    tail = (proc.stdout or "").strip().splitlines()[-25:]
    for ln in tail:
        log("  " + ln)
    if (proc.stderr or "").strip():
        log("  [stderr 尾部] " + (proc.stderr.strip().splitlines()[-1] or ""))
    dt = time.time() - t0
    ok = proc.returncode == 0
    log(f"[{'PASS' if ok else 'FAIL'}] {title}（{dt:.1f}s，退出码 {proc.returncode}）")
    if check and not ok:
        log("!! 复现在此步骤失败——上方输出即最小定位信息")
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="全量 27 个测试文件")
    args = ap.parse_args()

    log = Logger(os.path.join(
        PROJECT_ROOT, "output",
        f"reproduce_log_{time.strftime('%Y%m%d_%H%M%S')}.txt"))

    log("PMTEC 端到端复现日志（P18 复现包）")
    log(f"时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"仓库根：{REPO_ROOT}")
    log(f"Python：{sys.version.split()[0]} ｜ 平台：{sys.platform}")
    log("信息截至 2026-09（CRS R47589 / DoD FY2024 BSR）｜"
        "数量口径 67/22/15 见 pmtec_system/README.md「评估口径说明」")

    # ① 依赖体检
    log(f"\n{'=' * 66}\n[步骤] 依赖体检\n{'-' * 66}")
    missing = []
    for mod in CORE_DEPS:
        try:
            __import__(mod)
            log(f"  [OK] {mod}")
        except ImportError:
            missing.append(mod)
            log(f"  [缺] {mod}")
    for mod, note in OPTIONAL_DEPS.items():
        try:
            __import__(mod)
            log(f"  [OK] {mod}（{note}）")
        except ImportError:
            log(f"  [可选缺] {mod}——{note}")
    if missing:
        log("\n  补装命令：pip install -r pmtec_system/requirements.txt（缺 " + str(missing) + "）")
        log("!! 核心依赖缺失，终止（保证「复现环境如实」而非带病跑完）")
        log.save()
        return 1

    ok = True
    # ② 口径自检
    ok &= run_step(log, "口径自检（67/22/15 防漂移）",
                   [sys.executable, "pmtec_system/scripts/caliber_check.py"],
                   cwd=REPO_ROOT)
    # ③ 数据字典再生
    ok &= run_step(log, "数据字典再生（docs/PMTEC-数据字典.md）",
                   [sys.executable, "scripts/generate_data_dictionary.py"])
    # ④ 五问实跑
    ok &= run_step(log, "必答五问实跑（快速档 MC n=2000）",
                   [sys.executable, "scripts/five_questions_analysis.py", "--fast"])
    # ⑤ 验收测试
    quick_tests = ["test_p17_semantic_tools.py", "test_p18_five_questions.py",
                   "test_p14_ontology.py", "test_p16_dodaf.py", "test_web_auth.py"]
    if args.full:
        tests = sorted(t for t in os.listdir(PROJECT_ROOT)
                       if t.startswith("test_") and t.endswith(".py"))
    else:
        tests = [t for t in quick_tests if os.path.exists(
            os.path.join(PROJECT_ROOT, t))]
    for t in tests:
        ok &= run_step(log, f"验收测试 {t}",
                       [sys.executable, "-X", "utf8", t],
                       timeout=3600 if args.full else 900)

    log(f"\n{'=' * 66}")
    log(f"复现结论：{'全部步骤通过——交付物可由脚本再生' if ok else '存在失败步骤（见上）'}")
    log(f"日志已保存：{log.path}")
    log.save()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
