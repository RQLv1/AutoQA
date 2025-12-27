from textwrap import dedent


def build_review_prompt(
    question: str,
    answer: str,
    reasoning: str,
    mode: str = "multi_select",
) -> str:
    is_single = mode == "single_select"
    option_rule = (
        "必须包含 4-8 个按顺序编号的选项（A-H），且答案由一个或多个选项字母组成（可用逗号分隔，需按字母顺序）"
        if not is_single
        else "必须包含 A/B/C/D 四个选项，且答案为其中一个字母"
    )
    return dedent(
        f"""
        你是一名视觉问答数据集的严格审稿人。

        问题: {question}
        候选答案: {answer}
        推理: {reasoning}

        任务:
        1. 检查题目是否为标准{"多选题" if not is_single else "单选题"}：{option_rule}；否则判为 incorrect。
        2. 检查推理是否合理且一致。
        3. 【新增】检查数值区间互斥性：如果选项包含数值范围（如 10-20），必须检查各选项是否存在数学重叠。如果存在重叠导致答案不唯一（例如 A:10-20, B:15-25），必须判为 incorrect。

        输出格式:
        - 无问题则输出: <review>correct</review>
        - 存在问题则输出: <review>incorrect</review>
        - 如果判定为 incorrect，必须在后面给出具体原因: <reason>具体错误原因（例如：答案与推理不一致 / 推理逻辑存在跳跃 / 选项格式不规范 / 答案错误等）</reason>

        示例:
        <review>incorrect</review>
        <reason>选项 A (0.9-1.0) 与选项 B (0.95-1.05) 存在数值重叠，导致题目不严谨</reason>
        """
    ).strip()


def build_visual_verification_prompt(question: str) -> str:
    """
    构建视觉核查 Prompt，用于检测题干是否包含图片中不存在的视觉特征（幻觉）。
    """
    return dedent(
        f"""
        请核实以下问题中提到的视觉证据是否存在于提供的图片中。

        待核查问题:
        "{question}"

        核查标准:
        1. **仅检查明确的视觉定位描述**：如果问题提到了具体的空间位置（例如"右侧的曲线图"、"左上角的插图"、"红色箭头指示的部分"），请严格检查这些位置和元素是否存在。

        2. **宽松对待数据引用**：如果问题只是提到"图中给出了...信息"、"图示...数据"、"根据图中...参数"等，只要图片包含相关类型的数据或图表即可，不必完全字面匹配描述。

        3. **允许合理推断**：如果问题提到的信息可以从图片中的图表、数据、标注等合理推断出来，应判为有效。

        4. **只在明显矛盾时判否**：只有当问题明确描述了完全不存在的视觉元素时才判定为 no（例如：图中没有任何曲线却问"曲线的斜率"、图中没有颜色标注却问"红色区域的面积"）。

        只输出以下标签之一（必须单行输出，不得包含任何解释、编号或多余文字）:
        <verified>yes</verified> (如果视觉主张有效、合理或可推断)
        <verified>no</verified> (如果题目描述了图片中完全不存在且无法推断的视觉元素)

        如果你输出了除上述单行标签之外的任何内容，该回答将被直接判为无效并丢弃。
        """
    ).strip()


def build_review_feedback_prompt(
    question: str,
    answer: str,
    reasoning: str,
) -> str:
    return dedent(
        f"""
        你是一名视觉问答数据集的严格审稿人。

        问题: {question}
        候选答案: {answer}
        推理: {reasoning}

        任务:
        - 指出题目未通过的具体原因（与图不符/逻辑跳跃/证据不足/选项歧义/答案错误等）。
        - 给出可执行的修改方向（不直接改写题目）。

        仅输出项目符号列表，每条一行，2-4 条即可。
        """
    ).strip()
