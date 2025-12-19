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
        - 出题风格偏向条件计算：优先生成“数值/区间/等级”型单选题，并确保答案可由“图中读数/关系 + 题干条件”唯一确定。
        - 去词汇化(避免文本捷径)：题干不要直接写出图中读数/颜色/形状等具体值，改用“图中…的读数/显示的状态/位于…的部件”等指代性或位置性描述，迫使读者看图。
        - 干扰项生成必须先做“陷阱设计(Trap Design)”(仅内部推理，不要输出)：
          1) 单位陷阱：计算正确但单位未换算（如 kW vs W）。
          2) 视觉误读：假设用户看错刻度/位置/颜色导致的错误结果。
          3) 条件误用：假设用户套用了错误的阈值/分支规则导致的错误结果。
          然后把这 3 个错误路径的结果分别映射为选项 B/C/D（或 3 个错误选项），并确保它们都是参考信息/推理链中出现过的同类真实概念/条件（Hard Negatives）。
        - 选项同质性：四个选项的单位/小数位数/数量级尽量一致，避免长度差异过大导致一眼排除。
        {extra}

        推理链:
        {step_block}

        参考信息(仅供内部推理，不得在题干中提到):
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>正确选项字母</answer>
        <reasoning>简要推理过程(不超过4句)</reasoning>
        """
    ).strip()


def build_final_harden_prompt(
    context: str,
    final_question: str,
    final_answer: str,
    attempt: int,
    max_attempts: int,
    mode: str = "calc_first",
) -> str:
    mode_hint = "以计算/量化推理为第一优先级" if mode == "calc_first" else "优先改写为更难的题型"
    return dedent(
        f"""
        需要对最终题进行强制加难改写（第 {attempt}/{max_attempts} 次）。
        原题: {final_question}
        原答案: {final_answer}

        加难要求:
        - 必须重写为“视觉计算/量化推理”单选题，答案可由图像证据计算得到（计数/求和/差值/比例/阈值判断等）。
        - {mode_hint}，不要做轻微改写，必须显著提高难度。
        - 题干必须围绕图片中心视觉信息展开，参考信息仅作为内部推理依据。
        - 题干中禁止出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”等字样。
        - 去词汇化(避免文本捷径)：题干不要直接写出图中读数/颜色/形状等具体值，改用“图中…的读数/显示的状态/位于…的部件”等指代性或位置性描述。
        - 选项 A-D 必须是数字或数值区间，且彼此接近，单位/小数位/数量级尽量一致。
        - 干扰项必须基于“陷阱设计(Trap Design)”(仅内部推理，不要输出)：单位陷阱/视觉误读/条件误用，并将三条错误路径映射为错误选项。
        - 禁止外部知识；不得把参考信息当成唯一证据来源。

        参考信息(仅供内部推理，不得在题干中提到):
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>正确选项字母</answer>
        <reasoning>简要推理过程(不超过4句)</reasoning>
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
        - 出题风格偏向条件计算：优先生成“数值/区间/等级”型单选题。
        - 去词汇化(避免文本捷径)：题干不要直接写出图中读数/颜色/形状等具体值，改用“图中…的读数/显示的状态/位于…的部件”等指代性或位置性描述。
        - 题干包含 A-D 选项，且唯一正确答案。
        - 干扰项同类同粒度且合理。
        - 题干中禁止出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”等字样。
        - 干扰项优先从参考信息中挖掘“强负样本”（Hard Negatives），而不是编造无关概念。
        - 干扰项必须先做“陷阱设计(Trap Design)”(仅内部推理，不要输出)：单位陷阱/视觉误读/条件误用，然后映射为 3 个错误选项。
        - 选项同质性：四个选项的单位/小数位数/数量级尽量一致，避免长度差异过大。

        参考信息(仅供内部推理，不得在题干中提到):
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>正确选项字母</answer>
        <reasoning>简要推理过程(不超过4句)</reasoning>
        """
    ).strip()
