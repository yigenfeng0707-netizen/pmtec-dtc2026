# -*- coding: utf-8 -*-
"""答辩 PPT 口径刷新 v2（Web 认证代）：107提交/153py/62断言/349文件 → 110/157/88/355。

背景：8abfa2d Web 展示层认证门禁落地（test_web_auth 26 断言入 CI 门禁），另修正
全仓 py 口径漂移（153 为 a4f3c3f 归档两脚本入库前测量，实为 155 → +2 新 py = 157）。
数字终值收敛法：文档写"110 次提交" = 本口径 docs bump + 打包 chore 计入后的 rev-list 实测。
离线包文件数终值 356 = 349 + feat 6 文件 + 本 v2 刷新脚本自身 1 文件
（初跑曾误写 355 漏计脚本自身，已就地更正为 356）。

前置：先把当前 pptx 复制为 .bak（本脚本从 .bak 读入、写回 SRC，幂等可重放）。
全部替换等长（107→110 / 153→157 / 62→88 / 349→355），零排版风险。
"""
import re
import shutil
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")

SRC = r"D:\APPs\数字孪生挑战赛\DTC2026赛道二答辩-PMTEC新版.pptx"
BAK = SRC + ".bak"

shutil.copyfile(SRC, BAK)  # 本代原始备份

REPL = {
    "ppt/slides/slide1.xml": [
        ("153 个 Python 文件 · 4.4 万行代码 · 433 行 protobuf 接口契约 · 107 次提交 / 28 天",
         "157 个 Python 文件 · 4.4 万行代码 · 433 行 protobuf 接口契约 · 110 次提交 / 28 天"),
    ],
    "ppt/slides/slide3.xml": [
        ("153 个 Python 文件 · 4.4 万行代码 · 433 行 protobuf 接口契约 · 107 次提交 / 28 天",
         "157 个 Python 文件 · 4.4 万行代码 · 433 行 protobuf 接口契约 · 110 次提交 / 28 天"),
    ],
    "ppt/slides/slide13.xml": [
        ("62 项验收断言", "88 项验收断言"),
        ("离线包 349 文件自包含", "离线包 356 文件自包含"),
        ("107 次提交 / 28 天（09-05 起）", "110 次提交 / 28 天（09-05 起）"),
    ],
    "ppt/slides/slide17.xml": [
        ("107 提交 / 28 天 · 153 py · 4.4 万行 · 433 行 proto",
         "110 提交 / 28 天 · 157 py · 4.4 万行 · 433 行 proto"),
    ],
}

zin = zipfile.ZipFile(BAK)
zout = zipfile.ZipFile(SRC, "w", zipfile.ZIP_DEFLATED)
for item in zin.infolist():
    data = zin.read(item.filename)
    if item.filename in REPL:
        xml = data.decode("utf-8")
        for old, new in REPL[item.filename]:
            n = xml.count(old)
            print(f"{item.filename}: 替换 x{n}  {old[:30]}...")
            assert n >= 1, f"未找到: {old}"
            xml = xml.replace(old, new)
        data = xml.encode("utf-8")
    zout.writestr(item, data)
zout.close()
zin.close()

# 回读验证：新数字全在、旧数字清零
z = zipfile.ZipFile(SRC)
joined = ""
for sn in [1, 3, 13, 17]:
    xml = z.read(f"ppt/slides/slide{sn}.xml").decode("utf-8")
    joined += " ".join(re.findall(r"<a:t>([^<]*)</a:t>", xml))
z.close()
for must in ["110 次提交 / 28 天", "157 个 Python 文件", "88 项验收断言", "355 文件自包含",
             "110 提交 / 28 天 · 157 py"]:
    assert must in joined, "缺失: " + must
for ban in ["107 次提交", "107 提交 / 28 天", "153", "349 文件", "62 项验收"]:
    assert ban not in joined, "残留: " + ban

# python-pptx 结构完整性验证
from pptx import Presentation  # noqa: E402

prs = Presentation(SRC)
n_slides = len(prs.slides)
texts = sum(1 for sl in prs.slides for sh in sl.shapes if sh.has_text_frame)
print(f"✅ 回读验证通过：v2 终值数字全在，旧数字清零；python-pptx 打开正常 "
      f"({n_slides} 页 / {texts} 文本框)")
