# -*- coding: utf-8 -*-
"""
PRD → 原型生成器 v0
====================
解决的问题：产品经理把 PRD 写完，还要手工画一版线框给开发看，
这个"翻译"动作重复、耗时、且经常和文档对不上。

本工具做的事：读一份 PRD（markdown），抽出功能模块，
生成一张单文件 HTML 线框图（左侧菜单 + 主区域卡片 + 状态标注），
让 PRD 和原型从同一份源自动保持同步。

设计取舍：
1. 只出线框不出高保真 —— 高保真应该由设计师做，PM 出的图只解决"对齐理解"
2. 不做交互 —— 交互由开发实现，原型加了交互反而误导工期预期
3. 模块识别用规则不用模型 —— PRD 结构相对固定，规则更便宜更可复现
"""
import re
import sys
from pathlib import Path

# ---------- PRD 解析 ----------

def parse_prd(text: str) -> dict:
    """从 PRD markdown 里抽出：标题、目标用户、模块列表（含主流程与异常态）"""
    title = ""
    m = re.search(r"^#\s+(.+)$", text, re.M)
    if m:
        title = re.sub(r"^PRD\s*[：:]\s*", "", m.group(1).strip())

    audience = ""
    m = re.search(r"(?:目标用户|用户画像)[：:]\s*(.+)", text)
    if m:
        audience = m.group(1).strip()

    # 二级标题当作模块，其中的列表项当作功能点
    modules = []
    blocks = re.split(r"\n(?=##\s+)", text)
    for block in blocks:
        head = re.match(r"##\s+(.+)", block)
        if not head:
            continue
        name = re.sub(r"^[一二三四五六七八九十\d]+[、.．]\s*", "", head.group(1).strip())
        if any(k in name for k in ("背景", "目标", "概述", "文档", "修订", "验收")):
            continue
        points = [ln.strip("-* \t") for ln in block.splitlines()
                  if re.match(r"^\s*[-*]\s+", ln)]
        # 异常分支单独抽出来，线框图上要单独标注
        errors = [p for p in points if any(k in p for k in ("失败", "超时", "为空", "无结果",
                                                              "错误", "非法", "异常态", "不支持"))]
        normal = [p for p in points if p not in errors]
        modules.append({"name": name, "points": normal[:4], "errors": errors[:2]})

    return {"title": title or "未命名功能", "audience": audience, "modules": modules}


# ---------- HTML 渲染 ----------

CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:"PingFang SC","Microsoft YaHei",sans-serif; background:#F5F6F8; color:#1F2937; font-size:14px; }
.shell { display:flex; min-height:100vh; }
.side { width:200px; background:#FFFFFF; border-right:1px solid #E5E7EB; padding:20px 0; flex-shrink:0; }
.side .logo { font-size:15px; font-weight:600; padding:0 20px 16px; color:#111827; border-bottom:1px solid #F1F3F5; margin-bottom:12px; }
.side a { display:block; padding:9px 20px; color:#4B5563; text-decoration:none; font-size:13.5px; border-left:3px solid transparent; }
.side a.on { color:#2563EB; background:#F2F6FF; border-left-color:#2563EB; font-weight:500; }
.main { flex:1; padding:28px 32px; }
.hd { display:flex; align-items:baseline; gap:12px; margin-bottom:6px; }
.hd h1 { font-size:22px; font-weight:600; }
.tag { font-size:12px; color:#6B7280; background:#F3F4F6; padding:2px 8px; border-radius:3px; }
.sub { color:#6B7280; font-size:13px; margin-bottom:22px; }
.card { background:#FFF; border:1px solid #E5E7EB; border-radius:6px; padding:20px 22px; margin-bottom:16px; }
.card-h { display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; }
.card-h h2 { font-size:15px; font-weight:600; }
.chip { font-size:11.5px; padding:2px 8px; border-radius:10px; }
.chip.p0 { background:#FEF2F2; color:#B91C1C; }
.chip.p1 { background:#FFFBEB; color:#B45309; }
.row { border:1px dashed #D1D5DB; border-radius:4px; padding:12px 14px; margin-bottom:10px; background:#FAFBFC; }
.row .t { font-weight:500; color:#111827; margin-bottom:4px; }
.row .d { color:#6B7280; font-size:13px; line-height:1.7; }
.err { border-left:3px solid #F59E0B; background:#FFFBEB; padding:9px 12px; margin-top:8px; font-size:12.5px; color:#78350F; border-radius:0 4px 4px 0; }
.btn { display:inline-block; background:#2563EB; color:#fff; padding:8px 18px; border-radius:4px; font-size:13px; margin-top:6px; }
.empty { color:#9CA3AF; font-size:13px; padding:20px 0; text-align:center; }
.legend { margin-top:24px; font-size:12px; color:#9CA3AF; line-height:1.9; }
"""


def render_html(prd: dict) -> str:
    mods = prd["modules"]
    nav = "".join(
        f'<a href="#m{i}" class="{"on" if i == 0 else ""}">{m["name"]}</a>'
        for i, m in enumerate(mods)
    ) or '<a class="on">（未解析到模块）</a>'

    body = []
    for i, m in enumerate(mods):
        rows = []
        for j, p in enumerate(m["points"]):
            pri = "p0" if j == 0 else "p1"
            rows.append(f'<div class="row"><div class="t">{p}</div>'
                        f'<div class="d">［此处为线框区域：列表 / 表单 / 结果卡片，由交互稿细化］</div></div>')
        for e in m["errors"]:
            rows.append(f'<div class="err">异常态 · {e}</div>')
        if not rows:
            rows.append('<div class="empty">该模块在 PRD 中未列出功能点</div>')
        body.append(f'''<div class="card" id="m{i}">
  <div class="card-h"><h2>{m["name"]}</h2><span class="chip {("p0" if i == 0 else "p1")}">{"核心流程" if i == 0 else "支撑模块"}</span></div>
  {"".join(rows)}
  <span class="btn">主操作</span>
</div>''')

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>线框图 · {prd['title']}</title>
<style>{CSS}</style></head>
<body><div class="shell">
  <div class="side">
    <div class="logo">{prd['title'][:14]}</div>
    {nav}
  </div>
  <div class="main">
    <div class="hd"><h1>{prd['title']}</h1><span class="tag">线框图 v0 · 由 PRD 自动生成</span></div>
    <div class="sub">{('目标用户：' + prd['audience']) if prd['audience'] else ''}　共 {len(mods)} 个模块</div>
    {''.join(body)}
    <div class="legend">
      说明：本图由 <code>prd2wire.py</code> 从 PRD 自动生成，用于和开发/设计对齐"有哪些模块、每个模块放什么"。<br>
      不替代高保真设计稿；交互细节不在本图范围内。
    </div>
  </div>
</div></body></html>"""


def main():
    if len(sys.argv) < 2:
        print("用法：python prd2wire.py <prd.md> [-o out.html]")
        sys.exit(1)
    src = Path(sys.argv[1])
    out = Path(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[2] == "-o" else src.with_suffix(".wire.html")
    prd = parse_prd(src.read_text(encoding="utf-8"))
    if not prd["modules"]:
        print("[警告] 没有解析到任何 ## 模块，检查 PRD 是否用二级标题划分模块")
    out.write_text(render_html(prd), encoding="utf-8")
    print(f"[完成] 解析模块 {len(prd['modules'])} 个 → {out}")


if __name__ == "__main__":
    main()
