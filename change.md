
### 修改方案：支持多选模式 (Multiple Select) 与 A-H 选项

#### 1. 修改 Prompt 生成 (提示词)

 **目标** ：明确告知模型生成多选题，支持 A-H 选项范围，并移除互斥限制。

* **文件** : `rqlv1/autoqa/AutoQA-rqlv/prompts/final.py`
* **函数** : `build_final_compress_prompt`, `build_final_revise_prompt`, `build_final_harden_prompt`, `build_final_targeted_revise_prompt`
* **修改点** :
  *  **题型定义** : 将 `单选题(MCQ)` 修改为 `多选题(Multiple Select Question)`。
  *  **选项范围** : 明确指示 `选项范围为 A-H (至少4个，最多8个)`。
  *  **答案格式** : 修改 `<answer>` 说明，允许输出如 `AC`, `A,C,E` 等组合。
  *  **生成约束** :
  * 删除“四个数值选项”的硬性数量限制，改为“选项数量 4-8 个”。
  * 删除“互斥”相关暗示，明确“可能有一个或多个正确选项”。
  * 保留“干扰项设计”逻辑，但需适配多选（例如：漏选、多选包含干扰项）。
* **文件** : `rqlv1/autoqa/AutoQA-rqlv/prompts/solver.py`
* **函数** : `build_solver_prompt`, `build_solver_prompt_text_only`
* **修改点** :
  *  **任务说明** : 增加 `这是一道多选题，请选择所有正确的选项`。
  *  **输出格式** : 允许 `<answer>A,C</answer>` 或 `<answer>AC</answer>`。

#### 2. 修改答案解析逻辑 (Parsing)

 **目标** ：正确提取形如 "A, C" 或 "AC" 的多选答案，并标准化为 "AC"。

* **文件** : `rqlv1/autoqa/AutoQA-rqlv/utils/parsing.py`
* **修改全局常量/正则** (如有): 确保所有涉及选项的正则支持 `[A-H]` 而非仅 `[A-D]`。
* **函数** : `parse_option_letter_optional`, `_find_option_letter`, `extract_option_text`
* **修改点** :
  *  **正则扩展** : 将 `r"[A-D]"` 扩展为 `r"[A-H]"`。
  *  **提取逻辑** : 不再只返回匹配到的最后一个字母，而是提取所有出现的字母， **去重并按字母顺序排序** 。
  *  **代码示例** :
  **Python**

  ```
  def parse_option_letters(text: str) -> str:
      # 提取 A-H 的所有字母，忽略大小写
      matches = re.findall(r"[A-H]", text.upper())
      if not matches:
          return ""
      # 去重并排序，例如: "C, A" -> "AC"
      return "".join(sorted(set(matches)))
  ```

    ***兼容性** : 替换原有的 `parse_option_letter` 逻辑，确保单选答案 (如 "A") 也能通过此逻辑变为 "A"。

#### 3. 修改求解与判题逻辑 (Solver & Grading)

 **目标** ：实现集合判题（全对才算对），并支持“部分正确”的特殊标记。

* **文件** : `rqlv1/autoqa/AutoQA-rqlv/pipeline/pipeline_solvers.py`
* **函数** : `grade_answer`
* **修改点** : 使用集合比较实现严格匹配。
* **代码示例** :
  **Python**

    ``    def grade_answer(standard: str, prediction: str | None) -> bool:         if not standard or not prediction:             return False         # 严格全等：标准答案 "ABC" vs 预测 "ABC" -> True; "AC" -> False         return set(standard) == set(prediction)    ``

* **新增函数** : `grade_partial_answer` (用于支持你的校验需求)
* **功能** : 判断是否“部分答对且未选错”。
* **代码示例** :
  **Python**

    ``    def grade_partial_answer(standard: str, prediction: str | None) -> bool:         if not standard or not prediction:             return False         std_set = set(standard)         pred_set = set(prediction)         # 预测集是标准集的真子集 (Partial) 且 非空         # 例如 Std=ABC, Pred=AC -> True; Pred=AD -> False (D错); Pred=ABC -> False (全对, 非Partial)         return pred_set.issubset(std_set) and len(pred_set) > 0 and pred_set != std_set    ``

* **函数** : `evaluate_difficulty`
* **修改点** :
  * 在返回的字典 `metrics` 中，增加 `medium_partial_correct` 字段。
  * 调用 `grade_partial_answer(final.answer, medium_letter)` 赋值给该字段。
  * 保持原有的 `medium_correct` 为严格全对判定。

#### 4. 修改主流程路由 (Main)

 **目标** ：落实“若部分答对...则加入 genqa_medium.json”的业务规则。

* **文件** : `rqlv1/autoqa/AutoQA-rqlv/main.py`
* **函数** : `main` (循环内部)
* **修改点** : 调整结果保存的分流逻辑。
* **逻辑调整** :
  **Python**

    ```
    # 获取 metrics
    medium_correct = metrics.get("medium_correct", False)
    medium_partial = metrics.get("medium_partial_correct", False) # 新增
    strong_correct = metrics.get("strong_correct", False)

    if review_passed:
        if medium_correct:
            # Medium 模型全对 -> Simple
            target_path = genqa_simple_path
            # ...
        elif medium_partial:
            # Medium 模型部分正确 (无错选) -> Medium
            # 符合需求：若部分答对且没选择非正确答案... 加入 genqa_medium
            target_path = genqa_medium_path
            # ...
        elif strong_correct:
            # Medium 全错或有错选，但 Strong 全对 -> Medium (原逻辑)
            target_path = genqa_medium_path
            # ...
        else:
            # 均为错 -> Strong / Hard
            target_path = genqa_strong_path
    ```

#### 5. 修改质量检查与辅助工具 (Judge & Utils)

 **目标** ：适配 A-H 选项解析，防止因选项增多导致的解析错误。

* **文件** : `rqlv1/autoqa/AutoQA-rqlv/pipeline/pipeline_judge.py`
* **函数** : `_extract_options`, `judge_mcq`
* **修改点** :
  * 将 `_OPTION_MARKER` 正则中的 `[A-D]` 修改为 `[A-H]`。
  * **禁用或调整** `flags["correct_option_longest"]`：多选题通常不适用此规则（可能有多个正确项，长度不一），建议直接移除或仅当只有一个正确选项时才启用。
  * `missing_options`: 检查标准由 `< 4` 保持不变，但要能识别 A-H。
* **文件** : `rqlv1/autoqa/AutoQA-rqlv/utils/mcq.py`
* **函数** : `has_abcd_options` (建议重命名为 `has_valid_options`)
* **修改点** :
  * 正则 `_OPTION_RE` 支持 `[A-H]`。
  * 逻辑更新为：检查是否存在至少 4 个连续的选项（如 A,B,C,D...）。

#### 6. 总结检查清单

1. **范围** : 确认所有正则 `[A-D]` 均替换为 `[A-H]`。
2. **排序** : 确认 Parsing 模块输出的答案是字母排序的（如 "CA" -> "AC"），否则集合比较外的字符串日志会乱。
3. **路由** : 确认 `main.py` 中优先处理 `medium_correct` (Simple)，其次处理 `medium_partial` (Medium)。
