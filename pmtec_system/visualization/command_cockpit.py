# -*- coding: utf-8 -*-
"""
P13+: 数字孪生作战舱 (PMTEC Command Cockpit) — 单页指挥大屏生成器

对标"数字孪生装备质量服务"大屏风格并超越:
  - 深色星空底 + 玻璃拟态卡片 + 霓虹描边 (同风格)
  - 力导向知识网络: INDOPACOM 根 + 8 司令部 + 67 基地 (真实 C2 关系)
  - 超越点 1: 全页 WebSocket 实时数据驱动 (仿真真推送, 非静态截图)
  - 超越点 2: 每个节点可溯源 CRS R47589 / DoD FY2024 BSR
  - 超越点 3: 政治准入三态维度 (独有的对抗维度)

产出: output/PMTEC_Command_Cockpit.html (自包含单文件)
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output", "PMTEC_Command_Cockpit.html")

# ---------------- 数据装配 ----------------
gj = json.load(open(os.path.join(ROOT, "data", "bases_v2.geojson"), encoding="utf-8"))
c2 = json.load(open(os.path.join(ROOT, "config", "indopacom_c2.json"), encoding="utf-8"))

bases = []
for ft in gj["features"]:
    p = ft["properties"]
    lon, lat = ft["geometry"]["coordinates"][:2]
    bases.append({
        "id": p.get("id", ""),
        "name": p.get("name", ""),
        "name_cn": p.get("name_cn", ""),
        "tier": p.get("tier", 2),
        "tier_label": p.get("tier_label", ""),
        "branch": p.get("branch", ""),
        "country": p.get("country", ""),
        "region": p.get("region", ""),
        "unit": p.get("unit", ""),
        "role": p.get("role", ""),
        "lat": lat, "lon": lon,
        "access": p.get("access_uncertainty", ""),
        "ally": p.get("access_uncertainty") == "host_nation",
        "hub": bool(p.get("ace_hub")),
        "crs_no": p.get("crs_no", ""),
        "prv_q": p.get("fy24_prv_quartile", ""),
        "prv_musd": p.get("fy24_prv_musd", ""),
        "runway_m": p.get("runway_m", ""),
        "personnel": p.get("personnel", ""),
    })

commands = []
for sc in c2["service_components"]:
    commands.append({"id": sc["node_id"], "name": sc.get("name_cn", sc["name"]),
                     "kind": "component", "branch": sc.get("branch", ""),
                     "hq": sc.get("hq_location", "")})
for su in c2["subordinate_unified"]:
    commands.append({"id": su["node_id"], "name": su.get("name_cn", su["name"]),
                     "kind": "subordinate", "branch": su.get("branch", ""),
                     "hq": su.get("hq_location", "")})

assign = c2["base_assignments"]
for b in bases:
    a = assign.get(b["id"], {})
    b["command"] = a.get("command", "")
    b["components"] = a.get("components", [])

countries = sorted({b["country"] for b in bases if b["country"]})
ally_count = sum(1 for b in bases if b["ally"])
hub_count = sum(1 for b in bases if b["hub"])
b64 = open(os.path.join(ROOT, "data", "bases_v2.geojson"), "rb")

DATA = {
    "bases": bases, "commands": commands,
    "stats": {
        "nodes": 1 + len(commands) + len(bases),
        "edges": len(commands) + len(bases),
        "bases": len(bases), "commands": len(commands),
        "allies": ally_count, "hubs": hub_count,
        "countries": len(countries),
        "fields": 33,
    },
    "generated": time.strftime("%Y-%m-%d %H:%M"),
}

TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PMTEC 数字孪生作战舱</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
:root {
  --bg:#05070f; --panel:rgba(13,18,32,.72); --line:rgba(90,140,220,.25);
  --txt:#dfe8f4; --dim:#7e8ea6; --cyan:#39c2ff; --blue:#4f7cff; --green:#2fe08a;
  --amber:#ffb545; --red:#ff5d6c; --purple:#b07cff;
}
html,body { height:100%; }
body { background:var(--bg); color:var(--txt);
  font-family:"Segoe UI","Microsoft YaHei",sans-serif; overflow:hidden; }
#stars { position:fixed; inset:0; z-index:0; }
#wrap { position:relative; z-index:1; height:100vh; display:flex; flex-direction:column; }

/* ---- 顶栏 ---- */
header { display:flex; align-items:center; gap:22px; padding:12px 26px;
  background:linear-gradient(180deg, rgba(10,16,30,.92), rgba(10,16,30,.62));
  border-bottom:1px solid var(--line); backdrop-filter:blur(8px); }
.brand { display:flex; flex-direction:column; }
.brand b { font-size:17px; letter-spacing:1px;
  background:linear-gradient(90deg,#7fd4ff,#4f7cff); -webkit-background-clip:text;
  -webkit-text-fill-color:transparent; }
.brand span { font-size:10px; color:var(--dim); letter-spacing:3px; }
nav { display:flex; gap:6px; flex:1; }
nav .tab { padding:7px 18px; border-radius:16px; font-size:13.5px; color:var(--dim);
  cursor:pointer; border:1px solid transparent; transition:.2s; user-select:none; }
nav .tab:hover { color:var(--txt); }
nav .tab.on { color:#04121f; background:linear-gradient(90deg,#43d6ff,#4f7cff);
  font-weight:700; box-shadow:0 0 14px rgba(70,190,255,.45); }
#wsdot { font-size:11.5px; color:var(--dim); }
#wsdot.ok { color:var(--green); }

main { flex:1; position:relative; overflow:hidden; }
.page { position:absolute; inset:0; padding:18px 26px; overflow:auto; display:none; }
.page.on { display:block; }
h2.sec { font-size:13px; color:var(--cyan); margin:6px 0 10px; letter-spacing:1px; }
h2.sec::before { content:"▎"; color:var(--blue); }

/* ---- 玻璃卡片 ---- */
.glass { background:var(--panel); border:1px solid var(--line); border-radius:12px;
  backdrop-filter:blur(6px); box-shadow:0 0 22px rgba(20,60,140,.18) inset; }
.kpis { display:grid; grid-template-columns:repeat(6,1fr); gap:14px; margin-bottom:14px; }
.kpi { padding:13px 16px; position:relative; overflow:hidden; }
.kpi::before { content:""; position:absolute; left:0; top:0; bottom:0; width:3px;
  background:linear-gradient(180deg,var(--cyan),var(--blue)); }
.kpi .v { font-size:27px; font-weight:800; font-family:Consolas,monospace; }
.kpi .l { font-size:11px; color:var(--dim); margin-top:3px; }
.kpi .s { font-size:10px; color:#4d5d75; margin-top:2px; }
.v.c-cyan{color:var(--cyan)} .v.c-green{color:var(--green)}
.v.c-amber{color:var(--amber)} .v.c-red{color:var(--red)} .v.c-purple{color:var(--purple)}

/* ---- 态势总览 ---- */
.ovgrid { display:grid; grid-template-columns:1.6fr 1fr; gap:14px; }
.cardpad { padding:14px 16px; }
#phasebar { display:flex; gap:6px; margin:12px 0 4px; }
.ph { flex:1; text-align:center; padding:9px 0; border-radius:8px; font-size:13px;
  background:rgba(30,40,60,.5); color:var(--dim); border:1px solid var(--line);
  cursor:pointer; transition:.18s; user-select:none; }
.ph:hover { color:var(--txt); border-color:var(--cyan); }
.ph.on { color:#04121f; font-weight:800; background:linear-gradient(90deg,#43d6ff,#4f7cff);
  box-shadow:0 0 16px rgba(70,190,255,.5); }
.ph.pin { outline:2px solid var(--amber); outline-offset:1px; color:var(--amber); }
.ph .cnt { font-size:9.5px; color:var(--green); margin-left:4px; font-family:Consolas,monospace; }
#msgstream { margin-top:12px; max-height:330px; overflow:auto; }
.msg { display:flex; gap:10px; padding:7px 10px; border-left:2px solid var(--line);
  margin-bottom:6px; font-size:12px; background:rgba(20,28,46,.45); border-radius:6px; }
.msg .t { color:var(--dim); font-family:Consolas,monospace; white-space:nowrap; }
.msg .ty { color:var(--amber); white-space:nowrap; font-weight:700; }
.msg .d { color:var(--txt); }

/* ---- 力导向网络 ---- */
#netwrap { position:relative; height:calc(100vh - 130px); }
#net { width:100%; height:100%; display:block; cursor:grab; }
#netdetail { position:absolute; left:14px; top:196px; width:330px; padding:14px 16px;
  display:none; font-size:12.5px; }
#netpanel { position:absolute; right:14px; top:14px; width:250px; padding:12px 14px; }
#netpanel .it { display:flex; align-items:center; gap:8px; margin:5px 0; color:var(--txt);
  cursor:pointer; user-select:none; }
#netpanel .it.off { opacity:.32; }
#netpanel .it .sw { width:10px; height:10px; border-radius:50%; }
#netpanel .cnt { margin-left:auto; color:var(--cyan); font-family:Consolas,monospace; }
#netpanel .grp { color:var(--dim); font-size:10.5px; margin:9px 0 3px; letter-spacing:1px; }
#netdetail h3 { font-size:15px; color:var(--cyan); margin-bottom:8px; }
#netdetail .row { display:flex; justify-content:space-between; padding:5px 0;
  border-bottom:1px dashed rgba(90,140,220,.15); }
#netdetail .row span:first-child { color:var(--dim); }
#netdetail .src { margin-top:9px; font-size:11px; color:#5da4ff; }
.legendbox { position:absolute; left:14px; top:14px; padding:10px 14px; font-size:11.5px; }
.legendbox .it { display:flex; align-items:center; gap:7px; margin:4px 0; color:var(--dim); }
.legendbox .sw { width:10px; height:10px; border-radius:50%; }
.filters { position:absolute; left:14px; bottom:14px; padding:10px 14px; font-size:11.5px; }
.filters label { display:flex; align-items:center; gap:6px; margin:4px 0;
  color:var(--dim); cursor:pointer; }

/* ---- 数字线程 ---- */
.thread { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }
.stage { padding:15px 18px; position:relative; }
.stage h4 { font-size:14.5px; color:var(--txt); display:flex; justify-content:space-between; }
.stage h4 i { font-style:normal; font-size:12px; padding:2px 10px; border-radius:10px; }
.st-hi { color:var(--green); background:rgba(47,224,138,.12); }
.st-mid { color:var(--cyan); background:rgba(57,194,255,.12); }
.st-wa { color:var(--amber); background:rgba(255,181,69,.12); }
.stage .kv { display:flex; justify-content:space-between; font-size:12px;
  padding:5px 0; border-bottom:1px dashed rgba(90,140,220,.14); }
.stage .kv span:first-child { color:var(--dim); }
.stage .out { font-size:11.5px; color:#5da4ff; margin-top:8px; }
.bar { height:5px; border-radius:3px; background:rgba(40,52,74,.8); margin-top:10px; overflow:hidden; }
.bar i { display:block; height:100%; border-radius:3px;
  background:linear-gradient(90deg,#2fe08a,#39c2ff); animation:grow 1.2s ease; }
@keyframes grow { from { width:0 !important; } }

/* ---- 韧性 ---- */
.rgrid { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin-bottom:16px; }
.rcard { padding:16px 18px; text-align:center; }
.rcard .big { font-size:34px; font-weight:800; font-family:Consolas,monospace; }
.rcard .sub { font-size:11.5px; color:var(--dim); margin-top:4px; }
.echain { padding:14px 18px; }
.echain .row { display:flex; gap:14px; padding:8px 0; font-size:12.5px;
  border-bottom:1px dashed rgba(90,140,220,.15); }
.echain .row b { color:var(--cyan); min-width:120px; font-weight:600; }
iframe { width:100%; height:calc(100vh - 130px); border:0; border-radius:12px; }
.note { font-size:11px; color:#4d5d75; margin-top:10px; }
@media (max-width:1100px) {
  .kpis { grid-template-columns:repeat(3,1fr); }
  .ovgrid { grid-template-columns:1fr; }
  .thread { grid-template-columns:repeat(2,1fr); }
  #netwrap { height:70vh; }
}
@media (max-width:720px) {
  .kpis { grid-template-columns:repeat(2,1fr); }
  .thread { grid-template-columns:1fr; }
  header { flex-wrap:wrap; gap:10px; }
  nav { flex-wrap:wrap; }
  #netpanel { width:200px; }
  #netdetail { width:250px; top:150px; }
}
</style>
</head>
<body>
<canvas id="stars"></canvas>
<div id="wrap">
<header>
  <div class="brand"><b>PMTEC 数字孪生作战舱</b><span>DIGITAL TWIN BATTLEFIELD · DTC 2026</span></div>
  <nav id="nav">
    <div class="tab on" data-p="p1">态势总览</div>
    <div class="tab" data-p="p2">基地知识网络</div>
    <div class="tab" data-p="p3">实时地图</div>
    <div class="tab" data-p="p4">数字线程</div>
    <div class="tab" data-p="p5">韧性校验</div>
  </nav>
  <div id="wsdot">● 未连接</div>
</header>
<main>

<!-- 态势总览 -->
<div class="page on" id="p1">
  <div class="kpis">
    <div class="kpi glass"><div class="v c-cyan" id="k-ent">45</div><div class="l">实体总数</div><div class="s">飞机 / 导弹 / 传感器</div></div>
    <div class="kpi glass"><div class="v c-purple" id="k-trk">0</div><div class="l">威胁航迹</div><div class="s">Kalman / JPDA 融合</div></div>
    <div class="kpi glass"><div class="v c-amber" id="k-cyc">0</div><div class="l">ASDA 周期</div><div class="s">10s 闭环</div></div>
    <div class="kpi glass"><div class="v c-cyan" id="k-vul">0.0%</div><div class="l">网络脆弱度</div><div class="s">67 节点战斗网络</div></div>
    <div class="kpi glass"><div class="v c-green">67</div><div class="l">权威基地</div><div class="s">CRS R47589 / FY2024 BSR</div></div>
    <div class="kpi glass"><div class="v c-amber">79.1%</div><div class="l">总体拦截率</div><div class="s">六策略 · Wilson 95% CI</div></div>
  </div>
  <div class="ovgrid">
    <div class="glass cardpad">
      <h2 class="sec">ASDA 闭环相位 · Act → Sense → Decide → Adapt</h2>
      <div id="phasebar">
        <div class="ph" data-ph="Act">Act 行动<span class="cnt" id="cnt-Act"></span></div>
        <div class="ph" data-ph="Sense">Sense 感知<span class="cnt" id="cnt-Sense"></span></div>
        <div class="ph" data-ph="Decide">Decide 决策<span class="cnt" id="cnt-Decide"></span></div>
        <div class="ph" data-ph="Adapt">Adapt 适应<span class="cnt" id="cnt-Adapt"></span></div>
      </div>
      <div class="note" id="phaseinfo">点击任意相位 → 过滤该相位真实事件并显示实现说明 (再次点击返回自动跟随)</div>
      <div class="note" id="simtime">等待仿真推送… (启动: python main.py)</div>
      <h2 class="sec" style="margin-top:14px">指挥链消息流 · P11 C2 Chain (逐跳审计)</h2>
      <div id="msgstream"><div class="msg"><span class="t">--:--</span><span class="ty">SYSTEM</span><span class="d">等待 WebSocket 事件推送 (ws://localhost:8765)…</span></div></div>
    </div>
    <div class="glass cardpad">
      <h2 class="sec">体系韧性指标 · 实证数据</h2>
      <div class="echain" style="padding:0">
        <div class="row"><b>三场景对照</b><span>76.2% → 79.0% → 79.5%</span></div>
        <div class="row"><b>数据净效应</b><span>权威 67 实体 +2.8pp</span></div>
        <div class="row"><b>六策略全量</b><span>79.1% (CI 78.0-80.2)</span></div>
        <div class="row"><b>10 万次敏感性</b><span>最差可用率 95.5%</span></div>
        <div class="row"><b>政治敞口均值</b><span>273 (十万次 MC)</span></div>
        <div class="row"><b>CI/CD</b><span>6 阶段全绿 (Run #4)</span></div>
        <div class="row"><b>代码资产</b><span>24,800+ 行 · 308 项断言</span></div>
      </div>
      <div class="note">全部指标来自系统真实运行与统计实验, 溯源见"韧性校验"页。</div>
    </div>
  </div>
</div>

<!-- 基地知识网络 -->
<div class="page" id="p2">
  <div id="netwrap">
    <canvas id="net"></canvas>
    <div class="legendbox glass">
      <div class="it"><span class="sw" style="background:#4f7cff"></span>INDOPACOM</div>
      <div class="it"><span class="sw" style="background:#2fe08a"></span>陆军 USARPAC</div>
      <div class="it"><span class="sw" style="background:#39c2ff"></span>海军 PACFLT</div>
      <div class="it"><span class="sw" style="background:#ff5d6c"></span>陆战队 MARFORPAC</div>
      <div class="it"><span class="sw" style="background:#ffb545"></span>空军 PACAF</div>
      <div class="it"><span class="sw" style="background:#b07cff"></span>天军 USSFPAC / 联合</div>
      <div class="it"><span class="sw" style="background:#8b9bb5"></span>基地 (按 Tier 定径)</div>
    </div>
    <div id="netpanel" class="glass">
      <h2 class="sec" style="margin:0 0 4px">实体类别与筛选</h2>
      <div id="npitems"></div>
      <div class="note" style="margin-top:8px">滚轮缩放 · 拖拽平移 · 点击节点溯源</div>
    </div>
    <div id="netdetail" class="glass"></div>
  </div>
</div>

<!-- 实时地图 -->
<div class="page" id="p3">
  <iframe src="pmtec_realtime_map_v2.html"></iframe>
</div>

<!-- 数字线程 -->
<div class="page" id="p4">
  <h2 class="sec">数字线程 · 六阶段全生命周期 (真实资产台账)</h2>
  <div class="thread" id="thread"></div>
  <div class="note">每阶段进度条反映该环节资产完备度; 数据全部来自本仓库真实产物台账。</div>
</div>

<!-- 韧性校验 -->
<div class="page" id="p5">
  <h2 class="sec">韧性推理校验 · 三场景隔离对照 (模型不变, 数据与约束隔离变量)</h2>
  <div class="rgrid">
    <div class="rcard glass"><div class="big" style="color:#8b9bb5">76.2%</div><div class="sub">A 基线 · 原 22 站点 · 182 维 P6<br>95% CI 74.7-77.7</div></div>
    <div class="rcard glass"><div class="big" style="color:var(--cyan)">79.0%</div><div class="sub">B v2 权威数据 · 模型不变<br>95% CI 77.1-80.8 · <b style="color:var(--green)">+2.8pp</b></div></div>
    <div class="rcard glass"><div class="big" style="color:var(--green)">79.5%</div><div class="sub">C 政治准入 · 219 维 P12<br>约束下韧性不降反稳</div></div>
  </div>
  <div class="glass echain">
    <h2 class="sec">证据链 · 从权威数据到统计结论</h2>
    <div class="row"><b>数据源</b><span>CRS R47589 Table A-1 (66 站点) + DoD FY2024 Base Structure Report + Tinian → 67 实体 / 33 字段</span></div>
    <div class="row"><b>建模方法</b><span>政治准入三态状态机 (Full/Restricted/Denied) · RAND RRA967-2 对手分化策略 · MRF-D 轮换建模</span></div>
    <div class="row"><b>训练</b><span>DQN 219 维 (XPU 200K 步) · IQL/MADDPG 多智能体 219 维 (avg reward 1138, +29% vs P8)</span></div>
    <div class="row"><b>实验 A→B</b><span>60 episodes Monte Carlo, seed 对齐隔离: 数据净效应 +2.8pp</span></div>
    <div class="row"><b>实验 B→C</b><span>150 episodes 六策略全量: 79.1% (CI 78.0-80.2), 全策略 ≥77.6%</span></div>
    <div class="row"><b>敏感性</b><span>N=100,000 · Denied 均值 0.14 / Restricted 5.19 / 敞口 273 · 最差可用率 95.5%</span></div>
    <div class="row"><b>结论</b><span>适应优于压制 —— 用真实世界数据让数字孪生更真, 用政治不确定性让对抗更聪明</span></div>
  </div>
</div>

</main>
</div>

<script>
const DATA = __DATA_JSON__;

/* ---------------- 星空背景 ---------------- */
const sc = document.getElementById("stars"), sx = sc.getContext("2d");
let SW, SH, stars = [];
function initStars() {
  SW = sc.width = innerWidth; SH = sc.height = innerHeight;
  stars = Array.from({length: 190}, () => ({
    x: Math.random()*SW, y: Math.random()*SH,
    r: Math.random()*1.3+.3, s: Math.random()*.28+.05,
    c: Math.random() < .16 ? "120,180,255" : (Math.random()<.1 ? "255,190,120" : "200,220,255")
  }));
}
initStars(); addEventListener("resize", () => { initStars(); fitNet(); });
(function starLoop() {
  sx.clearRect(0,0,SW,SH);
  for (const s of stars) {
    s.x += s.s; if (s.x > SW) s.x = 0;
    sx.beginPath(); sx.arc(s.x, s.y, s.r, 0, 7);
    sx.fillStyle = `rgba(${s.c},.7)`; sx.fill();
  }
  requestAnimationFrame(starLoop);
})();

/* ---------------- 页签 ---------------- */
let curTab = "p1";
document.getElementById("nav").addEventListener("click", e => {
  const t = e.target.closest(".tab"); if (!t) return;
  document.querySelectorAll(".tab").forEach(x => x.classList.toggle("on", x === t));
  document.querySelectorAll(".page").forEach(p => p.classList.toggle("on", p.id === t.dataset.p));
  curTab = t.dataset.p;
  if (curTab === "p2") fitNet();
});

/* ---------------- WebSocket 实时 ---------------- */
const PHASE_META = {
  Act:   { color:"#ff8f6c", types:["missile_launch","intercept_attempt","intercept_outcome","dispersal"],
    impl:"执行当前指令: 对手智能体攻击决策 / 导弹发射 / 机群疏散执行",
    code:"_asda_act · services/grpc_server.py L611" },
  Sense: { color:"#39c2ff", types:["live_data_inject","sensor_scan"],
    impl:"全传感器扫描 + LVC Live 实时数据注入 (ADS-B/AIS/气象) + 气象闭环修正",
    code:"_asda_sense · services/grpc_server.py L782" },
  Decide:{ color:"#b07cff", types:["ma_dqn_decision","dqn_decision","ucb1_decision"],
    impl:"航迹融合 → 识别敌对目标 → IQL/MADDPG 多智能体协同决策 (拦截策略 + 疏散等级)",
    code:"_asda_decide · services/grpc_server.py L1190" },
  Adapt: { color:"#2fe08a", types:["adapt","political_","c2_order","learning_update","impact_assessment"],
    impl:"战果 Monte Carlo 评估 → 学习管理器更新 → 政治准入演化 → C2 跨军种协同",
    code:"_asda_adapt · services/grpc_server.py L1505" },
};
function phaseOf(ev) {
  // 事件体真实字段: event_type / description / data{...} / timestamp
  if (ev.data && ev.data.phase) return String(ev.data.phase);
  if (ev.asda_phase) return String(ev.asda_phase);
  const ty = String(ev.event_type || ev.type || "").toLowerCase();
  if (ty === "asda_cycle") return lastPhase;
  for (const [ph, m] of Object.entries(PHASE_META))
    if (m.types.some(t => ty.includes(t))) return ph;
  return "Adapt";  // 其余事件 (c2_order 等) 均由 Adapt 相位链路发出
}
const allEvents = [];
const evCount = { Act:0, Sense:0, Decade:0, Decide:0, Adapt:0 };
let pinned = null, lastPhase = "Act";
const stream = document.getElementById("msgstream");
const phaseInfo = document.getElementById("phaseinfo");

function fmtEv(e, m) {
  const ty = String(e.event_type || e.type || "event").toUpperCase();
  const d = e.description || e.desc || JSON.stringify(e).slice(0, 90);
  let t = (m && m.sim_time) || "";
  if (e.timestamp) {
    try { t = new Date(e.timestamp * 1000).toTimeString().slice(0, 8); } catch {}
  }
  const ph = phaseOf(e);
  return `<div class="msg"><span class="t">${t}</span>` +
    `<span class="ty" style="color:${(PHASE_META[ph]||{}).color||"#ffb545"}">${ph}·${ty}</span>` +
    `<span class="d">${d}</span></div>`;
}
function updateCounters() {
  for (const ph of ["Act","Sense","Decide","Adapt"]) {
    const el = document.getElementById("cnt-" + ph);
    if (el) el.textContent = evCount[ph] ? `+${evCount[ph]}` : "";
  }
}
function renderStream() {
  let evs, label;
  if (pinned) {
    evs = allEvents.filter(e => e._ph === pinned).slice(-9).reverse();
    const m = PHASE_META[pinned];
    label = `<b style="color:${m.color}">${pinned} 相位</b> · ${m.impl}` +
      `<br><span style="color:#5da4ff">${m.code} · 本次运行捕获 ${evCount[pinned]} 个事件</span>` +
      `<br><span style="color:var(--dim)">再次点击该相位返回自动跟随</span>`;
  } else {
    evs = allEvents.slice(-9).reverse();
    label = "自动跟随引擎相位 · 点击任意相位可审计该相位事件";
  }
  phaseInfo.innerHTML = label;
  stream.innerHTML = evs.length ? evs.map(e => fmtEv(e, null)).join("")
    : `<div class="msg"><span class="t">--:--</span><span class="ty">${pinned||""}</span>` +
      `<span class="d">${pinned ? "本相位暂无事件, 等待下一周期…" : "等待 WebSocket 事件推送…"}</span></div>`;
}
document.querySelectorAll("#phasebar .ph").forEach(el => {
  el.addEventListener("click", () => {
    const ph = el.dataset.ph;
    pinned = (pinned === ph) ? null : ph;
    document.querySelectorAll("#phasebar .ph").forEach(x =>
      x.classList.toggle("pin", x.dataset.ph === pinned));
    renderStream();
  });
});

let ws = null, wsOK = false;
const dot = document.getElementById("wsdot");
function connect() {
  ws = new WebSocket("ws://" + (location.hostname || "localhost") + ":8765");
  ws.onopen = () => { wsOK = true; dot.textContent = "● 已连接 ws://localhost:8765"; dot.classList.add("ok"); };
  ws.onclose = () => { wsOK = false; dot.textContent = "● 断开, 2s 重连"; dot.classList.remove("ok"); setTimeout(connect, 2000); };
  ws.onmessage = ev => {
    let m; try { m = JSON.parse(ev.data); } catch { return; }
    document.getElementById("k-ent").textContent = m.total_entities ?? "-";
    document.getElementById("k-trk").textContent = m.total_tracks ?? "-";
    document.getElementById("k-cyc").textContent = m.asda_cycle ?? "-";
    const v = (m.network_vulnerability ?? 0) * 100;
    const kv = document.getElementById("k-vul");
    kv.textContent = v.toFixed(1) + "%";
    kv.className = "v " + (v > 40 ? "c-red" : v > 15 ? "c-amber" : "c-green");
    document.getElementById("simtime").textContent =
      `仿真时刻 ${m.sim_time || "T+0"} · 周期 #${m.asda_cycle} · 相位 ${m.asda_phase || "-"}`;
    lastPhase = m.asda_phase || lastPhase;
    const evs = (m.type === "full" ? m.events : m.new_events) || [];
    if (evs.length) {
      for (const e of evs) {
        const item = Object.assign({}, e, { _ph: phaseOf(e), _m: m });
        allEvents.push(item);
        if (evCount[item._ph] !== undefined) evCount[item._ph]++;
      }
      if (allEvents.length > 400) allEvents.splice(0, allEvents.length - 400);
      updateCounters();
    }
    document.querySelectorAll(".ph").forEach(p => {
      const el = p.dataset.ph;
      p.classList.toggle("on", pinned ? el === pinned : el === lastPhase);
    });
    renderStream();
  };
}
connect();

/* ---------------- 数字线程 ---------------- */
const STAGES = [
  {n:"1. 权威数据底座", p:100, cls:"st-hi", rows:[["本体模型","67 基地实体 / 33 字段"],["数据资产","CRS R47589 + FY2024 BSR 双源"],["溯源率","100% (A 级精度 45 站)"]],out:"关键输出: indopacom_bases_v2.geojson"},
  {n:"2. 体系建模", p:98, cls:"st-hi", rows:[["本体模型","C2 8 司令部 · 政治准入状态机"],["数据资产","base_assignments 67 条 · 36 盟友站点"],["关键输出","ACE 优化器 + 约束版 Pareto"]],out:"关键输出: indopacom_c2.json / political_access.json"},
  {n:"3. AI 训练", p:96, cls:"st-mid", rows:[["本体模型","DQN 219 维 · IQL / MADDPG 多智能体"],["数据资产","XPU 200K 步 · avg reward 1138 (+29%)"],["关键输出","10+ 模型检查点 + 元数据"]],out:"关键输出: pmtec_dqn_p12.zip / *_219 模型族"},
  {n:"4. 仿真推演", p:95, cls:"st-mid", rows:[["本体模型","ASDA 四相位闭环 · LVC 三层"],["数据资产","1200s 战役 · 45 实体实时推送"],["关键输出","SPEAR 回放 / WebSocket 通道"]],out:"关键输出: pmtec_realtime_map_v2.html"},
  {n:"5. 验证评估", p:97, cls:"st-hi", rows:[["本体模型","308 项断言 · 18 个测试文件"],["数据资产","Monte Carlo 210 episodes · 10 万次敏感性"],["关键输出","79.1% (CI 78.0-80.2) · 最差可用率 95.5%"]],out:"关键输出: monte_carlo_results_v2_political.json"},
  {n:"6. 交付运维", p:100, cls:"st-hi", rows:[["本体模型","CI/CD 6 阶段 · Docker 7 服务编排"],["数据资产","Run #4 全绿 · 离线包 37.3MB"],["关键输出","ghcr 镜像 + 灾备 Runbook"]],out:"关键输出: PMTEC_CICD_Run_Record.html"},
];
document.getElementById("thread").innerHTML = STAGES.map(s => `
  <div class="stage glass">
    <h4>${s.n}<i class="${s.cls}">${s.p}%</i></h4>
    ${s.rows.map(r => `<div class="kv"><span>${r[0]}</span><span>${r[1]}</span></div>`).join("")}
    <div class="out">${s.out}</div>
    <div class="bar"><i style="width:${s.p}%"></i></div>
  </div>`).join("");

/* ---------------- 力导向知识网络 ---------------- */
const BRANCH_COLOR = { army:"#2fe08a", navy:"#39c2ff", "marine corps":"#ff5d6c",
  "space force":"#b07cff", joint:"#b07cff", usaf:"#ffb545" };
function bcolor(b) { return BRANCH_COLOR[(b.branch||"").toLowerCase()] || "#8b9bb5"; }
function ccolor(c) {
  return { USARPAC:"#2fe08a", PACFLT:"#39c2ff", MARFORPAC:"#ff5d6c",
    PACAF:"#ffb545", USSFPAC:"#b07cff" }[c.id] || "#b07cff";
}

const nodes = [{ id:"INDOPACOM", kind:"root", r:17, color:"#4f7cff", label:"INDOPACOM",
  x:0, y:0, vx:0, vy:0 }];
const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
for (const c of DATA.commands) {
  const n = { id:c.id, kind:"command", r:11.5, color:ccolor(c), label:c.name,
    x:(Math.random()-.5)*520, y:(Math.random()-.5)*360, vx:0, vy:0, c:c };
  nodes.push(n); byId[c.id] = n;
}
for (const b of DATA.bases) {
  const n = { id:b.id, kind:"base", r:4 + (5 - b.tier)*1.5, color:bcolor(b),
    label:b.name_cn || b.name, x:(Math.random()-.5)*840, y:(Math.random()-.5)*560,
    vx:0, vy:0, b:b };
  nodes.push(n); byId[n.id] = n;
}
function mkEdge(a, b, color) {
  return { a, b, color, k:(Math.random()*.14+.07)*(Math.random()<.5?-1:1),
    ph:Math.random(), sp:.16+Math.random()*.3 };
}
const edges = [];
for (const c of DATA.commands) edges.push(mkEdge(byId.INDOPACOM, byId[c.id], ccolor(c)));
for (const b of DATA.bases) {
  const cmd = b.command && byId[b.command] ? byId[b.command] : byId.INDOPACOM;
  edges.push(mkEdge(byId[b.id], cmd, bcolor(b)));
}

/* 类别筛选面板 */
const CATS = [
  { key:"root", grp:"战区级", label:"INDOPACOM 战区", color:"#4f7cff", cnt:1 },
  { key:"cmd:component", grp:"司令部", label:"军种组成司令部", color:"#39c2ff",
    cnt:DATA.commands.filter(c => c.kind === "component").length },
  { key:"cmd:subordinate", label:"下属联合司令部", color:"#b07cff",
    cnt:DATA.commands.filter(c => c.kind === "subordinate").length },
  { key:"t1", grp:"基地 (按 Tier)", label:"Tier-1 战略核心", color:"#ff8f6c",
    cnt:DATA.bases.filter(b => b.tier === 1).length },
  { key:"t2", label:"Tier-2 主要作战", color:"#ffc46b",
    cnt:DATA.bases.filter(b => b.tier === 2).length },
  { key:"t3", label:"Tier-3 专业站点", color:"#d2a8ff",
    cnt:DATA.bases.filter(b => b.tier === 3).length },
  { key:"t4", label:"Tier-4 轮换与准入", color:"#7ee787",
    cnt:DATA.bases.filter(b => b.tier === 4).length },
  { key:"ally", grp:"政治维度", label:"盟友站点 (host nation)", color:"#ffb545",
    cnt:DATA.bases.filter(b => b.ally).length },
  { key:"hub", label:"ACE Hub 枢纽", color:"#ffe066", cnt:DATA.stats.hubs },
];
const show = Object.fromEntries(CATS.map(c => [c.key, true]));
const visNode = n => n.kind === "root" ? show.root :
  n.kind === "command" ? show["cmd:" + n.c.kind] :
  (show["t" + n.b.tier] && (!n.b.ally || show.ally));
document.getElementById("npitems").innerHTML = CATS.map(c => `
  <div class="it" data-k="${c.key}"><span class="sw" style="background:${c.color}"></span>${c.label}<span class="cnt">${c.cnt}</span></div>`).join("");
document.getElementById("npitems").addEventListener("click", e => {
  const it = e.target.closest(".it"); if (!it) return;
  show[it.dataset.k] = !show[it.dataset.k];
  it.classList.toggle("off", !show[it.dataset.k]);
});

const cv = document.getElementById("net"), cx = cv.getContext("2d");
let W, H;
const cam = { x: 0, y: 0, s: 1 };
function fitNet() {
  const r = cv.parentElement.getBoundingClientRect();
  W = cv.width = r.width; H = cv.height = r.height;
}
fitNet();

/* 物理 (世界坐标以 0,0 为中心) */
function physics() {
  for (const n of nodes) {
    n.vx *= .86; n.vy *= .86;
    n.vx += (0 - n.x) * .0015; n.vy += (0 - n.y) * .0015;
  }
  for (let i = 0; i < nodes.length; i++)
    for (let j = i+1; j < nodes.length; j++) {
      const a = nodes[i], b = nodes[j];
      let dx = b.x - a.x, dy = b.y - a.y, d2 = dx*dx + dy*dy || 1;
      const f = 2600 / d2, d = Math.sqrt(d2);
      dx /= d; dy /= d;
      a.vx -= dx*f; a.vy -= dy*f; b.vx += dx*f; b.vy += dy*f;
    }
  for (const e of edges) {
    let dx = e.b.x - e.a.x, dy = e.b.y - e.a.y;
    const d = Math.sqrt(dx*dx + dy*dy) || 1;
    const rest = e.a.kind === "root" ? 170 : 110;
    const f = (d - rest) * .012;
    dx /= d; dy /= d;
    e.a.vx += dx*f; e.a.vy += dy*f; e.b.vx -= dx*f; e.b.vy -= dy*f;
  }
  for (const n of nodes) {
    if (n.drag) continue;
    n.x += n.vx; n.y += n.vy;
    n.x = Math.max(-760, Math.min(760, n.x));
    n.y = Math.max(-540, Math.min(540, n.y));
  }
}

/* 交互 (含缩放/平移, 世界坐标拾取) */
let mouse = { sx:0, sy:0, wx:0, wy:0, node:null, down:false, pan:false };
function s2w(mx, my) {
  return { x:(mx - W/2)/cam.s + cam.x, y:(my - H/2)/cam.s + cam.y };
}
function pick(wx, wy) {
  let best = null, bd = 16;
  for (const n of nodes) {
    const dx = n.x - wx, dy = n.y - wy, d = Math.sqrt(dx*dx + dy*dy);
    if (d < n.r + 10/cam.s + 4 && d < bd) { best = n; bd = d; }
  }
  return best;
}
cv.addEventListener("mousemove", e => {
  const r = cv.getBoundingClientRect();
  mouse.sx = e.clientX - r.left; mouse.sy = e.clientY - r.top;
  const w = s2w(mouse.sx, mouse.sy); mouse.wx = w.x; mouse.wy = w.y;
  if (mouse.down && mouse.node) {
    mouse.node.x = w.x; mouse.node.y = w.y; mouse.node.vx = mouse.node.vy = 0;
  } else if (mouse.down && mouse.pan) {
    cam.x -= e.movementX/cam.s; cam.y -= e.movementY/cam.s;
  } else {
    mouse.node = pick(w.x, w.y);
    cv.style.cursor = mouse.node ? "pointer" : "grab";
  }
});
cv.addEventListener("mousedown", () => {
  mouse.down = true;
  mouse.node = pick(mouse.wx, mouse.wy);
  mouse.pan = !mouse.node;
});
addEventListener("mouseup", () => { if (mouse.node) mouse.node.drag = false; mouse.down = false; mouse.pan = false; });
cv.addEventListener("wheel", e => {
  e.preventDefault();
  const r = cv.getBoundingClientRect();
  const w = s2w(e.clientX - r.left, e.clientY - r.top);
  cam.s = Math.min(3, Math.max(.4, cam.s * Math.exp(-e.deltaY * .0011)));
  const w2 = s2w(e.clientX - r.left, e.clientY - r.top);
  cam.x += w.x - w2.x; cam.y += w.y - w2.y;
}, { passive:false });
cv.addEventListener("click", () => {
  const n = mouse.node;
  if (!n) { hideDetail(); return; }
  if (n.kind === "base") showDetail(n.b);
  else if (n.kind === "command") showCmdDetail(n.c);
  else showRootDetail();
});
function hideDetail() { document.getElementById("netdetail").style.display = "none"; }
function showRootDetail() {
  const d = document.getElementById("netdetail");
  d.style.display = "block";
  d.innerHTML = `<h3>INDOPACOM 战区指挥中枢</h3>
    <div class="row"><span>层级</span><span>战区级 (Combatant Command)</span></div>
    <div class="row"><span>下辖</span><span>5 军种组成 + 3 下属联合司令部</span></div>
    <div class="row"><span>基地网络</span><span>67 站点 · 11 国家/地区</span></div>
    <div class="row"><span>兵力规模</span><span>约 375,000 (CRS IF12175)</span></div>
    <div class="src">溯源: CRS IF12175 · Camp H.M. Smith, Hawaii</div>`;
}
function showCmdDetail(c) {
  const d = document.getElementById("netdetail");
  const cnt = DATA.bases.filter(b => b.command === c.id).length;
  d.style.display = "block";
  d.innerHTML = `<h3>${c.name}</h3>
    <div class="row"><span>类型</span><span>${c.kind === "component" ? "军种组成司令部" : "下属联合司令部"}</span></div>
    <div class="row"><span>司令部驻地</span><span>${c.hq || "-"}</span></div>
    <div class="row"><span>下辖基地</span><span>${cnt} 个</span></div>
    <div class="src">上报链路: 基地 → ${c.id} → INDOPACOM (逐跳审计)</div>`;
}
function showDetail(b) {
  const d = document.getElementById("netdetail");
  d.style.display = "block";
  const state = b.ally ? '<span style="color:#ffb545">盟友 · 准入可变</span>'
    : '<span style="color:#2fe08a">美方 · 完全准入</span>';
  d.innerHTML = `<h3>${b.name_cn || b.name}</h3>
    <div class="row"><span>ID</span><span>${b.id}</span></div>
    <div class="row"><span>指挥关系</span><span>${b.command || "-"}</span></div>
    <div class="row"><span>军种 / 单位</span><span>${b.branch} · ${b.unit || "-"}</span></div>
    <div class="row"><span>Tier</span><span>Tier-${b.tier} ${b.tier_label||""}</span></div>
    <div class="row"><span>国家 / 地区</span><span>${b.country}</span></div>
    <div class="row"><span>政治准入</span><span>${state}</span></div>
    <div class="row"><span>跑道 / 兵力</span><span>${b.runway_m || "-"} m · ${b.personnel || "-"}</span></div>
    ${b.hub ? '<div class="row"><span>ACE Hub</span><span style="color:#ffb545">是</span></div>' : ""}
    <div class="src">溯源: CRS ${b.crs_no || "R47589 Table A-1"} · FY2024 BSR ${b.prv_q ? "(PRV Q"+b.prv_q+")" : ""}</div>
    <div class="src">${b.role || ""}</div>`;
}

/* 渲染 (贝塞尔渐变边 + 流动粒子 + 径向发光节点) */
function qpoint(a, c, b, t) {
  const u = 1 - t;
  return { x: u*u*a.x + 2*u*t*c.x + t*t*b.x,
           y: u*u*a.y + 2*u*t*c.y + t*t*b.y };
}
function draw(ts) {
  physics();
  cx.setTransform(1, 0, 0, 1, 0, 0);
  cx.clearRect(0, 0, W, H);
  cx.setTransform(cam.s, 0, 0, cam.s, W/2 - cam.x*cam.s, H/2 - cam.y*cam.s);

  for (const e of edges) {
    if (!visNode(e.a) || !visNode(e.b)) continue;
    const mx = (e.a.x + e.b.x)/2, my = (e.a.y + e.b.y)/2;
    const dx = e.b.x - e.a.x, dy = e.b.y - e.a.y;
    const dd = Math.sqrt(dx*dx + dy*dy) || 1;
    const ctrl = { x: mx + (-dy/dd) * e.k * dd, y: my + (dx/dd) * e.k * dd };
    const g = cx.createLinearGradient(e.a.x, e.a.y, e.b.x, e.b.y);
    g.addColorStop(0, e.color + "66"); g.addColorStop(1, e.color + "22");
    cx.strokeStyle = g; cx.lineWidth = 1.3;
    cx.beginPath(); cx.moveTo(e.a.x, e.a.y);
    cx.quadraticCurveTo(ctrl.x, ctrl.y, e.b.x, e.b.y); cx.stroke();
    const t = (ts/1000 * e.sp + e.ph) % 1;
    const p = qpoint(e.a, ctrl, e.b, t);
    cx.beginPath(); cx.arc(p.x, p.y, 2.1, 0, 7);
    cx.fillStyle = "#dff3ff"; cx.shadowColor = e.color; cx.shadowBlur = 7;
    cx.fill(); cx.shadowBlur = 0;
    const ah = qpoint(e.a, ctrl, e.b, .92);
    const at = qpoint(e.a, ctrl, e.b, 1.0);
    const ang = Math.atan2(at.y - ah.y, at.x - ah.x);
    cx.save(); cx.translate(ah.x, ah.y); cx.rotate(ang);
    cx.beginPath(); cx.moveTo(0, 0); cx.lineTo(-5, 2.6); cx.lineTo(-5, -2.6);
    cx.closePath(); cx.fillStyle = e.color + "88"; cx.fill(); cx.restore();
  }

  for (const n of nodes) {
    if (!visNode(n)) continue;
    const pulse = n.b && n.b.ally ? 1 + .22*Math.sin(ts/420 + n.x*.01) : 1;
    const r = n.r * pulse;
    const g = cx.createRadialGradient(n.x - r*.3, n.y - r*.3, r*.15, n.x, n.y, r);
    g.addColorStop(0, "#ffffff"); g.addColorStop(.35, n.color); g.addColorStop(1, n.color);
    cx.beginPath(); cx.arc(n.x, n.y, r, 0, 7);
    cx.fillStyle = g; cx.shadowColor = n.color; cx.shadowBlur = n.kind === "root" ? 20 : 10;
    cx.fill(); cx.shadowBlur = 0;
    if (n.kind === "command" || n.kind === "root") {
      cx.beginPath(); cx.arc(n.x, n.y, r + 3.5, 0, 7);
      cx.strokeStyle = "rgba(255,255,255,.35)"; cx.lineWidth = 1; cx.stroke();
    }
    if (n.b && n.b.hub) {
      cx.beginPath(); cx.arc(n.x, n.y, r + 4.5, 0, 7);
      cx.strokeStyle = "rgba(255,224,102,.75)"; cx.lineWidth = 1.3; cx.stroke();
    }
    if (n.kind === "command" || n.kind === "root" ||
        (n.kind === "base" && (n.r > 8 || cam.s > 1.35 || mouse.node === n))) {
      cx.font = "10.5px 'Microsoft YaHei'"; cx.textAlign = "center";
      cx.fillStyle = "rgba(223,232,244,.88)";
      cx.fillText(n.id, n.x, n.y - r - 5);
    }
    if (mouse.node === n) {
      cx.beginPath(); cx.arc(n.x, n.y, r + 7, 0, 7);
      cx.strokeStyle = "#fff"; cx.lineWidth = 1.4/cam.s; cx.stroke();
    }
  }
  requestAnimationFrame(draw);
}
requestAnimationFrame(draw);
</script>
</body>
</html>
"""

html = (TEMPLATE
        .replace("__DATA_JSON__", json.dumps(DATA, ensure_ascii=False))
        .replace("__GEN_TIME__", DATA["generated"]))
with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)
print(f"Command Cockpit -> {OUT} ({os.path.getsize(OUT)/1e3:.0f} KB)")
print(f"节点 {DATA['stats']['nodes']} | 指挥边 {DATA['stats']['edges']} | "
      f"盟友站点 {ally_count} | ACE Hub {hub_count} | 覆盖国家 {DATA['stats']['countries']}")
