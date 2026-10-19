# -*- coding: utf-8 -*-
"""
技术语言 → 人话 翻译器 v0
==========================
三档输出：同行版 / 职场版 / 大白版

设计核心：只给判据，不给形容词。
"要通俗易懂"是形容词，模型不知道算不算达到；
"禁止出现任何英文缩写"是判据，模型能逐条自查。
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

from openai import OpenAI

# ---------- 三档约束：这是整个产品的核心资产 ----------

LEVEL_SPEC = {
    "peer": {
        "name": "同行版",
        "audience": "懂技术的人（工程师、技术面试官）",
        "rules": """1. 保留原文所有术语，但每个术语首次出现时给一句括号解释
2. 不许删减任何技术细节，宁可长不可漏
3. 段落顺序重排为「先结论，后实现」
4. 长度不限，但每一句都要有信息量""",
    },
    "pro": {
        "name": "职场版",
        "audience": "跨部门同事、产品/运营面试官（懂业务不懂技术）",
        "rules": """1. 术语全部翻译成业务语言，英文缩写最多保留 2 个且必须解释
2. 必须单独用一句话写「这对我们意味着什么」
3. 必须出现至少 1 个具体数字（对比、耗时、成本都可）
4. 全文 ≤ 200 字
5. 分段，每段 ≤ 3 行""",
    },
    "plain": {
        "name": "大白版",
        "audience": "完全外行的人（家人、朋友、非技术同学）",
        "rules": """1. 禁止出现任何英文缩写和术语
2. 必须用一个日常生活里的类比贯穿全文（比如：文件柜、实习生、开卷考试）
3. 结尾必须是一句话，让读者能直接原封不动说给别人听
4. 全文 ≤ 150 字
5. 语气正常成年人对成年人，不要幼稚化、不要"小朋友们"式口吻""",
    },
}

SYSTEM_PROMPT = """你是一个能把技术讲成人话的技术编辑。
你的唯一判断标准：读者读完，能不能用自己的话把这件事复述给别人。

三条纪律：
1. 通俗不等于删减。不许为了好懂把技术内容删空。
2. 降的是语言难度，不是语气幼稚度。不要用哄小孩的口吻。
3. 类比必须来自日常生活，且必须在文中说清楚"对应关系"，不能只是甩一个比喻就完事。
"""

USER_TEMPLATE = """【目标读者】{audience}

【这一档的硬性要求】
{rules}

【通用禁令】
- 不许用「赋能」「闭环」「底层逻辑」「抓手」「护城河」
- 不许用「随着……的发展」「在当今时代」「众所周知」开头
- 不许用「总之」「综上所述」「总而言之」结尾
- 不许出现没解释的术语

【交稿自检】
写完逐条核对上面的硬性要求，哪条没做到就重写那一段。
不要解释、不要道歉，直接给改好的版本。
最后单独一行输出：字数 / 术语数 / 用到的类比

【技术材料】
{material}
"""


def translate(material: str, level: str, model: str = "deepseek-chat") -> str:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY，先 setx DEEPSEEK_API_KEY \"sk-xxx\" 再重开终端")
    spec = LEVEL_SPEC[level]
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE.format(
                audience=spec["audience"], rules=spec["rules"], material=material)},
        ],
        temperature=0.5,
    )
    return resp.choices[0].message.content.strip()


def main():
    ap = argparse.ArgumentParser(description="把技术材料翻译成人话，三档可选")
    ap.add_argument("input", help="输入文件路径（.txt/.md）")
    ap.add_argument("--level", "-l", default="pro", choices=list(LEVEL_SPEC),
                    help="peer=同行 pro=职场 plain=大白（默认 pro）")
    ap.add_argument("--all", action="store_true", help="一次输出三档并对比")
    args = ap.parse_args()

    material = Path(args.input).read_text(encoding="utf-8").strip()
    levels = list(LEVEL_SPEC) if args.all else [args.level]

    results = {}
    for lv in levels:
        print(f"\n{'='*56}\n【{LEVEL_SPEC[lv]['name']}】给 {LEVEL_SPEC[lv]['audience']}\n{'='*56}\n")
        out = translate(material, lv)
        print(out)
        results[lv] = out

    if args.all:
        out_path = Path(args.input).with_suffix(".compare.md")
        md = [f"# 三档翻译对比\n\n原文长度：{len(material)} 字\n"]
        for lv, txt in results.items():
            md.append(f"\n## {LEVEL_SPEC[lv]['name']}\n\n{txt}\n")
        out_path.write_text("\n".join(md), encoding="utf-8")
        print(f"\n对比稿已存：{out_path}")


if __name__ == "__main__":
    main()
