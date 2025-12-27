import re

from utils.config import VERIFY_STRICT
from utils.schema import StepResult


def validate_step(
    step: StepResult,
    force_cross_modal: bool,
    strong_correct: bool | None,
    medium_correct: bool | None,
    text_only_correct: bool | None,
) -> tuple[bool, str]:
    visual_anchors = [
        "图中",
        "图示",
        "图片",
        "图像",
        "图表",
        "曲线",
        "刻度",
        "指针",
        "箭头",
        "标注",
        "标记",
        "左上",
        "右上",
        "左下",
        "右下",
        "左侧",
        "右侧",
        "上方",
        "下方",
        "中心",
        "区域",
        "仪表",
        "面板",
        "屏幕",
        "读数",
        "坐标轴",
        "表格",
    ]
    if not any(anchor in step.question for anchor in visual_anchors):
        return True, "missing visual anchor"

    if step.k >= 1:
        option_matches = list(
            re.finditer(r"([A-H])[\.、:：\)]\s*([^\n]{0,80})", step.question)
        )
        first_option = option_matches[0].start() if option_matches else len(step.question)
        stem = step.question[:first_option]
        condition_hits = len(
            re.findall(
                r"(若|如果|当|则|按|根据|阈值|公式|计算|换算|分级|判定|规则|标准|区间|≥|≤|>|<|=)",
                stem,
            )
        )
        numeric_hits = len(re.findall(r"\\d+(?:\\.\\d+)?", stem))
        if condition_hits + numeric_hits < 1:
            return True, "missing neutral conditions"
    if not step.question:
        return True, "missing question"
    if step.answer_letter is None:
        return True, "missing answer_letter"
    if step.modal_use not in {"image", "text", "both"}:
        return True, "invalid modal_use"
    if force_cross_modal and "cross_modal_bridge" in step.raw and not step.cross_modal_bridge:
        return True, "cross-modal required"
    if VERIFY_STRICT and step.answer_text and step.answer_text.lower() in step.question.lower():
        return True, "answer leakage in question"

    if text_only_correct is True:
        return True, "text-only shortcut"
    
    # 新增：如果在生成过程中 Medium 模型就做对了，说明题目太简单，直接强制 Revise
    if medium_correct is True:
        return True, "Too Simple (Medium Solved)"
        
    # 用户要求：Strong 做错也算 Hard，所以不再因为 Strong 失败而强制 Revise
    # 只要不是太简单(Medium Correct)，且通过了基本的格式检查，就放行
    # if medium_correct is False and strong_correct is False:
    #    return True, "strong solver failed"
        
    return False, ""
