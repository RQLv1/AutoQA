from textwrap import dedent


def build_fact_extraction_prompt(context_with_lines: str, max_facts: int) -> str:
    return dedent(
        f"""
        你需要从下述文档中抽取最多 {max_facts} 条可用于出题的关键事实。
        要求:
        - 每条事实简洁明确，便于出题与验证。
        - 标注出处的行号区间，例如 "L12-L18"。
        - 只输出 JSON 数组，格式为:
          [{{"fact": "...", "source": "L12-L18"}}, ...]

        文档(已加行号):
        {context_with_lines.strip()}
        """
    ).strip()

