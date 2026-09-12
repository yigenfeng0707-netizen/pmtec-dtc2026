#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate base detail docx and QGIS project file for INDOPACOM bases."""

import json
import os
from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

# Load base data
geojson_path = os.path.join("D:/APPs/数字孪生挑战赛", "indopacom_bases.geojson")
with open(geojson_path, "r", encoding="utf-8") as f:
    geojson = json.load(f)

bases = []
for feat in geojson["features"]:
    b = feat["properties"].copy()
    b["lat"] = feat["geometry"]["coordinates"][1]
    b["lon"] = feat["geometry"]["coordinates"][0]
    bases.append(b)

# Sort by region then name
bases.sort(key=lambda x: (x["region"], x["name"]))

# ============================================================
# Generate DOCX
# ============================================================

doc = Document()

# Set default font
style = doc.styles["Normal"]
style.font.name = "Microsoft YaHei"
style.font.size = Pt(10.5)

# Title
title = doc.add_heading("INDOPACOM太平洋战区美军军事基地标绘档案", level=0)
title.alignment = WD_ALIGN_PARAGRAPH.CENTER

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("DTC 2026 数字孪生体挑战赛 | 场景开发赛道 第一级任务")
run.font.size = Pt(12)
run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run(
    f"共 {len(bases)} 个基地 | {len(set(b['region'] for b in bases))} 个区域 | {sum(1 for b in bases if b['ace_hub'])} 个ACE Hub"
)
run.font.size = Pt(10)
run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

doc.add_page_break()

# Table of Contents
doc.add_heading("目录", level=1)
toc_items = [
    "一、任务概述与DTB Model/ASDA闭环框架",
    "二、基地总览表",
    "三、按区域详细档案",
    "  3.1 日本区域",
    "  3.2 关岛区域",
    "  3.3 韩国区域",
    "  3.4 夏威夷区域",
    "  3.5 阿拉斯加区域",
    "  3.6 澳大利亚区域",
    "  3.7 菲律宾区域",
    "  3.8 北马里亚纳群岛区域",
    "四、VS26实战角色与LVC架构映射",
    "五、ACE分布式部署中心-辐条模型",
    "六、DTB Model组件映射总表",
    "七、ASDA闭环映射总表",
]
for item in toc_items:
    p = doc.add_paragraph(item)
    p.paragraph_format.left_indent = Cm(0.5 if not item.startswith("  ") else 1.5)

doc.add_page_break()

# Chapter 1: Overview
doc.add_heading("一、任务概述与DTB Model/ASDA闭环框架", level=1)

doc.add_heading("1.1 任务目标", level=2)
doc.add_paragraph(
    "本档案是DTC 2026数字孪生体挑战赛场景开发赛道第一级任务的交付物之一。"
    "任务要求使用开源GIS工具标绘太平洋战区（INDOPACOM辖区）美军军事基地，"
    "并为每个基地建立详细说明档案。每个基地的档案须体现对DTB Model（数字孪生战场模型）"
    "和ASDA闭环（行动-感知-决策-适应）的理解。"
)

doc.add_heading("1.2 DTB Model四层架构", level=2)
doc.add_paragraph("DTB Model是大赛的核心载体，包含四层架构：")
dtb_items = [
    (
        "作战引擎 (War Engine)",
        "底层仿真引擎，驱动数字孪生战场推演。PMTEC是其核心实现之一，提供LVC三层架构的仿真环境。",
    ),
    (
        "战斗网络 (Battle Network)",
        "连接各基地、平台和传感器的通信指挥网络。每个基地都是网络中的一个节点。",
    ),
    (
        "应用商店 (Application Store)",
        "即插即用的作战应用模块库。每个基地可加载不同的作战能力包（如F-35打击包、反导包、ISR包等）。",
    ),
    (
        "即插即用 (Plug-and-Play)",
        "标准化的接口设计（gRPC/Maven），使各模块可以快速组合部署。基地间可快速共享能力模块。",
    ),
]
for name, desc in dtb_items:
    p = doc.add_paragraph(style="List Bullet")
    run = p.add_run(name + "：")
    run.bold = True
    p.add_run(desc)

doc.add_heading("1.3 ASDA闭环", level=2)
doc.add_paragraph("ASDA闭环是大赛提出的作战认知框架，四个环节形成完整闭环：")
asda_items = [
    (
        "行动 (Act)",
        "执行作战行动，如战机起飞、导弹发射、部队部署。每个基地都有行动能力。",
    ),
    (
        "感知 (Sense)",
        "收集情报，如雷达探测、卫星侦察、电子侦察。基地的传感器是感知环节。",
    ),
    (
        "决策 (Decide)",
        "基于感知信息做出决策，如目标分配、兵力调度。指挥中心是决策环节。",
    ),
    (
        "适应 (Adapt)",
        "根据战场变化调整策略，如基地分散部署、装备转移、战术变更。ACE是适应的体现。",
    ),
]
for name, desc in asda_items:
    p = doc.add_paragraph(style="List Bullet")
    run = p.add_run(name + "：")
    run.bold = True
    p.add_run(desc)

doc.add_heading("1.4 VS26（Valiant Shield 2026）实战参考", level=2)
doc.add_paragraph(
    "2026年6月的VS26演习是本档案的重要参考。VS26在关岛周边展示了360度关岛防御（GDS）、"
    "LVC三层训练架构（实时-虚拟-构建）、SPEAR回放系统、JAD-AI智能代理等关键能力。"
    "每个基地的VS26角色标注体现了其在实战演习中的真实功能定位。"
)

doc.add_page_break()

# Chapter 2: Overview Table
doc.add_heading("二、基地总览表", level=1)

table = doc.add_table(rows=1, cols=6)
table.style = "Light Grid Accent 1"
table.alignment = WD_TABLE_ALIGNMENT.CENTER
hdr = table.rows[0].cells
headers = ["编号", "基地名称", "国家/地区", "军种", "区域", "ACE Hub"]
for i, h in enumerate(headers):
    hdr[i].text = h
    for p in hdr[i].paragraphs:
        for r in p.runs:
            r.bold = True
            r.font.size = Pt(9)

for b in bases:
    row = table.add_row().cells
    row[0].text = b["id"]
    row[1].text = f"{b['name']}\n{b['name_cn']}"
    row[2].text = b["country"]
    row[3].text = b["branch"]
    row[4].text = b["region"]
    row[5].text = "是" if b["ace_hub"] else "否"
    for cell in row:
        for p in cell.paragraphs:
            for r in p.runs:
                r.font.size = Pt(8)

doc.add_page_break()

# Chapter 3: Detailed base profiles by region
doc.add_heading("三、按区域详细档案", level=1)

regions_order = [
    ("Japan-North", "3.1 日本区域（北部）"),
    ("Japan-Central", "3.2 日本区域（中部）"),
    ("Japan-Okinawa", "3.3 日本区域（冲绳）"),
    ("Japan-South", "3.4 日本区域（南部）"),
    ("Guam", "3.5 关岛区域"),
    ("Korea", "3.6 韩国区域"),
    ("Hawaii", "3.7 夏威夷区域"),
    ("Alaska", "3.8 阿拉斯加区域"),
    ("Australia", "3.9 澳大利亚区域"),
    ("Philippines", "3.10 菲律宾区域"),
    ("Mariana Islands", "3.11 北马里亚纳群岛区域"),
]

for region_key, region_title in regions_order:
    region_bases = [b for b in bases if b["region"] == region_key]
    if not region_bases:
        continue

    doc.add_heading(region_title, level=2)

    for b in region_bases:
        doc.add_heading(f"{b['name']} ({b['name_cn']})", level=3)

        # Base profile table
        profile_table = doc.add_table(rows=0, cols=2)
        profile_table.style = "Light Grid Accent 1"

        fields = [
            ("基地编号", b["id"]),
            ("英文名称", b["name"]),
            ("中文名称", b["name_cn"]),
            ("国家/地区", b["country"]),
            ("区域分类", b["region"]),
            ("经度", f"{b['lon']:.4f}"),
            ("纬度", f"{b['lat']:.4f}"),
            ("驻扎军种", b["branch"]),
            ("主要单位", b["unit"]),
            ("常驻装备", b["aircraft"]),
            (
                "跑道长度",
                f"{b['runway_m']} 米" if b["runway_m"] > 0 else "N/A（海军基地）",
            ),
            (
                "常驻人员",
                f"{b['personnel']:,} 人" if b["personnel"] > 0 else "轮换部署",
            ),
            ("设施代码", b["facility_code"]),
            ("ACE Hub", "是" if b["ace_hub"] else "否"),
            ("SCARS模拟器", "有" if b["scars"] else "无"),
            ("LVC架构定位", b["lvc_layer"]),
            ("基地功能", b["role"]),
        ]

        for label, value in fields:
            row = profile_table.add_row().cells
            row[0].text = label
            row[1].text = str(value)
            for p in row[0].paragraphs:
                for r in p.runs:
                    r.bold = True
                    r.font.size = Pt(9)
            for p in row[1].paragraphs:
                for r in p.runs:
                    r.font.size = Pt(9)

        # DTB Model mapping
        p = doc.add_paragraph()
        run = p.add_run("DTB Model映射：")
        run.bold = True
        run.font.color.rgb = RGBColor(0x15, 0x65, 0xC0)
        p.add_run(b["dtb_mapping"])

        # ASDA mapping
        p = doc.add_paragraph()
        run = p.add_run("ASDA闭环映射：")
        run.bold = True
        run.font.color.rgb = RGBColor(0xC6, 0x28, 0x28)
        p.add_run(b["asda_mapping"])

        # VS26 role
        p = doc.add_paragraph()
        run = p.add_run("VS26实战角色：")
        run.bold = True
        run.font.color.rgb = RGBColor(0xE6, 0x51, 0x00)
        p.add_run(b["vs26_role"])

        doc.add_paragraph()  # spacing

doc.add_page_break()

# Chapter 4: VS26 & LVC mapping
doc.add_heading("四、VS26实战角色与LVC架构映射", level=1)

doc.add_paragraph(
    "VS26（Valiant Shield 2026）演习是理解INDOPACOM基地网络运作的关键参考。"
    "每个基地在LVC（Live-Virtual-Constructive）三层架构中的定位决定了其在数字孪生战场中的角色。"
)

lvc_table = doc.add_table(rows=1, cols=4)
lvc_table.style = "Light Grid Accent 1"
hdr = lvc_table.rows[0].cells
for i, h in enumerate(["基地", "LVC层级", "VS26角色", "DTB Model定位"]):
    hdr[i].text = h
    for p in hdr[i].paragraphs:
        for r in p.runs:
            r.bold = True
            r.font.size = Pt(8)

for b in bases:
    row = lvc_table.add_row().cells
    row[0].text = f"{b['name']}\n{b['name_cn']}"
    row[1].text = b["lvc_layer"]
    row[2].text = b["vs26_role"]
    row[3].text = b["dtb_mapping"]
    for cell in row:
        for p in cell.paragraphs:
            for r in p.runs:
                r.font.size = Pt(7.5)

doc.add_page_break()

# Chapter 5: ACE Hub-Spoke model
doc.add_heading("五、ACE分布式部署中心-辐条模型", level=1)

doc.add_paragraph(
    "ACE（Agile Combat Employment，敏捷战斗运用）是美军在INDOPACOM辖区实施分布式作战的核心概念。"
    '其基本架构为"中心-辐条"（Hub-Spoke）模型：'
)

ace_hubs = [b for b in bases if b["ace_hub"]]
ace_spokes = [b for b in bases if not b["ace_hub"]]

doc.add_heading("5.1 ACE Hub（中心节点）", level=2)
doc.add_paragraph(f"共 {len(ace_hubs)} 个ACE Hub基地，具备完整作战、保障与指挥能力：")
for b in ace_hubs:
    p = doc.add_paragraph(style="List Bullet")
    run = p.add_run(f"{b['name']} ({b['name_cn']})")
    run.bold = True
    p.add_run(f" - {b['role']}")

doc.add_heading("5.2 ACE Spoke（辐条节点）", level=2)
doc.add_paragraph(f"共 {len(ace_spokes)} 个辐条基地，侧重快速反应与区域监控：")
for b in ace_spokes:
    p = doc.add_paragraph(style="List Bullet")
    run = p.add_run(f"{b['name']} ({b['name_cn']})")
    run.bold = True
    p.add_run(f" - {b['role']}")

doc.add_heading("5.3 关岛-日本-夏威夷整合链", level=2)
doc.add_paragraph(
    "VS26演习展示了一条从关岛安德森AFB到日本嘉手纳/横田再到夏威夷珍珠港-希卡姆的整合链。"
    "这条链路是DTB Model战斗网络的主干，也是ASDA闭环从战术到战略的传导路径。"
    "在Leaflet交互式地图中，这条链路以橙色虚线标示。"
)

doc.add_page_break()

# Chapter 6: DTB Model mapping summary
doc.add_heading("六、DTB Model组件映射总表", level=1)
doc.add_paragraph("每个基地映射到DTB Model四层架构的对应组件：")

dtb_table = doc.add_table(rows=1, cols=3)
dtb_table.style = "Light Grid Accent 1"
hdr = dtb_table.rows[0].cells
for i, h in enumerate(["基地", "DTB Model组件", "说明"]):
    hdr[i].text = h
    for p in hdr[i].paragraphs:
        for r in p.runs:
            r.bold = True
            r.font.size = Pt(9)

for b in bases:
    row = dtb_table.add_row().cells
    row[0].text = f"{b['name']}"
    row[1].text = b["dtb_mapping"]
    row[2].text = b["role"]
    for cell in row:
        for p in cell.paragraphs:
            for r in p.runs:
                r.font.size = Pt(8)

doc.add_page_break()

# Chapter 7: ASDA mapping summary
doc.add_heading("七、ASDA闭环映射总表", level=1)
doc.add_paragraph("每个基地在ASDA闭环中的角色定位：")

asda_table = doc.add_table(rows=1, cols=3)
asda_table.style = "Light Grid Accent 1"
hdr = asda_table.rows[0].cells
for i, h in enumerate(["基地", "ASDA环节", "说明"]):
    hdr[i].text = h
    for p in hdr[i].paragraphs:
        for r in p.runs:
            r.bold = True
            r.font.size = Pt(9)

for b in bases:
    row = asda_table.add_row().cells
    row[0].text = f"{b['name']}"
    row[1].text = b["asda_mapping"]
    row[2].text = b["vs26_role"]
    for cell in row:
        for p in cell.paragraphs:
            for r in p.runs:
                r.font.size = Pt(8)

# Save docx
docx_path = os.path.join("D:/APPs/数字孪生挑战赛", "INDOPACOM基地标绘档案.docx")
doc.save(docx_path)
print(f"DOCX saved: {docx_path}")

# ============================================================
# Generate QGIS Project File (.qgs)
# ============================================================

qgs_content = """<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis projectname="INDOPACOM Military Bases" version="3.34.0">
  <homePath path=""/>
  <title>INDOPACOM Military Bases - DTC 2026 Level 1</title>
  <autotransaction enabled="0"/>
  <evaluateDefaultValues enabled="0"/>
  <layer-tree-group>
    <layer-tree-layer name="INDOPACOM Bases" source="../indopacom_bases.geojson|layername=INDOPACOM Military Bases" provider="ogr" id="indopacom_bases_1234abcd">
      <layer-tree-legend patch-size="0,0" name=""/>
    </layer-tree-layer>
  </layer-tree-group>
  <projectlayers>
    <maplayer name="INDOPACOM Bases" type="vector" maxScale="0" minScale="1e+8" geometry="Point" simplifyDrawingTol="1" simplifyMaxScale="1" refreshOnNotifyEnabled="0" autoRefreshEnabled="0" simplifyAlgorithm="0" simplifyLocal="1" styleCategories="AllStyleCategories" refreshOnNotifyMessage="" autoRefreshTime="0" hasScaleBasedVisibility="0" simplifyDrawingHints="1">
      <id>indopacom_bases_1234abcd</id>
      <datasource>./indopacom_bases.geojson|layername=INDOPACOM Military Bases</datasource>
      <keywordList>
        <value></value>
      </keywordList>
      <layername>INDOPACOM Bases</layername>
      <srs>
        <spatialrefsys nativeFormat="Wkt">
          <wkt>GEOGCRS["WGS 84",DATUM["World Geodetic System 1984",ELLIPSOID["WGS 84",6378137,298.257223563]],CS[ellipsoidal,2],AXIS["Latitude",north],AXIS["Longitude",east],UNIT["degree",9.86808271708726e-18],ID["EPSG",4326]]</wkt>
          <proj4>+proj=longlat +datum=WGS84 +no_defs</proj4>
          <identifier>EPSG:4326</identifier>
          <description>WGS 84</description>
        </spatialrefsys>
      </srs>
      <provider>ogr</provider>
      <vectorjestimation type="base" inforeground="0" vertical="0"/>
      <renderer-v2 type="categorizedSymbol" attr="region">
        <categories>
          <category render="true" label="Japan (North)" value="Japan-North" symbol="0"/>
          <category render="true" label="Japan (Central)" value="Japan-Central" symbol="1"/>
          <category render="true" label="Japan (Okinawa)" value="Japan-Okinawa" symbol="2"/>
          <category render="true" label="Japan (South)" value="Japan-South" symbol="3"/>
          <category render="true" label="Guam" value="Guam" symbol="4"/>
          <category render="true" label="Korea" value="Korea" symbol="5"/>
          <category render="true" label="Hawaii" value="Hawaii" symbol="6"/>
          <category render="true" label="Alaska" value="Alaska" symbol="7"/>
          <category render="true" label="Australia" value="Australia" symbol="8"/>
          <category render="true" label="Philippines" value="Philippines" symbol="9"/>
          <category render="true" label="Mariana Islands" value="Mariana Islands" symbol="10"/>
        </categories>
        <symbols>
          <symbol type="marker" name="0" alpha="1" clip_to_extent="1"><layer class="SimpleMarker" locked="0" enabled="1"><prop k="color" v="21,101,192"/><prop k="size" v="6"/><prop k="outline_color" v="255,255,255"/></layer></symbol>
          <symbol type="marker" name="1" alpha="1" clip_to_extent="1"><layer class="SimpleMarker" locked="0" enabled="1"><prop k="color" v="25,118,210"/><prop k="size" v="6"/><prop k="outline_color" v="255,255,255"/></layer></symbol>
          <symbol type="marker" name="2" alpha="1" clip_to_extent="1"><layer class="SimpleMarker" locked="0" enabled="1"><prop k="color" v="30,136,229"/><prop k="size" v="6"/><prop k="outline_color" v="255,255,255"/></layer></symbol>
          <symbol type="marker" name="3" alpha="1" clip_to_extent="1"><layer class="SimpleMarker" locked="0" enabled="1"><prop k="color" v="33,150,243"/><prop k="size" v="6"/><prop k="outline_color" v="255,255,255"/></layer></symbol>
          <symbol type="marker" name="4" alpha="1" clip_to_extent="1"><layer class="SimpleMarker" locked="0" enabled="1"><prop k="color" v="211,47,47"/><prop k="size" v="8"/><prop k="outline_color" v="255,255,255"/></layer></symbol>
          <symbol type="marker" name="5" alpha="1" clip_to_extent="1"><layer class="SimpleMarker" locked="0" enabled="1"><prop k="color" v="56,142,60"/><prop k="size" v="6"/><prop k="outline_color" v="255,255,255"/></layer></symbol>
          <symbol type="marker" name="6" alpha="1" clip_to_extent="1"><layer class="SimpleMarker" locked="0" enabled="1"><prop k="color" v="123,31,162"/><prop k="size" v="6"/><prop k="outline_color" v="255,255,255"/></layer></symbol>
          <symbol type="marker" name="7" alpha="1" clip_to_extent="1"><layer class="SimpleMarker" locked="0" enabled="1"><prop k="color" v="0,131,143"/><prop k="size" v="6"/><prop k="outline_color" v="255,255,255"/></layer></symbol>
          <symbol type="marker" name="8" alpha="1" clip_to_extent="1"><layer class="SimpleMarker" locked="0" enabled="1"><prop k="color" v="245,124,0"/><prop k="size" v="6"/><prop k="outline_color" v="255,255,255"/></layer></symbol>
          <symbol type="marker" name="9" alpha="1" clip_to_extent="1"><layer class="SimpleMarker" locked="0" enabled="1"><prop k="color" v="93,64,55"/><prop k="size" v="6"/><prop k="outline_color" v="255,255,255"/></layer></symbol>
          <symbol type="marker" name="10" alpha="1" clip_to_extent="1"><layer class="SimpleMarker" locked="0" enabled="1"><prop k="color" v="198,40,40"/><prop k="size" v="6"/><prop k="outline_color" v="255,255,255"/></layer></symbol>
        </symbols>
      </renderer-v2>
      <labeling type="simple">
        <settings>
          <text-style fontSize="8" fieldName="name_cn"/>
        </settings>
      </labeling>
    </maplayer>
  </projectlayers>
  <mapcanvas>
    <settings>
      <extent xmin="60" xmax="-60" ymin="-20" ymax="70" maxalone="0"/>
      <rotation>0</rotation>
      <destCRS>EPSG:4326</destCRS>
    </settings>
  </mapcanvas>
</qgis>"""

qgs_path = os.path.join("D:/APPs/数字孪生挑战赛", "INDOPACOM-Bases.qgs")
with open(qgs_path, "w", encoding="utf-8") as f:
    f.write(qgs_content)
print(f"QGIS project saved: {qgs_path}")

print(f"\n=== Level 1 Deliverables Summary ===")
print(f"1. GeoJSON: {geojson_path}")
print(
    f"2. HTML Map: {os.path.join('D:/APPs/数字孪生挑战赛', 'INDOPACOM-Bases-Map.html')}"
)
print(f"3. DOCX: {docx_path}")
print(f"4. QGIS: {qgs_path}")
print(f"Total bases: {len(bases)}")
print(f"Regions: {len(set(b['region'] for b in bases))}")
print(f"ACE Hubs: {sum(1 for b in bases if b['ace_hub'])}")
