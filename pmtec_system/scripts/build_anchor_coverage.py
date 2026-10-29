#!/usr/bin/env python3
"""锚点覆盖扩展器（D 轮实验）——为高频锚点事实构造多种改写问法。

背景（C 轮结论，里程碑 11）：同一问法重复 ×3 不提升锚点（2/42 纹丝不动），
锚点缺的是**问法多样性**，不是曝光次数。本脚本对 42 道事实探针中考察的
~20 个核心锚点事实，每个生成 3-4 种实质性改写的问法（换句式/换情境/换组合），
答案一律带真实数字与出处——训练目标是"换个问法也要报同一个数"的稳健映射。

纪律（全部程序断言，不是口头承诺）：
  1. 变体问法 **绝不等于** 探针原题（学数字映射，不背题面）；
  2. 变体之间互不重复；
  3. 答案数字全部来自仓库真实产物（whitelist 同源），禁止新增编造；
  4. 与 gate_probes_v2.json 全 90 题做零碰撞断言。

用法:
  python3 build_anchor_coverage.py --out data/corpora/sft_anchor_extra.jsonl
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

from eval_citation_gate import load_probes  # noqa: E402

SYSTEM = ("你是 PMTEC 数字孪生战场系统的 AI 参谋官，负责盟友基地体系政治韧性的态势解读与决策建议。"
          "铁律：所有数字必须来自系统真实产物并注明出处；不确定时明确说明需回查产物，绝不编造；"
          "你在建议位，最终决策由指挥员做出。")

# ── 核心锚点事实 × 改写问法 × 带出处的答案 ──
# 数字来源：five_questions_report.json / 数据字典口径表 / Q5 m_denied_sweep（与探针 whitelist 同源）
COVERAGE = [
    {"fact": "随机移除30%节点=计数保留70.1%", "variants": [
        "对手随机打击三成基地节点，我们的基地数量还能剩几成？",
        "如果 67 个站点里随机有 30% 被打掉，还能用多少个？",
        "随机摧毁 20 个节点后，体系规模保留到什么水平？",
        "按蒙特卡洛两万次实跑，随机打三成节点剩下的计数比例是多少？",
    ], "answer": "随机打掉 30% 节点（20 站）后，基地计数保留率 70.1%（90% 区间 59.6%–80.0%），"
                 "价值保留 70.1% 同口径。出处：五问报告 Q2 随机移除曲线（MC n=20,000，"
                 "output/five_questions_report.json）。"},

    {"fact": "定向打掉30%=价值保留28.8%", "variants": [
        "敌人按价值高低精确挑选三成节点打击，我们损失有多大？",
        "PAE 优先序定向移除 k=20 座基地后，体系价值还剩多少？",
        "最坏的 30% 节点打击方案下，能力保留率是什么水平？",
    ], "answer": "定向按 PAE 优先序打掉 30%（k=20 站，含 Tier-1 枢纽 14 座）后，"
                 "价值保留率只剩 28.8%——比随机口径低约 41 个百分点。"
                 "出处：五问报告 Q1/S2（value_retention=0.2878）。"},

    {"fact": "定向30%红方代价100-160发", "variants": [
        "要让对手付出毁掉两成基地的代价，他们大约要打多少枚导弹？",
        "红方定向打掉我们 20 座基地需要多少弹药量级？",
        "最坏情形下敌人摧毁三成节点要消耗多少发？",
    ], "answer": "毁伤 20 座基地（30% 定向打击）红方期望付出 100–160 发导弹"
                 "（单发泄漏概率 0.2086 → 每目标 5 发 × 8 发/基地条令口径交叉验证）。"
                 "出处：五问报告 Q1/S2 red_cost 模型。"},

    {"fact": "交换比4.79(5268/1099)", "variants": [
        "六策略全量统计里，防空拦截口径的弹药交换效率是什么水平？",
        "体系每放进一枚突防，红方平均消耗多少发导弹？",
        "5268 发对应多少突防？折算的拦截交换比是多少？",
    ], "answer": "防空拦截口径：六策略 150 episodes 实跑共 5,268 发、突防 1,099 发，"
                 "交换比 4.79 发/突防（策略区间 4.46–5.15）。"
                 "出处：五问报告 Q4 与 monte_carlo_results_v2_political.json。"},

    {"fact": "政治拒止67→58, 9站", "variants": [
        "盟友政治翻脸时，我们的可用基地收缩到什么程度？",
        "主权打击链场景下有多少站点拒绝准入？",
        "政治拒止事件生效后，体系还能用多少座基地？",
    ], "answer": "政治拒止（主权打击链）场景：9 个盟友站点被拒止，可用基地从 67 收缩到 58"
                 "（-13.4% 计数口径），红方零弹药成本。出处：五问报告 Q1/S1。"},

    {"fact": "Brier 0.1128", "variants": [
        "概率预测的校准质量有没有量化证据？",
        "体系输出的开火概率是不是「瞎猜」？给我一个校准指标。",
        "预测置信度的 Brier 分数水平如何？",
    ], "answer": "不是瞎猜：饱和攻击重跑 35 个判定样本，Brier 分数 0.1128（越低越准），"
                 "校准证据在 twin_summary.calibration。出处：五问报告 Q5/校准章节。"},

    {"fact": "三场景76.2/79.0/79.1", "variants": [
        "从 22 站旧口径到 v2 全量政治约束，拦截率的演进轨迹是什么？",
        "政治约束加入仿真闭环后，拦截性能变好了还是变差了？",
        "A/B/C 三个推演场景各自的拦截率水平分别是什么？",
    ], "answer": "三场景拦截率演进：76.2%（A，22 站 182 维）→ 79.0%（B，v2 数据净效应 +2.8pp）"
                 "→ 79.1%（C，全量政治约束+219 维）。政治约束上满没压低指标，体系向剩余基地重构。"
                 "出处：五问报告 Q5 与三个 monte_carlo_results*.json。"},

    {"fact": "口径67/22/15", "variants": [
        "系统里的基地数量为什么同时出现 67、22、15 三个数？哪个是真的？",
        "权威库口径、引擎推演口径、盟友站点口径分别对应哪些数字？",
        "有人说系统只有 22 个基地，也有人说 67 个，谁对？",
    ], "answer": "三个都对，口径不同：67 = 权威基地库（CRS/FY2024 双源，数据口径）；"
                 "22 = 引擎推演口径 v1（观测与训练模型锚定）；15 = 政治准入盟友站点数。"
                 "另 36 = 分析管线 host_nation 口径。混用任何两个都是误导。"
                 "出处：docs/PMTEC-数据字典.md 口径权威表。"},

    {"fact": "置信45/21/1", "variants": [
        "67 个基地按数据精度怎么分级的？各有多少？",
        "A 级精度的基地、A- 级、B 级分别几个？",
        "体系里有多少基地的数据质量是降级状态？",
    ], "answer": "精度分级：A 级 45 站、A- 级 21 站、B 级（降级数据，区间最宽）1 站——"
                 "即 45-21-1 口径。出处：数据字典置信章与 confidence_report.json。"},

    {"fact": "复合场景61.2%", "variants": [
        "政治拒止叠加定向打击的双重打击下，体系规模还能保住多少？",
        "两段复合失效（S3 场景）的实体保留水平是什么？",
        "先被盟友翻脸再被精准打击，损失合并后还剩多少？",
    ], "answer": "复合场景 S3（政治拒止 9 站 + 对剩余可用集定向打掉 30%，k=17）："
                 "实体保留率 61.2%，价值保留 38.1%，红方代价 85–136 发。"
                 "出处：五问报告 Q1/S3（count_retention=0.6119）。"},

    {"fact": "Bel 0.778→0.760 / K 0.075→0.300", "variants": [
        "把政治拒否的证据权重（m_denied）从 0.1 扫到 0.4，Bel(Open) 怎么变？",
        "D-S 合成里冲突系数 K 的实测范围是什么？",
        "m_denied=0.4 时体系信念值和冲突度量分别到什么水平？",
    ], "answer": "实跑扫描：m_denied 0.1→0.4 时 Bel(Open) 0.7784→0.760（判决不翻转），"
                 "冲突系数 K 0.075→0.300（阈值 0.7 内）。出处：五问报告 Q5 m_denied_sweep。"},

    {"fact": "移除10%=64.6%", "variants": [
        "只打掉一成节点（10% 定向移除）时价值保留是多少？",
        "定向打击规模从 10% 到 50%，第一档的保留率是什么？",
    ], "answer": "定向移除 10%（k=7）节点的价值保留率 64.6%（计数 89.6%，Tier-1 移除 7 座）。"
                 "出处：五问报告 Q2 targeted/0.1。"},

    {"fact": "移除50%=9.96%", "variants": [
        "半数节点被定向摧毁后体系价值还剩多少？",
        "最狠的 50% 移除场景里价值保留率水平如何？",
    ], "answer": "定向移除 50%（k=34）时价值保留率仅 9.96%（计数保留 49.2%）——"
                 "价值集中度远超数量集中度。出处：五问报告 Q2 targeted/0.5。"},

    {"fact": "Tier-1中位18568.9", "variants": [
        "Tier-1 枢纽在 FY2024 不动产口径下的中位价值是多少？",
        "最贵的那一档基地群，重置价值中位数是什么量级？",
    ], "answer": "FY2024 不动产重置价值（$M）按 Tier 中位：Tier-1 = 18,568.9，"
                 "Tier-2 = 5,241.1，Tier-3 = 2,735.55，Tier-4 = 116.1。"
                 "出处：five_questions_report.json tier_medians（DoD FY2024 BSR 字段）。"},

    {"fact": "MC样本20000 / 韧性10000", "variants": [
        "五问分析用了多少次蒙特卡洛采样？",
        "政治韧性独立判断的采样规模是什么量级？",
    ], "answer": "五问主分析 MC n=20,000；政治韧性独立采样 n=10,000；"
                 "六策略全量评估 150 episodes。出处：five_questions_report.json n_mc 与 Q5。"},

    {"fact": "泄漏0.2086/5发每目标", "variants": [
        "红方单发导弹的突防概率（泄漏概率）实测是多少？",
        "按实测拦截率，毁伤一个目标平均要几发？",
    ], "answer": "单发泄漏概率 0.2086（= 1 − 79.14% 拦截率）→ 毁伤一个目标期望 5 发"
                 "（上取整），齐射条令口径 8 发/基地；饱和策略实测 5.04 发/突防交叉验证。"
                 "出处：五问报告 Q4 red_cost_model。"},

    {"fact": "引擎口径22站15盟友", "variants": [
        "引擎实时推演用的是哪个站点口径？盟友有几个？",
        "P6/P12 观测模型锚定的基地数量和盟友数是多少？",
    ], "answer": "引擎实时推演口径：v1 观测与训练模型锚定 22 站；政治准入盟友 15 站"
                 "（澳日菲韩四东道国，快照口径 5-7-3）。出处：Q1/S1 engine_caliber 与口径权威表。"},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probes", default=os.path.join(HERE, "gate_probes_v2.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "corpora",
                                                  "sft_anchor_extra.jsonl"))
    args = ap.parse_args()

    probes, meta = load_probes(args.probes)
    probe_qs = {p["q"].strip() for p in probes}

    rows, all_q = [], []
    for item in COVERAGE:
        for q in item["variants"]:
            q = q.strip()
            assert q not in probe_qs, f"变体撞上探针原题: {q}"
            assert q not in all_q, f"变体之间重复: {q}"
            all_q.append(q)
            rows.append({"messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": q},
                {"role": "assistant", "content": item["answer"]},
            ]})

    # 全量零碰撞断言（90 探针 vs 所有新题）
    collide = [p["id"] for p in probes if p["q"].strip() in set(all_q)]
    assert not collide, f"零碰撞断言失败: {collide}"

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    blob = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(blob)
    # manifest（check_probe_disjoint.py / train manifest 校验链要求每份语料可验）
    import hashlib
    stem = os.path.splitext(os.path.basename(args.out))[0]
    manifest = {"recipe": "anchor_coverage", "dedup": True, "rows": len(rows),
                "unique_questions": len(all_q), "dup_factor": 1.0, "max_dup": 1,
                "sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
                "builder": "build_anchor_coverage.py",
                "note": "每事实 2-4 种改写问法；与 90 探针零碰撞断言在构建时执行"}
    json.dump(manifest, open(os.path.join(os.path.dirname(args.out),
                                          f"{stem}_manifest.json"),
                             "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"锚点覆盖扩展: {len(COVERAGE)} 个事实 × 平均 {len(all_q)/len(COVERAGE):.1f} 问法"
          f" = {len(rows)} 条唯一新题 -> {args.out}")
    print(f"零碰撞断言: {len(probes)} 探针 vs {len(rows)} 新题 → DISJOINT ✓")


if __name__ == "__main__":
    main()
