"""P13: 本地 CI/CD 流水线执行器 — 6 阶段与 GitHub Actions 同口径

Stages: lint -> test -> build(docker) -> security(trivy) -> push(local tag) -> deploy(validate)
每阶段完成即写 local_run.json (可轮询进度)。
产出: output/local_run.json + output/pipeline_logs/<stage>.log
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"d:\APPs\数字孪生挑战赛"
PS = os.path.join(ROOT, "pmtec_system")
OUT = os.path.join(PS, "output")
LOGS = os.path.join(OUT, "pipeline_logs")
PY = sys.executable
os.makedirs(LOGS, exist_ok=True)

STAGES = ["lint", "test", "build", "security", "push", "deploy"]
run = {
    "runner": f"Docker Desktop / {ROOT}",
    "started_at": datetime.now(timezone.utc).isoformat(),
    "stages": {},
}


def save():
    with open(os.path.join(OUT, "local_run.json"), "w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False, indent=2)


def run_stage(name, cmd, cwd=None, timeout=3600):
    log_path = os.path.join(LOGS, f"{name}.log")
    t0 = time.time()
    entry = {"status": "in_progress", "started_at": datetime.now(timezone.utc).isoformat()}
    run["stages"][name] = entry
    save()
    with open(log_path, "wb") as lf:
        p = subprocess.run(cmd, cwd=cwd or PS, stdout=lf, stderr=subprocess.STDOUT)
    dur = time.time() - t0
    entry.update({
        "status": "completed",
        "conclusion": "success" if p.returncode == 0 else "failure",
        "duration_s": round(dur, 1),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "log": log_path,
        "returncode": p.returncode,
    })
    save()
    with open(log_path, "rb") as f:
        tail = f.read()[-800:].decode("utf-8", "replace")
    print(f"[{name}] {entry['conclusion']} ({dur:.0f}s)")
    print("   ", tail.strip().splitlines()[-1][:150] if tail.strip() else "")
    return entry["conclusion"] == "success"


print("== PMTEC Local CI/CD Pipeline ==")

# Stage 1: lint
ok1 = run_stage("lint", [PY, "-m", "ruff", "check", "."])

# Stage 2: test (proto 生成 + 导入冒烟, 与 CI 同口径)
proto_cmd = [PY, "-m", "grpc_tools.protoc", "-I./proto",
             "--python_out=./proto/generated",
             "--grpc_python_out=./proto/generated", "proto/dtb_model.proto"]
ok_proto = run_stage("test", proto_cmd)
if ok_proto:
    smoke = (
        "import sys; sys.path.insert(0, 'proto/generated');"
        "from config import GRPC_HOST, GRPC_PORT;"
        "print(f'[OK] config: {GRPC_HOST}:{GRPC_PORT}');"
        "from services.prometheus_metrics import MetricsExporter;"
        "m = MetricsExporter(); print(f'[OK] prometheus: {m.enabled}');"
        "from live_data import LiveAdapterManager;"
        "mgr = LiveAdapterManager();"
        "print(f'[OK] live_data: adsb={mgr.adsb.use_real_api}');"
        "print('All imports successful')"
    )
    ok2 = run_stage("test_smoke", [PY, "-c", smoke])
    run["stages"]["test"]["conclusion"] = (
        "success" if ok_proto and ok2 else "failure")
    save()

# Stage 3: build (docker)
ok3 = run_stage("build", ["docker", "build", "-t", "pmtec-distributed:ci",
                          "."], timeout=5400)

# Stage 4: security (trivy 扫镜像)
ok4 = run_stage("security", ["docker", "run", "--rm",
                             "-v", "/var/run/docker.sock:/var/run/docker.sock",
                             "aquasec/trivy:latest", "image",
                             "--severity", "HIGH,CRITICAL",
                             "--quiet", "pmtec-distributed:ci"],
                timeout=1800)

# Stage 5: push (本地 tag, 无 registry 凭据故不实推)
ok5 = run_stage("push", ["docker", "tag", "pmtec-distributed:ci",
                         "ghcr.io/yigenfeng0707-netizen/pmtec-dtc2026/"
                         "pmtec-distributed:local"])

# Stage 6: deploy (compose 配置校验)
compose = os.path.join(PS, "docker-compose.yml")
if os.path.exists(compose):
    ok6 = run_stage("deploy", ["docker", "compose", "-f", compose, "config", "-q"])
else:
    run["stages"]["deploy"] = {"status": "completed",
                               "conclusion": "skipped",
                               "detail": "docker-compose.yml 不存在"}
    ok6 = True
    save()

run["finished_at"] = datetime.now(timezone.utc).isoformat()
concl = all(run["stages"].get(s, {}).get("conclusion") in
            ("success", "skipped") for s in STAGES)
run["conclusion"] = "success" if concl else "failure"
save()
print(f"== PIPELINE {run['conclusion'].upper()} ==")
