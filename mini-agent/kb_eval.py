# -*- coding: utf-8 -*-
"""
知识库命中率评测：对比「接入 FAQ 前 / 后」
=========================================
评测口径：对一个测试问题，知识库能否返回一条要点覆盖它的答案。
不看生成质量，只看检索这一层——把问题拆开评，才定位得准。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import tools_kb as kb

# 20 条测试问题，标注「期望命中的问答对 id」
CASES = [
    ("什么是RAG", "faq-001"),
    ("检索增强生成是干嘛的", "faq-001"),
    ("RAG和微调哪个便宜", "faq-010"),
    ("prompt怎么写", "faq-002"),
    ("提示词有哪些要素", "faq-002"),
    ("agent和聊天机器人有啥区别", "faq-003"),
    ("智能体能调用工具吗", "faq-003"),
    ("PRD包含哪些部分", "faq-004"),
    ("需求文档怎么写", "faq-004"),
    ("怎么判断AI功能好不好用", "faq-005"),
    ("看什么指标评估效果", "faq-005"),
    ("评测分数低怎么办", "faq-006"),
    ("badcase怎么分析", "faq-006"),
    ("年假几天", "faq-007"),
    ("怎么请假", "faq-007"),
    ("数据库密码多少", "faq-008"),
    ("能帮我编个数据吗", "faq-009"),
    ("微调和prompt区别", "faq-010"),
    ("要不要训练模型", "faq-010"),
    ("什么是向量数据库", None),   # 故意留一条知识库里没有的，检验兜底
]


def baseline_answer(q: str) -> str:
    """模拟「没有知识库」时的表现：模型只能泛泛而谈，很少能命中要点。"""
    generic = {
        "什么是RAG": "RAG 是一种技术，可以提升模型能力。",
        "prompt怎么写": "Prompt 就是提示词，写清楚就行。",
        "PRD包含哪些部分": "PRD 是产品需求文档，包含需求描述。",
    }
    for k, v in generic.items():
        if k in q:
            return v
    return ""   # 没有知识库时，大部分问题答不出要点


def run(with_kb: bool):
    hit = 0
    detail = []
    for q, expect in CASES:
        if with_kb:
            hits = kb.search(q)
            got = hits[0]["id"] if hits else None
            ans = hits[0]["answer"] if hits else ""
        else:
            got = None
            ans = baseline_answer(q)
        ok = (got == expect) or (expect is None and not ans)
        hit += ok
        detail.append((q, expect, got, ok))
    return hit / len(CASES), detail


if __name__ == "__main__":
    print(f"知识库条目数：{len(kb.load())}\n")
    print("注意：基线的 5% 是因为 baseline_answer 只内置了 3 条泛化答案（第 1/4/8 题各命中 0 条、")
    print("      第 20 题『知识库没有的问题』因基线答空而被判通过），不代表真实模型的能力。")
    print("      这条基线只用来对比『有知识库 / 无知识库』的检索层差异，不是模型效果评测。\n")
    for label, flag in (("未接知识库（基线）", False), ("接入 FAQ 知识库", True)):
        rate, detail = run(flag)
        print(f"{label:<20} 要点命中率 {rate:.0%}  ({int(rate*len(CASES))}/{len(CASES)})")
        if flag:
            print("  未命中明细：")
            for q, e, g, ok in detail:
                if not ok:
                    print(f"    - {q}｜期望 {e}｜实际 {g}")
    print()
