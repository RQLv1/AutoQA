from textwrap import dedent


def build_solver_prompt(context: str, question: str) -> str:
    return dedent(
        f"""
        你是一名考生，请结合图片和文档作答单选题。
    
        题目:
        {question}

        文档:
        {context.strip()}
        
        **严格只输出以下格式，禁止解释或追加其他内容，输出中不得出现除该标签外的任何字符:**
        <answer>A/B/C/D</answer>
        """
    ).strip()
