---
# AutoQA（强化版）：基于图文上下文的高难度 MCQ 自动生成（保持现有工程结构）

AutoQA 是一个「图片 + 文档上下文」驱动的自动出题系统，用多轮迭代生成**高难度、可验证、强多模态依赖**的单选题（MCQ），并通过“求解模型 + 反思模型 + 过程裁判（可选）”闭环提升难度。

> **注意：本强化版在“代码文件结构”上保持你当前项目的目录不变**（仍以 `main.py / config.py / api_client.py / prompts.py / pipeline.py / parsing.py / schema.py` 为主），仅在 `pipeline.py + prompts.py + schema.py + config.py` 内扩展：
>
> - 把原 Stage1/2/3 变成 **可循环复用的 step 模板**（multi-hop extension）
> - 在每轮内支持多次扩链、必要时 revise、最终 compress
> - 引入双求解器（Medium/Strong）在线校准难度（若未配置则自动退化为单求解器）
---
## 目标与原则

### 目标

1. **更具挑战性的推理链**：题目必须体现多跳推理（建议 ≥2 hops），尽量避免“单句命中答案”的检索式问题。
2. **更贴近多模态**：至少包含一次**跨模态桥接**（图 → 文 或 文 → 图），避免只看其中一个模态即可解题。
3. **答案可验证**：正确答案与关键推理证据必须能在给定图文上下文中定位（可选：输出证据 span/索引）。

### 强约束（硬性）

- 所有题目与正确答案 **不得依赖外部知识**。
- 最终题必须包含：4 个选项（A/B/C/D），且唯一正确答案。
- 选项必须“同类型同粒度”，避免明显离谱的干扰项。

---

## 工作流（强化版，兼容现有 Stage 结构）

入口：`main.py`

每一轮（`MAX_ROUNDS`）执行一个 Episode，由 `pipeline.py` 统一编排。整体仍保留你现在的“阶段式日志写法”（Stage1/2/3/Final + Solve/Analysis），但在内部新增 **Extension Loop**：

### 0) 预处理：图文锚点与候选事实

- 从图片生成**视觉锚点**（中心区域对象/符号/结构/关系）与候选描述（anchor candidates）
- 从文档上下文抽取**关键点/事实片段**（fact candidates，附带 span/段落索引）

> 说明：预处理不要求你引入新文件，可直接在 `pipeline.py` 内实现简化版本：
>
> - 视觉锚点：由 Stage1 prompt 引导模型“只围绕中心区域锚点描述”即可
> - 文档关键点：用文本模型从上下文抽取若干关键句或要点（带行号/段落索引）

---

## 每轮 Episode 的执行流程

### 1) Extension Loop（多次扩链，复用 Stage1/2/3 模板）

在一个 Episode 内，允许多次扩链 `step_k (k=0..K)`，每步产出一个 `StepResult`：

- `question`: 子问题（中间问题，不一定是最终 MCQ）
- `answer`: 子问题答案（必须可在上下文中定位）
- `evidence`: 证据定位（doc span/段落索引；可选 image 区域描述）
- `modal_use`: image/text/both
- `cross_modal_bridge`: bool（是否跨模态桥接）
- `raw`: 原始输出

**如何保持“现有 Stage1/2/3”但支持多次扩链？**

- `step_0`：使用 **Stage1 模板**（强视觉锚点，尽量只依赖图）
- `step_1`：使用 **Stage2 模板**（引入文档关键点 1，形成第一跳推理）
- `step_2`：使用 **Stage3 模板**（再引入文档关键点 2 或图中另一个关系，形成第二跳推理）
- `step_3..K`：**循环复用 Stage2/Stage3 模板**（或统一用一个 “EXTEND” prompt），每次强制：
  - 要么换新的文档关键点（不同段落/不同实体）
  - 要么换新的视觉锚点（同一中心区域内不同关系/符号/标注）
  - 并且至少一次 `cross_modal_bridge=true`（可由 judge 检测并强制 revise）

> 这样你无需新增 `agent.py` 文件：Agent 决策逻辑直接写在 `pipeline.py` 中（例如：是否继续扩链、是否 revise、何时 compress）。

---

### 2) Solve-in-the-loop（在线校验与难度标定）

对每个 `step` 以及候选 Final 题进行在线评估：

- **Strong Solver**：验证“可解性/一致性”
  - Strong 都答不对：大概率题坏/证据不足 → 触发 revise 或回滚
- **Medium Solver**：衡量难度增长
  - 理想状态：Medium 开始失败，而 Strong 仍可成功（难度有效提升）

系统维护 `difficulty_score`（可组合以下信号）：

- `medium_correct` vs `strong_correct`
- 一致性投票（多次采样/多模型一致性，可选）
- token 比、推理步数、信息分散度等 proxy（可选）

> **兼容策略**：如果你不想新增太多配置：
>
> - 未设置 `MODEL_SOLVE_STRONG` 时，默认 `MODEL_SOLVE_STRONG = MODEL_SOLVE`
> - 未设置 `MODEL_SOLVE_MEDIUM` 时，默认 `MODEL_SOLVE_MEDIUM = MODEL_SOLVE`
>   即自动退化为单 solver，但接口不变。

---

### 3) Revise（纠错 / 去捷径）

触发条件（示例）：

- Strong solver 失败或出现多解/歧义
- 存在明显捷径：只看文或只看图即可直接命中答案
- 证据无法定位或引用不一致
- 选项不均衡、干扰项过弱

Revise 目标：

- 修复歧义、补齐证据链
- 改写题干，隐藏“单句命中”线索
- 强化跨模态桥接：强制必须结合图与文才能作答

> **实现方式（不改结构）**：
>
> - 在 `prompts.py` 增加一个 `build_revise_prompt(...)`
> - 在 `pipeline.py` 中当触发条件成立时调用 revise，并覆盖当前 step 或 final 草稿

---

### 4) Compress（压缩合并为最终高难 MCQ，对应你现有 Final Stage）

当达到阈值后，把多步链路压缩成一个最终 MCQ：

- 将部分中间结论“隐式化”（不直接明说）
- 仅保留必要背景 + 终局问题
- 输出仍保持你现有格式：`<question>...</question><answer>...</answer>`（答案为 A/B/C/D）

---

### 5) Final Solve + Reflection（闭环提升，对应你现有 Solve+Analysis）

- 用 `MODEL_SOLVE_FINAL`（或复用 `MODEL_SOLVE`）只输出 A/B/C/D 作答最终题
- 若答对：调用 `MODEL_ANALYSIS` 输出 3 条“难度提升指引”（作为下一轮 feedback）
- 若答错或 feedback 收敛：提前停止循环

---

## 停止条件（Episode / Round）

### Episode 内停止（进入 compress/final）的典型条件

- 达到 `MIN_HOPS`（例如 ≥2）且出现至少一次 `cross_modal_bridge=true`
- `medium_correct == false` 且 `strong_correct == true`（理想难度区间）
- 或达到 `MAX_STEPS_PER_ROUND`

### Round 层面提前停止

- Solve 答错（说明已足够难，或需要回滚策略）
- 反思反馈与上一轮一致（收敛）
- 达到 `MAX_ROUNDS`

---

## 目录结构（保持你当前结构）

- `main.py`：主入口；读取图片、准备文档上下文、控制多轮循环与停止条件
- `config.py`：模型与运行参数配置（可用环境变量覆盖）
- `api_client.py`：OpenAI 兼容接口调用（文本/视觉）
- `prompts.py`：Stage1/2/3/Final + revise/judge（可选）等 prompt 构建
- `pipeline.py`：阶段编排、Extension Loop、在线校验、revise、日志落盘
- `parsing.py`：`<question>/<answer>` 标签提取、选项字母解析（可扩展 evidence 标签）
- `schema.py`：`StageResult / StepResult / EpisodeResult` 数据结构

> 你之前列的 `agent.py/difficulty.py/evidence.py/utils.py` 是“可拆分增强项”。
> **本 README 版本默认不新增文件**，所有逻辑可先落在 `pipeline.py` 中。

---

## 运行方式

1) 准备图片：将待出题图片放在项目根目录，命名为 `test.png`（或在 `main.py` 中改路径）。
2) 运行：

```bash
python main.py
```


## 配置（环境变量覆盖，兼容你当前变量名）

你当前已有：

* `MODEL_STAGE_1 / MODEL_STAGE_2 / MODEL_STAGE_3`
* `MODEL_SUM（或 MODEL_STAGE_SUM）`
* `MODEL_SOLVE`
* `MODEL_ANALYSIS`
* `MAX_ROUNDS`
* `QUESTION_LOG_PATH`

强化版新增：

### 求解器

* `MODEL_SOLVE_MEDIUM`：中等求解器（用于难度标定，默认=`MODEL_SOLVE`）
* `MODEL_SOLVE_STRONG`：强求解器（用于可解性验证，默认=`MODEL_SOLVE`）
* `MODEL_SOLVE_FINAL`：最终求解模型（只输出 A/B/C/D，默认=`MODEL_SOLVE`）

### 扩链与阈值

* `MAX_STEPS_PER_ROUND`：每轮最大扩链步数（例如 6~10，默认可设为 6）
* `MIN_HOPS`：最小推理跳数（例如 2）
* `REQUIRE_CROSS_MODAL`：是否强制跨模态桥接（true/false，默认 true）

### 裁判

* `MODEL_JUDGE`：捷径/证据/干扰项检测模型（默认可复用 `MODEL_ANALYSIS`）

---

## 输出与日志（JSONL，兼容现有 question_log.jsonl）

仍按你当前方式把 Stage1/2/3/Final 的 `question/answer/raw` 追加写入 `QUESTION_LOG_PATH`，并建议**新增一个 steps 字段**来记录扩链结果。

### 建议的日志结构（每行一个 Episode）

* `round_id`
* `stage1` / `stage2` / `stage3` / `final`：保留你现有字段（兼容旧脚本）
* `steps`: `StepResult[]`（新增，记录 step_0..K）
* `difficulty_metrics`：
  * `medium_correct`, `strong_correct`
  * `difficulty_score`, `cross_modal_used`, `num_hops`
* `solver_final_pred`（A/B/C/D）
* `reflect_feedback`（三条可执行指引）
* `stop_reason`

### `StepResult`（新增/扩展 schema 建议）

* `k`
* `question`
* `answer`
* `evidence`：
  * `doc_spans`: [start,end] 或 段落/行号
  * `image_regions`: bbox/区域描述（若可用）
* `modal_use`: image/text/both
* `cross_modal_bridge`: bool
* `judge_flags`: `leakage/ambiguity/unsupported/distractors_weak` 等（可选）
* `raw`

---

## Prompt 设计要点（在 prompts.py 内落地）

### Stage1（视觉锚点）

* 只围绕图像中心区域锚点出题
* 要求答案可从图中定位（若需要文档也必须显式标记为 both）

### Stage2/Stage3（可复用为 Extend）

* 每次引入“新的文档关键点/新关系”，并明确证据 span
* 强制至少一次 `cross_modal_bridge=true`
* 输出结构化字段：`question/answer/evidence/modal_use/cross_modal_bridge`

### Final（Compress）

* 折叠中间结论，不要写“第一步/第二步”
* 输出最终 MCQ：题干 + 4 选项 + `<answer>` 字母

### Revise（去捷径）

* 禁止“一句文档原话直接=答案”的线索
* 强制跨模态桥接（若此前缺失）
* 干扰项同类同粒度，且看似合理但被条件排除

### Judge

* 检查：证据是否足够、是否存在单模态捷径、干扰项是否过弱

---

## 与旧版 Stage1/2/3/Final 的兼容说明

* 旧版仍然可以只跑 Stage1→Stage2→Stage3→Final
* 强化版在 `pipeline.py` 中把 Stage2/Stage3 当作“扩链模板”循环调用，从而实现 `step_3..K`
* 日志仍保留 Stage1/2/3/Final，新增 `steps` 不影响旧工具读取
