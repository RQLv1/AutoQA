from textwrap import dedent

from schema import StageResult


def build_initial_prompt(context: str, feedback: str, previous_question: str | None) -> str:
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    previous = f"\n上一轮最终问题: {previous_question.strip()}" if previous_question else ""
    return dedent(
        f"""
        你需要围绕图片“中心区域”的视觉要素设计一个高难度的单选题（MCQ）。
        请在上一轮最终问题的基础上进行升级或变形，保持题干可由图片与文档推导得到。
        步骤:
        1) 先描述图片中央最关键的结构/现象，并指出它与整体的关系。
        2) 基于该视觉锚点提出题干，题干必须包含 A-D 四个选项。
        3) 正确答案需要在下述文档内容中找到依据，同时必须依赖图片理解而非纯文本记忆。
        {extra}{previous}

        文档内容:
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>正确选项字母，并用10-20字解释</answer>
        """
    ).strip()


def build_revision_prompt(context: str, first: StageResult, feedback: str) -> str:
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    return dedent(
        f"""
        这是第一步生成的问题与答案:
        问题: {first.question}
        答案: {first.answer}

        请继续围绕图片中心视觉锚点，增加一层额外推理，生成更难的单选题:
        - 新题需要在题干中显式提到第一次题目的视觉锚点，然后引入文档中的另一个关键要点形成因果/对比关系。
        - 题干必须包含 A-D 选项，且答案可在文档中找到确切依据。
        {extra}

        文档内容:
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>正确选项字母，并用10-20字解释</answer>
        """
    ).strip()


def build_third_prompt(context: str, second: StageResult, feedback: str) -> str:
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    return dedent(
        f"""
        这是第二步生成的问题与答案:
        问题: {second.question}
        答案: {second.answer}
        {extra}

        请继续围绕图片中心视觉锚点，增加一层额外推理，生成更难的单选题:
        - 新题需要在题干中显式提到第二步题目的视觉锚点，然后引入文档中的另一个关键要点形成因果/对比关系。
        - 题干必须包含 A-D 选项，且答案可在文档中找到确切依据。

        文档内容:
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>正确选项字母，并用10-20字解释</answer>
        """
    ).strip()


def build_final_prompt(
    context: str, first: StageResult, second: StageResult, third: StageResult, feedback: str
) -> str:
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    return dedent(
        f"""
        你需要把前三步的逻辑链路整合成一个“多步推理”的高难度单选题（MCQ），
        要求回答必须先识别图片中心视觉信息，再结合文档内容得出答案。

        前三步结果:
        1) 问题: {first.question}
           答案: {first.answer}
        2) 问题: {second.question}
           答案: {second.answer}
        3) 问题: {third.question}
           答案: {third.answer}
        {extra}

        生成新题的要求:
        - 题干引导考生先定位图片中央的关键结构，再利用文档信息完成多步推理。
        - 选项 A-D 需要设置迷惑项，只有经过多步推理才能排除。
        - 答案需要在文档中找到依据，但必须依赖图片中心信息才能确认。

        文档内容:
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>正确选项字母，并用10-20字解释</answer>
        """
    ).strip()


def build_solver_prompt(context: str, question: str) -> str:
    return dedent(
        f"""
        你是一名考生，请结合图片和文档作答单选题。仅输出选项字母 (A/B/C/D)。

        题目:
        {question}

        文档:
        {context.strip()}
        """
    ).strip()


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
