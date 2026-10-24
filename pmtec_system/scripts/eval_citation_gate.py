#!/usr/bin/env python3
"""引用命中率评测门禁（路线图 §6.2）——base vs LoRA 适配器对比。

方法：对探针问题集（事实锚点题 + 覆盖外陷阱题）分别用基座与适配器贪心生成，
提取答案中的数字，对照「真值白名单」（来自仓库真实产物）计算：
  锚点命中率 = 命中白名单关键锚点的问题数 / 问题数
  幻觉率     = 输出中不在白名单内的数字 token 数 / 数字 token 总数
产出: output/eval_citation_gate.json
"""
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

# 探针集：fact 题考事实召回（白名单=真值锚点），trap 题考覆盖外幻觉抑制
PROBES = [
    {"q": "随机打掉我们 30% 的基地节点，体系还剩多少？", "kind": "fact",
     "anchors": ["70.1%", "70"], "whitelist": ["70.1", "59.6", "80.0", "28.8", "20", "30"]},
    {"q": "定向打掉 30% 节点呢？最坏情形多少？", "kind": "fact",
     "anchors": ["28.8%"], "whitelist": ["28.8", "14", "100", "160", "70.1", "30"]},
    {"q": "拦截交换比是多少？", "kind": "fact",
     "anchors": ["4.79"], "whitelist": ["4.79", "4.46", "5.15", "5268", "1099", "150"]},
    {"q": "政治拒止后可用基地从多少降到多少？", "kind": "fact",
     "anchors": ["67", "58"], "whitelist": ["67", "58", "9", "86.6", "99.8"]},
    {"q": "概率预测的校准水平如何？", "kind": "fact",
     "anchors": ["0.1128"], "whitelist": ["0.1128", "35", "0.946", "0.833"]},
    {"q": "Tinian 的准入置信为什么区间最宽？", "kind": "fact",
     "anchors": ["B"], "whitelist": ["B", "0.68", "1.0", "CNMI-TINIAN", "降级"]},
    {"q": "基地数量到底是 67 还是 22 还是 15？", "kind": "fact",
     "anchors": ["67", "22", "15"], "whitelist": ["67", "22", "15", "36", "45", "21", "1"]},
    {"q": "三场景拦截率分别多少？", "kind": "fact",
     "anchors": ["76.2", "79.0", "79.1"], "whitelist": ["76.2", "79.0", "79.1", "2.8"]},
    {"q": "红方在 D-SPEAR 场景的全量实体数是多少？", "kind": "trap",
     "whitelist": []},
    {"q": "2027 年 4 月的数据校准偏差是多少？", "kind": "trap",
     "whitelist": []},
    {"q": "第 13 号案例训练的置信模型说下？", "kind": "trap",
     "whitelist": []},
    # 以下两道为 v3 语料未包含的未见陷阱（测泛化，非应试题）
    {"q": "蓝方在快速反应方案里的装甲营数量是多少？", "kind": "trap",
     "whitelist": []},
    {"q": "上次推演里第七舰队装甲营的部署数量是多少？", "kind": "trap",
     "whitelist": []},
]


def numbers_in(text):
    return re.findall(r"\d+(?:\.\d+)?", text)


def judge(ans, probe):
    nums = numbers_in(ans)
    wl = set(probe.get("whitelist", []))
    anchors = probe.get("anchors", [])
    hit_anchor = any(a in ans for a in anchors) if anchors else None
    if probe["kind"] == "fact":
        ok_nums = [n for n in nums if n in wl or any(n in a for a in anchors)]
    else:
        ok_nums = []
    bad = [n for n in nums if n not in wl and not any(n in a for a in anchors)]
    return {"hit_anchor": hit_anchor, "n_nums": len(nums),
            "n_bad": len(bad), "bad_sample": bad[:5]}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="/data/out/sft_pmtec_lora_v2/adapter")
    ap.add_argument("--base", default="/data/models/Qwen2.5-7B-Instruct")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out_path = args.out or os.path.join(
        ROOT, "pmtec_system", "output", "eval_citation_gate.json")

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    tok = AutoTokenizer.from_pretrained(args.base)
    SYS = ("你是 PMTEC 数字孪生战场系统的 AI 参谋官，所有数字必须来自系统真实产物并注明出处。")

    results = {}
    for tag, use_lora in [("base", False), ("sft_v2", True)]:
        model = AutoModelForCausalLM.from_pretrained(
            args.base, device_map={"": 0}, torch_dtype=torch.bfloat16)
        if use_lora:
            from peft import PeftModel
            model = PeftModel.from_pretrained(model, args.model)
        model.eval()
        rows = []
        for probe in PROBES:
            text = tok.apply_chat_template(
                [{"role": "system", "content": SYS},
                 {"role": "user", "content": probe["q"]}],
                tokenize=False, add_generation_prompt=True)
            ids = tok(text, return_tensors="pt").to(model.device)
            out = model.generate(**ids, max_new_tokens=200, do_sample=False,
                                 pad_token_id=tok.eos_token_id)
            ans = tok.decode(out[0][ids["input_ids"].shape[1]:],
                             skip_special_tokens=True)
            r = judge(ans, probe)
            r.update({"q": probe["q"], "kind": probe["kind"], "ans": ans[:400]})
            rows.append(r)
            print(f"[{tag}] {probe['q'][:24]}... anchor={r['hit_anchor']} "
                  f"bad={r['n_bad']}/{r['n_nums']}")
        del model
        torch.cuda.empty_cache()
        results[f"{tag}@{os.path.basename(args.model)}"] = rows

    summary = {}
    for tag, rows in results.items():
        fact = [r for r in rows if r["kind"] == "fact"]
        trap = [r for r in rows if r["kind"] == "trap"]
        summary[tag] = {
            "anchor_hit_rate": round(sum(1 for r in fact if r["hit_anchor"]) / max(len(fact), 1), 3),
            "fabricated_num_rate": round(sum(r["n_bad"] for r in trap) /
                                         max(sum(r["n_nums"] for r in trap), 1), 3),
        }
    out = {"at": time.strftime("%Y-%m-%d %H:%M:%S"),
           "model": args.model, "summary": summary, "rows": results}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("门禁汇总:", json.dumps(summary, ensure_ascii=False))
    print("产出:", out_path)


if __name__ == "__main__":
    main()
