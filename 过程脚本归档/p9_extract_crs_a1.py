#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P9.1 重新提取 CRS 报告 Table A-1 全部站点清单（PDF -> JSON，持久化中间数据）。"""

import json
import re
import sys

import fitz

sys.stdout.reconfigure(encoding="utf-8")

PDF = (
    "回复：+第八届数字孪生体挑战赛（DTC+2026）赛道二参赛报名+——+根深叶茂团队/"
    "1 U.S. Defense Infrastructure in the Indo-Pacific：Background and Issues for Congress.pdf"
)
OUT = "p9_crs_table_a1.json"

doc = fitz.open(PDF)
print(f"pages: {len(doc)}")

# 1. 定位 Table A-1 所在页
pages_a1 = []
for i, page in enumerate(doc):
    text = page.get_text()
    if "Table A-1" in text:
        pages_a1.append(i)
        print(f"page {i}: contains 'Table A-1'")
if not pages_a1:
    print("NOT FOUND")
    sys.exit(1)

# 2. 输出 Table A-1 起始页之后的连续几页原文（供逐行解析）
start = max(p for p in pages_a1 if p > 10)  # 附录正文页（跳过目录引用）
chunk = ""
for i in range(start, min(start + 6, len(doc))):
    chunk += doc[i].get_text() + "\n<<<PAGE-BREAK>>>\n"

with open("p9_crs_a1_raw.txt", "w", encoding="utf-8") as f:
    f.write(chunk)
print(f"raw text saved: p9_crs_a1_raw.txt ({len(chunk)} chars), start page = {start}")
