from pathlib import Path

from prompts import (
    build_final_targeted_revise_prompt,
    build_review_feedback_prompt,
    build_solver_rationale_prompt,
)
from utils.api_client import call_vision_model
from utils.config import DEFAULT_TEMPERATURE, MODEL_REVIEW, MODEL_SOLVE_MEDIUM, MODEL_SUM
from utils.parsing import extract_tag_optional
from utils.schema import StageResult, StepResult


def _run_final_revision(prompt: str, image_path: Path) -> StageResult:
    raw = call_vision_model(prompt, image_path, MODEL_SUM)
    question = extract_tag_optional(raw, "question") or raw.strip()
    answer = extract_tag_optional(raw, "answer") or ""
    reasoning = extract_tag_optional(raw, "reasoning")
    return StageResult(question=question, answer=answer, raw=raw, reasoning=reasoning)


def _get_medium_rationale(question: str, answer: str, image_path: Path) -> str:
    prompt = build_solver_rationale_prompt(question, answer)
    raw = call_vision_model(prompt, image_path, MODEL_SOLVE_MEDIUM, temperature=0)
    return raw.strip()


def _get_review_feedback(question: str, answer: str, reasoning: str, image_path: Path) -> str:
    prompt = build_review_feedback_prompt(question, answer, reasoning)
    raw = call_vision_model(prompt, image_path, MODEL_REVIEW, temperature=DEFAULT_TEMPERATURE)
    return raw.strip()


def refine_final_question(
    *,
    context: str,
    steps: list[StepResult],
    image_path: Path,
    final: StageResult,
    reason: str,
    review_raw: str | None = None,
    mode: str = "multi_select",
) -> tuple[StageResult, str]:
    feedback_detail = ""
    if reason == "medium_solved":
        feedback_detail = _get_medium_rationale(final.question, final.answer, image_path)
    elif reason == "review_failed":
        feedback_detail = _get_review_feedback(
            final.question, final.answer, final.reasoning or "", image_path
        )
        if not feedback_detail and review_raw:
            feedback_detail = review_raw.strip()
    else:
        feedback_detail = review_raw.strip() if review_raw else ""

    revise_prompt = build_final_targeted_revise_prompt(
        context,
        steps,
        final.question,
        final.answer,
        reason,
        feedback_detail,
        mode,
    )
    revised = _run_final_revision(revise_prompt, image_path)
    return revised, feedback_detail
