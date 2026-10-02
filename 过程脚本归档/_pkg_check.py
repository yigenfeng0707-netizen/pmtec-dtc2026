# -*- coding: utf-8 -*-
"""答辩前自检：离线提交包 vs git archive HEAD 逐项对比。"""
import subprocess
import sys
import zipfile

REPO = r"D:\APPs\数字孪生挑战赛"

# 1) git archive HEAD 文件清单（排除目录条目）
tar_list = subprocess.run(
    ["git", "archive", "HEAD", "--", ".", ":(exclude)DTC2026-离线提交包.zip"],
    cwd=REPO, capture_output=True,
)
import tarfile, io
tf = tarfile.open(fileobj=io.BytesIO(tar_list.stdout))
archive_files = sorted(m.name for m in tf.getmembers() if m.isfile())
tf.close()

# 2) zip 内容清单（归一化路径分隔符）
z = zipfile.ZipFile(REPO + r"\DTC2026-离线提交包.zip")
zip_files = sorted(n.replace("\\", "/") for n in z.namelist() if not n.endswith("/"))

print(f"git archive HEAD files: {len(archive_files)}")
print(f"zip entries:            {len(zip_files)}")

only_archive = [f for f in archive_files if f not in set(zip_files)]
only_zip = [f for f in zip_files if f not in set(archive_files)]

print(f"\n在 HEAD 但不在 zip ({len(only_archive)}):")
for f in only_archive:
    print("  -", f)
print(f"\n在 zip 但不在 HEAD ({len(only_zip)}):")
for f in only_zip:
    print("  +", f)

if not only_archive and not only_zip:
    print("\n✅ 打包内容与 HEAD 完全一致")
