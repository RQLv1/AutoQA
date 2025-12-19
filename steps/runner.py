from pathlib import Path

from utils.api_client import call_vision_model
from utils.config import MODEL_STAGE_1, MODEL_STAGE_2, MODEL_STAGE_3
from utils.parsing import (
    extract_labeled_value,
    extract_option_text,
    extract_tag_optional,
    parse_bool,
    parse_evidence,
    parse_option_letter_optional,
)
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
    answer_text = extract_tag_optional(raw, "answer_text") or extract_labeled_value(raw, "answer_text") or ""
    answer_tag = extract_tag_optional(raw, "answer")
    answer_letter = parse_option_letter_optional(answer_tag) if answer_tag else None
    if not answer_letter:
        legacy_tag = extract_tag_optional(raw, "answer_letter")
        if legacy_tag:
            answer_letter = parse_option_letter_optional(legacy_tag) or legacy_tag.strip()
    if not answer_letter:
        answer_letter = parse_option_letter_optional(raw)

    if not answer_text and answer_tag:
        remainder = answer_tag.strip()
        remainder = remainder[1:].lstrip(" ,，;；:：") if remainder else ""
        answer_text = remainder.split(" ", 1)[0].strip() if remainder else ""
    if not answer_text and answer_letter:
        inferred = extract_option_text(question, answer_letter)
        if inferred:
            answer_text = inferred

    evidence_raw = extract_tag_optional(raw, "evidence") or extract_labeled_value(raw, "evidence")
    evidence = parse_evidence(evidence_raw)
    modal_use = extract_tag_optional(raw, "modal_use") or extract_labeled_value(raw, "modal_use") or "both"
    cross_modal_raw = extract_tag_optional(raw, "cross_modal_bridge") or extract_labeled_value(
        raw, "cross_modal_bridge"
    )
    cross_modal_bridge = parse_bool(cross_modal_raw)
    reasoning = extract_tag_optional(raw, "reasoning")

    return StepResult(
        k=k,
        question=question,
        answer_text=answer_text,
        answer_letter=answer_letter,
        evidence=evidence,
        modal_use=modal_use,
        cross_modal_bridge=cross_modal_bridge,
        raw=raw,
        reasoning=reasoning,
    )
