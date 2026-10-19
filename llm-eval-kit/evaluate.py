# -*- coding: utf-8 -*-
"""
大模型效果评测工具 v0
======================
JD 里"模型效果评测 / Badcase 归因"占 21.6%，看着不高，
但它是 AI 产品岗**唯一能证明"你不是凭感觉说好"**的能力。

这个工具做三件小事：
1. 跑评测集（一批测试问题 + 期望要点），逐条调用模型
2. 四条规则自动打分（含要点命中 / 是否编造 / 长度合规 / 有无禁止词）
3. 按 badcase 类型聚合，输出归因报告（这是产品经理最该会的那部分）

设计取舍：
- 不做 LLM-as-Judge（用模型打分）。原因：小规模评测里模型打分不稳，
  规则能覆盖的部分先用规则，规则覆盖不了的再上模型，不要一上来就上贵的方案。
- 不追求指标漂亮，追求**能定位到"这批问题错在哪一类"**。
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from openai import OpenAI

# ---------- 评测集格式 ----------
# testsets/*.json 结构：
# [
#   {"id":"q1","input":"问题","must_contain":["要点A","要点B"],"forbidden":["赋能"],"max_len":200}
# ]


def rule_score(answer: str, case: dict) -> dict:
    """四条规则打分。返回每条的判定结果 + 失败原因，便于归因。"""
    fails = []

    # R1 要点命中率：期望要点里至少出现一半
    must = case.get("must_contain", [])
    hit = [k for k in must if k in answer]
    r1 = len(hit) / len(must) if must else 1.0
    if must and r1 < 0.5:
        missed = [k for k in must if k not in answer]
        fails.append(("要点缺失", f"缺 {len(missed)} 个要点：{'、'.join(missed[:3])}"))

    # R2 编造风险：答案里出现"具体数字/条款"但原文没有依据，用启发式标记
    #    真实工程里这里要接知识库核对，v0 先用"数字密度异常"做代理指标
    nums = re.findall(r"\d+", answer)
    r2 = 1.0
    if len(nums) >= 3 and len(must) > 0 and r1 < 0.5:
        r2 = 0.0
        fails.append(("疑似编造", f"答案含 {len(nums)} 处数字，但要点命中率仅 {r1:.0%}"))

    # R3 长度合规
    max_len = case.get("max_len", 300)
    r3 = 1.0 if len(answer) <= max_len else 0.0
    if r3 == 0:
        fails.append(("超长", f"{len(answer)} 字 > 上限 {max_len}"))

    # R4 禁止词
    forb = [w for w in case.get("forbidden", []) if w in answer]
    r4 = 0.0 if forb else 1.0
    if forb:
        fails.append(("禁用词", f"出现：{'、'.join(forb)}"))

    total = round((r1 * 0.4 + r2 * 0.3 + r3 * 0.15 + r4 * 0.15) * 100, 1)
    return {
        "score": total,
        "r1_recall": round(r1, 2),
        "r2_no_fabrication": r2,
        "r3_length_ok": r3,
        "r4_no_forbidden": r4,
        "fails": fails,
    }


def run_eval(testset_path: str, system_prompt: str, model: str = "deepseek-chat") -> dict:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY")
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    cases = json.loads(Path(testset_path).read_text(encoding="utf-8"))
    results = []
    for i, case in enumerate(cases, 1):
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": case["input"]}],
            temperature=0.3,
        )
        answer = resp.choices[0].message.content.strip()
        s = rule_score(answer, case)
        results.append({"id": case["id"], "input": case["input"],
                        "answer": answer, **s})
        print(f"[{i}/{len(cases)}] {case['id']}  {s['score']:>5} 分  "
              f"{' | '.join(f[0] for f in s['fails']) or '通过'}")

    return build_report(results)


def build_report(results: list) -> dict:
    n = len(results)
    avg = round(sum(r["score"] for r in results) / n, 1) if n else 0

    # badcase 归因：按失败类型聚合，这是产品经理最该做的事
    bucket = defaultdict(list)
    for r in results:
        for t, msg in r["fails"]:
            bucket[t].append({"id": r["id"], "input": r["input"][:30], "detail": msg})

    return {
        "sample_size": n,
        "avg_score": avg,
        "pass_rate": round(sum(1 for r in results if r["score"] >= 70) / n, 3) if n else 0,
        "badcase_distribution": {k: len(v) for k, v in sorted(bucket.items(), key=lambda x: -len(x[1]))},
        "badcase_detail": dict(bucket),
        "worst_3": sorted(results, key=lambda r: r["score"])[:3],
    }


def render(report: dict) -> str:
    L = ["=" * 56,
         f"样本数 {report['sample_size']}｜平均分 {report['avg_score']}｜通过率 {report['pass_rate']:.0%}",
         "=" * 56, "\n【Badcase 分布】"]
    if not report["badcase_distribution"]:
        L.append("无失败样本")
    for k, v in report["badcase_distribution"].items():
        bar = "█" * v
        L.append(f"{k:<8}{bar} {v} 例")
        for d in report["badcase_detail"][k][:2]:
            L.append(f"         · {d['id']}：{d['detail']}")
    L.append("\n【最差 3 条】")
    for r in report["worst_3"]:
        L.append(f"- {r['id']} ({r['score']}分) {r['input']}")
        L.append(f"  答：{r['answer'][:60]}…")
    return "\n".join(L)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python evaluate.py <testset.json> [system_prompt_file]")
        sys.exit(1)
    ts = sys.argv[1]
    sp = Path(sys.argv[2]).read_text(encoding="utf-8") if len(sys.argv) > 2 else "你是一个 AI 产品助手。"
    rep = run_eval(ts, sp)
    print("\n" + render(rep))
    out = Path(ts).with_suffix(".report.json")
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已存：{out}")
