### 1. 第一道防线：生成阶段（Generation）

在 `prompts/steps.py` 中，所有的生成 Prompt（如 `build_stage2_step_prompt`, `build_stage3_step_prompt` 等）都需要增加一条**“区间互斥硬约束”**。

请在 `rqlv1/autoqa/AutoQA-rqlv/prompts/steps.py` 文件中，找到所有构建 Prompt 的函数（特别是 `build_stage2_step_prompt`, `build_stage3_step_prompt`, `build_extend_step_prompt`, `build_graph_1hop_step_prompt`），在 **“- 同质且近邻：”** 这一段约束下方，统一插入以下代码：

**Python**

```
        - 区间互斥硬约束：
          - 若选项为数值范围，必须确保各选项在数学上互不重叠（例如 A:0-5, B:6-10）；
          - 严禁生成如 "A:0.90-1.00, B:0.95-1.05" 这样存在交集的重叠选项；
          - 推荐使用半开区间逻辑（如 A: <1.0, B: 1.0-1.5）或明确的分段点（A: 0-9, B: 10-19）。
```

**修改位置示例（以 `build_stage2_step_prompt` 为例）：**

**Python**

```
# 文件: rqlv1/autoqa/AutoQA-rqlv/prompts/steps.py

def build_stage2_step_prompt(...):
    # ... (省略上方代码)
        - 同质且近邻：
          - 四个数值选项必须同单位、同小数位；
          - 最大值/最小值 ≤ 1.25（或差值不超过正确值的±15%），避免跨度过大导致秒选。
    
        # 【新增插入点】
        - 区间互斥硬约束：
          - 若选项为数值范围，必须确保各选项在数学上互不重叠（例如 A:0-5, B:6-10）；
          - 严禁生成如 "A:0.90-1.00, B:0.95-1.05" 这样存在交集的重叠选项。
      
        - 禁止“纯实体匹配/纯定义检索”题...
    # ... (省略下方代码)
```

*(注意：你需要对 `steps.py` 中所有类似的 `build_..._prompt` 函数执行相同的插入操作。)*

---

### 2. 第二道防线：审查阶段（Review）

LLM 即使收到指令有时也会疏忽，因此必须在 Review 阶段进行拦截。修改 `rqlv1/autoqa/AutoQA-rqlv/prompts/review.py`，强制审稿人检查数学重叠。

**修改代码：**

**Python**

```
# 文件: rqlv1/autoqa/AutoQA-rqlv/prompts/review.py

def build_review_prompt(question: str, answer: str, reasoning: str) -> str:
    return dedent(
        f"""
        你是一名视觉问答数据集的严格审稿人。

        问题: {question}
        候选答案: {answer}
        推理: {reasoning}

        任务:
        1. 检查题目是否为标准单选题：必须包含 A/B/C/D 四个选项，且答案为其中一个字母；否则判为 incorrect。
        2. 检查推理是否合理且一致。
        3. 【新增】检查数值区间互斥性：如果选项包含数值范围（如 10-20），必须检查各选项是否存在数学重叠。如果存在重叠导致答案不唯一（例如 A:10-20, B:15-25），必须判为 incorrect。

        输出格式:
        - 无问题则输出: <review>correct</review>
        - 存在问题则输出: <review>incorrect</review>
        - 如果判定为 incorrect，必须在后面给出具体原因: <reason>具体错误原因</reason>

        示例:
        <review>incorrect</review>
        <reason>选项 A (0.9-1.0) 与选项 B (0.95-1.05) 存在数值重叠，导致题目不严谨</reason>
        """
    ).strip()
```

---

### 3. 补充建议：代码级校验（Python）

虽然 Prompt 能解决大部分问题，但如果你希望做到  **100% 杜绝** ，可以在 `rqlv1/autoqa/AutoQA-rqlv/steps/validation.py` 中增加一个简单的正则检测逻辑，专门针对“数字-数字”格式的选项进行重叠检测。

但考虑到实现复杂性（需要解析浮点数、百分比等多种格式），**上述 Prompt 的两步修改方案（Generation + Review）通常已经足够解决 95% 以上的此类问题。**
