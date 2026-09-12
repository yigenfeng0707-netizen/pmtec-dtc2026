"""CI 进度检查 (run id 参数化)"""
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
REPO = "yigenfeng0707-netizen/pmtec-dtc2026"
run_id = sys.argv[1] if len(sys.argv) > 1 else "34681166131"

r = subprocess.run(["gh", "api", f"repos/{REPO}/actions/runs/{run_id}/jobs"],
                   capture_output=True)
for j in json.loads(r.stdout)["jobs"]:
    print(f"{j['name']} | {j['status']} | {j['conclusion']}")
    if j["status"] != "completed":
        for s in j.get("steps", []):
            if s["status"] != "completed":
                print(f"   -> {s['name']} ({s['status']})")
