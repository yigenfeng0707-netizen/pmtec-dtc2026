#!/usr/bin/env python3
"""训练链路回归门禁（P19 验收表第 6 项）：探针零碰撞 + 语料 manifest 校验。

两项检查都是纯 stdlib、无需 GPU，纳入 CI（ci-cd.yml「P19 training-line gates」步）：

  1. 探针/语料零碰撞——训练集=测试集的直接防线。历史教训：v2 语料的 TRAPS 家族
     曾把三道门禁原题逐字硬编码进训练集；语料扩充（尤其新增拒答族/锚点变体）时
     极易再次撞车，此检查必须机器化。
  2. manifest 校验——data/corpora/ 下每份带 manifest 的语料，按 LF 归一化 sha256
     与行数比对（10-28 教训：autocrlf 行尾漂移会让原始字节哈希误报）。

用法:
  python3 scripts/check_probe_disjoint.py            # 全部语料
  python3 scripts/check_probe_disjoint.py a.jsonl b.jsonl   # 指定语料
退出码: 0=全过, 1=任一碰撞/不一致。
"""
import glob
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

from eval_citation_gate import load_probes, check_disjoint  # noqa: E402

CORPORA_DIR = os.path.join(ROOT, "data", "corpora")


def verify_manifest(data_path):
    """manifest 存在则校验 sha256（LF 归一化）与行数；返回 (ok, 信息)。"""
    stem = os.path.splitext(os.path.basename(data_path))[0]
    for cand in (os.path.join(CORPORA_DIR, f"{stem}_manifest.json"),
                 os.path.join(CORPORA_DIR, "corpus_manifest.json")):
        if not os.path.exists(cand):
            continue
        m = json.load(open(cand, encoding="utf-8"))
        # corpus_manifest.json 是事实语料的专用清单（applies_to 声明适用范围）；
        # 其他语料无 stem manifest 时不得误配到它（10-28 sft_anchor_extra 误报教训）
        applies = m.get("applies_to")
        if applies and applies != os.path.basename(data_path):
            continue
        if m.get("sha256") is None:
            return True, "manifest 无 sha 字段，跳过"
        raw = open(data_path, "rb").read()
        sha = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
        rows = sum(1 for _ in open(data_path, encoding="utf-8"))
        if m["sha256"] != sha or (m.get("rows") not in (None, rows)):
            return False, (f"manifest 不符: sha {m['sha256'][:12]}… vs {sha[:12]}…, "
                           f"rows {m.get('rows')} vs {rows}")
        return True, (f"manifest ok（{rows} 行 / 唯一 {m.get('unique_questions', '?')}）")
    return True, "无适用 manifest，跳过"


def main():
    probes, meta = load_probes(os.path.join(HERE, "gate_probes_v2.json"))
    print(f"探针集 {meta.get('version')}: {len(probes)} 道")

    targets = sys.argv[1:] or sorted(
        glob.glob(os.path.join(CORPORA_DIR, "sft_*.jsonl")))
    if not targets:
        print("FAIL: 未找到任何语料", file=sys.stderr)
        return 1

    n_fail = 0
    for path in targets:
        name = os.path.basename(path)
        r = check_disjoint(probes, path, verbose=False)
        if not r.get("checked"):
            print(f"FAIL {name}: 文件缺失")
            n_fail += 1
            continue
        m_ok, m_msg = verify_manifest(path)
        state = "ok  " if (r["disjoint"] and m_ok) else "FAIL"
        if state == "FAIL":
            n_fail += 1
        print(f"{state} {name:28} 碰撞 {len(r['collisions']):3} ｜ {m_msg}")
        if r["collisions"]:
            print(f"       碰撞题: {r['collisions'][:8]}")

    print(f"\nPROBE-DISJOINT + MANIFEST: {len(targets) - n_fail}/{len(targets)} passed")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main() or 0)