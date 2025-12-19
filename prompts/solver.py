from textwrap import dedent


def build_solver_prompt(question: str) -> str:
    return dedent(
        f"""
        你是一名考生，请结合图片和题目作答单选题。

        题目:
        {question}

        **严格只输出以下格式，禁止解释或追加其他内容，输出中不得出现除该标签外的任何字符:**
        <answer>A/B/C/D</answer>
        """
    ).strip()


def build_solver_prompt_text_only(question: str) -> str:
    return dedent(
        f"""
        你是一名考生。你看不到图片，只能看到题目文字；请根据题目本身作答单选题。

        题目:
        {question}

        **严格只输出以下格式，禁止解释或追加其他内容，输出中不得出现除该标签外的任何字符:**
        <answer>A/B/C/D</answer>
        """
    ).strip()
