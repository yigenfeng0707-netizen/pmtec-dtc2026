#!/usr/bin/env python3
"""P18-D 口径自检：基地数量口径（67/22/15/36）与置信度四级标注的防漂移检查。

评审 P1 整改项"统一基地数量口径（67/22/15）"的固化管理——数字本身都真实，
风险在引用时不带限定语导致口径打架。本脚本：
  1. 打印全仓唯一口径权威表（与 README「评估口径说明」同源）；
  2. 扫描关键交付文档中 67/22/15/36 与"基地/站点/实体"同现的行，
     报告缺限定语的裸引用（人工复核清单，WARN 不判死）；
  3. 硬校验：README 口径权威表在场、必答五问文档带双口径声明、
     失效边界卡为可复算口径（P18 修正后）。

Run: python scripts/caliber_check.py   （退出码 0=通过 / 1=硬校验失败）
"""

import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))  # 仓库根（数字孪生挑战赛/）：扫描目标含根级交付文档
sys.stdout.reconfigure(encoding="utf-8")

CALIBER_TABLE = """
───── 全仓唯一口径权威表（权威定义见 pmtec_system/README.md「评估口径说明」）─────
  67 = 印太基地实体总数（v2 权威库 bases_v2.geojson，CRS+FY2024 BSR 双源）
  22 = 引擎实时推演口径（v1 库；P6/P12 观测维度、训练模型、MC 三场景锚定）
  15 = 引擎政治准入盟友站点（22 站中澳日菲韩 4 东道国；推演中 5/7/3 分布）
  36 = v2 权威库 host_nation 计数（分析管线口径：韧性分析/五问 S1 主行）
  45/21/1(+D0) = 置信度四级：A 多源核验 / A- v1 沿用 / B 降级(Tinian) / D 待核验留白
  信息截至 2026-09（CRS R47589 / DoD FY2024 BSR）
──────────────────────────────────────────────────────────────────────"""

# 扫描目标（关键交付文档；新增交付物请登记到此处）
SCAN_FILES = [
    "pmtec_system/README.md",
    "docs/必答五问作答.md",
    "docs/PMTEC-数据字典.md",
    "docs/PMTEC-增量说明.md",
    "docs/PMTEC-智能体使用档案.md",
    "答辩演练脚本-DTC2026.md",
    "DTC2026全面提升改造计划-P18.md",
    "pmtec_system/ontology/failure_boundary_card.md",
]

QUALIFIERS = (
    "权威", "引擎", "推演口径", "盟友", "实体总数", "host_nation", "分析口径",
    "v2", "v1", "口径", "负载", "本体", "档案", "C2", "MC", "置信", "精度",
    "标绘", "部署", "四大", "站点", "东道国", "基地实体", "留白",
)

# 67/22/15/36 后接"个/座/站"且同句含"基地/实体"的行视为口径引用
PATTERN = re.compile(r"(67|22|15|36)\s*(个|座|站)?\s*(基地|实体|站点)")


def scan():
    warnings = []
    for rel in SCAN_FILES:
        path = os.path.join(PROJECT_ROOT, rel)
        if not os.path.exists(path):
            continue  # 未产出的交付物跳过（由 WP-C 生成后自动纳入）
        with open(path, encoding="utf-8") as f:
            for ln, line in enumerate(f, 1):
                if PATTERN.search(line) and not any(q in line for q in QUALIFIERS):
                    warnings.append((rel, ln, line.strip()[:90]))
    return warnings


def hard_checks():
    errs = []
    readme_path = os.path.join(PROJECT_ROOT, "pmtec_system", "README.md")
    readme = open(readme_path, encoding="utf-8").read()
    if "基地数量口径（评审 P1 整改项：67/22/15 统一）" not in readme:
        errs.append("README 缺基地数量口径权威表")
    if "信息截至 2026-09" not in readme:
        errs.append("README 缺'信息截至'声明")

    fq = os.path.join(PROJECT_ROOT, "docs", "必答五问作答.md")
    if os.path.exists(fq):
        t = open(fq, encoding="utf-8").read()
        if "推演口径" not in t or "截至 2026-09" not in t:
            errs.append("必答五问文档缺双口径/信息截至声明")

    card = os.path.join(PROJECT_ROOT, "pmtec_system", "ontology",
                        "failure_boundary_card.md")
    if os.path.exists(card):
        t = open(card, encoding="utf-8").read()
        if "2026-10-05 修正为可复算口径" not in t:
            errs.append("失效边界卡未切换到可复算口径（P18 修正缺失）")
    return errs


def main():
    print(CALIBER_TABLE)
    errs = hard_checks()
    warnings = scan()
    print(f"\n[硬校验] {'全部通过' if not errs else '失败 ' + str(len(errs)) + ' 项'}")
    for e in errs:
        print(f"  [ERR] {e}")
    print(f"[裸引用扫描] 扫描 {len(SCAN_FILES)} 个关键文档，"
          f"缺限定语的口径引用 {len(warnings)} 处（WARN，人工复核）")
    for rel, ln, line in warnings:
        print(f"  [WARN] {rel}:{ln}  {line}")
    print("\n结论：", "口径一致，可交付" if not errs else "存在硬伤，禁止交付")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
