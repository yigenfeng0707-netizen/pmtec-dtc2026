#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 output/index.html —— PMTEC 一键演示入口（评委仪表盘）。

聚合全部展示物：实时/3D/SPEAR 显示、AI 参谋官报告、孪生层 REST、
P12 权威报告、演示视频等。产物: output/index.html
"""
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output", "index.html")

CARDS = [
    ("🌍", "全球地球总览", "pmtec_globe.html",
     "MapLibre GL 地球投影：9 站拒止脉冲（seed=42 确定性回放）+ 饱和弹道流光 + EDCA 圈", "#22d3ee"),
    ("🛰️", "实时态势大屏", "pmtec_realtime_display.html",
     "2D/3D/数字地球三态切换 + 杀伤链实时流 + 孪生面板 + AI 参谋官按钮", "#2ec4b6"),
    ("🧬", "数字孪生仪表盘", "dt_dashboard.html",
     "虚实同步专属视图：KPI/策略反哺模型/孪生体双栏卡片，2s 轮询", "#2ec4b6"),
    ("🌐", "3D 战场显示", "pmtec_3d_display.html",
     "Three.js 三维战场视图（Kalman 置信度热力 + 天气叠加）", "#4e9af5"),
    ("🧠", "AI 参谋官报告", "ai_situation_analysis.html",
     "step-3.7-flash 基于孪生层+P10/P11+SPEAR 真实数据生成的战术级态势分析", "#f5b84e"),
    ("📈", "SPEAR 时间轴", "pmtec_spear_timeline.html",
     "四泳道（政治/拦截/损伤/威胁）逐周期回放 + 准入构成带", "#9e4ef5"),
    ("🗺️", "67 实体权威地图", "INDOPACOM-Bases-Map.html",
     "CRS/DoD 溯源基地数据库（Tier 分层 + EDCA 圈定）", "#4e9af5"),
    ("📊", "P12 重验证报告", "PMTEC_P12_Revalidation_Report.html",
     "三场景对照 76.2/79.0/79.5%，六策略全量 79.1%（CI 78.0-80.2%）", "#e63946"),
    ("🛡️", "政治韧性分析", "PMTEC_Political_Resilience_Analysis.html",
     "十万次蒙特卡洛敏感性：最差情形体系可用率 95.5%", "#e63946"),
    ("🎯", "ACE 部署方案", "ace_deployment_map.html",
     "政治约束下的敏捷战斗部署（Denied 站点自动排除）", "#2ec4b6"),
    ("🧩", "本体工作台", "pmtec_ontology_workbench.html",
     "本体类层级 + 语义检索台（67 全档案）+ D-S 置信分布 + 决策链路审计（P17/P18）", "#8b5cf6"),
    ("❓", "必答五问作答报告", "Five_Questions_Report.html",
     "失效场景×红方代价 / 30% 节点保留率 / 敏感性排序 / 交换比 / 政治韧性（MC 2 万次实跑）", "#e63946"),
    ("🎬", "演示视频 V3", "pmtec_demo_video_v3.mp4",
     "314s ≥5 分钟八幕实拍（含失败与边界四段：30% 打掉/政治拒止/参谋官降级/断网离线），神经旁白+同步字幕+配乐", "#f5b84e"),
]

HTML = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>PMTEC 数字孪生战场 - 演示中心</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:"Segoe UI","Microsoft YaHei",sans-serif; background:#0a0e17;
         color:#c9d1d9; min-height:100vh; }}
  header {{ padding:40px 40px 20px; border-bottom:1px solid #1b263b; }}
  h1 {{ color:#fff; font-size:26px; }}
  h1 span {{ color:#2ec4b6; }}
  .sub {{ color:#8b949e; margin-top:8px; font-size:14px; }}
  .stats {{ display:flex; gap:24px; margin-top:18px; flex-wrap:wrap; }}
  .stat {{ background:#111827; border:1px solid #1b263b; border-radius:8px;
          padding:12px 18px; }}
  .stat b {{ display:block; font-size:22px; color:#2ec4b6; }}
  .stat span {{ font-size:12px; color:#8b949e; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(340px,1fr));
          gap:20px; padding:32px 40px 60px; }}
  .card {{ background:#111827; border:1px solid #1b263b; border-radius:10px;
          padding:22px; transition:all .2s; display:block; text-decoration:none;
          color:inherit; }}
  .card:hover {{ transform:translateY(-3px); border-color:var(--c); }}
  .card .icon {{ font-size:28px; }}
  .card h3 {{ color:var(--c); margin:10px 0 8px; font-size:16px; }}
  .card p {{ font-size:13px; line-height:1.6; color:#8b949e; }}
  .run {{ margin:0 40px 40px; padding:20px 24px; background:#111827;
         border:1px solid #1b263b; border-radius:10px; font-size:13px; }}
  .run code {{ background:#0a0e17; padding:2px 8px; border-radius:4px;
              color:#4e9af5; }}
  footer {{ padding:20px 40px; color:#484f58; font-size:12px;
           border-top:1px solid #1b263b; }}
</style>
</head>
<body>
<header>
  <h1>PMTEC <span>数字孪生战场</span> · 演示中心</h1>
  <div class="sub">DTC 2026 Level 3 · Digital Twin Battlefield · ASDA 闭环 · LVC 三层架构 · P1-P18</div>
  <div class="stats">
    <div class="stat"><b>79.1%</b><span>基准拦截率 (CI 78.0-80.2%)</span></div>
    <div class="stat"><b>67</b><span>权威基地实体 (CRS/DoD 溯源)</span></div>
    <div class="stat"><b>23+</b><span>数字孪生体 (虚实同步)</span></div>
    <div class="stat"><b>13</b><span>迭代轮次 (P1-P18)</span></div>
  </div>
</header>
<div class="grid">
{"".join(f'''  <a class="card" style="--c:{c}" href="{href}">
    <div class="icon">{icon}</div>
    <h3>{title}</h3>
    <p>{desc}</p>
  </a>''' for icon, title, href, desc, c in CARDS)}
</div>
<div class="run">
  <b style="color:#2ec4b6;">本地运行：</b>
  <code>python main.py --saturation --duration 600</code>
  → 打开「实时态势大屏」观察数字孪生注册表逐周期刷新，点「AI 参谋官」实时生成分析并导出 Word。
  <br><br>
  <b style="color:#2ec4b6;">Docker 一键演示（推荐评委使用）：</b>
  <code>docker compose -f docker-compose.demo.yml up -d</code>
  → 演示中心 <code>http://localhost:8888/</code> · REST <code>:8080</code> · WebSocket <code>:8765</code>
  （生产级完整分布式栈：<code>docker compose up -d</code>，含 4 gRPC 服务 + Prometheus + Grafana + Jaeger）
</div>
<footer>PMTEC v13 · DTC 2026 第八届数字孪生体挑战赛 · 赛道二 · 生成于 {datetime.now().strftime("%Y-%m-%d %H:%M")}</footer>
</body>
</html>"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(HTML)
print(f"[OK] index -> {OUT}")
