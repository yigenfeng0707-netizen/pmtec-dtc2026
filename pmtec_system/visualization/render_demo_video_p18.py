#!/usr/bin/env python3
"""P18 演示视频 V3 自动渲染器（≥5 分钟，含失败与边界情况，全部画面来自真实运行系统）。

管线：
  1. TTS   : edge-tts zh-CN-YunxiNeural 逐幕旁白 + 词级时间戳 -> 短语字幕
  2. 实拍  : headless Chrome + **CDP Page.startScreencast 页面级抓帧**——帧直接来自
             标签页渲染内容，与桌面/窗口焦点/会话恢复彻底解耦（gdigrab 录桌面会
             拍到前台窗口之外的任何东西，V3 前三轮全败于此，弃用）。
             CDP 时间轴驱动公网 ECS (47.98.35.86:8888) 的真实页面。
  3. 音轨  : 程序化电影配乐（和弦进程随剧情张力）+ 旁白闪避 -> final_mix.wav
  4. 合成  : 帧序列按到达时间戳组帧 -> 逐幕淡入淡出 concat -> SRT 烧录 -> 音轨 mux

对应《演示视频分镜脚本-P18-5min.md》八幕，画面 100% 来自当前运行中的公网部署。

Run: python visualization/render_demo_video_p18.py
产出: output/pmtec_demo_video_v3.mp4
"""

import asyncio
import base64
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
from pathlib import Path

import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.stdout.reconfigure(encoding="utf-8")

WORK = os.path.join(PROJECT_ROOT, "output", "v3_work")
OUT = os.path.join(PROJECT_ROOT, "output", "pmtec_demo_video_v3.mp4")
FFMPEG = "ffmpeg"
SR = 24000
FPS = 30
W, H = 1920, 1080
VOICE = "zh-CN-YunxiNeural"
RATE, PITCH = "-4%", "-3Hz"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def _free_port():
    import socket
    sk = socket.socket()
    sk.bind(("127.0.0.1", 0))
    port = sk.getsockname()[1]
    sk.close()
    return port


CDP_PORT = _free_port()  # 每次运行挑空闲端口——9222 被僵尸监听占死的教训
SITE = os.environ.get("P18_VIDEO_SITE", "http://47.98.35.86:8888")
VIDEO_USER = os.environ.get("P18_VIDEO_USER", "pingwei")
VIDEO_PASS = os.environ.get("P18_VIDEO_PASS", "Test123456@")

# ================================================================ 八幕脚本
CHORD = {
    "Am": [110.00, 130.81, 164.81], "F": [87.31, 110.00, 130.81],
    "Dm": [73.42, 87.31, 110.00], "dim": [123.47, 146.83, 174.61],
    "Em": [82.41, 98.00, 123.47], "C": [130.81, 164.81, 196.00],
    "C9": [130.81, 164.81, 196.00, 293.66],
}

ACTS = [
    dict(tag="M1开场", plan=25, music=(CHORD["Am"], 0.16, 0.0, 0.25),
         narr=("PMTEC 数字孪生战场。它回答一个问题：当对手不开一枪、只用政治手段"
               "让盟友拒绝你使用基地时，防空体系怎么活下来。你现在看到的每一个画面、"
               "每一个数字，都来自正在公网运行的真实系统，无摆拍数据。"),
         tl=[(0, ("nav", "/")), (6, ("scrollpage", None)), (16, ("scrollpage", None))]),
    dict(tag="M2数据底座", plan=35, music=(CHORD["Am"], 0.18, 0.0, 0.30),
         narr=("数据底座，是六十七个权威基地实体，三十四个字段逐字段可溯源："
               "国会研究处报告、国防部基地结构报告双源锚定，置信度四级标注，"
               "信息截至二零二六年九月。右侧面板是虚实同步的数字孪生注册表："
               "一百三十余个孪生体实时对账，保真度百分之九十五以上，"
               "每一条事件都在指挥链、拦截决策与政治准入之间逐周期流转。"),
         tl=[(0, ("nav", "/pmtec_realtime_display.html")), (8, ("panel_scroll", None)),
             (24, ("panel_scroll", None))]),
    dict(tag="M3正常推演", plan=50, music=(CHORD["Dm"], 0.20, 1.0, 0.35),
         narr=("这是 SPEAR 事件流的逐周期回放：一千五百零六个真实事件、"
               "二十二类事件与 DoDAF 交换矩阵逐行对账。基准拦截率百分之七十九点一，"
               "六策略一百五十次蒙特卡洛实测；概率预测有校准证据，"
               "Brier 分数零点一一。四条泳道——政治、拦截、损伤、威胁——"
               "每一帧都可以回放、可以追责。"),
         tl=[(0, ("nav", "/pmtec_spear_timeline.html")), (8, ("click", "#btn-play")),
             (12, ("idle", None)), (40, ("idle", None))]),
    dict(tag="M4失效沙盘", plan=55, music=(CHORD["dim"], 0.26, 0.45, 0.35),
         narr=("评审最关心的问题：打掉百分之三十的节点，体系还剩多少？"
               "两万次蒙特卡洛给出曲线：随机打掉三成，体系价值保留七成——"
               "大数冗余在起作用；但按杀伤网优先序定向打，保留率骤降到百分之二十八点八，"
               "其中十四座是一级枢纽。红方的代价：一百到一百六十发导弹。"
               "这个数字有交叉验证：饱和策略实测每放进一枚突防，红方付出五发，"
               "与毁伤模型一致。保护一级枢纽，是体系设计的第一优先级。"),
         tl=[(0, ("nav", "/Five_Questions_Report.html")), (7, ("scrollto", None)),
             (20, ("idle", None)), (38, ("idle", None))]),
    dict(tag="M5政治拒止", plan=40, music=(CHORD["dim"], 0.22, 0.8, 0.30),
         narr=("政治拒止，是红方零弹药的攻击。主权打击链一响，九个盟友站点被拒止，"
               "可用基地从六十七收缩到五十八。价值口径只掉百分之零点二——"
               "它咬掉的是前沿存在感。复合场景叠加动能打击，实体保留率压到六十一。"
               "失效是分级的，边界是跑出来的：这套体系知道自己在哪里会失效。"),
         tl=[(0, ("nav", "/Five_Questions_Report.html")), (6, ("scrolltop", None)),
             (12, ("idle", None)), (24, ("nav", "/pmtec_realtime_display.html"))]),
    dict(tag="M6参谋官", plan=40, music=(CHORD["Em"], 0.22, 0.30, 0.45),
         narr=("AI 参谋官，在建议位，不在执行位。公网实测：它读取孪生摘要，"
               "调用大模型生成带图表的态势报告——现在返回两百，真实可用。"
               "把它的密钥拔掉，接口返回五百零三，参谋官下线，仿真照常运行——"
               "这就是失效降级设计。它的一切输出都要过人的审批，"
               "每条建议都能回放到 SPEAR 事件流逐周期对账。"),
         tl=[(0, ("nav", "/ai_situation_analysis.html")), (7, ("scrollpage", None)),
             (18, ("scrollpage", None)), (30, ("idle", None))]),
    dict(tag="M7断网离线", plan=35, music=(CHORD["F"], 0.20, 0.0, 0.55),
         narr=("断网呢？底图的两千二百五十张瓦片是本地自包含的，"
               "夜半球由浏览器端做真实天文计算——零外部数据源。"
               "地球总览、实时大屏、全部产物，断网可用。"
               "这在评审现场，很重要。"),
         tl=[(0, ("nav", "/pmtec_globe.html")), (10, ("idle", None)),
             (18, ("click", "#btn-zoom")), (22, ("idle", None))]),
    dict(tag="M8收束", plan=34, music=(CHORD["C9"], 0.26, 0.0, 0.85),
         narr=("一键复现脚本，五分钟跑完口径自检、数据字典再生与五问实跑，日志逐行留档；"
               "一百四十二次提交、三十二天，全部可查。"
               "适应，优于压制——用真实世界数据，让数字孪生更真；"
               "用失效边界，让答案更硬。PMTEC，谢谢观看。"),
         tl=[(0, ("nav", "/")), (6, ("idle", None)), (20, ("idle", None))]),
]


# ================================================================ TTS
def _phrase_split(narr_len, words):
    phrases, cur, cur0 = [], "", None
    for off_ns, dur_ns, wtext in words:
        t0 = off_ns / 1e7
        t1 = (off_ns + dur_ns) / 1e7
        if cur0 is None:
            cur0 = t0
        cur += wtext
        if any(p in wtext for p in "，。！？；、：—…") or len(cur) >= 16:
            phrases.append((cur0, t1, cur))
            cur, cur0 = "", None
    if cur:
        phrases.append((cur0, narr_len, cur))
    return [(a, b, t) for a, b, t in phrases if t.strip()]


async def _tts_act(i, text):
    import edge_tts

    mp3 = os.path.join(WORK, f"nar_{i}.mp3")
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
                        words.append((chunk["offset"], chunk["duration"],
                                      chunk["text"]))
            break
        except Exception as e:
            if attempt == 2:
                print(f"    [TTS] 幕 {i} 失败: {e}")
                return None, []
            await asyncio.sleep(2)
    wav = mp3.replace(".mp3", ".wav")
    subprocess.run([FFMPEG, "-y", "-i", mp3, "-ar", str(SR), "-ac", "1", wav],
                   capture_output=True)
    with wave.open(wav, "rb") as w:
        narr_dur = w.getnframes() / w.getframerate()
    return narr_dur, _phrase_split(narr_dur, words)


# ================================================================ CDP（单读泵架构）
class Page:
    """CDP 标签页：单一读泵分发消息——响应按 id 归还，事件交处理器。
    （多协程并发 recv 会互相偷消息，V3 前版的时间轴+帧收集并发冲突即源于此）"""

    def __init__(self, ws_url):
        self.ws_url, self._id, self.ws = ws_url, 0, None
        self._pending = {}
        self._frame_handler = None
        self._reader = None

    async def __aenter__(self):
        import websockets
        self.ws = await websockets.connect(self.ws_url, max_size=None,
                                           ping_interval=None)
        self._reader = asyncio.create_task(self._read_loop())
        return self

    async def __aexit__(self, *a):
        if self._reader:
            self._reader.cancel()
        await self.ws.close()

    async def _read_loop(self):
        print("    [CDP] 读泵启动")
        try:
            while True:
                raw = await self.ws.recv()
                msg = json.loads(raw)
                if "id" in msg:
                    fut = self._pending.pop(msg["id"], None)
                    if fut and not fut.done():
                        fut.set_result(msg)
                elif msg.get("method", "").startswith("Page.screencastFrame"):
                    pass  # 已弃用 screencast 路径
        except asyncio.CancelledError:
            print("    [CDP] 读泵取消")
        except Exception as e:
            import traceback
            print(f"    [CDP] 读泵退出: {type(e).__name__}: {e}")
            traceback.print_exc()

    async def cmd(self, method, **params):
        self._id += 1
        fut = asyncio.get_event_loop().create_future()
        self._pending[self._id] = fut
        await self.ws.send(json.dumps({"id": self._id, "method": method,
                                       "params": params}))
        msg = await asyncio.wait_for(fut, timeout=8)
        if "error" in msg:
            raise RuntimeError(f"{method}: {msg['error']}")
        return msg.get("result", {})

    async def js(self, expression, await_promise=False):
        r = await self.cmd("Runtime.evaluate", expression=expression,
                           returnByValue=True, awaitPromise=await_promise)
        if "exceptionDetails" in r:
            raise RuntimeError("页面 JS 异常: "
                               + str(r["exceptionDetails"].get("exception", {})
                                     .get("description", ""))[:200])
        return r.get("result", {}).get("value")

    async def nav(self, url):
        await self.cmd("Page.navigate", url=url)


CLICK = "document.querySelector({sel!r}) && document.querySelector({sel!r}).click()"


def http_json(path):
    """CDP 本地探测：绕过系统代理（后台 shell 若带 http_proxy 会劫持 127.0.0.1）。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f"http://127.0.0.1:{CDP_PORT}{path}", timeout=5) as r:
        return json.loads(r.read().decode())


def get_jwt():
    req = urllib.request.Request(SITE + "/api/v1/auth/login", method="POST")
    req.add_header("Content-Type", "application/json")
    data = json.dumps({"username": VIDEO_USER, "password": VIDEO_PASS}).encode()
    with urllib.request.urlopen(req, data=data, timeout=10) as r:
        tok = json.load(r)["token"]
    print(f"    [鉴权] {VIDEO_USER} 登录成功 (token {len(tok)}B)")
    return tok


LOGIN_JS = """
    (async () => {
        for (let i = 0; i < 30; i++) {
            if (document.readyState === 'complete') break;
            await new Promise(r => setTimeout(r, 300));
        }
        if (!location.pathname.includes('login')) return true;  // 已有会话
        const u = document.getElementById('u');
        const p = document.getElementById('p');
        if (!u || !p) return 'no-form';
        const set = (el, v) => { el.value = v;
            el.dispatchEvent(new Event('input', {bubbles: true})); };
        set(u, __USER__); set(p, __PASS__);
        const f = document.getElementById('f') || u.form;
        f.requestSubmit ? f.requestSubmit() : document.getElementById('b').click();
        for (let i = 0; i < 25; i++) {
            await new Promise(r => setTimeout(r, 300));
            if (!location.pathname.includes('login')) return true;
        }
        return 'no-redirect:' + location.pathname;
    })()
""".replace("__USER__", json.dumps(VIDEO_USER)).replace(
    "__PASS__", json.dumps(VIDEO_PASS))


async def ensure_session(page):
    """会话建立：headless 下先走 Cookie 注入（与目检截图同机制，已验证），
    失败回落表单登录。"""
    token = get_jwt()
    r = await page.cmd("Network.setCookie", name="pmtec_token", value=token,
                       url=SITE + "/", httpOnly=True)
    await page.nav(SITE + "/")
    await asyncio.sleep(2.5)
    loc = str(await page.js("location.pathname"))
    if "login" in loc or not r.get("success"):
        print("    [鉴权] Cookie 注入未生效，回落表单登录...")
        await page.nav(SITE + "/login.html")
        await asyncio.sleep(1.5)
        ok = await page.js(LOGIN_JS, await_promise=True)
        if ok is not True:
            raise RuntimeError(f"表单登录失败: {ok!r}")
    print("    [鉴权] 会话就绪:", await page.js("location.pathname"))


async def run_timeline(page, act, dur):
    t0 = time.monotonic()
    for at, step in act["tl"]:
        kind, arg = (list(step) + [None])[:2]
        wait = max(0, t0 + at - time.monotonic())
        if wait:
            await asyncio.sleep(wait)
        try:
            if kind == "nav":
                for attempt in range(2):
                    await page.nav(SITE + arg)
                    await asyncio.sleep(2.5)
                    loc = await page.js("location.pathname")
                    if "login" not in str(loc):
                        break
                    print(f"    [自愈] {arg} 落到登录页(第{attempt+1}次)，重试")
                    await asyncio.sleep(2.0)
            elif kind == "click":
                await page.js(CLICK.format(sel=arg))
            elif kind == "scrollpage":
                for _ in range(14):
                    await page.js("window.scrollBy(0,40)")
                    await asyncio.sleep(0.35)
            elif kind == "scrollto":
                await page.js("window.scrollTo(0,0)")
                for _ in range(30):
                    await page.js("window.scrollBy(0,60)")
                    await asyncio.sleep(0.12)
            elif kind == "scrolltop":
                await page.js("window.scrollTo(0,0)")
            elif kind == "panel_scroll":
                await page.js(
                    "(()=>{var p=document.getElementById('event-log')||"
                    "document.getElementById('ai-panel')||"
                    "document.scrollingElement;p.scrollTop+=120;})()")
            elif kind == "idle":
                pass
        except Exception as e:
            print(f"    [时间轴] {kind} 异常(继续): {type(e).__name__}: {e}")
    rest = t0 + dur - time.monotonic()
    if rest > 0:
        await asyncio.sleep(rest)


# ================================================================ Screencast 采集
def capture_acts(act_durs):
    kill_stale_chrome()
    profile = tempfile.mkdtemp(prefix="pmtec_v4_")
    chrome = subprocess.Popen(
        [CHROME, f"--remote-debugging-port={CDP_PORT}", f"--user-data-dir={profile}",
         "--headless=new", "--no-first-run", "--no-default-browser-check",
         "--hide-scrollbars", f"--window-size={W},{H}", f"{SITE}/login.html"])
    try:
        page_t = None
        for attempt in range(3):
            for _ in range(30):
                try:
                    targets = http_json("/json/list")
                    page_t = next(t for t in targets if t["type"] == "page")
                    break
                except Exception:
                    time.sleep(1)
            if page_t:
                break
            kill_stale_chrome()  # 端口被残留实例占住：清掉再试
            time.sleep(2)
            chrome.terminate()
            time.sleep(2)
            chrome = subprocess.Popen(
                [CHROME, f"--remote-debugging-port={CDP_PORT}",
                 f"--user-data-dir={tempfile.mkdtemp(prefix='pmtec_v4_')}",
                 "--headless=new", "--no-first-run",
                 "--no-default-browser-check", "--hide-scrollbars",
                 f"--window-size={W},{H}", f"{SITE}/login.html"])
        if not page_t:
            raise RuntimeError("Chrome 调试端口未就绪")
        asyncio.run(_capture_all(page_t["webSocketDebuggerUrl"], act_durs))
    finally:
        chrome.terminate()
        time.sleep(2)
        chrome.kill()


async def _capture_all(ws_url, act_durs):
    async with Page(ws_url) as page:
        await page.cmd("Page.enable")
        await page.cmd("Runtime.enable")
        await page.cmd("Network.enable")
        await page.cmd("Emulation.setDeviceMetricsOverride", width=W, height=H,
                       deviceScaleFactor=1, mobile=False)
        await ensure_session(page)

        for i, act in enumerate(ACTS):
            dur = act_durs[i]
            act_dir = os.path.join(WORK, f"frames_{i}")
            os.makedirs(act_dir, exist_ok=True)
            for f in os.listdir(act_dir):
                os.remove(os.path.join(act_dir, f))
            frames = []  # (arrival_monotonic, path)
            print(f"  [实拍] 幕 {i} {act['tag']} 目标 {dur:.1f}s ...", flush=True)
            # 定时轮询截图（0.15s ≈ 6.7fps）：请求-响应模式，帧数确定性保证。
            # headless 下页面不主动重绘，事件驱动的 screencast 每幕只推 2-3 帧
            # （合成器推帧机制对静态内容节流），轮询不依赖重绘。
            timeline_task = asyncio.create_task(run_timeline(page, act, dur))
            t0 = time.monotonic()
            deadline = t0 + dur + 25  # 整幕看门狗
            while True:
                elapsed = time.monotonic() - t0
                if elapsed >= dur:
                    break
                try:
                    shot = await page.cmd("Page.captureScreenshot",
                                          format="jpeg", quality=80)
                    path = os.path.join(act_dir, f"{len(frames):05d}.jpg")
                    with open(path, "wb") as f:
                        f.write(base64.b64decode(shot["data"]))
                    frames.append((time.monotonic(), path))
                except Exception as e:
                    print(f"    [抓帧] 异常(继续): {type(e).__name__}: {e}")
                    await asyncio.sleep(0.15)
                remain = dur - (time.monotonic() - t0)
                await asyncio.sleep(min(0.15, max(remain, 0)))
                if time.monotonic() > deadline:
                    print("    [看门狗] 墙钟超限，提前收幕")
                    break
            timeline_task.cancel()
            try:
                await timeline_task
            except (asyncio.CancelledError, Exception):
                pass

            if not frames:
                raise RuntimeError(f"幕 {i} 未收到任何帧")
            # 末帧补齐到 dur（组帧时最后一张驻留）
            write_concat_list(frames, dur, act_dir)
            frames_to_mp4(act_dir, dur, os.path.join(WORK, f"act_{i}.mp4"))
            print(f"    {len(frames)} 帧 -> {os.path.getsize(WORK, ) // 1024 if False else os.path.getsize(os.path.join(WORK, f'act_{i}.mp4'))//1024}KB")


def write_concat_list(frames, dur, act_dir):
    t0 = frames[0][0]
    lines = []
    for k, (t, path) in enumerate(frames):
        rel = max(t - t0, 0.0)
        lines.append(f"file '{os.path.basename(path)}'")
        tnext = frames[k + 1][0] - t0 if k + 1 < len(frames) else dur
        lines.append(f"duration {max(min(tnext, dur) - rel, 0.04):.3f}")
    lines.append(f"file '{os.path.basename(frames[-1][1])}'")
    with open(os.path.join(act_dir, "list.txt"), "w", encoding="utf-8") as f:
        f.write("ffconcat version 1.0\n" + "\n".join(lines))


def frames_to_mp4(act_dir, dur, out):
    # 输出必须是绝对路径——此前 basename(out)+cwd 把新编码的幕文件写进了
    # frames_N/ 子目录，assemble 消费的是 WORK 下的旧 gdigrab 文件（V3 末轮
    # "修好采集仍见登录页"的根因）
    subprocess.run(
        [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", "list.txt",
         "-vf", f"fps={FPS},format=yuv420p,setsar=1,"
                f"fade=t=in:st=0:d=0.35,fade=t=out:st={max(dur - 0.35, 0):.2f}:d=0.35",
         "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "fast", "-crf", "19",
         "-pix_fmt", "yuv420p", out],
        check=True, cwd=act_dir)


def kill_stale_chrome():
    """只杀本脚本此前启动的调试实例（按配置目录前缀匹配），不动用户浏览器。"""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
             "Where-Object { $_.CommandLine -like '*pmtec_v4_*' -or "
             "$_.CommandLine -like '*pmtec_video_profile*' -or "
             "$_.CommandLine -like '*chrome-p18*' -or "
             "$_.CommandLine -like '*remote-debugging-port=9222*' } | "
             "Select-Object -ExpandProperty ProcessId"],
            capture_output=True, text=True, timeout=20)
        for pid in r.stdout.split():
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
            print(f"    [清理] 结束残留调试实例 PID {pid}")
    except Exception:
        pass


# ================================================================ 音轨
def load_narr_wave(i):
    wav = os.path.join(WORK, f"nar_{i}.wav")
    if not os.path.exists(wav):
        return None
    with wave.open(wav, "rb") as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return data.astype(np.float64) / 32768.0


def synth_bgm(act_durs):
    total = int(sum(act_durs) * SR)
    bgm = np.zeros(total)
    t_cursor = 0
    for si, dur in enumerate(act_durs):
        chord, amp, pulse, bright = ACTS[si]["music"]
        n = int(dur * SR)
        t = np.arange(n) / SR
        seg = np.zeros(n)
        for k, f in enumerate(chord):
            ph = 0.7 * k
            trem = 1.0 + 0.15 * np.sin(2 * np.pi * 0.13 * t + ph)
            seg += np.sin(2 * np.pi * f * t + ph) * trem
            if bright > 0.3:
                seg += bright * 0.5 * np.sin(2 * np.pi * 2 * f * t + ph * 2)
        seg /= len(chord) * 1.6
        if pulse > 0:
            kick = np.zeros(n)
            period = int(pulse * SR)
            kn = min(int(0.16 * SR), period)
            kt = np.arange(kn) / SR
            kick_wave = np.sin(2 * np.pi * 52 * kt) * np.exp(-kt * 16)
            for j in range(n // period + 1):
                s = j * period
                e = min(s + kn, n)
                if s < n:
                    kick[s:e] += kick_wave[: e - s]
            seg += 0.55 * kick
            if si == 3:
                seg += 0.30 * np.sin(2 * np.pi * 55.0 * t)
        atk = min(int(1.2 * SR), n // 3)
        rel = min(int(1.5 * SR), n // 3)
        env = np.ones(n)
        env[:atk] = np.linspace(0, 1, atk)
        env[n - rel:] = np.linspace(1, 0, rel)
        e = seg * env * amp
        if si == len(ACTS) - 1:  # 终章后 40% 切纯 C 收束
            cut = int(n * 0.6)
            t2 = np.arange(n - cut) / SR
            tail = np.zeros(n - cut)
            for k, f in enumerate(CHORD["C"]):
                tail += np.sin(2 * np.pi * f * t2 + 0.7 * k)
            tail = tail / len(CHORD["C"]) * 1.2
            rel2 = min(int(2.0 * SR), n - cut)
            tenv = np.ones(n - cut)
            tenv[: int(0.8 * SR)] = np.linspace(0, 1, int(0.8 * SR))
            tenv[-rel2:] = np.linspace(1, 0, rel2)
            e[cut:] = tail * tenv * amp
        s = min(t_cursor + n, total)
        bgm[t_cursor:s] += e[: s - t_cursor]
        t_cursor += s - t_cursor
    return bgm


def build_final_mix(act_durs, narr_durs, out_path):
    total = int(sum(act_durs) * SR)
    narr = np.zeros(total)
    starts, cur = [], 0.0
    for i, d in enumerate(act_durs):
        starts.append(cur)
        if narr_durs[i] is not None:
            w = load_narr_wave(i)
            s = int((cur + 0.6) * SR)
            e = min(s + len(w), total)
            narr[s:e] += w[: e - s]
        cur += d
    env = np.abs(narr)
    k = int(0.20 * SR)
    env = np.convolve(env, np.ones(k) / k, mode="same")
    env = np.clip(env / 0.04, 0, 1)
    duck = 1.0 - 0.75 * env
    bgm = synth_bgm(act_durs)
    mix = narr * 0.95 + bgm * duck
    peak = np.abs(mix).max()
    if peak > 0:
        mix *= 0.89 / peak
    with wave.open(out_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    return sum(act_durs), starts


# ================================================================ 合成
def write_srt(sub_global, path):
    def ts(t):
        h, r = divmod(t, 3600)
        m, sec = divmod(r, 60)
        return f"{int(h):02d}:{int(m):02d}:{sec:06.3f}".replace(".", ",")
    lines = []
    for k, (a, b, txt) in enumerate(sub_global):
        lines.append(f"{k+1}\n{ts(a)} --> {ts(b)}\n{txt}\n")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))


def assemble(act_durs, sub_global):
    srt = os.path.join(WORK, "v3_subs.srt")
    write_srt(sub_global, srt)
    inputs, fparts = [], []
    for i, d in enumerate(act_durs):
        inputs += ["-i", os.path.join(WORK, f"act_{i}.mp4")]
        fparts.append(
            f"[{i}:v]fps=30,format=yuv420p,setsar=1[v{i}]")
    fc = ";".join(fparts) + ";" + "".join(f"[v{i}]" for i in range(len(ACTS))) + \
        f"concat=n={len(ACTS)}:v=1:a=0[cat]"
    cat = os.path.join(WORK, "concat.mp4")
    subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                    *inputs, "-filter_complex", fc, "-map", "[cat]",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                    "-pix_fmt", "yuv420p", cat], check=True)
    # 字幕烧录 + 音轨（subtitles 滤镜 filename 用相对路径 + cwd=WORK——
    # Windows 盘符冒号会破坏 ffmpeg 滤镜参数解析）
    style = ("FontName=Microsoft YaHei,FontSize=15,Bold=1,"
             "PrimaryColour=&H00F0F4F8&,OutlineColour=&H96000000&,"
             "BorderStyle=4,BackColour=&H6E000000&,Outline=0,Shadow=0,"
             "Alignment=2,MarginV=42")
    subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                    "-i", cat, "-i", os.path.join(WORK, "final_mix.wav"),
                    "-filter_complex",
                    f"[0:v]subtitles=filename=v3_subs.srt:force_style='{style}'[v]",
                    "-map", "[v]", "-map", "1:a",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                    "-shortest", OUT], check=True, cwd=WORK)


def qa():
    r = subprocess.run([FFMPEG, "-i", OUT, "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.findall(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    dur = int(m[0][0]) * 3600 + int(m[0][1]) * 60 + float(m[0][2]) if m else 0
    print(f"[QA] 容器时长 {dur:.1f}s ｜ ≥300s 达标: {dur >= 300}")
    return dur


def main():
    os.makedirs(WORK, exist_ok=True)
    print("[V3] 1/5 合成八幕神经旁白 (zh-CN-YunxiNeural, 词级时间戳)...")
    narr_durs, sub_scheds = [], []
    for i, act in enumerate(ACTS):
        d, ph = asyncio.run(_tts_act(i, act["narr"]))
        narr_durs.append(d)
        sub_scheds.append(ph)
        print(f"    {act['tag']}: {d:.1f}s / {len(ph)} 句" if d else
              f"    {act['tag']}: TTS 失败(静音+均分字幕)")

    act_durs = []
    sub_global = []
    cursor = 0.0
    for i, act in enumerate(ACTS):
        nd = narr_durs[i]
        d = max(act["plan"], math.ceil(nd + 2.0)) if nd else act["plan"]
        act_durs.append(d)
        ph = sub_scheds[i]
        if not ph:  # TTS 失败兜底：均分
            span = max(d - 1.4, 1e-6)
            segs = [act["narr"][j:j + 16] for j in range(0, len(act["narr"]), 16)]
            ph = [(0.6 + k * span / max(len(segs), 1),
                   0.6 + (k + 1) * span / max(len(segs), 1), t)
                  for k, t in enumerate(segs)]
            sub_scheds[i] = ph
        for (a, b, txt) in ph:
            sub_global.append((cursor + 0.6 + a, cursor + 0.6 + b, txt))
        cursor += d
    total = sum(act_durs)
    print(f"[V3] 2/5 幕时长 {[round(d) for d in act_durs]} -> 总长 {total:.0f}s"
          f"（≥300s: {total >= 300}），字幕 {len(sub_global)} 条")

    print("[V3] 3/5 实拍八幕（headless Chrome + CDP Screencast 页面级抓帧）...")
    capture_acts(act_durs)

    print("[V3] 4/5 混音（旁白 + 程序化配乐 + 闪避）...")
    build_final_mix(act_durs, narr_durs, os.path.join(WORK, "final_mix.wav"))

    print("[V3] 5/5 合成（组帧 concat + SRT 烧录 + 音轨）...")
    assemble(act_durs, sub_global)
    size = os.path.getsize(OUT)
    print(f"[V3] 完成: {OUT} ({size / 1e6:.1f} MB)")
    qa()


if __name__ == "__main__":
    main()
