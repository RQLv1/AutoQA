# AutoQA

基于「图片 + 文档上下文」自动生成高难度单选题（MCQ）的多轮工作流，并通过“求解模型 + 反思模型”迭代提升题目难度。

## 工作流（当前实现）

入口：`test.py`。

每一轮（`MAX_ROUNDS`）包含 5 个阶段：

1. **Stage 1（出题）**：围绕图片“中心区域”的视觉锚点生成 MCQ（输出 `<question>...</question><answer>...</answer>`）。
2. **Stage 2（加难）**：在 Stage 1 的视觉锚点基础上，引入文档关键点，增加一层推理后生成更难 MCQ。
3. **Stage 3（再加难）**：继续在 Stage 2 的视觉锚点基础上，再引入另一关键点增加推理，生成更难 MCQ。
4. **Stage Final（合并）**：将前三步的链路整合为“多步推理”的高难度 MCQ。
5. **Solve + Analysis（闭环提升）**：
   - 用求解模型只输出选项字母（A/B/C/D）作答最终题；
   - 若求解模型答对，则调用反思模型总结“为何仍然简单”，输出 3 条“难度提升指引”，作为下一轮生成的 `feedback`；
   - 若求解模型答错，或 `feedback` 收敛（与上一轮相同），提前停止循环。

每轮会把四个阶段（Stage 1/2/3/Final）的 `question/answer/raw` 追加写入 `QUESTION_LOG_PATH`（默认 `question_log.jsonl`）。

## 目录结构

- `test.py`：主入口；读取图片、准备文档上下文、控制多轮循环与停止条件
- `config.py`：模型与运行参数配置（可用环境变量覆盖）
- `api_client.py`：OpenAI 兼容接口调用（文本/视觉）
- `prompts.py`：各阶段 prompt 构建
- `pipeline.py`：阶段编排、日志落盘、求解流程
- `parsing.py`：`<question>/<answer>` 标签提取、选项字母解析
- `schema.py`：`StageResult` 数据结构

## 运行

1) 准备图片：将待出题图片放在项目根目录，命名为 `test.png`（或在 `test.py` 中改路径）。  
2) 运行：

```bash
python test.py
```

## 配置

通过环境变量覆盖（默认值见 `config.py`）：

- `MODEL_STAGE_1` / `MODEL_STAGE_2` / `MODEL_STAGE_3`：前三个阶段出题模型
- `MODEL_SUM`（或 `MODEL_STAGE_SUM`）：最终合并阶段模型
- `MODEL_SOLVE`：求解模型
- `MODEL_ANALYSIS`：反思/难度提升指引模型
- `MAX_ROUNDS`：最大轮次（默认 5）
- `QUESTION_LOG_PATH`：日志路径（默认 `question_log.jsonl`）

## 输出

- 控制台：打印每次生成的原始输出（raw）、求解结果、以及每轮“难度提升指引”
- 文件：`QUESTION_LOG_PATH` 以 JSONL 形式追加保存每轮结果
