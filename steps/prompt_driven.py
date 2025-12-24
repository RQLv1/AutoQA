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
from steps.obfuscate_agent import obfuscate_step_question
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
from utils.details_logger import get_details_logger
from utils.genqa import save_genqa_item
from utils.schema import StepResult
from utils.terminal import print_step_input, print_step_summary


def generate_steps_prompt_driven(
    context: str,
    image_path: Path,
    feedback: str,
    previous_final_question: str | None,
    visual_summary: str | None,
) -> tuple[list[StepResult], bool]:
    fact_candidates = load_fact_candidates(context, max(MAX_STEPS_PER_ROUND, 3))
    steps: list[StepResult] = []
    cross_modal_used = False
    min_steps = min(MAX_STEPS_PER_ROUND, max(MIN_HOPS, 3))

    for k in range(MAX_STEPS_PER_ROUND):
        fact = None
        if k > 0 and fact_candidates:
            fact = fact_candidates[(k - 1) % len(fact_candidates)]
        elif k == 0 and previous_final_question and fact_candidates:
            fact = fact_candidates[0]
        fact_hint = format_fact_hint(fact)
        force_cross_modal = REQUIRE_CROSS_MODAL and not cross_modal_used and (
            k >= 1 or previous_final_question is not None
        )
        model = select_model_for_step(k)

        operate_distinction_draft = ""
        operate_calculation_draft = ""
        effective_previous_step = None
        if k > 0 and steps:
            effective_previous_step = steps[-1]
        elif k == 0 and previous_final_question:
            effective_previous_step = StepResult(
                k=-1,
                question=previous_final_question,
                answer_text="(inherited from previous round)",
                answer_letter=None,
                evidence=None,
                modal_use="unknown",
                cross_modal_bridge=True,
                raw="",
            )

        if effective_previous_step:
            operate_distinction = run_operate_distinction_agent(
                context=context,
                image_path=image_path,
                previous_step=effective_previous_step,
                fact_hint=fact_hint,
                feedback=feedback,
                force_cross_modal=force_cross_modal,
            )
            operate_calculation = run_operate_calculation_agent(
                context=context,
                image_path=image_path,
                previous_step=effective_previous_step,
                fact_hint=fact_hint,
                feedback=feedback,
                force_cross_modal=force_cross_modal,
            )
            operate_distinction_draft = operate_distinction.draft
            operate_calculation_draft = operate_calculation.draft
            get_details_logger().log_event(
                "operate_drafts",
                {
                    "step": k,
                    "fact_hint": fact_hint,
                    "operate_distinction": operate_distinction_draft,
                    "operate_distinction_raw": operate_distinction.raw,
                    "operate_calculation": operate_calculation_draft,
                    "operate_calculation_raw": operate_calculation.raw,
                    "force_cross_modal": force_cross_modal,
                },
            )

        if k == 0:
            if previous_final_question and effective_previous_step:
                prompt = build_extend_step_prompt(
                    context,
                    effective_previous_step,
                    fact_hint,
                    operate_distinction_draft,
                    operate_calculation_draft,
                    feedback,
                    force_cross_modal,
                    visual_summary,
                )
            else:
                prompt = build_stage1_step_prompt(
                    context,
                    feedback,
                    previous_final_question,
                    visual_summary,
                )
        elif k == 1:
            prompt = build_stage2_step_prompt(
                context,
                steps[-1],
                fact_hint,
                operate_distinction_draft,
                operate_calculation_draft,
                feedback,
                force_cross_modal,
                visual_summary,
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
                visual_summary,
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
                visual_summary,
            )

        print_step_input(
            step_index=k,
            model=model,
            mode="prompt",
            fact_hint=fact_hint,
            force_cross_modal=force_cross_modal,
            has_operate_calc=bool(operate_calculation_draft.strip()),
            has_operate_dist=bool(operate_distinction_draft.strip()),
        )
        step = run_step(prompt, image_path, model, k)
        step = obfuscate_step_question(step)
        print(f"[Step {k}] 更新后题目:")
        print(step.question)
        get_details_logger().log_event(
            "step_result",
            {
                "step": k,
                "question": step.question,
                "answer_letter": step.answer_letter,
                "answer_text": step.answer_text,
                "reasoning": step.reasoning,
                "modal_use": step.modal_use,
                "cross_modal_bridge": step.cross_modal_bridge,
            },
        )
        medium_raw, medium_letter = solve_mcq(step.question, image_path, MODEL_SOLVE_MEDIUM)
        medium_correct = grade_answer(step.answer_letter or "", medium_letter)
        
        strong_raw = None
        strong_letter = None
        strong_correct = None
        strong_text_only_raw = None
        strong_text_only_letter = None
        strong_text_only_correct = None
        
        if not medium_correct:
            strong_text_only_raw, strong_text_only_letter = solve_mcq_text_only(
                step.question, MODEL_SOLVE_STRONG
            )
            strong_text_only_correct = grade_answer(
                step.answer_letter or "", strong_text_only_letter
            )
            strong_raw, strong_letter = solve_mcq(step.question, image_path, MODEL_SOLVE_STRONG)
            strong_correct = grade_answer(step.answer_letter or "", strong_letter)
            
        needs_revision, reason = validate_step(
            step,
            force_cross_modal,
            strong_correct,
            medium_correct,
            strong_text_only_correct,
        )
        revise_reason = reason if needs_revision else None

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
                visual_summary,
            )
            step = run_step(revise_prompt, image_path, model, k)
            step = obfuscate_step_question(step)
            print(f"[Step {k}] 更新后题目:")
            print(step.question)
            medium_raw, medium_letter = solve_mcq(step.question, image_path, MODEL_SOLVE_MEDIUM)
            medium_correct = grade_answer(step.answer_letter or "", medium_letter)
            
            strong_raw = None
            strong_letter = None
            strong_correct = None
            strong_text_only_raw = None
            strong_text_only_letter = None
            strong_text_only_correct = None
            
            if not medium_correct:
                strong_text_only_raw, strong_text_only_letter = solve_mcq_text_only(
                    step.question, MODEL_SOLVE_STRONG
                )
                strong_text_only_correct = grade_answer(
                    step.answer_letter or "", strong_text_only_letter
                )
                strong_raw, strong_letter = solve_mcq(step.question, image_path, MODEL_SOLVE_STRONG)
                strong_correct = grade_answer(step.answer_letter or "", strong_letter)
            get_details_logger().log_event(
                "step_result_revised",
                {
                    "step": k,
                    "reason": reason,
                    "question": step.question,
                    "answer_letter": step.answer_letter,
                    "answer_text": step.answer_text,
                    "reasoning": step.reasoning,
                    "modal_use": step.modal_use,
                    "cross_modal_bridge": step.cross_modal_bridge,
                },
            )
            revise_reason = reason

        if force_cross_modal and "cross_modal_bridge" not in step.raw:
            step.cross_modal_bridge = True

        print(f"[Step {k}] 完成 (model={model})")
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
                    # 逻辑修改：Strong 错 -> Hard; Strong 对 -> Simple
                    if not strong_correct:
                        target_path = Path(GENQA_HARD_PATH)
                        print(f"[Review] Step {k} 结果: correct -> {target_path} (Hard: Medium=X, Strong=X)")
                    else:
                        target_path = Path(GENQA_SIMPLE_PATH)
                        print(f"[Review] Step {k} 结果: correct -> {target_path} (Simple: Medium=X, Strong=O)")

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
