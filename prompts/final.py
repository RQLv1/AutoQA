from textwrap import dedent

from utils.schema import StepResult


def build_final_compress_prompt(context: str, steps: list[StepResult], feedback: str) -> str:
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    step_lines = []
    for step in steps:
        step_lines.append(
            f"- Step {step.k}: Q={step.question} | answer_text={step.answer_text} | answer_letter={step.answer_letter} | evidence={step.evidence}"
        )
    step_block = "\n".join(step_lines)
    return dedent(
        f"""
        你需要把下述多步推理链压缩成一个高难度单选题(MCQ)。
        要求:
        - 不要显式提“第一步/第二步”，把中间结论隐式化。
        - 题干必须围绕图片中心视觉信息展开，参考信息仅作为隐含依据。
        - 题干包含 A-D 选项，且唯一正确答案。
        - 题干中禁止出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”等字样。
        - 禁止“纯实体匹配/纯定义检索”题；必须以对比/计算/异常检测中的至少一种为核心。
        - 3 个干扰项必须是参考信息/推理链中出现过的同类真实概念/实体/条件，但在当前图像语境下为错误（Hard Negatives），避免明显离谱选项。
        {extra}

        推理链:
        {step_block}

        参考信息(仅供内部推理，不得在题干中提到):
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>正确选项字母，并用10-20字解释</answer>
        """
    ).strip()


def build_final_revise_prompt(context: str, final_question: str, final_answer: str, reason: str) -> str:
    return dedent(
        f"""
        需要修订最终题(单选题)，原因: {reason}
        原题: {final_question}
        原答案: {final_answer}

        修订要求:
        - 避免单模态捷径，推理可隐含使用参考信息，但题干必须围绕图片描述。
        - 题干包含 A-D 选项，且唯一正确答案。
        - 干扰项同类同粒度且合理。
        - 题干中禁止出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”等字样。
        - 干扰项优先从参考信息中挖掘“强负样本”（Hard Negatives），而不是编造无关概念。

        参考信息(仅供内部推理，不得在题干中提到):
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>正确选项字母，并用10-20字解释</answer>
        """
    ).strip()
