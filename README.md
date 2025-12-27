# AutoQA（强化版）：基于图片 + 参考信息的高难度多选题自动生成（保持现有工程结构）

AutoQA 是一个「图片为主 + 参考信息为辅」驱动的自动出题系统，用多轮迭代生成**高难度、可验证、强多模态依赖**的多选题，并通过 Medium/Strong 求解器的对抗筛选提升难度（Medium 过滤，Strong 验证）。

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
- 最终题必须包含：4-8 个按顺序排列的选项（A-H），答案可能包含多个正确选项（需列出全部）。
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

当前默认仅保留 step-level revise（`steps/` 内触发），Final revise 在默认流程中关闭。

---

### 2) Compress（压缩合并为最终高难 MCQ，对应你现有 Final Stage）

当达到阈值后，把多步链路压缩成一个最终 MCQ：

将部分中间结论“隐式化”（不直接明说）

仅保留必要背景 + 终局问题

压缩时会合并从第一个 Episode 的第一个 step 到当前 Episode 的最后一个 step 的所有 steps

输出仍保持你现有格式：`<question>...</question><answer>...</answer><reasoning>...</reasoning>`（答案为 A/B/C/D）

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

`main.py` 负责最终筛选逻辑（`run_episode()` 内包含 compress + difficulty 评估）：

- `medium_correct == true` → 视为简单题，Review 通过则写入 `GENQA_SIMPLE_PATH`
- `medium_correct == false && strong_correct == true` → 视为中等题，Review 通过则写入 `GENQA_MEDIUM_PATH`
- `medium_correct == false && strong_correct == false` → 视为困难题，Review 通过则写入 `GENQA_STRONG_PATH`
- 任意 Text-Only/No-Image 可解则直接废弃

默认会一直生成直到找到固定数量的困难题（见 `main.py` 的 `target_strong_questions`，默认 5）。

---

## 停止条件（Episode / Round）

### Episode 内停止（进入 compress/final）的典型条件

- 达到 `MIN_HOPS`（例如 ≥2）且出现至少一次 `cross_modal_bridge=true`
- 或达到 `MAX_STEPS_PER_ROUND`

### Round 层面提前停止

- 达到目标难题数量（`main.py` 的 `target_strong_questions`，默认 5）
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
- `pipeline/pipeline_logging.py`：日志写入接口（`question_log.*` 写入当前已禁用）
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
# 多选模式（默认）
python main.py --mode multi_select

# 单选模式
python main.py --mode single_select
```

运行时会在每次尝试打印过程信息：step 链路（题目/答案字母/答案短语/evidence）、最终题、以及各求解器输出；Medium 通过的题会被直接丢弃，直到筛出目标数量的难题为止。

## 配置（环境变量覆盖，兼容你当前变量名）

你当前已有：

* `MODEL_STAGE_1 / MODEL_STAGE_2 / MODEL_STAGE_3`
* `MODEL_SUM（或 MODEL_STAGE_SUM）`
* `MAX_ROUNDS`
* `GENQA_SIMPLE_PATH`
* `GENQA_MEDIUM_PATH`
* `GENQA_STRONG_PATH`
* `DETAILS_PATH`（默认 `details.json`）
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

## 输出与日志

默认写以下文件：

- `GENQA_SIMPLE_PATH`（默认 `genqa_simple.json`）：Medium 答对，经 Review 判定题目正确才会加入（包含 step/final）。
- `GENQA_MEDIUM_PATH`（默认 `genqa_medium.json`）：Medium 失败 & Strong 成功，经 Review 判定题目正确才会加入（包含 step/final）。
- `GENQA_STRONG_PATH`（默认 `genqa_strong.json`）：Medium 失败 & Strong 失败，经 Review 判定题目正确才会加入（包含 step/final）。
- `DETAILS_PATH`（默认 `details.json`）：记录 stdout 与事件，UTF-8 多行 JSON，便于阅读与定位。
- `question_log.jsonl/.json` 写入当前已禁用（如需恢复可在 `pipeline/pipeline_logging.py` 中恢复 `save_round_questions`）。

---

## Prompt 设计要点（在 prompts/ 内落地）

### Stage1（视觉锚点）

* 只围绕图像中心区域锚点出题（题干必须像“看图题”）
* 题干不得出现“文献/文档/上下文/context/结合文献/依据文献”等引用措辞

### Stage2/Stage3（可复用为 Extend）

* 每次引入“新的关键信息/新关系”，并明确证据 span（证据来自参考信息，但不得在题干中提及其来源）
* 强制至少一次 `cross_modal_bridge=true`（含义：题干必须同时依赖图像视觉证据 + 题干中给出的条件/事实）
* 计算优先：默认优先生成“条件计算”题（数值/区间/等级选项），无法形成可验证计算时才退化为对比/异常检测
* 输出结构化字段：`question/answer_letter/answer_text/evidence/modal_use/cross_modal_bridge/reasoning`

### Final（Compress）

* 折叠中间结论，不要写“第一步/第二步”
* 输出最终 MCQ：题干 + 4 选项 + `<answer>` 字母 + `<reasoning>`（题目生成阶段）
* 题干必须围绕图片描述，不得出现“结合文献/依据文献/文档/上下文/context”等措辞
* 压缩时合并从第一个 Episode 的第一个 step 到当前 Episode 的最后一个 step 的所有 steps

### Revise（Step 级去捷径）

仅用于 step-level revise（`steps/` 内触发），Final revise 默认关闭。

* 禁止“一句参考信息原话直接=答案”的线索
* 禁止 Text-Only 可解（避免题干泄漏/纯文本捷径）
* 强化图像锚点与约束（必要时把参考信息中的关键数据/定义以中性条件写进题干）
* 干扰项同类同粒度，且看似合理但被条件排除

### Judge（可选）

* 检查：证据是否足够、是否存在 Text-Only 捷径、干扰项是否过弱、以及启发式对抗检查（选项缺失/长度偏置等）
* 默认对抗筛选流程未启用

---

## 对齐 change.md 的实现状态（简表）

- 已实现：求解器只接收 `image + question`；Text-Only/No-Image 盲测；Stage/Final Prompt 强化（图像中心锚点 + 禁止引用措辞 + Hard Negatives）；Episode 内 compress + Medium/Strong 对抗筛选（Medium 过滤，Strong 验证）。
- 已实现：operate_distinction / operate_calculation 两个草稿智能体（每步生成后调用，并喂给下一步出题；计算优先）。
- 待明确：Blindfold（Image-Only）用于“强制依赖参考信息”的判据（与“求解器不接收参考信息”的约束存在目标冲突）。

---

## 与旧版 Stage1/2/3/Final 的兼容说明

* 旧版仍然可以只跑 Stage1→Stage2→Stage3→Final
* 强化版在 `steps/` 中把 Stage2/Stage3 当作“扩链模板”循环调用，从而实现 `step_3..K`
* 日志仍保留 Stage1/2/3/Final，新增 `steps` 不影响旧工具读取

```mermaid
flowchart TD
  %% ========== Styling ==========
  classDef agent fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
  classDef decision fill:#fff9c4,stroke:#fbc02d,stroke-width:2px,stroke-dasharray: 5 5;
  classDef process fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px;
  classDef storage fill:#e0f2f1,stroke:#00695c,stroke-width:2px;

  %% ========== Entry ==========
  subgraph MAIN["主控循环"]
    U[("外部输入\ncontext.txt + image.png")] --> M["main.py: main()\n循环生成 Episode"]
    M --> E["pipeline_episode.py: run_episode"]
  end

  %% ========== Vision Knowledge Agent ==========
  subgraph VK["智能体：VisualKnowledge (视觉锚点)"]
    direction TB
    E --> VK_in["输入: Prompt + Image"]
    VK_in --> VK_llm[["LLM: gemini-3-pro-preview"]]
    VK_llm --> VK_parse["解析: Description + Edges"]
    VK_parse --> VK_out["输出: Visual Summary"]
  end
  class VK agent

  %% ========== Step Generation ==========
  VK_out --> GS["steps_entry.py: generate_steps"]
  
  GS --> CHECK_MODE{"模式选择"}
  class CHECK_MODE decision

  %% Graph Mode Branch
  CHECK_MODE -->|ENABLE_GRAPH_MODE| GM["graph_mode.py: generate_steps_graph_mode"]
  GM --> EP

  %% Prompt Driven Branch
  CHECK_MODE -->|Prompt Driven| PD["prompt_driven.py: Loop k=0..MAX"]
  PD --> EP["选择 effective_previous_step"]

  subgraph OP["智能体：Operate Agents (算子草稿)"]
    EP --> OP_in["构造 Prompt\n(含 feedback/prev_step)"]
    OP_in --> OD_llm[["LLM: Distinction Draft"]]
    OP_in --> OC_llm[["LLM: Calculation Draft"]]
    OD_llm & OC_llm --> OP_out["Draft Context"]
  end
  class OP agent

  subgraph SG["智能体：Step Generator (生成子问题)"]
    OP_out --> SP["构造 Step Prompt\n(融合 Visual Summary)"]
    SP --> SG_llm[["LLM: Vision Model"]]
    SG_llm --> SG_parse["解析 StepResult"]
  end
  class SG agent

  %% ========== Obfuscate & Validate Loop ==========
  subgraph OB["智能体：Obfuscate (去词汇化)"]
    SG_parse --> OB_in["输入: 原始 Question + Options"]
    OB_in --> OB_llm[["LLM: Text Rewriter"]]
    OB_llm --> OB_out["Step (Obfuscated)"]
  end
  class OB agent

  OB_out --> VAL{"结构校验"}
  class VAL decision
  
  VAL -->|"失败: 缺选项/非数值"| RV["智能体: Revise Step"]
  class RV agent
  RV --> SG_parse

  %% ========== Solvers Gate (Intermediate) ==========
  VAL -->|通过| SOL_GATE{"Solver 门控\n(捷径检测)"}
  class SOL_GATE decision

  subgraph SOLVERS["智能体: Solvers (难度/捷径检测)"]
    SOL_GATE -->|Check| SNI[["Text-Only Solver"]]
    SOL_GATE -->|Check| MED[["Medium Vision Solver"]]
  end

  SNI -->|"Text-Only Correct"| RV_HARD["Revise: 增加视觉依赖"]
  RV_HARD --> SG_parse
  
  MED -->|"Vision Incorrect"| RV_EASY["Revise: 降低难度/澄清"]
  RV_EASY --> SG_parse

  SNI & MED -->|Pass| STEP_OK["Step 存入列表"]
  
  STEP_OK --> PD
  STEP_OK -->|"Graph Mode Next"| GM

  %% ========== Final Compress ==========
  PD -->|Done| FC_IN
  GM -->|Done| FC_IN

  subgraph FINAL["智能体：Final Compress (终题生成)"]
    FC_IN["输入: All Steps + Visual Summary"] --> FC_llm[["LLM: gemini-3-pro-preview"]]
    FC_llm --> FC_ob["Obfuscate Final Question"]
  end
  class FINAL agent

  %% ========== Final Refinement Loop ==========
  FC_ob --> FCHK{"终题评估"}
  class FCHK decision

  FCHK -->|"Text Solver 破解"| FH["Refine: Harden (增加混淆/依赖)"]
  FCHK -->|"缺少选项"| FR["Refine: Fix Format"]
  
  FCHK -->|"Check Pass"| REV

  subgraph REVIEW["智能体：Review (最终审核)"]
    REV["输入: Q + A + Image"] --> REV_llm[["LLM: gpt-5-mini"]]
    REV_llm --> REV_dec{"Decision"}
  end
  class REVIEW agent

  REV_dec -->|Incorrect| FF3["Refine: 根据 Review 意见修正"]
  FH & FR & FF3 --> FC_llm

  %% ========== Feedback & Save ==========
  REV_dec -->|"Correct / Max Retries"| DIFF["评估最终难度指标"]
  DIFF --> FBACK["生成 Reflection Feedback"]
  class FBACK process

  FBACK -->|"Feedback Loop"| M
  DIFF --> SAVE[("保存至数据集\n(Simple/Medium/Hard)")]
  class SAVE storage==
  U[外部输入\ncontext.txt + image.png] --> M[main.py: main()\n循环生成 Episode]
  M --> E[pipeline/pipeline_episode.py: run_episode(context,image,feedback,previous_final_question)]

  %% ========== Vision Knowledge Agent ==========
  subgraph VK["智能体：VisualKnowledge（视觉知识抽取）\n调用：call_vision_model(MODEL_VISION_KNOWLEDGE=gemini-3-pro-preview)"]
    VK_in[输入\nprompt(固定视觉描述模板) + image] --> VK_llm[LLM(vision)\nutils/api_client.py: call_vision_model]
    VK_llm --> VK_raw[输出 raw 文本\n<description>...<summary>...]
    VK_raw --> VK_parse[解析\nsummary + edges(从description抽边)]
    VK_parse --> VK_out[输出\nvisual_summary + visual_edges]
  end
  E --> VK

  %% ========== Step Generation ==========
  VK_out --> GS[steps/steps_entry.py: generate_steps()\n分支：GraphMode / PromptDriven]
  GS -->|ENABLE_GRAPH_MODE=true| GM[steps/graph_mode.py: generate_steps_graph_mode()\n(此处省略内部细节)]
  GS -->|否则| PD[steps/prompt_driven.py: generate_steps_prompt_driven()\nfor k in 0..MAX_STEPS_PER_ROUND]

  %% operate agents only when there is previous step (k>0 or inherited previous_final_question)
  PD --> EP[选择 effective_previous_step\n(k>0 用 steps[-1]\n或 k==0 继承 previous_final_question)]

  subgraph OP["智能体：Operate Agents（生成算子草稿）\n调用：call_vision_model"]
    EP --> OD_in[输入\nbuild_operate_distinction_prompt(context,prev_step,fact_hint,feedback,force_cross_modal)]
    OD_in --> OD_llm[LLM(vision)\nMODEL_OPERATE_DISTINCTION]
    OD_llm --> OD_out[输出\n<draft> distinction_draft]

    EP --> OC_in[输入\nbuild_operate_calculation_prompt(context,prev_step,fact_hint,feedback,force_cross_modal)]
    OC_in --> OC_llm[LLM(vision)\nMODEL_OPERATE_CALCULATION]
    OC_llm --> OC_out[输出\n<draft> calculation_draft]
  end

  %% Step LLM (vision)
  subgraph SG["智能体：Step Generator（生成子问题）\n调用：call_vision_model(MODEL_STAGE_1/2/3)"]
    OD_out --> SP[构建 step prompt\nbuild_stage1/2/3/extend_step_prompt(..., visual_summary)]
    OC_out --> SP
    SP --> SG_llm[LLM(vision)\nsteps/runner.py: run_step -> call_vision_model]
    SG_llm --> SG_raw[输出 raw\n含 <question>/<selections>/<answer>/<reasoning>]
    SG_raw --> SG_parse[解析为 StepResult\nquestion+selections, answer_letter, ...]
  end
  EP --> SP

  %% Obfuscate Agent (text)
  subgraph OB["智能体：Obfuscate（题干去词汇化/隐去细节）\n调用：call_text_model(MODEL_OBFUSCATE=MODEL_SUM)"]
    SG_parse --> OB_in[输入\nbuild_obfuscate_prompt(stem文本)\n(选项保持不变)]
    OB_in --> OB_llm[LLM(text)\nutils/api_client.py: call_text_model]
    OB_llm --> OB_out[输出\n改写后的 stem\n合并回 selections => step.question]
  end

  %% Solvers
  subgraph SOL["智能体：Solvers（难度评估/捷径检测）"]
    OB_out --> MED_in[输入\nbuild_solver_prompt(question)+image]
    MED_in --> MED_llm[LLM(vision)\nMODEL_SOLVE_MEDIUM=gpt-5-mini-0807-global]
    MED_llm --> MED_out[输出 raw + 解析 answer_letter]

    OB_out --> STXT_in[输入\nbuild_solver_prompt_text_only(question)]
    STXT_in --> STXT_llm[LLM(text)\nMODEL_SOLVE_STRONG=claude_sonnet4_5]
    STXT_llm --> STXT_out[输出 raw + 解析 answer_letter]

    OB_out --> STR_in[输入\nbuild_solver_prompt(question)+image]
    STR_in --> STR_llm[LLM(vision)\nMODEL_SOLVE_STRONG=claude_sonnet4_5]
    STR_llm --> STR_out[输出 raw + 解析 answer_letter]

    OB_out --> SNI_in[输入\nbuild_solver_prompt(question)\n(无图 no_image)]
    SNI_in --> SNI_llm[LLM(text/no-image)\nMODEL_SOLVE_STRONG=claude_sonnet4_5]
    SNI_llm --> SNI_out[输出 raw + 解析 answer_letter]
  end

  %% Step validation + revise loop
  OB_out --> VAL[非LLM：steps/validation.py: validate_step()\n可能返回 missing options / missing visual anchor / options not numeric/graded 等]
  VAL -->|needs_revision=True| RV

  subgraph RV["智能体：Revise Step（重写子问题）\n调用：call_vision_model(同 step 模型)"]
    RV_in[输入\nbuild_revise_prompt(context,step,reason,fact_hint,operate_drafts,force_cross_modal,visual_summary)+image]
    RV_in --> RV_llm[LLM(vision)\nsteps/runner.py: run_step]
    RV_llm --> RV_raw[输出 raw]
    RV_raw --> RV_parse[解析 StepResult]
    RV_parse --> RV_ob[再次 Obfuscate（同上 call_text_model）]
  end
  VAL -->|needs_revision=False| STEP_OK[Step 通过\n追加 steps[]\n更新 cross_modal_used]

  RV_ob --> STEP_OK

  STEP_OK --> PD
  PD -->|达到 min_steps 且满足 cross_modal| STEPS_OUT[输出 steps + cross_modal_used]

  %% ========== Final Compress ==========
  subgraph FINAL["智能体：Final（压缩生成最终题）\n调用：call_vision_model(MODEL_SUM=gemini-3-pro-preview)"]
    STEPS_OUT --> FC_in[输入\nbuild_final_compress_prompt(context,steps,feedback)+image]
    FC_in --> FC_llm[LLM(vision)\npipeline/pipeline_episode.py: run_final]
    FC_llm --> FC_raw[输出 raw\n<question><answer><reasoning>]
    FC_raw --> FC_parse[解析 StageResult]
    FC_parse --> FC_ob[Obfuscate question\ncall_text_model(MODEL_OBFUSCATE)]
  end

  %% ========== Final refinement loop ==========
  FC_ob --> FCHK{检查/评估}
  FCHK -->|缺 A-D 选项| FF1[pipeline/pipeline_final_refine.py: refine_final_question\nreason=format_missing_options]
  FCHK -->|text_only_veto=True| FH[prompts: build_final_harden_prompt -> run_final\n(vision MODEL_SUM) -> Obfuscate]
  FCHK -->|medium_correct=True| FF2[refine_final_question\nreason=medium_solved\n先调用 _get_medium_rationale(vision MODEL_SOLVE_MEDIUM)]
  FCHK -->|否则| REV

  subgraph REV["智能体：Review（审核正确性）\n调用：call_vision_model(MODEL_REVIEW=gpt-5-mini-0807-global)"]
    REV_in[输入\nbuild_review_prompt(question,answer,reasoning)+image]
    REV_in --> REV_llm[LLM(vision)\nreview_question()]
    REV_llm --> REV_out[输出 raw + decision(correct/incorrect/unknown)\n(incorrect 时含 <reason>)]
  end

  REV_out -->|incorrect 且可重试| FF3[refine_final_question\nreason=review_failed\n先 _get_review_feedback(vision MODEL_REVIEW)\n再 revision(vision MODEL_SUM)\n再 Obfuscate]
  REV_out -->|correct/unknown 或超次数| DONE_FINAL[final stage 输出]

  %% ========== Reflect feedback ==========
  DONE_FINAL --> DIFF[pipeline/pipeline_solvers.py: evaluate_difficulty\n调用 medium/strong/text-only/no-image solver 链路（同上）]
  DIFF --> FB_in[输入\nprompts/analysis.py: build_analysis_prompt(final_q,final_a,medium_raw)]
  FB_in --> FB_llm[LLM(text)\ncall_text_model(MODEL_SUM)]
  FB_llm --> FB_out[输出 reflect_feedback 字符串]

  %% ========== Loop back ==========
  FB_out --> M
  DONE_FINAL --> SAVE[保存 genqa_item\n按 difficulty_metrics 分流到 simple/medium/hard]
  SAVE --> M
```
