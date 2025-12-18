from textwrap import dedent

from schema import StepResult


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


def build_stage1_step_prompt(
    context: str, feedback: str, previous_question: str | None
) -> str:
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    previous = f"\n上一轮最终问题: {previous_question.strip()}" if previous_question else ""
    return dedent(
        f"""
        你需要围绕图片“中心区域”的视觉锚点，生成一个多跳题的第1步子问题(单选题)。
        要求:
        - 题干包含 A-D 四个选项。
        - 题干必须首先依赖图片中心视觉锚点，必要时可结合文档。
        - 输出 evidence(JSON)，包含 doc_spans 与 image_regions。
        - modal_use 只能是 image/text/both。
        - cross_modal_bridge 表示是否必须同时使用图文。
        {extra}{previous}

        文档内容:
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>正确选项字母，并用10-20字解释</answer>
        <evidence>{{"doc_spans": ["L12-L18"], "image_regions": ["中心区域..."]}}</evidence>
        <modal_use>image/text/both</modal_use>
        <cross_modal_bridge>true/false</cross_modal_bridge>
        """
    ).strip()


def build_stage2_step_prompt(
    context: str,
    previous_step: StepResult,
    fact_hint: str,
    feedback: str,
    force_cross_modal: bool,
) -> str:
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    cross_modal = "必须跨模态桥接(同时依赖图与文)。" if force_cross_modal else "可以跨模态桥接。"
    return dedent(
        f"""
        这是上一步的子问题与答案:
        问题: {previous_step.question}
        答案: {previous_step.answer}

        现在生成第2步子问题(单选题)，需在视觉锚点基础上引入新的文档关键点形成推理。
        - 新问题必须使用新的文档关键点: {fact_hint}
        - {cross_modal}
        - 题干包含 A-D 选项，答案可在文档中定位。
        {extra}

        文档内容:
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>正确选项字母，并用10-20字解释</answer>
        <evidence>{{"doc_spans": ["L12-L18"], "image_regions": ["中心区域..."]}}</evidence>
        <modal_use>image/text/both</modal_use>
        <cross_modal_bridge>true/false</cross_modal_bridge>
        """
    ).strip()


def build_stage3_step_prompt(
    context: str,
    previous_step: StepResult,
    fact_hint: str,
    feedback: str,
    force_cross_modal: bool,
) -> str:
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    cross_modal = "必须跨模态桥接(同时依赖图与文)。" if force_cross_modal else "可以跨模态桥接。"
    return dedent(
        f"""
        这是上一步的子问题与答案:
        问题: {previous_step.question}
        答案: {previous_step.answer}

        现在生成第3步子问题(单选题)，继续引入新的文档关键点形成更深推理。
        - 新问题必须使用新的文档关键点: {fact_hint}
        - {cross_modal}
        - 题干包含 A-D 选项，答案可在文档中定位。
        {extra}

        文档内容:
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>正确选项字母，并用10-20字解释</answer>
        <evidence>{{"doc_spans": ["L12-L18"], "image_regions": ["中心区域..."]}}</evidence>
        <modal_use>image/text/both</modal_use>
        <cross_modal_bridge>true/false</cross_modal_bridge>
        """
    ).strip()


def build_extend_step_prompt(
    context: str,
    previous_step: StepResult,
    fact_hint: str,
    feedback: str,
    force_cross_modal: bool,
) -> str:
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    cross_modal = "必须跨模态桥接(同时依赖图与文)。" if force_cross_modal else "可以跨模态桥接。"
    return dedent(
        f"""
        这是上一步的子问题与答案:
        问题: {previous_step.question}
        答案: {previous_step.answer}

        请继续扩链生成新的子问题(单选题)，要求:
        - 使用新的文档关键点或新的视觉关系: {fact_hint}
        - {cross_modal}
        - 题干包含 A-D 选项，答案可在文档中定位。
        {extra}

        文档内容:
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>正确选项字母，并用10-20字解释</answer>
        <evidence>{{"doc_spans": ["L12-L18"], "image_regions": ["中心区域..."]}}</evidence>
        <modal_use>image/text/both</modal_use>
        <cross_modal_bridge>true/false</cross_modal_bridge>
        """
    ).strip()


def build_revise_prompt(
    context: str,
    step: StepResult,
    reason: str,
    fact_hint: str,
    force_cross_modal: bool,
) -> str:
    cross_modal = "必须跨模态桥接(同时依赖图与文)。" if force_cross_modal else "可以跨模态桥接。"
    return dedent(
        f"""
        需要修订以下子问题(单选题)，原因: {reason}
        原问题: {step.question}
        原答案: {step.answer}
        原 evidence: {step.evidence}
        原 modal_use: {step.modal_use}
        原 cross_modal_bridge: {step.cross_modal_bridge}

        修订要求:
        - {cross_modal}
        - 使用新的文档关键点或明确证据: {fact_hint}
        - 题干包含 A-D 选项，答案唯一且可验证。

        文档内容:
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>正确选项字母，并用10-20字解释</answer>
        <evidence>{{"doc_spans": ["L12-L18"], "image_regions": ["中心区域..."]}}</evidence>
        <modal_use>image/text/both</modal_use>
        <cross_modal_bridge>true/false</cross_modal_bridge>
        """
    ).strip()


def build_final_compress_prompt(context: str, steps: list[StepResult], feedback: str) -> str:
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    step_lines = []
    for step in steps:
        step_lines.append(
            f"- Step {step.k}: Q={step.question} | A={step.answer} | evidence={step.evidence}"
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


def build_solver_prompt(context: str, question: str) -> str:
    return dedent(
        f"""
        你是一名考生，请结合图片和文档作答单选题。
        严格只输出以下格式，禁止解释或追加其他内容:
        <answer>A</answer>

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
