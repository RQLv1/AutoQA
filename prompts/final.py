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
        - 必须依赖图片中心视觉信息并结合文档完成推理。
        - 题干包含 A-D 选项，且唯一正确答案。
        {extra}

        推理链:
        {step_block}

        文档内容:
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
        - 避免单模态捷径，必须同时依赖图文。
        - 题干包含 A-D 选项，且唯一正确答案。
        - 干扰项同类同粒度且合理。

        文档内容:
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>正确选项字母，并用10-20字解释</answer>
        """
    ).strip()
