from textwrap import dedent

from utils.schema import StepResult


def build_stage1_step_prompt(context: str, feedback: str, previous_question: str | None) -> str:
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
        <answer_letter>A/B/C/D</answer_letter>
        <answer_text>正确选项对应的短实体/短短语(不超过12字)</answer_text>
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
        答案字母: {previous_step.answer_letter}
        答案短语: {previous_step.answer_text}

        现在生成第2步子问题(单选题)，需在视觉锚点基础上引入新的文档关键点形成推理。
        - 新问题必须使用新的文档关键点: {fact_hint}
        - {cross_modal}
        - 题干包含 A-D 选项，答案可在文档中定位。
        {extra}

        文档内容:
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer_letter>A/B/C/D</answer_letter>
        <answer_text>正确选项对应的短实体/短短语(不超过12字)</answer_text>
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
        答案字母: {previous_step.answer_letter}
        答案短语: {previous_step.answer_text}
        {extra}

        现在生成第3步子问题(单选题)，继续引入新的文档关键点形成更深推理。
        - 新问题必须使用新的文档关键点: {fact_hint}
        - {cross_modal}
        - 题干包含 A-D 选项，答案可在文档中定位。

        文档内容:
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer_letter>A/B/C/D</answer_letter>
        <answer_text>正确选项对应的短实体/短短语(不超过12字)</answer_text>
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
        答案字母: {previous_step.answer_letter}
        答案短语: {previous_step.answer_text}

        请继续扩链生成新的子问题(单选题)，要求:
        - 使用新的文档关键点或新的视觉关系: {fact_hint}
        - {cross_modal}
        - 题干包含 A-D 选项，答案可在文档中定位。
        {extra}

        文档内容:
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer_letter>A/B/C/D</answer_letter>
        <answer_text>正确选项对应的短实体/短短语(不超过12字)</answer_text>
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
        原答案字母: {step.answer_letter}
        原答案短语: {step.answer_text}
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
        <answer_letter>A/B/C/D</answer_letter>
        <answer_text>正确选项对应的短实体/短短语(不超过12字)</answer_text>
        <evidence>{{"doc_spans": ["L12-L18"], "image_regions": ["中心区域..."]}}</evidence>
        <modal_use>image/text/both</modal_use>
        <cross_modal_bridge>true/false</cross_modal_bridge>
        """
    ).strip()


def build_graph_1hop_step_prompt(
    *,
    anchor_question: str,
    chunk_id: int,
    chunk_text: str,
    head: str,
    relation: str,
    tail: str,
    distractor_entities: list[str],
    feedback: str,
    force_cross_modal: bool,
) -> str:
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    cross_modal = "必须跨模态桥接(同时依赖图与文)。" if force_cross_modal else "可以跨模态桥接。"
    distractors = ", ".join(distractor_entities[:12]) if distractor_entities else "(由你生成)"
    return dedent(
        f"""
        你需要基于“本地知识图谱”的一条边生成 1-hop 子问题(单选题)。
        该子问题用于后续 reverse-chaining 合成多跳题，因此必须满足：
        - 只凭文档 chunk 的证据就能确定正确选项，同时仍需结合图片中心视觉锚点避免纯文本捷径。
        - 题干中不要出现正确答案 head（包括同义词/缩写）。
        - {cross_modal}

        图片视觉锚点参考(来自 step_0 题目，请沿用其中心区域锚点语境):
        {anchor_question.strip()}

        当前 hop 的结构化证据:
        - chunk_id: {chunk_id}
        - chunk_text(仅供你生成题目，不要原样复制进题干):
        {chunk_text.strip()}
        - triple: head={head} ; relation={relation} ; tail={tail}
        - 可用干扰实体候选(不含 head): {distractors}
        {extra}

        输出要求:
        - 生成 4 个选项 A-D，其中正确选项对应 head，其他 3 个为同类干扰项。
        - answer_text 必须等于 head（短实体/短短语）。
        - evidence 必须包含 chunk_id，并给出可验证片段说明。

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer_letter>A/B/C/D</answer_letter>
        <answer_text>{head}</answer_text>
        <evidence>{{"chunk_id": {chunk_id}, "doc_spans": ["chunk:{chunk_id}"], "snippet": "...", "image_regions": ["中心区域..."]}}</evidence>
        <modal_use>image/text/both</modal_use>
        <cross_modal_bridge>true/false</cross_modal_bridge>
        """
    ).strip()
