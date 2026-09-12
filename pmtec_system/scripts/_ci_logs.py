"""拉取指定 run 中失败 job 的日志关键行"""
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
REPO = "yigenfeng0707-netizen/pmtec-dtc2026"
RUN = sys.argv[1] if len(sys.argv) > 1 else "34682637325"

r = subprocess.run(["gh", "api", f"repos/{REPO}/actions/runs/{RUN}/jobs"],
                   capture_output=True)
jobs = json.loads(r.stdout)["jobs"]
for j in jobs:
    if j["conclusion"] != "failure":
        continue
    print("FAILED JOB:", j["name"])
    r2 = subprocess.run(
        ["gh", "api", f"repos/{REPO}/actions/jobs/{j['id']}/logs"],
        capture_output=True)
    lines = r2.stdout.decode("utf-8", "replace").splitlines()
    errs = [l for l in lines
            if "##[error]" in l or "denied" in l.lower()
            or "error:" in l.lower()]
    for l in errs[-8:]:
        print(l[:200])
