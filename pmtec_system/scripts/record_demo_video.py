"""演示视频 V2 自动录制：ffmpeg gdigrab 录桌面 + Chrome CDP 按时间轴驱动五幕页面。

产出无声画面 pmtec_system/output/pmtec_demo_raw_take.mp4（约 166s），
旁白/字幕由 postprocess_demo_video.py 后期合成。
"""
import asyncio, json, os, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

import websockets

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE = "http://localhost:8899"
OUT = Path(__file__).resolve().parents[1] / "output" / "pmtec_demo_raw_take.mp4"
CDP_PORT = 9222


def http_json(path):
    with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}{path}", timeout=5) as r:
        return json.loads(r.read().decode())


class Page:
    def __init__(self, ws_url):
        self.ws_url = ws_url
        self._id = 0
        self.ws = None

    async def __aenter__(self):
        self.ws = await websockets.connect(self.ws_url, max_size=None, ping_interval=None)
        return self

    async def __aexit__(self, *a):
        await self.ws.close()

    async def cmd(self, method, **params):
        self._id += 1
        await self.ws.send(json.dumps({"id": self._id, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == self._id:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    async def nav(self, url):
        await self.cmd("Page.navigate", url=url)

    async def js(self, expression):
        r = await self.cmd("Runtime.evaluate", expression=expression, returnByValue=True)
        return r.get("result", {}).get("value")


CLICK = "document.querySelector({sel!r}) && document.querySelector({sel!r}).click()"
SETCHK = "(()=>{{var c=document.querySelector(\"input[data-l={layer!r}]\");c.checked={val};c.dispatchEvent(new Event('change',{{bubbles:true}}));}})()"


def set_layers(*specs):
    return ";".join(SETCHK.format(layer=l, val=v) for l, v in specs)


async def timeline(page):
    t0 = time.time()

    async def at(sec, label, coro=None):
        await asyncio.sleep(max(0, t0 + sec - time.time()))
        print(f"[{time.time()-t0:6.1f}s] {label}", flush=True)
        if coro is not None:
            await coro

    async def js_now(expr):
        await page.js(expr)

    # ---- S1 全球视野 0:00-0:40
    await at(0, "S1 地球总览", page.nav(f"{BASE}/pmtec_globe.html"))
    await at(8, "  隐藏三图层（留政治准入+昼夜线）", js_now(
        set_layers(("strike", "false"), ("burst", "false"), ("hub", "false"))))
    await at(12, "  开 政治准入(重绘)", js_now(
        set_layers(("pol", "false"), ("pol", "true"))))
    await at(17, "  开 弹道齐射", js_now(set_layers(("strike", "true"))))
    await at(23, "  开 拦截/突防", js_now(set_layers(("burst", "true"))))
    await at(28, "  开 EDCA 枢纽圈", js_now(set_layers(("hub", "true"))))
    await at(32, "  西太聚焦", js_now(CLICK.format(sel="#btn-zoom")))

    # ---- S2 实时孪生 + AI 参谋官 0:40-1:30
    await at(40, "S2 实时大屏", page.nav(f"{BASE}/pmtec_realtime_display.html"))
    await at(46, "  打开 AI 参谋官面板", js_now(CLICK.format(sel="#btn-ai")))
    await at(49, "  缓读面板 21s")
    for i in range(42):
        await asyncio.sleep(0.5)
        await page.js("(()=>{var p=document.getElementById('ai-panel');p.scrollTop+=9;})()")
    await at(72, "  切换 3D 视图", js_now(CLICK.format(sel="#view-toggle")))

    # ---- S3 孪生仪表盘 1:30-2:00
    await at(90, "S3 孪生仪表盘", page.nav(f"{BASE}/dt_dashboard.html"))
    await at(95, "  缓滚页面 20s")
    for i in range(40):
        await asyncio.sleep(0.5)
        await page.js("window.scrollBy(0,9)")

    # ---- S4 SPEAR 回放 2:00-2:30
    await at(120, "S4 SPEAR 时间线（7MB 加载留 6s）", page.nav(f"{BASE}/pmtec_spear_timeline.html"))
    await at(128, "  自动回放 Play", js_now(CLICK.format(sel="#btn-play")))

    # ---- S5 收尾 2:30-2:46
    await at(150, "S5 回到地球总览（默认全图层）", page.nav(f"{BASE}/pmtec_globe.html"))
    await at(158, "  西太聚焦定格", js_now(CLICK.format(sel="#btn-zoom")))
    await at(166, "  收束")


async def main():
    profile = os.path.join(tempfile.gettempdir(), "pmtec_video_profile")
    os.makedirs(profile, exist_ok=True)
    chrome = subprocess.Popen([
        CHROME, f"--remote-debugging-port={CDP_PORT}", f"--user-data-dir={profile}",
        "--no-first-run", "--no-default-browser-check", "--disable-session-crashed-bubble",
        "--kiosk",
        f"{BASE}/pmtec_globe.html"])
    try:
        for _ in range(30):
            try:
                targets = http_json("/json/list")
                page_t = next(t for t in targets if t["type"] == "page")
                break
            except Exception:
                time.sleep(1)
        else:
            raise RuntimeError("Chrome 调试端口未就绪")

        async with Page(page_t["webSocketDebuggerUrl"]) as boot:
            await boot.cmd("Runtime.enable")
            wid = (await boot.cmd("Browser.getWindowForTarget"))["windowId"]
            await boot.cmd("Browser.setWindowBounds", windowId=wid, bounds={"windowState": "fullscreen"})
        await asyncio.sleep(3)

        ff = subprocess.Popen(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "gdigrab", "-framerate", "30",
             "-i", "desktop", "-c:v", "libx264", "-preset", "fast", "-crf", "18",
             "-pix_fmt", "yuv420p", "-y", str(OUT)],
            stdin=subprocess.PIPE)
        print("recording ->", OUT, flush=True)
        await asyncio.sleep(2)  # ffmpeg 预热
        async with Page(page_t["webSocketDebuggerUrl"]) as page:
            await page.cmd("Runtime.enable")
            await timeline(page)
        ff.stdin.write(b"q"); ff.stdin.flush()
        ff.wait(timeout=60)
        print("saved:", OUT, OUT.stat().st_size // 1024, "KB", flush=True)
    finally:
        try:
            http_json("/json/version")
            with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/close", timeout=3):
                pass
        except Exception:
            pass
        chrome.terminate()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
