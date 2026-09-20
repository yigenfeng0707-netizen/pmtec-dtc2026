#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P13 第一级交付物：INDOPACOM 67 站点权威档案 v2

数据源：indopacom_bases_v2.geojson（CRS R47589 Table A-1 全量 66 站点
+ Tinian North Field，FY2024 基地结构报告字段融合，P10 政治准入属性）

产出：INDOPACOM基地档案v2-67实体.html（自包含、可打印）

每站档案字段：CRS 编号 / Tier 分层 / 军种 / 国家 / 坐标 / PRV 四分位 /
FY2024 厂库重置价值与土地面积 / DoD 运营 / 美国领土 / 政治准入不确定性 /
ACE Hub / SCARS / LVC 层 / VS26 角色 / 人员 / 跑道
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
GEOJSON = os.path.join(ROOT, "indopacom_bases_v2.geojson")
OUTPUT = os.path.join(ROOT, "INDOPACOM基地档案v2-67实体.html")

TIER_NAMES = {
    1: "Tier-1 核心枢纽",
    2: "Tier-2 主要作战 / 纵深",
    3: "Tier-3 前沿节点",
    4: "Tier-4 盟友 / EDCA / 第二岛链以远",
}

STATE_CN = {"full": "全面准入", "restricted": "有限准入", "denied": "准入被拒"}


def precision_grade(p):
    """P13 修复#7: 坐标精度等级标注（依据 data_source 溯源链）。"""
    src = p.get("data_source", "")
    bid = p.get("id", "")
    if "TINIAN" in bid.upper():
        return "B（特殊站点，计划允许降级精度）"
    if "web-verified" in src:
        return "A（CRS + FY2024 + Web 多源交叉验证）"
    if src.startswith("v1"):
        return "A-（P1-P8 多源验证沿用）"
    return "B（单源，建议复核）"


def esc(v):
    return str(v if v is not None else "—")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    with open(GEOJSON, encoding="utf-8") as f:
        gj = json.load(f)
    props = [ft["properties"] for ft in gj["features"]]

    # 按 Tier -> 国家分组
    groups = {}
    for p in props:
        groups.setdefault(p.get("tier", 4), {}).setdefault(
            p.get("country", "其他"), []
        ).append(p)

    sections = ""
    idx_rows = ""
    crs_seq = 0
    for tier in sorted(groups):
        tier_label = TIER_NAMES.get(tier, f"Tier-{tier}")
        sections += f"<h2>{tier_label}（{sum(len(v) for v in groups[tier].values())} 站）</h2>\n"
        for country in sorted(groups[tier]):
            sections += f"<h3>{esc(country)}</h3>\n"
            for p in sorted(groups[tier][country], key=lambda x: x.get("id", "")):
                crs_seq += 1
                bid = esc(p.get("id"))
                idx_rows += (
                    f"<tr><td>{crs_seq}</td><td>{bid}</td><td>{esc(p.get('name'))}</td>"
                    f"<td>{esc(p.get('branch'))}</td><td>Tier-{p.get('tier')}</td>"
                    f"<td>{esc(p.get('fy24_prv_quartile'))}</td>"
                    f"<td>{esc(p.get('access_uncertainty'))}</td>"
                    f"<td>{esc(precision_grade(p))}</td></tr>\n"
                )
                au = p.get("access_uncertainty")
                pol_cell = (
                    f"准入不确定性 {au:.2f}" if isinstance(au, (int, float))
                    else "美国主权站点（无准入约束）"
                )
                sections += f"""
<div class="card">
  <div class="head"><span class="cid">#{crs_seq:02d}</span>
    <b>{esc(p.get('name'))}</b>
    <span class="cn">{esc(p.get('name_cn'))}</span>
    <span class="bid">{bid}</span></div>
  <table>
    <tr><th>CRS 编号</th><td>{esc(p.get('crs_no'))}（{esc(p.get('crs_service'))}）</td>
        <th>Tier</th><td>Tier-{p.get('tier')}</td></tr>
    <tr><th>军种</th><td>{esc(p.get('branch'))}</td>
        <th>国家/地区</th><td>{esc(p.get('country'))} · {esc(p.get('region'))}</td></tr>
    <tr><th>坐标</th><td colspan="3">{esc(p.get('geometry_lat'))}, {esc(p.get('geometry_lon'))}</td></tr>
    <tr><th>FY2024 PRV</th><td>四分位 {esc(p.get('fy24_prv_quartile'))} · {esc(p.get('fy24_prv_musd'))} MUSD</td>
        <th>土地面积</th><td>{esc(p.get('fy24_total_acres'))} acres</td></tr>
    <tr><th>FY2024 建筑</th><td>自有 {esc(p.get('fy24_bldgs_owned'))} / 租赁 {esc(p.get('fy24_bldgs_leased'))} / 其他 {esc(p.get('fy24_bldgs_other'))}</td>
        <th>BSR 状态</th><td>{esc(p.get('fy24_bsr_status'))}</td></tr>
    <tr><th>DoD 运营</th><td>{'是' if p.get('dod_operated') else '否'}</td>
        <th>美国领土</th><td>{'是' if p.get('us_territory') else '否'}</td></tr>
    <tr><th>ACE Hub</th><td>{'是' if p.get('ace_hub') else '否'}</td>
        <th>SCARS</th><td>{esc(p.get('scars'))}</td></tr>
    <tr><th>LVC 层</th><td>{esc(p.get('lvc_layer'))}</td>
        <th>VS26 角色</th><td>{esc(p.get('vs26_role'))}</td></tr>
    <tr><th>人员</th><td>{esc(p.get('personnel'))}</td>
        <th>跑道</th><td>{esc(p.get('runway_m'))} m</td></tr>
    <tr><th>坐标精度（P13）</th><td colspan="3">{esc(precision_grade(p))}</td></tr>
    <tr><th>政治准入（P10）</th><td colspan="3">{pol_cell}</td></tr>
    <tr><th>DTB 映射</th><td colspan="3">{esc(p.get('dtb_mapping'))} · ASDA: {esc(p.get('asda_mapping'))}</td></tr>
  </table>
</div>"""

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>INDOPACOM 基地权威档案 v2 — 67 实体</title>
<style>
  body {{ font-family: 'Segoe UI','Microsoft YaHei',sans-serif; background: #f6f8fa; color: #1f2328; margin: 0; padding: 32px; }}
  h1 {{ font-size: 24px; border-bottom: 3px solid #0969da; padding-bottom: 10px; }}
  h2 {{ font-size: 18px; color: #0969da; margin-top: 36px; border-bottom: 1px solid #d0d7de; padding-bottom: 6px; }}
  h3 {{ font-size: 15px; color: #57606a; margin: 20px 0 8px; }}
  .meta {{ color: #57606a; font-size: 13px; }}
  .card {{ background: #fff; border: 1px solid #d0d7de; border-radius: 8px; margin: 10px 0; overflow: hidden; page-break-inside: avoid; }}
  .head {{ background: #ddf4ff; padding: 8px 14px; font-size: 14px; }}
  .head .cid {{ color: #0969da; font-weight: 700; margin-right: 8px; }}
  .head .cn {{ color: #57606a; margin-left: 10px; }}
  .head .bid {{ float: right; font-family: Consolas, monospace; color: #57606a; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
  th {{ background: #f6f8fa; text-align: left; width: 130px; color: #57606a; font-weight: 600; }}
  th, td {{ border-bottom: 1px solid #eaeef2; padding: 5px 14px; }}
  .idx {{ background: #fff; border: 1px solid #d0d7de; border-radius: 8px; border-collapse: separate; }}
  .idx th {{ background: #0969da; color: #fff; }}
  .idx td, .idx th {{ padding: 4px 10px; font-size: 12px; }}
  @media print {{ body {{ padding: 0; background: #fff; }} }}
</style>
</head>
<body>
<h1>INDOPACOM 基地权威档案 v2（67 实体）</h1>
<p class="meta">数据溯源：CRS R47589 Table A-1（66 站点）+ Tinian North Field 特殊保留 ｜
FY2024 DoD 基地结构报告（PRV 四分位 / 建筑与土地）｜ CRS IF12175（指挥架构）｜
RAND RRA967-2（政治准入属性）｜ 根深叶茂团队 · 2026-09-12</p>

<h2>总索引</h2>
<table class="idx">
<tr><th>#</th><th>ID</th><th>名称</th><th>军种</th><th>Tier</th><th>PRV 四分位</th><th>准入不确定性</th><th>坐标精度</th></tr>
{idx_rows}
</table>

{sections}

<p class="meta">生成脚本：generate_base_docs_v2.py ｜ 数据文件：indopacom_bases_v2.geojson ｜ 共 {len(props)} 实体</p>
</body>
</html>"""

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[P13] 基地档案 v2 生成: {OUTPUT} ({len(props)} 实体, {len(html):,} bytes)")


if __name__ == "__main__":
    main()
