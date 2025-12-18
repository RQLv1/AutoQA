from pathlib import Path

from utils.api_client import call_vision_model
from utils.config import MODEL_STAGE_1, MODEL_STAGE_2, MODEL_STAGE_3
from utils.parsing import extract_tag_optional, parse_evidence, parse_option_letter_optional
from utils.schema import StepResult


def select_model_for_step(k: int) -> str:
    if k == 0:
        return MODEL_STAGE_1
    if k % 2 == 1:
        return MODEL_STAGE_2
    return MODEL_STAGE_3


def run_step(prompt: str, image_path: Path, model: str, k: int) -> StepResult:
    raw = call_vision_model(prompt, image_path, model)
    question = extract_tag_optional(raw, "question") or raw.strip()
    answer_text = extract_tag_optional(raw, "answer_text") or ""
    answer_letter = extract_tag_optional(raw, "answer_letter")
    legacy_answer = extract_tag_optional(raw, "answer")

    if answer_letter:
        answer_letter = answer_letter.strip()
    if not answer_letter:
        answer_letter = parse_option_letter_optional(legacy_answer or "") if legacy_answer else None

    if not answer_text and legacy_answer:
        remainder = legacy_answer.strip()
        remainder = remainder[1:].lstrip(" ,，;；:：") if remainder else ""
        answer_text = remainder.split(" ", 1)[0].strip() if remainder else ""

    evidence = parse_evidence(extract_tag_optional(raw, "evidence"))
    modal_use = extract_tag_optional(raw, "modal_use") or "both"
    cross_modal_bridge = (extract_tag_optional(raw, "cross_modal_bridge") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "是",
    }

    return StepResult(
        k=k,
        question=question,
        answer_text=answer_text,
        answer_letter=answer_letter,
        evidence=evidence,
        modal_use=modal_use,
        cross_modal_bridge=cross_modal_bridge,
        raw=raw,
    )
