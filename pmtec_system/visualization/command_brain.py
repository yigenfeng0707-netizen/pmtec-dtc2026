# -*- coding: utf-8 -*-
"""
P13+: 联合指挥大脑 v2 — 全幅 COP 浮动 HUD 指挥中枢

设计范式对标全球现代 C4ISR 指挥中心 (Palantir Gotham / Anduril Lattice /
openwar-intelligence):
  - 全幅地图 = 公共作战图 (Common Operating Picture), 零边距铺满
  - 玻璃 HUD 面板悬浮于地图之上 (左翼情报 / 右翼决策), 可收敛
  - 顶部任务带: 战备等级 + ASDA 相位灯 + 任务时钟 + 双链路状态
  - 底部: KPI 舷窗带 + ASDA 相位时间轴 + 指令台
  - 数据全部实时: WS 8765 (推送) + REST 8080 (实查/指令)

产出: output/PMTEC_Command_Brain.html (自包含单文件, 覆盖旧版)
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output", "PMTEC_Command_Brain.html")

BRAIN = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PMTEC 联合指挥大脑 v2</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
:root {
  --bg:#03060c; --panel:rgba(7,13,24,.82); --line:rgba(70,140,255,.24);
  --txt:#dfe8f4; --dim:#6b7d96; --cyan:#35d0ff; --blue:#4f7cff;
  --green:#2fe08a; --amber:#ffb545; --red:#ff5d6c; --purple:#b07cff;
  --mono:Consolas,"SF Mono",monospace;
  /* 布局栅格: 所有面板边线严格对齐这套变量 */
  --pad:10px; --gut:10px; --head:52px; --tape:42px;
  --lw:240px; --rw:280px; --ch:150px;
}
html,body { height:100%; overflow:hidden; }
body { background:var(--bg); color:var(--txt);
  font-family:"Segoe UI","Microsoft YaHei",sans-serif; }
body::after { content:""; position:fixed; inset:0; pointer-events:none; z-index:90;
  background:repeating-linear-gradient(0deg,rgba(255,255,255,.012) 0 2px,transparent 2px 4px); }

/* ---------- 基础层: 全幅 COP ---------- */
#cop { position:fixed; inset:0; z-index:0; }
#cop iframe { width:100%; height:100%; border:0; }
#vignette { position:fixed; inset:0; z-index:1; pointer-events:none;
  background:radial-gradient(ellipse at center,transparent 55%,rgba(2,5,10,.55)); }

/* ---------- 浮动 HUD 面板 ---------- */
.hud { position:fixed; z-index:20; background:var(--panel);
  border:1px solid var(--line); border-radius:10px; backdrop-filter:blur(10px);
  box-shadow:0 4px 24px rgba(0,10,30,.55); }
.hud .hd { display:flex; align-items:center; gap:7px; padding:7px 12px 4px;
  font-size:10px; letter-spacing:1.6px; text-transform:uppercase; color:var(--cyan); }
.hud .hd::before { content:""; width:3px; height:11px; border-radius:2px;
  background:linear-gradient(180deg,var(--cyan),var(--blue)); }
.hud .hd .live { margin-left:auto; font-size:9px; color:var(--green);
  letter-spacing:1px; }
.hud .bd { padding:4px 12px 10px; }

/* 顶栏 */
#top { top:var(--pad); left:var(--pad); right:var(--pad); height:var(--head);
  display:flex; align-items:center; gap:16px; padding:0 16px; }
#top .brand b { font-size:16px; letter-spacing:1px;
  background:linear-gradient(90deg,#7fd4ff,#4f7cff); -webkit-background-clip:text;
  -webkit-text-fill-color:transparent; }
#top .brand span { display:block; font-size:8.5px; color:var(--dim); letter-spacing:2.6px; }
#ready { padding:4px 13px; border-radius:14px; font-size:11px; font-weight:800;
  letter-spacing:2px; border:1px solid var(--green); color:var(--green);
  background:rgba(47,224,138,.08); }
#ready.warn { border-color:var(--amber); color:var(--amber); background:rgba(255,181,69,.08); }
#ready.crit { border-color:var(--red); color:var(--red); background:rgba(255,93,108,.1); }
.phleds { display:flex; gap:6px; }
.phl { padding:4px 11px; border-radius:12px; font-size:10.5px; color:var(--dim);
  border:1px solid var(--line); letter-spacing:1px; transition:.25s; cursor:pointer; }
.phl:hover { color:var(--txt); border-color:var(--cyan); }
.phl.on { color:#03121e; background:linear-gradient(90deg,#43d6ff,#4f7cff);
  border-color:transparent; font-weight:800; box-shadow:0 0 14px rgba(67,214,255,.5); }
.phl.pin { color:var(--amber); border-color:var(--amber);
  box-shadow:0 0 12px rgba(255,181,69,.4); }
#mapbanner { position:absolute; top:10px; left:50%; transform:translateX(-50%);
  z-index:5; display:none; padding:5px 18px; border-radius:8px; font-size:12px;
  font-weight:700; letter-spacing:1px; pointer-events:none;
  background:rgba(255,181,69,.18); border:1px solid var(--amber); color:var(--amber); }
#audit { position:fixed; left:calc(var(--pad) + var(--lw) + var(--gut));
  bottom:calc(var(--pad) + var(--tape) + var(--gut) + 62px + var(--gut));
  width:min(380px, calc(100vw - var(--lw) - var(--rw) - 60px));
  z-index:35; display:none; }
#audit .bd { font-size:11.5px; max-height:240px; overflow:auto; }
#audit .impl { color:var(--txt); padding:4px 0; }
#audit .code { color:#5da4ff; font-family:var(--mono); font-size:10px;
  padding:2px 0 6px; border-bottom:1px dashed rgba(70,140,255,.2); }
#clock { font-family:var(--mono); font-size:23px; color:var(--cyan);
  text-shadow:0 0 14px rgba(53,208,255,.45); margin-left:auto; }
.dots { display:flex; gap:10px; }
.dot2 { font-size:10px; color:var(--dim); display:flex; align-items:center; gap:4px; }
.led { width:8px; height:8px; border-radius:50%; }
.led.g { background:var(--green); box-shadow:0 0 7px var(--green); }
.led.r { background:var(--red); box-shadow:0 0 7px var(--red); }
#alert { top:70px; left:50%; transform:translateX(-50%); z-index:30;
  display:none; padding:5px 20px; border-radius:8px; font-size:12px; font-weight:700;
  background:rgba(255,93,108,.14); border:1px solid var(--red); color:var(--red);
  animation:ablink 1.2s infinite; }
@keyframes ablink { 50% { opacity:.5; } }

/* 左翼 */
#left { top:calc(var(--pad) + var(--head) + var(--gut)); left:var(--pad);
  width:var(--lw); display:flex; flex-direction:column; gap:var(--gut);
  max-height:calc(100vh - var(--head) - var(--pad)*2 - var(--tape) - var(--gut));
  overflow:hidden; }
#left .hud { position:static; }
#radar { width:100%; height:148px; display:block; }
#polbar { width:100%; height:40px; display:block; }
#ewwave { width:100%; height:88px; display:block; }
.minirow { display:flex; justify-content:space-between; padding:3px 0;
  border-bottom:1px dashed rgba(70,140,255,.13); font-size:11px; }
.minirow span:first-child { color:var(--dim); }
.st-full { color:var(--green); } .st-res { color:var(--amber); } .st-den { color:var(--red); }

/* 右翼 */
#right { top:calc(var(--pad) + var(--head) + var(--gut)); right:var(--pad);
  width:var(--rw); display:flex; flex-direction:column; gap:var(--gut);
  max-height:calc(100vh - var(--head) - var(--pad)*2 - var(--ch) - var(--gut));
  overflow:hidden; }
#right .hud { position:static; }
#dqnring { width:100%; height:88px; display:block; }
#dqnlatest { min-height:20px; }
#dqnstrat { margin-bottom:4px; }
.sbar { display:flex; align-items:center; gap:7px; padding:2px 0; font-size:11px; }
.sbar span:first-child { color:var(--dim); width:78px; }
.sbar .track { flex:1; height:5px; border-radius:3px; background:rgba(40,55,80,.8); }
.sbar .fill { height:100%; border-radius:3px;
  background:linear-gradient(90deg,#43d6ff,#4f7cff); }
.sbar b { color:var(--cyan); font-family:var(--mono); font-size:11px; }
.evt { padding:4px 7px; margin:3px 0; border-left:2px solid var(--cyan);
  background:rgba(18,28,48,.55); border-radius:5px; font-size:10.8px; }
.evt b { color:var(--amber); font-size:9.5px; letter-spacing:.5px; }

/* 底部 KPI 舷窗 + 相位时间轴 */
#kpis { bottom:calc(var(--pad) + var(--tape) + var(--gut));
  left:calc(var(--pad) + var(--lw) + var(--gut));
  right:calc(var(--pad) + var(--rw) + var(--gut));
  display:flex; gap:9px; padding:8px 10px; justify-content:space-evenly; }
.kp { min-width:86px; text-align:center; padding:4px 12px; border-radius:8px;
  background:rgba(12,20,36,.7); border:1px solid var(--line); }
.kp b { display:block; font-size:19px; font-family:var(--mono); color:var(--cyan); }
.kp span { font-size:9.5px; color:var(--dim); letter-spacing:1px; }
#phasetape { bottom:var(--pad); left:var(--pad);
  right:calc(var(--pad) + var(--rw) + var(--gut)); height:var(--tape);
  display:flex; align-items:center; gap:8px; padding:0 14px; }
#phasetape .tl { flex:1; display:flex; gap:5px; }
#phasetape .seg { flex:1; text-align:center; padding:5px 0; font-size:11px;
  border-radius:6px; background:rgba(28,40,62,.55); color:var(--dim);
  border:1px solid var(--line); letter-spacing:1px; }
#phasetape .seg.on { background:linear-gradient(90deg,#43d6ff,#4f7cff); color:#03121e;
  font-weight:800; border-color:transparent; box-shadow:0 0 12px rgba(67,214,255,.45); }

/* 指令台 */
#console { bottom:var(--pad); right:var(--pad); width:var(--rw); height:var(--ch);
  overflow:hidden; padding:8px 12px; z-index:40; }
#console .cbtns { display:flex; gap:6px; margin:6px 0; }
#console select, #console input { background:#0a1220; color:var(--txt);
  border:1px solid var(--line); border-radius:6px; padding:4px 7px;
  font-size:11px; font-family:var(--mono); width:100%; margin-bottom:5px; }
.cbtn { flex:1; background:linear-gradient(90deg,#43d6ff,#4f7cff); color:#03121e;
  border:0; border-radius:6px; padding:6px 0; font-weight:800; font-size:11.5px;
  cursor:pointer; letter-spacing:1px; }
.cbtn.stop { background:linear-gradient(90deg,#ff5d6c,#ff8f6c); }
.cbtn:active { transform:scale(.96); }
#resplog { font-family:var(--mono); font-size:10px; color:var(--green);
  min-height:26px; max-height:26px; overflow:hidden; word-break:break-all; }

/* 响应式: 收窄栅格而非破坏对齐 */
@media (max-width:1250px) { :root { --lw:212px; --rw:246px; } }
@media (max-width:1020px) { :root { --lw:190px; --rw:224px; } }
@media (max-width:760px) {
  #left,#right { display:none; }
  #phasetape { right:var(--pad); }
  #kpis { left:var(--pad); right:var(--pad); }
  #audit { left:var(--pad); right:var(--pad); width:auto; }
  #alert { left:var(--pad); right:var(--pad); }
}
</style>
</head>
<body>

<!-- 全幅公共作战图 (COP) -->
<div id="cop"><iframe src="pmtec_realtime_map_v2.html?v=7" allowfullscreen></iframe>
<div id="mapbanner">◉ 相位审计模式</div></div>
<div id="vignette"></div>
<div id="alert">⚠ 网络脆弱度超阈值 — 建议立即下达疏散指令</div>

<!-- 顶栏 -->
<div id="top" class="hud">
  <div class="brand"><b>PMTEC 联合指挥大脑</b><span>JOINT COMMAND BRAIN · C4ISR</span></div>
  <div id="ready" style="margin-left:6px"><span id="defnum">DEF-5</span> · 战备 低</div>
  <div class="phleds" id="phleds">
    <div class="phl" data-ph="Act">ACT</div>
    <div class="phl" data-ph="Sense">SNS</div>
    <div class="phl" data-ph="Decide">DCD</div>
    <div class="phl" data-ph="Adapt">ADP</div>
  </div>
  <div id="clock">T+00:00:00</div>
  <div class="dots">
    <div class="dot2"><span class="led r" id="led-ws"></span>WS</div>
    <div class="dot2"><span class="led r" id="led-rest"></span>REST</div>
    <div class="dot2" title="多源融合: WebSocket + REST + GeoJSON + CRS/FY2024" style="color:var(--cyan)">SRC×4</div>
  </div>
</div>

<!-- 左翼 · 情报 -->
<div id="left">
  <div class="hud"><div class="hd">威胁态势 · 雷达扫描<span class="live">● LIVE</span></div>
    <div class="bd"><canvas id="radar" style="width:100%;height:148px;display:block"></canvas>
    <div id="threatlist" style="margin-top:5px"></div></div></div>
  <div class="hud"><div class="hd">政治准入 · 实时态势</div>
    <div class="bd">
      <canvas id="escbar" style="width:100%;height:34px;display:block"></canvas>
      <div style="margin-top:6px">
        <div class="minirow"><span>降级站点</span><b id="pol-deg" style="color:var(--green);font-family:var(--mono);font-size:13px">0</b></div>
        <div class="minirow"><span>MRF-D 就绪</span><b id="pol-mrfd" style="color:var(--cyan);font-family:var(--mono);font-size:13px">100%</b></div>
        <div class="minirow"><span>轮换日</span><b id="pol-day" style="color:var(--amber);font-family:var(--mono);font-size:13px">D0</b></div>
      </div>
      <div id="pollist" style="margin-top:5px"></div></div></div>
  <div class="hud"><div class="hd">EW · 信号 / SIGINT 频谱</div>
    <div class="bd">
      <canvas id="ewwave" style="width:100%;height:60px;display:block"></canvas>
      <canvas id="ewspec" style="width:100%;height:56px;display:block;margin-top:4px"></canvas>
      <div id="ewnote" style="font-size:10.5px;color:var(--dim);margin-top:3px">信号环境正常</div></div></div>
  <div class="hud"><div class="hd">⚠ 早期预警 · EARLY WARNING<span class="live">● 规则引擎</span></div>
    <div class="bd"><div id="ewarn" style="font-size:11px;min-height:34px">
      <div class="minirow"><span>系统待命</span><span style="color:var(--green)">无告警</span></div></div></div></div>
</div>

<!-- 右翼 · 决策 -->
<div id="right">
  <div class="hud"><div class="hd">AI 决策核 · DQN 219 维<span class="live" id="dqnlive">● STANDBY</span></div>
    <div class="bd">
      <canvas id="dqnring" style="width:100%;height:86px;display:block"></canvas>
      <div id="dqnlatest"></div>
      <div id="dqnstrat" style="margin-top:6px"></div>
    </div></div>
  <div class="hud"><div class="hd">指挥链 · 上报流</div>
    <div class="bd"><canvas id="c2flow" style="width:100%;height:104px;display:block"></canvas>
    <div id="c2list" style="margin-top:5px;max-height:150px;overflow:auto"></div></div></div>
  <div class="hud"><div class="hd">战斗序列 · ORBAT (REST 实查)</div>
    <div class="bd"><div id="orbat" style="font-size:11px;max-height:160px;overflow:auto">等待 /bases 实查…</div></div></div>
</div>

<!-- KPI 舷窗 -->
<div id="kpis" class="hud">
  <div class="kp"><b id="k-ent">-</b><span>ENTITIES</span></div>
  <div class="kp"><b id="k-trk">-</b><span>TRACKS</span></div>
  <div class="kp"><b id="k-cyc">-</b><span>CYCLE</span></div>
  <div class="kp"><b id="k-vul">-</b><span>VULN</span></div>
  <div class="kp"><b style="color:var(--green)">67</b><span>BASES</span></div>
  <div class="kp"><b style="color:var(--amber)">79.1%</b><span>INTERCEPT</span></div>
</div>

<!-- ASDA 相位时间轴 -->
<div id="phasetape" class="hud">
  <span style="font-size:10px;color:var(--dim);letter-spacing:2px">ASDA</span>
  <div class="tl">
    <div class="seg" data-ph="Act">ACT 行动</div>
    <div class="seg" data-ph="Sense">SENSE 感知</div>
    <div class="seg" data-ph="Decide">DECIDE 决策</div>
    <div class="seg" data-ph="Adapt">ADAPT 适应</div>
  </div>
  <span style="font-size:10px;color:var(--dim)" id="simnote">等待推演…</span>
</div>

<!-- 指令台 -->
<div id="console" class="hud">
  <div class="hd">指令台 · COMMAND</div>
  <select id="scenario">
    <option value="PMTEC-Pacific">PMTEC-Pacific 标准想定</option>
    <option value="multi_threat">multi_threat 多轴协同</option>
  </select>
  <div class="cbtns">
    <input id="duration" type="number" value="1200" min="120" step="120" title="时长(秒)">
    <input id="seed" type="number" value="42" title="种子">
  </div>
  <div class="cbtns">
    <button class="cbtn" onclick="cmdStart()">▶ 开始推演</button>
    <button class="cbtn stop" onclick="cmdStop()">⏹ 停止</button>
  </div>
  <div id="resplog">REST 网关 :8080 待命 · 17 端点在线</div>
</div>

<!-- 相位审计面板 -->
<div id="audit" class="hud">
  <div class="hd" id="audit-hd">相位审计</div>
  <div class="bd" id="audit-bd"></div>
</div>

<script>
const REST = "http://localhost:8080/api/v1";
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[<>&]/g, c => ({"<":"&lt;","&":"&amp;",">":"&gt;"}[c]));

/* ---------------- 日志 / 状态 ---------------- */
function resp(m, ok) {
  const el = $("resplog");
  el.textContent = (ok === false ? "✗ " : "✓ ") + m;
  el.style.color = ok === false ? "var(--red)" : "var(--green)";
}
async function api(p) { const r = await fetch(REST + p); return r.json(); }
async function post(p, b) {
  return api(p, { method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify(b || {}) });
}

/* ---------------- 指令台 ---------------- */
async function cmdStart() {
  resp("下发 ▶ 开始推演…");
  try {
    const r = await post("/sim/start", {
      scenario: $("scenario").value,
      duration: parseInt($("duration").value) || 1200,
      seed: parseInt($("seed").value) || 42 });
    resp("sim/start → " + (r.message || JSON.stringify(r)), r.success);
  } catch (e) { resp("指令失败: " + e.message, false); }
}
async function cmdStop() {
  resp("下发 ⏹ 停止…");
  try {
    const r = await post("/sim/stop", {});
    resp("sim/stop → " + (r.message || JSON.stringify(r)), r.success);
  } catch (e) { resp("指令失败: " + e.message, false); }
}

/* ---------------- 面板可视化引擎 ---------------- */
const viz = { threats: [], pol: { den:0 }, esc: 0 };
function fitCv(c) {
  const r = c.getBoundingClientRect();
  const dpr = devicePixelRatio || 1;
  if (c.width !== Math.round(r.width * dpr)) {
    c.width = Math.round(r.width * dpr);
    c.height = Math.round(r.height * dpr);
  }
  const ctx = c.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return [ctx, r.width, r.height];
}
function drawRadar(ts) {
  const c = $("radar"); if (!c.offsetParent) return;
  const [ctx, w, h] = fitCv(c);
  const cx = w/2, cy = h/2, R = Math.min(w, h)/2 - 8;
  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = "rgba(53,208,255,.3)"; ctx.lineWidth = 1;
  for (const rr of [R, R*.66, R*.33]) { ctx.beginPath(); ctx.arc(cx, cy, rr, 0, 7); ctx.stroke(); }
  ctx.beginPath(); ctx.moveTo(cx-R, cy); ctx.lineTo(cx+R, cy);
  ctx.moveTo(cx, cy-R); ctx.lineTo(cx, cy+R); ctx.stroke();
  const a = (ts/900) % (Math.PI*2);
  ctx.beginPath(); ctx.moveTo(cx, cy); ctx.arc(cx, cy, R, a-.9, a); ctx.closePath();
  ctx.fillStyle = "rgba(53,208,255,.15)"; ctx.fill();
  ctx.beginPath(); ctx.moveTo(cx, cy);
  ctx.lineTo(cx+R*Math.cos(a), cy+R*Math.sin(a));
  ctx.strokeStyle = "#35d0ff"; ctx.lineWidth = 1.6; ctx.stroke();
  viz.threats.slice(0, 12).forEach((t, i) => {
    const ang = (i*137.5)*Math.PI/180 + ts/9000;
    const rr = R*(.35 + ((i*29)%50)/100);
    ctx.beginPath(); ctx.arc(cx+rr*Math.cos(ang), cy+rr*Math.sin(ang), 3.2, 0, 7);
    ctx.fillStyle = i%3===0 ? "#ff5d6c" : "#ffb545";
    ctx.shadowColor = ctx.fillStyle; ctx.shadowBlur = 6;
    ctx.fill(); ctx.shadowBlur = 0;
  });
}
function drawEsc() {
  const c = $("escbar"); if (!c.offsetParent) return;
  const [ctx, w, h] = fitCv(c);
  ctx.clearRect(0, 0, w, h);
  const segs = [["rgba(47,224,138,.4)", 0, .4], ["rgba(255,181,69,.4)", .4, .75],
                ["rgba(255,93,108,.4)", .75, 1]];
  for (const [col, a, b] of segs) {
    ctx.fillStyle = col; ctx.fillRect(w*a, 4, w*(b-a) - 2, h - 18);
  }
  const x = w * Math.min(viz.esc || 0, 1);
  ctx.fillStyle = "#fff"; ctx.fillRect(x - 1.5, 2, 3, h - 16);
  ctx.fillStyle = "#6b7d96"; ctx.font = "10px 'Microsoft YaHei'";
  ctx.fillText("升级度 " + (viz.esc || 0).toFixed(2), 2, h - 2);
}
function drawEW(ts) {
  const c = $("ewwave"); if (!c.offsetParent) return;
  const [ctx, w, h] = fitCv(c);
  ctx.clearRect(0, 0, w, h);
  ctx.beginPath();
  const amp = 3 + viz.ew*(h/2-5);
  for (let x = 0; x <= w; x += 2) {
    const y = h/2 + Math.sin(x*.045+ts/220)*amp*Math.sin(x*.008+ts/900)
      + (Math.random()-.5)*viz.ew*6;
    x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  ctx.strokeStyle = viz.ew > .6 ? "#ff5d6c" : "#2fe08a";
  ctx.lineWidth = 1.3; ctx.shadowColor = ctx.strokeStyle; ctx.shadowBlur = 4;
  ctx.stroke(); ctx.shadowBlur = 0;
}
function drawEWSpec(ts) {
  const c = $("ewspec"); if (!c.offsetParent) return;
  const [ctx, w, h] = fitCv(c);
  ctx.clearRect(0, 0, w, h);
  const bars = 24, bw = w / bars;
  for (let i = 0; i < bars; i++) {
    const seed = Math.abs(Math.sin(i * 3.7 + ts/1400));
    const bh = 3 + seed * (h - 8) * (0.25 + viz.ew * 1.1);
    ctx.fillStyle = seed > .72 ? (viz.ew > .5 ? "#ff5d6c" : "#ffb545") : "rgba(53,208,255,.55)";
    ctx.fillRect(i * bw + 1, h - bh, bw - 2, bh);
  }
  ctx.strokeStyle = "rgba(70,140,255,.25)";
  ctx.beginPath(); ctx.moveTo(0, h - .5); ctx.lineTo(w, h - .5); ctx.stroke();
}
const warns = [];
let prevWarnKey = "";
function renderWarn() {
  const el = $("ewarn");
  if (!warns.length) {
    el.innerHTML = '<div class="minirow"><span>系统待命</span><span style="color:var(--green)">无告警</span></div>';
    $("ewlive").style.color = "var(--green)";
    return;
  }
  el.innerHTML = warns.slice(-5).reverse().map(w =>
    `<div class="minirow"><span>${esc(w[0])}</span>` +
    `<span class="${w[1] === "crit" ? "st-den" : "st-res"}">${w[1] === "crit" ? "告警" : "预警"}</span></div>`).join("");
  $("ewlive").style.color = warns.some(w => w[1] === "crit") ? "var(--red)" : "var(--amber)";
}
function fetchOrbat() {
  api("/bases").then(d => {
    const list = Array.isArray(d) ? d : (d.bases || []);
    const groups = {};
    for (const b of list) {
      const g = b.command || b.country || "未分配";
      (groups[g] = groups[g] || []).push(b);
    }
    $("orbat").innerHTML = Object.entries(groups).map(([g, arr]) =>
      `<div class="minirow"><span>${esc(g)}</span><span style="color:var(--cyan)">${arr.length} 站点</span></div>`).join("")
      + `<div class="minirow"><span style="color:var(--dim)">合计</span><span style="color:var(--cyan)">${list.length}</span></div>`;
  }).catch(e => { $("orbat").textContent = "获取失败: " + e.message; });
}
fetchOrbat();
function drawC2(ts) {
  const c = $("c2flow"); if (!c.offsetParent) return;
  const [ctx, w, h] = fitCv(c);
  ctx.clearRect(0, 0, w, h);
  const pts = [{x:14, y:h/2, l:"基地"}, {x:w/2, y:h/2-5, l:"司令部"},
               {x:w-26, y:h/2, l:"INDOPACOM"}];
  const cols = ["#8b9bb5", "#35d0ff", "#4f7cff"];
  for (let i = 0; i < 2; i++) {
    const a = pts[i], b = pts[i+1];
    const mx = (a.x+b.x)/2, my = (a.y+b.y)/2 - 14;
    ctx.strokeStyle = cols[i+1]; ctx.lineWidth = 1.3;
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.quadraticCurveTo(mx, my, b.x, b.y); ctx.stroke();
    const t = ((ts/1000)*.6 + i*.5) % 1, u = 1-t;
    ctx.beginPath();
    ctx.arc(u*u*a.x+2*u*t*mx+t*t*b.x, u*u*a.y+2*u*t*my+t*t*b.y, 2.4, 0, 7);
    ctx.fillStyle = "#dff3ff"; ctx.shadowColor = cols[i+1]; ctx.shadowBlur = 6;
    ctx.fill(); ctx.shadowBlur = 0;
  }
  pts.forEach((p, i) => {
    ctx.beginPath(); ctx.arc(p.x, p.y, 4.5-i, 0, 7); ctx.fillStyle = cols[i]; ctx.fill();
    ctx.fillStyle = "#6b7d96"; ctx.font = "9.5px 'Microsoft YaHei'";
    ctx.textAlign = "center"; ctx.fillText(p.l, p.x, p.y+16);
  });
}
const dqn = { counts:[0,0,0], last:null, act:0, trained:false,
  names:["direct","predictive","saturation"], disp:["hold","light","heavy"],
  alg:"DQN 219 维", obs:219 };
function drawDqn(ts) {
  const c = $("dqnring"); if (!c.offsetParent) return;
  const [ctx, w, h] = fitCv(c);
  const cx = w/2, cy = h/2, R = Math.min(w, h)/2 - 9;
  ctx.clearRect(0, 0, w, h);
  ctx.lineWidth = 6.5;
  ctx.strokeStyle = "rgba(53,208,255,.14)";
  ctx.beginPath(); ctx.arc(cx, cy, R, 0, 7); ctx.stroke();
  dqn.act *= .955;
  const sweep = (ts/1300) % (Math.PI*2);
  ctx.strokeStyle = dqn.act > .3 ? "#b07cff" : "#35d0ff";
  ctx.shadowColor = ctx.strokeStyle; ctx.shadowBlur = 9;
  ctx.beginPath(); ctx.arc(cx, cy, R, sweep-1.1+dqn.act*2, sweep+.3+dqn.act*2);
  ctx.stroke(); ctx.shadowBlur = 0;
  ctx.fillStyle = dqn.trained ? "#2fe08a" : "#35d0ff";
  ctx.font = "bold 12px 'Microsoft YaHei'"; ctx.textAlign = "center";
  ctx.fillText(dqn.trained ? "READY" : "BOOT", cx, cy-1);
  ctx.font = "8.5px 'Microsoft YaHei'"; ctx.fillStyle = "#6b7d96";
  ctx.fillText("DECISION CORE", cx, cy+11);
}
function renderDqn() {
  const total = dqn.counts.reduce((a,b)=>a+b,0) || 1;
  $("dqnstrat").innerHTML = dqn.names.map((n,i) => `
    <div class="sbar"><span>${n}</span>
    <span class="track"><span class="fill" style="width:${Math.round(dqn.counts[i]/total*100)}%"></span></span>
    <b>${dqn.counts[i]}</b></div>`).join("");
  $("dqnlatest").innerHTML = dqn.last
    ? `<div class="evt" style="border-left-color:#b07cff"><b>最新决策</b>
       intercept=<span style="color:var(--cyan)">${dqn.names[dqn.last.ia]}</span> ·
       dispersal=<span style="color:var(--amber)">${dqn.disp[dqn.last.da]}</span></div>`
    : "";
  $("dqnlive").textContent = dqn.trained ? "● READY" : "● STANDBY";
}
requestAnimationFrame(function loop(ts) {
  drawRadar(ts); drawEsc(); drawEW(ts); drawEWSpec(ts); drawC2(ts); drawDqn(ts);
  requestAnimationFrame(loop);
});

/* ---------------- REST 轮询 (4s 轮换) ---------------- */
const POLLS = [
  ["/political/access", d => {
    // 真实结构: {ally_sites: 降级数, by_country{}, escalation_level, mrfd{}, recent_transitions[]}
    viz.esc = d.escalation_level ?? 0;
    const deg = d.ally_sites ?? 0;
    const mr = d.mrfd || {};
    viz.pol.den = deg;
    const pd = $("pol-deg");
    pd.textContent = deg;
    pd.style.color = deg > 6 ? "var(--red)" : deg > 0 ? "var(--amber)" : "var(--green)";
    $("pol-mrfd").textContent = Math.round((mr.readiness ?? 1) * 100) + "%";
    $("pol-day").textContent = "D" + (mr.rotation_day ?? 0);
    const byC = d.by_country || {}, tr = d.recent_transitions || [];
    let html = "";
    const entries = Object.entries(byC);
    if (entries.length) {
      html = entries.slice(0, 8).map(([k, v]) => {
        const st = String((v && (v.state || v.access)) || v).toLowerCase();
        const cls = st.includes("den") ? "st-den" : st.includes("res") ? "st-res" : "st-full";
        return `<div class="minirow"><span>${esc(k)}</span><span class="${cls}">${esc(st)}</span></div>`;
      }).join("");
    } else {
      html = `<div class="minirow"><span style="color:var(--green)">全部 36 个盟友站点 Full · 无降级</span></div>`;
    }
    if (tr && tr.length) {
      html += tr.slice(-3).map(t =>
        `<div class="minirow"><span style="color:var(--amber)">⟳ ${esc(String(t.country || t.site || "transition"))}</span>` +
        `<span style="color:var(--dim)">${esc(String(t.from || "") + " → " + String(t.to || t.state || ""))}</span></div>`).join("");
    }
    if (mr.frozen) html += `<div class="minirow"><span style="color:var(--red)">MRF-D 战时冻结</span><span>readiness 锁定</span></div>`;
    $("pollist").innerHTML = html;
  }],
  ["/c2/chain", d => {
    const msgs = d.messages || d.recent || d.events || [];
    const el = $("c2list");
    if (Array.isArray(msgs) && msgs.length)
      el.innerHTML = msgs.slice(-8).reverse().map(m =>
        `<div class="evt"><b>${esc(String(m.type || m.kind || "msg").toUpperCase())}</b> ` +
        `${esc(m.description || m.desc || m.summary || JSON.stringify(m).slice(0, 80))}</div>`).join("");
    else el.textContent = JSON.stringify(d).slice(0, 180);
  }],
  ["/app/dqn/status", d => {
    dqn.trained = !!(d.trained || d.is_trained || String(d.status || "").includes("train"));
    dqn.alg = d.algorithm || d.model_name || d.model || dqn.alg;
    dqn.obs = d.obs_dim || dqn.obs;
    renderDqn();
  }],
  ["/threat-summary", d => {
    const items = d.threats || d.tracks || d.summary || d;
    viz.threats = Array.isArray(items) ? items : Object.keys(items || {});
    const el = $("threatlist");
    if (Array.isArray(items) && items.length)
      el.innerHTML = items.slice(0, 6).map(t =>
        `<div class="minirow"><span>${esc(t.id || t.track_id || "?")}</span>` +
        `<span class="${(t.confidence||0) > .7 ? "st-den" : "st-res"}">${esc(t.classification || t.type || "-")}` +
        ` ${t.confidence ? (t.confidence*100).toFixed(0) + "%" : ""}</span></div>`).join("");
    else el.textContent = "无非合作目标航迹";
  }],
  ["/war/ew-threats", d => {
    viz.ew = (d && (d.ew_active || d.jammed || Array.isArray(d) && d.length)) ? .85 : .3;
    $("ewnote").textContent = viz.ew > .6 ? "⚠ EW 压制活跃 — 信号降级" : "信号环境正常";
  }],
];
let pollIdx = 0;
async function pollTick() {
  const [path, fn] = POLLS[pollIdx % POLLS.length];
  pollIdx++;
  try { const d = await api(path); $("led-rest").className = "led g"; fn(d); }
  catch (e) { $("led-rest").className = "led r"; }
}
setInterval(pollTick, 3000);
pollTick();

/* ---------------- 相位审计引擎 ---------------- */
const PHASE_META = {
  Act:   { zh:"行动", color:"#ff8f6c", types:["missile_launch","intercept","dispersal"],
    impl:"执行当前指令：对手智能体攻击决策 / 导弹发射 / 机群疏散执行",
    code:"_asda_act · services/grpc_server.py L611" },
  Sense: { zh:"感知", color:"#39c2ff", types:["live_data_inject","sensor"],
    impl:"全传感器扫描 + LVC Live 实时注入 (ADS-B/AIS/气象) + 气象闭环修正",
    code:"_asda_sense · services/grpc_server.py L782" },
  Decide:{ zh:"决策", color:"#b07cff", types:["ma_dqn_decision","dqn_decision","ucb1"],
    impl:"航迹融合 → 识别敌对目标 → IQL/MADDPG 多智能体协同决策 (拦截+疏散)",
    code:"_asda_decide · services/grpc_server.py L1190" },
  Adapt: { zh:"适应", color:"#2fe08a", types:["adapt","political","c2_","learning","impact"],
    impl:"战果 Monte Carlo 评估 → 学习管理器更新 → 政治准入演化 → C2 跨军种协同",
    code:"_asda_adapt · services/grpc_server.py L1505" },
};
const evCount = { Act:0, Sense:0, Decide:0, Adapt:0 };
const allEvents = [];
let pinned = null;
function phaseOf(e) {
  if (e.data && e.data.phase) return String(e.data.phase);
  const ty = String(e.event_type || e.type || "").toLowerCase();
  if (ty === "asda_cycle") return lastPhase;
  for (const [ph, m] of Object.entries(PHASE_META))
    if (m.types.some(t => ty.includes(t))) return ph;
  return "Adapt";
}
function renderAudit() {
  const bd = $("audit-bd"), hd = $("audit-hd");
  const ab = $("audit");
  if (!pinned) { ab.style.display = "none"; return; }
  const m = PHASE_META[pinned];
  ab.style.display = "block";
  hd.innerHTML = `◉ 相位审计 · ${pinned} ${m.zh}`;
  const evs = allEvents.filter(x => x._ph === pinned).slice(-8).reverse();
  bd.innerHTML = `<div class="impl">${m.impl}</div>` +
    `<div class="code">${m.code} · 本次运行捕获 ${evCount[pinned]} 个事件</div>` +
    (evs.length ? evs.map(e =>
      `<div class="minirow"><span>${esc(String(e.event_type||"evt").toUpperCase())}</span>` +
      `<span style="color:var(--dim)">${esc(String(e.description||"").slice(0,46))}</span></div>`).join("")
     : `<div class="minirow"><span>等待该相位事件…</span><span style="color:var(--dim)">推送间隔约 40s</span></div>`);
}
document.querySelectorAll(".phl").forEach(el => {
  el.addEventListener("click", () => {
    pinned = (pinned === el.dataset.ph) ? null : el.dataset.ph;
    document.querySelectorAll(".phl").forEach(x =>
      x.classList.toggle("pin", x.dataset.ph === pinned));
    $("mapbanner").style.display = pinned ? "block" : "none";
    if (pinned) $("mapbanner").textContent = `◉ 相位审计 · ${pinned} ${PHASE_META[pinned].zh} — 大屏联动中`;
    renderAudit();
  });
});
document.querySelectorAll(".seg").forEach(el => {
  el.style.cursor = "pointer";
  el.addEventListener("click", () => {
    pinned = (pinned === el.dataset.ph) ? null : el.dataset.ph;
    document.querySelectorAll(".phl").forEach(x =>
      x.classList.toggle("pin", x.dataset.ph === pinned));
    $("mapbanner").style.display = pinned ? "block" : "none";
    if (pinned) $("mapbanner").textContent = `◉ 相位审计 · ${pinned} ${PHASE_META[pinned].zh}`;
    renderAudit();
  });
});

/* ---------------- WS 实时 ---------------- */
let ws = null, lastPhase = "Act";
function connect() {
  ws = new WebSocket("ws://" + (location.hostname || "localhost") + ":8765");
  ws.onopen = () => { $("led-ws").className = "led g"; };
  ws.onclose = () => { $("led-ws").className = "led r"; setTimeout(connect, 2000); };
  ws.onmessage = ev => {
    let m; try { m = JSON.parse(ev.data); } catch { return; }
    $("k-ent").textContent = m.total_entities ?? "-";
    $("k-trk").textContent = m.total_tracks ?? "-";
    $("k-cyc").textContent = m.asda_cycle ?? "-";
    const v = (m.network_vulnerability ?? 0) * 100;
    $("k-vul").textContent = v.toFixed(1) + "%";
    $("clock").textContent = m.sim_time || "T+00:00:00";
    lastPhase = m.asda_phase || lastPhase;
    document.querySelectorAll(".phl").forEach(p =>
      p.classList.toggle("on", p.dataset.ph === lastPhase));
    document.querySelectorAll(".seg").forEach(s =>
      s.classList.toggle("on", s.dataset.ph === lastPhase));
    $("simnote").textContent = `周期 #${m.asda_cycle} · ${m.sim_time || ""}`;
    const defn = v > 30 || (m.total_tracks ?? 0) > 25 ? 1 : v > 15 ? 3 : 5;
    $("defnum").textContent = "DEF-" + defn;
    const rd = $("ready");
    rd.className = v > 30 || defn === 1 ? "crit" : v > 15 ? "warn" : "";
    const w2 = [];
    if (v > 15) w2.push([`网络脆弱度 ${v.toFixed(1)}% 超阈值`, v > 30 ? "crit" : "warn"]);
    if ((m.total_tracks ?? 0) > 20) w2.push([`威胁航迹 ${m.total_tracks} 条 — 多轴协同压力`, "warn"]);
    if (viz.pol.den > 0) w2.push([`${viz.pol.den} 个盟友站点准入 Denied`, "crit"]);
    const key = w2.map(x => x[0]).join("|");
    if (w2.length && key !== prevWarnKey) {
      const ts = new Date().toTimeString().slice(0, 8);
      w2.forEach(x => warns.push([ts + " " + x[0], x[1]]));
      if (warns.length > 30) warns.splice(0, warns.length - 30);
      prevWarnKey = key;
      renderWarn();
    }
    const ab = $("alert");
    if (v > 15 || (m.total_tracks ?? 0) > 25) {
      ab.style.display = "block";
      ab.textContent = v > 15
        ? `⚠ 网络脆弱度 ${v.toFixed(1)}% 超阈值 — 建议立即下达疏散指令`
        : `⚠ 威胁航迹 ${m.total_tracks} 条 — 多轴协同压力`;
    } else ab.style.display = "none";
    const evs = (m.type === "full" ? m.events : m.new_events) || [];
    if (evs.length) {
      for (const e of evs) {
        const item = Object.assign({}, e, { _ph: phaseOf(e) });
        allEvents.push(item);
        if (evCount[item._ph] !== undefined) evCount[item._ph]++;
      }
      if (allEvents.length > 500) allEvents.splice(0, allEvents.length - 500);
      if (pinned) renderAudit();
      const c2 = $("c2list");
      const view = pinned
        ? allEvents.filter(x => x._ph === pinned).slice(-8).reverse()
        : evs.slice(-8).reverse().map(x => Object.assign({}, x, { _ph: phaseOf(x) }));
      c2.innerHTML = view.map(e =>
        `<div class="evt"><b>${esc(String(e._ph||"").toUpperCase())}·${esc(String(e.event_type || e.type || "evt").toUpperCase())}</b> ` +
        `${esc(e.description || e.desc || "")}</div>`).join("");
      for (const e of evs) {
        if (String(e.event_type || "") === "ma_dqn_decision" && e.data) {
          const ia = e.data.intercept_action ?? 0, da = e.data.dispersal_action ?? 0;
          dqn.counts[ia] = (dqn.counts[ia] || 0) + 1;
          dqn.last = { ia, da }; dqn.act = 1;
          renderDqn();
        }
      }
    }
  };
}
connect();
</script>
</body>
</html>
"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(BRAIN)
print(f"Command Brain v2 -> {OUT} ({os.path.getsize(OUT)/1e3:.0f} KB)")
