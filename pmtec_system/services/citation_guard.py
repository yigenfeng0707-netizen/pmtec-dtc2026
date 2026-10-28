# -*- coding: utf-8 -*-
"""推理端出处守卫（P19 训练研究线的部署落点，2026-10-28）。

背景（六轮实验终局判断，见 docs/PMTEC-参谋官SFT训练报告.md 里程碑 12-14）：
参谋官模型存在「出处幻觉」——数字可能对，但引用的文件是近似拼写的假路径
（monte_carlo_results_v2_polICY.json 类）。训练侧（H/I/J 族）证明了逐 token
纠正不能根治；根治路径是把出处校验放在**推理端**：答案里的路径式引用必须
能在 citation_whitelist.json（346 个在册文件/79 目录/21 个语料教过的引用短语）
命中，否则整答降级。

单一口径原则：本模块是 citation_check 的唯一权威实现，
scripts/eval_citation_gate.py（评测）与本模块（部署）共用同一份白名单与规则，
杜绝「训练评测一套口径、部署另一套」的漂移。

用法:
    from services.citation_guard import guard_answer, load_guard
    load_guard()                      # 缺白名单时守卫自动失效（不阻断业务）
    safe = guard_answer(llm_output)   # 假引用 → 拦截声明；真引用/无引用 → 原样

环境变量:
    PMTEC_CITATION_GUARD  0 = 关闭守卫（默认开）
"""

import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_WHITELIST = os.path.join(_HERE, "..", "scripts", "citation_whitelist.json")

# 引用 token：目录段/文件名前导只认 ASCII（\w 含 CJK 会把「即」字连进 token，
# 10-28 J 族构建实测）；中文文件名靠 [末段] 匹配 basenames 兜住。
_CIT = re.compile(
    r"(?:[A-Za-z0-9_.\-]+/)+[A-Za-z0-9_.\-\u4e00-\u9fff]+\.(?:json|md|html|py|txt"
    r"|geojson|yaml|log|csv)\b"
    r"|[A-Za-z0-9_\-]+\.(?:json|md|html|py|txt|geojson|yaml|log|csv|calibration"
    r"|conf|report)\b")

_STATE = {"loaded": False, "files": set(), "dirs": set(),
          "basenames": set(), "corpus_refs": set()}

GUARD_BANNER = (
    "【出处守卫拦截】本次回答引用了系统产物清单之外的来源（{bad}）。"
    "按参谋官铁律——数字必须注明真实出处、出处造假与数字造假同罪——"
    "含假出处引用的回答整份不予采信。请回查在册产物后重新提问；"
    "在册可引用清单可向系统索取。")


def load_guard(whitelist_path: str | None = None) -> bool:
    """加载白名单。返回是否可用；文件缺失时守卫静默失效（不阻断业务）。"""
    global _STATE
    p = whitelist_path or _WHITELIST
    if not os.path.exists(p):
        _STATE["loaded"] = False
        return False
    w = json.load(open(p, encoding="utf-8"))
    _STATE = {"loaded": True,
              "files": set(w["files"]),
              "dirs": set(w["dirs"]),
              "basenames": set(w["basenames"]),
              "corpus_refs": set(w["corpus_refs"])}
    return True


def citation_check(answer: str) -> tuple[list, list]:
    """答案里的路径/实体式引用 → (可回查列表, 出处幻觉列表)。

    五条规则（与 build_citation_whitelist.py 的 note 一致）：
    token t（先剥 pmtec_system/ 前缀）满足 ①t∈files ②pmtec_system/t∈files
    ③t∈corpus_refs ④basename(t)∈basenames ⑤t∈dirs 之一即回查。
    白名单未加载时返回 ([], [])（守卫失效，不误伤）。
    """
    if not _STATE["loaded"]:
        return [], []
    files, dirs = _STATE["files"], _STATE["dirs"]
    bnames, crefs = _STATE["basenames"], _STATE["corpus_refs"]
    ok, bad = [], []
    for t in set(_CIT.findall(answer or "")):
        t2 = t.removeprefix("pmtec_system/")
        if (t2 in files or f"pmtec_system/{t2}" in files or t2 in crefs
                or t2.split("/")[-1] in bnames or t2 in dirs):
            ok.append(t)
        else:
            bad.append(t)
    return sorted(ok), sorted(bad)


def guard_answer(answer: str, enabled: bool | None = None) -> tuple[str, dict]:
    """LLM 输出的出处守卫。返回 (安全答案, 审计信息)。

    答案含假出处引用 → 整答替换为拦截声明（原文进审计字段，不丢弃——
    供离线审计与语料飞轮采集「真实失败样本」，E 轮方法学的部署闭环）。
    enabled 显式传参优先于环境变量 PMTEC_CITATION_GUARD。
    """
    if enabled is None:
        enabled = os.environ.get("PMTEC_CITATION_GUARD", "1") != "0"
    audit = {"guarded": False, "bad_citations": [], "original": None}
    if not enabled or not _STATE["loaded"] or not answer:
        return answer, audit
    ok, bad = citation_check(answer)
    if not bad:
        return answer, audit
    audit.update({"guarded": True, "bad_citations": bad, "original": answer})
    banner = GUARD_BANNER.format(bad="、".join(bad[:3])
                                 + ("等" if len(bad) > 3 else ""))
    return banner, audit
