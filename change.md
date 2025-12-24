下面给你 **方案 B（“每个 stage 前都插入 draft 模块”）的可落地详细改法** ：改完后，题干会被“模板化”成**只问结论**的问句，像“读出/落在哪个区间/并据此判断”这类**提示推理动词**会被挡在 draft 里，出题 stage 只能复用 draft 给的“结论问法”。

---

## 总体思路（B 的核心）

对每个 stage（Stage1/2/3/Extend/Revise/Final/Graph1hop）统一改成两步：

1. **先跑 draft（operate_calculation 为主，operate_distinction 可选）**
   draft 输出必须包含：
   * `问句模板`：一句话，只问最终结论（禁止出现“读出/估算/计算/区间/并据此/再判断…”）
   * `题干条件句`：可直接写进题干的中性判据/阈值/公式（不提来源）
   * `内部推理步骤`：怎么从图得到变量、怎么判级（只留在 draft，不允许进题干）
   * `选项写法`：A-D 只给“结论标签”（避免选项里复读推理）
2. **再跑出题 stage** ：强制它

* 题干最后一句**必须**使用 draft 的问句模板（可微调但不得引入操作动词）
* 题干条件部分**必须**粘贴 draft 的条件句
* A-D 选项**必须**按 draft 的“结论标签”形式输出（不许在选项里写“约为/不低于/远低于/区间…”）

---

## 1）修改 `operate_calculation.py`（让 draft 产出“结论问法模板”）

你当前 draft 只有 1-4 点，缺了“问句模板/条件句/选项规范”。按下面改：

### 1.1 改 prompt：增加“问句模板 + 条件句 + 选项规范 + 禁用词”

把 `build_operate_calculation_prompt()` 里的 `<draft>` 输出格式替换为：

```diff
<draft>
用要点描述（不要写完整题干）：
+0) 问句模板（必须一句话，只问最终结论；禁止出现：读出/估算/计算/求出/区间/并据此/再判断/最大值是多少/根据色标读数）：
+   示例句式（选一种改写）： “依据图中……与下述判据，最符合的是哪一项？” / “该样品应归为哪一等级？”
1) 视觉证据：图中哪些数字/刻度/相对关系/计数可用于推断？（用 X、Y 占位，不写具体读数）
2) 参考信息：使用哪条公式/阈值/分级规则？（概括即可）
+2.1) 题干条件句（可直接写入题干，不提来源，不出现操作动词；1-2 句）：
+   例如：“规定等级判据为：…”
3) 计算：列出关键步骤，给出正确结果（带单位/区间/等级），并说明取整/误差规则（仅内部）
-4) 选项：A-D 候选（数值/区间/等级），其中 3 个为 Hard Negatives …
+4) 选项规范：
+   - 若是“等级/类别题”：A-D 只写“极低/偏低/中等/高”这类结论标签，禁止在选项里写区间/约为/不低于/远低于。
+   - 若必须数值：A-D 只写数值/单位，不在选项里解释推理。
+5) 干扰项来源（内部）：分别对应 单位陷阱/视觉误读/条件误用 的错误路径
</draft>
```

### 1.2 让 operate_calculation 支持 Stage1（fact_hint 可能为空）

现在 prompt 写死“下一步必须使用新关键信息”。建议加一句容错：

```diff
下一步必须使用的新关键信息(供你设计草稿用，不要直接复制进题干):
{fact_hint}

+如果 fact_hint 为空：请只基于“图片中心区域可读的量/关系”设计一个条件计算/判级草稿，并输出问句模板+条件句。
```

---

## 2）修改 `operate_distinction.py`（可选，但建议也产出“问句模板”）

`operate_distinction` 主要用于干扰项与对比逻辑。给它同样输出结构（至少输出 0 和 2.1），这样 Stage 可以统一“拿模板”。

把输出格式改为：

```diff
只输出以下格式:
-<draft>用要点描述：视觉证据→参考信息中的相近概念/条件→区分点→结论与选项设计(含Hard Negatives)</draft>
+<draft>
+0) 问句模板（只问最终结论；禁用：读出/估算/计算/区间/并据此/再判断）
+1) 视觉证据：图中哪些差异/位置/符号用于区分？（用 X、Y 占位）
+2) 区分判据：参考信息中哪条“相近概念差异点/条件”用于判断？（概括）
+2.1) 题干条件句（可直接写入题干，不提来源，不出现操作动词；1-2句）
+3) 内部结论：正确选项应对应哪个结论标签（仅内部）
+4) 选项规范：A-D 只给结论标签；三类 Hard Negatives 对应哪些误用路径
+</draft>
```

---

## 3）修改 `steps.py`（让每个 stage 强制使用 draft 的“问句模板”）

你现在 Stage2/3/Extend/Revise/Graph 已经把 draft 注入了，但没有“必须使用问句模板/条件句/选项规范”的硬约束，而且你 prompt 里还写了“视觉读数 X…”，这会诱导“读出”。

### 3.1 给所有 stage 加统一硬约束（Stage2/3/Extend/Revise/Graph）

在这些 prompt 的“要求”里新增下面这段（建议原样复制）：

```text
- 【强制落地 draft】你必须遵守 operate_calculation draft（必要时结合 operate_distinction draft）：
  1) 题干最后一句问句必须使用 draft 的“0) 问句模板”（可微调但不得引入：读出/估算/计算/区间/并据此/再判断等操作动词）。
  2) 题干必须包含 draft 的“2.1) 题干条件句”（可微调措辞但保留阈值/判据/公式；不提来源）。
  3) 选项必须遵守 draft 的“4) 选项规范”（尤其禁止在选项中写“约为/不低于/远低于/区间”这类推理提示）。
- 【词面硬禁用】题干中禁止出现：读出、估算、计算、求出、落在…区间、并据此、再判断、最大值是多少、根据色标读数。
```

### 3.2 把你原 prompt 里的“视觉读数 X”改成“视觉变量 X”

这一步很关键：否则你在指导模型“读数”，它就会写“读出…”。

把 Stage2/3/Extend/Revise/Graph 中出现的：

* `视觉读数 X + ...`
* `图中读数/关系 + ...`

改为更中性的：

* `视觉变量 X（由图中可定位的标注/刻度/相对强弱确定） + ...`
* `图中可定位的视觉证据 + ...`

（同样适用于 `build_graph_1hop_step_prompt` 那段模板）

---

## 4）让 Stage1 也“前置 draft”（这是你现在缺的）

`build_stage1_step_prompt()` 目前 **没有 draft 注入** ，所以它容易写出“读出/估算”等引导句。

### 4.1 改 `build_stage1_step_prompt` 的函数签名（加一个 draft 输入）

把签名改成：

```diff
def build_stage1_step_prompt(
    context: str,
    feedback: str,
    previous_question: str | None,
    visual_summary: str | None = None,
+   operate_calculation_draft: str | None = None,
) -> str:
```

在 prompt 文本里增加：

```text
- 你必须使用 operate_calculation draft 的“0) 问句模板”作为题干最后一句问句；
- 题干必须包含 draft 的“2.1) 题干条件句”（若 draft 提供）；
- 禁止出现：读出/估算/计算/区间/并据此/再判断。
```

并把 draft block 像 Stage2 那样注入（仅内部）：

```text
- operate_calculation 草稿(仅供内部推理，不得在题干中提到):
  - draft:
    {operate_calculation_draft}
```

### 4.2 pipeline 里 Stage1 前怎么拿到 draft？

Stage1 没有 `previous_step`，你有两种做法：

 **做法 A（最省改动）** ：构造一个 dummy `StepResult` 传给 operate_calculation（question/answer 置空即可），并传 `fact_hint=""`。
operate_calculation prompt 已按 1.2 支持空 fact_hint。

 **做法 B（更干净）** ：新增一个 `build_operate_calculation_prompt_stage1()`，不需要 previous_step，只输出问句模板+条件句+选项规范（推荐但要多加一个函数）。

---

## 5）Final 也要“前置 draft”（否则最终题仍会写“读出区间”）

你这次出现“读出其界面处最大拉伸应变落在哪个区间”，通常就是 **Final compress** 在复述“怎么做”。

### 5.1 新增一个 `operate_final_draft`（建议直接复用 operate_calculation 但输入为 steps 汇总）

最简单：在 `operate_calculation.py` 新增一个函数：

* `build_operate_final_draft_prompt(context, steps, feedback, forbidden_terms=...)`

draft 输出同样带：

* 0) 问句模板（只问结论）
* 2.1) 题干条件句
* 4. 选项规范（结论标签）
* 内部：正确答案是哪一档

### 5.2 修改 `final.py` 的 `build_final_compress_prompt` 接收并强制使用 final_draft

把函数签名改成：

```diff
def build_final_compress_prompt(context: str, steps: list[StepResult], feedback: str,
+                               operate_final_draft: str | None = None) -> str:
```

在 prompt 要求里加：

```text
- 你必须使用 operate_final_draft 的“0) 问句模板”作为题干最后一句问句（禁用：读出/估算/计算/区间/并据此/再判断）。
- 题干必须包含 operate_final_draft 的“2.1) 题干条件句”。
- 选项必须遵守 operate_final_draft 的“4) 选项规范”（等级题只写等级名，不在选项里写区间/约为/不低于）。
```

并注入 draft block（内部）：

```text
- operate_final_draft(仅供内部推理，不得在题干中提到):
  {operate_final_draft}
```

---

## 6）强烈建议加一个“词面门禁”（在 pipeline 里自动触发 revise）

即使 prompt 改了，模型偶尔还是会漏。最稳的是在 pipeline 加一个正则门禁：

### 6.1 禁用词表（建议）

```python
BANNED = [
  "读出", "估算", "计算", "求出", "落在", "区间", "并据此", "再判断",
  "最大拉伸应变是多少", "根据色标读数"
]
```

### 6.2 判定为“Over-Guiding Wording”直接 revise

* step 阶段：触发 `build_revise_prompt(..., reason="Over-Guiding Wording")`
* final 阶段：触发 `build_final_revise_prompt(..., reason="Over-Guiding Wording")`

这样你就不会再产出“教人怎么推”的题干。
