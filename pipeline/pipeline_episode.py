from pathlib import Path

from pipeline.pipeline_final_refine import refine_final_question
from pipeline.pipeline_review import review_question
from pipeline.pipeline_solvers import evaluate_difficulty
from pipeline.pipeline_vision_knowledge import build_visual_knowledge
from prompts import build_analysis_prompt, build_final_compress_prompt, build_final_harden_prompt
from steps import derive_stage_results, generate_steps
from steps.obfuscate_agent import obfuscate_question
from utils.api_client import call_text_model, call_vision_model
from utils.config import (
    DEFAULT_TEMPERATURE,
    MODEL_SUM,
)
from utils.details_logger import get_details_logger
from utils.parsing import extract_tag_optional
from utils.schema import EpisodeResult, StageResult, StepResult
from utils.terminal import print_final_input, print_final_summary


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
    stage_final.question = obfuscate_question(stage_final.question, raw=stage_final.raw)
    get_details_logger().log_event(
        "final_stage",
        {
            "question": stage_final.question,
            "answer": stage_final.answer,
            "reasoning": stage_final.reasoning,
        },
    )

    refine_attempts = 0
    max_refine_attempts = 2
    difficulty_metrics: dict[str, object] = {}
    reflect_feedback = ""
    review_raw = None
    review_passed = None
    refine_feedback = ""

    print_final_input(
        steps_count=len(compress_steps),
        cross_modal_used=cross_modal_used,
        refine_attempts=refine_attempts,
        max_refine_attempts=max_refine_attempts,
    )

    while True:
        difficulty_metrics = evaluate_difficulty(
            stage_final,
            image_path,
            cross_modal_used,
            len(compress_steps),
        )

        if difficulty_metrics.get("text_only_veto"):
            if refine_attempts >= max_refine_attempts:
                break
            refine_attempts += 1
            harden_prompt = build_final_harden_prompt(
                context,
                compress_steps,
                stage_final.question,
                stage_final.answer,
                "text-only solved",
            )
            stage_final = run_final(harden_prompt, image_path, MODEL_SUM)
            stage_final.question = obfuscate_question(stage_final.question, raw=stage_final.raw)
            get_details_logger().log_event(
                "final_stage_hardened",
                {
                    "question": stage_final.question,
                    "answer": stage_final.answer,
                    "reasoning": stage_final.reasoning,
                    "reason": "text_only_veto",
                },
            )
            continue

        if difficulty_metrics.get("medium_correct"):
            if refine_attempts >= max_refine_attempts:
                break
            refine_attempts += 1
            stage_final, refine_feedback = refine_final_question(
                context=context,
                steps=compress_steps,
                image_path=image_path,
                final=stage_final,
                reason="medium_solved",
            )
            stage_final.question = obfuscate_question(stage_final.question, raw=stage_final.raw)
            get_details_logger().log_event(
                "final_stage_refined",
                {
                    "question": stage_final.question,
                    "answer": stage_final.answer,
                    "reasoning": stage_final.reasoning,
                    "reason": "medium_solved",
                    "feedback": refine_feedback,
                },
            )
            continue

        review_raw, review_passed = review_question(
            stage_final.question,
            stage_final.answer,
            stage_final.reasoning,
            image_path,
        )
        if review_passed is False:
            if refine_attempts >= max_refine_attempts:
                break
            refine_attempts += 1
            stage_final, refine_feedback = refine_final_question(
                context=context,
                steps=compress_steps,
                image_path=image_path,
                final=stage_final,
                reason="review_failed",
                review_raw=review_raw,
            )
            stage_final.question = obfuscate_question(stage_final.question, raw=stage_final.raw)
            get_details_logger().log_event(
                "final_stage_refined",
                {
                    "question": stage_final.question,
                    "answer": stage_final.answer,
                    "reasoning": stage_final.reasoning,
                    "reason": "review_failed",
                    "feedback": refine_feedback,
                },
            )
            continue

        break

    print("[Final] Compress 完成")
    print(stage_final.question)
    print("标准答案:", stage_final.answer)

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

    print_final_summary(
        final=stage_final,
        metrics=difficulty_metrics,
        review_passed=review_passed,
        refine_attempts=refine_attempts,
        max_refine_attempts=max_refine_attempts,
    )

    return EpisodeResult(
        stage_1=stage_1,
        stage_2=stage_2,
        stage_3=stage_3,
        stage_final=stage_final,
        steps=steps,
        difficulty_metrics=difficulty_metrics,
        judge_flags={},
        reflect_feedback=reflect_feedback,
        review_raw=review_raw,
        review_passed=review_passed,
        refine_feedback=refine_feedback,
    )
