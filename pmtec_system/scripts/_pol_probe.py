# -*- coding: utf-8 -*-
"""探测 /political/access 真实返回结构 (落盘)"""
import json
import urllib.request

try:
    d = json.load(urllib.request.urlopen("http://localhost:8080/api/v1/political/access", timeout=8))
    out = json.dumps(d, ensure_ascii=False, indent=1)[:3000]
except Exception as e:
    out = f"ERROR: {e}"
open(r"d:\APPs\数字孪生挑战赛\_pol_probe.txt", "w", encoding="utf-8").write(out)
