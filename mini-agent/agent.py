# -*- coding: utf-8 -*-
"""
Agent 工具调用演示 v0
=====================
JD 里 "AI Agent / 智能体原理与搭建" 占 37.8%，
面试必问："Agent 和普通聊天机器人有什么区别？"

这个 100 行的小脚本就是为了回答这一句：
**普通聊天机器人只有"嘴"，Agent 多了一双"手"——它能决定调用哪个工具，并读取工具结果。**

实现的是最小 ReAct 循环（Reason → Act → Observe → Repeat），
不依赖 LangChain，纯手写，方便在面试时逐行讲清楚。
"""
import json
import os
import re
from datetime import datetime

from openai import OpenAI

# ---------- 1. 工具定义（这是 Agent 的"手"） ----------

def tool_now() -> str:
    """返回当前时间"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S 星期%w")


def tool_calc(expr: str) -> str:
    """只允许四则运算，防止 eval 注入"""
    if not re.fullmatch(r"[0-9+\-*/().\s]+", expr):
        return "错误：只支持数字和 + - * / ( )"
    try:
        return str(eval(expr, {"__builtins__": {}}, {}))
    except Exception as e:
        return f"错误：{e}"


def tool_search(keyword: str) -> str:
    """检索 FAQ 知识库（见 tools_kb.py）。命中则返回标准答案，未命中明确说不知道。"""
    import tools_kb
    hits = tools_kb.search(keyword)
    if not hits:
        return f"知识库里没有「{keyword}」相关的问答对。请如实告诉用户你无法确认，不要编造。"
    top = hits[0]
    return f"{top['answer']}（来源：{top['source']}，更新于 {top['updated']}，命中方式：{top['match']}）"


# 工具注册表：名字 → (函数, 描述, 参数说明)
# 描述写得好不好，直接决定模型会不会正确调用——这是 Agent 产品的核心工程
TOOLS = {
    "get_time": (tool_now, "获取当前日期和时间", "无参数"),
    "calculate": (tool_calc, "计算数学表达式", "expr: 四则运算字符串，如 3*7+2"),
    "search_kb": (tool_search, "在内部 FAQ 知识库检索标准答案；查不到时会返回「没有」，此时必须如实告知用户无法确认", "keyword: 要查的问题或概念，如 rag / 年假"),
}

SYSTEM = """你是一个会使用工具的助手。

可用工具：
{tools}

规则：
1. 需要外部信息或计算时，输出一行 JSON 调用工具：
   {{"tool": "工具名", "args": {{"参数": "值"}}}}
2. 不需要工具时，直接回答问题。
3. 拿到工具结果后，基于结果作答，不要忽略它。
4. 最多调用 3 次工具，够了就直接回答。

输出格式要求：调用工具时**只输出那一行 JSON**，不要加解释。
"""


def build_system() -> str:
    lines = []
    for name, (_, desc, args) in TOOLS.items():
        lines.append(f"- {name}：{desc}｜参数 {args}")
    return SYSTEM.format(tools="\n".join(lines))


# ---------- 2. ReAct 循环 ----------

def run_agent(question: str, model: str = "deepseek-chat", max_steps: int = 3, verbose=True) -> str:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY")
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    messages = [{"role": "system", "content": build_system()},
                {"role": "user", "content": question}]

    for step in range(1, max_steps + 1):
        resp = client.chat.completions.create(model=model, messages=messages, temperature=0)
        msg = resp.choices[0].message.content.strip()

        # 尝试解析工具调用
        call = None
        m = re.search(r'\{.*"tool".*\}', msg, re.S)
        if m:
            try:
                call = json.loads(m.group(0))
            except json.JSONDecodeError:
                call = None

        if not call:
            if verbose:
                print(f"[step {step}] 直接回答")
            return msg

        name = call.get("tool")
        args = call.get("args", {}) or {}
        if verbose:
            print(f"[step {step}] 调用工具 {name}({args})")

        if name not in TOOLS:
            observation = f"错误：没有名为 {name} 的工具"
        else:
            fn = TOOLS[name][0]
            try:
                observation = fn(**args)
            except TypeError as e:
                observation = f"参数错误：{e}"

        if verbose:
            print(f"[step {step}] 观察结果：{observation}")

        # 关键：把工具结果喂回对话，让模型基于结果继续（这就是 Observe → Reason）
        messages.append({"role": "assistant", "content": msg})
        messages.append({"role": "user", "content": f"工具返回：{observation}\n请基于这个结果回答原问题。"})

    return "（达到最大步数，未能给出最终答案）"


if __name__ == "__main__":
    demos = [
        "现在几点了？",
        "帮我算一下 (365-40)*24 是多少",
        "RAG 是什么？用一句话解释",
        "先查一下 prd 是什么，再告诉我它包含哪几个部分",
    ]
    for q in demos:
        print("\n" + "=" * 56)
        print("问：", q)
        print("-" * 56)
        print("答：", run_agent(q))
