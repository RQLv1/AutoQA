from pathlib import Path

from pipeline.pipeline_solvers import evaluate_difficulty
from pipeline.pipeline_vision_knowledge import build_visual_knowledge
from prompts import build_analysis_prompt, build_final_compress_prompt
from steps import derive_stage_results, generate_steps
from utils.api_client import call_text_model, call_vision_model
from utils.config import (
    DEFAULT_TEMPERATURE,
    MODEL_SUM,
)
from utils.details_logger import get_details_logger
from utils.parsing import extract_tag_optional
from utils.schema import EpisodeResult, StageResult, StepResult


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
    prior_steps: list[StepResult] | None = None,
) -> EpisodeResult:
    visual_knowledge = build_visual_knowledge(image_path)
    steps, cross_modal_used = generate_steps(
        context,
        image_path,
        feedback,
        previous_final_question,
        visual_knowledge.summary,
        visual_knowledge.edges,
    )
    stage_1, stage_2, stage_3 = derive_stage_results(steps)

    compress_steps = steps if not prior_steps else [*prior_steps, *steps]
    final_prompt = build_final_compress_prompt(context, compress_steps, feedback)
    stage_final = run_final(final_prompt, image_path, MODEL_SUM)
    get_details_logger().log_event(
        "final_stage",
        {
            "question": stage_final.question,
            "answer": stage_final.answer,
            "reasoning": stage_final.reasoning,
        },
    )
    print("[Final] Compress 完成")
    print(stage_final.question)
    print("标准答案:", stage_final.answer)
    difficulty_metrics = evaluate_difficulty(
        stage_final,
        image_path,
        cross_modal_used,
        len(compress_steps),
    )
    print(
        "[Final] Difficulty 评估:",
        f"medium_correct={difficulty_metrics.get('medium_correct')}",
        f"strong_correct={difficulty_metrics.get('strong_correct')}",
        f"score={difficulty_metrics.get('difficulty_score')}",
    )
    if not (
        difficulty_metrics.get("medium_correct", False)
        and difficulty_metrics.get("strong_correct", False)
    ) and stage_final.reasoning:
        print(f"推理过程: <reasoning>{stage_final.reasoning}</reasoning>")
    feedback_prompt = build_analysis_prompt(
        stage_final.question,
        stage_final.answer,
        str(difficulty_metrics.get("medium_raw") or ""),
    )
    reflect_feedback = call_text_model(
        feedback_prompt,
        MODEL_SUM,
        temperature=DEFAULT_TEMPERATURE,
    ).strip()
    if reflect_feedback:
        print("[Final] 反馈:", reflect_feedback)

    return EpisodeResult(
        stage_1=stage_1,
        stage_2=stage_2,
        stage_3=stage_3,
        stage_final=stage_final,
        steps=steps,
        difficulty_metrics=difficulty_metrics,
        judge_flags={},
        reflect_feedback=reflect_feedback,
    )
