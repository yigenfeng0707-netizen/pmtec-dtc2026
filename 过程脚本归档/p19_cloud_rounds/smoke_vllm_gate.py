#!/usr/bin/env python
"""vLLM 冒烟验证：sft_f 适配器经 vLLM 推理引擎跑满 90 探针（P19 收尾遗留项 A-6-③）。

复用 eval_citation_gate 的探针 / judge / summarize（与门禁严格同口径），仅把
生成后端从 transformers 换成 vLLM OpenAI 兼容服务。temperature=0 即贪心等价，
max_tokens 对齐门禁 max_new_tokens=200。citation_check 经 judge 间接调用，
覆盖 citation_guard 在 vLLM 输出上的端到端。

对照基准（gate_drill_f.json，transformers 贪心，训练报告里程碑 14）：
  净锚点 anchor_hit_rate_citation_clean = 8/42
  clean_refusal_rate = 0.667 (32/48)
  citation_halluc_probes（假出处题）= 6/90
通过判据：各指标偏差 <=2 题；超出按 runbook 排查顺序定位。

用法（实例上，vLLM 服务已在 8000 端口挂 sft_f）：
  /data/venv/bin/python -u scripts/smoke_vllm_gate.py \
      --api http://127.0.0.1:8000/v1 --model sft_f \
      --out /data/out/smoke_vllm_sft_f.json
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_citation_gate import (DEFAULT_PROBES, SYSTEM_PROMPT,  # noqa: E402
                                judge, load_guard, load_probes, summarize)


def chat(api, model, question, max_tokens, timeout=120, retries=2):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": question}],
        "temperature": 0,          # 贪心，与门禁 do_sample=False 等价
        "max_tokens": max_tokens,
    }).encode()
    last = None
    for _ in range(retries + 1):
        try:
            req = urllib.request.Request(
                f"{api}/chat/completions", data=body,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)["choices"][0]["message"]["content"]
        except (urllib.error.URLError, KeyError, TimeoutError) as e:
            last = e
            time.sleep(3)
    raise RuntimeError(f"chat 请求失败（重试 {retries} 次后）: {last}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000/v1")
    ap.add_argument("--model", default="sft_f", help="vLLM --lora-modules 里注册的模块名")
    ap.add_argument("--probes", default=DEFAULT_PROBES,
                    help="默认用门禁冻结探针 gate_probes_v2.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-tokens", type=int, default=200)
    ap.add_argument("--rejudge", default=None, metavar="JSON",
                    help="跳过生成：对已存 smoke JSON 的 rows 重新判分（需先 load_guard）")
    args = ap.parse_args()

    guard_ok = load_guard()
    print("citation 白名单:", "已加载" if guard_ok else "未加载（净锚点/假出处将为 None）")

    probes, meta = load_probes(args.probes)
    n_fact = sum(1 for p in probes if p["kind"] == "fact")
    n_trap = sum(1 for p in probes if p["kind"] == "trap")
    print(f"探针集 {meta.get('version')}: 事实 {n_fact} + 陷阱 {n_trap} = {len(probes)}")
    if args.rejudge:
        print(f"rejudge 模式：读 {args.rejudge} 的 rows 重新判分\n")
    else:
        print(f"后端 vLLM {args.api}  模块 {args.model}  max_tokens={args.max_tokens}\n")

    if args.rejudge:
        with open(args.rejudge, encoding="utf-8") as f:
            old_rows = json.load(f)["rows"]
        by_id = {p["id"]: p for p in probes}
        rows = [dict(judge(r["ans"], by_id[r["id"]]), ans=r["ans"][:600])
                for r in old_rows]
        tag = f"vllm-rejudge:{args.model}"
    else:
        tag = f"vllm:{args.model}"
        rows = []
    if not args.rejudge:
        for probe in probes:
            ans = chat(args.api, args.model, probe["q"], args.max_tokens) or ""
            r = judge(ans, probe)
            r["ans"] = ans[:600]
            rows.append(r)
            if r["kind"] == "trap":
                flag = "CLEAN" if r["clean"] else f"bad={r['n_bad']}/{r['n_nums']}"
            else:
                flag = f"anchor={r['hit_anchor']} cite_ok={r['citations_ok']}"
            print(f"[vllm] {probe['id']:4} {probe['q'][:26]:28} {flag}", flush=True)

    summary = summarize(rows)
    out = {"tag": tag, "backend": "vllm", "api": args.api,
           "model": args.model, "probes_version": meta.get("version"),
           "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "summary": summary, "rows": rows}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # 对照基准（gate_drill_f.json，transformers 贪心）
    base_anchor, base_clean, base_cite_bad = 8, 0.667, 6
    got_anchor = summary.get("anchor_hits")          # 毛锚点数
    got_anchor_c = summary.get("anchor_hit_rate_citation_clean")
    anchor_c_n = round((got_anchor_c or 0) * summary["n_fact"])
    print("\n== 冒烟汇总（vs 门禁 F 轮 transformers 口径）==")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"\n净锚点 {anchor_c_n}/{summary['n_fact']}  (基准 8/42, 容差 ±2)")
    print(f"clean {summary['clean_refusal_rate']}  (基准 0.667 = 32/48, 容差 ±2 题)")
    print(f"假出处题 {summary.get('citation_halluc_probes')}/90  (基准 6, 容差 ±2)")
    ok = (abs(anchor_c_n - base_anchor) <= 2
          and abs(summary["clean_refusal_rate"] * summary["n_trap"] - base_clean * 48) <= 2
          and abs((summary.get("citation_halluc_probes") or 0) - base_cite_bad) <= 2)
    print("SMOKE_PASS" if ok else "SMOKE_DIFF — 按 runbook 排查顺序定位")


if __name__ == "__main__":
    main()
