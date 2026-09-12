# -*- coding: utf-8 -*-
"""C 盘第二轮清理: 开发缓存 + 应用 Cache 子目录精确清理 (全程日志)"""
import os
import shutil
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
LOG = r"d:\APPs\数字孪生挑战赛\_cleanup2.log"
U = os.path.expanduser("~")
L = os.path.join(U, "AppData", "Local")
R = os.path.join(U, "AppData", "Roaming")


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def free_gb():
    return shutil.disk_usage("C:\\").free / 1024**3


def size_gb(path):
    total = 0
    for root, dirs, files in os.walk(path, onerror=lambda e: None):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total / 1024**3


def rm_contents(path):
    n = 0
    for root, dirs, files in os.walk(path, onerror=lambda e: None):
        for f in files:
            try:
                os.remove(os.path.join(root, f))
                n += 1
            except OSError:
                pass
    return n


def rm_dir(path):
    try:
        shutil.rmtree(path, ignore_errors=True)
        return True
    except Exception:
        return False


CACHE_DIR_NAMES = {
    "Cache", "Code Cache", "GPUCache", "CachedData", "CachedExtensionVSIXs",
    "FileCache", "Crashpad", "logs", "Logs", "DawnCache", "ShaderCache",
    "GrShaderCache", "blob_storage", "Service Worker\CacheStorage",
}

free0 = free_gb()
log(f"第二轮清理开始, C 可用 {free0:.2f} GB")

# ---- A1: 开发工具缓存 (整体目录安全删除) ----
for name, path in [
    ("npm-cache", os.path.join(L, "npm-cache")),
    ("pnpm-cache", os.path.join(L, "pnpm-cache")),
    ("chromium-browser-snapshots", os.path.join(U, ".chromium-browser-snapshots")),
    ("qianfan-desktop-app-updater", os.path.join(L, "qianfan-desktop-app-updater")),
    ("qoder-work-updater", os.path.join(L, "qoder-work-updater")),
    ("@zcodedesktop-updater", os.path.join(L, "@zcodedesktop-updater")),
    ("qwen-work-cn-updater", os.path.join(L, "qwen-work-cn-updater")),
    ("@opencode-aidesktop-updater", os.path.join(L, "@opencode-aidesktop-updater")),
]:
    if os.path.isdir(path):
        before = size_gb(path)
        ok = rm_dir(path)
        log(f"A1 {name}: {before:.2f} GB -> {'已删除' if ok else '部分锁定, 已尽力'}")

# uv 缓存 (官方命令)
if os.path.isdir(os.path.join(L, "uv")):
    before = size_gb(os.path.join(L, "uv"))
    r = subprocess.run(["uv", "cache", "clean"], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    after = size_gb(os.path.join(L, "uv"))
    log(f"A1 uv 缓存: {before:.2f} GB -> {after:.2f} GB (rc={r.returncode})")

free1 = free_gb()
log(f"A 类完成后 C 可用 {free1:.2f} GB (+{free1 - free0:.2f} GB)")

# ---- B: 大型应用的 Cache 类子目录 (只动 cache 名单, 不碰用户数据) ----
apps = [
    os.path.join(R, "TRAE SOLO CN"),
    os.path.join(R, "Cursor"),
    os.path.join(R, "LarkShell"),
    os.path.join(R, "kingsoft"),
    os.path.join(R, "QoderCN"),
    os.path.join(R, "office-raccoon"),
    os.path.join(R, "Trae CN"),
    os.path.join(R, "Qoder"),
    os.path.join(R, "bilibili"),
    os.path.join(R, "ZCode"),
    os.path.join(R, "WorkBuddy"),
    os.path.join(R, "ai.opencode.desktop"),
    os.path.join(U, ".cursor"),
    os.path.join(L, "Intel"),
]
CACHE_NAMES = {"cache", "code cache", "gpucache", "cacheddata", "filecache",
               "crashpad", "logs", "dawncache", "shadercache",
               "grshadercache", "cachestorage", "cachedfiles", "temp"}
for app in apps:
    if not os.path.isdir(app):
        continue
    before = size_gb(app)
    cleaned = 0.0
    for root, dirs, files in os.walk(app, onerror=lambda e: None):
        for d in list(dirs):
            if d.lower() in CACHE_NAMES:
                target = os.path.join(root, d)
                sz = size_gb(target)
                if sz < 0.05:
                    dirs.remove(d)
                    continue
                rm_contents(target)
                cleaned += sz
                dirs.remove(d)
    after = size_gb(app)
    if cleaned > 0.05:
        log(f"B {os.path.basename(app)}: {before:.2f} GB -> {after:.2f} GB"
            f" (清了 {cleaned:.2f} GB cache)")

# Intel LocalLow 着色器缓存
intel = os.path.join(U, "AppData", "LocalLow", "Intel")
if os.path.isdir(intel):
    b = size_gb(intel)
    rm_contents(intel)
    log(f"B Intel 着色器缓存: {b:.2f} GB -> {size_gb(intel):.2f} GB")

free2 = free_gb()
log(f"B 类完成后 C 可用 {free2:.2f} GB (+{free2 - free1:.2f} GB)")
log(f"== 第二轮清理结束, 合计回收 {free2 - free0:.2f} GB, C 可用 {free2:.2f} GB ==")
