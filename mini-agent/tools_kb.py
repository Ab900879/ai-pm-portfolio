# -*- coding: utf-8 -*-
"""
问答对知识库（FAQ）
====================
给 agent.py 里的 search_kb 用。设计原则：
1. 三列结构：问题 / 标准答案 / 禁用表述 —— 禁用表述是防幻觉的第一道闸
2. 每条带来源与更新时间 —— 答案会过期，没有工期的知识库等于没有
3. 命中规则：先精确关键词，再同义词，最后模糊匹配；都不中就走兜底拒答
"""
import json
import re
from pathlib import Path

FAQ_PATH = Path(__file__).with_name("faq.json")


def load() -> list:
    return json.loads(FAQ_PATH.read_text(encoding="utf-8"))


def save(items: list) -> None:
    FAQ_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def search(query: str, k: int = 2) -> list:
    """返回命中的问答对（最多 k 条），带命中方式说明。"""
    q = query.lower().strip()
    items = load()
    hits = []

    # 第一轮：关键词精确命中
    for it in items:
        keys = [x.lower() for x in it.get("keywords", [])]
        if any(kw in q for kw in keys):
            hits.append({**it, "match": "keyword"})

    # 第二轮：同义词扩展（也是关键词，只是优先级低）
    if not hits:
        for it in items:
            syns = [x.lower() for x in it.get("synonyms", [])]
            if any(s in q for s in syns):
                hits.append({**it, "match": "synonym"})

    # 兜底：查询里带「是什么/什么是/怎么/如何」这类泛化词但两轮都没命中，
    # 不硬凑答案，直接返回空，交给上游走拒答。宁可说不知道，也不要答错。
    if not hits and re.search(r"什么是|是什么|怎么|如何|为什么", q):
        return []

    # 第三轮：问题文本模糊包含（要求连续 3 字相同，避免误命中）
    if not hits:
        for it in items:
            qs = it.get("question", "")
            if any(qs[i:i+3] in q for i in range(len(qs) - 2)):
                hits.append({**it, "match": "fuzzy"})

    # 按优先级排序：对比/关系型条目优先，避免被单概念条目抢走
    hits.sort(key=lambda x: x.get("priority", 2))
    return hits[:k]


def guard(answer: str) -> tuple:
    """禁用表述闸门：答案里出现禁用词就拦下来。
    返回 (是否通过, 命中的禁用词列表)"""
    bad = []
    for it in load():
        for w in it.get("forbidden", []):
            if w and w in answer:
                bad.append(w)
    return (len(bad) == 0, bad)


def add(question: str, answer: str, keywords=None, synonyms=None, forbidden=None, source="manual"):
    """新增一条问答对。badcase 回填就走这个入口。"""
    from datetime import datetime
    items = load()
    items.append({
        "id": f"faq-{len(items)+1:03d}",
        "question": question,
        "answer": answer,
        "keywords": keywords or [],
        "synonyms": synonyms or [],
        "forbidden": forbidden or [],
        "source": source,
        "updated": datetime.now().strftime("%Y-%m-%d"),
    })
    save(items)
    return items[-1]


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        for h in search(sys.argv[1]):
            print(f"[{h['match']}] {h['question']}\n  {h['answer']}\n")
    else:
        print(f"共 {len(load())} 条问答对")
