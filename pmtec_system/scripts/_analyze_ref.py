# -*- coding: utf-8 -*-
"""分析参考仪表盘 (UTF-16 重读)"""
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
raw = open(r"d:\APPs\数字孪生挑战赛\_ref_monitor.html", "rb").read()
try:
    src = raw.decode("utf-16")
except Exception:
    src = raw.decode("utf-8", "replace")
print("decoded len:", len(src))

ids = list(dict.fromkeys(re.findall(r'id="([^"]+)"', src)))
print("== IDs ==")
print("  ", ", ".join(ids[:42]))

print("== 数据源 ==")
urls = sorted(set(re.findall(r'https?://[^\s"\'<>\\)\]]+', src)))
for m in urls[:22]:
    print("  ", m[:112])

print("== 函数 ==")
fns = []
for f in re.findall(r"function\s+(\w+)\s*\(", src):
    if f not in fns:
        fns.append(f)
print("  ", ", ".join(fns[:42]))

print("== 特效密度 ==")
for kw in ["radar", "sweep", "glow", "scan", "particle", "backdrop-filter",
           "conic", "keyframes", "gradient", "letter-spacing", "blur"]:
    print(f"   {kw}: {len(re.findall(kw, src, re.I))}")

print("== AI / 威胁特征 ==")
for kw in ["prediction", "confidence", "threat", "classification", "sigint",
           "satellite", "aircraft", "ship", "opensky", "adsb", "layer"]:
    print(f"   {kw}: {len(re.findall(kw, src, re.I))}")

print("== 地图 ==")
for m in re.findall(r"L\.map\([^)]*\)|setView\(\[[^\]]*\][^)]*\)|tileLayer\(['\"][^'\"]{0,80}", src)[:8]:
    print("  ", m[:130])
