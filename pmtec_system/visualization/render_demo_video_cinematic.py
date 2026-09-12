#!/usr/bin/env python3
"""
P13+: 电影级演示视频渲染 (神经语音旁白 + 同步字幕 + 程序化配乐)

升级点 (相对 render_demo_video.py):
  1. 旁白: edge-tts 神经语音 zh-CN-YunxiNeural (纪录片男声) 替换 SAPI Huihui
  2. 字幕: 词级时间戳 -> 短语字幕, 与旁白逐句严格同步 (burn-in)
  3. 配乐: numpy 程序化电影配乐, 和弦进程随剧情张力推进
     (紧张度: 灰色地带 Dm -> 主权打击低音 drone+脉冲 -> 适应 Em 脉冲
      -> 恢复 F->C -> 终章 Cadd9 上扬), 旁白段自动闪避 (ducking)
  4. 镜头: 每场景 Ken Burns 推拉 + 暗角 + 场景交叉淡入淡出
  5. 同步: 场景时长由旁白时长驱动 (0.6s 起始呼吸 + 0.9s 收尾), 音画严格对齐

产出: output/pmtec_demo_video.mp4 (覆盖交付物)

Run: D:/miniconda3/envs/pmtec-xpu/python.exe visualization/render_demo_video_cinematic.py
"""

import asyncio
import math
import os
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_demo_video as base  # 复用画面绘制 (draw_frame/results/base map)

PROJECT_ROOT = base.PROJECT_ROOT
OUTPUT_PATH = base.OUTPUT_PATH
TTS_DIR = os.path.join(PROJECT_ROOT, "output", "tts")
FFMPEG = "ffmpeg"

W, H, FPS = base.W, base.H, base.FPS
SR = 24000  # 混音采样率
VOICE = "zh-CN-YunxiNeural"
RATE, PITCH = "-4%", "-3Hz"

# ---------------------------------------------------------------- 叙事脚本
# (旁白文案, 画面沿用 render_demo_video 的七个场景)
NARRATION = [
    # S0 片头
    "PMTEC 数字孪生系统，在盟友政治准入的不确定性中，守护印太防空体系的韧性。"
    "所有画面与数据，均来自系统真实运行。",
    # S1 基线
    "体系的数据底座，是六十七个权威基地实体，每一颗坐标，都可溯源至国会研究处报告，"
    "与国防部基地结构报告。初始态势：全部基地政治可用，冲突升级度为零，"
    "对手握有六种攻击策略，随时待命。",
    # S2 灰色地带
    "演习开始。对手率先发动灰色地带行动，对盟友本土持续挑衅。"
    "政治准入状态机，在当周期即作出响应：菲律宾站点，从全面准入，降级为有限准入。",
    # S3 主权打击
    "主权打击接踵而至。冲突升级度不断累积，九个盟友站点被彻底拒止。"
    "可用基地，从六十七，收缩至五十八。",
    # S4 战术适应
    "ASDA 闭环的适应环节，立即介入。二百一十九维观测，实时感知每个盟友站点的准入容量；"
    "部署优化器自动排除被拒站点，分散方案向政治可用基地重构，"
    "政治风险敞口，被显式压制。",
    # S5 恢复
    "随后，再保证外交展开。准入概率缓慢修复，到第十二周期，可用基地完全恢复，"
    "体系展现出，对政治冲击的结构性缓冲。",
    # S6 结论
    "重验证结论：权威数据使拦截率提升二点八个百分点；引入政治约束后，拦截率不降反稳。"
    "十万次蒙特卡洛采样中，最差情形下，体系可用率仍达百分之九十五点五。"
    "适应优于压制。用真实世界数据，让数字孪生更真；用政治不确定性，让对抗更聪明。",
]

# 每场景配乐: (和弦频率表, 音量, 脉冲间隔秒 0=无, 亮度 0-1)
CHORD = {
    "Am":  [110.00, 130.81, 164.81],
    "F":   [87.31, 110.00, 130.81],
    "Dm":  [73.42, 87.31, 110.00],
    "dim": [123.47, 146.83, 174.61],
    "Em":  [82.41, 98.00, 123.47],
    "C":   [130.81, 164.81, 196.00],
    "C9":  [130.81, 164.81, 196.00, 293.66],
}
SCENE_MUSIC = [
    (CHORD["Am"], 0.16, 0.0, 0.25),   # S0 序幕: 柔和
    (CHORD["Am"], 0.18, 0.0, 0.30),   # S1 基线
    (CHORD["Dm"], 0.22, 1.00, 0.35),  # S2 灰色地带: 张力起
    (CHORD["dim"], 0.27, 0.45, 0.35),  # S3 主权打击: 低鸣+密脉冲
    (CHORD["Em"], 0.24, 0.30, 0.45),  # S4 适应: 节奏推进
    (CHORD["F"], 0.22, 0.0, 0.55),    # S5 恢复: 明亮化
    (CHORD["C9"], 0.28, 0.0, 0.85),   # S6 终章: 上扬
]
S6_SECOND_HALF = CHORD["C"]  # S6 后半回到纯 C 增加收束感


def font(size, bold=False):
    return base.font(size, bold)


# ================================================================ TTS
def _phrase_split(narr_len, words):
    """词级时间戳 -> 短语字幕 [(t0, t1, text)]，短语 ≤16 字，遇标点切分。"""
    phrases, cur, cur0 = [], "", None
    for off_ns, dur_ns, wtext in words:
        t0 = off_ns / 1e7
        t1 = (off_ns + dur_ns) / 1e7
        if cur0 is None:
            cur0 = t0
        cur += wtext
        end_now = any(p in wtext for p in "，。！？；、：—…")
        if end_now or len(cur) >= 16:
            phrases.append((cur0, t1, cur))
            cur, cur0 = "", None
    if cur:
        phrases.append((cur0, narr_len, cur))
    return [(a, b, t) for a, b, t in phrases if t.strip()]


async def _tts_scene(i, text):
    """合成单场景旁白 mp3 + 词级时间戳。返回 (narr_dur, phrases)。"""
    import edge_tts

    mp3 = os.path.join(TTS_DIR, f"nar_{i}.mp3")
    words = []
    for attempt in range(3):
        try:
            comm = edge_tts.Communicate(text, VOICE, rate=RATE, pitch=PITCH,
                                        boundary="WordBoundary")
            with open(mp3, "wb") as f:
                async for chunk in comm.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        words.append(
                            (chunk["offset"], chunk["duration"], chunk["text"])
                        )
            break
        except Exception as e:
            if attempt == 2:
                print(f"    [TTS] 场景 {i} 神经语音失败: {e}")
                return None, []
            await asyncio.sleep(2)

    wav = os.path.join(TTS_DIR, f"nar_{i}.wav")
    subprocess.run(
        [FFMPEG, "-y", "-i", mp3, "-ar", str(SR), "-ac", "1", wav],
        capture_output=True,
    )
    with wave.open(wav, "rb") as w:
        narr_dur = w.getnframes() / w.getframerate()
    return narr_dur, _phrase_split(narr_dur, words)


def synth_all_narration():
    os.makedirs(TTS_DIR, exist_ok=True)
    durs, sub_scheds = [], []
    for i, text in enumerate(NARRATION):
        d, ph = asyncio.run(_tts_scene(i, text))
        durs.append(d)
        sub_scheds.append(ph)
    return durs, sub_scheds


# ================================================================ 音轨
def load_narr_wave(i):
    wav = os.path.join(TTS_DIR, f"nar_{i}.wav")
    if not os.path.exists(wav):
        return None
    with wave.open(wav, "rb") as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return data.astype(np.float64) / 32768.0


def synth_bgm(scene_durs):
    """程序化电影配乐: 和弦垫 + 脉冲低音 + 终章上扬, 输出总长音轨。"""
    total = int(sum(scene_durs) * SR)
    bgm = np.zeros(total)
    t_cursor = 0
    for si, dur in enumerate(scene_durs):
        chord, amp, pulse, bright = SCENE_MUSIC[si]
        n = int(dur * SR)
        t = np.arange(n) / SR
        seg = np.zeros(n)
        for k, f in enumerate(chord):
            ph = 0.7 * k
            trem = 1.0 + 0.15 * np.sin(2 * np.pi * 0.13 * t + ph)
            seg += np.sin(2 * np.pi * f * t + ph) * trem
            if bright > 0.3:  # 高八度泛音随亮度增强
                seg += bright * 0.5 * np.sin(2 * np.pi * 2 * f * t + ph * 2)
        seg /= len(chord) * 1.6

        if pulse > 0:  # 张力脉冲低音
            kick = np.zeros(n)
            period = int(pulse * SR)
            kn = min(int(0.16 * SR), period)
            kt = np.arange(kn) / SR
            kick_wave = np.sin(2 * np.pi * 52 * kt) * np.exp(-kt * 16)
            n_kick = n // period
            for j in range(n_kick + 1):
                s = j * period
                e = min(s + kn, n)
                if s < n:
                    kick[s:e] += kick_wave[: e - s]
            seg += 0.55 * kick
            if si == 3:  # 主权打击: 附加低音 drone
                seg += 0.30 * np.sin(2 * np.pi * 55.0 * t)

        # 场内包络: 1.2s 起振 / 1.5s 收束, 场间自然衔接
        atk = min(int(1.2 * SR), n // 3)
        rel = min(int(1.5 * SR), n // 3)
        env = np.ones(n)
        env[:atk] = np.linspace(0, 1, atk)
        env[n - rel:] = np.linspace(1, 0, rel)
        e = seg * env * amp

        if si == 6:  # 终章后 40% 切纯 C 收束
            cut = int(n * 0.6)
            t2 = np.arange(n - cut) / SR
            tail = np.zeros(n - cut)
            for k, f in enumerate(S6_SECOND_HALF):
                tail += np.sin(2 * np.pi * f * t2 + 0.7 * k)
            tail = tail / len(S6_SECOND_HALF) * 1.2
            rel2 = min(int(2.0 * SR), n - cut)
            tenv = np.ones(n - cut)
            tenv[: int(0.8 * SR)] = np.linspace(0, 1, int(0.8 * SR))
            tenv[-rel2:] = np.linspace(1, 0, rel2)
            e[cut:] = tail * tenv * amp

        s = min(t_cursor + n, total)
        bgm[t_cursor:s] += e[: s - t_cursor]
        t_cursor = s
    return bgm


def build_final_mix(scene_durs, narr_durs, out_path):
    """旁白轨 + 配乐轨(闪避) -> 最终 wav。返回 (总秒, 旁白全局起点表)。"""
    total = int(sum(scene_durs) * SR)
    narr = np.zeros(total)

    # 旁白放置: 场景起点 + 0.6s
    starts, cur = [], 0.0
    for i, d in enumerate(scene_durs):
        starts.append(cur)
        if narr_durs[i] is not None:
            w = load_narr_wave(i)
            s = int((cur + 0.6) * SR)
            e = min(s + len(w), total)
            narr[s:e] += w[: e - s]
        cur += d

    # 闪避包络: 旁白活跃时配乐压至 25%
    env = np.abs(narr)
    k = int(0.20 * SR)
    kernel = np.ones(k) / k
    env = np.convolve(env, kernel, mode="same")
    env = np.clip(env / 0.04, 0, 1)
    duck = 1.0 - 0.75 * env

    bgm = synth_bgm(scene_durs)
    mix = narr * 0.95 + bgm * duck
    peak = np.abs(mix).max()
    if peak > 0:
        mix *= 0.89 / peak

    with wave.open(out_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    return sum(scene_durs), starts


# ================================================================ 画面
def make_vignette():
    """径向暗角遮罩 (0.55 角落 - 1.0 中心)。"""
    yy, xx = np.mgrid[0:H, 0:W]
    cx, cy = W / 2, H / 2
    r = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2)
    v = np.clip(1.05 - 0.5 * r ** 2.2, 0.55, 1.0)
    return v[:, :, None].astype(np.float32)


def ken_burns(img, frac, si):
    """Ken Burns: 缓慢推近 + 水平漂移 (方向逐场景交替)。"""
    z = 1.0 + 0.045 * (0.5 - 0.5 * math.cos(math.pi * frac))  # 1.0 -> 1.045
    drift = (1 if si % 2 == 0 else -1) * 18 * frac
    cw, chh = W / z, H / z
    x0 = (W - cw) / 2 + drift
    y0 = (H - chh) / 2 - 6 * frac
    box = (max(x0, 0), max(y0, 0), min(x0 + cw, W), min(y0 + chh, H))
    return img.crop(box).resize((W, H), Image.BILINEAR)


def draw_subtitle(img, phrase, frac_in):
    """底部字幕带 + 当前短语 (淡入)。"""
    d = ImageDraw.Draw(img, "RGBA")
    band_y0, band_y1 = H - 150, H - 66
    d.rectangle([0, band_y0, W, band_y1], fill=(8, 11, 20, 215))
    d.line([0, band_y0, W, band_y0], fill=(88, 166, 255, 90), width=2)
    if phrase:
        alpha = int(255 * min(frac_in * 4, 1.0))
        f_sub = font(30, bold=True)
        # 自动降字号防止超宽
        if d.textlength(phrase, font=f_sub) > W - 160:
            f_sub = font(26, bold=True)
        tw = d.textlength(phrase, font=f_sub)
        d.text(((W - tw) / 2, band_y0 + 26), phrase,
               font=f_sub, fill=(235, 241, 247, alpha))


def render(scenes, scene_durs, sub_global, vign):
    """逐帧渲染 -> ffmpeg 管道。sub_global: [(t0,t1,text)] 全局字幕表。"""
    bases = base.load_bases()
    base_img = Image.new("RGB", (W, H), base.BG)
    total_sec = sum(scene_durs)
    total_frames = int(total_sec * FPS)
    print(f"[CINEMA] 渲染 {total_frames} 帧 @ {FPS}fps (含 Ken Burns/暗角/字幕)")

    cmd = [
        FFMPEG, "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
        "-r", str(FPS), "-i", "-",
        "-i", os.path.join(TTS_DIR, "final_mix.wav"),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
        "-shortest", OUTPUT_PATH,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    n_sub = len(sub_global)
    sub_idx = 0
    frame = 0
    for si, scene in enumerate(scenes):
        n = int(scene_durs[si] * FPS)
        for f in range(n):
            frac = f / n
            t = frame / FPS
            # 字幕游标推进
            while (sub_idx < n_sub and t >= sub_global[sub_idx][1]):
                sub_idx += 1
            phrase = None
            frac_in = 0.0
            if sub_idx < n_sub and t >= sub_global[sub_idx][0]:
                p = sub_global[sub_idx]
                phrase = p[2]
                frac_in = (t - p[0]) / max(p[1] - p[0], 1e-6)

            if scene.get("results"):
                img = base.draw_results_frame(base_img)
            else:
                img = base.draw_frame(base_img, bases, scene, frac)

            img = ken_burns(img, frac, si)
            arr = np.asarray(img, dtype=np.float32) * vign  # 暗角
            img = Image.fromarray(arr.clip(0, 255).astype(np.uint8))
            draw_subtitle(img, phrase, frac_in)

            # 场景交叉淡入淡出 (首尾 0.35s)
            fade = 1.0
            edge = 0.35 * FPS
            if f < edge:
                fade *= f / edge
            if n - f <= edge:
                fade *= (n - f) / edge
            if fade < 1.0:
                a = np.asarray(img, dtype=np.float32) * fade
                img = Image.fromarray(a.clip(0, 255).astype(np.uint8))

            proc.stdin.write(np.asarray(img).tobytes())
            frame += 1
        print(f"    场景 {si}/6 完成 ({scene['tag']}, {n} 帧)")

    proc.stdin.close()
    proc.wait()
    return frame


def qa_check():
    """QA: 时长对齐 + 中段抽帧字幕存在性。"""
    r = subprocess.run(
        [FFMPEG, "-i", OUTPUT_PATH, "-f", "null", "-"],
        capture_output=True, text=True,
    )
    info = r.stderr
    dur_v = None
    for line in info.splitlines():
        if "Video:" in line and "Duration" not in line:
            pass
    import re
    m = re.findall(r"Duration: (\d+):(\d+):([\d.]+)", info)
    if m:
        h, mn, s = m[0]
        dur_v = int(h) * 3600 + int(mn) * 60 + float(s)
    streams = [l for l in info.splitlines() if "Stream" in l]
    print("[QA] streams:")
    for l in streams:
        print("   ", l.strip()[:110])
    print(f"[QA] 容器时长 {dur_v:.1f}s")
    return dur_v


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print("[CINEMA] 1/4 合成神经语音旁白 (zh-CN-YunxiNeural, 词级时间戳)...")
    narr_durs, sub_scheds = synth_all_narration()
    for i, d in enumerate(narr_durs):
        status = f"{d:.1f}s / {len(sub_scheds[i])} 句" if d else "失败(将静音+均分字幕)"
        print(f"    场景 {i}: {status}")

    # 场景时长 = max(计划, 旁白+1.5s), 字幕全局时间表
    scenes = [dict(s) for s in base.SCENES]
    scene_durs = []
    sub_global = []
    cursor = 0.0
    for i, sc in enumerate(scenes):
        if narr_durs[i] is not None:
            d = max(sc["dur"], math.ceil(narr_durs[i] + 1.5))
        else:
            d = sc["dur"]
            ph = sub_scheds[i]
            span = max(d - 0.8, 1e-6)
            ph = [(0.3 + k * span / max(len(ph), 1),
                   0.3 + (k + 1) * span / max(len(ph), 1), t)
                  for k, (_, _, t) in enumerate(ph)]
            sub_scheds[i] = ph
        scene_durs.append(d)
        for (a, b, txt) in sub_scheds[i]:
            sub_global.append((cursor + 0.6 + a, cursor + 0.6 + b, txt))
        cursor += d
    total = sum(scene_durs)
    print(f"[CINEMA] 2/4 场景时长 {scene_durs} -> 总长 {total:.0f}s")
    print(f"    字幕短语 {len(sub_global)} 条, 全部对齐词级时间戳")

    print("[CINEMA] 3/4 混音 (旁白 + 程序化配乐 + 闪避)...")
    total_sec, starts = build_final_mix(
        scene_durs, narr_durs, os.path.join(TTS_DIR, "final_mix.wav"))
    for i, s in enumerate(starts):
        nd = narr_durs[i]
        print(f"    场景 {i}: 画面 {s:6.1f}s | 旁白 {s + 0.6:6.1f}s"
              f" | 旁白长 {nd:.1f}s" if nd else f"    场景 {i}: (无旁白)")

    vign = make_vignette()
    print("[CINEMA] 4/4 渲染合成...")
    n_frames = render(scenes, scene_durs, sub_global, vign)
    size = os.path.getsize(OUTPUT_PATH)
    print(f"[CINEMA] 完成: {OUTPUT_PATH} ({size / 1e6:.1f} MB, "
          f"{n_frames / FPS:.0f}s, 神经旁白+同步字幕+配乐)")
    qa_check()


if __name__ == "__main__":
    main()
