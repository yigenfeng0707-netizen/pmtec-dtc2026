# -*- coding: utf-8 -*-
"""C 盘安全清理 (分阶段, 全程日志, 只动缓存/临时/未用镜像)

Phase 1 无风险: 用户 Temp(>48h 旧文件) / npm 缓存 / 崩溃转储 / pip 缓存
Phase 2 Docker: prune 未使用镜像与构建缓存 (可随时重建) + 尝试压缩 vhdx 归还 C 盘
Phase 3 报告: 系统大文件清单 (pagefile/hiberfil 仅报告不动作)
"""
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8")
LOG = r"d:\APPs\数字孪生挑战赛\_cleanup.log"


def log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def free_bytes():
    import shutil
    return shutil.disk_usage("C:\\").free


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def rm_tree_contents(path, older_hours=None):
    removed = 0
    cutoff = time.time() - (older_hours * 3600 if older_hours else 0)
    for root, dirs, files in os.walk(path, onerror=lambda e: None):
        for f in files:
            fp = os.path.join(root, f)
            try:
                if older_hours and os.path.getmtime(fp) > cutoff:
                    continue
                os.remove(fp)
                removed += 1
            except OSError:
                pass
    return removed


U = os.path.expanduser("~")
free0 = free_bytes()
log(f"清理前 C 盘可用: {human(free0)}")

# ---- Phase 1: 无风险清理 ----
t = os.path.join(U, r"AppData\Local\Temp")
if os.path.isdir(t):
    n = rm_tree_contents(t, older_hours=48)
    log(f"Phase1 用户 Temp: 清理 {n} 个文件 (>48h)")

for name, cmd in [
    ("npm 缓存", ["npm", "cache", "clean", "--force"]),
    ("pip 缓存", [sys.executable, "-m", "pip", "cache", "purge"]),
]:
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    log(f"Phase1 {name}: rc={r.returncode}")

dumps = os.path.join(U, r"AppData\Local\CrashDumps")
if os.path.isdir(dumps):
    n = rm_tree_contents(dumps)
    log(f"Phase1 崩溃转储: 清理 {n} 个文件")

free1 = free_bytes()
log(f"Phase1 后 C 盘可用: {human(free1)} (本阶段回收 {human(free1 - free0)})")

# ---- Phase 2: Docker 清理 + vhdx 压缩 ----
r = subprocess.run(["docker", "system", "prune", "-af"],
                   capture_output=True, text=True,
                   encoding="utf-8", errors="replace", timeout=900)
log(f"Phase2 docker system prune -af: rc={r.returncode}")
r = subprocess.run(["docker", "builder", "prune", "-af"], capture_output=True,
                   text=True, encoding="utf-8", errors="replace", timeout=600)
log(f"Phase2 builder prune: rc={r.returncode}")

# 关闭 WSL 以解锁 vhdx, 尝试压缩
subprocess.run(["wsl", "--shutdown"], capture_output=True)
time.sleep(5)
vhdx = os.path.join(U, r"AppData\Local\Docker\wsl")
vhdx_files = []
for root, dirs, files in os.walk(vhdx, onerror=lambda e: None):
    for f in files:
        if f.endswith(".vhdx"):
            fp = os.path.join(root, f)
            vhdx_files.append((fp, os.path.getsize(fp)))
for fp, sz in vhdx_files:
    log(f"Phase2 vhdx: {fp} = {human(sz)}")

# diskpart 压缩 (需要管理员; 失败则记录)
if vhdx_files:
    script = os.path.join(U, "_compact.txt")
    out = os.path.join(U, "_compact_out.txt")
    with open(script, "w") as f:
        f.write(f"select vdisk file=\"{vhdx_files[0][0]}\"\n"
                "attach vdisk readonly\n"
                "compact vdisk\n"
                "detach vdisk\n"
                "exit\n")
    r = subprocess.run(["diskpart", "/s", script], capture_output=True,
                       text=True, encoding="utf-8", errors="replace",
                       timeout=1800)
    ok = "DiskPart successfully" in (r.stdout or "") or r.returncode == 0
    log(f"Phase2 diskpart 压缩: rc={r.returncode} (需管理员权限, 失败则跳过)")
    for fp, _ in vhdx_files:
        if os.path.exists(fp):
            log(f"Phase2 vhdx 压缩后: {human(os.path.getsize(fp))}")
    os.remove(script) if os.path.exists(script) else None

# Docker Desktop 重启 (恢复可用)
subprocess.Popen([os.path.join(r"C:\Program Files\Docker\Docker",
                               "Docker Desktop.exe")])
log("Phase2 Docker Desktop 已重启")

free2 = free_bytes()
log(f"最终 C 盘可用: {human(free2)} (共回收 {human(free2 - free0)})")

# ---- Phase 3: 系统大文件报告 (仅报告) ----
log("== C:\\ 根目录 >500MB 文件 (仅报告) ==")
for e in os.scandir("C:\\"):
    try:
        if e.is_file() and e.stat().st_size > 500 * 1024 * 1024:
            log(f"  {e.name} = {human(e.stat().st_size)}")
    except OSError:
        pass
log("== 完成 ==")
