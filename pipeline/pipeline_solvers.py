from pathlib import Path
from typing import Any

from prompts import build_solver_prompt, build_solver_prompt_text_only
from utils.api_client import call_no_image_model, call_text_model, call_vision_model
from utils.config import (
    DEFAULT_TEMPERATURE,
    MODEL_SOLVE_MEDIUM,
    MODEL_SOLVE_STRONG,
)
from utils.parsing import extract_tag_optional, parse_option_letter_optional
from utils.schema import StageResult


def _normalize_solver_output(raw: str) -> tuple[str, str | None]:
    tagged = extract_tag_optional(raw, "answer")
    letter = parse_option_letter_optional(tagged) if tagged else None
    if not letter:
        head_line = raw.strip().splitlines()[0] if raw.strip() else ""
        letter = parse_option_letter_optional(head_line)
    if letter:
        return f"<answer>{letter}</answer>", letter
    return "<answer></answer>", None


def solve_mcq(
    question: str, image_path: Path, model: str, mode: str = "multi_select"
) -> tuple[str, str | None]:
    solver_prompt = build_solver_prompt(question, mode)
    solver_raw = call_vision_model(
        solver_prompt,
        image_path,
        model,
        temperature=DEFAULT_TEMPERATURE,
    )
    normalized_raw, solver_letter = _normalize_solver_output(solver_raw)
    return normalized_raw, solver_letter


def solve_mcq_text_only(
    question: str, model: str, mode: str = "multi_select"
) -> tuple[str, str | None]:
    solver_prompt = build_solver_prompt_text_only(question, mode)
    solver_raw = call_text_model(solver_prompt, model, max_tokens=4096, temperature=0)
    normalized_raw, solver_letter = _normalize_solver_output(solver_raw)
    return normalized_raw, solver_letter


def solve_mcq_no_image(
    question: str, model: str, mode: str = "multi_select"
) -> tuple[str, str | None]:
    solver_prompt = build_solver_prompt(question, mode)
    solver_raw = call_no_image_model(
        solver_prompt,
        model,
        temperature=DEFAULT_TEMPERATURE,
    )
    normalized_raw, solver_letter = _normalize_solver_output(solver_raw)
    return normalized_raw, solver_letter


def grade_answer(answer: str, solver_letter: str | None) -> bool:
    standard = parse_option_letter_optional(answer)
    if not standard or not solver_letter:
        return False
    return set(standard) == set(solver_letter)


def grade_partial_answer(standard: str, prediction: str | None) -> bool:
    if not standard or not prediction:
        return False
    std_set = set(parse_option_letter_optional(standard) or "")
    pred_set = set(parse_option_letter_optional(prediction) or "")
    return bool(pred_set) and pred_set.issubset(std_set) and pred_set != std_set


def evaluate_difficulty(
    final: StageResult,
    image_path: Path,
    cross_modal_used: bool,
    num_hops: int,
    mode: str = "multi_select",
) -> dict[str, Any]:
    medium_raw, medium_letter = solve_mcq(
        final.question, image_path, MODEL_SOLVE_MEDIUM, mode
    )
    medium_correct = grade_answer(final.answer, medium_letter)
    medium_partial = grade_partial_answer(final.answer, medium_letter)

    strong_text_only_raw, strong_text_only_letter = solve_mcq_text_only(
        final.question, MODEL_SOLVE_STRONG, mode
    )
    strong_text_only_correct = grade_answer(final.answer, strong_text_only_letter)

    strong_raw = None
    strong_letter = None
    strong_no_image_raw = None
    strong_no_image_letter = None
    strong_correct = None
    strong_no_image_correct = None

    if not medium_correct:
        strong_raw, strong_letter = solve_mcq(final.question, image_path, MODEL_SOLVE_STRONG)
        strong_no_image_raw, strong_no_image_letter = solve_mcq_no_image(
            final.question, MODEL_SOLVE_STRONG, mode
        )
        strong_correct = grade_answer(final.answer, strong_letter)
        strong_no_image_correct = grade_answer(final.answer, strong_no_image_letter)
    
    difficulty_score = (
        1.0
        if (strong_correct and not medium_correct and not strong_text_only_correct)
        else 0.5
        if strong_correct
        else 0.0
    )
    return {
        "medium_correct": medium_correct,
        "medium_partial_correct": medium_partial,
        "strong_correct": strong_correct,
        "strong_text_only_correct": strong_text_only_correct,
        "strong_no_image_correct": strong_no_image_correct,
        "text_only_veto": strong_text_only_correct,
        "difficulty_score": difficulty_score,
        "cross_modal_used": cross_modal_used,
        "num_hops": num_hops,
        "medium_pred": medium_letter,
        "strong_pred": strong_letter,
        "strong_text_only_pred": strong_text_only_letter,
        "strong_no_image_pred": strong_no_image_letter,
        "medium_raw": medium_raw,
        "strong_raw": strong_raw,
        "strong_text_only_raw": strong_text_only_raw,
        "strong_no_image_raw": strong_no_image_raw,
    }


def try_solve_question(question: str, image_path: Path, model: str) -> tuple[str, str | None]:
    return solve_mcq(question, image_path, model)
