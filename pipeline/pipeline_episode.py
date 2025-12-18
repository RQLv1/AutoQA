from pathlib import Path

from pipeline.pipeline_solvers import evaluate_difficulty
from prompts import build_final_compress_prompt, build_final_revise_prompt
from steps import derive_stage_results, generate_steps
from utils.api_client import call_vision_model
from utils.config import MODEL_SUM, REQUIRE_CROSS_MODAL
from utils.parsing import extract_tag_optional
from utils.schema import EpisodeResult, StageResult


def run_final(prompt: str, image_path: Path, model: str) -> StageResult:
    raw = call_vision_model(prompt, image_path, model)
    question = extract_tag_optional(raw, "question") or raw.strip()
    answer = extract_tag_optional(raw, "answer") or ""
    return StageResult(question=question, answer=answer, raw=raw)


def run_episode(
    context: str,
    image_path: Path,
    feedback: str,
    previous_final_question: str | None,
) -> EpisodeResult:
    steps, cross_modal_used = generate_steps(context, image_path, feedback, previous_final_question)
    stage_1, stage_2, stage_3 = derive_stage_results(steps)

    final_prompt = build_final_compress_prompt(context, steps, feedback)
    stage_final = run_final(final_prompt, image_path, MODEL_SUM)
    difficulty_metrics = evaluate_difficulty(
        context, stage_final, image_path, cross_modal_used, len(steps)
    )

    revise_reasons = []
    if REQUIRE_CROSS_MODAL and not cross_modal_used:
        revise_reasons.append("missing cross-modal bridge")
    if not difficulty_metrics.get("strong_correct", False):
        revise_reasons.append("strong solver failed")

    if revise_reasons:
        revise_prompt = build_final_revise_prompt(
            context, stage_final.question, stage_final.answer, " & ".join(revise_reasons)
        )
        stage_final = run_final(revise_prompt, image_path, MODEL_SUM)
        difficulty_metrics = evaluate_difficulty(
            context, stage_final, image_path, cross_modal_used, len(steps)
        )

    return EpisodeResult(
        stage_1=stage_1,
        stage_2=stage_2,
        stage_3=stage_3,
        stage_final=stage_final,
        steps=steps,
        difficulty_metrics=difficulty_metrics,
    )
