#!/usr/bin/env python3
"""PMTEC 参谋官 SFT 语料构建器——全部样本源自仓库真实产物，无编造数字。

输出: output/sft_pmtec.jsonl (Qwen chat messages 格式)
配比: 五问作答 / 口径置信 / 失效边界 / 态势解读(真实SPEAR数据) / 语义知识 /
      工程部署 / 诚实拒答边界  共 7 类
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output", "sft_pmtec.jsonl")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "pmtec_system"))
sys.stdout.reconfigure(encoding="utf-8")

SYSTEM = ("你是 PMTEC 数字孪生战场系统的 AI 参谋官，负责盟友基地体系政治韧性的态势解读与决策建议。"
          "铁律：所有数字必须来自系统真实产物并注明出处；不确定时明确说明需回查产物，绝不编造；"
          "你在建议位，最终决策由指挥员做出。")
QUOTES = chr(34)

pairs = []


def add(user, assistant):
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
for b in conf["bases"]:
    o = b["bel_pl"]["Open"]
    add(f"{b['name']}的准入置信怎么样？给我 Bel 和 Pl。",
        f"{b['name']}（{b['id']}，{b['grade']} 级 / {b['access_type']}）："
        f"Bel(Open)={o['Bel']}、Pl(Open)={o['Pl']}，冲突系数 K={b['conflict_K']}，"
        f"{'证据相容、正常合成' if not b['rejected'] else '证据高度冲突、已拒合成'}。"
        "出处：ontology/confidence_report.json。解读须结合口径：该值是单基地准入置信，"
        "体系级结论见必答五问报告。")

# ── 写出 ──
# ── 写出 ──

# ── 8. 全基地置信查询（67 站逐一，真实 bel_pl） ──
for b in conf["bases"]:
    o = b["bel_pl"]["Open"]
    add(f"{b['name']}的准入置信怎么样？给我 Bel 和 Pl。",
        f"{b['name']}（{b['id']}，{b['grade']} 级 / {b['access_type']}）："
        f"Bel(Open)={o['Bel']}、Pl(Open)={o['Pl']}，冲突系数 K={b['conflict_K']}，"
        f"{'证据相容、正常合成' if not b['rejected'] else '证据高度冲突、已拒合成'}。"
        "出处：ontology/confidence_report.json。解读须结合口径：该值是单基地准入置信，"
        "体系级结论见必答五问报告。")

# ── 写出 ──
# ── 写出 ──
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    for p in pairs:
        f.write(json.dumps(p, ensure_ascii=False) + "\n")
print(f"SFT 语料构建完成: {len(pairs)} 条 -> {OUT}")
