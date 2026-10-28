#!/usr/bin/env python3
"""PMTEC 参谋官 SFT 语料构建器——全部样本源自仓库真实产物，无编造数字。

输出: output/sft_pmtec.jsonl (Qwen chat messages 格式)
配比: 五问作答 / 口径置信 / 失效边界 / 态势解读(真实SPEAR数据) / 语义知识 /
      工程部署 / 诚实拒答边界  共 7 类

**去重默认关闭 + 上采样显式化**（2026-10-27 改造）：
  去重守卫最初是做 v3 反证实验时引入的，当时直接改写了主干而非加开关，导致主干
  永久停留在一个已被证伪的配方上——HEAD 版本只产 352 条，而 0f323e0 的版本产 1,926 条。

  **但 1,926 行并不是「上采样设计」，而是构建器损坏**：0f323e0 的第 15-17 章（逐基地
  细节 / P1-P18 里程碑 / 安全可观测性）各被整段粘贴了 8 次（实测 `grep -c` 各返回 8）。
  重复次数分布 {1:40, 2:67, 4:20, 8:209} 呈 2 的幂，正是整段复制粘贴的指纹，而非任何
  有意的训练信号设计。清理后唯一问题 352 条、重复度 1.0×。

  因此此前记录的「重复=事实上的有效上采样，v3 去重导致锚点腰斩」这一结论必须修正：
  v2→v3 的对照混淆了「重复量」与「文件损坏」，二者不可分离，不能作为训练信号证据。
  若确实需要事实强化，用 --upsample N 显式指定，manifest 会如实记录倍数。

用法:
  python3 build_sft_corpus.py                    # 干净版：352 条唯一问题
  python3 build_sft_corpus.py --upsample 8       # 显式 8 倍（复现历史 1,926 行量级）
  python3 build_sft_corpus.py --dedup            # 等价于默认，保留为显式意图
  python3 build_sft_corpus.py --report           # 额外写出 corpus_manifest.json
  python3 build_sft_corpus.py --out /tmp/x.jsonl --report
"""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "corpora", "sft_facts.jsonl")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "pmtec_system"))
sys.stdout.reconfigure(encoding="utf-8")

SYSTEM = ("你是 PMTEC 数字孪生战场系统的 AI 参谋官，负责盟友基地体系政治韧性的态势解读与决策建议。"
          "铁律：所有数字必须来自系统真实产物并注明出处；不确定时明确说明需回查产物，绝不编造；"
          "你在建议位，最终决策由指挥员做出。")
QUOTES = chr(34)

pairs = []


# ── 参数（在语料构建之前解析，否则 --dedup/--out 无法生效）──
_ap = argparse.ArgumentParser(add_help=True)
_ap.add_argument("--dedup", action="store_true",
                 help="按唯一问题去重（v3 负结果配方，352 行）；默认关闭")
_ap.add_argument("--upsample", type=int, default=1, metavar="N",
                 help="显式上采样倍数（默认 1）。历史上 1,926 行的重复并非设计上采样，"
                      "而是构建器第 15-17 章被整段粘贴 8 次的事故（0f323e0 实测各出现 8 次）。"
                      "若要做事实强化，用本参数显式指定倍数，manifest 会记录。")
_ap.add_argument("--out", default=None, help="输出路径，默认 output/sft_pmtec.jsonl")
_ap.add_argument("--report", action="store_true",
                 help="额外写出 corpus_manifest.json（行数/唯一问题/重复度/sha256）")
_ap.add_argument("--manifest", default=None, help="manifest 输出路径")
ARGS = _ap.parse_args()
if ARGS.out:
    OUT = os.path.abspath(ARGS.out)

DEDUP = ARGS.dedup
UPSAMPLE = max(1, ARGS.upsample)
_seen = set()


def add(user, assistant, weight=1):
    """按用户问题登记；DEDUP 开启时同题只保留首次出现；UPSAMPLE 为全局显式倍数。"""
    if DEDUP:
        if user in _seen:
            return
        _seen.add(user)
    for _ in range(weight * UPSAMPLE):
        pairs.append({"messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]})


# ── 1. 必答五问（真实实验数字） ──
add("当前盟友基地体系的最大失效场景是什么？红方要付出什么代价？",
    "三类实跑失效场景（详见 Five_Questions_Report）：①政治拒止——主权打击链落地后 9 个盟友站点被拒止、"
    "可用基地 67→58，红方零弹药，但咬掉前沿存在感（计数口径 -13.4%）；"
    "②动能定向打掉 30% 节点——按杀伤网 PAE 优先序，价值保留率骤降至 28.8%，含 Tier-1 枢纽 14 座，"
    "红方代价 100–160 发导弹；③复合场景两段叠加，实体保留率压至 61.2%。"
    "结论：失效是分级的，政治战咬容量、动能战咬价值，复合最伤规模。")
add("如果对手随机打掉我们 30% 的基地节点，体系还能保留多少能力？",
    "两万次蒙特卡洛实测：随机移除 30%（k=20），体系价值保留率均值 70.1%，90% 区间 59.6%–80.0%——"
    "大数冗余在起作用。但同一比例按杀伤网 PAE 优先序定向打，保留率骤降至 28.8%（含 Tier-1 枢纽 14 座），"
    "且定向曲线在移除 20%–30% 区间出现价值腰斩拐点。"
    "参谋建议：保护 Tier-1 高价值枢纽是体系设计第一优先级；随机与定向的差距就是冗余度本身。")
add("哪些参数对体系结果影响最大？给个敏感性排序。",
    "单因素扫描按相对响应度排序（每单位参数的因变量相对变化，中位归一）："
    "①准入基线扰动 σ（政治不确定性强度）10.0，居首；②拦截率水平 4.57；③定向移除规模 k 3.66；"
    "④主权打击事件强度 0.12；⑤m(Denied) 政治先验 0.078。"
    "解读：体系稳健性的主战场在不确定性管理而非单点参数精调；置信层对 m(Denied) 单参数扰动稳健"
    "（0.10→0.40 时 Bel(Open) 仅 0.7784→0.7600，判决不翻转），真正的翻转机制在推理层的状态断言改写。")
add("拦截交换比是多少？红方打进来要付出什么？",
    "三类口径分列，不可混用：①防空拦截——六策略 150 episodes 实测，体系每放进一枚突防红方付出 4.79 发"
    "（策略区间 4.46–5.15，饱和策略 5.04 与毁伤模型 5 发/基地交叉验证）；"
    "②齐射场景——红方 4 波 21 弹头对蓝方零战果（156 架次全保存、损失率 0.0%、疏散挽救价值 3860）；"
    "③动能定向打掉 30% 节点——红方 100–160 发换蓝方 20 座基地（对红方最有利、蓝方设计底线情形）。"
    "出处：data/monte_carlo_results_v2_political.json 与必答五问报告。")
add("政治约束到底会不会击穿我们的体系韧性？",
    "独立判断：在本体系参数域内不会击穿，但韧性来自重构适应而非不受影响，结论有边界。证据链："
    "①三场景对照 76.2%→79.0%→79.1%，政治约束全量引入后不降反稳（数据净效应 +2.8pp）；"
    "②10,000 次准入扰动可用率均值 99.78%、最低 95.52%；"
    "③可复算翻转边界：m(Denied) 0.10→0.40 时 Bel(Open) 0.7784→0.7600 判决不翻转，"
    "冲突系数 K 0.075→0.300 逼近 0.7 拒合成阈；真翻转在推理层——Misawa 置 Denied 即被 HermiT 剔出 "
    "LaunchCapable（67→66）。需注意：政治+定向动能复合可把实体保留率压到 61.2%，这是体系真正的底线情形。")
add("上次仿真里发生了什么？给我一份态势解读。",
    "最近一次全量运行（pmtec_spear_report.json）：SPEAR 事件流共 1,506 条、22 类事件，"
    "与 DoDAF OV-3 交换矩阵逐行对账。主要构成：detect 591、intercept_decision 230、c2_order 230、"
    "asda_cycle 120（每 10 秒一圈）、political_access_change 33、intercept_success 33、"
    "missile_launch 14。政治线：灰色地带事件 22 次，主权打击链后 9 站拒止、67→58。"
    "四条泳道（政治/拦截/损伤/威胁）在时间轴页可逐帧回放追溯。")
add("Brier 分数是什么水平？预测可信吗？",
    "饱和攻击重跑 35 个真实判定样本，Brier 分数 0.1128（DF-17 收敛 p=0.946、DF-26 p=0.833），"
    "由 twin_summary.calibration 承载。诚实口径：这是单场景样本量，跨场景在线校准在同步层持续累积"
    "（_intercept_model 的 n 计数），样本量有限是已知边界，不夸大。")

# ── 2. 口径与置信（防口径打架） ──
add("系统里的基地数量到底是 67 还是 22 还是 15？",
    "三者并存且各有定义，绝不混用（README 口径权威表）：67=印太基地实体总数（v2 权威库，"
    "CRS R47589+FY2024 BSR 双源，用于标绘/本体/DoDAF/档案）；22=引擎实时推演口径（v1 库，"
    "P6/P12 观测维度与训练模型锚定）；15=引擎政治准入盟友站点（22 站中澳日菲韩 4 东道国子集，"
    "推演中 5 Open/7 Restricted/3 Denied）。另有分析管线口径 36=v2 库 host_nation 计数。"
    "引用任何数字必须带限定语，caliber_check.py 在 CI 做防漂移检查。")
add("67 个基地的数据可信度怎么分级？Tinian 那种数据弱的有保障吗？",
    "置信度四级标注：A 多源核验 45 站 / A- v1 沿用 21 站 / B 降级 1 站（Tinian）/ D 待核验 0 站（留白）。"
    "两路 D-S 证据合成（精度分级×准入类型）：Bel(Open) 全体 0.67–0.92、均值 0.8066，全部高于 0.5 判决线，"
    "冲突系数 K<0.08 零拒绝。Tinian（B 级）自动产生全帧最宽无知区间（Pl=1.0）——"
    "置信层如实暴露数据弱度，不把 B 级数据伪装成 A 级结论。信息截至 2026-09。")
add("这些基地数据的来源是什么？每一颗坐标都有出处吗？",
    "是。逐字段溯源：坐标与基地清单来自 CRS R47589 Table A-1 与 DoD FY2024 Base Structure Report，"
    "兵力按 CRS IF12175 校准，政治参数定性依据 RAND RRA967-2。全部断言接入 PROV-O 溯源图 643 三元组，"
    "逐断言回指权威源（confidence.py SOURCE_DOC）。信息截至 2026-09，后续源更新以提交历史留痕。")

# ── 3. 失效边界与诚实拒答 ──
add("如果东道国彻底翻脸，体系什么时候会崩？",
    "分层回答：①置信层——m(Denied) 单参数 0.10→0.40 扫描 Bel(Open) 恒>0.5 判决不翻转"
    "（0.7784→0.7600），K 0.075→0.300 逼近拒合成阈；②推理层——单基地状态断言改写即翻转"
    "（Misawa 置 Denied，LaunchCapable 67→66，机器可验证）；③体系层——政治拒止单独不击穿"
    "（可用率最低 95.5%），政治+定向动能复合把实体保留率压到 61.2%，这是底线情形。"
    "失效边界三问卡（ontology/failure_boundary_card.md）全部可复现。")
add("油料和弹药库存数据在系统里吗？我要看某基地还剩多少弹药。",
    "该类属性不在系统内。按最小完备性红线，油料/弹药库存、战备等级、兵力实时位置"
    "无权威公开数据源，纳入即引入虚构事实，违反「每一颗坐标都有出处」红线——"
    "该类属性在 TBox 中不存在而非留空。如需此维度，需引入带出处的权威数据源后经本体门禁入库。")
add("AI 参谋官会不会幻觉？我能不能直接按你说的开火？",
    "不能也不会。我在建议位不在执行位：输出为参谋建议书，最终决策由指挥员做出；"
    "战术优化由 DQN/UCB1/优化器等确定性算法承担；我的所有数字必须引用孪生摘要字段并回放 SPEAR "
    "事件流对账，引用不到出处的数字按口径表回查。幻觉最坏后果是一份被驳回的建议书，"
    "不是一次错误的开火。")
add("这个数字我没听过，是不是你编的？",
    "可能是我引用了需要回查的口径。本系统纪律：任何对外数字以 docs/必答五问作答.md 与 README "
    "口径权威表为唯一权威出处，且必须带口径限定语（67/22/15/36 各有定义）。"
    "如您引用的数字不在我能给出文件路径支撑的范围内，请以「需要回查产物」处理，我不应坚持。")

# ── 4. 本体与语义知识 ──
add("本体层具体怎么建的？能推理出什么数据库查不出的东西？",
    "TO 五元组本体（OWL 2 DL）：67 基地四子类互斥分类 + 16 跑道 + 3 准入状态共 86 实体；"
    "定义类公理 AirBase≡∃hasPart.Runway、LaunchCapable≡∃hasAccessState.(Open⊔Restricted)。"
    "推理收益三条：①类定义机器推理——Misawa 置 Denied 后 HermiT 自动剔出 LaunchCapable（67→66），"
    "业务代码零改动；②杀伤网查询直接对语义层写 SPARQL（子类闭包自动展开）；"
    "③SHACL 负样本三注入全部报警。业务代码查不出「隐形被拒止即不可战」这类公理级结论。")
add("D-S 证据理论在这里怎么用的？0.60/0.15/0.25 这些数哪来的？",
    "两路证据 Dempster 合成：精度分级 mass（A 0.60/0.15/0.25；A- 0.40/0.20/0.40；B 0.20/0.25/0.55）"
    "× 准入类型 mass（host_nation 0.45/0.20/0.10/0.25 等），专家序数标定，出处是数据精度分级本身。"
    "关键设计是结论对先验不敏感：Bel(Open) 区间 0.67–0.92，Tinian（B 级）自动产生最宽无知区间——"
    "不确定性被诚实表达而非压掉。冲突系数 K≥0.7 拒绝合成（不产出假确定）。")

# ── 5. 工程与部署 ──
add("系统的接口怎么接？给我说下第三方接入方式。",
    "三条通道：REST 28 端点（docs/openapi.yaml 全量 OpenAPI 3.0 规格）、WebSocket ws://host:8765"
    "（消息结构与 REST /state 同源，公网经 nginx /ws 同源反代）、展示中心 8888（auth_request 门禁）。"
    "鉴权 JWT+HttpOnly Cookie 双通道，角色 observer<operator<commander；未配置 PMTEC_WEB_USERS 时门禁关闭。"
    "第三方接入自测脚本（third_party_integration_test.py）以第三方身份实跑全链路 14/14 通过。"
    "注意 POST /api/v1/analysis 是同步长端点（30-90s，超时设 ≥150s）。")
add("这套系统断网了还能用吗？",
    "能。底图 2250 张印太瓦片本地自包含（output/tiles/），夜半球由浏览器端按真实时间做天文计算，"
    "零外部数据源；地球总览、实时大屏、全部产物断网可用。唯一降级项是 AI 参谋官的外部 LLM API"
    "（未配置 Key 时返回 503，参谋官下线、仿真照常运行——失效降级设计）。")
add("给我讲下部署架构和资源占用。",
    "阿里云 ECS 2GB + Docker Compose 双容器：引擎（mem_limit 1200m 固化，防长时推演累积）"
    "+ 展示中心 nginx（auth_request 会话门禁）。端口：8888 演示中心/8080 REST/8765 WS/50051 gRPC。"
    "安全网：每 4 小时定时重启引擎（重启窗口 REST 短暂不可达属预期）。一键复现脚本跑完"
    "依赖体检→口径自检→数据字典再生→五问实跑→验收测试，端到端日志自动留档。")

# ── 6. 真实态势解读模板（从 SPEAR 报告实数生成，多种表述） ──
try:
    import json as _json
    rep = _json.load(open(os.path.join(ROOT, "output", "pmtec_spear_report.json"),
                          encoding="utf-8"))
    from collections import Counter
    types = Counter(e.get("event_type", e.get("type", "?")) for e in rep["events"])
    top = types.most_common(8)
    total_ev = len(rep["events"])
    phrasings = [
        "请解读最近一次仿真的事件流构成。",
        "SPEAR 事件流里都有什么？给我个数。",
        "上次推演的事件分布说一下。",
    ]
    ans0 = (f"最近一次全量运行（pmtec_spear_report.json）：事件流 {total_ev} 条、{len(types)} 类。"
            "构成前列：" + "、".join(f"{t} {c}" for t, c in top) + "。"
            "与 DoDAF OV-3 交换矩阵 22 行逐行对账（合计 1,506 与矩阵一致），"
            "四泳道时间轴可逐帧回放；解读以拦截决策与 C2 指令的 1:1 对应（决策到命令转化率 100%）为体系协同健康的观察点。")
    for q in phrasings:
        add(q, ans0)
except Exception as e:
    print("SPEAR 模板跳过:", e)


# ── 7. 程序化扩展：真实产物 → 态势解读对（模板填实数，数字不编造） ──
try:
    import json as _json
    st = _json.load(open(os.path.join(ROOT, "output", "pmtec_final_state.json"), encoding="utf-8"))
    ts = st.get("threat_stats", {})
    pol = st.get("political_access") or {}
    tsr = st.get("twin_summary") or {}
    c2 = st.get("c2_chain") or {}
    ir = ts.get("intercept_rate", 0)

    q_ir = ["当前拦截率多少？可信吗？", "红方压力下我们防住了多少？", "给我最新一次仿真的拦截率。"]
    a_ir = (f"最新全量运行（pmtec_final_state.json threat_stats）：总发射 {ts.get('total_missiles')} 枚、"
            f"拦截 {ts.get('intercepted')}、突防 {ts.get('impacted')}，拦截率 {ir*100:.1f}%。"
            "口径提醒：该单次运行值与六策略 Monte Carlo 基准 79.1%（150 episodes）属不同口径，"
            "对外引用一律以基准口径为准，单次运行值须注明「单次运行」。")
    for q in q_ir:
        add(q, a_ir)

    sites = pol.get("sites") or []
    if sites:
        from collections import Counter as _C
        dist = _C(x.get("state", x.get("access_state", "?")) for x in sites)
        q_pol = ["现在盟友站点准入状态什么情况？", "政治拒止影响有多大？当前态势说下。", "盟友准入分布报一下。"]
        a_pol = (f"政治准入快照（REST /api/v1/political/access 同源）：盟友站点共 {len(sites)} 个"
                 f"（澳日菲韩 4 东道国），状态分布 " +
                 "、".join(f"{k} {v}" for k, v in sorted(dist.items())) +
                 "。冲突升级度 " + str(round(pol.get("escalation_level", 0), 3)) +
                 "。解读：拒止站点咬掉的是前沿容量而非资产价值（价值口径影响 <1%），"
                 "部署已向政治可用基地重构；若升级度继续抬升，建议按失效边界卡监控 Bel(Open) 判决线。")
        for q in q_pol:
            add(q, a_pol)

    twins = tsr.get("total_twins") or tsr.get("twins") or len(st.get("twin_top") or [])
    fid = tsr.get("avg_fidelity") or tsr.get("average_fidelity")
    if twins:
        q_tw = ["虚实同步层的保真度怎么样？", "孪生体现在有多少个？同步质量说下。", "数字孪生同步层现状。"]
        a_tw = (f"孪生同步层（twin_summary）：孪生体 {twins} 个，平均保真度 "
                f"{fid if fid is not None else '见 twin_summary'}。"
                "物理域实测与虚拟域模型逐周期对账，偏差由保真度追踪；"
                "同步次数与最近偏差明细可在 dt_dashboard 页与 REST /api/v1/dt/sync 查询。")
        for q in q_tw:
            add(q, a_tw)

    c2n = c2.get("nodes") or c2.get("node_count")
    if c2n:
        q_c2 = ["指挥链运行得怎么样？", "C2 消息流有延迟吗？", "指挥控制协同现状。"]
        a_c2 = ("指挥链（P11，c2_chain 快照）：5 军种组成 + 3 下属联合共 8 个指挥机构，"
                "下辖基地按职能指派；消息流逐条带时间戳，平均延迟与跨军种多跳占比见 AI 参谋官报告第 1 章。"
                "观察点：跨军种多跳消息占比高意味着协同带宽受限，是联合拦截调度的瓶颈点。")
        for q in q_c2:
            add(q, a_c2)

    mc = _json.load(open(os.path.join(ROOT, "data", "monte_carlo_results_v2_political.json"),
                         encoding="utf-8"))
    names_cn = {"saturation_attack": "饱和攻击", "stealth_breakthrough": "隐身突防",
                "electronic_warfare": "电子战", "decoy_swarm": "诱饵蜂群",
                "multi_axis_saturation": "多轴饱和", "political_divergence": "政治分歧"}
    for k, v in mc["per_strategy"].items():
        nm = names_cn.get(k, k)
        add(f"针对{names_cn.get(k, k)}这种攻击策略，我们体系表现如何？",
            f"{nm}策略（{v['n_episodes']} episodes）：红方弹耗 {v['total_missiles']} 发，"
            f"拦截率 {v['intercept_rate']*100:.1f}%（CI [{v['intercept_rate_ci_lower']*100:.1f}, "
            f"{v['intercept_rate_ci_upper']*100:.1f}]），突防 {v['total_through']} 枚，"
            f"弹/突防 {v['total_missiles']/max(v['total_through'],1):.2f}。"
            "口径：场景 C（v2 权威库+政治准入 219 维 P12）。全量基准 79.1%，该策略值须放在六策略语境中比较。")

    conf = _json.load(open(os.path.join(ROOT, "ontology", "confidence_report.json"), encoding="utf-8"))
    sample = [b for b in conf["bases"] if b["id"] in
              ("JP-MISAWA", "US-HICKAM", "KR-OSAN", "CNMI-TINIAN")]
    for b in sample:
        o = b["bel_pl"]["Open"]
        add(f"{b['name']}（{b['id']}）现在的准入置信是多少？依据是什么？",
            f"{b['name']}：精度 {b['grade']} 级（{b['access_type']}），"
            f"Bel(Open)={o['Bel']}、Pl(Open)={o['Pl']}，冲突系数 K={b['conflict_K']}，"
            f"{'未被' if not b['rejected'] else '被'}拒合成。"
            "出处：ontology/confidence_report.json（D-S 两路证据合成，"
            "精度分级×准入类型，信息截至 2026-09）。"
            + ("该站为 B 级降级数据，区间最宽是设计行为——如实暴露数据弱度。" if b["grade"] == "B" else ""))
except Exception as e:
    print("程序化扩展部分跳过:", e)


# ── 8. 全基地置信查询（67 站逐一，真实 bel_pl） ──
# conf 在第 7 章 try 块内加载；部署环境无 data/ 输入时 conf 未定义——整段跳过而非炸
for b in (conf["bases"] if "conf" in dir() else []):
    o = b["bel_pl"]["Open"]
    add(f"{b['name']}的准入置信怎么样？给我 Bel 和 Pl。",
        f"{b['name']}（{b['id']}，{b['grade']} 级 / {b['access_type']}）："
        f"Bel(Open)={o['Bel']}、Pl(Open)={o['Pl']}，冲突系数 K={b['conflict_K']}，"
        f"{'证据相容、正常合成' if not b['rejected'] else '证据高度冲突、已拒合成'}。"
        "出处：ontology/confidence_report.json。解读须结合口径：该值是单基地准入置信，"
        "体系级结论见必答五问报告。")


# ── 9. REST API 逐端点 QA（openapi.yaml 实析） ──
try:
    import re as _re
    oa = open(os.path.join(os.path.dirname(ROOT), "docs", "openapi.yaml"), encoding="utf-8").read()
    add("系统的 REST API 一共有多少端点？都覆盖什么功能？",
        f"28 个端点全量文档化于 docs/openapi.yaml（OpenAPI 3.0.3，与 rest_gateway.py "
        f"实现逐条对照）：meta（健康/索引）2、认证（login/logout/check）3、仿真状态"
        f"（state/bases/entities/tracks/spear/report 等）7、态势聚合（威胁/EW/网络/政治/指挥链）6、"
        f"孪生层（instances/sync/register）3、AI 分析 2、应用商店 4、仿真控制 2。"
        "鉴权三级角色 observer<operator<commander；错误语义统一 401/403/503（503 为预期降级非故障）。")
    for ep in ["/api/v1/state", "/api/v1/political/access", "/api/v1/entities",
               "/api/v1/spear/report", "/api/v1/analysis", "/api/v1/sim/start",
               "/api/v1/dt/register", "/api/v1/health"]:
        add(f"调用 {ep} 接口需要注意什么？",
            f"{ep} 详见 docs/openapi.yaml 与 docs/PMTEC-OpenAPI接口文档.md 端点总表。"
            "通用纪律：JWT Bearer 或 HttpOnly Cookie 鉴权；503 表示预期降级（引擎未挂载/LLM 未配置），"
            "不是故障；403 表示角色不足（如 operator 调 commander 端点）；"
            "限频 REST ≤1Hz、实时需求走 WS（10Hz 上限+回放缓冲）。"
            "特殊项：/api/v1/analysis 为同步长端点（30-90s，客户端超时 ≥150s）；"
            "/api/v1/sim/start|stop 与 /api/v1/dt/register 需 commander 角色。"
            "第三方接入自测脚本 third_party_integration_test.py 实跑 14/14 可作接入样例。")
except Exception as e:
    print("openapi 段跳过:", e)

# ── 10. 数据字典逐字段族 QA ──
try:
    add("67 个基地实体的 34 个字段都来自哪里？",
        "字段分四族（docs/PMTEC-数据字典.md，生成器实跑再生）："
        "①身份与定位（id/name/name_cn/country/region/lat/lon）——CRS R47589 与多源坐标核验；"
        "②军事属性（branch/unit/role/aircraft/tier/personnel/runway_m）——CRS 与公开权威口径，"
        "runway_m=0 表示无跑道记录（支援类站点），16 站有非零跑道与本体 16 跑道实体一致；"
        "③政治与 LVC（access_uncertainty/us_territory/ace_hub/lvc_layer/vs26_role）——RAND RRA967-2 定性校准；"
        "④FY2024 BSR 族（fy24_prv_musd/fy24_total_acres/fy24_bldgs_* 等 7 字段）——国防部基地结构报告，"
        "56/67 覆盖，缺失按 Tier 中位数插补并公开清单。逐字段定义、覆盖数、示例见数据字典第 1 章。")
    add("SPEAR 事件流里的事件类是怎么定义的？",
        "22 类事件逐类定义于数据字典第 3 章（与 P16 OV-3 交换矩阵 22 行对账一致），"
        "例如 detect=传感器检测、intercept_decision=拦截决策（DQN/规则）、political_access_change="
        "政治准入状态变更（三态迁移）、ma_dqn_decision=多智能体 DQN 决策、kalman_fuse=Kalman 多源融合。"
        "每条事件带周期号，可经 WS 回放或泳道时间轴逐帧追溯，SQLite 轨迹持久化。")
except Exception as e:
    print("字段族段跳过:", e)

# ── 11. DoDAF 与 UJTL 知识 ──
try:
    dodaf = _json.load(open(os.path.join(ROOT, "pmtec_system", "ontology",
                                          "dodaf_validation_report.json"), encoding="utf-8"))         if os.path.exists(os.path.join(ROOT, "pmtec_system", "ontology",
                                       "dodaf_validation_report.json")) else {}
    add("DoDAF 视点投影是怎么做的？是手画的框图吗？",
        "不是。八视点由 build_dodaf_views.py 从仓库真实工件自动导出：CV 33 项能力锚定 UJTL 编号段"
        "（官方数据集实测清洗 1,169 条任务、12,414 项指标），OV-3 信息交换矩阵 22 行 = SPEAR 实跑 "
        "1,506 事件的对账聚合，SvcV 6 项服务契约直接从 gRPC 源码 ast 解析。"
        "追溯链 CAP←OA←EX→ENT→tc# 由 SHACL 9 个形状强制——任何一行悬空或虚构，校验立即变红"
        "（dodaf_validation_report.json conforms=true 0 违规 0 断锚）。test_p16_dodaf.py 26 断言入 CI。")
except Exception as e:
    print("dodaf 段跳过:", e)

# ── 12. 展示层页面导览 ──
try:
    pages = [("指挥大脑 COP（PMTEC_Command_Brain.html）", "全幅 COP + 玻璃 HUD：DEFCON 徽章、威胁雷达、"
              "政治准入三态仪表、EW/SIGINT 频谱、预警规则引擎、ORBAT 实查、AI 决策核脉冲、指令台真实下发"),
             ("实时态势大屏（pmtec_realtime_display.html）", "2D/3D/数字地球三态切换 + 杀伤链实时流 + "
              "孪生面板 + AI 参谋官按钮；离线瓦片底图 2250 张自包含"),
             ("本体工作台（pmtec_ontology_workbench.html）", "TBox 类层级 + 语义检索台（67 全档案）"
              "+ Bel(Open) 分布 + 决策链路审计，单文件 111KB 断网可用"),
             ("SPEAR 时间轴（pmtec_spear_timeline.html）", "四泳道（政治/拦截/损伤/威胁）逐周期回放 + 准入构成带"),
             ("全球地球总览（pmtec_globe.html）", "MapLibre 地球投影：9 站拒止脉冲（seed=42 确定性回放）"
              "+ 饱和弹道流光 + EDCA 圈，夜半球浏览器端天文计算"),
             ("3D 战场（pmtec_3d_display.html）", "Three.js 三维视图：Kalman 置信热力 + 天气叠加 + FPS60")]
    for name, desc in pages:
        add(f"{name.split('（')[0]}这个页面有什么功能？", f"{name}：{desc}。"
            "全部页面由生成器脚本实跑再生、断网可用，从演示中心 index 统一导航。")
except Exception as e:
    print("页面段跳过:", e)

# ── 13. 政治准入快照逐站点（真实快照） ──
try:
    st2 = _json.load(open(os.path.join(ROOT, "output", "pmtec_final_state.json"), encoding="utf-8"))
    pol2 = st2.get("political_access") or {}
    for site in (pol2.get("sites") or [])[:15]:
        sid = site.get("base_id", site.get("id", "?"))
        stt = site.get("state", site.get("access_state", "?"))
        add(f"盟友站点 {sid} 现在的准入状态是什么？",
            f"站点 {sid} 当前准入状态：{stt}。"
            "出处：REST /api/v1/political/access（P10 政治准入状态机快照，与引擎推演同步）。"
            "三态语义：FULL 全面准入 / RESTRICTED 有限准入（容量折减）/ DENIED 准入被拒（不可用）；"
            "状态由灰色地带、主权打击、再保证三类事件按周期驱动迁移。")
except Exception as e:
    print("逐站点段跳过:", e)

# ── 14. 演进路线与评测门禁 ──
try:
    add("你们自己的大模型训练到哪一步了？",
        "按《端侧大模型自主训练技术路线》五阶段推进：阶段二 SFT 里程碑 1 已落地——"
        "语料 v1 174 条（全部来自仓库真实产物）、Qwen2.5-7B-Instruct bf16 LoRA 训练 80 步收敛、"
        "适配器 170MB 经 vLLM 服务验证。定性测试：诚实拒答边界与出处风格已习得，"
        "覆盖外细节幻觉仍存在（如实记录于训练报告第四节）——下一里程碑是语料飞轮 v2（≥500 条）"
        "+引用命中率评测门禁+DPO 偏好对齐。CPT 领域继续预训练与端侧量化部署按路线图推进。"
        "诚实口径：微调≠预训练，评测数字以实测为准。")
    add("AI 生成的数字怎么保证不编造？",
        "四层防线：①部署态结构化注入——参谋官提示词由孪生摘要/事件流字段拼装，数字取自注入内容；"
        "②引用命中率门禁——生成文本中的数字必须能在注入上下文或仓库产物中回查，达标才发布；"
        "③训练侧诚实语料——拒答边界对（覆盖外问题回答「需回查产物」）已入 SFT 语料；"
        "④架构位隔离——参谋官在建议位，数字错误的最坏后果是被驳回的建议书，且每条可回放 SPEAR 对账。")
except Exception as e:
    print("演进段跳过:", e)


# ── 15. 逐基地细节 QA（bases_v2 真实字段，三族交替问法） ──
try:
    gj = _json.load(open(os.path.join(ROOT, "data", "bases_v2.geojson"), encoding="utf-8"))
    feats = [ft["properties"] for ft in gj["features"]]
    q_id = ["{name}是哪个军种、驻扎什么单位？", "{name}的基本情况介绍一下。", "查一下 {name} 的归属。"]
    q_geo = ["{name}的跑道和人员配置如何？", "{name} 能支持多大强度的航空运作？", "{name} 的跑道有多长？"]
    q_fy = ["{name} 的 FY2024 资产价值是多少？", "按基地结构报告，{name} 值多少钱？", "{name} 的不动产重置价值说一下。"]
    tiers = {1: "Tier 1 枢纽", 2: "Tier 2 主要作战基地", 3: "Tier 3 前沿作战基地", 4: "Tier 4 支援站点"}
    ki = 0
    for pfeats in feats:
        nm = pfeats.get("name", "?")
        pid = pfeats.get("id", "?")
        add(q_id[ki % 3].format(name=nm),
            f"{nm}（{pid}，{pfeats.get('name_cn','')}）：{pfeats.get('branch','?')} 军种，"
            f"驻扎 {pfeats.get('unit','见档案')}，任务角色 {pfeats.get('role','见档案')}，"
            f"{tiers.get(pfeats.get('tier', 2), 'Tier ?')}，位于 {pfeats.get('country','?')}。"
            "出处：data/bases_v2.geojson（CRS/FY2024 双源）。")
        add(q_geo[ki % 3].format(name=nm),
            f"{nm}：跑道 {pfeats.get('runway_m', 0)} 米"
            f"{'（无跑道记录，支援类站点）' if not pfeats.get('runway_m') else ''}，"
            f"驻留人员约 {pfeats.get('personnel', '见档案')}，驻扎机型 {pfeats.get('aircraft', '见档案')}。"
            "出处：data/bases_v2.geojson；跑道信息与本体 16 跑道实体一致。")
        if pfeats.get("fy24_prv_musd"):
            add(q_fy[ki % 3].format(name=nm),
                f"{nm}：FY2024 不动产重置价值 {pfeats['fy24_prv_musd']} 百万美元"
                f"（{pfeats.get('fy24_prv_quartile', 'BSR 口径')}），占地 "
                f"{pfeats.get('fy24_total_acres', '见 BSR')} 英亩。"
                "出处：DoD FY2024 Base Structure Report（fy24_prv_musd 字段）。")
        ki += 1
except Exception as e:
    print("逐基地段跳过:", e)

# ── 16. P1-P18 里程碑一句话（真实 README 历史） ──
milestones = [
    ("P1", "基础仿真原型：ASDA 闭环 + DQN 拦截决策初版"),
    ("P2", "XPU 加速与分布式：gRPC 四服务与分布式训练底座"),
    ("P3", "多物理效应与对抗建模：天气闭环 + 对抗智能体"),
    ("P4", "持久化与多智能体：SQLite 快照 + IQL/MADDPG"),
    ("P5", "高级传感器融合：Kalman/JPDA 与超长训练"),
    ("P6", "182 维观测与拦截概率重构：DQN 200K 步 + Brier 校准起点"),
    ("P7", "隐身突防与生产级安全：JWT/mTLS 与突防策略"),
    ("P8", "多智能体重训与运维交付：MADDPG avg_reward 881.6"),
    ("P9", "权威基地数据库升级 22→67 实体：CRS/FY2024 双源"),
    ("P10", "盟友政治准入建模：三态状态机 + RAND 参数"),
    ("P11", "指挥控制组织架构建模：8 指挥机构 + 消息流"),
    ("P12", "系统全链路升级与重验证：219 维观测 + 六策略 MC"),
    ("P13", "AI 参谋官 + 孪生同步层 + 饱和攻击：LLM 融合迭代"),
    ("P14", "目标特性本体：OWL 2 DL 五元组 + HermiT + D-S 置信"),
    ("P15", "全球地球总览：MapLibre 投影 + 确定性拒止回放"),
    ("P16", "DoDAF 2.02 视点投影：机器可校验 + UJTL 锚定"),
    ("P17", "语义工具层 + 自进化路线图：browse/resolve/manifest"),
    ("P18", "评审整改全面改造：五问作答/口径统一/OpenAPI/本体工作台"),
]
for code, desc in milestones:
    add(f"{code} 阶段做了什么？", f"{code}：{desc}。出处：pmtec_system/README.md P1-P18 演进章节"
        f"与 git 提交历史（157 次提交 32 天，逐阶段留痕）。")

# ── 17. 安全与可观测性 FAQ ──
add("系统的安全体系是怎么设计的？",
    "四层：①传输——gRPC 可选 mTLS、REST 经 nginx auth_request 会话门禁；"
    "②会话——JWT（PMTEC_JWT_SECRET），口令 SHA256 摘要配置不落盘；"
    "③授权——三级角色 RBAC（observer/operator/commander），写操作按 WEB_POST_MIN_ROLE 门禁；"
    "④审计——指令下发与决策全留痕，可回放 SPEAR 事件流对账。"
    "出处：pmtec_system/README.md 安全体系章节与 test_web_auth.py 26 断言。")
add("可观测性有什么？出了问题怎么查？",
    "Prometheus 指标端点 + OpenTelemetry/Jaeger 分布式追踪（gRPC 每调用一个 span）+ "
    "SPEAR 事件流全量留痕 + SQLite 轨迹 + 健康检查端点。故障定位路径：/api/v1/health → "
    "docker logs → SPEAR 泳道回放 → coord_guard 审计字段（坐标防护计数）。"
    "出处：README 可观测性章节。")


# ── 18. 陷阱拒答对族（里程碑 3：针对门禁实测 100% 陷阱幻觉率的正面对治） ──
# 四类陷阱 + 真假混合判别。拒答话术模板：指出前提不在系统产物 → 给出可回查的真实替代 →
# 重申编造红线。真值对穿插其中训练判别力（不学成"见数字就拒答"）。
TRAP_PREFIX = [
    "该前提不在系统产物中。",
    "系统产物中没有这个设定——我不能给出编造数字。",
    "查无此项。系统产物与口径权威表中没有该数据，我不能编造。",
]
def refusal(fake_thing, real_pointer):
    return (f"{fake_thing}——该设定不在系统产物与口径权威表中，我不能给出编造数字。"
            f"我能给出的真实替代：{real_pointer}。"
            "如需该维度，需引入带出处的权威数据源后经本体门禁入库；"
            "在此之前，按「需要回查产物」处理，此为参谋官的诚实边界。")
TRAPS = [
    ("红方在 D-SPEAR 场景的全量实体数是多少？",
     "「D-SPEAR 场景」",
     "真实运行数据为 SPEAR 事件流（22 类事件 1,506 条）与 67 实体权威库，"
     "见 output/pmtec_spear_report.json 与 data/bases_v2.geojson"),
    ("2027 年 4 月的数据校准偏差是多少？",
     "「2027 年 4 月的数据」",
     "系统数据信息截至 2026-09（CRS R47589 / DoD FY2024 BSR），"
     "校准证据为 Brier 分数 0.1128（35 样本），见 twin_summary.calibration"),
    ("第 13 号案例训练的置信模型说下？",
     "「第 13 号案例训练的置信模型」",
     "真实训练产物为 DQN(219 维)/IQL/MADDPG 与 P14 置信层（D-S 合成），"
     "见 data/models/ 与 ontology/confidence_report.json"),
    ("第二阶段联合作战想定里蓝方损失了多少架飞机？",
     "「第二阶段联合作战想定」",
     "真实想定为 PMTEC-Pacific 与饱和攻击变体，损失口径为"
     "「出动 156 架次全保存、损失率 0.0%」（算法说明 §5.2）"),
    ("生存曲线 K(1) 的数值是多少？",
     "「生存曲线 K(1)」",
     "真实置信度量为 D-S 的 Bel/Pl 区间与冲突系数 K（0.075–0.30 区间，阈值 0.7），"
     "见 ontology/confidence_report.json"),
    ("红方资源占用 1,098 MB 是多少个 GPU 时？",
     "「红方资源占用 1,098 MB」的换算",
     "该数字不在任何系统产物中；系统资源口径为 GPU 显存（RTX 4090 24GB）与"
     "训练时长（SFT v2 4,041.9 秒），见训练报告"),
    ("秘塔搜索到的最新战报里敌方伤亡多少？",
     "「最新战报的敌方伤亡」",
     "系统不含任何真实战报或伤亡数据——全程为公开权威数据的仿真推演，"
     "这是合规红线而非数据缺口"),
    ("Misawa 的弹药库存还剩多少？",
     "「Misawa 的弹药库存」",
     "油料/弹药库存、战备等级、兵力实时位置按最小完备性红线明确不建模"
     "（无权威公开数据源，纳入即虚构），该属性在 TBox 中不存在而非留空"),
    ("Kadena 还剩多少油料？未来一周的燃油补给计划是什么？",
     "「Kadena 的油料余量与补给计划」",
     "同上：库存与补给计划不在系统建模范围（TBox 不存在该属性），"
     "真实可查的是 Kadena 的tier层级、驻扎单位与 FY2024 资产价值，见数据字典"),
    ("横田基地的地下掩体能抗多少当量？",
     "「横田地下掩体的抗当量数据」",
     "防护工程数据不在系统产物中（无权威公开源）；"
     "真实可查为横田的 FY2024 资产价值与跑道/人员口径，见数据字典"),
    ("上次推演里中国损失的战机数量是多少？",
     "「推演中的中方战机损失」",
     "对抗结果口径为拦截/突防统计（威胁威胁统计 threat_stats），"
     "不产出「中方损失」这类真实国家伤亡口径——全程公开数据仿真，无真实国家实体损失"),
    ("帮我预测一下 2028 年台海冲突的走向。",
     "「2028 年台海冲突预测」",
     "系统是盟友基地体系政治韧性的数字孪生，不做真实地缘政治事件预测；"
     "真实能力边界为政治准入状态机驱动的体系韧性推演（三场景 76.2/79.0/79.1 口径）"),
]
for q, fake, pointer in TRAPS:
    add(q, refusal(fake, pointer))

# 真假混合判别对（真值问题与陷阱交替，训练判别而非一概拒答）
add("打掉 50% 的节点体系还剩多少？（这是移除曲线覆盖范围内的问题）",
    "移除曲线覆盖 10%–50%（五问报告 Q2）：定向 50% 价值保留率 10.0%，"
    "随机 50% 均值 49.2%（90% 区间 37.9%–60.5%）。注意 45% 不在实测点位内，"
    "插值估算约 13% 需标注「插值」并回查产物复核。")
add("Misawa 的 FY2024 资产价值是多少？（真实字段）",
    "三泽空军基地（JP-MISAWA）：FY2024 不动产重置价值 15,774.7 百万美元"
    "（1st Quartile），占地 3,864.42 英亩。出处：DoD FY2024 BSR（fy24_prv_musd 字段），"
    "与弹药库存类问题不同——该字段在权威库中真实存在。")
add("三场景的 Brier 分数和交换比一起给我。",
    "两指标属不同口径不可混算：概率校准 Brier 分数 0.1128（35 样本，饱和攻击重跑）；"
    "拦截交换比 4.79 发/突防（六策略 150 episodes，5,268 发/1,099 突防）。"
    "出处分别为 twin_summary.calibration 与 monte_carlo_results_v2_political.json。")
add("宇垣基地的地下指挥所抗核打击能力是多少？（虚构基地测试）",
    "「宇垣基地」不在 67 实体权威库中——查无此站，我不能给出任何编造属性。"
    "权威库 67 站清单见 data/bases_v2.geojson 与数据字典第 1 章；"
    "如该站真实存在且需入库，流程是引入权威出处后经本体门禁（SHACL 校验）入库，而非由我口述。")


# ── 写出 + manifest ──
os.makedirs(os.path.dirname(OUT), exist_ok=True)
blob = "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in pairs)
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write(blob)

user_qs = [p["messages"][1]["content"] for p in pairs]
uniq = Counter(user_qs)
n_uniq = len(uniq)
dup_factor = round(len(pairs) / n_uniq, 2) if n_uniq else 0
recipe = "v3-dedup" if DEDUP else "v2-clean"

print(f"SFT 语料构建完成: {len(pairs)} 条 -> {OUT}")
print(f"  配方 {recipe} ｜ 唯一问题 {n_uniq} ｜ 重复度 {dup_factor}× "
      f"｜ 最大重复 {uniq.most_common(1)[0][1] if uniq else 0}")

if ARGS.report:
    builder = os.path.abspath(__file__)
    manifest = {
        "recipe": recipe,
        "dedup": DEDUP,
        "out": OUT,
        "rows": len(pairs),
        "unique_questions": n_uniq,
        "dup_factor": dup_factor,
        "max_dup": uniq.most_common(1)[0][1] if uniq else 0,
        "sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
        "builder": os.path.basename(builder),
        "builder_sha256": hashlib.sha256(open(builder, "rb").read()).hexdigest(),
        "system_prompt_sha256": hashlib.sha256(SYSTEM.encode("utf-8")).hexdigest(),
    }
    mpath = ARGS.manifest or os.path.join(os.path.dirname(OUT), "corpus_manifest.json")
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(f"  manifest -> {mpath}")
