# -*- coding: utf-8 -*-
"""答辩 PPT 口径刷新：86提交/21天/132py/3.9万/326文件/21断言 → 99/28/153/4.4万/347/62。"""
import shutil
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")

SRC = r"D:\APPs\数字孪生挑战赛\DTC2026赛道二答辩-PMTEC新版.pptx"
BAK = SRC + ".bak"

REPL = {
    "ppt/slides/slide1.xml": [
        ("132 个 Python 文件 · 3.9 万行代码 · 433 行 protobuf 接口契约 · 86 次提交 / 21 天",
         "153 个 Python 文件 · 4.4 万行代码 · 433 行 protobuf 接口契约 · 99 次提交 / 28 天"),
    ],
    "ppt/slides/slide3.xml": [
        ("132 个 Python 文件 · 3.9 万行代码 · 433 行 protobuf 接口契约 · 86 次提交 / 21 天",
         "153 个 Python 文件 · 4.4 万行代码 · 433 行 protobuf 接口契约 · 99 次提交 / 28 天"),
    ],
    "ppt/slides/slide13.xml": [
        ("工程质量：一个人、21 天、可复现交付", "工程质量：一个人、28 天、可复现交付"),
        ("21 项验收断言", "62 项验收断言"),
        ("离线包 326 文件自包含", "离线包 347 文件自包含"),
        ("86 次提交 / 21 天（09-05 起）", "99 次提交 / 28 天（09-05 起）"),
    ],
    "ppt/slides/slide17.xml": [
        ("86 提交 / 21 天 · 132 py · 3.9 万行 · 433 行 proto",
         "99 提交 / 28 天 · 153 py · 4.4 万行 · 433 行 proto"),
    ],
}

shutil.copy2(SRC, BAK)

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

# 回读验证
z = zipfile.ZipFile(SRC)
joined = ""
for sn in [1, 3, 13, 17]:
    joined += " ".join(re.findall(r"<a:t>([^<]*)</a:t>", z.read(f"ppt/slides/slide{sn}.xml").decode("utf-8")))
import re
assert "99 次提交 / 28 天" in joined and "153 个 Python 文件" in joined
assert "62 项验收断言" in joined and "347 文件自包含" in joined
assert "86 次提交" not in joined and "132" not in joined and "326 文件" not in joined and "21 项验收" not in joined
print("✅ 回读验证通过，旧数字已清零（slide17 P14 的 '21 断言'/'86 实体' 为正确口径，保留）")
