# AutoQA（强化版）：基于图文上下文的高难度 MCQ 自动生成（保持现有工程结构）

AutoQA 是一个「图片 + 文档上下文」驱动的自动出题系统，用多轮迭代生成**高难度、可验证、强多模态依赖**的单选题（MCQ），并通过“求解模型 + 反思模型 + 过程裁判（可选）”闭环提升难度。

> **注意：本强化版保持入口不变**（`main.py`）。
> 当前实现已拆分为目录包：`utils/`（配置/解析/API/schema）、`pipeline/`（episode/logging/solvers/facts）、`steps/`（每轮扩链）、`graph/`（Graph Mode）、`prompts/`（提示词）。

---

## 目标与原则

### 目标

1. **更具挑战性的推理链**：题目必须体现多跳推理（建议 ≥2 hops），尽量避免“单句命中答案”的检索式问题。
2. **更贴近多模态**：至少包含一次**跨模态桥接**（图 → 文 或 文 → 图），避免只看其中一个模态即可解题。
3. **答案可验证**：正确答案与关键推理证据必须能在给定图文上下文中定位（建议记录证据 span/段落索引；图可记录区域描述或 bbox）。

### 强约束（硬性）

- 所有题目与正确答案 **不得依赖外部知识**（默认仅使用给定 PDF/文档与图片上下文）。
- 最终题必须包含：4 个选项（A/B/C/D），且唯一正确答案。
- 选项必须“同类型同粒度”，避免明显离谱的干扰项；每个干扰项都要“看似合理”，但可被上下文中的某个条件排除。

## 工作流（强化版，兼容现有 Stage 结构）

入口：`main.py`

每一轮（`MAX_ROUNDS`）执行一个 Episode，由 `pipeline/`（门面包，`from pipeline import run_episode`）统一编排。对外仍保留“阶段式日志写法”（Stage1/2/3/Final + Solve/Analysis），但在内部新增 **Extension Loop**，并可选启用 **Graph Mode**（路径采样驱动）。

### 0) 预处理：图文锚点与候选事实

- **视觉锚点**：由 Stage1/Extend prompt 引导模型只描述/只出题于“图片中心区域的对象/符号/结构/关系”（anchor candidates）。
- **知识点链**：直接基于全文总结多条“串联的知识点链”，用于构建 Local KG。
- **事实候选**（两种策略二选一，或同时运行）：
  - Prompt 提取：从全文抽取“关键点/事实片段”（fact candidates，带 span/段落索引）。
  - Graph Mode：从全文总结知识点链并构建 Local KG。

> 说明：当前实现把文本关键点抽取放在 `pipeline/pipeline_facts.py`；Graph Mode 使用 `graph/pipeline_graph.py` 负责 context→知识点链→KG。

### 1) Extension Loop（多次扩链：Prompt-driven 或 Graph Mode 产出 steps）

在一个 Episode 内允许多次扩链 `step_k (k=0..K)`，每步产出一个 `StepResult`：

- `question`: 子问题（中间问题，不一定是最终 MCQ）
- `answer_text`: 子问题答案（短实体/短短语，必须可在上下文中定位）
- `evidence`: 证据定位（doc span/段落索引；可选 image 区域描述/bbox）
- `modal_use`: image/text/both
- `cross_modal_bridge`: bool（是否跨模态桥接）
- `raw`: 原始输出

**两种产出 steps 的方式：**

A) **Prompt-driven（默认，保持你现有 Stage1/2/3 复用方式）**

- `step_0`：Stage1 模板（强视觉锚点，尽量只依赖图）
- `step_1`：Stage2 模板（引入文档关键点 1）
- `step_2`：Stage3 模板（引入关键点 2 或图中另一关系）
- `step_3..K`：循环复用 Stage2/Stage3 模板（或统一 EXTEND prompt），每次强制：
  - 换新的文档关键点（不同知识点/实体），或换新的视觉锚点（同中心区域内不同关系）
  - 至少一次 `cross_modal_bridge=true`（可由 judge 检测并强制 revise）

B) **Graph Mode（推荐用于长文档，路径采样更稳定地产生“真多跳”）**

- **路径采样**：从 Local KG 采样长度为 `K` 的路径，尽量避免重复来源。
- **1-hop 生成**：对路径的每条边先生成 1-hop 子问题（答案=entity1），并逐条验证可证据定位、无歧义、题干不包含答案。
- **reverse-chaining 聚合**：从路径尾部的子问题开始反向串联，生成一个“自然的多跳问题骨架”；然后再进入本仓库的 revise/compress。

> 这一步与“论文的 bottom-up + reverse-chaining”一致：先确保每跳都成立，再合成最终多跳题。

### 2) Solve-in-the-loop（在线校验与难度标定）

对每个 `step` 以及候选 Final 题进行在线评估（可对 Final 更严格）：

- **Strong Solver**：验证“可解性/一致性”
  - Strong 都答不对：大概率题坏/证据不足 → 触发 revise 或回滚
- **Medium Solver**：衡量难度增长
  - 理想状态：Medium 开始失败，而 Strong 仍可成功（难度有效提升）

系统维护 `difficulty_score`（可组合以下信号）：

- `medium_correct` vs `strong_correct`
- 一致性投票（多次采样/多模型一致性，可选）
- token 比、推理步数、信息分散度、distinct sources 数等 proxy（可选）

> **兼容策略**：未设置 `MODEL_SOLVE_STRONG/MEDIUM` 时，可默认等于 `MODEL_SOLVE`，接口不变。

### 3) Judge / Verify（证据与捷径检测）

裁判模型/规则做三件事（每次 step 生成后、以及 Final 前都可跑）：

1. **证据覆盖**：证据是否足以支持答案；doc span 是否存在且与题干匹配。
2. **单模态捷径**：是否只看图/只看文即可直接命中（若是 → 触发 revise 强制跨模态）。
3. **干扰项质量**：选项是否同类同粒度，是否存在“明显离谱”或“过弱干扰项”。

可额外加入两类“论文式过滤”：

- **答案泄露检测**：答案词面是否出现在题干或选项描述中（可用大小写/同义归一化后匹配）。
- **多解风险检测**：是否存在多个上下文片段支持不同候选答案（触发 revise 或直接丢弃）。

### 4) Revise（纠错 / 去捷径）

触发条件（示例）：

- Strong solver 失败或出现多解/歧义
- 存在明显捷径：只看文或只看图即可直接命中答案
- 证据无法定位或引用不一致
- 选项不均衡、干扰项过弱

Revise 目标：

- 修复歧义、补齐证据链
- 改写题干，隐藏“单句命中”线索
- 强化跨模态桥接：强制必须结合图与文才能作答
- 若启用 Graph Mode：必要时替换路径/替换某一跳的 source，确保信息分散

### 5) Compress（压缩合并为最终高难 MCQ）

当达到阈值后，把多步链路压缩成一个最终 MCQ：

- 将部分中间结论“隐式化”（不直接明说）
- 仅保留必要背景 + 终局问题
- 输出保持你现有格式：`<question>...</question><answer>...</answer>`（答案为 A/B/C/D）

> 推荐实现：沿用 reverse-chaining 的思想，把“尾部信息”放在题干前半作背景，把“头部信息”变成最终要问的对象，减少答案泄露。

### 6) Final Solve + Reflection（闭环提升）

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

## 目录结构（保持你当前结构 + 可选增强项）

**核心（保持不变）**

- `main.py`：主入口；读取图片、准备文档上下文、控制多轮循环与停止条件
- `utils/config.py`：模型与运行参数配置（可用环境变量覆盖）
- `utils/api_client.py`：OpenAI 兼容接口调用（文本/视觉）
- `prompts/`：Stage1/2/3/Final + extend/revise/judge 等 prompt 构建
- `pipeline/`：门面包（对外导出 `run_episode/save_round_questions/try_solve_question`）
- `utils/parsing.py`：`<question>/<answer>` 标签提取、选项字母解析（建议扩展 evidence 标签）
- `utils/schema.py`：`StageResult / StepResult / EpisodeResult` 数据结构

**建议拆分（便于演进，但不要求一次到位）**

- `pipeline/pipeline_episode.py`：Episode 编排（steps → revise → compress → final solve → logging）
- `steps/`：Extension Loop（step 生成/校验/必要 revise）与 `StepResult` 构造
- `pipeline/pipeline_facts.py`：文档 fact candidates 抽取与提示格式化
- `pipeline/pipeline_solvers.py`：求解器调用、答案判定、难度指标评估
- `pipeline/pipeline_logging.py`：日志落盘（JSONL + 人类可读 JSON）

**论文思路落地的可选增强模块（推荐逐步加）**

- `graph/pipeline_graph.py`：全文 → 知识点链 → Local KG
- `graph/pipeline_path_sampling.py`：随机化 BFS 路径采样（支持“distinct source”约束）
- `pipeline_verify.py`：1-hop / multi-hop 的 verifier（可复用 `MODEL_JUDGE`）
- `pipeline_shortcut.py`：捷径边检测（是否存在 head↔tail 直接证据导致伪多跳）
- `text_chunker.py`：段落/词数切分与 span 映射工具（可选，当前 Graph Mode 不使用）
- `normalization.py`：实体归一化（大小写/符号/缩写）辅助“答案泄露/多解”检测

---

## 配置（环境变量覆盖，兼容你当前变量名）

默认值见 `utils/config.py`。

你当前已有：

- `MODEL_STAGE_1 / MODEL_STAGE_2 / MODEL_STAGE_3`
- `MODEL_SUM（或 MODEL_STAGE_SUM）`
- `MODEL_SOLVE`
- `MODEL_ANALYSIS`
- `MAX_ROUNDS`
- `QUESTION_LOG_PATH`

强化版新增（建议）：

### 求解器

- `MODEL_SOLVE_MEDIUM`：中等求解器（用于难度标定，默认=`MODEL_SOLVE`）
- `MODEL_SOLVE_STRONG`：强求解器（用于可解性验证，默认=`MODEL_SOLVE`）
- `MODEL_SOLVE_FINAL`：最终求解模型（只输出 A/B/C/D，默认=`MODEL_SOLVE`）

### 扩链与阈值

- `MAX_STEPS_PER_ROUND`：每轮最大扩链步数（例如 6~10）
- `MIN_HOPS`：最小推理跳数（例如 2）
- `REQUIRE_CROSS_MODAL`：是否强制跨模态桥接（true/false，默认 true）

### 裁判 / 验证

- `MODEL_JUDGE`：捷径/证据/干扰项检测模型（默认可复用 `MODEL_ANALYSIS`）
- `VERIFY_STRICT`：是否启用“答案泄露/多解风险/证据覆盖”严格校验（true/false）

### Graph Mode

- `ENABLE_GRAPH_MODE`：是否启用 Local KG + 路径采样（true/false，默认 false）
- `REQUIRE_DISTINCT_SOURCES`：路径每跳尽量来自不同知识链来源（true/false，默认 true）
- `PATH_SAMPLER`：`rbfs` / `random_walk` 等（默认 `rbfs`）
- `MAX_SHORTCUT_EDGES`：允许的捷径边数量（默认 0）

---

## 运行方式

1) 准备图片：将待出题图片放在项目根目录，命名为 `test.png`（或在 `main.py` 中改路径）。
2) 运行：

```bash
python main.py
```

运行时会在每一轮打印过程信息：step 链路（题目/答案/evidence）、最终题、以及各求解器输出与反馈。

---

## 输出与日志（JSONL + JSON）

默认写两个文件：

- `QUESTION_LOG_PATH`（默认 `question_log.jsonl`）：一行一个 Episode，便于流式追加与脚本处理（建议中文不转义）。
- 同名 `.json`（例如 `question_log.json`）：层级化 + 缩进格式，便于人工阅读（数组形式累计保存）。

### 日志结构（每行一个 Episode）

建议字段（兼容你现有字段名，并逐步增量扩展）：

- `round`
- `stage_1 / stage_2 / stage_3 / stage_final`：保留阶段字段（兼容阶段式回看）
- `steps`: `StepResult[]`（记录 step_0..K）
- `final_question / final_answer`（answer 为 A/B/C/D）
- `difficulty_metrics`：
  - `medium_correct`, `strong_correct`
  - `difficulty_score`, `cross_modal_used`, `num_hops`
  - **建议新增**：`distinct_sources`, `total_context_tokens`, `pooled_hop_tokens`, `shortcut_edges`
- `solver_final_pred`（A/B/C/D）
- `reflect_feedback`（三条可执行指引）
- `stop_reason`
- `judge_flags`（Episode 级汇总：`leakage/ambiguity/unsupported/distractors_weak/shortcut` 等）

### `StepResult`（建议扩展 schema）

- `k`
- `question`
- `answer_text`（短实体/短短语；MCQ 时也建议存）
- `answer_letter`（若该 step 本身是 MCQ，可选）
- `evidence`：
  - `doc_spans`: [start,end] 或 段落/行号/上下文位置标记
  - `image_regions`: bbox/区域描述（若可用）
- `modal_use`: image/text/both
- `cross_modal_bridge`: bool
- `raw`
- `judge_flags`：`leakage/ambiguity/unsupported/distractors_weak/shortcut` 等（可选）

---

## Prompt 设计要点（在 prompts/ 内落地）

### 1) 1-hop 子问题生成（Graph Mode / 也可用于 Prompt-driven 的 step 生成）

关键约束（强烈建议写进 prompt）：

- **不要在题干中出现答案**（包括同义词/缩写，尽量做归一化检测）
- 题目必须能**仅依赖给定 text**回答
- 不要提及“在论文/表格/摘要/图中”等元叙事（避免把位置提示当捷径）
- 若关系不够具体导致多解，必须用 text 中的描述补充限定，使答案唯一

### 2) Multi-hop 聚合（reverse-chaining）

- 输入：多个 1-hop Q/A（已验证）
- 输出：一个连贯的多跳问题
- 约束：从**最后一个问题**开始反向串联，最终答案对应**第一个问题**的答案；任何中间答案都不能直接出现在题干中

### 3) Revise（去捷径）

- 禁止“一句原文直接=答案”的线索
- 强制跨模态桥接（若此前缺失）
- 干扰项同类同粒度，且看似合理但被条件排除

### 4) Judge / Verify（证据与捷径检测）

- 证据是否足够支持正确答案（必须可定位）
- 是否存在单模态捷径（只看图/只看文即可做）
- 干扰项是否过弱/异类
- （可选）是否存在捷径边导致伪多跳

---

## 与旧版 Stage1/2/3/Final 的兼容说明

- 旧版仍然可以只跑 Stage1→Stage2→Stage3→Final
- 强化版在 `steps/` 中把 Stage2/Stage3 当作“扩链模板”循环调用，从而实现 `step_3..K`
- 日志仍保留 Stage1/2/3/Final，新增 `steps` 不影响旧工具读取
- 若启用 Graph Mode：可把“采样路径+生成 1-hop”当作 `steps` 的来源，后续 revise/compress/solve/logging 流程保持不变
