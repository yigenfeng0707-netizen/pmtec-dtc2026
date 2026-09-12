#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P13: 演示视频 MP4 渲染 — 灰色地带演化链路 (1920x1080 @ 30fps, 约 46s)

与 visualization/demo_animation.py 同一套场景时序与数据（真实系统产物），
逐帧 PIL 渲染后直接管道输入 ffmpeg 编码 H.264。

产出：output/pmtec_demo_video.mp4

Run: D:/miniconda3/envs/pmtec-xpu/python.exe visualization/render_demo_video.py
"""

import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(PROJECT_ROOT, "data", "bases_v2.geojson")
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "output", "pmtec_demo_video.mp4")
FFMPEG = "ffmpeg"

W, H, FPS = 1920, 1080, 30
BG = (10, 14, 26)
PANEL = (22, 27, 34)
TXT = (201, 209, 217)
TITLE_BLUE = (88, 166, 255)
ESC_ORANGE = (245, 158, 78)
GREEN = (63, 185, 80)
RED = (248, 81, 73)
AMBER = (245, 196, 78)
GRAY = (139, 148, 158)
TIER_COLORS = {1: (255, 123, 114), 2: (255, 166, 87), 3: (210, 168, 255), 4: (126, 231, 135)}
ACCESS_COLORS = {"full": GREEN, "restricted": AMBER, "denied": RED}
STROKE = {b: (139, 148, 158) for b in ("full", "restricted", "denied")}
STROKE["denied"] = RED

SCENES = [
    {"dur": 4, "esc": 0.0, "avail": 67, "ph": "full", "tag": "S0 片头",
     "title": "PMTEC · 政治不确定性下的体系韧性",
     "sub": "政治事件 → 准入降级 → 战术适应 → 体系重平衡（全部数据来自系统真实运行）"},
    {"dur": 6, "esc": 0.0, "avail": 67, "ph": "full", "tag": "S1 基线态势",
     "title": "S1 基线态势（c0）",
     "sub": "67 基地全政治可用 · 冲突升级度 0 · 对手 6 策略待命（含多轴协同饱和 / 政治分化压制）"},
    {"dur": 7, "esc": 0.049, "avail": 67, "ph": "restricted", "tag": "S2 灰色地带",
     "title": "S2 灰色地带行动（c1-c2）",
     "sub": "对手挑衅盟友本土 → 准入概率下滑 → 菲律宾站点降级 Restricted（容量折损）"},
    {"dur": 7, "esc": 0.062, "avail": 58, "ph": "denied", "tag": "S3 主权打击",
     "title": "S3 主权打击（c3）",
     "sub": "冲突升级 → 9 个 EDCA 站点 Denied → 可用基地集合 67 → 58"},
    {"dur": 8, "esc": 0.062, "avail": 58, "ph": "denied", "tag": "S4 战术适应", "adapt": True,
     "title": "S4 ASDA-Adapt 战术适应",
     "sub": "219 维观测感知准入容量 → 部署优化器排除 Denied 站点 → 分散重构 + 政治敞口压制"},
    {"dur": 6, "esc": 0.039, "avail": 67, "ph": "full", "tag": "S5 恢复",
     "title": "S5 再保证与恢复（c4-c12）",
     "sub": "再保证外交 + 准入修复 → 第 12 周期可用基地完全恢复（结构性缓冲）"},
    {"dur": 8, "esc": 0.039, "avail": 67, "ph": "full", "tag": "S6 结论", "results": True,
     "title": "S6 重验证结论",
     "sub": "三场景对照 76.2% → 79.0% → 79.5% ｜ 六策略全量 79.1%（CI 78.0-80.2）｜ 适应优于压制"},
]


def font(size, bold=False):
    name = "msyhbd.ttc" if bold else "msyh.ttc"
    path = os.path.join(r"C:\Windows\Fonts", name)
    if not os.path.exists(path):
        path = os.path.join(r"C:\Windows\Fonts", "msyh.ttc")
    return ImageFont.truetype(path, size)


def load_bases():
    with open(DATA_PATH, encoding="utf-8") as f:
        gj = json.load(f)
    bases = []
    for ft in gj["features"]:
        p = ft["properties"]
        lon, lat = ft["geometry"]["coordinates"][:2]
        bases.append({
            "id": p.get("id", ""),
            "tier": p.get("tier", 2),
            "ally": p.get("access_uncertainty") is not None,
            "ph": (p.get("id", "") or "").startswith("PH-"),
            "x": (lon - 95) / 90 * (W - 120) + 60,
            "y": (58 - lat) / 70 * (H - 220) + 50,
        })
    return bases


def ease(t):
    return t * t * (3 - 2 * t)


def draw_frame(base_img, bases, scene, frac):
    """frac: 0-1 场景内进度（前 25% 做状态过渡混合）。"""
    img = base_img.copy()
    d = ImageDraw.Draw(img, "RGBA")

    # 场景过渡混合（进入场景前 25% 从上一场景状态渐变）
    trans = min(frac / 0.25, 1.0)
    k = ease(trans)

    # 标题与副标题
    d.text((56, 34), scene["title"], font=font(40, bold=True), fill=TITLE_BLUE)
    d.text((58, 96), scene["sub"], font=font(24), fill=TXT)

    # HUD：可用基地 / 升级度
    avail = scene["avail"]
    esc = scene["esc"]
    d.text((W - 420, 34), "政治可用基地", font=font(22), fill=GRAY)
    d.text((W - 420, 64), str(avail), font=font(52, bold=True),
           fill=GREEN if avail >= 60 else RED)
    d.text((W - 420, 140), "冲突升级度", font=font(22), fill=GRAY)
    d.text((W - 420, 170), f"{esc:.3f}", font=font(40, bold=True), fill=ESC_ORANGE)

    # 基地点
    ph_state = scene["ph"]
    for b in bases:
        access = "full"
        if b["ph"]:
            access = ph_state
        elif b["ally"] and scene["tag"] in ("S3 主权打击", "S4 战术适应"):
            access = "restricted"
        r = 10 if b["tier"] == 1 else 7
        fill = ACCESS_COLORS[access]
        stroke = STROKE[access]
        alpha = 140 if access == "denied" else 255
        d.ellipse([b["x"] - r, b["y"] - r, b["x"] + r, b["y"] + r],
                  fill=fill + (alpha,), outline=stroke + (255,),
                  width=3 if access == "denied" else 1)

    # S4 适应示意：从被拒 PH 区域向夏威夷/关岛枢纽的再部署弧线
    if scene.get("adapt"):
        hubs = [b for b in bases if b["id"] in ("HI-PHICKAM", "GU-ANDERSEN", "HI-SCHOFIELD")]
        denied = [b for b in bases if b["ph"]]
        for i, src in enumerate(denied[:5]):
            dst = hubs[i % len(hubs)]
            mid = ((src["x"] + dst["x"]) / 2, min(src["y"], dst["y"]) - 60 - i * 12)
            pts = []
            for t in range(0, 21):
                u = t / 20
                x = (1 - u) ** 2 * src["x"] + 2 * (1 - u) * u * mid[0] + u ** 2 * dst["x"]
                y = (1 - u) ** 2 * src["y"] + 2 * (1 - u) * u * mid[1] + u ** 2 * dst["y"]
                pts.append((x, y))
            # 流动虚线（随 frac 平移）
            offset = int(frac * 40) % 2
            for j in range(offset, len(pts) - 1, 2):
                d.line([pts[j], pts[j + 1]], fill=AMBER + (200,), width=3)
        d.text((56, H - 330),
               "⇄ ASDA-Adapt：分散再部署规避 Denied 站点 · Pareto 政治风险敞口显式压制",
               font=font(24), fill=AMBER)
        d.text((56, H - 288),
               "（DQN 219 维观测：36 盟友准入容量因子实时驱动决策）",
               font=font(20), fill=GRAY)

    # 升级度条
    bar_x, bar_y, bar_w, bar_h = 56, H - 210, 360, 16
    d.text((bar_x, bar_y - 28), "CONFLICT ESCALATION", font=font(16), fill=GRAY)
    d.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], 8, fill=PANEL)
    fw = int(bar_w * min(esc * 8, 1.0) * (0.6 + 0.4 * k) + 2)
    if esc > 0:
        d.rounded_rectangle([bar_x, bar_y, bar_x + fw, bar_y + bar_h], 8,
                            fill=ESC_ORANGE)

    # 图例
    lx = W - 460
    d.text((lx, H - 210), "准入状态:", font=font(16), fill=GRAY)
    for i, (name, c) in enumerate((("Full", GREEN), ("Restricted", AMBER), ("Denied", RED))):
        x = lx + 100 + i * 130
        d.ellipse([x, H - 208, x + 12, H - 196], fill=c)
        d.text((x + 18, H - 212), name, font=font(16), fill=GRAY)

    # 副标题（旁白字幕）
    sub = scene["sub"]
    d.rounded_rectangle([0, H - 150, W, H - 66], 0, fill=(10, 14, 26, 200))
    tw = d.textlength(sub, font=font(28))
    d.text(((W - tw) / 2, H - 136), sub, font=font(28), fill=(230, 237, 243))

    # 底部进度条 + 场景标签
    done = sum(s["dur"] for s in SCENES[:SCENES.index(scene)]) + scene["dur"] * frac
    total = sum(s["dur"] for s in SCENES)
    d.rectangle([0, H - 10, W * done / total, H], fill=TITLE_BLUE)
    d.text((24, H - 52), scene["tag"], font=font(20), fill=GRAY)
    return img


def draw_results_frame(base_img):
    img = base_img.copy()
    d = ImageDraw.Draw(img, "RGBA")
    d.text((56, 34), "S6 重验证结论", font=font(40, bold=True), fill=TITLE_BLUE)
    d.text((58, 96), "三场景对照 ｜ 六策略全量 150 episodes（Wilson 95% CI）",
           font=font(24), fill=TXT)
    cards = [
        ("76.2%", "P6 基线\n原 22 站点 · 182 维", GRAY),
        ("79.0%", "v2 权威数据\n模型不变 · +2.8pp", TITLE_BLUE),
        ("79.5%", "政治准入\n219 维 P12 模型", GREEN),
        ("79.1%", "六策略全量\nCI 78.0-80.2 · PASS", ESC_ORANGE),
    ]
    cw, ch, gap = 420, 320, 30
    x0 = (W - 4 * cw - 3 * gap) / 2
    y0 = 220
    for i, (num, label, color) in enumerate(cards):
        x = x0 + i * (cw + gap)
        d.rounded_rectangle([x, y0, x + cw, y0 + ch], 16, fill=PANEL,
                            outline=(48, 54, 61), width=2)
        d.text((x + cw / 2 - d.textlength(num, font=font(72, bold=True)) / 2,
               y0 + 60), num, font=font(72, bold=True), fill=color)
        for j, line in enumerate(label.split("\n")):
            lw = d.textlength(line, font=font(22))
            d.text((x + cw / 2 - lw / 2, y0 + 180 + j * 34), line,
                   font=font(22), fill=TXT)
    d.rounded_rectangle([x0, y0 + ch + 50, x0 + 4 * cw + 3 * gap, y0 + ch + 130], 14,
                        fill=(232, 243, 236, 40), outline=GREEN, width=2)
    msg = "六策略全量验证：总体拦截率 79.1%（95% CI 78.0 - 80.2）· 全部策略 ≥ 77.6% · 均过 70% 竞赛门槛"
    d.text(((W - d.textlength(msg, font=font(28, bold=True))) / 2, y0 + ch + 72),
           msg, font=font(28, bold=True), fill=GREEN)
    concl = "适应优于压制 —— 用真实世界数据让数字孪生更真，用政治不确定性让对抗更聪明"
    d.text(((W - d.textlength(concl, font=font(30, bold=True))) / 2, y0 + ch + 190),
           concl, font=font(30, bold=True), fill=TXT)
    return img


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    bases = load_bases()
    base_img = Image.new("RGB", (W, H), BG)

    total_frames = sum(s["dur"] for s in SCENES) * FPS
    print(f"[P13] 渲染演示视频: {total_frames} 帧 @ {FPS}fps -> {OUTPUT_PATH}")

    cmd = [
        FFMPEG, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", OUTPUT_PATH,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for si, scene in enumerate(SCENES):
        for f in range(scene["dur"] * FPS):
            frac = f / (scene["dur"] * FPS)
            if scene.get("results"):
                img = draw_results_frame(base_img)
            else:
                img = draw_frame(base_img, bases, scene, frac)
            proc.stdin.write(img.tobytes())
        print(f"    场景 {si}/6 完成 ({scene['tag']})")

    proc.stdin.close()
    proc.wait()
    size = os.path.getsize(OUTPUT_PATH)
    print(f"[P13] 演示视频完成: {OUTPUT_PATH} ({size / 1e6:.1f} MB, {total_frames / FPS:.0f}s)")


if __name__ == "__main__":
    main()
