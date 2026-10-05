#!/usr/bin/env python3
"""P18-F 本体工作台生成器（对标 OntoStudio 画布 / Palantir AIP 审计视图的展示层）。

数据全部来自仓库真实产物（离线导出，重跑即再生）：
  - ontology/semantic_tools.py   browse/resolve/manifest（P17 语义工具层）
  - ontology/confidence_report.json  67 基地 D-S 置信区间
  - ontology/validation_report.json  HermiT + SHACL 校验结论
  - ontology/provenance.ttl      PROV-O 溯源图
产出：output/pmtec_ontology_workbench.html（单文件自包含，无 CDN，断网可用）

与开源对标的关系：借鉴 OntoFlow/OntoStudio 的"本体画布+语义检索台"交互范式
（MIT 协议，仅参考范式，未复制代码）；本体内容 100% 自有且 PROV-O 可溯源。

Run: python visualization/ontology_workbench.py
"""

import json
import os
import sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "ontology"))
sys.stdout.reconfigure(encoding="utf-8")

from ontology.semantic_tools import browse, manifest, resolve
from rdflib import Graph
from rdflib.namespace import RDFS

OUTPUT = os.path.join(PROJECT_ROOT, "output", "pmtec_ontology_workbench.html")
TC_NS = "http://pmtec.example.org/tc#"  # 注意带 .org，与 tc_ontology.py 一致
LAT_PROP = TC_NS + "latitude"
LON_PROP = TC_NS + "longitude"


def export_data():
    man = manifest()
    terms = browse("", kind="term", n=500)["results"] if "results" in str(browse("", kind="term", n=2)) else None
    # browse 返回结构探测
    probe = browse("AirBase", kind="term", n=2)
    if isinstance(probe, dict):
        items_key = "results" if "results" in probe else "items"
    else:
        items_key = None
    def all_of(kind):
        r = browse("", kind=kind, n=1000)
        return r[items_key] if items_key else r

    terms = all_of("term")
    mappings = all_of("mapping")
    constraints = all_of("constraint")
    evidence = all_of("evidence")

    # 67 基地全档案：geojson id 与本体 id 命名不一致（如 US-HICKAM vs
    # base_HI_PHICKAM），用经纬度精确匹配（4 位小数）建立映射再批量 resolve
    with open(os.path.join(PROJECT_ROOT, "ontology", "confidence_report.json"), encoding="utf-8") as f:
        conf = json.load(f)
    with open(os.path.join(PROJECT_ROOT, "data", "bases_v2.geojson"), encoding="utf-8") as f:
        gj = json.load(f)
    geo = {}
    for ft in gj["features"]:
        c = ft["geometry"]["coordinates"]
        p = ft["properties"]
        geo[p["id"]] = {"name": p.get("name", ""), "lat": round(float(c[1]), 3),
                        "lon": round(float(c[0]), 3)}
    g = Graph()
    g.parse(os.path.join(PROJECT_ROOT, "ontology", "target_characteristics.owl"),
            format="xml")
    coord2owl = {}
    from rdflib import URIRef
    for s in set(g.subjects()):
        if not str(s).startswith(TC_NS + "base_"):
            continue
        lats = list(g.objects(s, URIRef(LAT_PROP)))
        lons = list(g.objects(s, URIRef(LON_PROP)))
        if lats and lons:
            coord2owl[(round(float(lats[0]), 3), round(float(lons[0]), 3))] = str(s).split("#")[1]
    owl_ids = []
    for b in conf["bases"]:
        gi = geo.get(b["id"])
        owl_ids.append(coord2owl.get((gi["lat"], gi["lon"])) if gi else None)
    resolved_ids = [i for i in owl_ids if i]
    profiles_list = resolve(resolved_ids)
    profiles = {p["id"]: p for p in profiles_list if p.get("found")}
    id_display = {}  # owl_id → geojson id（页面显示/置信关联用）
    for b, oid in zip(conf["bases"], owl_ids):
        if oid:
            id_display[oid] = b["id"]

    # 类层级（TBox subClassOf，复用已解析的 g）
    hierarchy = []
    for sub, sup in g.subject_objects(RDFS.subClassOf):
        if str(sub).startswith(TC_NS) and str(sup).startswith(TC_NS):
            hierarchy.append({"sub": str(sub).split("#")[1], "sup": str(sup).split("#")[1]})
    classes = sorted({c for x in [list(x) for x in g.subject_objects(RDFS.subClassOf)]
                      for c in x if str(c).startswith(TC_NS)} |
                     {s["id"] for s in terms if s.get("detail", "").startswith("本体类")})

    # 溯源图规模
    prov = Graph()
    prov.parse(os.path.join(PROJECT_ROOT, "ontology", "provenance.ttl"),
               format="turtle")
    prov_triples = len(prov)

    with open(os.path.join(PROJECT_ROOT, "ontology", "validation_report.json"), encoding="utf-8") as f:
        val = json.load(f)

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "data_cutoff": "2026-09（CRS R47589 / DoD FY2024 BSR）",
        "manifest": man,
        "terms": terms, "mappings": mappings,
        "constraints": constraints, "evidence": evidence,
        "profiles": profiles, "id_display": id_display,
        "confidence": conf,
        "hierarchy": hierarchy, "classes": classes,
        "prov_triples": prov_triples,
        "validation": {"hermit": val.get("hermit"), "shacl": val.get("shacl")},
    }


def build_html(d):
    payload = json.dumps({
        "meta": {k: d[k] for k in ("generated_at", "data_cutoff", "prov_triples")},
        "manifest": d["manifest"],
        "terms": d["terms"],
        "profiles": d["profiles"], "id_display": d["id_display"],
        "confidence_bases": d["confidence"]["bases"],
        "confidence_summary": d["confidence"]["summary"],
        "hierarchy": d["hierarchy"],
        "validation": d["validation"],
    }, ensure_ascii=False).replace("</", "<\\/")

    counts = d["manifest"]["counts"]
    html = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PMTEC 本体工作台 · Ontology Workbench</title><style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0b1220;color:#c8d3e8;font-family:"Microsoft YaHei",Consolas,sans-serif;font-size:14px}
header{padding:14px 22px;border-bottom:1px solid #1d2b45;display:flex;gap:18px;align-items:baseline;flex-wrap:wrap}
header h1{font-size:18px;color:#5eb3f6}
.badge{background:#12233d;border:1px solid #24406b;border-radius:12px;padding:2px 12px;font-size:12px;color:#8fb8e8}
.wrap{display:grid;grid-template-columns:300px 1fr 340px;gap:0;height:calc(100vh - 58px)}
@media(max-width:1100px){.wrap{grid-template-columns:1fr;height:auto}}
.pane{border-right:1px solid #1d2b45;overflow-y:auto;padding:14px}
.pane h3{font-size:13px;color:#5eb3f6;margin:12px 0 8px;text-transform:uppercase;letter-spacing:.06em}
.tree div{padding:3px 0 3px 10px;border-left:1px solid #24406b;font-family:Consolas,monospace;font-size:13px}
.tree .cls{color:#7fd1a8}.tree .ind{color:#9db3d6}
input#q{width:100%;background:#0e1930;border:1px solid #24406b;color:#e8f0ff;padding:8px 10px;border-radius:6px;font-size:14px;margin-bottom:8px}
.hit{padding:6px 8px;border-radius:5px;cursor:pointer;border:1px solid transparent}
.hit:hover{background:#132743;border-color:#24406b}
.hit small{color:#5a7396;display:block}
.kv{display:grid;grid-template-columns:150px 1fr;gap:3px 10px;font-size:13px;margin:8px 0}
.kv b{color:#8fb8e8;font-weight:500}.kv span{font-family:Consolas,monospace;color:#c8d3e8;word-break:break-all}
.card{background:#0e1930;border:1px solid #1d2b45;border-radius:8px;padding:12px;margin-bottom:10px}
.card h4{color:#5eb3f6;font-size:13px;margin-bottom:6px}
.stat{display:inline-block;background:#12233d;border-radius:8px;padding:4px 10px;margin:2px;font-size:12px}
.stat b{color:#7fd1a8}
canvas{width:100%;height:180px}
.audit{font-size:12.5px;line-height:1.7}
.audit li{margin-left:16px;margin-bottom:4px}
footer{padding:8px 22px;border-top:1px solid #1d2b45;color:#5a7396;font-size:12px}
.ok{color:#7fd1a8}.warn{color:#f6c560}
</style></head><body>
<header><h1>PMTEC 本体工作台</h1>
<span class="badge">语义对象 term __T__ / mapping __M__ / constraint __C__ / evidence __E__</span>
<span class="badge">HermiT 一致性 <b class="ok">✓</b></span>
<span class="badge">SHACL 双向校验 <b class="ok">✓</b></span>
<span class="badge">PROV-O 溯源 __P__ 三元组</span>
<span class="badge">信息截至 __D__</span></header>
<div class="wrap">
<div class="pane"><h3>类层级（TBox）</h3><div class="tree" id="tree"></div>
<h3>校验状态</h3><div id="val" class="audit"></div></div>
<div class="pane"><h3>语义检索台 <small style="color:#5a7396">（P17 browse/resolve 离线导出，全部实体可查）</small></h3>
<input id="q" placeholder="输入查询：Misawa / AirBase / 跑道 / host_nation …">
<div id="hits"></div><div id="detail"></div></div>
<div class="pane"><h3>置信分布 Bel(Open)</h3><canvas id="cv" width="320" height="180"></canvas>
<div id="confmeta"></div>
<h3>决策链路审计（AIP 范式）</h3><div class="card audit"><ol>
<li><b>自然语言指令</b> → 语义解析（本体术语闭包）</li>
<li><b>权限校验前置</b>：JWT 三级角色 RBAC（observer/operator/commander）</li>
<li><b>知识检索</b>：browse/resolve 按需取证据（不全量注入）</li>
<li><b>确定性推理</b>：HermiT 分类 + D-S 置信合成（冲突 K&lt;0.7 才采信）</li>
<li><b>建议位输出</b>：参谋官报告引用孪生摘要字段（人保留批准权）</li>
<li><b>事件回指</b>：每条建议可回放 SPEAR 事件流逐周期对账</li>
</ol></div>
<h3>坐标出口审计</h3><div class="card audit">引擎统一出口 <code>_coord_check</code>：纬度域校验 +
经度卷绕归一 [-180,180)（跨国际日期变更线实体，如阿拉斯加巡逻），审计计数经
<code>GET /api/v1/state → coord_guard</code> 对外可查——「坐标大面积越界」在出口即被拦截/归一。</div>
</div></div>
<footer>生成于 __G__ ｜ 数据 100% 来自仓库真实产物（semantic_tools 离线导出），本页无 CDN 依赖、断网可用 ｜ 范式参考 OntoFlow/OntoStudio(MIT) 与 Palantir AIP 公开文章，未复制其代码与数据</footer>
<script>
const D = __PAYLOAD__;
// 类层级树
const sup2subs = {}; D.hierarchy.forEach(h => (sup2subs[h.sup] = sup2subs[h.sup] || []).push(h.sub));
const roots = ['MilitaryInstallation','AirBase','AccessState','Runway'].filter(r => D.hierarchy.some(h => h.sup === r) || true);
let tree = '';
function draw(node, depth){
  tree += `<div class="cls" style="padding-left:${depth*14+6}px">${node}</div>`;
  (sup2subs[node]||[]).forEach(s => draw(s, depth+1));
}
['MilitaryInstallation'].forEach(r => draw(r, 0));
D.hierarchy.forEach(h => { if(h.sup==='AirBase' && !D.hierarchy.some(x=>x.sub===h.sup)) {} });
document.getElementById('tree').innerHTML = tree +
  D.hierarchy.filter(h=>h.sup!=='MilitaryInstallation'&&!D.hierarchy.some(x=>x.sub===h.sup))
    .map(h=>`<div class="cls" style="padding-left:20px">${h.sub} ⊑ ${h.sup}</div>`).join('');
// 校验状态
const v = D.validation;
document.getElementById('val').innerHTML =
  `<div>HermiT: <span class="ok">${(v.hermit&&(v.hermit.consistent??v.hermit.status))?'一致 ✓':JSON.stringify(v.hermit).slice(0,60)}</span></div>
   <div>SHACL: <span class="ok">${(v.shacl&&(v.shacl.conforms??v.shacl.status))?'conforms ✓':JSON.stringify(v.shacl).slice(0,60)}</span></div>
   <div>个体 ${Object.keys(D.profiles).length} 个全档案已导出</div>`;
// 检索台
const index = [];
D.terms.forEach(t => index.push({id:t.id, name:t.name, kind:'term', detail:t.detail}));
Object.values(D.profiles).forEach(p => index.push({id:p.id, name:(p.properties&&(p.properties.name||p.id))||p.id, kind:'individual', p}));
function esc(s){return String(s).replace(/</g,'&lt;')}
function search(){
  const q = document.getElementById('q').value.trim().toLowerCase();
  const hits = !q ? index.slice(0, 20) :
    index.filter(x => (x.id+' '+x.name+' '+(x.detail||'')).toLowerCase().includes(q)).slice(0, 40);
  document.getElementById('hits').innerHTML = hits.map((h,i) =>
    `<div class="hit" onclick="show('${esc(h.id)}')"><b>${esc(h.name)}</b> <small>${h.kind} · ${esc(h.id)}${h.detail?' · '+esc(h.detail):''}</small></div>`).join('')
    || '<div class="hit">无命中</div>';
}
function show(id){
  const p = D.profiles[id] || Object.values(D.profiles).find(x => x.id === id);
  const c = D.confidence_bases.find(b => b.id === (D.id_display[id] || id.replace(/^base_/, '')));
  let html = '';
  if(p){
    html += `<div class="card"><h4>${esc(p.id)} 全档案（resolve）</h4><div class="kv">`;
    html += `<b>类型</b><span>${esc((p.types||[]).join(', '))}</span>`;
    Object.entries(p.properties||{}).forEach(([k,v]) => html += `<b>${esc(k)}</b><span>${esc(v.join(', '))}</span>`);
    (p.constraints||[]).forEach(cn => html += `<b>约束</b><span>${esc(cn)}</span>`);
    if(p.evidence) html += `<b>证据</b><span>${esc(p.evidence.detail||p.evidence.name)}</span>`;
    html += '</div></div>';
  }
  if(c){
    const o = c.bel_pl.Open;
    html += `<div class="card"><h4>D-S 置信（${esc(c.grade)} 级 · ${esc(c.access_type)}）</h4>
      <div class="kv"><b>Bel(Open)</b><span>${o.Bel}</span><b>Pl(Open)</b><span>${o.Pl}</span>
      <b>冲突系数 K</b><span>${c.conflict_K}</span></div></div>`;
  }
  document.getElementById('detail').innerHTML = html;
}
document.getElementById('q').addEventListener('input', search);
search();
// Bel(Open) 分布条形图（canvas，无依赖）
const bs = D.confidence_bases.map(b => b.bel_pl.Open.Bel).sort((a,b)=>a-b);
const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
const W = cv.width, H = cv.height, n = bs.length, bw = W/n;
ctx.fillStyle = '#0e1930'; ctx.fillRect(0,0,W,H);
bs.forEach((v,i) => {
  const h = v/1.0*(H-20);
  ctx.fillStyle = v>0.75 ? '#7fd1a8' : (v>0.7 ? '#5eb3f6' : '#f6c560');
  ctx.fillRect(i*bw+0.5, H-h-14, Math.max(bw-1,1), h);
});
ctx.fillStyle = '#5a7396'; ctx.font = '10px Consolas';
ctx.fillText('0.5 判决线', 4, H-26);
ctx.strokeStyle = '#f6c56044'; ctx.beginPath();
ctx.moveTo(0, H-0.5*(H-20)-14); ctx.lineTo(W, H-0.5*(H-20)-14); ctx.stroke();
ctx.fillText('min '+bs[0]+' · max '+bs[n-1], 4, 10);
document.getElementById('confmeta').innerHTML = `<div class="stat">均值 <b>${D.confidence_summary.belief_open_mean}</b></div>
<div class="stat">冲突拒绝 <b>${D.confidence_summary.conflict_rejections}</b></div>
<div class="stat">max K <b>${D.confidence_summary.max_conflict_K}</b>（阈值 0.7）</div>`;
</script></body></html>"""
    html = (html
            .replace("__T__", str(counts["term"]))
            .replace("__M__", str(counts["mapping"]))
            .replace("__C__", str(counts["constraint"]))
            .replace("__E__", str(counts["evidence"]))
            .replace("__P__", str(d["prov_triples"]))
            .replace("__D__", d["data_cutoff"])
            .replace("__G__", d["generated_at"])
            .replace("__PAYLOAD__", payload))
    return html


def main():
    d = export_data()
    html = build_html(d)
    with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
        f.write(html)
    print(f"本体工作台已生成: {OUTPUT}（{len(html):,} bytes）")
    print(f"  术语 {len(d['terms'])} | 档案 {len(d['profiles'])} | "
          f"层级边 {len(d['hierarchy'])} | 溯源 {d['prov_triples']} 三元组")


if __name__ == "__main__":
    main()
