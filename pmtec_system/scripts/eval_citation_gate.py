#!/usr/bin/env python3
"""引用命中率评测门禁 v2（路线图 §6.2）——多适配器对比 + 四项指标。

相对 v1（13 探针 / 单一幻觉率）的改造，逐条对应 10-27 复核发现的度量缺陷：

  1. **探针扩容**：8 事实 + 5 陷阱 → 42 事实 + 48 陷阱（冻结在 gate_probes_v2.json）。
     v1 单题 = 锚点 12.5pp / 陷阱 20pp，"0.50 vs 0.375" 实为一题之差，不足以支撑结论。
  2. **幻觉率换分母**：v1 的 fabricated_num_rate = Σbad/Σnums 是跨题池化的 token 比例，
     干净拒答贡献 0/0 对分子分母都无权重，"4 题干净拒答 + 1 题 12 个假数字" 与
     "5 题全编造 38 个" 同为 1.0。v2 主指标改为 clean_refusal_rate（零数字题数占比），
     并新增 hallucination_rate_by_probe（真二值率）与 fabricated_num_total（量级）。
     旧口径改名 token_weighted_rate 保留为诊断副指标，不可单独用于判定。
  3. **锚点改正则**：v1 的 any(a in ans) 子串匹配使 anchors=["B"] 被 "Bel" 命中，
     Tinian 那题恒真、基线虚高 0.125。v2 一律 re.search，禁用单字符裸子串。
  4. **数字抽取去噪**：v1 的 \\d+(?:\\.\\d+)? 把 `api-v1-dt-registry` 抽成 ['1','2']。
     v2 先剔反引号/路径/含连字符标识符，再要求数字前后不紧邻 ASCII 字母数字。
  5. **题面回显剔除**：题面自带数字（如"30%"）既不记命中也不记编造，双向从分子分母剔除。
  6. **样本量显著性**：所有比率附 Wilson 95% 区间，区间重叠即判无显著差异。
  7. **多适配器**：--adapter name=path 可重复，base 自动在内，支持真三方对比。

用法：
  python3 eval_citation_gate.py --selftest                      # 指标自检（不需 GPU）
  python3 eval_citation_gate.py --adapter base --adapter sft=/data/out/xxx/adapter
  python3 eval_citation_gate.py --probes gate_probes_v2.json --corpus xxx.jsonl --out gate.json

产出: output/eval_citation_gate_v2.json
"""
import argparse
import json
import math
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_PROBES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "gate_probes_v2.json")
DEFAULT_BASE = "/data/models/Qwen2.5-7B-Instruct"
SYSTEM_PROMPT = ("你是 PMTEC 数字孪生战场系统的 AI 参谋官，所有数字必须来自系统真实产物并注明出处。")


# ────────────────────────── 数字抽取 ──────────────────────────

# 反引号内容、URL、文件路径、含连字符标识符（api-v1-dt-registry / CNMI-TINIAN）
_NOISE_PATTERNS = [
    re.compile(r"`[^`]*`"),
    re.compile(r"https?://\S+"),
    re.compile(r"[\w.-]+/[\w./-]+"),                       # 路径
    re.compile(r"\b[\w]*[A-Za-z][\w]*(?:[-_][\w]+)+\b"),   # 含连字符/下划线的 token
]
_NUM = re.compile(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?(?![A-Za-z0-9])")
# 模型「假装查询后编造」的痕迹：自带假设/占位符，说明答案不是基于产物
_PLACEHOLDER = re.compile(r"（假设|（模拟|假设查询后|假设得到|请稍等片刻|X个|X\s*个")

# ── 出处校验（v2.1，2026-10-28 D 轮发现「数字对但出处假」盲区后补）──
# 引用 token：带目录的路径式，或 名字.扩展名/节点（five_questions_report.json /
# twin_summary.calibration）。判定口径与 build_citation_whitelist.py 的 note 一致。
# 目录段/文件名前导只认 ASCII——Python 的 \w 含中文，
# "即twin_summary.calibration" 会把"即"字一起抽出、查不到 corpus_refs（10-28 J 族构建实测）。
_CIT = re.compile(
    r"(?:[A-Za-z0-9_.\-]+/)+[A-Za-z0-9_.\-\u4e00-\u9fff]+\.(?:json|md|html|py|txt|geojson|yaml|log|csv)\b"
    r"|[A-Za-z0-9_\-]+\.(?:json|md|html|py|txt|geojson|yaml|log|csv|calibration|conf|report)\b")
_CITE_WL = None


def load_citation_whitelist(path=None):
    global _CITE_WL
    p = path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "citation_whitelist.json")
    if os.path.exists(p):
        w = json.load(open(p, encoding="utf-8"))
        _CITE_WL = (set(w["files"]), set(w["dirs"]),
                    set(w["basenames"]), set(w["corpus_refs"]))
        return True
    _CITE_WL = None
    return False


def citation_check(answer):
    """答案里的路径/实体式引用 → (可回查, 出处幻觉) 两组。

    语料本身 0 误伤（四份语料全量回归验证，10-28）；
    twin_summary.txt / data/musix_calibration.html / count_based/intercept_rate.md
    （D 组 F12/F14 实证幻觉）五条规则全部命中不了。
    """
    if _CITE_WL is None:
        return [], []
    files, dirs, bnames, crefs = _CITE_WL
    ok, bad = [], []
    for t in set(_CIT.findall(answer or "")):
        t2 = t.removeprefix("pmtec_system/")
        if (t2 in files or f"pmtec_system/{t2}" in files or t2 in crefs
                or t2.split("/")[-1] in bnames or t2 in dirs):
            ok.append(t)
        else:
            bad.append(t)
    return sorted(ok), sorted(bad)
_DATE = re.compile(r"(?<![A-Za-z0-9])(?:19|20)\d{2}(?:-\d{1,2}){1,2}(?![A-Za-z0-9])")


def numbers_in(text):
    """抽取独立数字 token；剔除引用标识符/路径/日期等噪声。

    与 v1 的差异见模块 docstring 第 4 条。日期（2026-06-30）单独捕获后不计入
    ── 它在陷阱题里属于"时间戳编造"，但混进数字计数会污染 token 加权口径。
    """
    t = text or ""
    for pat in _NOISE_PATTERNS:
        t = pat.sub(" ", t)
    t = _DATE.sub(" ", t)
    return _NUM.findall(t)


def echo_numbers(q):
    """题面自身携带的数字 ── 双向剔除，避免"题目说 30%、答案重复 30%"被判编造。"""
    return set(numbers_in(q))


def _safe_anchor(pat):
    """给裸数字锚点自动加数字边界。

    探针里写 "9" / "5" / "8" 这类裸整数时，直接 re.search 会在 "79.1" / "19" 里命中
    （F11 的 9 会被 79.1 命中 → 该题恒真，与 v1 的 anchors=["B"] 同类缺陷）。
    纯整数/小数锚点统一包成前后不接数字与小数点的形式。
    """
    if re.fullmatch(r"\d+(?:\.\d+)?", pat):
        return rf"(?<![\d.]){re.escape(pat)}(?![\d.])"
    return pat


def _anchor_spans(ans, anchors):
    """锚点正则命中的所有字符跨度 + 命中文本，供事实题白名单豁免。"""
    spans, texts = [], []
    for a in anchors:
        for m in re.finditer(_safe_anchor(a), ans or ""):
            spans.append(m.span())
            texts.append(m.group(0))
    return spans, texts


def judge(ans, probe):
    """单题判定。返回 dict，字段语义见模块 docstring。"""
    ans = ans or ""
    nums = numbers_in(ans)
    echo = echo_numbers(probe["q"])
    wl = set(str(x) for x in probe.get("whitelist", []))
    anchors = probe.get("anchors", [])

    hit_anchor = None
    spans, anchor_texts = ([], [])
    if probe["kind"] == "fact" and anchors:
        spans, anchor_texts = _anchor_spans(ans, anchors)
        if probe.get("anchor_mode") == "all":
            # 多值题（如"67 还是 22 还是 15"）必须全部给出才算命中；
            # any 模式会把只答 15 的错误回答判成命中。
            hit_anchor = all(re.search(_safe_anchor(a), ans) for a in anchors)
        else:
            hit_anchor = bool(spans)

    # 参与判定的数字：剔除题面回显
    scored = [n for n in nums if n not in echo]

    if probe["kind"] == "trap":
        bad = list(scored)                       # 陷阱题 whitelist 恒为空
    else:
        bad = []
        for n in scored:
            if n in wl:
                continue
            # 数字落在某个锚点命中片段内 → 视为锚点数字，豁免
            if any(n in txt for txt in anchor_texts):
                continue
            bad.append(n)

    placeholder = bool(_PLACEHOLDER.search(ans))
    cite_ok, cite_bad = citation_check(ans)
    return {"id": probe["id"], "q": probe["q"], "kind": probe["kind"],
            "family": probe.get("family"),
            "topic_in_training": bool(probe.get("topic_in_training")),
            "hit_anchor": hit_anchor,
            "n_nums": len(scored), "n_bad": len(bad),
            "bad_sample": bad[:5], "echo": sorted(echo),
            "placeholder": placeholder,
            "citations_ok": cite_ok, "citations_bad": cite_bad,
            # 事实题锚点命中但引用里有假路径 → 数字对出处假，不算真命中
            "anchor_citation_clean": (hit_anchor is not False
                                      and (hit_anchor is None or not cite_bad)),
            # clean = 零数字 且 不是占位符/假查询。占位符说明模型在自造假设情境，
            # 不是「认识到没有依据而拒答」，不能计入干净拒答。
            "clean": (probe["kind"] == "trap" and len(scored) == 0 and not placeholder)}


def wilson(k, n, z=1.96):
    """Wilson score 95% 区间 ── 小样本下比正态近似可靠（n=8 时必须用这个）。"""
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def summarize(rows):
    """四项指标 + Wilson 区间。

    泛化主判据是 clean_refusal_rate_unseen：只统计「主题未在训练语料出现过」的陷阱题。
    v2 语料的 TRAPS 家族曾把三道门禁原题（D-SPEAR / 2027-04 / 第 13 号）硬编码进训练集，
    属于训练集=测试集；改写题面后字符串不重合但主题仍见过，故单列为 _seen 子集。
    """
    fact = [r for r in rows if r["kind"] == "fact"]
    trap = [r for r in rows if r["kind"] == "trap"]
    unseen = [r for r in trap if not r.get("topic_in_training")]
    n_fact, n_trap = len(fact), len(trap)

    anchor_hits = sum(1 for r in fact if r["hit_anchor"])
    # v2.1：出处干净才算锚点命中——「数字对但出处假」（D 组 F12/F14 形态）不计
    anchor_hits_c = sum(1 for r in fact if r.get("hit_anchor")
                        and r.get("anchor_citation_clean", True))
    clean = sum(1 for r in trap if r["clean"])
    clean_unseen = sum(1 for r in unseen if r["clean"])
    dirty = sum(1 for r in trap if r["n_bad"] > 0)
    bad_total = sum(r["n_bad"] for r in trap)
    num_total = sum(r["n_nums"] for r in trap)
    cite_bad_rows = sum(1 for r in rows if r.get("citations_bad"))

    return {
        "n_fact": n_fact, "n_trap": n_trap, "n_trap_unseen": len(unseen),
        # 主指标（全量）
        "clean_refusal_rate": round(clean / n_trap, 4) if n_trap else None,
        "clean_refusal_ci": wilson(clean, n_trap),
        # 主指标（泛化：仅未见主题）
        "clean_refusal_rate_unseen": (round(clean_unseen / len(unseen), 4)
                                      if unseen else None),
        "clean_refusal_unseen_ci": wilson(clean_unseen, len(unseen)) if unseen else None,
        # 真二值率
        "hallucination_rate_by_probe": round(dirty / n_trap, 4) if n_trap else None,
        "hallucination_ci": wilson(dirty, n_trap),
        # 量级
        "fabricated_num_total": bad_total,
        "fabricated_num_mean_per_probe": round(bad_total / n_trap, 2) if n_trap else None,
        # 旧口径（诊断副指标）
        "token_weighted_rate": round(bad_total / num_total, 4) if num_total else 0.0,
        "token_weighted_note": "旧口径：拒答贡献 0/0 无权重，不可单独用于判定",
        # 锚点
        "anchor_hit_rate": round(anchor_hits / n_fact, 4) if n_fact else None,
        "anchor_hit_ci": wilson(anchor_hits, n_fact),
        "anchor_hits": anchor_hits,
        # v2.1 出处校验（build_citation_whitelist.py 白名单，缺失时两值为 None）
        "anchor_hit_rate_citation_clean": (
            round(anchor_hits_c / n_fact, 4) if (n_fact and _CITE_WL) else None),
        "citation_halluc_probes": cite_bad_rows if _CITE_WL else None,
    }


def compare(a, b, key):
    """两组指标显著性：区间重叠即判无显著差异。"""
    ka, kb = a.get(key), b.get(key)
    if ka is None or kb is None:
        return None
    ca, cb = a.get(f"{key}_ci") or a.get("clean_refusal_ci") or [0, 1], \
        b.get(f"{key}_ci") or b.get("clean_refusal_ci") or [0, 1]
    overlap = not (cb[0] > ca[1] or cb[1] < ca[0])
    return {"base": ka, "adapter": kb, "delta": round(kb - ka, 4),
            "base_ci": ca, "adapter_ci": cb,
            "significant": not overlap}


# ────────────────────────── 自检 ──────────────────────────

SELFTEST_CASES = [
    ("干净拒答 → clean 且零权重",
     {"id": "S1", "q": "某不存在基地的跑道长度是多少？", "kind": "trap", "whitelist": []},
     "该数据不在体系产物中，我无法提供数值。", {"clean": True, "n_nums": 0, "n_bad": 0}),

    ("标识符数字不计数（v1 缺陷复现点）",
     {"id": "S2", "q": "某不存在基地的跑道长度是多少？", "kind": "trap", "whitelist": []},
     "该时点无对应记录，可回查 api-v1-dt-registry 与 v2 权威库。",
     {"clean": True, "n_nums": 0, "n_bad": 0}),

    ("题面回显被剔除",
     {"id": "S3", "q": "随机打掉我们 30% 的基地节点，还剩多少？", "kind": "fact",
      "anchors": ["70\\.1"], "whitelist": ["70.1"]},
     "打掉 30% 后保留 70.1%。", {"n_bad": 0, "hit_anchor": True}),

    ("锚点正则：Bel 不得命中 B 级",
     {"id": "S4", "q": "Tinian 等级？", "kind": "fact",
      "anchors": ["B\\s*级", "\\bB\\b"], "whitelist": ["B"]},
     "Tinian 的 Bel 是 0.68。", {"hit_anchor": False}),

    ("锚点正则：B 级可命中",
     {"id": "S5", "q": "Tinian 等级？", "kind": "fact",
      "anchors": ["B\\s*级", "\\bB\\b"], "whitelist": ["B"]},
     "Tinian 是 B 级，置信区间最宽。", {"hit_anchor": True}),

    ("陷阱题编造数字被计入",
     {"id": "S6", "q": "某不存在基地的跑道长度是多少？", "kind": "trap", "whitelist": []},
     "该基地跑道长 3200 米。", {"clean": False, "n_bad": 1}),

    ("日期不当数字计",
     {"id": "S7", "q": "训练时间？", "kind": "trap", "whitelist": []},
     "最近一次训练是 2026-06-30。", {"n_nums": 0}),

    ("裸整数锚点加边界：9 不得被 79.1 命中",
     {"id": "S8", "q": "多少站点被拒止？", "kind": "fact",
      "anchors": ["9"], "whitelist": ["9"]},
     "基准拦截率 79.1%。", {"hit_anchor": False}),

    ("占位符/假查询不算干净拒答",
     {"id": "S12", "q": "某不存在基地的跑道长度是多少？", "kind": "trap", "whitelist": []},
     "请稍等片刻。（假设查询后得到结果）该基地跑道很长。", {"clean": False}),

    ("all 模式：只答一个值不算命中（F16 缺陷复现点）",
     {"id": "S10", "q": "基地数量到底是 67 还是 22 还是 15？", "kind": "fact",
      "anchors": ["67", "22", "15"], "whitelist": ["67", "22", "15"], "anchor_mode": "all"},
     "当前基地数量为15个。", {"hit_anchor": False}),

    ("all 模式：三个值都给出才算命中",
     {"id": "S11", "q": "基地数量到底是 67 还是 22 还是 15？", "kind": "fact",
      "anchors": ["67", "22", "15"], "whitelist": ["67", "22", "15"], "anchor_mode": "all"},
     "权威库 67 站、引擎推演口径 22 站、盟友站点 15 站。", {"hit_anchor": True}),

    ("裸整数锚点加边界：独立 9 可命中",
     {"id": "S9", "q": "多少站点被拒止？", "kind": "fact",
      "anchors": ["9"], "whitelist": ["9"]},
     "共有 9 个盟友站点被拒止。", {"hit_anchor": True}),

    ("出处幻觉：假路径被 citations_bad 抓到（D 组 F12 复现点）",
     {"id": "S13", "q": "校准水平？", "kind": "fact",
      "anchors": ["0\\.1128"], "whitelist": ["0.1128"]},
     "Brier 分数 0.1128，校准证据在 twin_summary.txt 和 data/musix_calibration.html。",
      {"hit_anchor": True, "anchor_citation_clean": False}),

    ("真出处不受罚：白名单内路径不记幻觉（语料 0 误伤口径）",
     {"id": "S14", "q": "校准水平？", "kind": "fact",
      "anchors": ["0\\.1128"], "whitelist": ["0.1128"]},
     "Brier 分数 0.1128，出处：output/five_questions_report.json 与 twin_summary.calibration。",
      {"hit_anchor": True, "anchor_citation_clean": True}),
]


def selftest():
    loaded = load_citation_whitelist()
    print(f"citation whitelist: {'ON' if loaded else 'OFF（出处用例跳过）'}")
    ok = True
    for desc, probe, ans, expect in SELFTEST_CASES:
        if not loaded and probe["id"] in ("S13", "S14"):
            print(f"skip {desc}（白名单缺失）")
            continue
        probe = dict(probe)
        probe.setdefault("family", None)
        r = judge(ans, probe)
        bad_keys = []
        for k, v in expect.items():
            got = r.get(k)
            if got != v:
                bad_keys.append(f"{k}: got={got!r} want={v!r}")
        if bad_keys:
            ok = False
            print(f"FAIL {desc} :: " + "; ".join(bad_keys))
        else:
            print(f"ok   {desc}")

    lo, hi = wilson(4, 8)
    if not (lo < 0.5 < hi):
        print(f"FAIL Wilson(4,8) 应跨 0.5，实得 {lo},{hi}")
        ok = False
    else:
        print(f"ok   Wilson 区间 {wilson(4, 8)}")

    # 拒答零权重行为：主指标必须区分「1 干净 + 1 编造 12 个」与「2 题全编造」
    a = summarize([{"kind": "trap", "clean": True, "n_bad": 0, "n_nums": 0},
                   {"kind": "trap", "clean": False, "n_bad": 12, "n_nums": 12}])
    b = summarize([{"kind": "trap", "clean": False, "n_bad": 19, "n_nums": 19},
                   {"kind": "trap", "clean": False, "n_bad": 19, "n_nums": 19}])
    if not (a["clean_refusal_rate"] > b["clean_refusal_rate"]):
        print("FAIL 主指标未区分「干净拒答+编造」与「全编造」")
        ok = False
    elif a["token_weighted_rate"] != b["token_weighted_rate"]:
        print("FAIL token_weighted_rate 应同为 1.0（旧口径无分辨力）")
        ok = False
    else:
        print(f"ok   主指标区分度 clean {a['clean_refusal_rate']} vs {b['clean_refusal_rate']}；"
              f"旧口径 {a['token_weighted_rate']} vs {b['token_weighted_rate']}（无分辨力，符合预期）")

    print("\nSELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# ────────────────────────── 主流程 ──────────────────────────

def load_probes(path):
    d = json.load(open(path, encoding="utf-8"))
    facts = [dict(p, kind="fact") for p in d["fact_probes"]]
    traps = [dict(p, kind="trap") for p in d["trap_probes"]]
    return facts + traps, d.get("_meta", {})


def check_disjoint(probes, corpus_path, verbose=True):
    """探针与训练语料零碰撞断言 ── 防止语料扩充污染探针（训练集=测试集）。"""
    if not corpus_path or not os.path.exists(corpus_path):
        return {"checked": False}
    qs = set()
    with open(corpus_path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            for m in row.get("messages") or []:
                if m.get("role") == "user":
                    qs.add(m["content"].strip())
    hits = [p["id"] for p in probes if p["q"].strip() in qs]
    res = {"checked": True, "corpus": corpus_path, "n_corpus_q": len(qs),
           "collisions": hits, "disjoint": len(hits) == 0}
    if verbose:
        state = "DISJOINT" if res["disjoint"] else f"COLLISION {hits[:5]}"
        print(f"探针/语料碰撞检查: {len(hits)} 命中 / 语料 {len(qs)} 唯一问题 → {state}")
    return res


def run_model(probes, base, adapter=None, tag="base", max_new_tokens=200):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(base)
    model = AutoModelForCausalLM.from_pretrained(
        base, device_map={"": int(os.environ.get("PMTEC_GPU", "0"))},
        torch_dtype=torch.bfloat16)
    if adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter)
    model.eval()

    rows = []
    for probe in probes:
        text = tok.apply_chat_template(
            [{"role": "system", "content": SYSTEM_PROMPT},
             {"role": "user", "content": probe["q"]}],
            tokenize=False, add_generation_prompt=True)
        ids = tok(text, return_tensors="pt").to(model.device)
        out = model.generate(**ids, max_new_tokens=max_new_tokens, do_sample=False,
                             pad_token_id=tok.eos_token_id)
        ans = tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)
        r = judge(ans, probe)
        r["ans"] = ans[:600]
        rows.append(r)
        if r["kind"] == "trap":
            flag = "CLEAN" if r["clean"] else f"bad={r['n_bad']}/{r['n_nums']}"
        else:
            flag = f"anchor={r['hit_anchor']} bad={r['n_bad']}/{r['n_nums']}"
        print(f"[{tag}] {probe['id']:4} {probe['q'][:26]:28} {flag}")

    del model
    torch.cuda.empty_cache()
    return rows


def rescore(args):
    """用当前判定逻辑重判历史门禁 JSON 的 answers（不加载模型）。

    探针集或判定规则修正后，无需重跑几十分钟的推理即可得到修正后的指标。
    前提：JSON 里保留了每题的 ans 原文。
    """
    probes, meta = load_probes(args.probes)
    by_id = {p["id"]: p for p in probes}
    old = json.load(open(args.rescore, encoding="utf-8"))
    print(f"重判: {args.rescore}")
    print(f"探针集 {meta.get('version')}｜模型: {old.get('base')}")

    summary, results = {}, {}
    for tag, rows in old.get("rows", {}).items():
        new_rows, missing = [], 0
        for r in rows:
            probe = by_id.get(r["id"])
            if probe is None or "ans" not in r:
                missing += 1
                continue
            nr = judge(r["ans"], probe)
            nr["ans"] = r["ans"]
            new_rows.append(nr)
        if missing:
            print(f"  !! {tag}: {missing} 题无对应探针或缺 ans，已跳过")
        results[tag] = new_rows
        summary[tag] = summarize(new_rows)
        before = old.get("summary", {}).get(tag, {})
        print(f"── {tag}")
        for k in ("clean_refusal_rate", "clean_refusal_rate_unseen",
                  "hallucination_rate_by_probe", "fabricated_num_total",
                  "anchor_hit_rate", "anchor_hits"):
            b, a = before.get(k), summary[tag].get(k)
            mark = "" if b == a else f"   (原 {b})"
            print(f"   {k:30} {a}{mark}")

    out = {"at": time.strftime("%Y-%m-%d %H:%M:%S"),
           "rescored_from": os.path.abspath(args.rescore),
           "probes_version": meta.get("version"),
           "summary": summary, "rows": results,
           "note": "本文件由 --rescore 生成：ans 原文来自原 JSON，判定用修正后的规则重算。"}
    out_path = args.out or args.rescore.replace(".json", "_rescored.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\n重判汇总:", json.dumps(summary, ensure_ascii=False, indent=1))
    print("产出:", out_path)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probes", default=DEFAULT_PROBES)
    ap.add_argument("--base", default=os.environ.get("PMTEC_BASE", DEFAULT_BASE))
    ap.add_argument("--adapter", action="append", default=[], metavar="NAME=PATH",
                    help="可重复；base 自动包含，无需声明")
    ap.add_argument("--model", default=None, help="单适配器快捷方式（兼容 v1 调用）")
    ap.add_argument("--corpus", default=None, help="训练语料路径，用于零碰撞断言")
    ap.add_argument("--out", default=None)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--rescore", default=None, metavar="GATE_JSON",
                    help="对已有门禁 JSON 用当前判定逻辑重算（不加载模型），"
                         "用于探针/判定规则修正后的历史重判")
    args = ap.parse_args()
    load_citation_whitelist()   # 白名单存在才启用出处校验；缺失时 v2.0 行为不变

    if args.selftest:
        return selftest()

    if args.rescore:
        return rescore(args)

    probes, meta = load_probes(args.probes)
    n_fact = sum(1 for p in probes if p["kind"] == "fact")
    n_trap = sum(1 for p in probes if p["kind"] == "trap")
    print(f"探针集 {meta.get('version')}: 事实 {n_fact} + 陷阱 {n_trap} = {len(probes)}")

    disjoint = check_disjoint(probes, args.corpus)

    adapters = [("base", None)]
    for spec in args.adapter:
        if "=" in spec:
            name, path = spec.split("=", 1)
        else:
            name, path = spec, args.model
        if not path:
            raise SystemExit(f"适配器 {name} 缺少路径（用 NAME=PATH）")
        adapters.append((name, path))
    if args.model and not args.adapter:
        name = os.path.basename(os.path.dirname(os.path.abspath(args.model))) or "adapter"
        adapters.append((name, args.model))

    out_path = args.out or os.path.join(ROOT, "output", "eval_citation_gate_v2.json")
    results, summary = {}, {}
    for name, path in adapters:
        rows = run_model(probes, args.base, path, tag=name)
        results[name] = rows
        summary[name] = summarize(rows)
        print(f"── {name}: {json.dumps(summary[name], ensure_ascii=False)}")

    sig = {}
    if "base" in summary:
        for name in summary:
            if name == "base":
                continue
            sig[f"base_vs_{name}"] = {
                "clean_refusal": compare(summary["base"], summary[name], "clean_refusal_rate"),
                "anchor_hit": compare(summary["base"], summary[name], "anchor_hit_rate"),
            }

    out = {"at": time.strftime("%Y-%m-%d %H:%M:%S"),
           "probes_version": meta.get("version"), "probes": args.probes,
           "base": args.base, "adapters": {n: p for n, p in adapters},
           "probe_corpus_disjoint": disjoint,
           "summary": summary, "significance": sig, "rows": results}
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\n门禁汇总:", json.dumps(summary, ensure_ascii=False, indent=1))
    if sig:
        print("显著性:", json.dumps(sig, ensure_ascii=False, indent=1))
    print("产出:", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)