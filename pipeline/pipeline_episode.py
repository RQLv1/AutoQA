from pathlib import Path

from pipeline.pipeline_final_refine import refine_final_question
from pipeline.pipeline_review import review_question
from pipeline.pipeline_solvers import evaluate_difficulty
from pipeline.pipeline_vision_knowledge import build_visual_knowledge
from prompts import (
    build_analysis_prompt,
    build_final_compress_prompt,
    build_final_harden_prompt,
)
from steps import derive_stage_results, generate_steps
from steps.obfuscate_agent import obfuscate_question
from utils.api_client import call_text_model, call_vision_model
from utils.config import (
    DEFAULT_TEMPERATURE,
    MODEL_SUM,
)
from utils.details_logger import get_details_logger
from utils.mcq import has_valid_options
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
    mode: str = "multi_select",
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
    final_prompt = build_final_compress_prompt(context, compress_steps, feedback, mode)
    stage_final = run_final(final_prompt, image_path, MODEL_SUM)
    stage_final.question = obfuscate_question(stage_final.question, raw=stage_final.raw)
    get_details_logger().log_event(
        "final_stage",
        {
            "question": stage_final.question,
            "answer": stage_final.answer,
            "reasoning": stage_final.reasoning,
            "mode": mode,
        },
    )

    refine_attempts = 0
    max_refine_attempts = 2
    difficulty_metrics: dict[str, object] = {}
    reflect_feedback = ""
    review_raw = None
    review_passed = None
    refine_feedback = ""

    print(f"[Final] 生成模式: {mode}")
    format_hint = (
        "补全为标准多选题，必须包含 4-8 个按顺序排列的选项（A-H），答案可包含多个字母。"
        if mode != "single_select"
        else "补全为标准单选题，必须包含 A-D 四个选项，且答案只能是其中一个字母。"
    )
    print_final_input(
        steps_count=len(compress_steps),
        cross_modal_used=cross_modal_used,
        refine_attempts=refine_attempts,
        max_refine_attempts=max_refine_attempts,
    )

    while True:
        if not has_valid_options(stage_final.question):
            if refine_attempts >= max_refine_attempts:
                break
            refine_attempts += 1
            stage_final, refine_feedback = refine_final_question(
                context=context,
                steps=compress_steps,
                image_path=image_path,
                final=stage_final,
                reason="format_missing_options",
                review_raw=format_hint,
                mode=mode,
            )
            stage_final.question = obfuscate_question(stage_final.question, raw=stage_final.raw)
            get_details_logger().log_event(
                "final_stage_refined",
                {
                    "question": stage_final.question,
                    "answer": stage_final.answer,
                    "reasoning": stage_final.reasoning,
                    "reason": "format_missing_options",
                    "feedback": refine_feedback,
                    "mode": mode,
                },
            )
            continue
        difficulty_metrics = evaluate_difficulty(
            stage_final,
            image_path,
            cross_modal_used,
            len(compress_steps),
            mode=mode,
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
                mode,
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
                    "mode": mode,
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
                mode=mode,
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
                    "mode": mode,
                },
            )
            continue

        review_raw, review_passed, review_reason = review_question(
            stage_final.question,
            stage_final.answer,
            stage_final.reasoning,
            image_path,
            mode=mode,
        )
        if review_passed is False:
            if review_reason:
                print(f"[Review] Final 错误原因: {review_reason}")
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
                mode=mode,
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
                    "mode": mode,
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
        f"medium_partial={difficulty_metrics.get('medium_partial_correct')}",
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
        mode,
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
