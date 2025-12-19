## README.md 修改方案：引入 Episode 内“对抗式加难闭环（计算优先）”

### 修改目标

在现有“Medium 过滤、Strong 验证”的框架上，进一步把“加难”从提示词建议升级为 **强制程序闭环** ：

* **Episode 内部** ：题目一旦被 Medium Solver 做对，系统自动触发“加难重写（计算/量化推理优先）”，并再次用 Medium 攻击，直到 Medium 做错或达到最大加难次数。
* **Round 层面（main.py）** ：入口逻辑极简化——如果 Episode 已经尽力加难但 Medium 仍然做对，则直接丢弃，不进入日志/库。

---

## 需要在 README 增补/调整的章节与内容

### 1) 更新「每轮 Episode 的执行流程」：新增“Adversarial Refinement Loop（Episode 内加难闭环）”

在你当前 README 的 Episode 流程里，`2) Compress` 与 `3) Difficulty 评估`之间，插入一个新的小节：

**新增小节标题建议：**

* `2.5) Adversarial Refinement Loop（不难不休：计算优先加难）`

**新增内容要点（文案建议）：**

* Final 题目生成后，立即调用 `evaluate_difficulty` 做 Medium Attack
* 若 `medium_correct == true`：进入“加难模式”，强制模型将题目改写为 **视觉计算题** （计数差值、总和、比例、范围判断等）
* 加难后再次评估；循环直到：
  * Medium 失败（`medium_correct == false`）→ 题目通过 Episode 内难度门槛
  * 或达到 `MAX_HARDEN_ATTEMPTS` → 保留当前版本（但 main.py 仍会做最终丢弃/入库判定）

**强调点：**

* 加难模式不是“提示一下”，而是**强制重写 + 再攻击**的闭环
* 加难策略以**计算与量化推理**为第一优先级，且数值必须来自图像可验证证据（计数/读数/标签）

---

### 2) 更新「Difficulty 评估（Medium/Strong）」：明确“Episode 内会多次评估”

你当前 README 把 Difficulty 评估写成单次（对候选 Final 题）。需要补一句：

* Difficulty 评估在强化版中可能发生多次：**初版 Final + 若干次加难重写后的 Final**
* 评估结果以最后一次通过门槛（或达到上限）时的 metrics 为准记录到 `difficulty_metrics`

---

### 3) 更新「Adversarial Filter（主循环筛选）」：main.py 改为“极简筛选 + 只认 Medium”

你当前 README 的 `main.py 负责筛选逻辑`已写“medium_correct==true → 废弃”。这里需要进一步明确新的策略：

* `run_episode()` 内部已经做了“加难闭环”，`main.py` 不再做复杂 feedback / reflection 调参
* **最终入库条件** ：`medium_correct == false`（Medium 覆灭即入库）
* `strong_correct` 仅用于标记难度等级（中难/极难），不作为入库硬门槛（可选策略）

并加一句关键描述（避免读者误解）：

* “如果 Episode 内已加难但 Medium 仍做对，则说明题目无法有效加硬，主循环直接丢弃继续生成。”

---

### 4) 新增「加难 Prompt 规范」：PROMPT_HARDEN_TEMPLATE 的文档化描述（不贴代码也能说明清楚）

建议在 `Prompt 设计要点`下新增一个子段落：

**标题建议：**

* `Hardening Prompt（计算优先加难模板）`

**要点：**

* 加难模板强制把“识别题”重写为“计算题/量化题”
* 必须满足：
  * 题目答案可由图像证据计算得到（计数、求和、差值、比例、阈值判断）
  * 干扰项为**数字或数值区间**且彼此接近，降低蒙对概率
  * 禁止外部知识；禁止把参考信息当成唯一证据来源（仍须以图像为核心证据）

---

### 5) 更新「停止条件」：增加 `MAX_HARDEN_ATTEMPTS`（Episode 内上限）

在 `停止条件（Episode / Round）`中补充：

* Episode 内新增停止/收敛条件：`MAX_HARDEN_ATTEMPTS`（如 3 次）
* 达到上限后 Episode 输出当前版本，但最终是否入库仍由 main.py 的 Medium 判定决定

---

### 6) 更新「配置」：新增/说明加难相关参数（可选写法）

在配置章节里新增一组参数说明（即便你不做 env var，也建议写清楚默认值）：

* `MAX_HARDEN_ATTEMPTS`：Episode 内最大加难轮数（默认 3）
* （可选）`HARDEN_MODE`：固定为 `calc_first`（用于未来扩展不同加难策略）

---

## README 中需要删/改的旧表述（避免冲突）

建议把与以下含义冲突的句子弱化或改写：

* “难度筛选由 main.py 统一完成”
  * 改为：main.py 负责最终筛选；Episode 内部也包含对抗式加难与多次难度评估。
* “Final revise 默认关闭”
  * 补充：虽然 Final revise 仍关闭，但 Episode 内新增 harden loop 属于“Final 重写”范畴（不是 judge/reflect 那套）。
