"""Graph mode evaluation: solver testing, validation, and review logic."""

from pathlib import Path

from pipeline.pipeline_review import review_question
from pipeline.pipeline_solvers import (
    grade_answer,
    solve_mcq,
    solve_mcq_no_image,
    solve_mcq_text_only,
)
from steps.validation import validate_step
from utils.config import (
    GENQA_MEDIUM_PATH,
    GENQA_STRONG_PATH,
    GENQA_SIMPLE_PATH,
    MODEL_SOLVE_MEDIUM,
    MODEL_SOLVE_STRONG,
)
from utils.genqa import save_genqa_item
from utils.schema import StepResult
from utils.terminal import print_step_summary


def evaluate_step_with_solvers(
    step: StepResult,
    image_path: Path,
    is_graph_mode: bool,
    mode: str = "multi_select",
) -> tuple[
    str | None,  # medium_raw
    str | None,  # medium_letter
    bool,        # medium_correct
    str | None,  # strong_raw
    str | None,  # strong_letter
    bool | None, # strong_correct
    str | None,  # strong_text_only_raw
    str | None,  # strong_text_only_letter
    bool | None, # strong_text_only_correct
]:
    """
    Evaluate step with Medium and Strong solvers.
    Returns (medium_raw, medium_letter, medium_correct,
             strong_raw, strong_letter, strong_correct,
             strong_text_only_raw, strong_text_only_letter, strong_text_only_correct).
    """
    if not step.answer_letter:
        return None, None, False, None, None, None, None, None, None

    medium_raw, medium_letter = solve_mcq(step.question, image_path, MODEL_SOLVE_MEDIUM, mode=mode)
    medium_correct = grade_answer(step.answer_letter or "", medium_letter)

    strong_raw = None
    strong_letter = None
    strong_correct = None
    strong_text_only_raw = None
    strong_text_only_letter = None
    strong_text_only_correct = None

    if not medium_correct:
        strong_text_only_raw, strong_text_only_letter = solve_mcq_text_only(
            step.question, MODEL_SOLVE_STRONG, mode=mode
        )
        strong_text_only_correct = grade_answer(
            step.answer_letter or "", strong_text_only_letter
        )
        strong_raw, strong_letter = solve_mcq(step.question, image_path, MODEL_SOLVE_STRONG, mode=mode)
        strong_correct = grade_answer(step.answer_letter or "", strong_letter)

    return (
        medium_raw,
        medium_letter,
        medium_correct,
        strong_raw,
        strong_letter,
        strong_correct,
        strong_text_only_raw,
        strong_text_only_letter,
        strong_text_only_correct,
    )


def validate_and_check_needs_revision(
    step: StepResult,
    is_graph_mode: bool,
    strong_correct: bool | None,
    medium_correct: bool,
    strong_text_only_correct: bool | None,
    mode: str = "multi_select",
) -> tuple[bool, str]:
    """
    Check if step needs revision based on validation rules.
    Returns (needs_revision, reason).
    """
    needs_revision, reason = validate_step(
        step, is_graph_mode, strong_correct, medium_correct, strong_text_only_correct, mode=mode
    )
    return needs_revision, reason


def review_and_save_step(
    step: StepResult,
    step_index: int,
    image_path: Path,
    medium_correct: bool,
    strong_correct: bool | None,
    medium_letter: str | None,
    strong_letter: str | None,
    medium_raw: str | None,
    strong_raw: str | None,
    mode: str = "multi_select",
) -> None:
    """
    Review step and save to appropriate output file if it passes review.
    """
    if not step.answer_letter:
        return

    review_raw, review_passed, review_reason = review_question(
        step.question,
        step.answer_letter,
        step.reasoning,
        image_path,
        mode=mode,
    )

    if review_passed is True:
        # Run additional solver tests
        strong_text_only_raw, strong_text_only_letter = solve_mcq_text_only(
            step.question, MODEL_SOLVE_STRONG, mode=mode
        )
        strong_no_image_raw, strong_no_image_letter = solve_mcq_no_image(
            step.question, MODEL_SOLVE_STRONG, mode=mode
        )
        strong_text_only_correct = grade_answer(
            step.answer_letter or "", strong_text_only_letter
        )
        strong_no_image_correct = grade_answer(
            step.answer_letter or "", strong_no_image_letter
        )

        step_metrics = {
            "medium_correct": medium_correct,
            "strong_correct": strong_correct,
            "strong_text_only_correct": strong_text_only_correct,
            "strong_no_image_correct": strong_no_image_correct,
            "difficulty_score": (
                0.0
                if medium_correct
                else 0.5
                if strong_correct
                else 1.0
            ),
            "cross_modal_used": step.cross_modal_bridge,
            "num_hops": step.k,
            "medium_pred": medium_letter,
            "strong_pred": strong_letter,
            "strong_text_only_pred": strong_text_only_letter,
            "strong_no_image_pred": strong_no_image_letter,
            "medium_raw": medium_raw,
            "strong_raw": strong_raw,
            "strong_text_only_raw": strong_text_only_raw,
            "strong_no_image_raw": strong_no_image_raw,
        }

        if strong_text_only_correct or strong_no_image_correct:
            print(
                f"[Review] Step {step_index} 结果: text-only/no-image 可解，跳过入库"
            )
        else:
            if medium_correct:
                target_path = Path(GENQA_SIMPLE_PATH)
                print(f"[Review] Step {step_index} 结果: correct -> {target_path} (Simple: Medium=O)")
            elif strong_correct:
                target_path = Path(GENQA_MEDIUM_PATH)
                print(f"[Review] Step {step_index} 结果: correct -> {target_path} (Medium: Medium=X, Strong=O)")
            else:
                target_path = Path(GENQA_STRONG_PATH)
                print(f"[Review] Step {step_index} 结果: correct -> {target_path} (Strong: Medium=X, Strong=X)")

            save_genqa_item(
                target_path,
                {
                    "source": "step",
                        "step_k": step_index,
                        "image_path": str(image_path),
                        "question": step.question,
                        "answer": step.answer_letter,
                        "reasoning": step.reasoning,
                        "difficulty_metrics": step_metrics,
                        "review_decision": "correct",
                        "review_raw": review_raw,
                    },
                )
    elif review_passed is False:
        print(f"[Review] Step {step_index} 结果: incorrect")
        if review_reason:
            print(f"[Review] 错误原因: {review_reason}")
    else:
        print(f"[Review] Step {step_index} 结果: unknown")


def print_solver_results(
    step_index: int,
    step: StepResult,
    medium_raw: str | None,
    medium_correct: bool,
    strong_raw: str | None,
    strong_correct: bool | None,
    strong_text_only_correct: bool | None,
    revise_reason: str | None,
) -> None:
    """Print solver evaluation results to console."""
    print(f"[Step {step_index}] 完成 (Graph Mode{'anchor' if step_index == 0 else ''})") if step_index == 0 else print(f"[Step {step_index}] 完成 (Graph Mode)")
    print(step.question)
    print(f"标准答案: <answer>{step.answer_letter}</answer> | answer_text={step.answer_text}")
    print_step_summary(
        step=step,
        medium_correct=medium_correct,
        strong_correct=strong_correct,
        text_only_correct=strong_text_only_correct,
        revise_reason=revise_reason,
    )
    print(f"中求解器: {medium_raw} | correct={medium_correct}")
    if not medium_correct:
        print(f"强求解器: {strong_raw} | correct={strong_correct}")
    else:
        print("中求解器答对，跳过强求解器。")
    if not (medium_correct and strong_correct) and step.reasoning:
        print(f"推理过程: <reasoning>{step.reasoning}</reasoning>")
