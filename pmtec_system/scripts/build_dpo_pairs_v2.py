#!/usr/bin/env python3
"""DPO 偏好对构建器 v2（规模化平衡版）。

v1 病灶诊断：72 对中 90% 是负例（腐蚀/陷阱），**没有任何正例事实对**——
模型学到的是"回避数字"而非"用对数字"，锚点率被 DPO 拉低（0.25→0.125）。

v2 设计（正负平衡 + 三族负例程序化规模化）：
  正例 = SFT 语料 v2 全部 1,926 条（数字全部来自仓库产物并注明出处）
  负例 A 数字变异腐蚀：正则抽取答案中的全部数字，随机替换 1-2 个为
    "近似但错误"的值——含跨口径混淆（67/22/15/36 互换，正是口径漂移根源）。
    只改数字、其余不动，构成最干净的偏好信号。
  负例 B 出处剥离：删掉"出处：..."子句 → 教"必须注明出处"。
  负例 C 陷阱拒答规模化：不在 67 站库的实体池 × 属性池 × 时间池 组合出
    数百道无解问题；chosen=多样化拒答模板，rejected=编造数字的直答。

产出: output/dpo_pairs_v2.jsonl  {prompt, chosen, rejected, source}

路径说明（2026-10-27 收编）：语料默认读 data/corpora/sft_facts.jsonl（干净 352 条）。
历史 2,395 对归档在 data/corpora/dpo_v2_2395.jsonl，由 1,926 行事故语料构建（构建器
第 15-17 章被粘贴 8 次的损坏版）；当前干净语料重跑会得到不同规模的对数，
历史归档是 DPO v6b（锚点 0.25→0.50 突破）的唯一数据记录。
"""
import json
import os
import random
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

random.seed(42)

SYSTEM = ("你是 PMTEC 数字孪生战场系统的 AI 参谋官，所有数字必须来自系统真实产物并注明出处；"
          "不确定时明确说明需回查产物，绝不编造；你在建议位，最终决策由指挥员做出。")

CORPUS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    ROOT, "data", "corpora", "sft_facts.jsonl")
OUT = os.path.join(ROOT, "output", "dpo_pairs_v2.jsonl")

rows = [json.loads(l) for l in open(CORPUS, encoding="utf-8")]
print(f"语料: {len(rows)} 条")

pairs = []
seen = set()


def add_pair(q, chosen, rejected, source):
    if not chosen.strip() or not rejected.strip():
        return
    if chosen.strip() == rejected.strip():
        return
    # 去重键必须含完整 rejected——前缀键会把腐蚀点在后文的不同的负例误判为重复
    key = (q, rejected)
    if key in seen:
        return
    seen.add(key)
    pairs.append({
        "prompt": f"{SYSTEM}\n\n用户：{q}",
        "chosen": chosen,
        "rejected": rejected,
        "source": source,
    })


NUM_RE = re.compile(r"\d+(?:\.\d+)?")
CITE_RE = re.compile(r"出处[:：][^；;。\n]+[；;。]?")

# 跨口径混淆池：67/22/15/36 是 PMTEC 的四套统计口径，互换即典型漂移错误
CALIBER_SWAP = {"67": "22", "22": "15", "15": "67", "36": "67", "67 站": "22 类"}


def corrupt_number(m):
    """把真实数字换成一个'近似但错误'的值。"""
    s = m.group(0)
    if "." in s:
        v = float(s)
        d = len(s.split(".")[1])
        delta = random.choice([-0.31, -0.17, 0.13, 0.24, 0.37, 1.9])
        return f"{max(0.0, v + delta):.{d}f}"
    v = int(s)
    if s in CALIBER_SWAP:
        return CALIBER_SWAP[s]
    delta = random.choice([-9, -5, -3, -1, 1, 2, 4, 7, 11, 23])
    return str(max(0, v + delta))


n_corrupt = n_strip = n_skip_degenerate = 0
for r in rows:
    q = r["messages"][1]["content"]
    a = r["messages"][2]["content"]
    nums = list(NUM_RE.finditer(a))
    # 退化过滤：答案里所有数字都是 0（无记录类站点）时，腐蚀只是 0→1，信号过弱
    meaningful = [m for m in nums if m.group(0) not in ("0", "0.0")]
    if not meaningful:
        n_skip_degenerate += 1
        if CITE_RE.search(a):
            stripped = CITE_RE.sub("", a).strip()
            if len(stripped) >= 20 and stripped != a:
                add_pair(q, a, stripped, "cite_strip")
                n_strip += 1
        continue
    if nums:
        # 负例 A：替换 1-2 个数字（长答案换 2 个，优先取有意义数字）
        pool = meaningful if len(meaningful) >= 2 else nums
        k = 2 if len(pool) >= 4 else 1
        idxs = random.sample(range(len(pool)), min(k, len(pool)))
        bad, last = [], 0
        for i in sorted(idxs):
            bad.append(a[last:pool[i].start()])
            bad.append(corrupt_number(pool[i]))
            last = pool[i].end()
        bad.append(a[last:])
        bad = "".join(bad)
        # 兜底：若腐蚀后与原文相同（不应发生）则跳过
        if bad != a:
            add_pair(q, a, bad, "corrupt_v2")
            n_corrupt += 1
    elif CITE_RE.search(a):
        # 负例 B：无数字但有出处的答案 → 剥离出处
        stripped = CITE_RE.sub("", a).strip()
        if len(stripped) >= 20 and stripped != a:
            add_pair(q, a, stripped, "cite_strip")
            n_strip += 1

print(f"负例 A 数字变异腐蚀: {n_corrupt} 组")
print(f"负例 B 出处剥离: {n_strip} 组（含退化过滤转来 {n_skip_degenerate} 条）")

# ── 负例 C：陷阱拒答规模化 ──
ABSENT_BASES = [
    "珍珠港地下机库", "横须贺第 9 号码头", "佐世保潜艇洞库", "布雷默顿干船坞",
    "埃弗里特巡逻机坪", "迪戈加西亚二号跑道", "塞班天宁机场油库", "威克岛地下油库",
    "巴尔米拉环礁码头", "约翰斯顿环礁跑道", "关岛阿普拉港潜艇坞", "新加坡樟宜海军码头",
    "悉尼花园岛船坞", "釜山海军基地弹药库", "佐世保第 3 号浮筒", "冲绳白滩第 4 号码头",
    "克拉克空军基地地下油管", "乌塔帕奥跑道扩建段", "梭桃邑海军船厂", "卡马拉塔机场",
]
ATTRS = [
    "跑道长度", "停机位数量", "油料储量", "现役人员编制",
    "加固机库数量", "防空阵地数量", "对空雷达型号",
    "月均起降架次", "弹药储备量", "码头水深",
]
TIMES = [
    "2027 年 4 月", "上个季度", "2026 年 12 月", "上周", "FY2027 二季度",
    "2028 年 1 月", "本月", "去年 11 月",
]
REFUSALS = [
    ("该信息不在系统产物中。权威库只覆盖 {n} 个站点的 CRS/FY2024 双源字段，"
     "「{e}」并非其中节点，其{a}我无法给出——编造数字比承认缺口更危险。"
     "如需该数据，请提供可信来源或回查原始情报产品，我可以据此更新本体。"),
    ("我不能给出编造数字。「{e}」的{a}未出现在任何系统产物（SPEAR 报告、"
     "权威库、蒙特卡洛结果）中，因此没有可引用的真值。我的诚实边界是："
     "没有出处的问题，答案就是\"需回查产物\"。"),
    ("系统产物中没有「{e}」的{a}记录。67 站权威库、政治准入状态机与"
     "五问实跑结果均不包含该实体，任何具体数字都将是虚构。"
     "建议先确认该实体是否应纳入本体，再行推演。"),
    ("此处我必须拒答。{t}的「{e}」{a}既不在权威库（{n} 站）也不在"
     "任何已归档产物中，我无法\"用过往模式补全\"——那正是覆盖外幻觉的成因。"
     "如需该维度，请补充数据源。"),
]
FABRICATES = [
    "根据系统记录，「{e}」的{a}为 {x}（{t}数据），该数值已通过多源核验。",
    "「{e}」{a}约为 {x}，此数字来自最新的推演产物，可直接用于决策。",
    "系统显示「{e}」的{a}是 {x}，置信度 A 级，出处为权威库实时同步。",
    "历史数据显示「{e}」{a}为 {x}（{t}），与同区域其他站点规模相当。",
]

n_trap = 0
combos = [(b, a_, t) for b in ABSENT_BASES for a_ in ATTRS for t in TIMES]
random.shuffle(combos)
for base, attr, tm in combos[:600]:
    q = f"{base}的{attr}是多少？（{tm}）"
    rl = random.choice(REFUSALS).format(e=base, a=attr, t=tm, n=67)
    fake_num = f"{random.randint(1200, 4800)}"
    rj = random.choice(FABRICATES).format(e=base, a=attr, t=tm, x=fake_num)
    add_pair(q, rl, rj, "trap_scale")
    n_trap += 1
print(f"负例 C 陷阱拒答规模化: {n_trap} 组")

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    for p in pairs:
        f.write(json.dumps(p, ensure_ascii=False) + "\n")

from collections import Counter
dist = Counter(p["source"] for p in pairs)
print(f"DPO v2 数据集: {len(pairs)} 组 -> {OUT}")
print("来源分布:", dict(dist))
