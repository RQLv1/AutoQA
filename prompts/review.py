from textwrap import dedent


def build_review_prompt(
    question: str,
    answer: str,
    reasoning: str,
) -> str:
    return dedent(
        f"""
        You are a strict reviewer for a visual question answering dataset.

        Question: {question}
        Proposed Answer: {answer}
        Reasoning: {reasoning}

        Task:
        1. Check if the question clearly refers to visual features in the image (e.g., "the red curve", "the inset", "structure A").
        2. Check if the answer is logically derived from the visual evidence + common knowledge.
        3. Check if the reasoning is sound and consistent.

        Output only one of the following:
        <review>correct</review> (If valid and high quality)
        <review>incorrect</review> (If logic is flawed or answer is wrong)
        <review>ambiguous</review> (If the image is unclear or question is confusing)
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
        1. 如果问题提到了具体的视觉特征（例如“右侧的曲线图”、“左上角的插图”、“刻度尺读数”、“红色箭头指示的部分”），请检查它们在图中是否清晰可见且真实存在。
        2. 如果问题隐含了需要读取的视觉数据（例如“图表显示的数值是多少”、“斜率表明了什么”），请检查对应的数据源（图表、表格、仪表盘）是否包含在图中。
        3. 忽略不需要视觉确认的纯理论/抽象概念（例如“该物质的化学式是什么”），只关注题目中对图片内容的描述性主张（Visual Claims）。

        只输出以下标签之一:
        <verified>yes</verified> (如果所有视觉主张都有效，或者题目没有提出具体的视觉主张)
        <verified>no</verified> (如果题目描述了图片中根本不存在的视觉元素，例如图中没有曲线却问“曲线的趋势”)
        """
    ).strip()
