import json
from pathlib import Path

from api_client import call_vision_model
from config import MODEL_SOLVE, MODEL_STAGE_1, MODEL_STAGE_2, MODEL_STAGE_3, MODEL_SUM
from parsing import extract_tag, parse_option_letter
from prompts import (
    build_final_prompt,
    build_initial_prompt,
    build_revision_prompt,
    build_solver_prompt,
    build_third_prompt,
)
from schema import StageResult


def run_stage(prompt: str, image_path: Path, model: str) -> StageResult:
    raw = call_vision_model(prompt, image_path, model)
    return StageResult(
        question=extract_tag(raw, "question"),
        answer=extract_tag(raw, "answer"),
        raw=raw,
    )


def save_round_questions(
    log_path: Path,
    round_idx: int,
    stage_one: StageResult,
    stage_two: StageResult,
    stage_three: StageResult,
    stage_final: StageResult,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "round": round_idx,
        "stage_1": {
            "question": stage_one.question,
            "answer": stage_one.answer,
            "raw": stage_one.raw,
        },
        "stage_2": {
            "question": stage_two.question,
            "answer": stage_two.answer,
            "raw": stage_two.raw,
        },
        "stage_3": {
            "question": stage_three.question,
            "answer": stage_three.answer,
            "raw": stage_three.raw,
        },
        "stage_final": {
            "question": stage_final.question,
            "answer": stage_final.answer,
            "raw": stage_final.raw,
        },
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")


def generate_questions(
    context: str, image_path: Path, feedback: str, previous_final_question: str | None
) -> tuple[StageResult, StageResult, StageResult, StageResult]:
    stage_one = run_stage(
        build_initial_prompt(context, feedback, previous_final_question),
        image_path,
        MODEL_STAGE_1,
    )
    print("第一次生成:", stage_one.raw)

    stage_two = run_stage(build_revision_prompt(context, stage_one, feedback), image_path, MODEL_STAGE_2)
    print("第二次生成:", stage_two.raw)

    stage_three = run_stage(build_third_prompt(context, stage_two, feedback), image_path, MODEL_STAGE_3)
    print("第三次生成:", stage_three.raw)

    stage_final = run_stage(
        build_final_prompt(context, stage_one, stage_two, stage_three, feedback),
        image_path,
        MODEL_SUM,
    )
    print("最终合并生成:", stage_final.raw)

    return stage_one, stage_two, stage_three, stage_final


def try_solve_question(context: str, question: str, image_path: Path) -> tuple[str, str]:
    solver_prompt = build_solver_prompt(context, question)
    solver_raw = call_vision_model(solver_prompt, image_path, MODEL_SOLVE)
    solver_letter = parse_option_letter(solver_raw)
    print("求解模型回答:", solver_raw)
    return solver_raw, solver_letter
