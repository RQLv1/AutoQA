from textwrap import dedent

from utils.schema import StepResult


def build_operate_distinction_prompt(
    *,
    context: str,
    previous_step: StepResult,
    fact_hint: str,
    feedback: str,
    force_cross_modal: bool,
    forbidden_terms: list[str] | None = None,
) -> str:
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    cross_modal = "必须跨模态桥接(同时依赖图片与参考信息)。" if force_cross_modal else "可以跨模态桥接。"
    forbidden_note = ""
    forbidden_terms = forbidden_terms or []
    if forbidden_terms:
        forbidden = "，".join(t.strip() for t in forbidden_terms if t and t.strip())
        if forbidden:
            forbidden_note = f"\n- 草稿中不得出现以下词/短语（避免答案泄露）: {forbidden}"
    return dedent(
        f"""
        你是区分智能体。你的任务不是出题，而是为“下一步子问题”生成一个可执行的修改草稿(draft)，
        让出题智能体据此生成一个更难、且必须依赖图片中心视觉证据的单选题。

        上一步子问题与答案(供你理解推理链):
        - 问题: {previous_step.question}
        - 答案: {previous_step.answer_letter}
        - 答案解析: {previous_step.answer_text}

        下一步必须使用的新关键信息(供你设计草稿用，不要直接复制进题干):
        {fact_hint}

        约束:
        - 本草稿必须以“差异对比”为核心：
          参考信息给出相近概念/条件；题干要求根据图中视觉证据区分并推断结论。
        - {cross_modal}
        - 只描述“下一步要怎么问/怎么设选项/依赖哪些视觉证据”，不要直接生成完整题干。
        - 草稿中不得出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”等字样。
        {forbidden_note}
        {extra}

        参考信息(仅供内部推理):
        {context.strip()}

        只输出以下格式(不要输出其他内容):
        <draft>用要点描述：视觉证据→参考信息中的相近概念/条件→区分点→结论与选项设计(含Hard Negatives)</draft>
        """
    ).strip()

