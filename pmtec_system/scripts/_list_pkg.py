# -*- coding: utf-8 -*-
"""离线提交包内容清单"""
import os
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"d:\APPs\数字孪生挑战赛"
pkg = None
for f in os.listdir(ROOT):
    if "离线提交包" in f and f.endswith(".zip"):
        pkg = os.path.join(ROOT, f)
        break
if not pkg:
    print("未找到离线提交包")
    sys.exit(0)
print("包:", os.path.basename(pkg), f"{os.path.getsize(pkg)/1e6:.1f} MB")
print("-" * 70)
with zipfile.ZipFile(pkg) as z:
    names = z.namelist()
    print(f"共 {len(names)} 项")
    # 归类展示
    for n in sorted(names):
        info = z.getinfo(n)
        if info.is_dir():
            continue
        print(f"  {info.file_size/1e3:9.0f} KB  {n}")
