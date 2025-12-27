from textwrap import dedent


def build_analysis_prompt(
    question: str, answer: str, solver_answer: str, mode: str = "multi_select"
) -> str:
    q_type = "多选题" if mode != "single_select" else "单选题"
    return dedent(
        f"""
        请分析这道{q_type}为什么显得简单，并指出可提升的点。若求解模型未答对，也请基于题面与作答输出找出可能的简化点。
        题目: {question}
        标准答案: {answer}
        求解模型作答: {solver_answer}

        输出格式:
        - 简单原因: 几句话
        - 提升点: 用简洁中文列出多条可提升难度的建议
        - 不要重复题面原句。
        """
    ).strip()
