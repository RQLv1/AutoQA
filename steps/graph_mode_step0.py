"""Graph mode Step 0 generation logic."""

import random
from pathlib import Path

from graph.pipeline_graph import KnowledgeEdge
from prompts import build_extend_step_prompt, build_revise_prompt, build_stage1_step_prompt
from steps.graph_mode_evaluation import (
    evaluate_step_with_solvers,
    print_solver_results,
    review_and_save_step,
    validate_and_check_needs_revision,
)
from steps.graph_mode_utils import edge_source_label
from steps.obfuscate_agent import obfuscate_step_question
from steps.operate_calculation_agent import run_operate_calculation_agent
from steps.operate_distinction_agent import run_operate_distinction_agent
from steps.runner import run_step, select_model_for_step
from utils.details_logger import get_details_logger
from utils.schema import StepResult
from utils.terminal import print_step_input


def generate_step0(
    context: str,
    image_path: Path,
    feedback: str,
    previous_final_question: str | None,
    visual_summary: str | None,
    all_edges: list[KnowledgeEdge],
    mode: str = "multi_select",
) -> StepResult:
    """
    Generate Step 0 in graph mode.

    Returns the generated StepResult.
    """
    model = select_model_for_step(0)
    operate_distinction = None
    operate_calculation = None
    fact_hint_for_revision = "请基于图片进行综合推断。"

    # Build prompt based on whether this is extending from a previous question
    if previous_final_question:
        dummy_prev = StepResult(
            k=-1,
            question=previous_final_question,
            answer_text="(inherited from previous round)",
            answer_letter=None,
            evidence=None,
            modal_use="unknown",
            cross_modal_bridge=True,
            raw="",
        )
        fact_hint = "请基于图片与参考信息进行综合推断。"
        if all_edges:
            edge = random.choice(all_edges)
            source_label = edge_source_label(edge)
            fact_hint = (
                f"[来源: {source_label}]\n"
                f"Knowledge Link: {edge.head} -> {edge.relation} -> {edge.tail}\n"
                f"Evidence: {edge.evidence}"
            )
        operate_distinction = run_operate_distinction_agent(
            context=context,
            image_path=image_path,
            previous_step=dummy_prev,
            fact_hint=fact_hint,
            feedback=feedback,
            force_cross_modal=True,
        )
        operate_calculation = run_operate_calculation_agent(
            context=context,
            image_path=image_path,
            previous_step=dummy_prev,
            fact_hint=fact_hint,
            feedback=feedback,
            force_cross_modal=True,
        )
        fact_hint_for_revision = fact_hint
        get_details_logger().log_event(
            "operate_drafts",
            {
                "step": 0,
                "fact_hint": fact_hint,
                "operate_distinction": operate_distinction.draft,
                "operate_distinction_raw": operate_distinction.raw,
                "operate_calculation": operate_calculation.draft,
                "operate_calculation_raw": operate_calculation.raw,
                "force_cross_modal": True,
            },
        )
        prompt = build_extend_step_prompt(
            context,
            dummy_prev,
            fact_hint,
            operate_distinction.draft,
            operate_calculation.draft,
            feedback,
            force_cross_modal=True,
            visual_summary=visual_summary,
            mode=mode,
        )
    else:
        prompt = build_stage1_step_prompt(
            context,
            feedback,
            previous_final_question,
            visual_summary,
            mode=mode,
        )

    print_step_input(
        step_index=0,
        model=model,
        mode="graph",
        fact_hint=fact_hint_for_revision if previous_final_question else "graph_anchor",
        force_cross_modal=True,
        has_operate_calc=bool(operate_calculation.draft.strip()) if operate_calculation else False,
        has_operate_dist=bool(operate_distinction.draft.strip()) if operate_distinction else False,
    )

    # Generate initial step
    step0 = run_step(prompt, image_path, model, 0)
    step0 = obfuscate_step_question(step0)
    print("[Step 0] 更新后题目:")
    print(step0.question)
    get_details_logger().log_event(
        "step_result",
        {
            "step": 0,
            "question": step0.question,
            "answer_letter": step0.answer_letter,
            "answer_text": step0.answer_text,
            "reasoning": step0.reasoning,
            "modal_use": step0.modal_use,
            "cross_modal_bridge": step0.cross_modal_bridge,
        },
    )

    # Evaluate with solvers
    if step0.answer_letter:
        (
            medium_raw,
            medium_letter,
            medium_correct,
            strong_raw,
            strong_letter,
            strong_correct,
            strong_text_only_raw,
            strong_text_only_letter,
            strong_text_only_correct,
        ) = evaluate_step_with_solvers(step0, image_path, False, mode=mode)

        # Validate and revise if needed
        needs_revision, reason = validate_and_check_needs_revision(
            step0, False, strong_correct, medium_correct, strong_text_only_correct, mode=mode
        )
        revise_reason = reason if needs_revision else None

        if needs_revision:
            print(f"[Step 0] 触发 revise: {reason}")
            revise_prompt = build_revise_prompt(
                context,
                step0,
                reason,
                fact_hint_for_revision,
                operate_distinction.draft if operate_distinction else "",
                operate_calculation.draft if operate_calculation else "",
                False,
                visual_summary,
                mode=mode,
            )
            step0 = run_step(revise_prompt, image_path, model, 0)
            step0 = obfuscate_step_question(step0)
            print("[Step 0] 更新后题目:")
            print(step0.question)

            # Re-evaluate after revision
            (
                medium_raw,
                medium_letter,
                medium_correct,
                strong_raw,
                strong_letter,
                strong_correct,
                strong_text_only_raw,
                strong_text_only_letter,
                strong_text_only_correct,
            ) = evaluate_step_with_solvers(step0, image_path, False, mode=mode)

            get_details_logger().log_event(
                "step_result_revised",
                {
                    "step": 0,
                    "reason": reason,
                    "question": step0.question,
                    "answer_letter": step0.answer_letter,
                    "answer_text": step0.answer_text,
                    "reasoning": step0.reasoning,
                    "modal_use": step0.modal_use,
                    "cross_modal_bridge": step0.cross_modal_bridge,
                },
            )
            revise_reason = reason

        # Print results
        print_solver_results(
            0,
            step0,
            medium_raw,
            medium_correct,
            strong_raw,
            strong_correct,
            strong_text_only_correct,
            revise_reason,
        )

        # Review and save if passes
        review_and_save_step(
            step0,
            0,
            image_path,
            medium_correct,
            strong_correct,
            medium_letter,
            strong_letter,
            medium_raw,
            strong_raw,
            mode=mode,
        )

    return step0
