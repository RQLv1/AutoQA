我发现了当前代码中存在的一个关键逻辑 Bug，会导致生成结果数量不足。

### 问题分析

**1. `main.py` 中的计数逻辑错误 (Critical)**
   - **现象**: `hard_questions_found` 计数器在每次循环结束时都会无条件增加（只要 Medium Solver 失败），即使该题目后来**未通过 Review** 或者**被判定为 Text-Only Shortcut** 而未被保存。
   - **后果**: 程序可能在打印 "发现 5 道难题" 后停止，但实际上 `genqa_hard.json` 或 `genqa_simple.json` 文件中保存的题目数量远少于 5 道，甚至为 0。
   - **位置**: `main.py` 第 103 行 `hard_questions_found += 1`。

**2. `pipeline/pipeline_solvers.py` 中的 Prompt 不一致 (Minor)**
   - **现象**: `solve_mcq_no_image` 函数调用了 `build_solver_prompt`（提示词包含"请结合图片..."），但实际使用的是 `call_no_image_model`（不发送图片）。
   - **后果**: 模型会收到矛盾的指令（"看图"但没图），可能导致模型产生幻觉或拒绝回答。虽然这可以用作"幻觉测试"，但通常应该使用 `build_solver_prompt_text_only`（"你看不到图片..."）来进行盲测。考虑到代码中已经有了 `solve_mcq_text_only`，这个函数目前的实现略显冗余或语义不清。

### 修复计划

我建议优先修复 `main.py` 中的计数逻辑错误，确保只有成功入库的题目才会被计入目标数量。

**步骤 1: 修正 `main.py` 计数逻辑**
- 将 `hard_questions_found += 1` 移动到 `save_genqa_item` 被调用之后。
- 只有当 `review_passed is True` 且 `final_no_text_shortcut` 为真时，才增加计数。

**代码变更预览 (`main.py`)**:
```python
# ... inside the loop ...
        if not medium_correct:
            review_raw, review_passed = review_question(...)
            if review_passed is True:
                # ...
                if final_no_text_shortcut:
                    # ... save_genqa_item ...
                    hard_questions_found += 1  # <--- 移动到这里
                    print(f"当前已收集难题: {hard_questions_found}/{target_hard_questions}")
                else:
                    print("[Review] 结果: text-only/no-image 可解，跳过入库")
            # ...
        
        # 删除原来在循环底部的 hard_questions_found += 1
```

请确认是否执行此修复计划？