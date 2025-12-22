from pathlib import Path

from prompts import (
    build_extend_step_prompt,
    build_revise_prompt,
    build_stage1_step_prompt,
    build_stage2_step_prompt,
    build_stage3_step_prompt,
)
from pipeline.pipeline_facts import format_fact_hint, load_fact_candidates
from pipeline.pipeline_review import review_question
from pipeline.pipeline_solvers import (
    grade_answer,
    solve_mcq,
    solve_mcq_no_image,
    solve_mcq_text_only,
)
from steps.operate_calculation_agent import run_operate_calculation_agent
from steps.operate_distinction_agent import run_operate_distinction_agent
from steps.quality import is_low_quality_entity_matching
from steps.runner import run_step, select_model_for_step
from steps.validation import validate_step
from utils.config import (
    GENQA_HARD_PATH,
    GENQA_SIMPLE_PATH,
    MAX_STEPS_PER_ROUND,
    MIN_HOPS,
    MODEL_SOLVE_MEDIUM,
    MODEL_SOLVE_STRONG,
    REQUIRE_CROSS_MODAL,
)
from utils.genqa import save_genqa_item
from utils.schema import StepResult


def generate_steps_prompt_driven(
    context: str,
    image_path: Path,
    feedback: str,
    previous_final_question: str | None,
) -> tuple[list[StepResult], bool]:
    fact_candidates = load_fact_candidates(context, max(MAX_STEPS_PER_ROUND, 3))
    steps: list[StepResult] = []
    cross_modal_used = False
    min_steps = min(MAX_STEPS_PER_ROUND, max(MIN_HOPS, 3))

    for k in range(MAX_STEPS_PER_ROUND):
        fact = None
        if k > 0 and fact_candidates:
            fact = fact_candidates[(k - 1) % len(fact_candidates)]
        fact_hint = format_fact_hint(fact)
        force_cross_modal = REQUIRE_CROSS_MODAL and not cross_modal_used and k >= 1
        model = select_model_for_step(k)

        operate_distinction_draft = ""
        operate_calculation_draft = ""
        if k > 0 and steps:
            operate_distinction = run_operate_distinction_agent(
                context=context,
                image_path=image_path,
                previous_step=steps[-1],
                fact_hint=fact_hint,
                feedback=feedback,
                force_cross_modal=force_cross_modal,
            )
            operate_calculation = run_operate_calculation_agent(
                context=context,
                image_path=image_path,
                previous_step=steps[-1],
                fact_hint=fact_hint,
                feedback=feedback,
                force_cross_modal=force_cross_modal,
            )
            operate_distinction_draft = operate_distinction.draft
            operate_calculation_draft = operate_calculation.draft

        if k == 0:
            prompt = build_stage1_step_prompt(context, feedback, previous_final_question)
        elif k == 1:
            prompt = build_stage2_step_prompt(
                context,
                steps[-1],
                fact_hint,
                operate_distinction_draft,
                operate_calculation_draft,
                feedback,
                force_cross_modal,
            )
        elif k == 2:
            prompt = build_stage3_step_prompt(
                context,
                steps[-1],
                fact_hint,
                operate_distinction_draft,
                operate_calculation_draft,
                feedback,
                force_cross_modal,
            )
        else:
            prompt = build_extend_step_prompt(
                context,
                steps[-1],
                fact_hint,
                operate_distinction_draft,
                operate_calculation_draft,
                feedback,
                force_cross_modal,
            )

        step = run_step(prompt, image_path, model, k)
        medium_raw, medium_letter = solve_mcq(step.question, image_path, MODEL_SOLVE_MEDIUM)
        strong_raw, strong_letter = solve_mcq(step.question, image_path, MODEL_SOLVE_STRONG)
        medium_correct = grade_answer(step.answer_letter or "", medium_letter)
        strong_correct = grade_answer(step.answer_letter or "", strong_letter)
        needs_revision, reason = validate_step(step, force_cross_modal, strong_correct)

        if not needs_revision and k > 0 and is_low_quality_entity_matching(step.question):
            needs_revision, reason = True, "LOW_QUALITY (entity matching / missing operator)"

        if (
            not needs_revision
            and k > 0
            and step.modal_use in {"text", "image"}
            and steps[-1].modal_use == step.modal_use
        ):
            needs_revision, reason = True, f"modal_use consecutive pure({step.modal_use})"

        if needs_revision:
            print(f"[Step {k}] 触发 revise: {reason}")
            revise_prompt = build_revise_prompt(
                context,
                step,
                reason,
                fact_hint,
                operate_distinction_draft,
                operate_calculation_draft,
                force_cross_modal,
            )
            step = run_step(revise_prompt, image_path, model, k)
            medium_raw, medium_letter = solve_mcq(step.question, image_path, MODEL_SOLVE_MEDIUM)
            strong_raw, strong_letter = solve_mcq(step.question, image_path, MODEL_SOLVE_STRONG)
            medium_correct = grade_answer(step.answer_letter or "", medium_letter)
            strong_correct = grade_answer(step.answer_letter or "", strong_letter)

        if force_cross_modal and "cross_modal_bridge" not in step.raw:
            step.cross_modal_bridge = True

        print(f"[Step {k}] 完成 (model={model})")
        print(step.question)
        print(f"标准答案: <answer>{step.answer_letter}</answer> | answer_text={step.answer_text}")
        print(f"中求解器: {medium_raw} | correct={medium_correct}")
        print(f"强求解器: {strong_raw} | correct={strong_correct}")
        if not (medium_correct and strong_correct) and step.reasoning:
            print(f"推理过程: <reasoning>{step.reasoning}</reasoning>")
        if step.answer_letter and not medium_correct:
            review_raw, review_passed = review_question(
                step.question,
                step.answer_letter,
                step.reasoning,
                image_path,
            )
            if review_passed is True:
                strong_text_only_raw, strong_text_only_letter = solve_mcq_text_only(
                    step.question, MODEL_SOLVE_STRONG
                )
                strong_no_image_raw, strong_no_image_letter = solve_mcq_no_image(
                    step.question, MODEL_SOLVE_STRONG
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
                    "difficulty_score": 1.0
                    if (strong_correct and not medium_correct)
                    else 0.5
                    if strong_correct
                    else 0.0,
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
                    print(f"[Review] Step {k} 结果: text-only/no-image 可解，跳过入库")
                else:
                    target_path = (
                        Path(GENQA_SIMPLE_PATH) if strong_correct else Path(GENQA_HARD_PATH)
                    )
                    print(f"[Review] Step {k} 结果: correct -> {target_path}")
                    save_genqa_item(
                        target_path,
                        {
                            "source": "step",
                            "step_k": k,
                            "question": step.question,
                            "answer": step.answer_letter,
                            "reasoning": step.reasoning,
                            "difficulty_metrics": step_metrics,
                            "review_decision": "correct",
                            "review_raw": review_raw,
                        },
                    )
            elif review_passed is False:
                print(f"[Review] Step {k} 结果: incorrect")
            else:
                print(f"[Review] Step {k} 结果: unknown")

        steps.append(step)
        cross_modal_used = cross_modal_used or step.cross_modal_bridge

        if k + 1 >= min_steps and (not REQUIRE_CROSS_MODAL or cross_modal_used):
            break

    return steps, cross_modal_used
