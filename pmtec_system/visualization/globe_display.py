#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P15 全球地球总览 — MapLibre GL globe 投影单文件可视化.

手法借鉴开源 OSINT 平台 Osiris（maplibre-gl globe + 公开数据聚合），
MapLibre GL JS 5.9.0 本地 vendor（visualization/vendor/，生成时复制到
output/assets/，答辩断网可用；在线 CDN 仅作兜底）。
数据全部来自 PMTEC 真实产物:
  - data/bases_v2.geojson (67 权威实体)
  - output/pmtec_spear_report.json (饱和攻击 SPEAR 回放: 发射弧线 + 拦截判定)
  - models/political_access.py 灰色地带演化确定性回放 (seed=42, 与
    scripts/political_resilience_analysis.py 实验 2 及演示动画同源:
    c3 主权打击峰值 9 站点 Denied / 可用基地 67→58)
产物: output/pmtec_globe.html
"""
import json
import math
import os
import shutil
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEOJSON_PATH = os.path.join(PROJECT_ROOT, "data", "bases_v2.geojson")
SPEAR_PATH = os.path.join(PROJECT_ROOT, "output", "pmtec_spear_report.json")
OUT_PATH = os.path.join(PROJECT_ROOT, "output", "pmtec_globe.html")
VENDOR_DIR = os.path.join(PROJECT_ROOT, "visualization", "vendor")
ASSETS_DIR = os.path.join(PROJECT_ROOT, "output", "assets")

# 想定发射区（第二炮兵发射场近似位置，属仿真想定数据）
LAUNCH_ZONES = {
    "DF-17": (26.65, 118.15),   # 南平方向（高超滑翔）
    "DF-26": (31.05, 109.90),   # 内陆纵深（中导）
    "DF-21": (29.60, 106.50),
}


def load_bases():
    gj = json.load(open(GEOJSON_PATH, encoding="utf-8"))
    bases = []
    for ft in gj["features"]:
        lon, lat = ft["geometry"]["coordinates"][:2]
        p = ft["properties"]
        bases.append({
            "id": p["id"], "name": p["name"], "name_cn": p.get("name_cn", ""),
            "country": p.get("country", ""), "branch": p.get("branch", ""),
            "tier": p.get("tier", 3), "tier_label": p.get("tier_label", ""),
            "lat": lat, "lon": lon,
            "unit": p.get("unit", ""), "aircraft": p.get("aircraft", ""),
            "runway_m": p.get("runway_m"), "personnel": p.get("personnel"),
            "access_uncertainty": p.get("access_uncertainty", ""),
            "ace_hub": bool(p.get("ace_hub")),
        })
    return bases


def load_political():
    """灰色地带演化确定性回放 (seed=42, 与实验 2 / 演示动画同源).

    返回 (peak_snapshot, 全程限入峰值, transitions, final_snapshot, snaps):
    peak_snapshot 为 Denied 最多时刻的逐基地准入态, 用于地球静态着色;
    snaps 为逐周期快照序列, 驱动前端推演回放。
    """
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    from models.political_access import (EVENT_GREY_ZONE, EVENT_REASSURANCE,
                                         EVENT_SOVEREIGN_STRIKE, AccessState,
                                         PoliticalAccessModel, PoliticalEvent)
    gj = json.load(open(GEOJSON_PATH, encoding="utf-8"))
    rows = [{"id": p["id"], "country": p.get("country", ""),
             "access_uncertainty": p.get("access_uncertainty")}
            for p in (ft["properties"] for ft in gj["features"])]
    all_ids = [r["id"] for r in rows]

    m = PoliticalAccessModel.from_bases(rows, seed=42)

    def snapshot(cycle, label):
        states = {bid: s.state.value for bid, s in m.sites.items()}
        return {"cycle": cycle, "label": label, "states": states,
                "avail": len(m.available_bases(all_ids)),
                "denied": sum(1 for v in states.values() if v == "denied"),
                "restricted": sum(1 for v in states.values() if v == "restricted")}

    snaps = [snapshot(0, "baseline")]
    script = [(1, "grey_zone PH x1.0", 0.3,
               [PoliticalEvent(EVENT_GREY_ZONE, "Philippines", intensity=1.0, cycle=1)]),
              (2, "grey_zone PH x0.8 + 高导弹活动", 0.7,
               [PoliticalEvent(EVENT_GREY_ZONE, "Philippines", intensity=0.8, cycle=2)]),
              (3, "sovereign_strike PH x0.9", 0.3,
               [PoliticalEvent(EVENT_SOVEREIGN_STRIKE, "Philippines", intensity=0.9, cycle=3)])]
    for c, label, ma, ev in script:
        m.update_cycle(cycle=c, missile_activity=ma, events=ev)
        snaps.append(snapshot(c, label))
    for c in range(4, 13):
        ev = ([PoliticalEvent(EVENT_REASSURANCE, "Philippines", intensity=0.9, cycle=c)]
              if c <= 6 else [])
        m.update_cycle(cycle=c, events=ev)
    snaps.append(snapshot(12, "reassurance + recovery"))

    peak = max(snaps, key=lambda s: s["denied"])
    peak_res = max(s["restricted"] for s in snaps)
    transitions = []
    prev = {}
    for s in snaps:
        for bid, st in s["states"].items():
            old = prev.get(bid, "full")
            if st != old:
                transitions.append({"cycle": s["cycle"], "base_id": bid,
                                    "from": old, "to": st})
        prev = dict(s["states"])
    return peak, peak_res, transitions, snaps[-1], snaps


def load_warhead(bases_by_id):
    """重放 SPEAR 事件: 发射弧线 + 拦截标记."""
    r = json.load(open(SPEAR_PATH, encoding="utf-8"))
    events = sorted(r["events"], key=lambda e: e["timestamp"])

    launches, pending_by_type = [], {}
    for e in events:
        t = e["event_type"]
        if t == "missile_launch":
            d = e["data"]
            tgt = bases_by_id.get(d["target"])
            if not tgt:
                continue
            origin = LAUNCH_ZONES.get(d["missile_type"], LAUNCH_ZONES["DF-26"])
            item = {"type": d["missile_type"], "salvo": d.get("salvo_size", 1),
                    "cycle": d.get("asda_cycle"), "target": tgt["id"],
                    "target_name": tgt["name_cn"] or tgt["name"],
                    "from": list(origin), "to": [tgt["lon"], tgt["lat"]],
                    "intercepts": []}
            launches.append(item)
            pending_by_type.setdefault(d["missile_type"], []).append(item)
        elif t in ("intercept_success", "intercept_fail"):
            d = e["data"]
            q = pending_by_type.get(d.get("missile_type") or "")
            if q:
                q[0]["intercepts"].append({
                    "ok": t == "intercept_success",
                    "p": round(float(d.get("probability", 0)), 3),
                    "strategy": d.get("intercept_strategy", "")})
                if sum(1 for x in q[0]["intercepts"] if x["ok"]) >= q[0]["salvo"]:
                    q.pop(0)

    n_ok = sum(1 for e in events if e["event_type"] == "intercept_success")
    n_fail = sum(1 for e in events if e["event_type"] == "intercept_fail")
    stats = {"intercept_ok": n_ok, "intercept_fail": n_fail}
    return launches, stats


def arc_points(lon1, lat1, lon2, lat2, steps=48, bulge=0.18):
    """三维球面 slerp 大圆弧 + 高度拱起投影回经纬度."""
    def to_vec(lon, lat):
        la, lo = math.radians(lat), math.radians(lon)
        return (math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la))
    v1, v2 = to_vec(lon1, lat1), to_vec(lon2, lat2)
    dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(v1, v2))))
    omega = math.acos(dot)
    out = []
    for i in range(steps + 1):
        f = i / steps
        if omega < 1e-9:
            v = v1
        else:
            s = math.sin(omega)
            a, b = math.sin((1 - f) * omega) / s, math.sin(f * omega) / s
            v = tuple(a * x + b * y for x, y in zip(v1, v2))
        h = 1.0 + bulge * math.sin(math.pi * f)  # 中段拱起
        v = tuple(x * h for x in v)
        lat = math.degrees(math.asin(max(-1, min(1, v[2] / math.sqrt(sum(x * x for x in v))))))
        lon = math.degrees(math.atan2(v[1], v[0]))
        out.append([round(lon, 3), round(lat, 3)])
    return out


def arc_mid(points, f=0.62):
    return points[int(len(points) * f)]


def edca_ring(lon, lat, radius_km=250, n=48):
    """纬度圈近似缓冲圆."""
    d = radius_km / 111.32
    ring = []
    for i in range(n + 1):
        th = 2 * math.pi * i / n
        la = lat + d * math.cos(th)
        lo = lon + d * math.cos(th) / max(0.2, math.cos(math.radians(lat)))
        ring.append([round(lo, 3), round(la, 3)])
    return ring


def build_geojson(bases, final_state, launches):
    feats = []
    for b in bases:
        st = final_state.get(b["id"], "full")
        feats.append({"type": "Feature", "properties": {**b, "state": st,
                        "_pulse": 0, "_pop": 0,
                        "_statec": ("#ef4444" if st == "denied" else
                                    "#f59e0b" if st == "restricted" else "#16213a")},
                      "geometry": {"type": "Point", "coordinates": [b["lon"], b["lat"]]}})
    arc_feats = []
    burst_feats = []
    for L in launches:
        pts = arc_points(L["from"][0], L["from"][1], L["to"][0], L["to"][1])
        arc_feats.append({"type": "Feature",
                          "properties": {"type": L["type"], "salvo": L["salvo"],
                                          "cycle": L["cycle"], "target": L["target_name"]},
                          "geometry": {"type": "LineString", "coordinates": pts}})
        n_ok = sum(1 for x in L["intercepts"] if x["ok"])
        for k in range(min(n_ok, 3)):
            m = arc_mid(pts, 0.55 + 0.08 * k)
            burst_feats.append({"type": "Feature",
                                "properties": {"ok": True, "target": L["target_name"],
                                               "missile": L["type"], "cycle": L["cycle"]},
                                "geometry": {"type": "Point", "coordinates": m}})
        if any(not x["ok"] for x in L["intercepts"]):
            m = arc_mid(pts, 0.9)
            burst_feats.append({"type": "Feature",
                                "properties": {"ok": False, "target": L["target_name"],
                                               "missile": L["type"], "cycle": L["cycle"]},
                                "geometry": {"type": "Point", "coordinates": m}})
    hub_feats = [{"type": "Feature", "properties": {"name": b["name_cn"] or b["name"]},
                  "geometry": {"type": "Polygon",
                               "coordinates": [edca_ring(b["lon"], b["lat"])]}}
                 for b in bases if b["ace_hub"]]
    return ({"type": "FeatureCollection", "features": feats},
            {"type": "FeatureCollection", "features": arc_feats},
            {"type": "FeatureCollection", "features": burst_feats},
            {"type": "FeatureCollection", "features": hub_feats})


HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PMTEC 全球地球总览 · 政治拒止与饱和拦截</title>
<link href="assets/maplibre-gl-5.9.0.css" rel="stylesheet">
<script src="assets/maplibre-gl-5.9.0.js"></script>
<script>if(!window.maplibregl)document.write('<scr'+'ipt src="https://cdn.jsdelivr.net/npm/maplibre-gl@5.9.0/dist/maplibre-gl.js"><\\/scr'+'ipt>');</script>
<style>
:root{--bg:#05070f;--ink:#e5eaf5;--dim:#8b97b0;--cyan:#22d3ee;--amber:#f59e0b;--red:#ef4444;--green:#34d399}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--ink);font:14px/1.6 "PingFang SC","Microsoft YaHei",system-ui,sans-serif;overflow:hidden}
#map{position:absolute;inset:0}
.hud{position:absolute;top:0;left:0;right:0;padding:14px 20px;display:flex;gap:14px;align-items:center;flex-wrap:nowrap;
 background:linear-gradient(180deg,rgba(5,7,15,.92),transparent);pointer-events:none;z-index:5;overflow:hidden}
.hud h1{font-size:18px;letter-spacing:2px;white-space:nowrap}
.hud h1 em{color:var(--cyan);font-style:normal}
.chips{display:flex;gap:7px;flex-wrap:nowrap}
.chip{border:1px solid #263149;border-radius:20px;padding:2px 10px;font-size:11.5px;color:var(--dim);white-space:nowrap}
.chip b{color:var(--ink);font-size:13px;margin-right:2px}
.chip.red b{color:var(--red)}.chip.green b{color:var(--green)}.chip.amber b{color:var(--amber)}
.chip.cyan b{color:var(--cyan)}
.legend{position:absolute;left:26px;bottom:22px;z-index:5;background:rgba(8,11,22,.86);
 border:1px solid #263149;border-radius:10px;padding:12px 16px;font-size:12px;color:var(--dim)}
.legend div{display:flex;align-items:center;gap:8px;margin:3px 0}
.dot{width:10px;height:10px;border-radius:50%}.ln{width:22px;height:2px}
.tools{position:absolute;right:26px;bottom:22px;z-index:5;display:flex;gap:8px}
.tools button{background:#0d1426;color:var(--ink);border:1px solid #2a3752;border-radius:8px;
 padding:7px 14px;font-size:12px;cursor:pointer}
.tools button:hover{border-color:var(--cyan);color:var(--cyan)}
.maplibregl-popup-content{background:#0d1426!important;color:var(--ink)!important;
 border:1px solid #2a3752;border-radius:10px;font-size:12.5px;padding:12px 14px!important}
.maplibregl-popup-close-button{color:var(--dim)!important;right:4px;top:2px}
.maplibregl-popup-tip{border-top-color:#0d1426!important;border-bottom-color:#0d1426!important}
.pop b{color:var(--cyan)}.pop .row{margin:2px 0;color:var(--dim)}
.pop .st{padding:1px 8px;border-radius:8px;font-size:11px;color:#0b0f1a;font-weight:700}
.foot{position:absolute;left:20px;top:60px;z-index:5;font-size:11px;color:#42506e;pointer-events:none;white-space:nowrap}
</style>
</head>
<body>
<div id="map"></div>
<div class="hud">
  <h1>PMTEC <em>GLOBAL COPE</em> 地球总览</h1>
  <div class="chips">
    <span class="chip"><b>__N_BASES__</b>基地实体</span>
    <span class="chip red"><b>__N_PEAKDENIED__</b>拒止峰值@c__PEAK_CYCLE__（可用 __AVAIL_PEAK__/67）</span>
    <span class="chip amber"><b>__N_PEAKRES__</b>限入峰值（c1-c2）</span>
    <span class="chip"><b>__N_POLTRANS__</b>准入迁移</span>
    <span class="chip"><b>__N_LAUNCH__</b>波齐射/__N_SALVO__弹头</span>
    <span class="chip green"><b>__N_OK__</b>拦截成功</span>
    <span class="chip red"><b>__N_FAIL__</b>逃逸</span>
    <span class="chip cyan"><b id="cyc">c0</b>推演周期</span>
  </div>
</div>
<div class="foot">数据源: bases_v2.geojson · political_access seed=42 确定性回放 · pmtec_spear_report.json 弹道回放 · 自动循环推演</div>
<div class="legend">
  <div><span class="dot" style="background:#60a5fa"></span>Tier-1 枢纽&nbsp;&nbsp;<span class="dot" style="background:#3b82f6;transform:scale(.7)"></span>Tier-2/3</div>
  <div><span class="dot" style="box-shadow:0 0 0 2px var(--red)"></span>Denied（脉冲）&nbsp;&nbsp;<span class="dot" style="box-shadow:0 0 0 2px var(--amber)"></span>Restricted</div>
  <div><span class="ln" style="background:var(--cyan)"></span>DF-17 高超弹道</div>
  <div><span class="ln" style="background:var(--amber)"></span>DF-26/21 中程弹道</div>
  <div><span class="dot" style="background:var(--green);transform:scale(.6)"></span>拦截杀伤 &nbsp;<span class="dot" style="background:var(--red);transform:scale(.6)"></span>突防</div>
  <div><span class="ln" style="border-top:2px dashed #7dd3fc;height:0"></span>EDCA 250km 辐射圈</div>
</div>
<div class="tools">
  <button id="btn-play">⏸ 推演</button>
  <button id="btn-rot">⏸ 自转</button>
  <button id="btn-reset">🌏 视角复位</button>
  <button id="btn-zoom">🔍 西太聚焦</button>
</div>
<script>
const BASES=__BASES_GJ__, ARCS=__ARCS_GJ__, BURSTS=__BURSTS_GJ__, HUBS=__HUBS_GJ__;
const POL=__POL__, TMAX=__TMAX__;
let baseData=JSON.parse(JSON.stringify(BASES)), playing=true;
const FALLBACK={version:8,glyphs:"https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
 sources:{},layers:[{id:"bg",type:"background",paint:{"background-color":"#05070f"}}]};
const map=new maplibregl.Map({container:"map",style:"https://demotiles.maplibre.org/style.json",
 center:[158,16],zoom:2.4,pitch:38,attributionControl:false});
window.map=map; // 演示调试钩子
map.addControl(new maplibregl.NavigationControl({visualizePitch:true}),"top-right");
map.on("error",()=>{ // 在线底图失败(断网)时降级: 纯暗色地球仍承载全部数据层
 if(!window.__fb&&!(map.getStyle()&&map.getStyle().layers&&map.getStyle().layers.length)){
   window.__fb=true; map.setStyle(FALLBACK);}});
function stateColor(s){return s==="denied"?"#ef4444":s==="restricted"?"#f59e0b":"#16213a"}
function boot(){
 if(window.__booted || !map.setProjection) return; window.__booted=true;
 try{map.setProjection({type:"globe"})}catch(_){}
 map.setSky({"sky-color":"#060a16","horizon-color":"#0d1b33","fog-color":"#05070f",
             "sky-horizon-blend":0.35,"horizon-fog-blend":0.4,"fog-ground-blend":0.85,
             "atmosphere-blend":["interpolate",["linear"],["zoom"],0,0.35,6,0.08]});
 map.addSource("hubs",{type:"geojson",data:HUBS});
 map.addSource("arcs",{type:"geojson",data:ARCS});
 map.addSource("bursts",{type:"geojson",data:BURSTS});
 map.addSource("bases",{type:"geojson",data:BASES});
 map.addLayer({id:"hub-ring",type:"line",source:"hubs",
  paint:{"line-color":"#7dd3fc","line-width":0.9,"line-dasharray":[2,3],"line-opacity":0.5}});
 map.addLayer({id:"arc-glow",type:"line",source:"arcs",
  paint:{"line-color":["match",["get","type"],"DF-17","#22d3ee","#f59e0b"],
         "line-width":4.5,"line-opacity":0.10,"line-blur":3}});
 map.addLayer({id:"arc-line",type:"line",source:"arcs",
  paint:{"line-color":["match",["get","type"],"DF-17","#22d3ee","#fbbf24"],
         "line-width":1.5,"line-opacity":0.85}});
 map.addLayer({id:"arc-flow",type:"line",source:"arcs",
  paint:{"line-color":"#ffffff","line-width":2.4,"line-opacity":0.9,
         "line-dasharray":[0.1,4],"line-translate-anchor":"map"}});
 map.addLayer({id:"burst",type:"circle",source:"bursts",
  paint:{"circle-radius":3.4,"circle-color":["match",["get","ok"],true,"#34d399","#ef4444"],
         "circle-stroke-color":"#ffffff","circle-stroke-width":0.6,"circle-opacity":0.95,
         "circle-blur":0.25}});
 map.addLayer({id:"pulse",type:"circle",source:"bases",filter:["==",["get","state"],"denied"],
  paint:{"circle-radius":["get","_pulse"],"circle-opacity":["get","_pop"],
         "circle-color":"#ef4444","circle-blur":0.5}});
 map.addLayer({id:"ring",type:"circle",source:"bases",
  filter:["in",["get","state"],["literal",["denied","restricted"]]],
  paint:{"circle-radius":["match",["get","state"],"denied",8.5,7],
         "circle-opacity":0,"circle-stroke-color":["get","_statec"],
         "circle-stroke-width":1.6,"circle-stroke-opacity":0.9}});
 map.addLayer({id:"base-pt",type:"circle",source:"bases",
  paint:{"circle-radius":["case",["<=",["get","tier"],1],6.5,["<=",["get","tier"],2],4.6,3.4],
         "circle-color":["case",["<=",["get","tier"],1],"#60a5fa",["<=",["get","tier"],2],"#3b82f6","#2b4a8f"],
         "circle-stroke-color":"#dbe7ff","circle-stroke-width":0.7,"circle-opacity":0.95}});
 map.on("click","base-pt",(ev)=>{
   const b=ev.features[0].properties;
   const sc={full:["全面准入","#34d399"],restricted:["有限准入","#f59e0b"],denied:["拒止","#ef4444"]}[b.state]||["权威","#60a5fa"];
   new maplibregl.Popup({maxWidth:"300px",offset:10}).setLngLat(ev.lngLat).setHTML(
    `<div class="pop"><b>${b.name_cn||b.name}</b> · ${b.name}<div class="row">${b.tier_label||("Tier-"+b.tier)} · ${b.branch} · ${b.country} <span class="st" style="background:${sc[1]}">${sc[0]}</span></div>`+
    (b.unit?`<div class="row">部队：${b.unit}</div>`:"")+(b.aircraft?`<div class="row">驻机：${b.aircraft}</div>`:"")+
    (b.runway_m?`<div class="row">跑道 ${b.runway_m}m · ${b.personnel?b.personnel+" 人":""}</div>`:"")+
    (b.access_uncertainty?`<div class="row">准入不确定性：${b.access_uncertainty}</div>`:"")+`</div>`).addTo(map);
 });
 map.on("click","arc-line",(ev)=>{
   const p=ev.features[0].properties;
   new maplibregl.Popup({maxWidth:"240px",offset:8}).setLngLat(ev.lngLat).setHTML(
    `<div class="pop"><b>${p.type} ×${p.salvo}</b><div class="row">目标：${p.target} · 周期 c${p.cycle}</div></div>`).addTo(map);
 });
 function polStateAt(t){let s={};for(const p of POL){if(p.cycle<=t)s=p.states;else break;}return s;}
 function render(t){
   window.__curT=t; const st=polStateAt(t);
   baseData=JSON.parse(JSON.stringify(BASES));
   baseData.features.forEach(ft=>{const s=st[ft.properties.id]||"full";
     ft.properties.state=s;ft.properties._statec=stateColor(s);});
   map.getSource("bases").setData(baseData);
   map.getSource("arcs").setData({type:"FeatureCollection",features:ARCS.features.filter(f=>f.properties.cycle<=t)});
   map.getSource("bursts").setData({type:"FeatureCollection",features:BURSTS.features.filter(f=>f.properties.cycle<=t)});
   document.getElementById("cyc").textContent="c"+t;
  }
 window.render=render; render(0);
 let phase=0;
 setInterval(()=>{ // Denied 脉冲（随当前周期态）
   phase=(phase+1)%24; const f=phase/24;
   const d=JSON.parse(JSON.stringify(baseData));
   d.features.forEach(ft=>{const dn=ft.properties.state==="denied"?1:0;
     ft.properties._pulse=(6+f*16)*dn; ft.properties._pop=0.42*(1-f)*dn;});
   map.getSource("bases").setData(d);
  },70);
 setInterval(()=>{ if(!playing)return; render(window.__curT>=TMAX?0:window.__curT+1); },220);
 let off=0; // 弹道流光
 (function flow(){off-=0.9;
   if(map.getLayer("arc-flow"))map.setPaintProperty("arc-flow","line-dashoffset",off);
   requestAnimationFrame(flow);})();
}
map.on("load",()=>{ if(map.getStyle().layers) boot(); });
map.on("style.load",()=>{ if(!map.getSource("bases")) boot(); });
let rot=true;
// 平滑自转（easeTo 增量旋转）
setInterval(()=>{ if(!rot)return;
 map.easeTo({bearing:map.getBearing()+0.6,duration:1200,easing:t=>t});},1200);
document.getElementById("btn-rot").onclick=e=>{rot=!rot;e.target.textContent=rot?"⏸ 自转":"▶ 自转"};
document.getElementById("btn-play").onclick=e=>{playing=!playing;e.target.textContent=playing?"⏸ 推演":"▶ 推演"};
document.getElementById("btn-reset").onclick=()=>map.easeTo({center:[158,16],zoom:2.4,pitch:38,bearing:0,duration:1500});
document.getElementById("btn-zoom").onclick=()=>map.easeTo({center:[140,22],zoom:4.0,pitch:55,bearing:0,duration:1800});
</script>
</body>
</html>
"""


def main():
    bases = load_bases()
    by_id = {b["id"]: b for b in bases}
    peak, peak_res, transitions, final, snaps = load_political()
    launches, stats = load_warhead(by_id)
    bases_gj, arcs_gj, bursts_gj, hubs_gj = build_geojson(bases, peak["states"], launches)
    tmax = max([s["cycle"] for s in snaps] + [L["cycle"] for L in launches])
    pol_tl = [{"cycle": s["cycle"], "states": s["states"]} for s in snaps]
    html = (HTML
            .replace("__BASES_GJ__", json.dumps(bases_gj, ensure_ascii=False))
            .replace("__ARCS_GJ__", json.dumps(arcs_gj, ensure_ascii=False))
            .replace("__BURSTS_GJ__", json.dumps(bursts_gj, ensure_ascii=False))
            .replace("__HUBS_GJ__", json.dumps(hubs_gj, ensure_ascii=False))
            .replace("__POL__", json.dumps(pol_tl, ensure_ascii=False))
            .replace("__TMAX__", str(tmax))
            .replace("__N_BASES__", str(len(bases)))
            .replace("__N_PEAKDENIED__", str(peak["denied"]))
            .replace("__PEAK_CYCLE__", str(peak["cycle"]))
            .replace("__AVAIL_PEAK__", str(peak["avail"]))
            .replace("__N_PEAKRES__", str(peak_res))
            .replace("__N_POLTRANS__", str(len(transitions)))
            .replace("__N_LAUNCH__", str(len(launches)))
            .replace("__N_SALVO__", str(sum(L["salvo"] for L in launches)))
            .replace("__N_OK__", str(stats["intercept_ok"]))
            .replace("__N_FAIL__", str(stats["intercept_fail"])))
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    os.makedirs(ASSETS_DIR, exist_ok=True)
    for name in ("maplibre-gl-5.9.0.js", "maplibre-gl-5.9.0.css"):
        src = os.path.join(VENDOR_DIR, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(ASSETS_DIR, name))
    print(f"[OK] globe -> {OUT_PATH}")
    print(f"     bases={len(bases)} peak: c{peak['cycle']} denied={peak['denied']} "
          f"restricted={peak['restricted']} (全程限入峰值 {peak_res}) "
          f"avail={peak['avail']}/67 | "
          f"final: denied={final['denied']} restricted={final['restricted']} "
          f"avail={final['avail']}/67 | transitions={len(transitions)} | "
          f"launches={len(launches)} ok={stats['intercept_ok']} fail={stats['intercept_fail']}")


if __name__ == "__main__":
    main()
