from pathlib import Path
from typing import Any

from api_client import call_vision_model
from config import MODEL_SOLVE_MEDIUM, MODEL_SOLVE_STRONG
from parsing import parse_option_letter_optional, parse_tagged_option_letter
from prompts import build_solver_prompt
from schema import StageResult


def solve_mcq(
    context: str, question: str, image_path: Path, model: str
) -> tuple[str, str | None]:
    solver_prompt = build_solver_prompt(context, question)
    solver_raw = call_vision_model(solver_prompt, image_path, model, max_tokens=64, temperature=0)
    solver_letter = parse_tagged_option_letter(solver_raw, "answer")
    return solver_raw, solver_letter


def grade_answer(answer: str, solver_letter: str | None) -> bool:
    standard = parse_option_letter_optional(answer)
    if not standard or not solver_letter:
        return False
    return standard == solver_letter


def evaluate_difficulty(
    context: str,
    final: StageResult,
    image_path: Path,
    cross_modal_used: bool,
    num_hops: int,
) -> dict[str, Any]:
    medium_raw, medium_letter = solve_mcq(context, final.question, image_path, MODEL_SOLVE_MEDIUM)
    strong_raw, strong_letter = solve_mcq(context, final.question, image_path, MODEL_SOLVE_STRONG)
    medium_correct = grade_answer(final.answer, medium_letter)
    strong_correct = grade_answer(final.answer, strong_letter)
    difficulty_score = 1.0 if (strong_correct and not medium_correct) else 0.5 if strong_correct else 0.0
    return {
        "medium_correct": medium_correct,
        "strong_correct": strong_correct,
        "difficulty_score": difficulty_score,
        "cross_modal_used": cross_modal_used,
        "num_hops": num_hops,
        "medium_pred": medium_letter,
        "strong_pred": strong_letter,
        "medium_raw": medium_raw,
        "strong_raw": strong_raw,
    }


def try_solve_question(
    context: str, question: str, image_path: Path, model: str
) -> tuple[str, str | None]:
    return solve_mcq(context, question, image_path, model)
