# -*- coding: utf-8 -*-
"""下载演示区域离线底图瓦片（自包含，服务器/答辩现场零外网依赖）。

源: tile.openstreetmap.de（FOSSGIS 德国 OSM 镜像, 标准 XYZ/Web 墨卡托, 与原
tile.openstreetmap.org 同款 Carto 样式；国内可达, 官方主站不可达）。
覆盖: 全球 z2-z4 + 印太 bbox(lon 55-215, lat -50~40) z5-z6
      + 基地密集区(lon 120-170, lat -15~20) z7。
产物: pmtec_system/output/tiles/{z}/{x}/{y}.png —— gitignore 管理（可再生资产,
不入库不入包）, 随镜像 COPY 进演示栈 volume。重跑幂等（跳过已存在）。
用法: python generate_map_tiles.py   （无参数, ~3-6 分钟, 8 并发礼貌限速）
"""
import os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.stdout.reconfigure(encoding="utf-8")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "pmtec_system", "output", "tiles")
SRC = "https://tile.openstreetmap.de/{z}/{x}/{y}.png"
SUBS = ["", "a.", "b."]  # 备用子域轮换
UA = {"User-Agent": "PMTEC-DTC2026-offline-tiles/1.0 (one-time demo sync)"}

def tile_range(z, lon0, lon1, lat0, lat1):
    """标准 slippy-map XYZ: x 起点在 -180°（与 Leaflet 一致）。bbox 跨 180° 时 lon0/lon1 需先拆段。"""
    import math
    n = 2 ** z
    def lon_x(lon):
        return int((lon + 180) / 360 * n) % n
    def y(lat):
        return int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)
    x0, x1 = lon_x(lon0), lon_x(lon1)
    xs = range(x0, x1 + 1) if x0 <= x1 else list(range(x0, n)) + list(range(0, x1 + 1))
    return xs, range(min(y(lat1), y(lat0)), max(y(lat1), y(lat0)) + 1)

jobs = []
for z in (2, 3, 4):  # 全球底图
    xs, ys = tile_range(z, 0, 360, -85, 85)
    jobs += [(z, x, y) for x in xs for y in ys]
# 印太 bbox 跨 180° 经线, 拆两段: 55E-180 与 -180--145(=215E)
for z, lon_lo in ((5, (55, 180)), (6, (55, 180)), (7, (120, 170))):
    xs, ys = tile_range(z, *lon_lo, -50, 40)
    jobs += [(z, x, y) for x in xs for y in ys]
    xs2, ys2 = tile_range(z, -180, -145, -50, 40)
    jobs += [(z, x, y) for x in xs2 for y in ys2]
todo = [(z, x, y) for z, x, y in jobs if not os.path.exists(os.path.join(OUT, str(z), str(x), f"{y}.png"))]
print(f"清单 {len(jobs)} 张, 已有 {len(jobs)-len(todo)}, 待下载 {len(todo)}")

fail, done, size = [], 0, 0
def fetch(t):
    global done, size
    z, x, y = t
    path = os.path.join(OUT, str(z), str(x))
    os.makedirs(path, exist_ok=True)
    for i, s in enumerate(SUBS * 2):  # 每张最多 2 轮子域重试
        try:
            time.sleep(0.05)
            r = urllib.request.urlopen(urllib.request.Request(
                SRC.format(z=z, x=x, y=y).replace("https://", f"https://{s}"), headers=UA), timeout=20)
            d = r.read()
            if len(d) > 100:
                with open(os.path.join(path, f"{y}.png"), "wb") as f:
                    f.write(d)
                size += len(d)
                return None
        except Exception as e:
            if i == len(SUBS) * 2 - 1:
                return f"{z}/{x}/{y}: {type(e).__name__}"
    return None

t0 = time.time()
with ThreadPoolExecutor(8) as ex:
    for i, r in enumerate(ex.map(fetch, todo)):
        if r:
            fail.append(r)
        if (i + 1) % 200 == 0:
            print(f"  进度 {i+1}/{len(todo)}, {size//1024}KB, {time.time()-t0:.0f}s")
total = sum(len(fs) for _, _, fs in os.walk(OUT))
print(f"完成: 总计 {total} 张瓦片, {sum(os.path.getsize(os.path.join(r,f)) for r,_,fs in os.walk(OUT) for f in fs)//1024//1024}MB, 失败 {len(fail)}, 耗时 {time.time()-t0:.0f}s")
if fail:
    print("失败清单(前10):", *fail[:10], sep="\n  ")
    sys.exit(1)
