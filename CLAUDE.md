# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AutoQA is an adversarial multi-modal MCQ (multiple-choice question) generation system that creates high-difficulty questions requiring visual reasoning from images plus reference text. The system uses iterative multi-hop reasoning chains and dual-solver validation (Medium/Strong) to ensure questions are challenging but solvable.

**Core Constraint**: Questions must be image-centric. Solvers receive only `image + question` (no reference text), so questions cannot rely on text-only shortcuts. Reference information is used during generation to extract facts that are incorporated as neutral statements in the question stem, but the question must never mention "文献/文档/context" or similar reference terms.

## Running the System

```bash
# Main workflow: generates questions until target is met
python main.py

# Requires:
# - test.png (or data/test.png): input image
# - context.txt (or data/context.txt): reference text for fact extraction

# Syntax check all modules
python -m py_compile $(find . -name "*.py" -not -path "./env/*" | tr '\n' ' ')
```

## Architecture Overview

### 1. Main Loop (`main.py`)

Orchestrates adversarial filtering:
- Runs episodes until collecting target number of hard questions (default: 5)
- Filters by difficulty: Medium solver fails → keep, Medium succeeds → discard
- Classifies into Simple/Medium/Hard based on Medium/Strong solver results
- Uses Review agent to verify correctness before saving

### 2. Episode Structure (`pipeline/pipeline_episode.py`)

Each episode generates one candidate question through:

**A. Visual Knowledge Extraction** (`pipeline/pipeline_vision_knowledge.py`)
- Extracts visual anchors and knowledge edges from image
- Builds entity pool and relationships for graph mode

**B. Step Generation** (`steps/`)
- Entry point: `generate_steps()` dispatches to either:
  - **Graph Mode** (`steps/graph_mode.py`): Uses knowledge graph + path sampling to construct multi-hop reasoning chains
  - **Prompt-Driven Mode** (`steps/prompt_driven.py`): Uses Stage1→Stage2→Stage3 template progression
- Both modes produce `list[StepResult]`, each representing one reasoning hop with:
  - `question`: sub-question text
  - `answer_text`: short answer entity/phrase
  - `answer_letter`: correct option (A/B/C/D) if MCQ
  - `evidence`: evidence location (doc span, image region)
  - `modal_use`: "image"/"text"/"both"
  - `cross_modal_bridge`: whether step bridges image ↔ text reasoning

**C. Operate Agents** (run after each step)
- `operate_calculation_agent`: generates calculation-based draft for next step
- `operate_distinction_agent`: generates comparison/distinction draft for next step
- Drafts are injected into next step's prompt (internal reasoning only, never appear in question stem)
- Default preference: calculation-based questions over comparison questions

**D. Compression** (`prompts/final.py`)
- `build_final_compress_prompt()`: merges all steps into single final MCQ
- Hides intermediate reasoning, keeps necessary context + terminal question
- Output: 4-option MCQ with unique correct answer

**E. Difficulty Evaluation** (`pipeline/pipeline_solvers.py`)
- **Medium Solver** (`MODEL_SOLVE_MEDIUM`): filters too-easy questions
- **Strong Solver** (`MODEL_SOLVE_STRONG`): validates solvability
- **Text-Only Test**: detects text shortcuts (question answerable without image)
- **No-Image Test**: confirms image dependency

**F. Review Agent** (`pipeline/pipeline_review.py`)
- When Strong solver fails, Review agent checks if question is actually correct
- Only questions passing review are saved to output files

### 3. Two Generation Modes

**Graph Mode** (default, `ENABLE_GRAPH_MODE=true`):
1. Builds local knowledge graph from reference text + image
2. Samples multi-hop paths through graph (configurable sampler: `PATH_SAMPLER=rbfs`)
3. Converts each edge in path to a reasoning step
4. Ensures distinct sources per hop (if `REQUIRE_DISTINCT_SOURCES=true`)

**Prompt-Driven Mode** (`ENABLE_GRAPH_MODE=false`):
1. Extracts fact candidates from reference text
2. Step 0: Stage1 template (pure visual anchor)
3. Step 1: Stage2 template (introduces first fact)
4. Step 2: Stage3 template (introduces second fact)
5. Step 3+: Cycles through Stage2/Stage3/Extend templates
6. Each step validated and revised if needed

Both modes enforce:
- Minimum hops: `MIN_HOPS` (default: 5)
- Maximum steps: `MAX_STEPS_PER_ROUND` (default: 6)
- At least one `cross_modal_bridge=true` step

### 4. Key Validation & Quality Controls

**Step-Level Validation** (`steps/validation.py`):
- Checks answer completeness, evidence validity
- Filters low-quality entity matching questions
- Triggers step revision if validation fails

**Question Obfuscation** (`steps/obfuscate_agent.py`):
- Rewrites question stems to hide explicit details
- Prevents direct answer leakage
- Applied to both individual steps and final questions

**Judge Checks** (`pipeline/pipeline_judge.py`, optional):
- Detects answer leakage, length bias, missing options
- Not enabled in default flow

## Configuration (`utils/config.py`)

All settings support environment variable overrides:

**Generation Models**:
- `MODEL_STAGE_1/2/3`: step generation models
- `MODEL_SUM`: compression/summarization model
- `MODEL_VISION_KNOWLEDGE`: visual knowledge extraction
- `MODEL_OPERATE`: operate agent default model
- `MODEL_OPERATE_CALCULATION/DISTINCTION`: specific operate agents

**Solver Models**:
- `MODEL_SOLVE_MEDIUM`: difficulty filter (default: gpt-5-mini)
- `MODEL_SOLVE_STRONG`: solvability validator (default: claude_sonnet4_5)
- `MODEL_REVIEW`: correctness verifier

**Generation Control**:
- `MAX_ROUNDS`: maximum generation rounds (default: 10)
- `MAX_STEPS_PER_ROUND`: max reasoning hops per episode (default: 6)
- `MIN_HOPS`: minimum required hops (default: 5)
- `REQUIRE_CROSS_MODAL`: enforce cross-modal bridging (default: true)

**Graph Mode**:
- `ENABLE_GRAPH_MODE`: enable graph-based generation (default: true)
- `DOC_CHUNK_WORDS`: document chunking size (default: 160)
- `REQUIRE_DISTINCT_SOURCES`: enforce different sources per hop (default: false)
- `PATH_SAMPLER`: path sampling algorithm (default: "rbfs")
- `MAX_SHORTCUT_EDGES`: allowed shortcut edges (default: 10)

**Output**:
- `GENQA_SIMPLE_PATH`: Medium fails, Strong passes (default: genqa_simple.json)
- `GENQA_MEDIUM_PATH`: Medium fails, Strong fails (default: genqa_medium.json)
- `GENQA_HARD_PATH`: both solvers fail (default: genqa_hard.json)
- `DETAILS_PATH`: execution log with stdout events (default: details.json)

## Module Organization

```
utils/          # Core infrastructure
├── config.py         # All configuration constants
├── api_client.py     # OpenAI-compatible API calls (vision/text)
├── schema.py         # Data structures (StageResult, StepResult, EpisodeResult)
├── parsing.py        # XML tag extraction (<question>, <answer>, etc.)
├── details_logger.py # Structured logging to DETAILS_PATH
├── terminal.py       # Console output formatting
├── mcq.py           # MCQ format validation (A/B/C/D options)
└── genqa.py         # Output file writing

pipeline/       # Episode orchestration
├── pipeline_episode.py         # Main episode flow
├── pipeline_vision_knowledge.py # Visual knowledge extraction
├── pipeline_facts.py           # Reference text fact extraction
├── pipeline_solvers.py         # Solver invocation & grading
├── pipeline_review.py          # Review agent
├── pipeline_final_refine.py    # Final question refinement
├── pipeline_judge.py           # Optional adversarial checks
└── pipeline_logging.py         # Question logging (currently disabled)

steps/          # Step generation
├── steps_entry.py              # Dispatcher (graph vs prompt-driven)
├── graph_mode.py               # Graph-based step generation
├── prompt_driven.py            # Template-based step generation
├── runner.py                   # Step execution helpers
├── validation.py               # Step validation logic
├── quality.py                  # Quality filters
├── stage_compat.py             # Stage1/2/3 compatibility layer
├── operate_calculation_agent.py # Calculation draft generation
├── operate_distinction_agent.py # Comparison draft generation
└── obfuscate_agent.py          # Question obfuscation

graph/          # Knowledge graph mode
├── pipeline_graph.py           # KG construction & caching
└── pipeline_path_sampling.py   # Multi-hop path sampling

prompts/        # Prompt templates
├── steps.py                    # Stage1/2/3/Extend/Revise prompts
├── final.py                    # Compression & hardening prompts
├── operate_calculation.py      # Calculation draft prompt
├── operate_distinction.py      # Distinction draft prompt
├── obfuscate.py               # Obfuscation prompt
├── review.py                  # Review & verification prompts
├── solver.py                  # Solver system prompts
├── facts.py                   # Fact extraction prompt
└── analysis.py                # Analysis prompt
```

## Data Structures

**StepResult**: Single reasoning hop
- Produced by `steps/graph_mode.py` or `steps/prompt_driven.py`
- Contains question, answer, evidence, modal usage, cross-modal flag

**StageResult**: Single model output
- Legacy structure for Stage1/2/3/Final compatibility
- Contains question, answer, raw output, reasoning

**EpisodeResult**: Complete generation attempt
- Aggregates: steps, stage results, difficulty metrics, review results
- Returned by `run_episode()` to `main.py`

## Important Constraints

1. **Image-Centric Questions**: Question stems must describe visual anchors. Never use phrases like "根据文献" or "结合上下文".

2. **Solver Input**: Solvers receive ONLY `image + question`. No reference text. Questions must be solvable from image alone (facts extracted from reference text must be stated neutrally in question).

3. **Cross-Modal Bridge**: At least one step must bridge visual evidence ↔ textual facts/conditions stated in question.

4. **Option Quality**:
   - All 4 options must be same type, same granularity
   - Avoid obviously wrong distractors
   - For numeric options: use same units, similar magnitude (max/min ≤ 1.25x)

5. **Text-Only Filter**: Questions answerable without the image are discarded.

6. **Calculation Preference**: System prefers quantifiable calculation-based questions over qualitative comparison questions.

## Debugging

- **Execution Log**: `details.json` contains all stdout and structured events
- **Step Chain**: Each episode prints step-by-step reasoning chain with evidence
- **Solver Outputs**: Medium/Strong solver responses printed for each attempt
- **Review Decisions**: Review agent reasoning shown when Strong solver fails

## Recent Changes (from change.md)

Focus areas for prompt hardening:
1. Prohibit "explanatory options" - options should be pure values/labels (≤12 chars), no descriptions
2. Enforce verifiable visual quantification - use countable/grid-estimatable evidence
3. Prohibit fabricated formulas - only use relationships from reference text
4. Ensure numeric options are close/similar - avoid obvious outliers
