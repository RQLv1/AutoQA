from textwrap import dedent

from utils.schema import StepResult


def _final_mode_config(mode: str) -> dict[str, str]:
    multi = mode != "single_select"
    question_type = "多选题(Multiple Select Question)" if multi else "单选题(MCQ)"
    calc_style = "多选题" if multi else "单选题"
    option_instruction = (
        "- 这是多选题，可能有一个或多个正确选项，请在答案中列出全部正确字母（按字母顺序连续输出，无空格/逗号，如 ACEF）。"
        if multi
        else "- 这是单选题，只有一个正确选项，答案写一个字母（如 A）。"
    )
    option_range_rule = (
        "- 选项范围为 A-H，至少4个、最多8个，按顺序排列（如无需使用全部选项，可省略尾部行）。"
        if multi
        else "- 选项范围为 A-D，必须提供 4 个选项。"
    )
    option_leak_rule = (
        "- A-H 选项只允许输出“数值/区间/等级标签”（长度≤12字），不得附带原因、现象、分布描述或任何与图像特征对应的解释；"
        if multi
        else "- A-D 选项只允许输出“数值/区间/等级标签”（长度≤12字），不得附带原因、现象、分布描述或任何与图像特征对应的解释；"
    )
    option_count_rule = (
        "- 选项数量 4-8 个，全部同单位、同小数位；"
        if multi
        else "- 4 个选项单位/小数位/数量级一致；"
    )
    selections_block = (
        """
        <selections>
        A. 选项内容
        B. 选项内容
        C. 选项内容
        D. 选项内容
        E. 选项内容
        F. 选项内容
        G. 选项内容
        H. 选项内容
        </selections>
        """
        if multi
        else """
        <selections>
        A. 选项内容
        B. 选项内容
        C. 选项内容
        D. 选项内容
        </selections>
        """
    ).strip()
    answer_hint = (
        "<answer>正确选项字母(多选需按字母顺序连续输出，无空格/逗号，如 ACEF)</answer>"
        if multi
        else "<answer>正确选项字母(单选，如 A)</answer>"
    )
    return {
        "question_type": question_type,
        "calc_style": calc_style,
        "option_instruction": option_instruction,
        "option_range_rule": option_range_rule,
        "option_leak_rule": option_leak_rule,
        "option_count_rule": option_count_rule,
        "selections_block": selections_block,
        "answer_hint": answer_hint,
    }


def build_final_compress_prompt(
    context: str, steps: list[StepResult], feedback: str, mode: str = "multi_select"
) -> str:
    cfg = _final_mode_config(mode)
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    step_lines = []
    for idx, step in enumerate(steps, start=1):
        step_lines.append(
            f"- Step {idx}: Q={step.question} | answer_text={step.answer_text} | answer_letter={step.answer_letter} | evidence={step.evidence}"
        )
    step_block = "\n".join(step_lines)
    return dedent(
        f"""
        你需要把下述多步推理链压缩成一个高难度{cfg['question_type']}。
        要求:
        - 不要显式提“第一步/第二步”，把中间结论隐式化。
        - 必须“留头留尾”：保留首步视觉锚点线索与末步关键结论/判别依据，中间步骤刻意隐藏，仅以隐含条件/背景融入题干。
        - 题干必须围绕图片中心视觉信息展开，参考信息仅作为隐含依据。
        - 题干中禁止出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”“文中”“原文”“文本内容”“参考信息”等字样，且不得出现图号/图表编号（如“图1”“图2”“图10”“图X”“图表1”“如图X”）。
        - 禁止“纯实体匹配/纯定义检索”题；必须以计算作为核心。
        - 出题风格偏向条件计算：优先生成“数值/区间/等级”型{cfg['calc_style']}。
        - 风格硬约束：
          - 题干正文不得出现“【】”以及“已知条件/判据/任务说明/提示/步骤/解题思路”等词。
          - 不得使用(1)(2)(3)或“先…再…”等指令式引导。
          
        - 信息约束：
          - 题干仅允许包含必要规则（1-2句，最多2句），其余推导与阈值表必须进入参考答案，不得进入题干。
          - 若存在链式定义(A->B->C)，必须先化简成等价的一条表达再写入。
          - 分级阈值表默认不写入题干；若必须提及等级，只允许写“按给定等级阈值划分”这一句。
        - 去词汇化(避免文本捷径)：题干不要直接写出图中读数/颜色/形状等具体值，改用“图中…的读数/显示的状态/位于…的部件”等指代性或位置性描述，迫使读者看图。
        - 如需指代图片中的文字信息，使用“文字/标签/标注/界面文字”等表述，避免“文本内容/文本字符串”。
        - 去词汇化仅针对图上读数/视觉结果，不限制写入中性规则(阈值/公式/单位换算)。
        - 若题干包含“【”或“已知条件/判据/任务说明/步骤/(1)(2)(3)”等任一禁词，或等号“=”超过2个，
          或出现“保留两位小数/代入公式/依次求出”等引导词，必须重写题干并压缩为一个自然段，仅保留必要读图对象与最多2句规则。
        - 题型与选项设置：
          {cfg['option_instruction']}
          {cfg['option_range_rule']}
        - 干扰项生成必须先做“陷阱设计”(仅内部推理，不要输出)：
          1) 单位陷阱：计算正确但单位未换算（如 kW vs W）。
          2) 视觉误读：假设用户看错刻度/位置/颜色导致的错误结果。
          3) 条件误用：假设用户套用了错误的阈值/分支规则导致的错误结果。
          然后把这3个错误路径的结果分别映射为3个错误选项，并确保它们都是参考信息/推理链中出现过的同类真实概念/条件。
        - 选项泄露禁令:
          {cfg['option_leak_rule']}
          - 禁止出现“高度重合/明显分离/只在外圈/几乎只在背景”等可被直接图像匹配的词。
        - 可核验视觉量化：
          - 若题材是元素点映射/点云分布，必须使用可计数/可网格估算的量化证据（如：指定ROI内点数比、内外环点数比、四象限计数、网格覆盖格数）；
          - 禁止仅凭“重合程度/略富集/看起来更密集”这类主观描述来定义比例或指标。
        - 来源约束：
          - 不得新增任何未在 reference/context/steps evidence 中出现的变量定义、经验关系或阈值；
          - 若参考信息不足以支撑计算题，必须改写为“读图可核验的计数/比较/排序”型问题，而不是自造公式。
        - 同质且近邻：
          {cfg['option_count_rule']}
          - 最大值/最小值 ≤ 1.25（或差值不超过正确值的±15%），避免跨度过大导致秒选。
        {extra}

        推理链:
        {step_block}

        参考信息(仅供内部推理；题干只保留必要规则与读图对象，最多1-2句规则):
        {context.strip()}

        只输出以下格式（必须严格遵守，将题干和选项分开）:
        <question>题干描述（作为连续自然段，不包含选项）</question>
        {cfg['selections_block']}
        {cfg['answer_hint']}
        <reasoning>简要推理过程(不超过4句)</reasoning>
        """
    ).strip()


def build_final_revise_prompt(
    context: str, final_question: str, final_answer: str, reason: str, mode: str = "multi_select"
) -> str:
    cfg = _final_mode_config(mode)
    return dedent(
        f"""
        需要修订最终题({cfg['question_type']})，原因: {reason}
        原题: {final_question}
        原答案: {final_answer}

        修订要求:
        {cfg['option_instruction']}
        {cfg['option_range_rule']}
        - 避免单模态捷径，推理可隐含使用参考信息，但题干必须围绕图片描述。
        - 出题风格偏向条件计算：优先生成“数值/区间/等级”型{cfg['calc_style']}。
        - 去词汇化(避免文本捷径)：题干不要直接写出图中读数/颜色/形状等具体值，改用“图中…的读数/显示的状态/位于…的部件”等指代性或位置性描述。
        - 去词汇化仅针对图上读数/视觉结果，不限制写入中性规则(阈值/公式/单位换算)。
        - 干扰项同类同粒度且合理。
        - 题干中禁止出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”“文中”“原文”“文本内容”“参考信息”等字样，且不得出现图号/图表编号（如“图1”“图2”“图10”“图X”“图表1”“如图X”）。
        - 风格硬约束：
          - 题干正文不得出现“【】”以及“已知条件/判据/任务说明/提示/步骤/解题思路”等词。
          - 不得使用(1)(2)(3)或“先…再…”等指令式引导。
          
        - 信息约束：
          - 题干仅允许包含必要规则（1-2句，最多2句），其余推导与阈值表必须进入参考答案，不得进入题干。
          - 若存在链式定义(A->B->C)，必须先化简成等价的一条表达再写入。
          - 分级阈值表默认不写入题干；若必须提及等级，只允许写“按给定等级阈值划分”这一句。
        - 干扰项优先从参考信息中挖掘“强负样本”，而不是编造无关概念。
        - 干扰项必须先做“陷阱设计”(仅内部推理，不要输出)：单位陷阱/视觉误读/条件误用，然后映射为 3 个错误选项。
        - 选项同质性：{cfg['option_count_rule'].split('：')[-1].strip()}
        参考信息(仅供内部推理；题干只保留必要规则与读图对象，最多1-2句规则):
        {context.strip()}

        只输出以下格式（必须严格遵守，将题干和选项分开）:
        <question>题干描述（作为连续自然段，不包含选项）</question>
        {cfg['selections_block']}
        {cfg['answer_hint']}
        <reasoning>简要推理过程(不超过4句)</reasoning>
        """
    ).strip()


def build_final_harden_prompt(
    context: str,
    steps: list[StepResult],
    final_question: str,
    final_answer: str,
    reason: str,
    mode: str = "multi_select",
) -> str:
    cfg = _final_mode_config(mode)
    step_lines = []
    for idx, step in enumerate(steps, start=1):
        step_lines.append(
            f"- Step {idx}: Q={step.question} | answer_text={step.answer_text} | answer_letter={step.answer_letter} | evidence={step.evidence}"
        )
    step_block = "\n".join(step_lines)
    return dedent(
        f"""
        你需要将最终题加难重写，因为检测到: {reason}
        原题: {final_question}
        原答案: {final_answer}

        硬性要求:
        {cfg['option_instruction']}
        {cfg['option_range_rule']}
        - 必须引入一个中间变量（先算再判），并明确两个以上推理步骤。
        - 必须增加一个分支规则（先由图像选择分支，再计算/判级）。
        - 题干必须围绕图片中心视觉锚点，去词汇化仅针对图上读数/视觉结果，不限制写入中性规则(阈值/公式/单位换算)。
        - 选项必须为数值/区间/等级型答案，且单位/数量级一致。
        - 错误选项必须来自三条错误路径：单位换算错 / 读图误读 / 条件误用。
        - 禁止出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”“文中”“原文”“文本内容”“参考信息”等字样，且不得出现图号/图表编号（如“图1”“图2”“图10”“图X”“图表1”“如图X”）。
        - 风格硬约束：
          - 题干正文不得出现“【】”以及“已知条件/判据/任务说明/提示/步骤/解题思路”等词。
          - 不得使用(1)(2)(3)或“先…再…”等指令式引导。
        - 信息约束：
          - 题干仅允许包含必要规则（1-2句，最多2句），其余推导与阈值表必须进入参考答案，不得进入题干。
          - 若存在链式定义(A->B->C)，必须先化简成等价的一条表达再写入。
          - 分级阈值表默认不写入题干；若必须提及等级，只允许写“按给定等级阈值划分”这一句。

        推理链:
        {step_block}

        参考信息(仅供内部推理；题干只保留必要规则与读图对象，最多1-2句规则):
        {context.strip()}

        只输出以下格式（必须严格遵守，将题干和选项分开）:
        <question>题干描述（作为连续自然段，不包含选项）</question>
        {cfg['selections_block']}
        {cfg['answer_hint']}
        <reasoning>简要推理过程(不超过4句)</reasoning>
        """
    ).strip()


def build_final_targeted_revise_prompt(
    context: str,
    steps: list[StepResult],
    final_question: str,
    final_answer: str,
    reason: str,
    feedback: str,
    mode: str = "multi_select",
) -> str:
    cfg = _final_mode_config(mode)
    step_lines = []
    for idx, step in enumerate(steps, start=1):
        step_lines.append(
            f"- Step {idx}: Q={step.question} | answer_text={step.answer_text} | answer_letter={step.answer_letter} | evidence={step.evidence}"
        )
    step_block = "\n".join(step_lines)
    feedback_block = feedback.strip() or "(无补充反馈)"
    return dedent(
        f"""
        你需要对最终题进行针对性改写，因为: {reason}
        原题: {final_question}
        原答案: {final_answer}

        依据的反馈/推理要点:
        {feedback_block}

        强制要求:
        {cfg['option_instruction']}
        {cfg['option_range_rule']}
        - 必须隐藏推理逻辑与引导，不得出现“根据/因此/所以/先...再.../请先/由此可知”等提示语。
        - 题目必须包含至少2步推理（先由图选分支或读关键线索，再计算/判级/比较），但不要明示步骤。
        - 题干必须围绕图片中心视觉锚点，去词汇化仅针对图上读数/视觉结果，不限制写入中性规则(阈值/公式/单位换算)。
        - 选项必须为数值/区间/等级型答案，且单位/数量级一致。
        - 干扰项必须体现三种错误路径：单位换算错 / 读图误读 / 条件误用。
        - 禁止出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”“文中”“原文”“文本内容”“参考信息”等字样，且不得出现图号/图表编号（如“图1”“图2”“图10”“图X”“图表1”“如图X”）。
        - 风格硬约束：
          - 题干正文不得出现“【】”以及“已知条件/判据/任务说明/提示/步骤/解题思路”等词。
          - 不得使用(1)(2)(3)或“先…再…”等指令式引导。
          
        - 信息约束：
          - 题干仅允许包含必要规则（1-2句，最多2句），其余推导与阈值表必须进入参考答案，不得进入题干。
          - 若存在链式定义(A->B->C)，必须先化简成等价的一条表达再写入。
          - 分级阈值表默认不写入题干；若必须提及等级，只允许写“按给定等级阈值划分”这一句。
        - 若反馈指出具体捷径或误导点，必须在新题中彻底移除或改写。

        推理链:
        {step_block}

        参考信息(仅供内部推理；题干只保留必要规则与读图对象，最多1-2句规则):
        {context.strip()}

        只输出以下格式（必须严格遵守，将题干和选项分开）:
        <question>题干描述（作为连续自然段，不包含选项）</question>
        {cfg['selections_block']}
        {cfg['answer_hint']}
        <reasoning>简要推理过程(不超过4句)</reasoning>
        """
    ).strip()
