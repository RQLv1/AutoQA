from textwrap import dedent


def build_analysis_prompt(question: str, answer: str, solver_answer: str) -> str:
    return dedent(
        f"""
        下述单选题已被求解模型答出，请总结题目为何仍然简单，并给出提高难度的3条建议。
        题目: {question}
        标准答案: {answer}
        求解模型作答: {solver_answer}

        输出格式:
        - 用简洁中文列出3条提高难度的指引。
        - 不要重复题面原句。
        """
    ).strip()

