from textwrap import dedent


def build_fact_extraction_prompt(context_with_lines: str, max_facts: int) -> str:
    return dedent(
        f"""
        你需要从下述文档中抽取最多 {max_facts} 条“可用于条件计算/分支判定”的关键事实。
        要求:
        - 优先抽取：阈值/公式/单位换算/表格数值/分级规则/判定条件（能写成“若…则…”或“按…计算…”）。
        - 避免抽取：纯定义/背景描述/无法落地计算的陈述。
        - 标注出处的行号区间，例如 "L12-L18"。
        - 输出 JSON 数组，并给出类型 kind: "threshold|formula|rule|table|other"
        - 只输出 JSON 数组，格式为:
          [{{"fact": "...", "source": "L12-L18", "kind": "threshold"}}, ...]

        文档(已加行号):
        {context_with_lines.strip()}
        """
    ).strip()
