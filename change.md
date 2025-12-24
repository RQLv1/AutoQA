根据你的分析， **中求解器（Medium Solver）之所以能答对，是因为题目通过“先...再...”的句式泄露了推理路径（CoT Shortcut）** 。为了迫使模型自主推理（从而区分出只有强模型才能做对的题目），我们需要在生成 Prompt 中明确 **禁止“说明书式”的题干** 。

以下是针对 `prompts/steps.py` 和 `prompts/final.py` 的修改方案。核心改动是增加了 **[Anti-Instructional / 禁止解题说明书]** 的约束，强制题干只给出“目标”和“条件”，隐藏“过程”。

### 修改方案 1: `prompts/steps.py`

我们需要在所有生成多步/图谱题的 Prompt 中（Stage 2, Stage 3, Extend, Graph 1-hop），加入禁止泄露步骤的指令。

**Python**

```
# rqlv1/autoqa/AutoQA-rqlv/prompts/steps.py

# ... (保持 imports 和辅助函数不变)

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
    # ... (保持开头不变)
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
        - operate_calculation 智能体草稿(仅供内部推理，不得在题干中提到):
          - draft:
{operate_calculation_block}
        - {cross_modal}
        - 题干包含 A-D 选项，答案需可验证。
        - 题干必须围绕图片中心视觉锚点，禁止出现“文献”“文档”“上下文”“context”“结合文献”“依据文献”等字样。
        - 去词汇化(避免文本捷径)：题干不要直接写出图中读数/颜色/形状等具体值，改用“图中…的读数/显示的状态/位于…的部件”等指代性或位置性描述，迫使读者看图。
      
        [关键修改点 1]
        - 禁止“解题说明书”式引导(Anti-Instructional)：严禁在题干中写出“先计算...再对比...最后得出...”这样的步骤指导。
          - 错误示例：“请先计算X，再将X代入公式Y，最后判断等级。”
          - 正确示例：“根据图中特征与公式Y，该区域的最终等级为？”（迫使模型自己去找计算X的必要性）。
      
        - 禁止“纯实体匹配/纯定义检索”题。
        - 难度算子要求... (保持不变)
        - 条件计算题必须... (保持不变)
        - 干扰项必须... (保持不变)

        参考信息(仅供内部推理，不得在题干中提到):
        {context.strip()}

        只输出以下格式:
        <question>题干，包含 A-D 选项</question>
        <answer>A/B/C/D</answer>
        <reasoning>简要推理过程(不超过4句)</reasoning>
        """
    ).strip()

# 对于 build_stage3_step_prompt 和 build_extend_step_prompt，做同样的修改：
# 在 "去词汇化" 和 "禁止纯实体匹配" 之间插入 "禁止解题说明书式引导"。

def build_stage3_step_prompt(...):
    # ... (代码结构同上，插入 Anti-Instructional 约束)
    return dedent(f"""
        ...
        - 去词汇化(避免文本捷径)：...
        - 禁止“解题说明书”式引导(Anti-Instructional)：严禁在题干中写出“先计算...再对比...最后得出...”这样的步骤指导。题干只能给出必要的背景知识（如公式、阈值）和最终问题，强迫模型自主构建解题路径。
        - 禁止“纯实体匹配/纯定义检索”题...
        ...
    """).strip()

def build_extend_step_prompt(...):
    # ... (代码结构同上，插入 Anti-Instructional 约束)
    return dedent(f"""
        ...
        - 去词汇化(避免文本捷径)：...
        - 禁止“解题说明书”式引导(Anti-Instructional)：严禁在题干中写出“先计算...再对比...最后得出...”这样的步骤指导。题干只能给出必要的背景知识（如公式、阈值）和最终问题，强迫模型自主构建解题路径。
        - 禁止“纯实体匹配/纯定义检索”题...
        ...
    """).strip()

# 针对 Graph 模式的修改
def build_graph_1hop_step_prompt(
    # ...
) -> str:
    # ...
    return dedent(
        f"""
        ...
        - 必须围绕图片中心视觉锚点展开，避免纯文本问答。
      
        [关键修改点 2]
        - 隐藏推理逻辑(Hide Logic)：禁止在题干中显式指导计算步骤（如“请先读A，再算B”）。题干应直接询问基于知识链 {head}->{tail} 的最终推断结果，让模型自己去发现需要读取哪些图表数据来满足知识链的条件。

        - 本步必须是“条件计算题”，不能是概念解释/机制判断/实体匹配。
        ...
        """
    ).strip()
```

### 修改方案 2: `prompts/final.py`

Final 阶段的 Prompt 最容易把之前的 Step 1-2-3 串成一个长指令，这里必须强制“隐式化”。

**Python**

```
# rqlv1/autoqa/AutoQA-rqlv/prompts/final.py

def build_final_compress_prompt(context: str, steps: list[StepResult], feedback: str) -> str:
    # ... (保持不变)
    return dedent(
        f"""
        你需要把下述多步推理链压缩成一个高难度单选题(MCQ)。
        要求:
        - 不要显式提“第一步/第二步”，把中间结论隐式化。
      
        [关键修改点 3]
        - 彻底移除过程指导(No Procedural Guidance)：题干禁止包含任何“先做这个，再做那个”的指令。
          - 必须将题目转化为“目标导向”：例如不要问“计算A和B的平均值”，要问“根据图示综合评估的最终指标 F 是多少？”（假设 F 定义为 A B 平均，这个定义放在背景知识里，而不是题干指令里）。
          - 让中等模型因为不知道“要先算 A 和 B 再平均”而做错，迫使强模型去检索隐含逻辑。

        - 必须“留头留尾”：保留首步视觉锚点线索与末步关键结论/判别依据...
        - 题干必须围绕图片中心视觉信息展开...
        # ... (后续保持不变)
        """
    ).strip()

def build_final_revise_prompt(context: str, final_question: str, final_answer: str, reason: str) -> str:
    return dedent(
        f"""
        需要修订最终题(单选题)，原因: {reason}
      
        [关键修改点 4]
        修订要求:
        - 消除“说明书”痕迹：如果原题干包含了具体计算步骤（如“请通过...公式计算...”），请将其改为只提供背景公式，问题直接指向最终结果。
      
        - 避免单模态捷径...
        # ... (后续保持不变)
        """
    ).strip()
```
