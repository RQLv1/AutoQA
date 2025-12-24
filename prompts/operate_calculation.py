from textwrap import dedent

from utils.schema import StepResult


def build_operate_calculation_prompt(
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
        你是计算智能体。你的任务不是出题，而是为“下一步子问题”生成一个可执行的修改草稿(draft)，
        让出题智能体据此生成一个更难、且必须依赖图片中心视觉证据的单选题。

        上一步子问题与答案(供你理解推理链):
        - question: {previous_step.question}
        - answer_letter: {previous_step.answer_letter}
        - answer_text: {previous_step.answer_text}

        下一步必须使用的新关键信息(供你设计草稿用，不要直接复制进题干):
        {fact_hint}

        约束:
        - 本草稿必须以“条件计算”为核心：
          参考信息给出公式/数据/阈值；题干要求结合图中参数/关系进行计算或条件推断（选项为数值/区间/等级）。
        - {cross_modal}
        - 只描述“下一步要怎么问/怎么设选项/依赖哪些视觉证据”，不要直接生成完整题干。
        - 必须给出可入题干的短句 short_rule_for_stem：仅1-2句自然语言，不要标题/编号/公式墙/指令式引导。
          若存在链式关系，先化简成一条等价表达再写入。
        - 必须在两种逻辑模板中二选一来组织计算：
          1) 双源合成：提取图中读数 X + 参考信息系数/阈值 Y，通过计算得到结论（如 X*Y、对照阈值分级）。
          2) 条件分支：参考信息给出分支条件（如 温度>50 用规则A 否则B），通过视觉观察选择分支后再计算/判级。
        - 草稿尽量具体到可执行的计算：指出图中可读的参数/关系、引用的阈值/公式、计算步骤、最终应落到的正确数值/区间/等级。
        - 选项设计必须是数值/区间/等级：给出 1 个正确值 + 3 个易混淆干扰（单位/换算/阈值边界/读图误差），且干扰项尽量来自参考信息中的同类真实条件（Hard Negatives）。
        - 若涉及读图误差/四舍五入：在草稿中明确“保留几位/向上或向下取整/允许误差带”。
        - 去词汇化：不要在草稿中直接写出图中读数/颜色等具体值，改用“图中仪表/曲线/标注的读数 X”“图中装置当前显示的状态”等占位描述，迫使下一步必须看图。
        - 草稿中不得出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”等字样。
        {forbidden_note}
        {extra}

        参考信息(仅供内部推理):
        {context.strip()}

        只输出以下格式(不要输出其他内容):
        <draft>
        internal_chain:
        - 视觉证据：图中哪些数字/刻度/相对关系/计数可用于计算？
        - 参考信息：使用哪条公式/阈值/表格数据？（可概括，不要原文整段复制）
        - 计算：列出关键步骤，给出正确结果（带单位/区间/等级），并说明取整/误差规则
        short_rule_for_stem:
        给出1-2句自然语言规则（不提来源，不要标题/编号/步骤指令）
        options:
        - A-D 候选（数值/区间/等级），其中 3 个为 Hard Negatives（边界、单位换算错、读图错等）
        </draft>
        """
    ).strip()
