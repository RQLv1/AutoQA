from textwrap import dedent, indent

from utils.schema import StepResult


def build_stage1_step_prompt(context: str, feedback: str, previous_question: str | None) -> str:
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    previous = f"\n上一轮最终问题: {previous_question.strip()}" if previous_question else ""
    return dedent(
        f"""
        你需要围绕图片“中心区域”的视觉锚点，生成一个多跳题的第1步子问题(单选题)。
        要求:
        - 题干包含 A-D 四个选项。
        - 题干必须围绕图片中心视觉锚点，不得引导读者查阅文档/文献。
        - 题干中禁止出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”等字样。
        {extra}{previous}

        参考信息(仅供内部推理，不得在题干中提到):
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>A/B/C/D</answer>
        """
    ).strip()


def build_stage2_step_prompt(
    context: str,
    previous_step: StepResult,
    fact_hint: str,
    operate_distinction_draft: str,
    operate_calculation_draft: str,
    feedback: str,
    force_cross_modal: bool,
) -> str:
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    cross_modal = "必须跨模态桥接(同时依赖图片与参考信息)。" if force_cross_modal else "可以跨模态桥接。"
    operate_distinction_block = indent((operate_distinction_draft.strip() or "(empty)"), "          ")
    operate_calculation_block = indent((operate_calculation_draft.strip() or "(empty)"), "          ")
    return dedent(
        f"""
        这是上一步的子问题与答案:
        问题: {previous_step.question}
        答案字母: {previous_step.answer_letter}
        答案短语: {previous_step.answer_text}

        现在生成第2步子问题(单选题)，需在视觉锚点基础上引入新的关键信息形成推理。
        - 新问题必须使用新的关键信息: {fact_hint}
        - operate_distinction 智能体草稿(仅供内部推理，不得在题干中提到):
          - draft:
{operate_distinction_block}
        - operate_calculation 智能体草稿(仅供内部推理，不得在题干中提到):
          - draft:
{operate_calculation_block}
        - {cross_modal}
        - 题干包含 A-D 选项，答案需可验证。
        - 题干必须围绕图片中心视觉锚点，禁止出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”等字样。
        - 去词汇化(避免文本捷径)：题干不要直接写出图中读数/颜色/形状等具体值，改用“图中…的读数/显示的状态/位于…的部件”等指代性或位置性描述，迫使读者看图。
        - 禁止“纯实体匹配/纯定义检索”题（例如“X 是什么/哪个是 X/下列哪项描述正确”但不依赖图像细节）。
        - 难度算子要求（不要在题干中写出算子名）：
          - 风格偏向条件计算：优先采用 operate_calculation 草稿落地为“数值/区间/等级”可验证题。
          - 若确实无法形成可验证计算（例如图中无可读参数/关系），再退化为 operate_distinction；仍不适用再用异常检测（找流程缺失/冲突）。
        - 条件计算题必须在两种逻辑模板中二选一：
          1) 双源合成(Synthesis)：视觉读数 X + 参考信息参数 Y → 计算/判级。
          2) 条件分支(Branching)：视觉观察选择分支规则 → 再计算/判级。
        - 干扰项必须是参考信息中出现过的同类真实概念/实体/条件，但在当前图像语境下为错误（Hard Negatives）。
        {extra}

        参考信息(仅供内部推理，不得在题干中提到):
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>A/B/C/D</answer>
        """
    ).strip()


def build_stage3_step_prompt(
    context: str,
    previous_step: StepResult,
    fact_hint: str,
    operate_distinction_draft: str,
    operate_calculation_draft: str,
    feedback: str,
    force_cross_modal: bool,
) -> str:
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    cross_modal = "必须跨模态桥接(同时依赖图片与参考信息)。" if force_cross_modal else "可以跨模态桥接。"
    operate_distinction_block = indent((operate_distinction_draft.strip() or "(empty)"), "          ")
    operate_calculation_block = indent((operate_calculation_draft.strip() or "(empty)"), "          ")
    return dedent(
        f"""
        这是上一步的子问题与答案:
        问题: {previous_step.question}
        答案字母: {previous_step.answer_letter}
        答案短语: {previous_step.answer_text}
        {extra}

        现在生成第3步子问题(单选题)，继续引入新的关键信息形成更深推理。
        - 新问题必须使用新的关键信息: {fact_hint}
        - operate_distinction 智能体草稿(仅供内部推理，不得在题干中提到):
          - draft:
{operate_distinction_block}
        - operate_calculation 智能体草稿(仅供内部推理，不得在题干中提到):
          - draft:
{operate_calculation_block}
        - {cross_modal}
        - 题干包含 A-D 选项，答案需可验证。
        - 题干必须围绕图片中心视觉锚点，禁止出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”等字样。
        - 去词汇化(避免文本捷径)：题干不要直接写出图中读数/颜色/形状等具体值，改用“图中…的读数/显示的状态/位于…的部件”等指代性或位置性描述，迫使读者看图。
        - 禁止“纯实体匹配/纯定义检索”题（例如“X 是什么/哪个是 X/下列哪项描述正确”但不依赖图像细节）。
        - 难度算子要求（不要在题干中写出算子名）：
          - 风格偏向条件计算：优先采用 operate_calculation 草稿落地为“数值/区间/等级”可验证题。
          - 若确实无法形成可验证计算（例如图中无可读参数/关系），再退化为 operate_distinction；仍不适用再用异常检测（找流程缺失/冲突）。
        - 条件计算题必须在两种逻辑模板中二选一：
          1) 双源合成(Synthesis)：视觉读数 X + 参考信息参数 Y → 计算/判级。
          2) 条件分支(Branching)：视觉观察选择分支规则 → 再计算/判级。
        - 干扰项必须是参考信息中出现过的同类真实概念/实体/条件，但在当前图像语境下为错误（Hard Negatives）。

        参考信息(仅供内部推理，不得在题干中提到):
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>A/B/C/D</answer>
        """
    ).strip()


def build_extend_step_prompt(
    context: str,
    previous_step: StepResult,
    fact_hint: str,
    operate_distinction_draft: str,
    operate_calculation_draft: str,
    feedback: str,
    force_cross_modal: bool,
) -> str:
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    cross_modal = "必须跨模态桥接(同时依赖图片与参考信息)。" if force_cross_modal else "可以跨模态桥接。"
    operate_distinction_block = indent((operate_distinction_draft.strip() or "(empty)"), "          ")
    operate_calculation_block = indent((operate_calculation_draft.strip() or "(empty)"), "          ")
    return dedent(
        f"""
        这是上一步的子问题与答案:
        问题: {previous_step.question}
        答案字母: {previous_step.answer_letter}
        答案短语: {previous_step.answer_text}

        请继续扩链生成新的子问题(单选题)，要求:
        - 使用新的关键信息或新的视觉关系: {fact_hint}
        - operate_distinction 智能体草稿(仅供内部推理，不得在题干中提到):
          - draft:
{operate_distinction_block}
        - operate_calculation 智能体草稿(仅供内部推理，不得在题干中提到):
          - draft:
{operate_calculation_block}
        - {cross_modal}
        - 题干包含 A-D 选项，答案需可验证。
        - 题干必须围绕图片中心视觉锚点，禁止出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”等字样。
        - 禁止“纯实体匹配/纯定义检索”题；必须以 operate_distinction / operate_calculation 或异常检测为核心。
        - 风格偏向条件计算：优先输出“数值/区间/等级”型选项（与图中参数/关系 + 参考信息阈值/公式绑定）。
        - 去词汇化(避免文本捷径)：题干不要直接写出图中读数/颜色/形状等具体值，改用“图中…的读数/显示的状态/位于…的部件”等指代性或位置性描述，迫使读者看图。
        - 条件计算题必须在两种逻辑模板中二选一：
          1) 双源合成(Synthesis)：视觉读数 X + 参考信息参数 Y → 计算/判级。
          2) 条件分支(Branching)：视觉观察选择分支规则 → 再计算/判级。
        - 干扰项必须是参考信息中出现过的同类真实概念/实体/条件，但在当前图像语境下为错误（Hard Negatives）。
        {extra}

        参考信息(仅供内部推理，不得在题干中提到):
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>A/B/C/D</answer>
        """
    ).strip()


def build_revise_prompt(
    context: str,
    step: StepResult,
    reason: str,
    fact_hint: str,
    operate_distinction_draft: str | None,
    operate_calculation_draft: str | None,
    force_cross_modal: bool,
) -> str:
    cross_modal = "必须跨模态桥接(同时依赖图片与参考信息)。" if force_cross_modal else "可以跨模态桥接。"
    operate_distinction_block = indent((operate_distinction_draft or "").strip() or "(empty)", "      ")
    operate_calculation_block = indent((operate_calculation_draft or "").strip() or "(empty)", "      ")
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
        - 使用新的关键信息或明确证据: {fact_hint}
        - operate_distinction 草稿(仅供内部推理，不得在题干中提到):
          - draft:
{operate_distinction_block}
        - operate_calculation 草稿(仅供内部推理，不得在题干中提到):
          - draft:
{operate_calculation_block}
        - 题干包含 A-D 选项，答案唯一且可验证。
        - 题干必须围绕图片中心视觉锚点，禁止出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”等字样。
        - 禁止“纯实体匹配/纯定义检索”题；必须以对比/计算/异常检测中的至少一种为核心。
        - 风格偏向条件计算：优先输出“数值/区间/等级”型选项（与图中参数/关系 + 参考信息阈值/公式绑定）。
        - 去词汇化(避免文本捷径)：把题干中对视觉特征的直接描述（颜色/形状/状态/直接读数）改为指代或位置描述（如“图中仪表盘读数”“图中装置当前显示的颜色”）。
        - 干扰项必须是参考信息中出现过的同类真实概念/实体/条件，但在当前图像语境下为错误（Hard Negatives）。

        参考信息(仅供内部推理，不得在题干中提到):
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>A/B/C/D</answer>
        """
    ).strip()


def build_graph_1hop_step_prompt(
    *,
    anchor_question: str,
    evidence_snippet: str,
    head: str,
    relation: str,
    tail: str,
    operate_distinction_draft: str,
    operate_calculation_draft: str,
    distractor_entities: list[str],
    feedback: str,
    force_cross_modal: bool,
) -> str:
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    cross_modal = "必须跨模态桥接(同时依赖图片与参考信息)。" if force_cross_modal else "可以跨模态桥接。"
    distractors = ", ".join(distractor_entities[:12]) if distractor_entities else "(由你生成)"
    operate_distinction_block = indent((operate_distinction_draft.strip() or "(empty)"), "        ")
    operate_calculation_block = indent((operate_calculation_draft.strip() or "(empty)"), "        ")
    return dedent(
        f"""
        你需要基于“本地知识点链”的一条关联生成 1-hop 子问题(单选题)。
        该子问题用于后续 reverse-chaining 合成多跳题，因此必须满足：
        - 证据来自参考信息，但题干必须围绕图片中心视觉锚点，避免纯文本捷径。
        - 题干中不要出现正确答案 head（包括同义词/缩写）。
        - {cross_modal}
        - 题干中禁止出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”等字样。

        图片视觉锚点参考(来自 step_0 题目，请沿用其中心区域锚点语境):
        {anchor_question.strip()}

        当前 hop 的结构化证据(仅供内部推理，不要原样复制进题干):
        - evidence_snippet(仅供你生成题目，不要原样复制进题干):
        {evidence_snippet.strip() or "(未提供)"}
        - knowledge_link: head={head} ; relation={relation} ; tail={tail}
        - operate_distinction 智能体草稿(仅供内部推理，不得在题干中提到):
          - draft:
{operate_distinction_block}
        - operate_calculation 智能体草稿(仅供内部推理，不得在题干中提到):
          - draft:
{operate_calculation_block}
        - 可用干扰实体候选(不含 head): {distractors}
        {extra}

        输出要求:
        - 生成 4 个选项 A-D，其中正确选项对应 head，其他 3 个为同类干扰项。
        - 题干避免泄露 head，确保答案唯一可验证。
        - 难度算子要求（不要在题干中写出算子名）：
          - 风格偏向条件计算：优先采用 operate_calculation 草稿落地为“数值/区间/等级”可验证题。
          - 若确实无法形成可验证计算，再退化为 operate_distinction；仍不适用再用异常检测（找流程缺失/冲突）。
        - 去词汇化(避免文本捷径)：题干不要直接写出图中读数/颜色/形状等具体值，改用“图中…的读数/显示的状态/位于…的部件”等指代性或位置性描述。

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>A/B/C/D</answer>
        """
    ).strip()
