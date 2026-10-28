#!/usr/bin/env python3
"""可引用产物白名单生成器（门禁 v2.1 出处校验的数据底座）。

背景（里程碑 12 发现的出处幻觉）：D 组模型 F12/F14 答案数字对，但引用了
不存在的路径（twin_summary.txt、data/musix_calibration.html、
count_based/intercept_rate.md）——锚点判定只校验数字、不校验出处可回查性。
参谋官铁律里「出处造假」与「数字造假」同罪，故门禁补出处校验。

做法：把仓库里**真实可引用的产物**（按 git 跟踪清单 + 后缀白名单）冻结成
citation_whitelist.json（含 sha256），门禁据此判定答案里的路径式引用是否可回查。

用法（本地跑，产物入库）:
  python3 build_citation_whitelist.py
"""
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # pmtec_system/
REPO = os.path.dirname(ROOT)                        # 仓库根
sys.stdout.reconfigure(encoding="utf-8")

CITABLE_EXT = (".json", ".md", ".html", ".yaml", ".yml", ".py",
               ".csv", ".geojson", ".txt", ".log")

# 目录本身也可被引用（"见 data/models/" 这类答案）
CITABLE_DIRS = set()


def main():
    tracked = subprocess.run(
        ["git", "-c", "core.quotePath=false", "ls-files"],
        cwd=REPO, capture_output=True, text=True,
        encoding="utf-8").stdout.splitlines()
    files = sorted(f for f in tracked if f.endswith(CITABLE_EXT))

    # 两种路径约定都算可回查：
    #   仓库根相对（docs/必答五问作答.md）与 pmtec_system 相对（output/five_questions_report.json）
    dirs = set()
    for f in files:
        parts = f.split("/")
        for i in range(1, len(parts)):
            dirs.add("/".join(parts[:i]))
            if parts[i] != "pmtec_system":
                dirs.add("/".join(parts[1:i]))    # 剥 pmtec_system/ 后的相对目录
    dirs = sorted(dirs)

    # 扫描训练语料的「出处：…」句，收集合法引用短语全集
    # （实体式引用如 twin_summary.calibration 只认语料原文教过的组合，
    #   不认任意 stem+扩展名拼接——twin_summary.txt 就是 D 组实测幻觉）
    cite_pat = re.compile(r"[A-Za-z0-9_\-./\u4e00-\u9fff]+(?:\.[A-Za-z0-9_\-]+)+")
    corpus_refs = set()
    for cf in ["sft_facts.jsonl", "sft_anchor_extra.jsonl", "sft_v6_2696.jsonl",
               "sft_refusal.jsonl"]:
        cpath = os.path.join(ROOT, "data", "corpora", cf)
        if not os.path.exists(cpath):
            continue
        for line in open(cpath, encoding="utf-8"):
            ans = json.loads(line)["messages"][2]["content"]
            for seg in re.split(r"出处[：:]|见 |依据：", ans)[1:]:
                for m in cite_pat.findall(seg[:220]):
                    corpus_refs.add(m)

    blob = {"generated_at": "2026-10-27",
            "note": "出处可回查判定（单一口径实现在 eval_citation_gate.citation_check）："
                    "引用 token t（先剥 pmtec_system/ 前缀）满足 ①t∈files ②pmtec_system/t∈files "
                    "③t∈corpus_refs ④basename(t)∈basenames ⑤t∈dirs 之一即可回查；"
                    "否则记出处幻觉。假路径 twin_summary.txt / musix_calibration.html / "
                    "count_based/intercept_rate.md 五条全命中不了（10-28 D 组 F12/F14 实证）。",
            "files": files, "dirs": dirs,
            "basenames": sorted({f.split("/")[-1] for f in files}),
            "corpus_refs": sorted(corpus_refs)}
    out_path = os.path.join(HERE, "citation_whitelist.json")
    body = json.dumps(blob, ensure_ascii=False, indent=1)
    sha = hashlib.sha256(body.replace("\r\n", "\n").encode("utf-8")).hexdigest()
    blob["sha256_self"] = sha
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(blob, f, ensure_ascii=False, indent=1)
    print(f"可引用产物: {len(files)} 文件 / {len(dirs)} 目录 / "
          f"{len(corpus_refs)} 语料引用短语 -> {out_path}")


if __name__ == "__main__":
    main()
