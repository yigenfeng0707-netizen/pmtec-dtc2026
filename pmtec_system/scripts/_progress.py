"""总进度检查: 本地流水线 + 云端 Actions 最新 run"""
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
REPO = "yigenfeng0707-netizen/pmtec-dtc2026"

print("== 本地流水线 ==")
try:
    r = json.load(open(r"d:\APPs\数字孪生挑战赛\pmtec_system\output\local_run.json",
                       encoding="utf-8"))
    for k, v in r["stages"].items():
        print(f"  {k:9s} | {v.get('status'):10s} | {v.get('conclusion')} |"
              f" {v.get('duration_s', '-')}s")
    if "conclusion" in r:
        print("  RESULT:", r["conclusion"])
except FileNotFoundError:
    print("  (尚未开始)")
except Exception as e:
    print("  err:", e)

print("== 云端 Actions (最新) ==")
rr = subprocess.run(
    ["gh", "api", f"repos/{REPO}/actions/runs?per_page=1"], capture_output=True)
d = json.loads(rr.stdout)
w = d["workflow_runs"][0]
print(f"  run {w['id']} | {w['status']} | {w['conclusion']} | {w['head_sha'][:8]}")
if w["status"] != "completed":
    rj = subprocess.run(
        ["gh", "api", f"repos/{REPO}/actions/runs/{w['id']}/jobs"],
        capture_output=True)
    for j in json.loads(rj.stdout)["jobs"]:
        if j["status"] != "completed":
            step = next((s["name"] for s in j.get("steps", [])
                         if s["status"] != "completed"), "")
            print(f"  -> {j['name']}: {step}")
