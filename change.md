
### 修改策略：从“查找”转向“判别与推演”

目前的 `Extension Loop` 可能是在做加法（A -> B -> C），大模型很擅长顺藤摸瓜。我们要改成：

1. **去捷径（Blindfold Test）** ：如果只看参考信息就能做对，直接废弃。
2. **强干扰（Hard Negatives）** ：干扰项必须是参考信息中存在的真实概念，但在当前图像语境下是错误的。
3. **高阶任务** ：引入数学计算、空间变换或条件约束。

---

### 具体修改方案

#### 1. 修改 `Solve-in-the-loop`：引入“蒙眼测试”（Blindfold Check）

在 `pipeline_episode.py` 的求解环节，增加一个 **“盲测”** 步骤。这是提升题目“跨模态必要性”的最有效手段。

* **逻辑** ：

1. **Text-Only Check** ：不给图片，只给 `question`，让 Solver 答题。如果答对了 -> **题目太简单/泄漏答案** -> 触发 `Revise` 或直接 `Drop`。
2. **Image-Only Check** ：不给外部参考知识（假设 Solver 只有通用知识），只给 `image + question`。如果答对了 -> **不需要参考文献** -> 触发 `Revise`（强行要求引入文献中的特殊定义或数据）。

* 修改建议：
  在 pipeline/pipeline_solvers.py 或 pipeline_episode.py 中增加：
  **Python**

  ```
  def check_blindfold_shortcuts(question, image, prompt_solver):
      # 1. 尝试只看文字能否解题（检测题干是否泄漏）
      pred_text_only = prompt_solver.solve(image=None, question=question) 

      # 2. 尝试只看图能否解题（检测是否依赖 Reference）
      # 注意：这里需要Prompt稍微调整，模拟没有Reference的场景
      pred_image_only = prompt_solver.solve(image=image, question=question, context=None) 

      return {
          "text_shortcut": pred_text_only == correct_answer,
          "image_shortcut": pred_image_only == correct_answer
      }
  ```

  *如果任一 shortcut 为 True，则难度系数直接打折，或者强制重写。*

#### 2. 强化 `Step` 模板：强制“逻辑变换”而非“信息拼接”

在 `prompts/` 目录的 Stage2/3（或 Extend）Prompt 中，不要只让模型“寻找下一个关联”，而是强制要求使用以下**难度算子**之一：

* **算子 A - 差异对比（Distinction）** ：文中提到两个相似概念（如两种催化剂），图里画的是其中一种。题目问：“图示结构与另一种结构（未画出）的主要区别是什么？”
* **算子 B - 条件计算（Calculation）** ：文中给出公式或数据（如转化率=X），图里给出参数（如温度曲线）。题目问：“根据图示条件，计算结果是多少？”（选项是数字）。
* **算子 C - 异常检测（Anomaly）** ：图里画了一个过程，文中描述了标准流程。题目问：“图示流程缺少了文中提到的哪个关键步骤？”
* **Prompt 修改思路** ：

> "Do NOT simply ask 'what is X'. Instead, construct a scenario where the user must identify the visual feature X, map it to the definition in the text, and then  **deduce a consequence, calculate a value, or identify a conflicting condition** ."

#### 3. 强化 `Compress/Final`：对抗性干扰项生成

大模型答对往往是因为干扰项太蠢（一眼假）。在生成最终 MCQ 时，专门调用一次  **“干扰项增强”** 。

* 修改 steps/ 或 Final Prompt：
  要求模型从参考文档中挖掘 “Hard Negatives”（强负样本）。
  * **Bad Distractor** : "Apple" (当答案是 "Banana" 时，且文中没提 Apple)。
  * **Good Distractor (Hard Negative)** : 文中提到了 "Plantain"（大蕉），且描述了它和 Banana 很像。生成的选项必须包含 "Plantain"，并诱导对此不熟悉的人选错。

#### 4. 引入 `Adversarial Revise`（红队测试）

在 `pipeline_episode.py` 的 `Extension Loop` 结束后，增加一个 `Adversarial Check`：

* **角色** ：扮演一个极其挑剔的考官。
* **任务** ：试图攻击题目。
* “我能不能通过排除法猜出答案？”
* “选项 C 的长度是不是明显比其他长？”
* “题干是不是包含了 '如图所示的红色物体' 这种直接提示？”
* **操作** ：如果攻击成功，调用 `Refiner Model` 进行改写，专门针对漏洞打补丁。

---

### 工作流修改路线图（基于你的 README）

建议按照以下顺序实施代码调整：

1. **修改 `pipeline/pipeline_solvers.py`** ：

* 实现 `solve_blind_text()` 和 `solve_blind_image()`。
* 输出不仅仅是 A/B/C/D，而是 `is_shortcut_found` bool 值。

1. **修改 `pipeline/pipeline_episode.py` (Extension Loop)** ：

* 在 `step` 生成后，立刻运行 `Judge`。
* **新增规则** ：如果 `step` 只是简单的实体匹配（Entity Matching），标记为 `LOW_QUALITY`，下一轮必须应用“计算”或“对比”算子。

1. **修改 `prompts/` (Distractor Generation)** ：

* 在 `Compress` 阶段，传入 `fact_candidates`（参考信息片段）。
* Prompt 指令：“Generate 3 distractors that act as 'traps'. They must be entities or concepts mentioned in the provided text segments but act as plausible misconceptions for the visual evidence.”

1. **配置调整 `main.py`** ：

* 设置 `VERIFY_STRICT = True`。
* 设置 `MODEL_SOLVE_MEDIUM` 为一个较弱的模型（如 GPT-3.5 或 7B 模型），`MODEL_SOLVE_STRONG` 为 GPT-4o 或 Claude 3.5 Sonnet。
* **目标** ：只有当 Medium 答错（或随机猜测），而 Strong 答对时，才算合格的高难题目。

### 一个高难度题目的范例（供 Prompt 参考）

* **图片** ：一张锂电池循环伏安曲线图，显示在 3.5V 有氧化峰。
* **文本** ：提到材料 A 在 3.5V 反应，材料 B 在 3.8V 反应；且提到材料 A 在高温下容量衰减快，材料 B 较稳定。
* **低难度题（现状）** ：图中的材料是什么？（答案：材料 A）。
* **高难度题（修改后）** ：
* **题干** ：基于图中显示的氧化还原电位特征，推断该材料在高温环境下的电化学性能表现如何？
* **推理链** ：
  1. (视) 观察图 -> 峰位在 3.5V。
  2. (文) 对照文本 -> 确认是材料 A。
  3. (文) 检索材料 A 属性 -> 高温衰减快。
  4. (结) 答案：高温下循环稳定性差。
* **干扰项** ：放入材料 B 的属性（“具有优异的高温稳定性”），专门坑那些只看图没对应准，或者只看文没看图的人。
## 实现状态（对齐本文件方案）

### 已实现

- [x] **Solver 输入约束**：求解器只接收图片 + `question`（不喂入参考信息/`context`）。
- [x] **Blindfold（Text-Only）**：新增“只看题干不看图”的求解检查，用于检测题干泄漏/纯文本捷径。
  - 落地：`pipeline/pipeline_solvers.py` 增加 `solve_mcq_text_only`；`evaluate_difficulty` 增加 `strong_text_only_*` 字段；`pipeline/pipeline_episode.py` 将 `text-only shortcut found` 作为 revise 原因之一。
- [x] **Prompt 强化（Step/Final）**：Stage2/3/Extend/Final 强制以“差异对比 / 条件计算 / 异常检测”之一为核心，避免纯实体匹配；并要求干扰项为参考信息中的 Hard Negatives（题干仍需围绕图片锚点）。
  - 落地：`prompts/steps.py`、`prompts/final.py`
- [x] **Adversarial Check（启发式）**：新增启发式 MCQ 质量检查（如选项缺失/选项长度偏置），命中则触发最终题 revise。
  - 落地：`pipeline/pipeline_judge.py`、`pipeline/pipeline_episode.py`

### 未实现 / 需要进一步明确

- [ ] **Blindfold（Image-Only）判“是否需要参考信息”**：由于求解器不接收参考信息，该判据与“强制依赖参考信息”存在目标冲突；需要明确期望（例如：是否允许把必要数据写进题干，使求解器仍可解）。
- [ ] **Step 级 Judge + 低质量（Entity Matching）强制改写**：当前仅通过 Prompt 约束提升，不做逐步的“低质量判别与强制重写”。
