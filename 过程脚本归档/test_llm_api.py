#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试阶跃星辰 Token Plan API（OpenAI 兼容协议）+ PMTEC 真实数据调用"""
import json
import sys
import time
import requests

API_KEY = "3vZfQUCfxYfjN7RP8wcTTHPL64ffq9R1ami1eXut0NxmcNQnGTmEyJhefG6V4XTfA"
BASE_URL = "https://api.stepfun.com/step_plan/v1"
MODEL = "step-3.7-flash"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


def chat(messages, max_tokens=2048, label=""):
    t0 = time.time()
    resp = requests.post(
        f"{BASE_URL}/chat/completions",
        headers=HEADERS,
        json={"model": MODEL, "messages": messages, "max_tokens": max_tokens},
        timeout=180,
    )
    dt = time.time() - t0
    print(f"\n{'='*60}")
    print(f"[{label}] HTTP {resp.status_code}  耗时 {dt:.1f}s")
    if resp.status_code != 200:
        print(resp.text[:500])
        sys.exit(1)
    data = resp.json()
    usage = data.get("usage", {})
    content = data["choices"][0]["message"]["content"]
    print(f"模型: {data.get('model')}  tokens: "
          f"prompt={usage.get('prompt_tokens')} completion={usage.get('completion_tokens')}")
    print(f"{'-'*60}")
    print(content)
    return content


def main():
    # 1. 连通性测试
    chat(
        [{"role": "user", "content": "用一句话回复：连接测试成功。"}],
        max_tokens=1024,
        label="TEST-1 连通性",
    )

    # 2. 真实数据测试：PMTEC P6 vs P7 评估结果
    with open(
        r"d:\APPs\数字孪生挑战赛\pmtec_system\data\p6_vs_p7_comparison.json",
        encoding="utf-8",
    ) as f:
        p6p7 = json.load(f)

    with open(
        r"d:\APPs\数字孪生挑战赛\pmtec_system\data\p7v2_monte_carlo_evaluation.json",
        encoding="utf-8",
    ) as f:
        p7v2 = json.load(f)

    # 只取关键部分避免过长
    p7v2_brief = {
        "target": p7v2.get("target"),
        "environment": p7v2.get("environment"),
        "stealth_breakthrough_50ep": p7v2.get("stealth_breakthrough_50ep"),
    }

    user_msg = (
        "以下是数字孪生反导仿真系统 PMTEC 的两组真实蒙特卡洛评估数据，请分析：\n"
        "1) P6 与 P7 模型的拦截率差异是否具有统计显著性（对比置信区间）；\n"
        "2) 改进环境（探测距离减半+区域防御+高超声速）下突破 70% 目标的达成情况；\n"
        "3) 给出下一步训练优化的建议。\n\n"
        f"【P6 vs P7 原始环境评估】\n{json.dumps(p6p7, ensure_ascii=False, indent=1)}\n\n"
        f"【P7v2 改进环境评估（摘要）】\n{json.dumps(p7v2_brief, ensure_ascii=False, indent=1)}"
    )

    chat(
        [
            {"role": "system", "content": "你是一名导弹防御与强化学习领域的仿真分析专家。"},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=16384,
        label="TEST-2 真实数据分析",
    )

    print("\n[OK] 全部测试通过")


if __name__ == "__main__":
    main()
