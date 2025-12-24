from textwrap import dedent

from utils.schema import StepResult


def build_final_compress_prompt(context: str, steps: list[StepResult], feedback: str) -> str:
    extra = f"\n提升难度指引: {feedback.strip()}" if feedback else ""
    step_lines = []
    for idx, step in enumerate(steps, start=1):
        step_lines.append(
            f"- Step {idx}: Q={step.question} | answer_text={step.answer_text} | answer_letter={step.answer_letter} | evidence={step.evidence}"
        )
    step_block = "\n".join(step_lines)
    return dedent(
        f"""
        你需要把下述多步推理链压缩成一个高难度单选题(MCQ)。
        要求:
        - 不要显式提“第一步/第二步”，把中间结论隐式化。
        - 必须“留头留尾”：保留首步视觉锚点线索与末步关键结论/判别依据，中间步骤刻意隐藏，仅以隐含条件/背景融入题干。
        - 题干必须围绕图片中心视觉信息展开，参考信息仅作为隐含依据。
        - 题干必须显式包含至少2条【中性条件/判据/公式】（来自 steps 的 evidence/fact_hint 改写，不提来源）。
        - 题目必须至少包含2步推理（例如先由图读X→计算Y→对照判据分级，或先判分支→再计算/比较）。
        - 题干包含 A-D 选项，且唯一正确答案。
        - 题干中禁止出现“文献”,“文档”,“上下文”,“context”“结合文献”“依据文献”等字样。
        - 禁止“纯实体匹配/纯定义检索”题；必须以计算作为核心。
        - 出题风格偏向条件计算：优先生成“数值/区间/等级”型单选题。
        - 去词汇化(避免文本捷径)：题干不要直接写出图中读数/颜色/形状等具体值，改用“图中…的读数/显示的状态/位于…的部件”等指代性或位置性描述，迫使读者看图。
        - 去词汇化仅针对图上读数/视觉结果，不限制写入中性判据(阈值/公式/单位换算)。
        - 干扰项生成必须先做“陷阱设计”(仅内部推理，不要输出)：
          1) 单位陷阱：计算正确但单位未换算（如 kW vs W）。
          2) 视觉误读：假设用户看错刻度/位置/颜色导致的错误结果。
          3) 条件误用：假设用户套用了错误的阈值/分支规则导致的错误结果。
          然后把这3个错误路径的结果分别映射为3个错误选项，并确保它们都是参考信息/推理链中出现过的同类真实概念/条件。
        - 选项同质性：四个选项的单位/小数位数/数量级尽量一致，避免长度差异过大导致一眼排除。
        {extra}

        推理链:
        {step_block}

        参考信息(仅供内部推理；允许将其中1-2条事实改写为题干的中性条件/阈值/公式，不得提及来源):
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
        - 去词汇化仅针对图上读数/视觉结果，不限制写入中性判据(阈值/公式/单位换算)。
        - 题干必须显式包含至少2条【中性条件/判据/公式】，且包含至少2步推理。
        - 题干包含 A-D 选项，且唯一正确答案。
        - 干扰项同类同粒度且合理。
        - 题干中禁止出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”等字样。
        - 干扰项优先从参考信息中挖掘“强负样本”，而不是编造无关概念。
        - 干扰项必须先做“陷阱设计”(仅内部推理，不要输出)：单位陷阱/视觉误读/条件误用，然后映射为 3 个错误选项。
        - 选项同质性：四个选项的单位/小数位数/数量级尽量一致，避免长度差异过大。

        参考信息(仅供内部推理；允许将其中1-2条事实改写为题干的中性条件/阈值/公式，不得提及来源):
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>正确选项字母</answer>
        <reasoning>简要推理过程(不超过4句)</reasoning>
        """
    ).strip()


def build_final_harden_prompt(
    context: str,
    steps: list[StepResult],
    final_question: str,
    final_answer: str,
    reason: str,
) -> str:
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
        - 必须引入一个中间变量（先算再判），并明确两个以上推理步骤。
        - 必须增加一个分支规则（先由图像选择分支，再计算/判级）。
        - 题干必须显式包含至少2条【中性条件/判据/公式】（来自 steps 的 evidence/fact_hint 改写，不提来源）。
        - 题干必须围绕图片中心视觉锚点，去词汇化仅针对图上读数/视觉结果，不限制写入中性判据(阈值/公式/单位换算)。
        - 选项必须为数值/区间/等级型答案，且单位/数量级一致。
        - 错误选项必须来自三条错误路径：单位换算错 / 读图误读 / 条件误用。
        - 禁止出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”等字样。

        推理链:
        {step_block}

        参考信息(仅供内部推理；允许将其中1-2条事实改写为题干的中性条件/阈值/公式，不得提及来源):
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>正确选项字母</answer>
        <reasoning>简要推理过程(不超过4句)</reasoning>
        """
    ).strip()
