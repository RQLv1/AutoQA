from textwrap import dedent, indent

from utils.schema import StepResult


def _format_feedback_block(feedback: str) -> str:
    if not feedback:
        return ""
    return f"""
    [必须执行的修正指令]
    上一轮生成的题目因质量不达标被拒绝。
    拒绝原因(Feedback): {feedback.strip()}

    修正要求:
    1. 如果反馈指出"太简单"或"逻辑线性": 你必须引入干扰项、增加计算步骤(如先求参数再代入)、或移除题干中的直接判断阈值。
    2. 如果反馈指出"直接给出了判据": 必须将直接的数值判据(如"大于X则为Y")改为需要从图表趋势中分析，或改为定性描述。
    3. 你生成的题目必须与上述"拒绝原因"形成鲜明对比。
    """.strip()


def _format_visual_summary_block(visual_summary: str | None) -> str:
    if not visual_summary:
        return ""
    return f"""
    [图片详细文本描述摘要 / Visual Summary]
    {visual_summary.strip()}
    (仅供辅助理解，题干仍需依赖图片视觉证据)
    """.strip()


def build_stage1_step_prompt(
    context: str,
    feedback: str,
    previous_question: str | None,
    visual_summary: str | None = None,
) -> str:
    feedback_block = _format_feedback_block(feedback)
    visual_block = _format_visual_summary_block(visual_summary)
    previous = f"\n上一轮最终问题: {previous_question.strip()}" if previous_question else ""
    return dedent(
        f"""
        {feedback_block}
        {visual_block}

        你需要围绕图片“中心区域”的视觉锚点，生成一个多跳题的第1步子问题(单选题)。
        要求:
        - 题干包含 A-D 四个选项。
        - 选项格式建议每个选项单独一行：A. ... / B. ... / C. ... / D. ...
        - 题干必须围绕图片中心视觉锚点，不得引导读者查阅文档/文献。
        - 题干中禁止出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”等字样。
        - 风格硬约束：
          - 题干正文不得出现“【】”以及“已知条件/判据/任务说明/提示/步骤/解题思路”等词。
          - 不得使用(1)(2)(3)或“先…再…”等指令式引导。
          - 题干必须为一个连续自然段（A-D选项可换行），不得出现分节标题。
        - 信息约束：
          - 题干中最多写1-2句规则/阈值/定义；若存在链式定义(A->B->C)，必须先化简成等价的一条表达再写入。
          - 分级阈值表默认不写入题干；若必须提及等级，只允许写“按文中等级阈值划分”这一句。
        {previous}

        参考信息(仅供内部推理；题干只保留必要规则与读图对象，最多1-2句规则):
        {context.strip()}

        只输出以下格式:
        <question>
        题干描述（作为连续自然段）。
        A. 选项内容
        B. 选项内容
        C. 选项内容
        D. 选项内容
        </question>
        <answer>A/B/C/D</answer>
        <reasoning>简要推理过程(不超过4句)</reasoning>
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
    visual_summary: str | None = None,
) -> str:
    feedback_block = _format_feedback_block(feedback)
    visual_block = _format_visual_summary_block(visual_summary)
    cross_modal = "必须跨模态桥接(同时依赖图片与参考信息)。" if force_cross_modal else "可以跨模态桥接。"
    operate_distinction_block = indent((operate_distinction_draft.strip() or "(empty)"), "          ")
    operate_calculation_block = indent((operate_calculation_draft.strip() or "(empty)"), "          ")
    return dedent(
        f"""
        {feedback_block}
        {visual_block}

        这是上一步的子问题与答案:
        问题: {previous_step.question}
        答案字母: {previous_step.answer_letter}
        答案短语: {previous_step.answer_text}

        现在生成第2步子问题(单选题)，需在视觉锚点基础上引入新的关键信息形成推理。
        - 新问题必须使用新的关键信息: {fact_hint}
        - operate_distinction 智能体草稿(仅供内部推理，不得在题干中提到):
          - draft:
{operate_distinction_block}
        - operate_calculation 智能体草稿(仅供内部推理):
          - draft:
{operate_calculation_block}
        - 题干规则只能采用 operate_calculation 草稿中的 short_rule_for_stem（可微调措辞），禁止搬运完整公式链条或阈值表。
        - {cross_modal}
        - 题干包含 A-D 选项，答案需可验证。
        - 选项格式建议每个选项单独一行：A. ... / B. ... / C. ... / D. ...
        - 题干必须围绕图片中心视觉锚点，禁止出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”等字样。
        - 风格硬约束：
          - 题干正文不得出现“【】”以及“已知条件/判据/任务说明/提示/步骤/解题思路”等词。
          - 不得使用(1)(2)(3)或“先…再…”等指令式引导。
          - 题干必须为一个连续自然段（A-D选项可换行），不得出现分节标题。
        - 信息约束：
          - 题干中最多写1-2句规则/阈值/定义；若存在链式定义(A->B->C)，必须先化简成等价的一条表达再写入。
          - 分级阈值表默认不写入题干；若必须提及等级，只允许写“按文中等级阈值划分”这一句。
        - 去词汇化(避免文本捷径)：题干不要直接写出图中读数/颜色/形状等具体值，改用“图中…的读数/显示的状态/位于…的部件”等指代性或位置性描述，迫使读者看图。
        - 去词汇化仅针对图上读数/视觉结果，不限制写入中性规则(阈值/公式/单位换算)。
        - 选项泄露禁令：
          - A-D 选项只允许输出“数值/区间/等级标签”（长度≤12字），不得附带原因、现象、分布描述或任何与图像特征对应的解释；
          - 禁止出现“高度重合/明显分离/只在外圈/几乎只在背景”等可被直接图像匹配的词。
        - 可核验视觉量化：
          - 若题材是元素点映射/点云分布，必须使用可计数/可网格估算的量化证据（如：指定ROI内点数比、内外环点数比、四象限计数、网格覆盖格数）；
          - 禁止仅凭“重合程度/略富集/看起来更密集”这类主观描述来定义比例或指标。
        - 来源约束：
          - 不得新增任何未在 reference/context/steps evidence 中出现的变量定义、经验关系或阈值；
          - 若参考信息不足以支撑计算题，必须改写为“读图可核验的计数/比较/排序”型问题，而不是自造公式。
        - 同质且近邻：
          - 四个数值选项必须同单位、同小数位；
          - 最大值/最小值 ≤ 1.25（或差值不超过正确值的±15%），避免跨度过大导致秒选。
        - 禁止“纯实体匹配/纯定义检索”题（例如“X 是什么/哪个是 X/下列哪项描述正确”但不依赖图像细节）。
        - 难度算子要求（不要在题干中写出算子名）：
          - 风格偏向条件计算：优先采用 operate_calculation 草稿落地为“数值/区间/等级”可验证题。
          - 针对反馈优化：若反馈提到"太简单"，请尝试"逆向推理"（已知结果求条件）或"多步合成"（A+B->C）。
        - 条件计算题必须在两种逻辑模板中二选一：
          1) 双源合成：视觉读数 X + 参考信息参数 Y → 计算/判级。
          2) 条件分支：视觉观察选择分支规则 → 再计算/判级。
        - 干扰项必须是参考信息中出现过的同类真实概念/实体/条件，但在当前图像语境下为错误（Hard Negatives）。

        参考信息(仅供内部推理；题干只保留必要规则与读图对象，最多1-2句规则):
        {context.strip()}

        只输出以下格式:
        <question>
        题干描述（作为连续自然段）。
        A. 选项内容
        B. 选项内容
        C. 选项内容
        D. 选项内容
        </question>
        <answer>A/B/C/D</answer>
        <reasoning>简要推理过程</reasoning>
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
    visual_summary: str | None = None,
) -> str:
    feedback_block = _format_feedback_block(feedback)
    visual_block = _format_visual_summary_block(visual_summary)
    cross_modal = "必须跨模态桥接(同时依赖图片与参考信息)。" if force_cross_modal else "可以跨模态桥接。"
    operate_distinction_block = indent((operate_distinction_draft.strip() or "(empty)"), "          ")
    operate_calculation_block = indent((operate_calculation_draft.strip() or "(empty)"), "          ")
    return dedent(
        f"""
        {feedback_block}
        {visual_block}

        这是上一步的子问题与答案:
        问题: {previous_step.question}
        答案字母: {previous_step.answer_letter}
        答案短语: {previous_step.answer_text}

        现在生成第3步子问题(单选题)，继续引入新的关键信息形成更深推理。
        - 新问题必须使用新的关键信息: {fact_hint}
        - operate_distinction 智能体草稿(仅供内部推理，不得在题干中提到):
          - draft:
{operate_distinction_block}
        - operate_calculation 智能体草稿(仅供内部推理):
          - draft:
{operate_calculation_block}
        - 题干规则只能采用 operate_calculation 草稿中的 short_rule_for_stem（可微调措辞），禁止搬运完整公式链条或阈值表。
        - {cross_modal}
        - 题干包含 A-D 选项，答案需可验证。
        - 选项格式建议每个选项单独一行：A. ... / B. ... / C. ... / D. ...
        - 题干必须围绕图片中心视觉锚点，禁止出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”等字样。
        - 风格硬约束：
          - 题干正文不得出现“【】”以及“已知条件/判据/任务说明/提示/步骤/解题思路”等词。
          - 不得使用(1)(2)(3)或“先…再…”等指令式引导。
          - 题干必须为一个连续自然段（A-D选项可换行），不得出现分节标题。
        - 信息约束：
          - 题干中最多写1-2句规则/阈值/定义；若存在链式定义(A->B->C)，必须先化简成等价的一条表达再写入。
          - 分级阈值表默认不写入题干；若必须提及等级，只允许写“按文中等级阈值划分”这一句。
        - 去词汇化(避免文本捷径)：题干不要直接写出图中读数/颜色/形状等具体值，改用“图中…的读数/显示的状态/位于…的部件”等指代性或位置性描述，迫使读者看图。
        - 去词汇化仅针对图上读数/视觉结果，不限制写入中性规则(阈值/公式/单位换算)。
        - 选项泄露禁令：
          - A-D 选项只允许输出“数值/区间/等级标签”（长度≤12字），不得附带原因、现象、分布描述或任何与图像特征对应的解释；
          - 禁止出现“高度重合/明显分离/只在外圈/几乎只在背景”等可被直接图像匹配的词。
        - 可核验视觉量化：
          - 若题材是元素点映射/点云分布，必须使用可计数/可网格估算的量化证据（如：指定ROI内点数比、内外环点数比、四象限计数、网格覆盖格数）；
          - 禁止仅凭“重合程度/略富集/看起来更密集”这类主观描述来定义比例或指标。
        - 来源约束：
          - 不得新增任何未在 reference/context/steps evidence 中出现的变量定义、经验关系或阈值；
          - 若参考信息不足以支撑计算题，必须改写为“读图可核验的计数/比较/排序”型问题，而不是自造公式。
        - 同质且近邻：
          - 四个数值选项必须同单位、同小数位；
          - 最大值/最小值 ≤ 1.25（或差值不超过正确值的±15%），避免跨度过大导致秒选。
        - 禁止“纯实体匹配/纯定义检索”题（例如“X 是什么/哪个是 X/下列哪项描述正确”但不依赖图像细节）。
        - 难度算子要求（不要在题干中写出算子名）：
          - 风格偏向条件计算：优先采用 operate_calculation 草稿落地为“数值/区间/等级”可验证题。
          - 针对反馈优化：若反馈提到"太简单"，请尝试"逆向推理"（已知结果求条件）或"多步合成"（A+B->C）。
        - 条件计算题必须在两种逻辑模板中二选一：
          1) 双源合成：视觉读数 X + 参考信息参数 Y → 计算/判级。
          2) 条件分支：视觉观察选择分支规则 → 再计算/判级。
        - 干扰项必须是参考信息中出现过的同类真实概念/实体/条件，但在当前图像语境下为错误。

        参考信息(仅供内部推理；题干只保留必要规则与读图对象，最多1-2句规则):
        {context.strip()}

        只输出以下格式:
        <question>
        题干描述（作为连续自然段）。
        A. 选项内容
        B. 选项内容
        C. 选项内容
        D. 选项内容
        </question>
        <answer>A/B/C/D</answer>
        <reasoning>简要推理过程</reasoning>
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
    visual_summary: str | None = None,
) -> str:
    feedback_block = _format_feedback_block(feedback)
    visual_block = _format_visual_summary_block(visual_summary)
    cross_modal = "必须跨模态桥接(同时依赖图片与参考信息)。" if force_cross_modal else "可以跨模态桥接。"
    operate_distinction_block = indent((operate_distinction_draft.strip() or "(empty)"), "          ")
    operate_calculation_block = indent((operate_calculation_draft.strip() or "(empty)"), "          ")
    return dedent(
        f"""
        {feedback_block}
        {visual_block}

        这是上一步的子问题与答案:
        问题: {previous_step.question}
        答案字母: {previous_step.answer_letter}
        答案短语: {previous_step.answer_text}

        请继续扩链生成新的子问题(单选题)，要求:
        - 使用新的关键信息或新的视觉关系: {fact_hint}
        - operate_distinction 智能体草稿(仅供内部推理，不得在题干中提到):
          - draft:
{operate_distinction_block}
        - operate_calculation 智能体草稿(仅供内部推理):
          - draft:
{operate_calculation_block}
        - 题干规则只能采用 operate_calculation 草稿中的 short_rule_for_stem（可微调措辞），禁止搬运完整公式链条或阈值表。
        - {cross_modal}
        - 题干包含 A-D 选项，答案需可验证。
        - 选项格式建议每个选项单独一行：A. ... / B. ... / C. ... / D. ...
        - 题干必须围绕图片中心视觉锚点，禁止出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”等字样。
        - 风格硬约束：
          - 题干正文不得出现“【】”以及“已知条件/判据/任务说明/提示/步骤/解题思路”等词。
          - 不得使用(1)(2)(3)或“先…再…”等指令式引导。
          - 题干必须为一个连续自然段（A-D选项可换行），不得出现分节标题。
        - 信息约束：
          - 题干中最多写1-2句规则/阈值/定义；若存在链式定义(A->B->C)，必须先化简成等价的一条表达再写入。
          - 分级阈值表默认不写入题干；若必须提及等级，只允许写“按文中等级阈值划分”这一句。
        - 禁止“纯实体匹配/纯定义检索”题；必须以 operate_distinction / operate_calculation 或异常检测为核心。
        - 风格偏向条件计算：优先输出“数值/区间/等级”型选项（与图中参数/关系 + 参考信息阈值/公式绑定）。
        - 去词汇化(避免文本捷径)：题干不要直接写出图中读数/颜色/形状等具体值，改用“图中…的读数/显示的状态/位于…的部件”等指代性或位置性描述，迫使读者看图。
        - 去词汇化仅针对图上读数/视觉结果，不限制写入中性规则(阈值/公式/单位换算)。
        - 条件计算题必须在两种逻辑模板中二选一：
          1) 双源合成：视觉读数 X + 参考信息参数 Y → 计算/判级。
          2) 条件分支：视觉观察选择分支规则 → 再计算/判级。
        - 干扰项必须是参考信息中出现过的同类真实概念/实体/条件，但在当前图像语境下为错误（Hard Negatives）。

        参考信息(仅供内部推理；题干只保留必要规则与读图对象，最多1-2句规则):
        {context.strip()}

        只输出以下格式:
        <question>
        题干描述（作为连续自然段）。
        A. 选项内容
        B. 选项内容
        C. 选项内容
        D. 选项内容
        </question>
        <answer>A/B/C/D</answer>
        <reasoning>简要推理过程</reasoning>
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
    visual_summary: str | None = None,
    extra_requirements: str | None = None,
) -> str:
    # Revise prompt 通常不直接接收外部 feedback (而是接收内部 reason)，
    # 但如果 reason 本身来自 difficulty check，也可以格式化强调。
    cross_modal = "必须跨模态桥接(同时依赖图片与参考信息)。" if force_cross_modal else "可以跨模态桥接。"
    operate_distinction_block = indent((operate_distinction_draft or "").strip() or "(empty)", "      ")
    operate_calculation_block = indent((operate_calculation_draft or "").strip() or "(empty)", "      ")
    visual_block = _format_visual_summary_block(visual_summary)
    extra_block = ""
    if extra_requirements:
        extra_block = "\n        额外要求:\n"
        extra_block += indent(extra_requirements.strip(), "        ")
    return dedent(
        f"""
        [必须执行的修正指令]
        必须修订以下子问题，因为原问题被判定为: {reason}

        原问题: {step.question}
        原答案字母: {step.answer_letter}
        原答案短语: {step.answer_text}
        {visual_block}

        修正要求:
        1. 彻底解决上述判定原因。如果原因是"Low Difficulty"或"Simple Logic"，必须大幅增加推理深度。
        2. 不要只是微调措辞，请重构题目的逻辑路径。
        {extra_block}

        其他要求:
        - {cross_modal}
        - 使用新的关键信息或明确证据: {fact_hint}
        - operate_distinction 草稿(仅供内部推理，不得在题干中提到):
          - draft:
{operate_distinction_block}
        - operate_calculation 草稿(仅供内部推理):
          - draft:
{operate_calculation_block}
        - 题干规则只能采用 operate_calculation 草稿中的 short_rule_for_stem（可微调措辞），禁止搬运完整公式链条或阈值表。
        - 题干包含 A-D 选项，答案唯一且可验证。
        - 选项格式建议每个选项单独一行：A. ... / B. ... / C. ... / D. ...
        - 题干必须围绕图片中心视觉锚点，禁止出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”等字样。
        - 风格硬约束：
          - 题干正文不得出现“【】”以及“已知条件/判据/任务说明/提示/步骤/解题思路”等词。
          - 不得使用(1)(2)(3)或“先…再…”等指令式引导。
          - 题干必须为一个连续自然段（A-D选项可换行），不得出现分节标题。
        - 信息约束：
          - 题干中最多写1-2句规则/阈值/定义；若存在链式定义(A->B->C)，必须先化简成等价的一条表达再写入。
          - 分级阈值表默认不写入题干；若必须提及等级，只允许写“按文中等级阈值划分”这一句。
        - 禁止“纯实体匹配/纯定义检索”题；必须以对比/计算/异常检测中的至少一种为核心。
        - 风格偏向条件计算：优先输出“数值/区间/等级”型选项（与图中参数/关系 + 参考信息阈值/公式绑定）。
        - 去词汇化(避免文本捷径)：把题干中对视觉特征的直接描述（颜色/形状/状态/直接读数）改为指代或位置描述（如“图中仪表盘读数”“图中装置当前显示的颜色”）。
        - 去词汇化仅针对图上读数/视觉结果，不限制写入中性规则(阈值/公式/单位换算)。
        - 干扰项必须是参考信息中出现过的同类真实概念/实体/条件，但在当前图像语境下为错误（Hard Negatives）。

        参考信息(仅供内部推理；题干只保留必要规则与读图对象，最多1-2句规则):
        {context.strip()}

        只输出以下格式:
        <question>
        题干描述（作为连续自然段）。
        A. 选项内容
        B. 选项内容
        C. 选项内容
        D. 选项内容
        </question>
        <answer>A/B/C/D</answer>
        <reasoning>简要推理过程</reasoning>
        """
    ).strip()


def build_graph_1hop_step_prompt(
    *,
    anchor_question: str,
    previous_step: StepResult | None,
    evidence_snippet: str,
    head: str,
    relation: str,
    tail: str,
    target_side: str = "head",
    operate_distinction_draft: str,
    operate_calculation_draft: str,
    distractor_entities: list[str],
    feedback: str,
    force_cross_modal: bool,
    knowledge_source_label: str | None = None,
    knowledge_source_prefix: str | None = None,
    visual_summary: str | None = None,
) -> str:
    feedback_block = _format_feedback_block(feedback)
    visual_block = _format_visual_summary_block(visual_summary)
    cross_modal = "必须跨模态桥接(同时依赖图片与参考信息)。" if force_cross_modal else "可以跨模态桥接。"
    distractors = ", ".join(distractor_entities[:12]) if distractor_entities else "(由你生成)"
    operate_distinction_block = indent((operate_distinction_draft.strip() or "(empty)"), "        ")
    operate_calculation_block = indent((operate_calculation_draft.strip() or "(empty)"), "        ")

    context_bridge = ""
    if previous_step and previous_step.answer_text:
        context_bridge = (
            "\n[逻辑连贯性要求]:\n"
            f"前置推理结论: {previous_step.answer_text}\n"
            "请基于上述前置结论，结合当前图片与新知识点进行更深层提问。\n"
            "例如：'既然(前置结论)成立，那么观察图中...可推断...?'"
        )

    target_concept = head if target_side == "head" else tail
    source_prefix = knowledge_source_prefix or "根据参考信息 (Reference)"
    return dedent(
        f"""
        {feedback_block}
        {visual_block}

        你需要基于“本地知识点链”生成一个 1-hop 子问题(单选题)。
        提示前缀: {source_prefix}。
        {context_bridge}

        当前使用知识链: {head} --[{relation}]--> {tail}
        正确答案必须对应实体: {target_concept}

        要求：
        - 题干包含 A-D 四个选项。
        - 题干中不要直接出现正确答案 {target_concept} (包括同义词)。
        - {cross_modal}
        - 题干中禁止出现“文献”“文档”“context”等字样。
        - 必须围绕图片中心视觉锚点展开，避免纯文本问答。
        - 本步必须是“条件计算题”，不能是概念解释/机制判断/实体匹配。
        - 题干规则只能采用 operate_calculation 草稿中的 short_rule_for_stem（可微调措辞），禁止搬运完整公式链条或阈值表。
        - 风格硬约束：
          - 题干正文不得出现“【】”以及“已知条件/判据/任务说明/提示/步骤/解题思路”等词。
          - 不得使用(1)(2)(3)或“先…再…”等指令式引导。
          - 题干必须为一个连续自然段（A-D选项可换行），不得出现分节标题。
        - 信息约束：
          - 题干中最多写1-2句规则/阈值/定义；若存在链式定义(A->B->C)，必须先化简成等价的一条表达再写入。
          - 分级阈值表默认不写入题干；若必须提及等级，只允许写“按文中等级阈值划分”这一句。
        - 优先使用 operate_calculation draft 作为题干主线，operate_distinction 仅用于构造干扰项或对照条件。
        - 选项必须为数值/区间/等级型答案，且可由“图中读数/关系 + 参考信息阈值/公式”计算或判级得到。
        - 条件计算必须遵循两种模板之一：
          1) 双源合成：图中读数 X + 参考信息参数 Y → 计算/判级；
          2) 条件分支：先由图像选择分支规则 → 再计算/判级。

        图片视觉锚点参考:
        {anchor_question.strip()}

        参考证据(仅供内部推理；题干只保留必要规则与读图对象，最多1-2句规则):
        - 知识来源: {knowledge_source_label or "参考信息"}
        - 参考证据: {evidence_snippet.strip() or "(未提供)"}
        - 区分草稿:
{operate_distinction_block}
        - 计算草稿:
{operate_calculation_block}
        - 可用干扰项候选: {distractors}

        输出要求:
        - 生成 4 个选项 A-D，其中正确选项对应 {target_side} ({target_concept})，其他为干扰项。
        - 视觉防幻觉：只描述图中确实存在的视觉特征。不要编造图中不存在的曲线、图例或读数。
        - 难度递进：必须利用 operate_calculation 将定性描述转化为半定量或逻辑推断题。
        - 针对 Feedback 的特别执行：如果 Feedback 要求隐藏规则或增加前置计算，请务必移除题目中直接给出的判断标准（例如"当X>5时..."），改为更隐性的规则描述。

        只输出以下格式:
        <question>
        题干描述（作为连续自然段）。
        A. 选项内容
        B. 选项内容
        C. 选项内容
        D. 选项内容
        </question>
        <answer>A/B/C/D</answer>
        <reasoning>简要推理过程(不超过4句)</reasoning>
        """
    ).strip()
