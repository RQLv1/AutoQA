from pathlib import Path

from pipeline.pipeline_solvers import evaluate_difficulty
from prompts import build_final_compress_prompt, build_final_harden_prompt
from steps import derive_stage_results, generate_steps
from utils.api_client import call_vision_model
from utils.config import HARDEN_MODE, MAX_HARDEN_ATTEMPTS, MODEL_SUM
from utils.parsing import extract_tag_optional
from utils.schema import EpisodeResult, StageResult


def run_final(prompt: str, image_path: Path, model: str) -> StageResult:
    raw = call_vision_model(prompt, image_path, model)
    question = extract_tag_optional(raw, "question") or raw.strip()
    answer = extract_tag_optional(raw, "answer") or ""
    reasoning = extract_tag_optional(raw, "reasoning")
    return StageResult(question=question, answer=answer, raw=raw, reasoning=reasoning)


def run_episode(
    context: str,
    image_path: Path,
    feedback: str = "",
    previous_final_question: str | None = None,
) -> EpisodeResult:
    steps, cross_modal_used = generate_steps(context, image_path, feedback, previous_final_question)
    stage_1, stage_2, stage_3 = derive_stage_results(steps)

    final_prompt = build_final_compress_prompt(context, steps, feedback)
    stage_final = run_final(final_prompt, image_path, MODEL_SUM)
    print("[Final] Compress 完成")
    print(stage_final.question)
    print("标准答案:", stage_final.answer)
    difficulty_metrics = evaluate_difficulty(stage_final, image_path, cross_modal_used, len(steps))
    print(
        "[Final] Difficulty 评估:",
        f"medium_correct={difficulty_metrics.get('medium_correct')}",
        f"strong_correct={difficulty_metrics.get('strong_correct')}",
        f"score={difficulty_metrics.get('difficulty_score')}",
    )
    harden_attempts = 0
    max_harden_attempts = max(0, MAX_HARDEN_ATTEMPTS)
    while difficulty_metrics.get("medium_correct", False) and harden_attempts < max_harden_attempts:
        harden_attempts += 1
        harden_prompt = build_final_harden_prompt(
            context,
            stage_final.question,
            stage_final.answer,
            harden_attempts,
            max_harden_attempts,
            HARDEN_MODE,
        )
        stage_final = run_final(harden_prompt, image_path, MODEL_SUM)
        print(f"[Final] Harden 完成: {harden_attempts}/{max_harden_attempts}")
        print(stage_final.question)
        print("标准答案:", stage_final.answer)
        difficulty_metrics = evaluate_difficulty(stage_final, image_path, cross_modal_used, len(steps))
        print(
            "[Final] Harden 后 Difficulty:",
            f"medium_correct={difficulty_metrics.get('medium_correct')}",
            f"strong_correct={difficulty_metrics.get('strong_correct')}",
            f"score={difficulty_metrics.get('difficulty_score')}",
        )

    return EpisodeResult(
        stage_1=stage_1,
        stage_2=stage_2,
        stage_3=stage_3,
        stage_final=stage_final,
        steps=steps,
        difficulty_metrics=difficulty_metrics,
        judge_flags={},
    )
