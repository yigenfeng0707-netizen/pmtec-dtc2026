"""P13: CI/CD 运行记录渲染 — GitHub Actions 真实运行数据 -> PNG 截图 + HTML 报告

数据源: GitHub REST API (repos/*/actions/runs/{id} + /jobs)
产出: output/PMTEC_CICD_Run_Record.png / .html
"""
import json
import os
import subprocess
import sys
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding="utf-8")
REPO = "yigenfeng0707-netizen/pmtec-dtc2026"
RUN_ID = sys.argv[1] if len(sys.argv) > 1 else "34680777225"
ROOT = r"d:\APPs\数字孪生挑战赛"
OUT_DIR = os.path.join(ROOT, "pmtec_system", "output")
PNG = os.path.join(OUT_DIR, "PMTEC_CICD_Run_Record.png")
HTML = os.path.join(OUT_DIR, "PMTEC_CICD_Run_Record.html")


def gh(endpoint):
    r = subprocess.run(["gh", "api", f"repos/{REPO}/{endpoint}"],
                       capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[:300])
    return json.loads(r.stdout.decode("utf-8", "replace"))


def iso(t):
    return datetime.fromisoformat(t.replace("Z", "+00:00"))


def dur_s(a, b):
    return (iso(b) - iso(a)).total_seconds()


def fmt_dur(s):
    if s >= 60:
        return f"{int(s // 60)}m {int(s % 60)}s"
    return f"{s:.0f}s"


run = gh(f"actions/runs/{RUN_ID}")
jobs = gh(f"actions/runs/{RUN_ID}/jobs")["jobs"]
head_msg = run.get("display_title", "")
sha = run["head_sha"][:8]
run_url = run["html_url"]
status = run["status"]
concl = run.get("conclusion")
run_no = run["run_number"]

# ---------------- PNG 渲染 (GitHub Actions 深色风格) ----------------
W = 1560
BG, PANEL, BORDER = (13, 17, 23), (22, 27, 34), (48, 54, 61)
TXT, DIM = (230, 237, 243), (139, 148, 158)
GREEN, RED, BLUE, YELLOW = (63, 185, 80), (248, 81, 73), (88, 166, 255), (212, 167, 44)
def F(s, b=False):
    return ImageFont.truetype(
    os.path.join(r"C:\Windows\Fonts", "msyhbd.ttc" if b else "msyh.ttc"), s)

rows = []
for j in jobs:
    d = dur_s(j["started_at"], j["completed_at"] or datetime.utcnow()
              .strftime("%Y-%m-%dT%H:%M:%SZ"))
    rows.append((j["name"], j["status"], j.get("conclusion"), d,
                 j.get("steps") or []))

row_h = 64
H = 210 + sum(row_h + (26 * min(len(r[4]), 12) + 14) for r in rows) + 130
img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

# 顶栏
d.rectangle([0, 0, W, 56], fill=PANEL)
d.text((28, 14), "yigenfeng0707-netizen / pmtec-dtc2026", font=F(18), fill=TXT)
d.text((28, 16), "·", font=F(18), fill=DIM)
tw = d.textlength("yigenfeng0707-netizen / pmtec-dtc2026", font=F(18))
d.text((tw + 44, 14), "Actions", font=F(18, True), fill=TXT)
d.text((W - 150, 16), f"#{run_no}", font=F(18, True), fill=BLUE)

# 运行头
y = 76
d.text((28, y), "PMTEC CI/CD", font=F(26, True), fill=TXT)
y += 42
badge = "✓ Success" if concl == "success" else (
    "✕ Failure" if concl == "failure" else "• In progress")
bcol = GREEN if concl == "success" else (RED if concl == "failure" else YELLOW)
d.rounded_rectangle([28, y, 40 + d.textlength(badge, font=F(16, True)) + 20,
                     y + 30], 15, outline=bcol, width=2)
d.text((46, y + 4), badge, font=F(16, True), fill=bcol)
d.text((100 + d.textlength(badge, font=F(16, True)), y + 4),
       f"Trigger: {run['event']}  ·  Branch: {run['head_branch']}  ·  Commit: {sha}",
       font=F(15), fill=DIM)
y += 44
d.text((28, y), head_msg, font=F(17), fill=TXT)
y += 30
d.text((28, y), f"Run: {run_url}", font=F(13), fill=BLUE)
y += 26
d.line([28, y, W - 28, y], fill=BORDER, width=1)
y += 18

ICON = {"success": ("✓", GREEN), "failure": ("✕", RED),
        "in_progress": ("•", YELLOW), "skipped": ("→", DIM), None: ("•", YELLOW)}

for name, st, cc, dur, steps in rows:
    icon, col = ICON.get(cc, ("•", YELLOW))
    d.rounded_rectangle([28, y, W - 28, y + row_h - 10], 10, fill=PANEL,
                        outline=BORDER, width=1)
    d.text((46, y + 12), icon, font=F(22, True), fill=col)
    d.text((80, y + 14), name, font=F(17, True), fill=TXT)
    state = cc or st
    scol = col if cc else YELLOW
    d.text((W - 220, y + 16), f"{state}", font=F(15, True), fill=scol)
    d.text((W - 120, y + 16), fmt_dur(dur), font=F(15), fill=DIM)
    y += row_h
    # 步骤明细 (最多 12 步)
    if steps:
        sx = 92
        shown = 0
        line = ""
        for sp in steps:
            si, sc = ICON.get(sp.get("conclusion"), ("·", DIM))
            nm = sp["name"]
            if len(line) + len(nm) > 108:
                d.text((sx, y), line, font=F(13), fill=DIM)
                y += 22
                line = ""
            line += f"{si} {nm}   "
        if line:
            d.text((sx, y), line, font=F(13), fill=DIM)
            y += 22
    y += 12

# 底部
y = H - 96
d.line([28, y - 12, W - 28, y - 12], fill=BORDER, width=1)
d.text((28, y),
       f"数据来源: GitHub REST API (repos/{REPO}/actions/runs/{RUN_ID}) · "
       f"Run #{run_no} · commit {sha}",
       font=F(14), fill=DIM)
d.text((28, y + 24),
       f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · "
       f"DTC 2026 赛道二 · PMTEC Digital Battlefield",
       font=F(14), fill=DIM)
img.save(PNG)
print(f"PNG: {PNG}")

# ---------------- HTML ----------------
def job_html(j):
    steps = "".join(
        f'<span style="color:{"#3fb950" if s.get("conclusion")=="success" else "#d4a72c"}">'
        f'{"✓" if s.get("conclusion")=="success" else "•"} {s["name"]}</span>'
        for s in (j.get("steps") or [])[:14])
    cc = j.get("conclusion") or j["status"]
    color = "#3fb950" if cc == "success" else ("#f85149" if cc == "failure" else "#d4a72c")
    dur = fmt_dur(dur_s(j["started_at"], j["completed_at"]
                        or datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")))
    return (f'<div style="background:#161b22;border:1px solid #30363d;'
            f'border-radius:8px;padding:14px 18px;margin:10px 0">'
            f'<b style="color:#e6edf3">{j["name"]}</b>'
            f'<span style="color:{color};margin-left:16px;font-weight:700">{cc}</span>'
            f'<span style="color:#8b949e;margin-left:12px">{dur}</span>'
            f'<div style="margin-top:8px;font-size:12px;line-height:1.9">{steps}</div></div>')


jobs_html = "".join(job_html(j) for j in jobs)
with open(HTML, "w", encoding="utf-8") as f:
    f.write(f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>PMTEC CI/CD Run Record</title></head>
<body style="background:#0d1117;font-family:'Segoe UI','Microsoft YaHei',sans-serif;
color:#c9d1d9;max-width:1200px;margin:0 auto;padding:24px">
<h1 style="color:#e6edf3">PMTEC CI/CD — 运行记录 <span style="color:#58a6ff">#{run_no}</span></h1>
<p>状态: <b style="color:{'#3fb950' if concl=='success' else '#d4a72c'}">{concl or status}</b>
 · Trigger: {run['event']} · Branch: {run['head_branch']} · Commit: <code>{sha}</code></p>
<p style="color:#8b949e">{head_msg}</p>
<p>Run URL: <a style="color:#58a6ff" href="{run_url}">{run_url}</a></p>
{jobs_html}
<p style="color:#8b949e;font-size:12px">数据来源: GitHub REST API · 生成时间
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · DTC 2026 赛道二</p>
</body></html>""")
print(f"HTML: {HTML}")
