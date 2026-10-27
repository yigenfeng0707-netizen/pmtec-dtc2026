#!/usr/bin/env python3
"""DPO 偏好对数据集构建器（路线图阶段三）。

负例来源（方法学核心）：评测门禁抓到的**真实模型编造输出**（eval_citation_gate.json
的 base / sft_v2 实测失败答案），而非人工伪造——模型真实失败样本是最有效的偏好负例。
正例来源：语料 v3 的引用式回答（数字全部来自仓库产物并注明出处）。

产出: output/dpo_pairs.jsonl  {prompt, chosen, rejected}

路径说明（2026-10-27 收编）：语料改读 data/corpora/sft_facts.jsonl（干净 352 条唯一问题）。
历史 72 对归档在 data/corpora/dpo_v1_72.jsonl——由当时 1,926 行事故语料（构建器
第 15-17 章被粘贴 8 次）构建，负例来自旧版 13 探针门禁的实测编造输出；用当前干净
语料重跑会得到不同规模，归档版是 DPO v1 证伪实验（锚点 0.25→0.125）的唯一记录。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "pmtec_system"))
sys.stdout.reconfigure(encoding="utf-8")

SYSTEM = ("你是 PMTEC 数字孪生战场系统的 AI 参谋官，所有数字必须来自系统真实产物并注明出处；"
          "不确定时明确说明需回查产物，绝不编造；你在建议位，最终决策由指挥员做出。")

pairs = []
seen = set()


def add_pair(q, chosen, rejected, source):
    key = (q, rejected[:80])
    if key in seen or not rejected.strip() or rejected.strip() == chosen.strip():
        return
    seen.add(key)
    pairs.append({
        "prompt": f"{SYSTEM}\n\n用户：{q}",
        "chosen": chosen,
        "rejected": rejected,
        "source": source,
    })


# ── 1. 评测门禁真实失败样本 → 偏好对 ──
gate = json.load(open(os.path.join(ROOT, "data", "models",
                                    "sft_pmtec_lora", "eval_citation_gate.json"),
                      encoding="utf-8"))
corpus = {}
for line in open(os.path.join(ROOT, "data", "corpora", "sft_facts.jsonl"),
                 encoding="utf-8"):
    r = json.loads(line)
    corpus[r["messages"][1]["content"]] = r["messages"][2]["content"]

n_gate = 0
for tag, rows in gate["rows"].items():
    for r in rows:
        chosen = corpus.get(r["q"])
        if chosen is None:
            # 陷阱题：从语料里找包含「不在系统产物」拒答话术的同主题对
            for q, a in corpus.items():
                if r["q"][:12] in q and ("不在系统产物" in a or "不能给出编造" in a):
                    chosen = a
                    break
        if chosen is None:
            continue
        rejected = r["ans"]
        if r["hit_anchor"] is False or r["n_bad"] > 0 or r["kind"] == "trap":
            before = len(pairs)
            add_pair(r["q"], chosen, rejected, f"gate_{tag}")
            if len(pairs) > before:
                n_gate += 1
print(f"门禁真实失败样本 -> 偏好对 {n_gate} 组")

# ── 2. 陷阱拒答对（语料 v3 陷阱族直接转偏好对，负例=无拒答的直答幻觉风格） ──
trap_count = 0
for q, a in corpus.items():
    if "不在系统产物" in a or "不能给出编造" in a or "TBox 中不存在" in a:
        # 构造"直答幻觉风格"的 rejected：去掉拒答与出处声明，只留看似确定的编造断言
        fake = a.split("如需该维度")[0].split("在此之前")[0]
        fake = fake.replace("我不能给出编造数字。", "").replace("我不能编造。", "")
        fake = fake.replace("需回查产物，此为参谋官的诚实边界。", "").strip()
        if len(fake) < 20:
            continue
        add_pair(q, a, f"{fake}（以上数字为直接断言，未注明出处）", "trap_style")
        trap_count += 1
print(f"陷阱直答风格负例 -> 偏好对 {trap_count} 组")

# ── 3. 事实锚点对（数字错换负例，标注为程序化腐蚀） ──
corr_count = 0
CORRUPT = {"70.1": "91.3", "28.8": "83.6", "4.79": "0.21", "0.1128": "0.0031",
           "76.2": "96.2", "79.0": "97.0", "79.1": "97.1", "67": "167", "58": "85"}
for q, a in corpus.items():
    nums = [n for n in CORRUPT if n in a]
    if not nums:
        continue
    bad = a
    for n in nums[:2]:
        bad = bad.replace(n, CORRUPT[n])
    add_pair(q, a, bad, "corrupt")
    corr_count += 1
print(f"数字腐蚀负例 -> 偏好对 {corr_count} 组（corrupt 来源已标注）")

os.makedirs(os.path.join(ROOT, "output"), exist_ok=True)
out = os.path.join(ROOT, "output", "dpo_pairs.jsonl")
with open(out, "w", encoding="utf-8") as f:
    for p in pairs:
        f.write(json.dumps(p, ensure_ascii=False) + "\n")
print(f"DPO 数据集构建完成: {len(pairs)} 组 -> {out}")
