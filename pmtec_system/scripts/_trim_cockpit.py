# -*- coding: utf-8 -*-
"""从 command_cockpit.py 移除旧 Brain 模板块 (已由 command_brain.py 取代)"""
import sys

sys.stdout.reconfigure(encoding="utf-8")
P = r"d:\APPs\数字孪生挑战赛\pmtec_system\visualization\command_cockpit.py"
src = open(P, encoding="utf-8").read()
marker = "# ======================================================================\n# 联合指挥大脑"
i = src.find(marker)
if i < 0:
    print("marker not found")
else:
    open(P, "w", encoding="utf-8").write(src[:i].rstrip() + "\n")
    print(f"trimmed {len(src) - i} chars at offset {i}")
