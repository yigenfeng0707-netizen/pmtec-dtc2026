# -*- coding: utf-8 -*-
"""演示视频 V2 后期合成：片头卡 + edge-tts 旁白 + 同源 SRT 烧字幕.

输入  pmtec_system/output/pmtec_demo_raw_take.mp4 (167.9s 实拍一镜, 取 0-166s)
输出  pmtec_system/output/pmtec_demo_video_v2.mp4 (1080p30, 旁白+字幕音字同步)

同步保证: 旁白句子先生成、ffprobe 实测时长、按幕窗口排期, SRT 与音轨共用同一排期表.
"""
import asyncio
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

import edge_tts

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "pmtec_system", "output")
WORK = os.path.join(OUT, "v2_work")
RAW = os.path.join(OUT, "pmtec_demo_raw_take.mp4")
FINAL = os.path.join(OUT, "pmtec_demo_video_v2.mp4")
MAIN_END = 166.0
CARD_S = 3.0
VOICE = "zh-CN-YunxiNeural"
RATE = "+6%"

# (main 时间轴窗口起点, 终点, 句子列表) — 与录制时间轴一致
SCENES = [
    (2, 38, [
        "这是 PMTEC 政治韧性数字孪生。",
        "67 个印太盟友基地，在系统里只有三种状态：开放、受限、拒止。",
        "对手不必开一枪，只要让盟友说不。",
    ]),
    (42, 88, [
        "系统正在实跑。",
        "政治事件驱动准入状态机迁移，每一次降级都实时进入态势。",
        "参谋官由大模型在线生成分析，数据全部来自引擎真实产物。",
    ]),
    (92, 118, [
        "孪生仪表盘持续比对保真度。",
        "实战偏差反哺决策模型，形成数据闭环。",
    ]),
    (122, 148, [
        "回放推演全程：第 3 周期起 9 站拒止，可用基地从 67 收缩到 58。",
        "体系没有崩溃，拦截率稳定在 79% 以上。",
    ]),
    (152, 165, [
        "适应优于压制。",
        "用真实世界数据让孪生更真，用政治不确定性让对抗更聪明。",
    ]),
]


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if r.returncode != 0:
        print("FAILED:", " ".join(str(c) for c in cmd))
        print(r.stderr[-3000:])
        sys.exit(1)
    return r.stdout


def ffprobe_duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", path])
    return float(out.strip())


async def gen_tts():
    tasks = []
    for si, (_, _, sents) in enumerate(SCENES):
        for j, s in enumerate(sents):
            mp3 = os.path.join(WORK, f"t{si}_{j}.mp3")
            tasks.append((s, mp3))
    for s, mp3 in tasks:
        c = edge_tts.Communicate(s, VOICE, rate=RATE)
        await c.save(mp3)
    return tasks


def make_card():
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (1920, 1080), (13, 17, 23))
    d = ImageDraw.Draw(img)

    def font(sz, bold=False):
        p = r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc"
        return ImageFont.truetype(p, sz)

    def center(text, f, y, fill=(230, 235, 240)):
        w = d.textlength(text, font=f)
        d.text(((1920 - w) / 2, y), text, font=f, fill=fill)

    center("PMTEC", font(150, True), 300, (122, 162, 247))
    center("政 治 韧 性 数 字 孪 生", font(64, True), 505)
    center("DTC2026 数字孪生挑战赛 · 赛道二 演示", font(36), 630, (160, 170, 185))
    center("82 次提交 · 21 天 · 一条可信的数据闭环", font(28), 760, (110, 120, 135))
    img.save(os.path.join(WORK, "titlecard.png"))


def main():
    os.makedirs(WORK, exist_ok=True)

    print("== 1. TTS 旁白 ==")
    asyncio.run(gen_tts())

    print("== 2. 转 wav + 实测时长 + 排期 ==")
    schedule = []  # (start_main, dur, sentence)
    for si, (w0, w1, sents) in enumerate(SCENES):
        cursor = float(w0)
        for j, s in enumerate(sents):
            mp3 = os.path.join(WORK, f"t{si}_{j}.mp3")
            wav = os.path.join(WORK, f"t{si}_{j}.wav")
            run(["ffmpeg", "-y", "-i", mp3, "-ar", "48000", "-ac", "1", wav])
            dur = ffprobe_duration(wav)
            if cursor + dur > w1:
                print(f"WARN scene{si} overflow: {s} ends {cursor+dur:.1f} > {w1}")
            schedule.append((cursor, dur, s, wav))
            print(f"  S{si+1} {cursor:6.1f}-{cursor+dur:5.1f}s  {s}")
            cursor += dur + 0.6
    total_end = max(s + d for s, d, _, _ in schedule)
    assert total_end < MAIN_END, f"narration overruns main ({total_end} >= {MAIN_END})"

    print("== 3. 旁白混音 narration.wav ==")
    inputs, filters = [], []
    for k, (start, _, _, wav) in enumerate(schedule):
        inputs += ["-i", wav]
        ms = int(round((start + CARD_S) * 1000))
        filters.append(f"[{k}:a]adelay={ms}|{ms}[a{k}]")
    amix = "".join(f"[a{k}]" for k in range(len(schedule)))
    n = len(schedule)
    filters.append(f"{amix}amix=inputs={n}:duration=longest:normalize=0[amix]")
    filters.append("[amix]apad[out]")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters),
         "-map", "[out]", "-ar", "48000", "-ac", "2", "-t", str(MAIN_END + CARD_S),
         os.path.join(WORK, "narration.wav")])

    print("== 4. SRT（与音轨同源排期, +3s 片头偏移） ==")
    lines = []
    for k, (start, dur, s, _) in enumerate(schedule):
        def ts(t):
            h, r = divmod(t, 3600); m, sec = divmod(r, 60)
            return f"{int(h):02d}:{int(m):02d}:{sec:06.3f}".replace(".", ",")
        lines.append(f"{k+1}\n{ts(start+CARD_S)} --> {ts(start+CARD_S+dur)}\n{s}\n")
    srt_path = os.path.join(WORK, "video_v2_subs.srt")
    with open(srt_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))

    print("== 5. 片头卡 ==")
    make_card()

    print("== 6. 合成最终视频 ==")
    style = ("FontName=Microsoft YaHei,FontSize=15,Bold=1,"
             "PrimaryColour=&H00F0F4F8&,OutlineColour=&H96000000&,"
             "BorderStyle=4,BackColour=&H6E000000&,Outline=0,Shadow=0,"
             "Alignment=2,MarginV=42")
    fc = (
        "[0:v]fps=30,format=yuv420p,setsar=1[t];"
        "[1:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0d1117,fps=30,format=yuv420p,setsar=1[m];"
        "[t][m]concat=n=2:v=1:a=0[c];"
        f"[c]subtitles=video_v2_subs.srt:force_style='{style}'[v]"
    )
    run(["ffmpeg", "-y",
         "-loop", "1", "-framerate", "30", "-t", str(CARD_S), "-i", os.path.join(WORK, "titlecard.png"),
         "-ss", "0", "-to", str(MAIN_END), "-i", RAW,
         "-i", os.path.join(WORK, "narration.wav"),
         "-filter_complex", fc,
         "-map", "[v]", "-map", "2:a",
         "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k",
         "-shortest", FINAL], cwd=WORK)

    dur = ffprobe_duration(FINAL)
    kb = os.path.getsize(FINAL) // 1024
    print(f"DONE: {FINAL}\n  duration={dur:.1f}s size={kb} KB")


if __name__ == "__main__":
    main()
