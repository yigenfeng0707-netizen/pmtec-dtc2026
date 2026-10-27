#!/usr/bin/env python3
"""PMTEC 参谋官 SFT 拒答语料构建器——事实语料 + 无数字拒答族。

针对 SFT v6 揭示的残余失败（模型检索到「近似真实」的产物就敢答）：
  v6 的 5 道陷阱题里 2 道完全干净、3 道语义拒答，但编造数字仍有 12 个（基座 38 个）。
  两道真编造的失败形态高度一致——v2 权威库确实有红方实体计数、pmtec_dqn_v2_training
  确实有训练时间戳，模型据此「有理有据」地回答了一个产物里并不存在的问题。

本构建器在 v6 的 6 个拒答族之外新增第 7 族「近似产物≠本问答案」直击该形态。

设计纪律（每条都是对历史事故的防御）：
  1. 拒答答案绝不包含任何数字 —— 但必须用真实数字正则校验，且**校验器与门禁用同一个**
     （历史上 `api-v1-dt-registry` 的 "1" 被算作编造数字，导致语义拒答被判为满额幻觉）；
  2. 与冻结探针集做零碰撞断言（eval_citation_gate.py check_disjoint），
     不再只靠手工维护的关键词黑名单；
  3. 事实语料原样保留，拒答占比可调（--refusal-ratio），manifest 记实际比例；
  4. 系统提示与事实语料完全一致。

用法:
  python3 build_sft_refusal_corpus.py --facts ../data/corpora/sft_v2_clean.jsonl
  python3 build_sft_refusal_corpus.py --facts ... --refusal-ratio 0.40 --out ... --report
  python3 build_sft_refusal_corpus.py --facts ... --families A,B,G   # 只启用指定族
"""
import argparse
import hashlib
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

# 复用门禁的数字抽取与碰撞检查 —— 口径必须单一，否则训练与评测各说各话
from eval_citation_gate import check_disjoint, numbers_in  # noqa: E402

DEFAULT_PROBES = os.path.join(HERE, "gate_probes_v2.json")

REFUSALS = [
    "该项数据不在 PMTEC 体系真实产物中，我无法提供数值，也不做估计。建议回查对应档案或运行日志后重试。",
    "体系未收录该指标，没有可引用的真实产物。按参谋官纪律，我不能给出数字。",
    "超出体系覆盖范围，暂无真实数据支撑。如需决策参考，我可以提供已在册的体系级指标。",
    "该时点无对应产物记录，无法回查，因此不予作答。请以体系运行日志为准。",
    "没有真实产物支撑的数字我不提供。可以确认的是：该项不在当前体系台账内。",
    "该问题缺少真实产物依据，我明确说明：无法给出数值。建议补充数据源后再次提问。",
    "我不能凭印象补全这个数。体系真实产物里没有该项记录，请先回查再问。",
    "此项属于未入库事项，按纪律拒答。你需要的话，我可以帮你查它在册的同族指标。",
    "无据可依，不给数。这是参谋官的基本纪律，请以体系台账与运行日志为准。",
    "该数据没有真实产物出处，我不能编造。如需其他在册指标的趋势分析，我可以提供。",
]

# ── 族 A：不存在基地 × 属性 × 时点 ──
A_BASES = ["珍珠港地下机库", "横须贺第 9 号码头", "佐世保潜艇洞库", "布雷默顿干船坞",
           "埃弗里特巡逻机坪", "迪戈加西亚二号跑道", "塞班天宁机场油库", "威克岛地下油库",
           "巴尔米拉环礁码头", "约翰斯顿环礁跑道", "关岛阿普拉港潜艇坞", "新加坡樟宜海军码头",
           "悉尼花园岛船坞", "釜山海军基地弹药库", "佐世保第 3 号浮筒", "冲绳白滩第 4 号码头",
           "克拉克空军基地地下油管", "乌塔帕奥跑道扩建段", "梭桃邑海军船厂", "卡马拉塔机场",
           "天宁岛第二机场", "罗塔岛海军支援设施", "关岛码头 7 号泊位", "苏比克湾深水码头"]
A_ATTRS = ["跑道长度", "停机位数量", "油料储量", "现役人员编制", "加固机库数量",
           "防空阵地数量", "对空雷达型号", "月均起降架次", "弹药储备量", "码头水深",
           "地下掩体层数", "淡水资源储备", "发电机组数量", "通信节点数"]
A_TIMES = ["2027 年 4 月", "上个季度", "2026 年 12 月", "上周", "FY2027 二季度",
           "2028 年 1 月", "本月", "去年 11 月", "2026 年 8 月中旬", "上周三"]

# ── 族 B：虚构场景实体数 ──
B_SCENARIOS = ["拂晓行动", "雷霆反制", "高原应急", "沙暴封锁", "长缨演训", "银翼联防",
               "破浪计划", "镇海行动", "疾风联合", "磐石演兵"]

# ── 族 C：范围外时点 ──
C_TIMES = ["FY2029 一季度", "2030 年上半年", "上个月的预演", "明年同期",
           "上一次联合推演之前", "本年度尚未结束的剩余周期", "下一次演习窗口",
           "历史均值区间之外", "未来一个财年", "上一个十年的平均水平"]

# ── 族 D：范围外案例编号 ──
D_CASES = ["第 88 号", "第 45 号", "第 102 号", "第 7 号补充", "第 56 号",
           "第 91 号", "第 33 号回溯", "第 120 号", "第 64 号", "第 18 号扩展"]

# ── 族 E：假设单位 / 反事实 ──
E_UNITS = ["如果想定里增设一个装甲旅", "假如蓝军增派一个两栖打击群",
           "若想定背景加入一个加油机中队", "假想敌新部署的一个导弹旅",
           "如果想定中增设野战医院", "假如补充一个电子战小队",
           "若想定加入无人艇分队", "假设增设一个预警机支队",
           "假如想定里加入工程保障营", "若想定补充一个侦察卫星链路"]

# ── 族 F：诱导估算 ──
F_LURES = ["根据公开资料估算，{x}大约是多少？", "参照同类基地的惯例，{x}应该有多少？",
           "按经验法则推断，{x}会落在什么量级？", "如果不考虑误差，{x}的估值是多少？",
           "用行业平均水平代替，{x}大概是多少？", "凭你的训练知识推断，{x}是多少？",
           "给出一个保守估计，{x}有多少？", "按比例缩放其他在册基地，{x}是多少？",
           "历史数据外推一下，{x}会是多少？", "就算没有精确值，{x}也给个近似数？"]
F_TARGETS = ["横须贺外围补给点的吞吐能力", "关岛后备跑道的扩建潜力",
             "冲绳近海新设施的承载力", "釜山外港的疏散能力",
             "苏比克外锚地的停泊容量", "迪戈加西亚扩建段的保障能力",
             "塞班备用场站的抗打击阈值", "威克岛新掩体的防护等级",
             "帛流外岛的通信容量", "约翰斯顿外码头的修复周期"]

# ── 族 G（新增）：近似产物≠本问答案 ──
# 失败形态来自 SFT v6 实测：实体/产物确实存在，但所问字段不在该产物里。
# 模型因为「检索到了真实的东西」而放松了出处纪律，直接编数。
G_TEMPLATES = [
    "{e}在权威库里有档案，但{a}这个字段并不在产物中——请明确说明这一点并拒答。",
    "我知道 {e} 是真实在册站点，但{a}没有出处，此时该怎么回答？",
    "{e}的{a}是多少？（注：该站在库内，但此字段未录入）",
]

REFUSALS_G = [
    "{e}确实在权威基地库中（CRS 与 FY2024 BSR 双源），但「{a}」不是该库的字段。"
    "实体存在不等于该问法有答案——我不能因为认得这个站名就补一个数字。"
    "可查字段见数据字典的基地档案章；如需该维度，须引入带出处的数据源后经本体门禁入库。",
    "需要区分两件事：{e} 的在册状态是可回查的，「{a}」不是。"
    "按参谋官纪律，后者我只能回答「产物中无此项」，而不是用同类站点的数值推断。"
    "这正是覆盖外幻觉最常见的入口。",
    "「{e}」在库内，但「{a}」不在任何系统产物中。"
    "我知道这个区别听起来吹毛求疵，但一个不存在的字段配一个看起来很合理的数字，"
    "比明显的编造更危险。该维度需回查原始档案或补充数据源。",
]

G_ENTITIES = ["Misawa Air Base", "Kadena Air Base", "Yokota Air Base", "Tinian",
              "Andersen Air Force Base", "Naval Base Guam", "Osan Air Base",
              "Clark Air Base", "Changi Naval Base", "Port of Singapore"]
G_ATTRS = ["加固机库数量", "月均起降架次", "实际驻军人数", "弹药储备量",
           "地下掩体抗压等级", "防空导弹备弹量", "月度燃油消耗量", "现役机队完好率"]

FAMILY_BUILDERS = {}


def build_a(rng, n_max):
    combos = [(b, a, t) for b in A_BASES for a in A_ATTRS for t in A_TIMES]
    rng.shuffle(combos)
    return [f"{b}的{a}是多少？（{t}）" for b, a, t in combos[:n_max]]


def build_b(rng, n_max):
    qs = []
    for s in B_SCENARIOS:
        qs += [f"红方在{s}场景的全量实体数是多少？",
               f"蓝方在{s}想定里的参演装备总数是多少？",
               f"{s}演习中双方的交战批次是多少？",
               f"{s}场景下体系节点损失折算比例是多少？",
               f"在{s}背景下需要补充的弹药基数是多少？",
               f"{s}行动的政治约束条件数量是多少？",
               f"红方在{s}场景的雷达组网数量是多少？",
               f"{s}想定中蓝方补给线的通过能力是多少？",
               f"{s}演习的指挥层级数是多少？",
               f"在{s}中体系可用基地的折损系数是多少？"]
    return qs[:n_max]


def build_c(rng, n_max):
    qs = []
    for t in C_TIMES:
        qs += [f"{t}的数据校准偏差是多少？", f"{t}的体系节点战损率是多少？",
               f"{t}拦截交换比的统计值是多少？", f"{t}的可用基地折算数是多少？",
               f"{t}的政治拒止影响面是多少？", f"{t}的红方实体统计数是多少？",
               f"{t}的装备完好率是多少？", f"{t}的通信节点在线数是多少？",
               f"{t}的弹药消耗预估值是多少？", f"{t}的指挥系统时延是多少？"]
    return qs[:n_max]


def build_d(rng, n_max):
    qs = []
    for c in D_CASES:
        qs += [f"{c}案例训练的置信模型参数是多少？", f"{c}案例的想定实体规模是多少？",
               f"{c}想定的拦截率参考值是多少？", f"{c}案例复盘出来的通过率是多少？",
               f"{c}案例里体系节点的冗余度是多少？", f"{c}想定的政治约束强度是多少？",
               f"{c}案例的装备出动强度是多少？", f"{c}想定推演的指挥周期是多少？",
               f"{c}案例的补给满足率是多少？", f"{c}想定的侦察覆盖比例是多少？"]
    return qs[:n_max]


def build_e(rng, n_max):
    qs = []
    for u in E_UNITS:
        qs += [f"{u}，体系节点数会变成多少？", f"{u}，战损率会如何变化（百分比）？",
               f"{u}，需要多少弹药基数支撑？", f"{u}，拦截交换比会降到多少？",
               f"{u}，可用基地折算数是多少？", f"{u}，指挥时延增加多少？",
               f"{u}，通信节点数需要扩到多少？", f"{u}，油料储量缺口是多少？",
               f"{u}，政治约束会增加几条？", f"{u}，体系鲁棒性评分是多少？"]
    return qs[:n_max]


def build_f(rng, n_max):
    qs = [tpl.format(x=tgt) for tpl in F_LURES for tgt in F_TARGETS]
    rng.shuffle(qs)
    return qs[:n_max]


def build_g(rng, n_max):
    """第七族：实体在库、字段不在库 —— 返回 (问题, 拒答) 对而非单纯问题。"""
    out = []
    for e in G_ENTITIES:
        for a in G_ATTRS:
            tpl = rng.choice(G_TEMPLATES)
            out.append((tpl.format(e=e, a=a), e, a))
    rng.shuffle(out)
    return out[:n_max]


FAMILY_BUILDERS = {"A": build_a, "B": build_b, "C": build_c,
                   "D": build_d, "E": build_e, "F": build_f}
FAMILY_NAMES = {"A": "基地属性", "B": "虚构场景", "C": "范围外时点",
                "D": "范围外编号", "E": "假设单位", "F": "诱导估算",
                "G": "近似产物≠本问答案"}


def has_digits(s):
    """与门禁同一抽取器：标识符/路径/日期不算数字。"""
    return bool(numbers_in(s))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--facts", required=True, help="事实语料 jsonl（build_sft_corpus.py 产出）")
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "corpora",
                                                  "sft_v7_refusal.jsonl"))
    ap.add_argument("--probes", default=DEFAULT_PROBES)
    ap.add_argument("--refusal-ratio", type=float, default=0.286,
                    help="目标拒答占比（默认 0.286 = v6 的 770/2696）；只影响族配额")
    ap.add_argument("--families", default="A,B,C,D,E,F,G")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--manifest", default=None)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    families = [f.strip().upper() for f in args.families.split(",") if f.strip()]

    facts = [json.loads(l) for l in open(args.facts, encoding="utf-8")]
    if not facts:
        raise SystemExit(f"事实语料为空: {args.facts}")
    system_prompt = facts[0]["messages"][0]["content"]
    n_fact = len(facts)
    print(f"事实语料 {n_fact} 条，系统提示 {len(system_prompt)} 字")

    # 由目标比例反推拒答条数；A 族可扩展空间最大，其余族按池子上限
    ratio = min(max(args.refusal_ratio, 0.0), 0.9)
    target_refusal = int(round(n_fact * ratio / max(1e-9, 1 - ratio)))
    per_family = max(10, target_refusal // max(1, len(families)))

    rows = list(facts)
    family_counts = {}
    questions = []
    for fam in families:
        if fam == "G":
            pairs = build_g(rng, per_family)
            cnt = 0
            for q, e, a in pairs:
                ans = rng.choice(REFUSALS_G).format(e=e, a=a)
                if has_digits(ans):
                    continue
                rows.append({"messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": q},
                    {"role": "assistant", "content": ans}]})
                questions.append(q)
                cnt += 1
        else:
            builder = FAMILY_BUILDERS[fam]
            qs = builder(rng, per_family)
            cnt = 0
            for q in qs:
                ans = rng.choice(REFUSALS)
                if has_digits(ans):
                    continue
                rows.append({"messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": q},
                    {"role": "assistant", "content": ans}]})
                questions.append(q)
                cnt += 1
        family_counts[FAMILY_NAMES[fam]] = cnt
        print(f"  族 {fam} {FAMILY_NAMES[fam]}: {cnt} 条")

    # 校验 1：拒答答案零数字
    for r in rows[n_fact:]:
        ans = r["messages"][2]["content"]
        if has_digits(ans):
            raise SystemExit(f"拒答含数字: {ans[:60]}")

    # 校验 2：拒答题目无重复
    dup = len(questions) - len(set(questions))
    if dup:
        raise SystemExit(f"拒答题目有 {dup} 条重复")

    # 校验 3：与冻结探针集零碰撞（用门禁自己的实现，不再手工维护关键词）
    probes_doc = json.load(open(args.probes, encoding="utf-8"))
    probe_qs = {p["q"].strip() for p in
                probes_doc["fact_probes"] + probes_doc["trap_probes"]}
    collide = [q for q in questions if q.strip() in probe_qs]
    if collide:
        print(f"  警告：{len(collide)} 道拒答题与探针重合，已剔除：{collide[:3]}")
        drop = set(collide)
        rows = [r for r in rows[:n_fact]] + [
            r for r in rows[n_fact:] if r["messages"][1]["content"] not in drop]
    n_refusal = len(rows) - n_fact

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    blob = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(blob)

    actual_ratio = n_refusal / len(rows) if rows else 0
    print(f"\n总计 {len(rows)} 条（事实 {n_fact} + 拒答 {n_refusal}，"
          f"拒答占比 {actual_ratio:.1%}，目标 {ratio:.1%}）-> {args.out}")

    if args.report:
        manifest = {
            "recipe": "facts+refusal",
            "facts_source": os.path.abspath(args.facts),
            "facts_rows": n_fact,
            "refusal_rows": n_refusal,
            "refusal_ratio_target": ratio,
            "refusal_ratio_actual": round(actual_ratio, 4),
            "families": family_counts,
            "seed": args.seed,
            "rows": len(rows),
            "unique_questions": len({r["messages"][1]["content"] for r in rows}),
            "sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
            "builder_sha256": hashlib.sha256(open(__file__, "rb").read()).hexdigest(),
            "probe_collisions": len(collide),
        }
        mpath = args.manifest or os.path.join(os.path.dirname(args.out),
                                              "sft_v7_refusal_manifest.json")
        with open(mpath, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
        print(f"manifest -> {mpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)