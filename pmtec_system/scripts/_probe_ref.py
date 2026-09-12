# -*- coding: utf-8 -*-
"""参考视频探测: 元信息 + 关键帧提取"""
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
VID = r"D:\APPs\数字孪生挑战赛\工业互联网研究院的视频.mp4"
OUT = r"d:\APPs\数字孪生挑战赛\pmtec_system\output\_ref_frames"
os.makedirs(OUT, exist_ok=True)

r = subprocess.run(["ffmpeg", "-i", VID], capture_output=True)
info = r.stderr.decode("utf-8", "replace")
for line in info.splitlines():
    if any(k in line for k in ("Duration", "Stream", "bitrate")):
        print(line.strip()[:140])

import re
m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info)
dur = 10.0
if m:
    h, mn, s = m.groups()
    dur = int(h) * 3600 + int(mn) * 60 + float(s)
print(f"=> 提取 8 帧 (每 {dur/8:.1f}s 一帧)")
for i in range(8):
    t = dur * (i + 0.5) / 8
    fp = os.path.join(OUT, f"ref_{i}.jpg")
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(t), "-i", VID, "-frames:v", "1",
         "-q:v", "3", fp], capture_output=True)
    if os.path.exists(fp):
        print(f"frame {i}: t={t:.1f}s {os.path.getsize(fp)//1024}KB")
