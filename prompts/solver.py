from textwrap import dedent


def _solver_answer_hint(mode: str) -> str:
    if mode == "single_select":
        return "<answer>A/B/C/D</answer>"
    return "<answer>按字母顺序连续输出的正确选项(无空格/逗号，如 ACEF)</answer>"


def _solver_instructions(mode: str, text_only: bool) -> str:
    prefix = (
        "你是一名考生。你看不到图片，只能看到题目文字；请根据题目本身作答"
        if text_only
        else "你是一名考生，请结合图片和题目作答"
    )
    suffix = "单选题" if mode == "single_select" else "多选题，请选择所有正确的选项"
    return f"{prefix}{suffix}。"


def build_solver_prompt(question: str, mode: str = "multi_select") -> str:
    return dedent(
        f"""
        {_solver_instructions(mode, False)}

        题目:
        {question}

        **严格只输出以下格式，禁止解释或追加其他内容，输出中不得出现除该标签外的任何字符:**
        {_solver_answer_hint(mode)}
        """
    ).strip()


def build_solver_prompt_text_only(question: str, mode: str = "multi_select") -> str:
    return dedent(
        f"""
        {_solver_instructions(mode, True)}

        题目:
        {question}

        **严格只输出以下格式，禁止解释或追加其他内容，输出中不得出现除该标签外的任何字符:**
        {_solver_answer_hint(mode)}
        """
    ).strip()


def build_solver_rationale_prompt(question: str, answer: str) -> str:
    return dedent(
        f"""
        你是一名考生，已知正确答案是 {answer}。请用要点说明你为何能从题干与图片中得出该答案。

        要求:
        - 仅输出 3-5 条要点，每条不超过 20 个字。
        - 只写关键依据与必要判断，不要复述题干。
        - 禁止使用“因此/所以/首先/其次/然后/先...再...”等引导语。
        - 不要直接写出图中具体读数或数值。

        题目:
        {question}
        """
    ).strip()
