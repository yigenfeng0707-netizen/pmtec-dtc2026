# PMTEC 复现指南（Reproduction Guide）

> 评审 P0 整改项：复现包（环境+依赖+脚本+端到端日志）｜ 配套脚本：`pmtec_system/scripts/reproduce_all.py`
> 承诺：交付包内所有关键数字可由本指南的命令再生；跑不通的步骤就是缺陷，欢迎按此报障
> 信息截至 2026-09 ｜ 口径 67/22/15 见 `pmtec_system/README.md`「评估口径说明」

---

## 一、环境要求

| 项 | 要求 | 说明 |
|----|------|------|
| Python | ≥3.11 | 开发环境 3.11/3.12 实测 |
| 操作系统 | Windows / Linux 均可 | CI 在 ubuntu-latest 实跑六阶段 |
| JVM（可选） | java ≥8 | 仅 P14 HermiT 一致性推理需要；缺失时 SHACL/SPARQL/置信层全部可用 |
| Docker（可选） | compose v2 | 演示栈 `docker-compose.demo.yml`（引擎+展示中心+会话门禁） |
| 大模型 API（可选） | 任一 OpenAI 兼容端点 | 仅 AI 参谋官报告需要；不配则 503 降级，主链路零影响 |

## 二、安装

```bash
cd pmtec_system
pip install -r requirements.txt          # 全部依赖（P18 起含 requests/matplotlib/python-docx）
# 编译 proto（如需重新生成 gRPC 桩）
python -m grpc_tools.protoc -I proto --python_out=. --grpc_python_out=. proto/dtb_model.proto
```

## 三、一键复现（推荐入口）

```bash
python scripts/reproduce_all.py          # 快速档：依赖体检→口径自检→数据字典再生→五问实跑→5 个验收测试（约 5 分钟）
python scripts/reproduce_all.py --full   # 全量 27 个测试文件 + 60s 仿真冒烟（约 30-60 分钟）
```

**端到端日志**：每次运行自动留档 `output/reproduce_log_<时间戳>.txt`（步骤/命令/输出尾部/耗时/退出码）——交付包内附带一份实跑日志样例作为证据；评审重跑后可比对日志结构逐行核对。

## 四、分项复现命令（对应关键数字）

| 数字/产物 | 复现命令 | 预期 |
|-----------|----------|------|
| 基准拦截率 79.1%（CI 78.0-80.2） | `data/monte_carlo_results_v2_political.json` → `overall` | n=150、六策略 |
| 三场景 76.2→79.0→79.1 | 三个 `monte_carlo_results*.json` 逐个 `overall.intercept_rate` | 与 README 口径表一致 |
| 必答五问全部数字 | `python scripts/five_questions_analysis.py`（n=20,000；`--fast` 快速档） | `output/Five_Questions_Report.html` |
| 数据字典 | `python scripts/generate_data_dictionary.py` | `docs/PMTEC-数据字典.md` 再生 |
| 本体一致性/翻转测试 | `python -X utf8 test_p14_ontology.py`（需 JVM） | 21 断言 |
| DoDAF 投影校验 | `python -X utf8 test_p16_dodaf.py` | 26 断言，conforms=true |
| 语义工具层 | `python -X utf8 test_p17_semantic_tools.py` | 15 断言 |
| 五问门禁 | `python -X utf8 test_p18_five_questions.py` | 20 断言 |
| 口径自检 | `python scripts/caliber_check.py` | 硬校验全过 |
| 单机仿真全产物 | `python main.py --duration 300` | 战术页/报告/回放全量再生 |
| 演示栈（公网同款） | `docker compose -f docker-compose.demo.yml up -d` | :8888 展示中心 / :8080 REST / :8765 WS |

## 五、已知边界（如实声明）

1. `output/tiles/` 离线底图瓦片为可再生资产（`scripts/generate_map_tiles.py` 幂等重建），不入 git 不入包的副本随离线包附带；
2. torch 在容器内为 CPU 版（CI 磁盘与网络超时的共同根因已治）；本地 XPU/GPU 训练另见 README P5-P8 章节；
3. MC 结果文件为管线产物存档（重跑会因并行调度有 ±0.3pp 级波动，CI 口径以提交版本为准）；
4. AI 参谋官报告依赖外部 LLM API，复现环境中该步骤降级为 503 属**预期行为**，不算复现失败。
