from utils.config import VERIFY_STRICT
from utils.schema import StepResult


def validate_step(
    step: StepResult, force_cross_modal: bool, strong_correct: bool
) -> tuple[bool, str]:
    if not step.question or not step.answer_text:
        return True, "missing question or answer_text"
    if step.answer_letter is None:
        return True, "missing answer_letter"
    if step.evidence is None:
        return True, "missing evidence"
    if step.modal_use not in {"image", "text", "both"}:
        return True, "invalid modal_use"
    if force_cross_modal and not step.cross_modal_bridge:
        return True, "cross-modal required"
    if VERIFY_STRICT and step.answer_text and step.answer_text.lower() in step.question.lower():
        return True, "answer leakage in question"
    if not strong_correct:
        return True, "strong solver failed"
    return False, ""
