# -*- coding: utf-8 -*-
"""答辩 PPT 口径刷新 v3（P18 评审整改代）：130提交/30天/158py → 142/32天/167py。

背景：P18 全面整改（评审 51/100 反馈触发）后口径终值收敛。
终值收敛法：142 = 本刷新 docs bump + 打包 chore 计入后的 rev-list 实测；
167 py = 166（刷新前实测）+ 本 v3 刷新脚本自身；包内 381 文件 = 382 跟踪 - zip 自身。
窗口 2026-09-05 ～ 10-06（含头含尾 32 天）。
替换全部等长（130→142 / 30→32 / 158→167），仅 slide1/slide3 两处真实口径行，
零排版风险。PPT 为 gitignore 演示件，本地刷新不入库。
"""
import os
import shutil
import zipfile

SRC = r"D:\APPs\数字孪生挑战赛\DTC2026赛道二答辩-PMTEC新版.pptx"
BAK = SRC + ".bak-2026-10-06"
if not os.path.exists(BAK):
    shutil.copyfile(SRC, BAK)

REPL = [
    ("158 个 Python 文件", "167 个 Python 文件"),
    ("130 次提交 / 30 天", "142 次提交 / 32 天"),
]

zin = zipfile.ZipFile(BAK)
items = [(i, zin.read(i.filename)) for i in zin.infolist()]
zin.close()
out = zipfile.ZipFile(SRC, "w", zipfile.ZIP_DEFLATED)
hits = 0
for info, data in items:
    if info.filename.startswith("ppt/slides/slide") and info.filename.endswith(".xml"):
        x = data.decode("utf-8")
        for old, new in REPL:
            if old in x:
                hits += x.count(old)
                x = x.replace(old, new)
        data = x.encode("utf-8")
    out.writestr(info, data)
out.close()
print(f"PPT 等长换完成: {hits} 处替换（备份 {BAK}）")
