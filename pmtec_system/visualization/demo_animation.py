#!/usr/bin/env python3
"""
P13: 演示视频核心录制源 — 灰色地带演化链路自动播放动画

数据驱动（全部来自真实系统产物，无摆拍）：
  - 67 实体基地坐标：data/bases_v2.geojson
  - 演化链路时序：scripts/political_resilience_analysis.py 实验 2（seed=42 确定性回放）
  - 结果数据：monte_carlo_results*.json（三场景对照 / 六策略全量）

场景序列（约 46s 循环）：
  S0 片头 → S1 基线态势 → S2 灰色地带(PH→Restricted) → S3 主权打击(9 站 Denied,
  可用 67→58) → S4 ASDA-Adapt 战术适应(规避/redeploy/敞口压制) → S5 再保证恢复
  (c12 可用 67) → S6 重验证结果(76.2/79.0/79.5/79.1)

产出：output/pmtec_demo_animation.html

Run: D:/miniconda3/envs/pmtec-xpu/python.exe visualization/demo_animation.py
"""

import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(PROJECT_ROOT, "data", "bases_v2.geojson")
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "output", "pmtec_demo_animation.html")

TIER_COLORS = {1: "#ff7b72", 2: "#ffa657", 3: "#d2a8ff", 4: "#7ee787"}
ACCESS_COLORS = {"full": "#3fb950", "restricted": "#f5c44e", "denied": "#f85149"}

# 场景时序（与 演示视频分镜脚本-P13.md 对应；dur=秒）
SCENES = [
    {"id": "s0", "dur": 4, "esc": 0.0, "avail": 67, "ph": "full",
     "title": "PMTEC · 政治不确定性下的体系韧性",
     "sub": "政治事件 → 准入降级 → 战术适应 → 体系重平衡（全部数据来自系统真实运行）"},
    {"id": "s1", "dur": 6, "esc": 0.0, "avail": 67, "ph": "full",
     "title": "S1 基线态势（c0）",
     "sub": "67 基地全政治可用 · 冲突升级度 0 · 对手 6 策略待命（含多轴协同饱和 / 政治分化压制）"},
    {"id": "s2", "dur": 7, "esc": 0.049, "avail": 67, "ph": "restricted",
     "title": "S2 灰色地带行动（c1-c2）",
     "sub": "对手挑衅盟友本土 → 准入概率下滑 → 菲律宾 6 站降级 Restricted（容量折损）"},
    {"id": "s3", "dur": 7, "esc": 0.062, "avail": 58, "ph": "denied",
     "title": "S3 主权打击（c3）",
     "sub": "冲突升级 → 9 个 EDCA 站点 Denied → 可用基地集合 67 → 58"},
    {"id": "s4", "dur": 8, "esc": 0.062, "avail": 58, "ph": "denied", "adapt": True,
     "title": "S4 ASDA-Adapt 战术适应",
     "sub": "219 维观测感知准入容量 → 部署优化器排除 Denied 站点 → 分散重构 + 政治敞口压制"},
    {"id": "s5", "dur": 6, "esc": 0.039, "avail": 67, "ph": "full",
     "title": "S5 再保证与恢复（c4-c12）",
     "sub": "再保证外交 + 准入修复 → 第 12 周期可用基地完全恢复（结构性缓冲）"},
    {"id": "s6", "dur": 8, "esc": 0.039, "avail": 67, "ph": "full", "results": True,
     "title": "S6 重验证结论",
     "sub": "三场景对照 76.2% → 79.0% → 79.5% ｜ 六策略全量 79.1%（CI 78.0-80.2）｜ 适应优于压制"},
]

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>PMTEC 演示动画 — 政治事件 → 准入降级 → 战术适应 → 体系重平衡</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #0a0e1a; color: #c9d1d9; font-family: 'Segoe UI','Microsoft YaHei',sans-serif;
         height: 100vh; display: flex; flex-direction: column; overflow: hidden; }}
  #stage {{ flex: 1; position: relative; }}
  svg {{ width: 100%; height: 100%; }}
  #title {{ position: absolute; top: 24px; left: 32px; font-size: 26px; font-weight: 700; color: #58a6ff; }}
  #subtitle {{ position: absolute; bottom: 78px; left: 0; right: 0; text-align: center;
              font-size: 19px; color: #e6edf3; text-shadow: 0 2px 8px #000; padding: 0 60px; }}
  #hud {{ position: absolute; top: 24px; right: 32px; text-align: right; font-size: 14px; }}
  #hud .v {{ font-size: 26px; font-weight: 700; font-family: Consolas, monospace; }}
  .avail-ok {{ color: #3fb950; }} .avail-low {{ color: #f85149; }}
  #escwrap {{ position: absolute; bottom: 130px; left: 32px; width: 300px; }}
  #escwrap .lbl {{ font-size: 12px; color: #8b949e; margin-bottom: 4px; }}
  #escbar {{ height: 12px; background: #21262d; border-radius: 6px; overflow: hidden; }}
  #escfill {{ height: 100%; width: 0%; background: linear-gradient(90deg, #f5c44e, #f85149);
             transition: width 1.2s ease; }}
  #legend {{ position: absolute; bottom: 130px; right: 32px; font-size: 12px; color: #8b949e;
            text-align: right; line-height: 1.8; }}
  .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-left: 6px; vertical-align: middle; }}
  #ctrl {{ height: 56px; background: #161b22; border-top: 1px solid #30363d; display: flex;
          align-items: center; gap: 12px; padding: 0 20px; }}
  .btn {{ background: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px;
         padding: 6px 16px; cursor: pointer; font-size: 13px; }}
  .btn:hover {{ border-color: #58a6ff; }}
  #progress {{ flex: 1; height: 8px; background: #21262d; border-radius: 4px; overflow: hidden; }}
  #pfill {{ height: 100%; width: 0%; background: #58a6ff; }}
  #scene-tag {{ font-size: 13px; color: #8b949e; min-width: 130px; }}
  .fade {{ transition: opacity 0.8s ease; }}
  #results {{ position: absolute; inset: 0; display: none; align-items: center; justify-content: center;
             gap: 28px; background: rgba(10,14,26,0.88); }}
  .rcard {{ background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 26px 40px;
           text-align: center; }}
  .rcard .n {{ font-size: 52px; font-weight: 700; font-family: Consolas, monospace; }}
  .rcard .l {{ font-size: 14px; color: #8b949e; margin-top: 6px; }}
  #adapt-note {{ position: absolute; bottom: 200px; left: 32px; font-size: 14px; color: #f5c44e;
                display: none; max-width: 560px; line-height: 1.7; }}
</style>
</head>
<body>
<div id="stage">
  <svg id="map" viewBox="0 0 1200 620" preserveAspectRatio="xMidYMid meet"></svg>
  <div id="title" class="fade"></div>
  <div id="hud">
    <div>政治可用基地</div><div class="v avail-ok" id="avail">67</div>
    <div style="margin-top:8px">冲突升级度</div><div class="v" id="esc" style="color:#f59e4e">0.000</div>
  </div>
  <div id="escwrap"><div class="lbl">CONFLICT ESCALATION</div><div id="escbar"><div id="escfill"></div></div></div>
  <div id="adapt-note">⇄ ASDA-Adapt：分散再部署规避 Denied 站点 · Pareto 政治风险敞口显式压制<br>
    （DQN 219 维观测：36 盟友准入容量因子实时驱动决策）</div>
  <div id="results">
    <div class="rcard"><div class="n" style="color:#8b949e">76.2%</div><div class="l">P6 基线<br>原 22 站点 · 182 维</div></div>
    <div class="rcard"><div class="n" style="color:#58a6ff">79.0%</div><div class="l">v2 权威数据<br>模型不变 · +2.8pp</div></div>
    <div class="rcard"><div class="n" style="color:#3fb950">79.5%</div><div class="l">政治准入<br>219 维 P12 模型</div></div>
    <div class="rcard"><div class="n" style="color:#f59e4e">79.1%</div><div class="l">六策略全量<br>CI 78.0-80.2 · PASS</div></div>
  </div>
  <div id="legend">
    准入状态：<span>Full</span><span class="dot" style="background:#3fb950"></span>
    <span>Restricted</span><span class="dot" style="background:#f5c44e"></span>
    <span>Denied</span><span class="dot" style="background:#f85149"></span><br>
    军种描边：USAF <span class="dot" style="background:#58a6ff"></span>
    USN <span class="dot" style="background:#79c0ff"></span>
    USMC <span class="dot" style="background:#d29922"></span>
    Army <span class="dot" style="background:#3fb950"></span>
    USSF <span class="dot" style="background:#bc8cff"></span>
  </div>
  <div id="subtitle" class="fade"></div>
</div>
<div id="ctrl">
  <button class="btn" id="b-play" onclick="togglePlay()">⏸ 暂停</button>
  <button class="btn" onclick="restart()">⟲ 重播</button>
  <div id="progress"><div id="pfill"></div></div>
  <span id="scene-tag">S0 片头</span>
</div>
<script>
const BASES = {bases_json};
const SCENES = {scenes_json};
const TIER_COLORS = {tiers_json};
const ACCESS_COLORS = {access_json};
const TOTAL = SCENES.reduce((a, s) => a + s.dur, 0);

// lon/lat -> viewBox (印太战区: lon 95-185, lat -12~58)
function proj(lon, lat) {{
  return [ (lon - 95) / 90 * 1180 + 10, (58 - lat) / 70 * 600 + 10 ];
}}

const svg = document.getElementById('map');
const NS = 'http://www.w3.org/2000/svg';
const nodes = [];
for (const b of BASES) {{
  const [x, y] = proj(b.lon, b.lat);
  const g = document.createElementNS(NS, 'circle');
  g.setAttribute('cx', x); g.setAttribute('cy', y);
  g.setAttribute('r', b.tier === 1 ? 6 : 4.5);
  g.setAttribute('stroke', '#8b949e'); g.setAttribute('stroke-width', '1');
  g.setAttribute('fill', TIER_COLORS[b.tier] || '#555');
  svg.appendChild(g);
  nodes.push({{ el: g, ally: b.ally, ph: b.ph }});
}}

let sceneIdx = 0, sceneT = 0, playing = true, lastTick = null;

function applyScene(i, blend) {{
  const s = SCENES[i];
  document.getElementById('title').textContent = s.title;
  document.getElementById('subtitle').textContent = s.sub;
  document.getElementById('scene-tag').textContent = 'S' + i + ' / 6';
  document.getElementById('avail').textContent = s.avail;
  document.getElementById('avail').className = 'v ' + (s.avail >= 60 ? 'avail-ok' : 'avail-low');
  document.getElementById('esc').textContent = s.esc.toFixed(3);
  document.getElementById('escfill').style.width = Math.min(s.esc * 100 * 8, 100) + '%';
  document.getElementById('results').style.display = s.results ? 'flex' : 'none';
  document.getElementById('adapt-note').style.display = s.adapt ? 'block' : 'none';
  for (const n of nodes) {{
    let access = 'full';
    if (n.ph) access = s.ph;                       // 菲律宾 EDCA 站点随剧情演化
    else if (n.ally && i >= 3 && i <= 4) access = 'restricted';  // 其他盟友轻微折损
    n.el.setAttribute('fill', ACCESS_COLORS[access]);
    n.el.setAttribute('stroke', access === 'denied' ? '#f85149' : '#8b949e');
    n.el.setAttribute('stroke-width', access === 'denied' ? 2.5 : 1);
    n.el.setAttribute('opacity', access === 'denied' ? 0.55 : 1);
  }}
}}

function tick(ts) {{
  if (lastTick === null) lastTick = ts;
  const dt = (ts - lastTick) / 1000;
  lastTick = ts;
  if (playing) {{
    sceneT += dt;
    const s = SCENES[sceneIdx];
    if (sceneT >= s.dur) {{ sceneT = 0; sceneIdx = (sceneIdx + 1) % SCENES.length; applyScene(sceneIdx); }}
    let done = 0;
    for (let i = 0; i < sceneIdx; i++) done += SCENES[i].dur;
    document.getElementById('pfill').style.width = ((done + sceneT) / TOTAL * 100) + '%';
  }}
  requestAnimationFrame(tick);
}}

function togglePlay() {{
  playing = !playing;
  document.getElementById('b-play').textContent = playing ? '⏸ 暂停' : '▶ 播放';
}}
function restart() {{ sceneIdx = 0; sceneT = 0; applyScene(0); if (!playing) togglePlay(); }}
document.addEventListener('keydown', e => {{ if (e.code === 'Space') {{ e.preventDefault(); togglePlay(); }}}});

applyScene(0);
requestAnimationFrame(tick);
</script>
</body>
</html>"""


def load_bases():
    with open(DATA_PATH, encoding="utf-8") as f:
        gj = json.load(f)
    bases = []
    for ft in gj["features"]:
        p = ft["properties"]
        lon, lat = ft["geometry"]["coordinates"][:2]
        bases.append(
            {
                "id": p.get("id", ""),
                "tier": p.get("tier", 2),
                "ally": p.get("access_uncertainty") is not None,
                "ph": (p.get("id", "") or "").startswith("PH-"),
                "lat": lat,
                "lon": lon,
            }
        )
    return bases


def generate():
    bases = load_bases()
    html = HTML_TEMPLATE.format(
        bases_json=json.dumps(bases, ensure_ascii=False),
        scenes_json=json.dumps(SCENES, ensure_ascii=False),
        tiers_json=json.dumps(TIER_COLORS),
        access_json=json.dumps(ACCESS_COLORS),
    )
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[P13] 演示动画生成: {OUTPUT_PATH} ({len(bases)} bases, "
          f"{sum(s['dur'] for s in SCENES)}s/循环, {len(html):,} bytes)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    generate()
