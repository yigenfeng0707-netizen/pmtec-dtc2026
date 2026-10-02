# -*- coding: utf-8 -*-
"""答辩 PPT 口径刷新（终值版）：86提交/21天/132py/3.9万/326文件/21断言 → 105/28/153/4.4万/347/62。

从首次修改前的原始备份 .bak 读入，一次性写入终值数字；可重复执行（幂等）。
数字终值收敛法：文档写"105 次提交" = 本文档 bump 提交 + 打包 chore 提交计入后的 rev-list 实测值。
"""
import re
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")

SRC = r"D:\APPs\数字孪生挑战赛\DTC2026赛道二答辩-PMTEC新版.pptx"
BAK = SRC + ".bak"

REPL = {
    "ppt/slides/slide1.xml": [
        ("132 个 Python 文件 · 3.9 万行代码 · 433 行 protobuf 接口契约 · 86 次提交 / 21 天",
         "153 个 Python 文件 · 4.4 万行代码 · 433 行 protobuf 接口契约 · 105 次提交 / 28 天"),
    ],
    "ppt/slides/slide3.xml": [
        ("132 个 Python 文件 · 3.9 万行代码 · 433 行 protobuf 接口契约 · 86 次提交 / 21 天",
         "153 个 Python 文件 · 4.4 万行代码 · 433 行 protobuf 接口契约 · 105 次提交 / 28 天"),
    ],
    "ppt/slides/slide13.xml": [
        ("工程质量：一个人、21 天、可复现交付", "工程质量：一个人、28 天、可复现交付"),
        ("21 项验收断言", "62 项验收断言"),
        ("离线包 326 文件自包含", "离线包 347 文件自包含"),
        ("86 次提交 / 21 天（09-05 起）", "105 次提交 / 28 天（09-05 起）"),
    ],
    "ppt/slides/slide17.xml": [
        ("86 提交 / 21 天 · 132 py · 3.9 万行 · 433 行 proto",
         "105 提交 / 28 天 · 153 py · 4.4 万行 · 433 行 proto"),
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
for must in ["105 次提交 / 28 天", "153 个 Python 文件", "62 项验收断言", "347 文件自包含",
             "105 提交 / 28 天 · 153 py"]:
    assert must in joined, "缺失: " + must
for ban in ["86 次提交", "86 提交 / 21 天", "132", "326 文件", "21 项验收", "3.9 万行"]:
    assert ban not in joined, "残留: " + ban
print("✅ 回读验证通过：终值数字全在，旧数字清零（slide17 P14 '21 断言'/'86 实体' 为正确口径，保留）")
