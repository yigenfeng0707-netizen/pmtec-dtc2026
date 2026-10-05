# P14 失效边界三问答案卡（Failure Boundary Q&A）

> 赛题B支撑材料要求：任何本体结论必须同时给出「结论成立的边界条件」——
> 形式化为翻转条件 ∃c: Judge(e,c) ≠ Judge(e,c₀)。本卡三问均可用所列命令复现。

---

## 问一：哪些属性不可推断？边界在哪里？

- **声明**：本体只从「已断言事实」做逻辑后承推断，绝不从缺失推缺失（开放世界
  假设下的最小承诺）。三类边界：
  1. **可观测但不可推断**：`accessUncertainty`（host_nation/sovereign/territory）
     与 `basedAircraft`——它们是 D-S 置信层的**输入证据**，不是 HermiT 的推理目标；
     由 ABox 直赋，推理机不得由其派生状态结论
  2. **明确不建模（最小完备性）**：油料/弹药库存、战备等级、兵力实时位置——
     无权威公开数据源，纳入即引入虚构事实，违反「每一颗坐标都有出处」红线；
     该类属性在 TBox 中**不存在**而非"留空"，防止评审误读为已覆盖
  3. **可推断（公理保证）**：`AirBase ≡ ∃hasPart.Runway`、`LaunchCapable ≡
     ∃hasAccessState.(Open⊔Restricted)`、`AccessDeniedSite ≡ hasAccessState={denied}`
     ——仅这三条定义类公理驱动归类
- **复现**：删除任一基地的 hasAccessState 断言后跑 `python ontology/reason_check.py`，
  SHACL InstallationShape 报"状态断言缺失——无状态实体不得进入推理"（负样本已实测命中）

## 问二：可战性判定的翻转条件（政治 Denied 事件）

- **基线结论（c₀）**：HermiT 推理 |LaunchCapable|=67、|AccessDeniedSite|=0
- **翻转条件（形式化）**：∃ 单基地状态断言 c: hasAccessState(b)=state_denied，
  使 Judge(b∈LaunchCapable) 由真翻假，且 b 自动归入 AccessDeniedSite——
  **定义类公理保证翻转零人工规则**，与 P10 政治准入状态机 / P13 威胁孪生事件流
  语义接口对齐（事件改写断言 → 重推理即得新判定）
- **实测证据**：Misawa 置 Denied → LC 67→66、AD={base_JP_MISAWA}（唯一成员）；
  **仅 Restricted 不翻转**（Open⊔Restricted 均可战）——刻意设计，与东道国
  "受限但未禁飞"的现实语义一致
- **置信侧对称结论（参数扫描，2026-10-05 修正为可复算口径）**：host_nation+A 级
  证据下，政治证据 m({Denied}) 从 0.10→0.40（质量自无知集 Θ 转入明确拒止）时，
  **Bel(Open) 0.778→0.760，单参数域内判决不翻转**（始终 >0.5 判决线）；
  同期冲突系数 K 0.075→0.300 线性逼近 0.7 拒合成阈（已走 43% 路程）。
  **修正说明**：本卡曾引用"0.910→0.400 在 0.35-0.40 破 0.5、K 至 0.500"的扫描值，
  经复核与 `confidence.py` 的 `dempster_combine` 不相容（恒有 K≤m({Denied})，且
  Open 侧质量固定时 Bel 对 md 单参数不敏感）且无脚本可复现——P18 已作废该数字，
  以 `scripts/five_questions_analysis.py` Q5 实跑扫描为准。**正确的翻转机制是
  断言改写（上条 Misawa 实测）而非先验漂移**——置信层对先验单参数扰动稳健
  恰是设计目标（结论对先验不敏感），多参数联合失效见 Q3 敏感性排序
  （σ 扰动下 Denied 均值 0.15、最大 3）与 S1/S3 复合场景
- **复现**：`python -X utf8 test_p14_ontology.py`（断言 07-10，Misawa 翻转）；
  `python scripts/five_questions_analysis.py --fast`（Q5 m(Denied) 扫描，独立复算）

## 问三：本体出错场景——低精度数据源（Tinian B 级）会否产生假确定？

- **出错场景**：Tinian（CNMI-TINIAN）坐标沿用 v1 库（B 级降级，评级报告 #7 已标注）。
  若把"数据未覆盖"当作"属性不存在"，会静默错分（机场站缺 runway_m → 降为
  SupportSite 且不报错）——这是本体最真实的出错通道
- **三层防御（均已实测）**：
  1. **D-S 不装确定**：B 级 mass（0.20/0.25/0.55 无知）与准入证据合成后
     Tinian Bel(Open)=0.68、Pl(Open)=1.0——全帧最宽区间，置信层如实暴露数据弱度，
     不把 B 级数据伪装成 A 级结论
  2. **SHACL 报警**：InstallationShape/RunwayShape/NoOrphanPartShape 对缺失、
     越界（纬度 999）、孤立部件三注入全部命中（test 断言 12）
  3. **已声明的数据假设**：`singleRunwayDependency` 由"数据集每基地至多一条跑道
     记录"的记录级假设直赋（tc_ontology.py 注释声明）——上游 GeoJSON 升级多跑道
     记录时该属性必须改由 hasPart 基数推断，属**已知最脆弱假设**而非隐藏缺陷
- **复现**：`python ontology/confidence.py` 看 Tinian 区间；删跑道记录重跑
  `tc_ontology.py && reason_check.py` 观察分类与报警行为

---

**三问共同结论**：推理层（问二）由公理保证、单断言级可翻转且机器可验证；
置信层（问三）在证据弱时自我否决（拒绝合成/宽区间），不产出假确定；
数据假设层的失效路径全部有 SHACL 报警或显式声明，不存在"静默失效"通道。
