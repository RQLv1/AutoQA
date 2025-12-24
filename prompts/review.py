from textwrap import dedent


def build_review_prompt(
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
        1. 检查问题是否明确提及图像中的视觉特征。
        2. 检查推理是否合理且一致。

        仅输出以下之一:
        <review>correct</review> (如果有效且高质量)
        <review>incorrect</review> (如果逻辑存在缺陷或答案错误)
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
        1. 如果问题提到了具体的视觉特征（例如“右侧的曲线图”、“左上角的插图”、“刻度尺读数”、“红色箭头指示的部分”），请检查它们在图是否存在。
        2. 如果问题隐含了需要读取的视觉数据，请检查对应的数据源是否包含在图中。

        只输出以下标签之一（必须单行输出，不得包含任何解释、编号或多余文字）:
        <verified>yes</verified> (如果所有视觉主张都有效，或者题目没有提出具体的视觉主张)
        <verified>no</verified> (如果题目描述了图片中根本不存在的视觉元素，例如图中没有曲线却问“曲线的趋势”)

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
