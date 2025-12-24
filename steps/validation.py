from utils.config import VERIFY_STRICT
from utils.schema import StepResult


def validate_step(
    step: StepResult, force_cross_modal: bool, strong_correct: bool | None, medium_correct: bool | None
) -> tuple[bool, str]:
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
    
    # 新增：如果在生成过程中 Medium 模型就做对了，说明题目太简单，直接强制 Revise
    if medium_correct is True:
        return True, "Too Simple (Medium Solved)"
        
    # 用户要求：Strong 做错也算 Hard，所以不再因为 Strong 失败而强制 Revise
    # 只要不是太简单(Medium Correct)，且通过了基本的格式检查，就放行
    # if medium_correct is False and strong_correct is False:
    #    return True, "strong solver failed"
        
    return False, ""
