# PMTEC 参谋官训练体系改造计划（P19）

> 制定日期：2026-10-27 ｜ 依据：10-24～10-26 七轮训练迭代（SFT v1-v6 / DPO v1-v7）的实测复盘
> 本计划是**改造方案**，不含已实施的代码改动。所有缺陷均标注了文件与行号，并附实证复现方式。
> 口径纪律：本文所有数字均为 2026-10-27 本机实测，非引自记忆或历史报告。执行完毕后须按仓库既有的「收敛法」重新核算终值。

---

## 零、一句话诊断

**训练线的路线判断是对的，但支撑判断的测量工具是坏的，执行工具是断的。**

七轮迭代的科学结论（正例事实对提升锚点、负例剂量-反应、SFT 拒答克隆比 DPO 安全）方向可信；但承载这些结论的 13 道探针门禁存在三重度量缺陷，一键续跑脚本存在三重硬故障，语料构建器已静默回退到被证伪的配方。**如果现在换 48GB 卡续跑，会在第一步就以设备索引错误中断；如果侥幸跑通，会拿到 352 条去重语料的次优模型，而且门禁会给出无法解读的分数。**

因此本计划把「修工具」排在「跑实验」之前。

---

## 一、缺陷清单（按严重度）

### D-1【阻断级】一键 Bootstrap 脚本存在三处硬故障，换卡必挂

文件：`pmtec_system/scripts/bootstrap_gpu_instance.sh`（已入库，末次提交 7487b2d）

| # | 位置 | 现象 | 根因 |
|---|---|---|---|
| a | L47 调用链 → `train_sft_pmtec.py:47` | `device_map={"": 1}` 硬编码 GPU 1 | 该值是双 4090 时代为绕开 transformers 4.51 跨设备 loss bug 而写死。48GB 单卡实例上不存在 `cuda:1`，加载即抛 `invalid device ordinal` |
| b | L19 `train_dpo_pmtec.py:19` | `SFT = "/data/out/sft_pmtec_lora_v2b/adapter"` | 脚本 L39 实际产出到 `sft_pmtec_lora_v2`（无 `b`）。v2b 适配器权重已确认丢失，两者都不是它的路径 → DPO 步骤 `FileNotFoundError` |
| c | L58 | `sed -i "s/MAXLEN = 256/MAXLEN = 384/"` | 目标文件实际是 `MAXLEN = 192`，替换静默无效。注释声称「48GB 卡回升 384」从未生效 |

附加三项（非阻断但削弱结果可信度）：

- **L55/L59 用的是 v1 语料**：`cp output/dpo_pairs.jsonl`（72 对，90% 负例）——正是已被 v6b 实验证伪、会把锚点从 0.25 拖到 0.125 的配方。v2 平衡版（2,395 对）在 `output/dpo_pairs_v2.jsonl`，脚本没引用。
- **L59-L60 的环境变量是空转**：`train_dpo_pmtec.py:20-21` 的 `DATA`/`OUT` 是硬编码，不读 `PMTEC_DPO_DATA`/`PMTEC_DPO_OUT`。
- **L72 声称「基座 vs SFT vs DPO 三方对比」**：`eval_citation_gate.py:88` 的循环只有 `("base", False), ("sft_v2", True)` 两支，且 `--model` 只接受单个适配器。三方对比从未发生。

> 同类问题还有一处：`pmtec_bundle/step2.sh` 等脚本引用 `sft_pmtec_v2.jsonl`（1,926 条），而 bundle 里只有 352 条版；这些 step 脚本按现状无法运行。

**影响**：这正是「重跑即再生」纪律的兑现点。当前状态是「承诺可再生，实际第一步就挂」。

---

### D-2【阻断级】语料构建器已静默回退到被证伪的 v3 配方

文件：`pmtec_system/scripts/build_sft_corpus.py:26-33`

```python
_seen = set()
def add(user, assistant, weight=1):
    """去重守卫（按用户问题唯一）；weight 用于陷阱拒答族上采样。"""
    if user in _seen:
        return
    _seen.add(user)
```

**实测对照**（本机执行）：

| 构建器版本 | 产出行数 | 说明 |
|---|---|---|
| `HEAD`（含去重守卫） | **352** | 即 e618f97 的负结果配方（锚点回归 0.25） |
| `0f323e0`（v2 时代） | **1,926** | 且与 `sft_pmtec_v3.jsonl` 前 1,926 行**逐字节一致**（已验证 `prefix identical: True`） |

去重守卫是在做 v3 反证实验时引入的，但它是**直接改写主干**而非加开关，于是主干永久停留在负结果配方上。而 `bootstrap_gpu_instance.sh:41` 调用的是 `scripts/build_sft_corpus.py` → 生成 352 条 → 脚本注释仍写着「SFT: 语料飞轮 v2 (1926 条)」。

**为什么这条最危险**：352 条训练同样会正常收敛、正常打出 `训练完成`、正常通过 `grep -q` 校验。**没有任何断言会发现它错了**，只是模型变差。

---

### D-3【阻断级】主干训练脚本保留了已知会降点的配方

文件：`pmtec_system/scripts/train_sft_pmtec.py`

| 行号 | 问题 | 后果 |
|---|---|---|
| 69, 76, 80 | `load_best_model_at_end=True` + `EarlyStoppingCallback(patience=2)` | 与 v4 锚点崩塌到 0.125 的记录根因完全一致。修好的版本只存在于**未入库**的 `pmtec_bundle/train_sft_refusal_v6.py` |
| 27 | `rows.sort(key=lambda r: hash(json.dumps(...)) % 1000)` | Python 字符串 hash 每进程随机化。实测：默认种子下前后两次运行 `eval[0]` 不同（`巴尔米拉…` / `Naval Base Guam…` / `Lal-lo…`）；固定 `PYTHONHASHSEED=0` 才稳定 → **train/eval 切分不可复现** |
| 27-30 | 按**行**切分，而非按**唯一问题**切分 | 见 D-5：语料 max_dup=8，同一问题极可能同时落入 train 和 eval → **eval 集被训练数据污染**，eval_loss 失去意义，早停决策建立在泄漏数据上 |
| 47 | `device_map={"": 1}` | 同 D-1a，单卡机不可用 |

**影响**：主干脚本的产物既不可复现，又大概率是次优检查点。v4/v5/v5b 三轮结果的离散（0.125 / 0.25 / 0.25）中，有多少来自配方差异、多少来自随机切分，目前无法区分——这是必须消除的混淆变量。

---

### D-4【严重】门禁指标存在三重度量缺陷

文件：`pmtec_system/scripts/eval_citation_gate.py`

#### (a) 「幻觉率」的分母里，拒答的权重为零

```python
fabricated_num_rate = sum(r['n_bad'] for r in trap) / max(sum(r['n_nums'] for r in trap), 1)
```

这是**跨 5 道陷阱题池化的 token 比例**。一道干净拒答贡献 `0 假 / 0 总`，对分子分母都不产生权重。于是「4 道干净拒答 + 1 道 12 个假数字」= `12/12 = 1.0`，「5 道全编造 38 个数字」也是 `38/38 = 1.0`。

**这不是「二值指标」，而是「拒答零权重指标」。** 之前总结的「必须 5/5 全干净才能翻转」是对的，但机制判断需要修正为分母加权问题——这个差别决定了修法：不是提高拒答剂量，而是换分母。

#### (b) 锚点用子串匹配，白送一分

`PROBES[5]`（Tinian）的 `anchors = ["B"]`，判定式为 `any(a in ans for a in anchors)`。任何含字母 B 的文本——包括 `Bel`——都命中。**这道题实际上恒真**，使得锚点基线虚高 1/8 = 0.125。

#### (c) 数字正则把标识符当数字

`numbers_in` 用 `\d+(?:\.\d+)?` 直接扫全文。实测：

| 文本 | 被抽出 |
|---|---|
| `见 api-v1-dt-registry 与 v2 权威库` | `['1', '2']` |
| `27 个实体` | `['27']` |

记忆中 v6 的「3/5 语义拒答却仍记 1.0」里，那唯一的假数字来源正是 `api-v1-dt-registry` 的 `1`。**一个合法的引用标识符被计成了编造数字。**

#### (d) 样本量不足以支撑现有结论

13 道探针（8 事实 + 5 陷阱）→ 单题 = 锚点 12.5pp、陷阱 20pp。

已被写入结论的关键对比，实际只差 1 道题：

| 对比 | 数值 | 实际含义 |
|---|---|---|
| v6b 0.50 vs v7 0.375 | 4/8 vs 3/8 | **一处一题之差** |
| v6b 0.50 vs 基线 0.25 | 4/8 vs 2/8 | 两题之差 |

「负例剂量-反应关系明确」这个结论，建立在单题差异上。方向可能是真的，但当前证据强度不足以称「明确」。

---

### D-5【严重】语料规模口径虚高 5.7 倍，且污染 eval

实测唯一问题数与重复度：

| 语料 | 行数 | 唯一问题 | 最大重复 | 唯一率 |
|---|---|---|---|---|
| v1（已入库） | 174 | 107 | 2 | 61.5% |
| v2（1,926 条） | 1,926 | **336** | **8** | 17.4% |
| v3 去重版 | 352 | 352 | 1 | 100% |
| v6 语料 | 2,696 | 1,106 | 8 | 41.0% |

三个直接推论：

1. **「11 倍语料飞轮（174→1,926）」实际是「唯一问题 107→336，3.1 倍」**，其余 5.7 倍是重复。文档与答辩口径需要修正。
2. v2 → v3 的锚点崩塌（0.50 → 0.25）是一次**近乎完美的干净对照**：v3 的唯一问题数从 336 **上升**到 352，行数从 1,926 **下降**到 352，锚点腰斩。这确凿证明塌掉的是**重复带来的事实上采样**，不是覆盖率。原结论正确，但真实数字比记录的更有说服力。
3. 既然 v2 有 336 个唯一问题、1,926 行，**按行切分 8 条 eval 必定与训练集共享问题**。之前的 eval_loss 全程不可信。

---

### D-6【中】承载全部关键结论的产物未入库

`git status` 实测 12 项未跟踪，合计约 6.4MB：

- `pmtec_bundle/`：5 个 step 脚本 + 4 份语料 + 6 个训练脚本
- `sft_pmtec_v3.jsonl`（2,696 条，1.8MB）、`dpo_pairs_v2.jsonl`（2,395 对，2.0MB）——**10-24 以来所有结论的唯一数据载体**
- `step2~6.tar.gz`、`pmtec_bundle.tar.gz`、`step4_bundle.tar.gz`：一次性传输载体
- `pmtec_system/data/models/sft_pmtec_lora_v2b/`：仅剩 `adapter_config.json` + `README.md`，权重已确认丢失

其中 5 个 bundle 脚本与主干同名脚本存在漂移（`train_sft_pmtec_dsw.py` 仅差 `device_map` 一行；`train_dpo_pmtec_dsw.py` 多了 liger 探测逻辑），属于「同一逻辑两份副本各自演化」。

**影响**：这些文件的唯一完整副本在 DSW 实例的 NAS（`/mnt/workspace/pmtec_out/`）。NAS 一旦清理即全失——而它们恰恰是「重跑即再生」所需的**配方本身**。可再生性的承诺，指向了一份不可再生且未入库的配方。

---

### D-7【中】训练报告停在 10-24，v4-v6 六轮结论零记录

`docs/PMTEC-参谋官SFT训练报告.md`（末次提交 10-24 22:34）只记录到里程碑 3（v3 负结果）。以下全部只存在于会话记忆，仓库内无任何痕迹：

- v4/v5/v5b 早停假设证伪
- DPO v6b 正例突破（0.50）、v7 剂量-反应（0.375）
- SFT v6 首个干净拒答（2/5 无数字、编造数字 38→12）
- DPO 在 24GB 卡上可跑（推翻 4090 时代的结构性 OOM 结论）、MAXLEN 与显存实测表

这与项目一贯「如实记录」的风格不符，也是换人或换会话即丢的风险。

---

### D-8【低】仓库卫生

- `.git` 已 854MB；6 个 step tar.gz 均为一次性传输载体，内容已还原为目录
- refs 与 packfile 未执行过 `gc`

---

## 二、改造方案

### 设计原则（三条）

1. **禁止用 `sed` 改写源码来传参。** D-1 的三处硬故障里有两处源于此（b 和 c 都是文本替换失配）。所有可变项走环境变量或命令行参数，源码只有一份。
2. **语料必须有 manifest，训练前强校验。** 行数、唯一问题数、sha256、配方名四元组对不上就拒训。D-2 的静默降级之所以危险，是因为缺少这一层。
3. **指标先于实验。** 在门禁重建完成前，不再启动任何新的训练轮次——否则新一轮的分数依然无法与历史比较。

---

### WP-1｜门禁指标重建（最高优先）

**新建** `pmtec_system/scripts/gate_probes_v2.json`（冻结探针集，含 seed 与生成规则）：
- 事实题 ≥ 40 道，覆盖五问锚点、口径三值（67/22/15）、Bel/Pl/K、交换比、三场景拦截率、FY2024 价值、政治准入三态
- 陷阱题 ≥ 40 道，六族等比例（基地属性 / 虚构场景 / 范围外时点 / 范围外编号 / 假设单位 / 诱导估算）+ 新增第七族「近似产物≠本问答案」（针对 v6 的两道残余失败：模型检索到 v2 库确有 27 个红方实体、确有 dqn 训练时间戳就敢答）
- 每道题带 `anchors`（**正则**，非子串）、`whitelist`、`echo`（题面自身的数字，双向剔除）

**改造** `eval_citation_gate.py`：

| 改动 | 具体做法 |
|---|---|
| 数字抽取 | 先剔除标识符/路径/代码片段（反引号内容、含连字符的 alnum token），再抽独立数字 token；要求数字前后非字母数字 |
| 锚点判定 | 改为正则匹配，`"B"` → `r"B\s*级\|B(?![A-Za-z])"`；禁用单字符子串 |
| 题面回显 | 题面出现的数字（如「30%」）既不记命中也不记编造，双向从分子分母剔除 |
| 指标族 | 新增四项并列报告：<br>① `clean_refusal_rate` = 零数字陷阱题数 / 陷阱题总数（**新主指标**）<br>② `hallucination_rate_by_probe` = 至少含 1 个编造数字的陷阱题数 / 陷阱题总数（真·二值率）<br>③ `fabricated_num_total` = 编造数字绝对个数（量级指标）<br>④ 保留原 `fabricated_num_rate` 作诊断副指标，改名为 `token_weighted_rate` 并注明拒答零权重 |
| 样本量 | 同时报告 Wilson 95% 置信区间；两模型差异须给出区间重叠判定，重叠即判「无显著差异」 |
| 多适配器 | `--adapter name=path` 可重复，支持 base + SFT + DPO 真三方对比，替换现有硬编码两支循环 |
| 自检 | 新增 `--selftest`，用固定 fixture（已知答案串）断言四项指标精确等于预期值，纳入 CI |

**验收**：
- `python scripts/eval_citation_gate.py --selftest` 精确通过
- 新门禁对历史门禁 JSON 能给出解释性对照（同一模型两套指标并列，说明差异来源）
- 探针集与训练语料的题目做**零碰撞断言**（写进 CI，防止未来语料扩充污染探针）

**工作量**：约 1 人日（含探针编写与自检 fixture）

---

### WP-2｜语料层：恢复 v2 配方 + manifest + 显式加权

**改造** `build_sft_corpus.py`：

1. **去重改为开关，默认关**：`--dedup` 才启用守卫，默认保持 1,926 条的重复上采样行为（该行为已被实证为锚点机制，不能默认去掉）。
2. **`--report` 输出 manifest** `output/corpus_manifest.json`：
   ```json
   {"recipe":"v2|v3-dedup|v6-refusal","rows":1926,"unique_questions":336,
    "dup_factor":5.73,"max_dup":8,"sha256":"...","builder_sha256":"...",
    "families":{"facts":1926,"refusal_A":270,...},"built_at":"..."}
   ```
3. **保留 v6 拒答构建器**：把 `pmtec_bundle/build_sft_refusal_v3.py` 收编为 `scripts/build_sft_refusal_corpus.py`，参数化 `--refusal-ratio`（当前 28.6%）、`--families`，并把 6 族权重写进 manifest。
4. **新增第七拒答族**「近似产物≠本问答案」：针对「实体真实存在但该问法不在产物里」的形态。这是 SFT v6 两道残余失败的直接对症。

**改造** `train_sft_pmtec.py` 的语料校验段（加在加载后、训练前）：
- 读同目录 manifest，断言 `sha256` 与数据一致、`rows` 与预期一致
- 断言 `unique_questions` 不低于配方下限
- 任一不符即 `sys.exit`，**不允许静默降级**

**验收**：
- `python scripts/build_sft_corpus.py --report` → 行数 1,926 / 唯一 336，与 0f323e0 产出逐字节一致
- 人为把语料截断到 100 行后启动训练 → 必须在 5 秒内拒绝并给出明确错误
- `--dedup` → 352 行，manifest 中 `dup_factor=1.0`

**工作量**：约 0.5 人日

---

### WP-3｜训练脚本主干化

**改造** `train_sft_pmtec.py`：

| 项 | 改动 |
|---|---|
| 早停 | 移除 `EarlyStoppingCallback` 与 `load_best_model_at_end=True`；改为 `save_strategy="no"`、训满固定 epoch。若将来需要早停，走 `--early-stop` 显式开关 |
| 切分 | 按**唯一问题**分组切分：先按 `hashlib.sha256(question)` 排序（跨进程稳定），再取前 N 个问题**连同其全部重复行**入 eval。消除 D-5 的泄漏 |
| 设备 | `device_map={"": int(os.environ.get("PMTEC_GPU", "0"))}`，默认 0 |
| 参数 | `MAXLEN`、`EPOCHS`、`LR` 全部走环境变量，带默认值 |
| 产物 | 适配器旁落 `training_meta.json`，额外记录：语料 manifest 的 sha256、GPU 型号与显存、torch/transformers/peft 版本、随机种子、切分实测（train/eval 各多少唯一问题） |

**改造** `train_dpo_pmtec.py`：
- `DATA`/`OUT`/`SFT`/`MAXLEN` 全部走 `PMTEC_DPO_*` 环境变量（消除 D-1 的空转）
- SFT 基座路径改为必填参数，不再给死路径默认值
- 保留 `precompute_ref_log_probs=True` 与 liger 0.5.10 的既有结论，写入脚本头部注释

**同一性约束**：`pmtec_bundle/*_dsw.py` 与主干脚本合并为一份。DSW 差异（`device_map`）已由环境变量覆盖，不再需要副本。

**验收**：
- 连续两次启动训练，`eval` 唯一问题集合的 sha256 完全一致（用 `--dry-run` 只跑切分并打印）
- 训练中断后无需人工判断即可从 `training_meta.json` 复原全部配方
- 单卡与双卡机都能启动到第一个 step（`PMTEC_GPU` 可覆盖）

**工作量**：约 0.5 人日

---

### WP-4｜Bootstrap 重写

**新建** `pmtec_system/scripts/train_pipeline.sh`，替换 `bootstrap_gpu_instance.sh`，子命令化：

```
train_pipeline.sh preflight   # 体检：GPU 数/显存、磁盘、基座、语料 manifest、依赖版本
train_pipeline.sh sft         # 训练 + 自动写 meta
train_pipeline.sh dpo         # 训练 + 自动写 meta
train_pipeline.sh gate        # 多适配器门禁
train_pipeline.sh all         # preflight → sft → dpo → gate，全程失败即停
```

关键改动：

1. **preflight 必须断言**：语料行数 == manifest 声明值；基座目录存在；显存 ≥ 需求；`pmtec_system/scripts` 中所有脚本 sha256 记录在案（防远程副本漂移）
2. **零 `sed`**：所有参数走环境变量（`PMTEC_GPU` / `PMTEC_SFT_DATA` / `PMTEC_SFT_OUT` / `PMTEC_DPO_SFT` / `PMTEC_DPO_DATA` / `PMTEC_DPO_OUT` / `PMTEC_MAXLEN`）
3. **DPO 语料默认 v2**：`dpo_pairs_v2.jsonl`（2,395 对），v1 的 72 对降级为 `--recipe v1` 显式选择
4. **门禁真三方**：`--adapter base= / sft=<path> / dpo=<path>`，一次跑完三个模型
5. **失败即停 + 状态标记**：每一步落 `STEP_STATE/<step>.{done,fail}`，失败带退出码与最后 20 行日志；不再依赖 `grep "训练完成"` 这种字符串校验
6. **显存自适应**：`PMTEC_MAXLEN` 默认按显存分档（<32GB→256，≥32GB→384），但**必须显式打印实际取值**并写进 meta，不允许静默

**验收**：
- 在无 GPU 的本机，`train_pipeline.sh preflight` 能正确报出全部缺失项并以非零码退出（不误报成功）
- 把语料人为换成 352 行版 → preflight 在训练前拒绝
- 三处硬故障（D-1 a/b/c）在脚本中不存在：全脚本 `grep -c "sed -"` 为 0

**工作量**：约 0.5 人日

---

### WP-5｜产物与配方入库

| 动作 | 明细 |
|---|---|
| 收编语料 | `pmtec_bundle/sft_pmtec_v3.jsonl` → `pmtec_system/data/corpora/sft_v6_2696.jsonl`；`dpo_pairs_v2.jsonl` → `data/corpora/dpo_v2_2395.jsonl`；同步 manifest |
| 收编脚本 | 5 个 bundle 脚本合并进 `scripts/`（与主干去重后只留一份）；`build_sft_refusal_v3.py` → `build_sft_refusal_corpus.py` |
| 收编运行手册 | 5 个 step 脚本合并为 `docs/PMTEC-训练迭代记录.md` 的附录（保留实验顺序与假设，作为可读的 runbook，而非可执行脚本） |
| 清理 | 删除 `step2/3/5/6.tar.gz`、`step4_bundle.tar.gz`、`pmtec_bundle.tar.gz`；`pmtec_bundle/` 清空后删除 |
| v2b 处置 | 保留 `adapter_config.json` + `README.md` 迁至 `data/models/provenance/sft_v2b/`，附 `WEIGHTS_LOST.md` 说明丢失经过 |
| gitignore | 新增 `pmtec_system/data/corpora/*.jsonl` 的**反向放行**（语料是文本、体积可控，必须入库）；`.git` 执行一次 `gc --aggressive --prune=now` |

**验收**：`git status` 干净，工作区无未跟踪的配方文件；`git ls-files | grep corpora` 可见三份语料 + 三份 manifest；`.git` 体积下降。

**工作量**：约 0.5 人日

---

### WP-6｜文档补齐与口径修正

**追加** `docs/PMTEC-参谋官SFT训练报告.md` 里程碑 4-6：

| 章节 | 内容 |
|---|---|
| 里程碑 4 | SFT v4/v5/v5b：早停假设证伪（0.25 不变），并**补记切分随机化这一混淆变量**（D-3） |
| 里程碑 5 | DPO v6/v6b/v7：正例事实对是锚点关键（0.25→0.50）、负例剂量-反应（25%→0.50 / 33%→0.375）、DPO 在 24GB 卡可跑（推翻旧结构性 OOM 结论）、MAXLEN×显存实测表 |
| 里程碑 6 | SFT v6 拒答克隆：首个干净拒答（2/5 无数字、3/5 语义拒答、编造数字 38→12）、锚点不掉（0.50） |
| 口径修正 | ①「11 倍语料」→「唯一问题 107→336（3.1 倍），行数因重复上采样放大 5.7 倍」；②「幻觉率 1.0」加注「token 加权口径，拒答零权重」；③所有锚点对比补「相差 N 题 / 样本量 8」 |

**新建** `docs/PMTEC-门禁指标说明.md`：定义四项指标、判定规则、置信区间用法、以及**为什么不再用旧的单一幻觉率**。

**工作量**：约 0.5 人日

---

### WP-7｜下一轮实验设计（依赖 WP-1～WP-4 完成）

工具修好后，48GB 卡上的实验应按此设计，而不是简单重跑：

| 组 | 配方 | 目的 |
|---|---|---|
| 基线 | 基座，无微调 | 新门禁下的重新标定 |
| A | SFT v2 配方（1,926 行 / 336 唯一） | 锚点基线，验证重复上采样在新门禁下的效应 |
| B | SFT v6 配方（事实 + 28.6% 拒答） | 复现「干净拒答」 |
| C | SFT v6 + 第七族「近似产物」+ 拒答比 40% | 针对两道残余失败 |
| D | DPO on C（2,395 平衡对） | 检验 DPO 是否在已克隆拒答的基座上仍有增益 |

**主判定指标**：`clean_refusal_rate`（40 道陷阱题中零数字的比例）。
**次判定**：`fabricated_num_total`、`hallucination_rate_by_probe`。
**上报锚点**：`anchor_hit` 及 Wilson 区间。

**不做的实验**：不再单纯提高负例占比（剂量-反应已测到 33% 反降）；不引入 GRPO（工具未稳，先不做新范式）；不换基座。

---

## 三、执行顺序与依赖

```
P0  D-1/D-2/D-3 阻断项最小修复（让链路能跑通）
 └─> WP-2 语料层 + WP-3 训练脚本        [并行]
 └─> WP-4 Bootstrap 重写
P1  WP-1 门禁重建（可与 P0 并行，但必须在任何新训练前完成）
P2  WP-5 产物入库 + WP-6 文档
P3  WP-7 云端实验（48GB 卡）
```

关键依赖：**WP-1 必须先于 WP-7**。若门禁未重建就开跑，新一轮结果无法与历史对照，等于再浪费一个实例计时。

预计总工作量 **4 人日**（不含云端训练机时）。

---

## 四、总体验收（可机器检查）

| # | 检查 | 命令 |
|---|---|---|
| 1 | 门禁自检精确通过 | `python scripts/eval_citation_gate.py --selftest` |
| 2 | 语料可复现且口径正确 | `python scripts/build_sft_corpus.py --report` → 1,926 行 / 336 唯一 |
| 3 | 训练切分确定 | 连跑两次 `--dry-run`，eval 唯一问题 sha256 一致 |
| 4 | 语料截断被拒 | 截断到 100 行 → 训练在 5 秒内以非零码退出 |
| 5 | 脚本无 sed 改写 | `grep -c "sed -" scripts/train_pipeline.sh` == 0 |
| 6 | 探针与语料零碰撞 | `python scripts/check_probe_disjoint.py` 退出码 0 |
| 7 | 工作区干净 | `git status --porcelain` 为空 |
| 8 | 三方门禁可跑 | `train_pipeline.sh gate --adapter base= --adapter sft= --adapter dpo=` |

---

## 五、不做的事（防跑偏）

1. **不动 DTC2026 已交付物**。离线包、技术方案、演示视频、ECS 部署均已提交，本计划全部改动限于训练线与文档。
2. **不重构 PMTEC 主系统**。`pmtec_system` 下引擎、可视化、本体层代码一律不碰，`train_pipeline.sh` 只是新增文件。
3. **不追求「幻觉率归零」这个表述**。修好门禁后若 `clean_refusal_rate` 达到 80% 而 `hallucination_rate_by_probe` 仍为 20%，那就是诚实的结果，如实写进报告，不用旧口径包装成失败或成功。
4. **不新增未经验证的断言**。所有本计划中的数字（336、2696、352、1926）附复现命令；执行后按「收敛法」重算，旧值在文档中留痕而非直接覆盖。

---

## 六、附：本计划所依据的实测复现命令

```bash
# D-2：构建器回归（HEAD 352 条 / 0f323e0 1926 条）
cd pmtec_system && python scripts/build_sft_corpus.py           # → 352
git show 0f323e0:pmtec_system/scripts/build_sft_corpus.py > /tmp/h.py && python /tmp/h.py  # → 1926

# D-3：切分不可复现（默认种子下 eval[0] 每次不同）
python -c "import json;rows=[json.loads(l) for l in open('pmtec_bundle/sft_pmtec_v3.jsonl',encoding='utf-8')];rows.sort(key=lambda r: hash(json.dumps(r['messages'],sort_keys=True))%1000);print(rows[0]['messages'][1]['content'][:30])"

# D-4c：正则把标识符当数字
python -c "import re;print(re.findall(r'\d+(?:\.\d+)?','见 api-v1-dt-registry 与 v2 权威库'))"  # → ['1','2']

# D-5：唯一问题数
python -c "import json,collections;rows=[json.loads(l) for l in open('pmtec_bundle/sft_pmtec_v3.jsonl',encoding='utf-8')][:1926];u=collections.Counter(r['messages'][1]['content'] for r in rows);print(len(rows),len(u),u.most_common(1)[0][1])"  # → 1926 336 8

# D-1：bootstrap 三处硬故障
grep -n 'device_map' pmtec_system/scripts/train_sft_pmtec.py            # L47 {"": 1}
grep -n '^SFT' pmtec_system/scripts/train_dpo_pmtec.py                  # L19 lora_v2b
grep -n 'MAXLEN =' pmtec_system/scripts/train_dpo_pmtec.py              # L22 192（sed 找的是 256）
```
---

# 附录：实施结果（2026-10-27）

本方案 WP-1 至 WP-6 已实施完毕，WP-7（云端实验）待 48GB 卡。实施期间发现一项
方案制定时未预见的重大缺陷（见 §A-1），其影响推翻了此前一轮实验的核心结论。

## A-1 新发现：语料构建器的整段复制粘贴事故

方案制定时把「1,926 行 vs 352 行」判断为「重复上采样 vs 去重」，并据此认为
v2 的重复是「事实上采样、有效训练信号」。**实施 WP-2 时发现该判断错误。**

### 实证

`build_sft_corpus.py` 的第 15–17 章在 v2 版本中被整段粘贴了 8 次：

```bash
$ git show 0f323e0:pmtec_system/scripts/build_sft_corpus.py | grep -c "# ── 15. 逐基地细节"
8
$ git show 0f323e0:... | grep -c "# ── 16. P1-P18"
8
$ git show 0f323e0:... | grep -c "# ── 17. 安全与可观测性"
8
```

改造前的 HEAD 更严重：第 561–2608 行整段重复约 10 遍，文件共 2,730 行。

### 三项交叉验证

| 检验 | 结果 | 含义 |
|---|---|---|
| 重复次数分布 | `{1:40, 2:67, 4:20, 8:209}` | 2 的幂 = 整段粘贴指纹，非设计 |
| `1926 ÷ 352` | **5.472**（非整数） | 均匀上采样必为整数倍 |
| `--upsample 8` 对照 | 352 × 8 = **2,816** | 真上采样应为整数倍 |

### 结论撤回

里程碑 3 记录的「重复=有效训练信号，去重伤害召回」**必须撤回**。
v2→v3 的对照混淆了两个不可分离的变量：重复量与**文件损坏程度**。
锚点 0.50 → 0.25 无法归因于任何一方。

**可主张的稳妥结论**：该差异原因未明。若要做「重复是否有效」的实验，
必须用 `--upsample N` 在同源干净语料上做受控对照。

### 已实施的修复

- 删除全部重复段：2,730 → **597 行**
- 去重守卫改 `--dedup` 开关（默认关 = 干净版）
- 新增 `--upsample N` 显式上采样 + manifest 记录倍数
- 新增 `--report` 输出 manifest（行数/唯一数/重复度/sha256/构建器 sha256）
- 训练脚本读 manifest 强校验，不符即拒训（退出码 1）

## A-2 另一项新发现：训练语料含门禁原题

v2 语料的 `TRAPS` 家族把三道门禁探针**逐字**硬编码进训练集：

| 训练语料中的题目 | 对应门禁探针 |
|---|---|
| 红方在 D-SPEAR 场景的全量实体数是多少？ | T01 |
| 2027 年 4 月的数据校准偏差是多少？ | T02 |
| 第 13 号案例训练的置信模型说下？ | T03 |

这是教科书式的**训练集=测试集**。v3 与 v6 的陷阱题成绩因此不可信。

**处理**：探针集内这三道题已改写（字符串不重合），但主题仍见过，
故标记 `topic_in_training: true` 并单列为「已见主题」子集；
新增 `clean_refusal_rate_unseen` 作为**泛化主判据**（45/48 道未见题）。

此外，第一版 v2 探针集有 **25 道陷阱题与 v6 语料逐字重合**——构建器与探针共用了
同一批实体/时点/编号/单位池。已全部替换并做零碰撞断言（现为 0 命中）。

## A-3 各工作包实施状态

| WP | 内容 | 状态 | 验证方式 |
|----|------|------|---------|
| WP-1 | 探针集 90 道 + 四指标门禁 | ✅ | `--selftest` 11 项全过；与两份语料零碰撞 |
| WP-2 | 语料构建器修复 + 拒答构建器七族 | ✅ | 副本删除；`--upsample` 1→352、8→2,816；拒答 28.5%/39.6% 双档 0 碰撞 |
| WP-3 | SFT/DPO 脚本主干化 | ✅ | 切分指纹三次一致（`6d837f517ac119df`）；截断语料退出码 1；v2b 丢权场景精确诊断 |
| WP-4 | `train_pipeline.sh` | ✅ | `grep -c "sed -i"` = **0**；preflight 正确识别全部缺失项；sft 失败留 `.fail` 标记 |
| WP-5 | 产物入库 | ✅ | 10 个语料/manifest 文件全部可跟踪；一次性 tar 包与 bundle 已清理 |
| WP-6 | 文档 | ✅ | 本文件 + `PMTEC-门禁指标说明.md` + 训练报告里程碑 4–8 |
| WP-7 | 云端实验 | ⏳ 待 48GB 卡 | 见下方 A-4 |

## A-4 WP-7 实验设计（在实施中细化）

工具修好后，48GB 卡上的实验：

| 组 | 配方 | 命令 | 目的 |
|----|------|------|------|
| 基线 | 基座 | `gate` | 新门禁下的重新标定（**必做**，旧基座分数已失效） |
| A | 干净事实语料 352 | `corpus`(clean) → `sft` | 新基线，同时给出「重复是否有效」的对照锚点 |
| B | 事实 + 28.6% 拒答（七族） | `corpus`(refusal) → `sft` | 复现干净拒答 + 新增第七族 |
| C | 事实 + 40% 拒答 | `PMTEC_REFUSAL_RATIO=0.40` | 剂量对照 |
| D | DPO on B | `sft` → `dpo` | DPO 在已克隆拒答的基座上是否仍有增益 |

**主判定**：`clean_refusal_rate_unseen`（未见主题的零数字比例）。
**次判定**：`fabricated_num_total`、`hallucination_rate_by_probe`。
**锚点**：`anchor_hit_rate` 及 Wilson 区间；区间与基线重叠即判无提升。

**必须先跑基线**：旧门禁下的 0.25 / 0.50 等数值在新口径下无意义，
不做基线重标定就无法判断任何实验组是否真的更好。

## A-5 与方案原定目标的偏差

| 项 | 方案原定 | 实际 | 说明 |
|---|---|---|---|
| 语料默认配方 | 恢复 1,926 行（保留重复） | **352 行干净版** | 重复是事故而非设计（A-1） |
| 探针集 | ≥40 事实 + ≥40 陷阱 | 42 + 48（七族） | 达成 |
| 主指标 | `clean_refusal_rate` | 同 + 新增泛化分层 `_unseen` | A-2 要求分层 |
| 工作量 | 4 人日 | 约 1 日（本机可验证部分全完成） | WP-7 待卡 |

## A-6 遗留事项

1. **WP-7 未执行**：需要 GPU（本机无 CUDA）。所有脚本已可在云端直接运行。
2. **旧分数未重标定**：v6b 的 0.50、v6 的「干净拒答」等均为旧口径，
   需在新门禁下重跑该模型才能对照。归档的 `sft_v6_2696.jsonl` 可用于复现 v6。
   （基座的重标定已完成，见训练报告里程碑 9；v6b/v6 适配器权重在 NAS。）
3. ~~`build_dpo_pairs.py` / `build_dpo_pairs_v2.py` 尚未收编~~
   **已收编（2026-10-27 清理归档）**：路径改读 `data/corpora/sft_facts.jsonl`，
   docstring 注明历史归档（`dpo_v1_72` / `dpo_v2_2395`）由事故语料构建、
   干净语料重跑会得到不同规模。同批清理：`bootstrap_gpu_instance.sh`（3 处硬故障，
   已被 `train_pipeline.sh` 取代）移入 `过程脚本归档/`；`output/` 下旧构建产物删除
   （canonical 副本在 `data/corpora/`）；`train_pipeline.sh` 的 `DPO_DATA` 默认值
   由已删除的 `output/dpo_pairs_v2.jsonl` 修正为 `data/corpora/dpo_v2_2395.jsonl`。
4. **CI 未接入新门禁**：`--selftest` 与零碰撞断言建议加入
   `.github/workflows/ci-cd.yml`，作为训练链路的回归门禁。
5. **云端实例残留（未动，有意保留）**：实例 36.103.199.153 的 `/data/out/` 存有
   10-21 一代训练的 diag_rag17b*/diag_rag4b*/demo* 等旧文件（本地 `artifacts/`
   有同源记录，该目录 gitignore 不入库）；`/data/models/` 下的 Qwen3-1.7B/4B/8B
   与 `/data/serve_qwen3.sh` 等 vLLM 脚本属并行使用的其他项目，**不得清理**。
   如需回收磁盘只动 diag_*/demo*，且先确认与南湖项目无交集。
