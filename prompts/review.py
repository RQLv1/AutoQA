from textwrap import dedent


def build_review_prompt(question: str, answer: str, reasoning: str | None) -> str:
    reasoning_block = reasoning.strip() if reasoning else ""
    return dedent(
        f"""
        你是审稿人，请检查下述单选题的答案是否正确。你会看到图片与题干。

        题目:
        {question}

        标准答案:
        {answer}

        参考推理(可能不完整):
        {reasoning_block}

        请仅输出以下格式:
        <answer>correct/incorrect</answer>
        """
    ).strip()
