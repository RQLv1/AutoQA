# AutoQA（强化版）：基于图片 + 参考信息的高难度 MCQ 自动生成（保持现有工程结构）

AutoQA 是一个「图片为主 + 参考信息为辅」驱动的自动出题系统，用多轮迭代生成**高难度、可验证、强多模态依赖**的单选题（MCQ），并通过 Medium/Strong 求解器的对抗筛选提升难度（Medium 过滤，Strong 验证）。

关键约束：

- 出题阶段：题干必须围绕图片中心视觉锚点展开，参考信息仅供内部推理，不得在题干中显式提到或“引导读者查阅”。
- 求解阶段：求解器模型**只接收图片 + question**，不会喂入参考信息。
- 题干禁止出现引用措辞：如“结合文献 / 依据文献 / 文档 / 上下文 / context”等。

> **注意：本强化版保持入口不变**（`main.py`）。
> 目前项目按职责拆分为目录包：`utils/`（配置/解析/API/schema）、`pipeline/`（episode/logging/solvers/facts 门面）、`steps/`（每轮扩链）、`graph/`（Graph Mode）、`prompts/`（提示词）。
>
> - 把原 Stage1/2/3 变成 **可循环复用的 step 模板**（multi-hop extension）
> - 在每轮内支持多次扩链、必要时 step revise、最终 compress
> - 引入双求解器（Medium/Strong）在线校准难度（若未配置则自动退化为单求解器）

## 目标与原则

### 目标

1. **更具挑战性的推理链**：题目必须体现多跳推理（建议 ≥2 hops），尽量避免“单句命中答案”的检索式问题。
2. **更贴近多模态**：至少包含一次**跨模态桥接**（图像视觉证据 ↔ 题干中给出的事实/条件）。其中“事实/条件”可以来自参考信息抽取，但必须以**中性陈述**写入题干（不得提及来源），确保答题侧只用 `image + question` 仍可解题。
3. **答案可验证**：正确答案与关键推理证据必须能在给定图片中定位；若题干使用了来自参考信息的数字/定义/条件，需在日志中记录其证据 span/索引以便回溯（但不出现在题干的“引用措辞”中）。

### 强约束（硬性）

- 所有题目与正确答案 **不得依赖外部知识**。
- 最终题必须包含：4 个选项（A/B/C/D），且唯一正确答案。
- 选项必须“同类型同粒度”，避免明显离谱的干扰项。

---

## 工作流（对抗筛选版，兼容现有 Stage 结构）

入口：`main.py`

每一轮（`MAX_ROUNDS`）执行一个 Episode，由 `pipeline/`（门面包，`from pipeline import run_episode`）统一编排。整体仍保留“阶段式日志写法”（Stage1/2/3/Final + Difficulty），Episode 负责生成、评估与对抗式加难闭环，`main.py` 仅做最终筛选。在内部新增 **Extension Loop**：

### 0) 预处理：图像锚点与候选事实

- 从图片生成**视觉锚点**（中心区域对象/符号/结构/关系）与候选描述（anchor candidates）
- 从参考信息抽取**关键点/事实片段**（fact candidates，附带 span/段落索引）

> 说明：当前实现的预处理位于 `pipeline/pipeline_facts.py`（从参考信息抽取 fact candidates），视觉锚点主要通过 Stage prompt 引导输出。
>
> - 视觉锚点：由 Stage1 prompt 引导模型“只围绕中心区域锚点描述”即可
> - 参考信息关键点：用文本模型从参考信息中抽取若干关键句或要点（带行号/段落索引）

---

## 每轮 Episode 的执行流程

### 1) Extension Loop（多次扩链，复用 Stage1/2/3 模板）

在一个 Episode 内，允许多次扩链 `step_k (k=0..K)`，每步产出一个 `StepResult`：

- `question`: 子问题（中间问题，不一定是最终 MCQ）
- `answer_text`: 子问题答案的短实体/短短语（必须可在参考信息中定位）
- `answer_letter`: 若该 step 本身是 MCQ，对应正确选项字母（A/B/C/D）
- `evidence`: 证据定位（doc span/段落索引；可选 image 区域描述）
- `modal_use`: image/text/both
- `cross_modal_bridge`: bool（是否跨模态桥接）
- `raw`: 原始输出

**如何保持“现有 Stage1/2/3”但支持多次扩链？**

- `step_0`：使用 **Stage1 模板**（强视觉锚点，尽量只依赖图）
- `step_1`：使用 **Stage2 模板**（引入参考信息关键点 1，形成第一跳推理）
- `step_2`：使用 **Stage3 模板**（再引入参考信息关键点 2 或图中另一个关系，形成第二跳推理）
- `step_3..K`：**循环复用 Stage2/Stage3 模板**（或统一用一个 “EXTEND” prompt），每次强制：
  - 要么换新的参考信息关键点（不同段落/不同实体）
  - 要么换新的视觉锚点（同一中心区域内不同关系/符号/标注）
  - 并且至少一次 `cross_modal_bridge=true`（可由 step 校验触发 revise）

> 这样你无需新增 `agent.py` 文件：Agent 决策逻辑集中在 Episode/Step 编排中（`pipeline/pipeline_episode.py / steps/`），并由 `pipeline/` 统一导出。

当前默认仅保留 step-level revise（`steps/` 内触发），Final revise 在默认流程中关闭；Final 通过 Episode 内的 harden loop 做强制重写。

---

### 2) Compress（压缩合并为最终高难 MCQ，对应你现有 Final Stage）

当达到阈值后，把多步链路压缩成一个最终 MCQ：

- [ ] 将部分中间结论“隐式化”（不直接明说）
- [ ] 仅保留必要背景 + 终局问题
- [ ] 输出仍保持你现有格式：`<question>...</question><answer>...</answer><reasoning>...</reasoning>`（答案为 A/B/C/D）

---

### 2.5) Adversarial Refinement Loop（不难不休：计算优先加难）

Final 题目生成后，立即调用 `evaluate_difficulty` 做 Medium Attack：

- 若 `medium_correct == true`：进入“加难模式”，强制模型将题目改写为**视觉计算题**（计数差值、总和、比例、范围判断等）。
- 加难后再次评估；循环直到：
  - Medium 失败（`medium_correct == false`）→ 题目通过 Episode 内难度门槛
  - 或达到 `MAX_HARDEN_ATTEMPTS` → 保留当前版本（但 `main.py` 仍会做最终丢弃/入库判定）

加难模式是**强制重写 + 再攻击**的闭环，且以**计算与量化推理**为第一优先级，数值必须来自图像可验证证据（计数/读数/标签）。

---

### 3) Difficulty 评估（Medium/Strong）

对候选 Final 题进行在线评估（强化版中可能发生多次：初版 Final + 若干次加难后的 Final）：

- **Medium Solver**：难度过滤（Medium 能做对 → 题太简单）
- **Strong Solver**：可解性验证（Strong 能做对 → 难题可信）
- 可选附加检查：Text-Only / No-Image 盲测，用于发现文本捷径

> 注意：求解器输入仅包含图片与题目文本（question），不会提供参考信息；因此题目必须在图片层面有明确锚点，不能是纯文本可解的“参考信息检索题”。

系统维护 `difficulty_score`（可组合以下信号），以最后一次通过门槛（或达到上限）时的 metrics 作为记录结果：

- `medium_correct` vs `strong_correct`
- token 比、推理步数、信息分散度等 proxy（可选）

> **配置建议**：如需单一求解器，将 `MODEL_SOLVE_MEDIUM` 与 `MODEL_SOLVE_STRONG` 设置为同一模型即可。

---

### 4) Adversarial Filter（主循环筛选）

`main.py` 负责最终筛选逻辑（`run_episode()` 内已包含加难闭环）：

- `medium_correct == true` → 说明 Episode 内已加难但仍偏简单，直接废弃并继续生成
- `medium_correct == false` → 保留并记录，`strong_correct` 仅用于标记“中难/极难”
- 若 `strong_correct == false` → 触发 Review 智能体复核；复核为正确则追加到 `GENQA_PATH`

默认会一直生成直到找到固定数量的难题（见 `main.py` 的 `target_hard_questions`）。

---

## 停止条件（Episode / Round）

### Episode 内停止（进入 compress/final）的典型条件

- 达到 `MIN_HOPS`（例如 ≥2）且出现至少一次 `cross_modal_bridge=true`
- 或达到 `MAX_STEPS_PER_ROUND`
- Episode 内加难轮数达到 `MAX_HARDEN_ATTEMPTS`（输出当前版本）

### Round 层面提前停止

- 达到目标难题数量（`main.py` 的 `target_hard_questions`，默认 5）
- 达到最大尝试次数（`MAX_ROUNDS * 3`，见 `main.py`）

---

## 目录结构（保持你当前结构）

- `main.py`：主入口；读取图片、准备参考信息、控制多轮循环与停止条件
- `utils/config.py`：模型与运行参数配置（可用环境变量覆盖）
- `utils/api_client.py`：OpenAI 兼容接口调用（文本/视觉）
- `prompts/`：Stage1/2/3/Final + extend/revise 等 prompt 构建
- `pipeline/`：门面包（对外导出 `run_episode/save_round_questions/try_solve_question`）
- `pipeline/pipeline_episode.py`：Episode 编排（steps → compress → difficulty 评估）
- `steps/`：每轮的 Extension Loop（step 生成/校验/必要 revise），并提供 `derive_stage_results/step_to_dict`
- `pipeline/pipeline_facts.py`：参考信息 fact candidates 抽取与提示格式化
- `pipeline/pipeline_judge.py`：启发式对抗检查（选项完整性/长度偏置等，默认流程未启用）
- `pipeline/pipeline_solvers.py`：求解器调用、答案判定、难度指标评估
- `pipeline/pipeline_logging.py`：日志落盘（JSONL + 人类可读 JSON）
- `graph/pipeline_graph.py`：Graph Mode：全文知识点链总结、Local KG 构建（可选）
- `graph/pipeline_path_sampling.py`：Graph Mode：路径采样（可选）
- `utils/parsing.py`：`<question>/<answer>/<reasoning>` 标签提取、选项字母解析（可扩展 evidence 标签）
- `utils/schema.py`：`StageResult / StepResult / EpisodeResult` 数据结构

> 你之前列的 `agent.py/difficulty.py/evidence.py/utils.py` 仍属于“可进一步增强项”，当前以 `pipeline_*.py` 的拆分方式完成同等职责划分。

---

## 运行方式

1) 准备图片：将待出题图片放在项目根目录，命名为 `test.png`（或在 `main.py` 中改路径）。
2) 运行：

```bash
python main.py
```

运行时会在每次尝试打印过程信息：step 链路（题目/答案字母/答案短语/evidence）、最终题、以及各求解器输出；Medium 通过的题会被直接丢弃，直到筛出目标数量的难题为止。

## 配置（环境变量覆盖，兼容你当前变量名）

你当前已有：

* `MODEL_STAGE_1 / MODEL_STAGE_2 / MODEL_STAGE_3`
* `MODEL_SUM（或 MODEL_STAGE_SUM）`
* `MAX_ROUNDS`
* `QUESTION_LOG_PATH`
* `GENQA_PATH`
* `API_MAX_RETRIES`：API 最大重试次数（默认 5）
* `API_RETRY_SLEEP_SECONDS`：API 报错后等待秒数再重试（默认 5）

强化版新增：

### 求解器

* `MODEL_SOLVE_MEDIUM`：中等求解器（用于难度标定，默认值见 `utils/config.py`）
* `MODEL_SOLVE_STRONG`：强求解器（用于可解性验证，默认值见 `utils/config.py`）

### 扩链与阈值

* `MAX_STEPS_PER_ROUND`：每轮最大扩链步数（例如 6~10，默认可设为 6）
* `MIN_HOPS`：最小推理跳数（例如 2）
* `REQUIRE_CROSS_MODAL`：是否强制跨模态桥接（true/false，默认 true）

### 加难闭环（Episode 内）

* `MAX_HARDEN_ATTEMPTS`：Episode 内最大加难轮数（默认 3）
* `HARDEN_MODE`：加难策略（默认 `calc_first`）

### Operate Agents（计算/对比草稿）

每个 step/hop 生成后，会先调用两个 operate 智能体产出“下一步修改草稿”，并把草稿注入到下一步出题 Prompt 中（草稿只用于内部推理，不得出现在题干里）。

* `MODEL_OPERATE`：operate 默认模型（默认复用 `MODEL_STAGE_2`）
* `MODEL_OPERATE_DISTINCTION`：差异对比草稿模型（默认=`MODEL_OPERATE`）
* `MODEL_OPERATE_CALCULATION`：条件计算草稿模型（默认=`MODEL_OPERATE`）

当前出题风格偏向条件计算：优先把 `operate_calculation` 草稿落地为“数值/区间/等级”可验证题，只有确实无法计算时才退化为对比/异常检测。

### 裁判

* `MODEL_JUDGE`：捷径/证据/干扰项检测模型（可选，默认流程未启用）

### Review 智能体

* `MODEL_REVIEW`：当 Strong Solver 失败时用于复核题目正确性（默认=`MODEL_SOLVE_STRONG`）

### 验证（可选）

* `VERIFY_STRICT`：是否启用更严格的校验（如答案泄露粗检），默认 `false`

### Graph Mode（可选）

* `ENABLE_GRAPH_MODE`：是否启用 Local KG + 路径采样（默认 `true`，已实现基础版本）
* `REQUIRE_DISTINCT_SOURCES`：路径每跳尽量来自不同知识链来源（默认 `true`）
* `PATH_SAMPLER`：路径采样器名称（默认 `rbfs`）
* `MAX_SHORTCUT_EDGES`：允许的捷径边数量（默认 0）

---

## 输出与日志（JSONL + JSON）

默认写以下文件：

- `QUESTION_LOG_PATH`（默认 `question_log.jsonl`）：一行一个 Episode，便于流式追加与脚本处理（中文不再转义）。
- 同名 `.json`（例如 `question_log.json`）：层级化 + 缩进格式，便于人工阅读（数组形式累计保存）。
- `GENQA_PATH`（默认 `genqa.json`）：当 Strong Solver 失败时，经 Review 判定题目正确才会加入。

### 日志结构（每行一个 Episode）

* `round`
* `stage_1` / `stage_2` / `stage_3` / `stage_final`：保留阶段字段（兼容阶段式回看，含 reasoning）
* `steps`: `StepResult[]`（新增，记录 step_0..K）
* `final_question` / `final_answer` / `final_reasoning`：最终题题面、答案与推理过程（与 `stage_final` 冗余，便于直取）
* `difficulty_metrics`：
  * `medium_correct`, `strong_correct`
  * `strong_text_only_correct`（不看图仅看题干是否也能做对，用于检测纯文本捷径）
  * `strong_no_image_correct`（不传图片仅题干是否也能做对，用于额外检测文本捷径）
  * `difficulty_score`, `cross_modal_used`, `num_hops`
* `solver_final_pred`（Strong Solver 的选项字母，A/B/C/D）
* `solver_final_raw`（Strong Solver 原始输出，用于排查解析问题）
* `reflect_feedback`（筛选备注，如 `adversarial_filter_passed`）
* `stop_reason`
* `judge_flags`（预留：Episode 级汇总 flags）

### `StepResult`（新增/扩展 schema 建议）

* `k`
* `question`
* `answer_text`（短实体/短短语）
* `answer_letter`（A/B/C/D；若该 step 是 MCQ）
* `evidence`：
  * `doc_spans`: [start,end] 或 段落/行号
  * `image_regions`: bbox/区域描述（若可用）
* `modal_use`: image/text/both
* `cross_modal_bridge`: bool
* `judge_flags`: `leakage/ambiguity/unsupported/distractors_weak` 等（可选）
* `raw`

---

## Prompt 设计要点（在 prompts/ 内落地）

### Stage1（视觉锚点）

* 只围绕图像中心区域锚点出题（题干必须像“看图题”）
* 题干不得出现“文献/文档/上下文/context/结合文献/依据文献”等引用措辞

### Stage2/Stage3（可复用为 Extend）

* 每次引入“新的关键信息/新关系”，并明确证据 span（证据来自参考信息，但不得在题干中提及其来源）
* 强制至少一次 `cross_modal_bridge=true`（含义：题干必须同时依赖图像视觉证据 + 题干中给出的条件/事实）
* 计算优先：默认优先生成“条件计算”题（数值/区间/等级选项），无法形成可验证计算时才退化为对比/异常检测
* 输出结构化字段：`question/answer_letter/answer_text/evidence/modal_use/cross_modal_bridge`

### Final（Compress）

* 折叠中间结论，不要写“第一步/第二步”
* 输出最终 MCQ：题干 + 4 选项 + `<answer>` 字母 + `<reasoning>`（题目生成阶段）
* 题干必须围绕图片描述，不得出现“结合文献/依据文献/文档/上下文/context”等措辞

### Hardening Prompt（计算优先加难模板）

* 强制把“识别题”重写为“计算题/量化题”
* 必须满足：
  * 题目答案可由图像证据计算得到（计数、求和、差值、比例、阈值判断）
  * 干扰项为数字或数值区间且彼此接近，降低蒙对概率
  * 禁止外部知识；禁止把参考信息当成唯一证据来源（仍须以图像为核心证据）

### Revise（Step 级去捷径）

仅用于 step-level revise（`steps/` 内触发），Final revise 默认关闭；Final 通过 harden loop 做强制重写加难。

* 禁止“一句参考信息原话直接=答案”的线索
* 禁止 Text-Only 可解（避免题干泄漏/纯文本捷径）
* 强化图像锚点与约束（必要时把参考信息中的关键数据/定义以中性条件写进题干）
* 干扰项同类同粒度，且看似合理但被条件排除

### Judge（可选）

* 检查：证据是否足够、是否存在 Text-Only 捷径、干扰项是否过弱、以及启发式对抗检查（选项缺失/长度偏置等）
* 默认对抗筛选流程未启用

---

## 对齐 change.md 的实现状态（简表）

- 已实现：求解器只接收 `image + question`；Text-Only/No-Image 盲测；Stage/Final Prompt 强化（图像中心锚点 + 禁止引用措辞 + Hard Negatives）；Episode 内 calc-first harden loop + Medium/Strong 对抗筛选（Medium 过滤，Strong 验证）。
- 已实现：operate_distinction / operate_calculation 两个草稿智能体（每步生成后调用，并喂给下一步出题；计算优先）。
- 待明确：Blindfold（Image-Only）用于“强制依赖参考信息”的判据（与“求解器不接收参考信息”的约束存在目标冲突）。

---

## 与旧版 Stage1/2/3/Final 的兼容说明

* 旧版仍然可以只跑 Stage1→Stage2→Stage3→Final
* 强化版在 `steps/` 中把 Stage2/Stage3 当作“扩链模板”循环调用，从而实现 `step_3..K`
* 日志仍保留 Stage1/2/3/Final，新增 `steps` 不影响旧工具读取
