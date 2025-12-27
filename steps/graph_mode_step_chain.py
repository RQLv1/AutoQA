"""Graph mode step chain generation logic (Steps 1+)."""

import random
from pathlib import Path

from graph.pipeline_graph import KnowledgeEdge, build_entity_pool, edge_to_evidence_payload
from prompts import build_graph_1hop_step_prompt, build_revise_prompt
from prompts.review import build_visual_verification_prompt
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
from steps.quality import is_low_quality_entity_matching
from steps.runner import run_step, select_model_for_step
from utils.api_client import call_vision_model
from utils.config import MODEL_REVIEW
from utils.details_logger import get_details_logger
from utils.schema import StepResult


def generate_step_chain(
    context: str,
    image_path: Path,
    feedback: str,
    visual_summary: str | None,
    step0: StepResult,
    path: list[KnowledgeEdge],
    all_edges: list[KnowledgeEdge],
) -> list[StepResult]:
    """
    Generate subsequent steps (1+) along the knowledge graph path.

    Args:
        context: Reference text
        image_path: Path to image
        feedback: User feedback
        visual_summary: Optional visual summary
        step0: The anchor step (Step 0)
        path: Sampled knowledge graph path
        all_edges: All available knowledge edges

    Returns:
        List of StepResults (excluding Step 0, which is passed in)
    """
    steps: list[StepResult] = []
    entity_pool = build_entity_pool(all_edges)
    current_step_index = 1

    for edge in path:
        target_side = "tail"
        distractors = [e for e in entity_pool if e != edge.tail]
        branch_candidates = [
            e for e in all_edges if e.head == edge.head and e.tail != edge.tail
        ]
        branch_hint = ""
        if branch_candidates:
            branch_edge = random.choice(branch_candidates)
            branch_label = edge_source_label(branch_edge)
            branch_hint = (
                "\n[Branch/Contrast Knowledge]"
                f"[来源: {branch_label}]: "
                f"{branch_edge.head} --[{branch_edge.relation}]--> {branch_edge.tail}"
            )

        source_label = edge_source_label(edge)
        source_prefix = (
            "根据对图片的视觉分析 (Visual Analysis)"
            if edge.source_type == "image"
            else "根据参考信息 (Reference)"
        )
        operate_fact_hint = (
            f"[来源: {source_label}]\n"
            f"evidence_snippet={edge.evidence or ''}\n"
            f"knowledge_link: head={edge.head} ; relation={edge.relation} ; tail={edge.tail}"
            f"{branch_hint}"
        )

        # Get previous step (could be step0 or last step in chain)
        previous_step = step0 if not steps else steps[-1]

        # Run operate agents
        operate_distinction = run_operate_distinction_agent(
            context=context,
            image_path=image_path,
            previous_step=previous_step,
            fact_hint=operate_fact_hint,
            feedback=feedback,
            force_cross_modal=False,
            forbidden_terms=[edge.tail],
        )
        operate_calculation = run_operate_calculation_agent(
            context=context,
            image_path=image_path,
            previous_step=previous_step,
            fact_hint=operate_fact_hint,
            feedback=feedback,
            force_cross_modal=False,
            forbidden_terms=[edge.tail],
        )
        get_details_logger().log_event(
            "operate_drafts",
            {
                "step": current_step_index,
                "fact_hint": operate_fact_hint,
                "operate_distinction": operate_distinction.draft,
                "operate_distinction_raw": operate_distinction.raw,
                "operate_calculation": operate_calculation.draft,
                "operate_calculation_raw": operate_calculation.raw,
                "force_cross_modal": False,
            },
        )

        # Build prompt and generate step
        prompt = build_graph_1hop_step_prompt(
            anchor_question=step0.question,
            previous_step=previous_step,
            evidence_snippet=edge.evidence or "",
            head=edge.head,
            relation=edge.relation,
            tail=edge.tail,
            target_side=target_side,
            operate_distinction_draft=operate_distinction.draft,
            operate_calculation_draft=operate_calculation.draft,
            distractor_entities=distractors,
            feedback=feedback,
            force_cross_modal=False,
            knowledge_source_label=source_label,
            knowledge_source_prefix=source_prefix,
            visual_summary=visual_summary,
        )
        model = select_model_for_step(current_step_index)
        from utils.terminal import print_step_input
        print_step_input(
            step_index=current_step_index,
            model=model,
            mode="graph",
            fact_hint=operate_fact_hint,
            force_cross_modal=False,
            has_operate_calc=bool(operate_calculation.draft.strip()),
            has_operate_dist=bool(operate_distinction.draft.strip()),
        )

        step = run_step(prompt, image_path, model, current_step_index)
        step = obfuscate_step_question(step)
        print(f"[Step {current_step_index}] 更新后题目:")
        print(step.question)
        if step.evidence is None:
            step.evidence = edge_to_evidence_payload(edge)
        get_details_logger().log_event(
            "step_result",
            {
                "step": current_step_index,
                "question": step.question,
                "answer_letter": step.answer_letter,
                "answer_text": step.answer_text,
                "reasoning": step.reasoning,
                "modal_use": step.modal_use,
                "cross_modal_bridge": step.cross_modal_bridge,
            },
        )

        # Visual hallucination check
        max_visual_revisions = 2
        visual_attempts = 0
        while True:
            print(f"[Step {current_step_index}] 正在进行视觉幻觉核查...")
            verify_prompt = build_visual_verification_prompt(step.question)
            try:
                verify_raw = call_vision_model(verify_prompt, image_path, MODEL_REVIEW)
            except Exception as exc:
                print(f"[Step {current_step_index}] 视觉核查调用出错: {exc}。默认放行。")
                break

            if "<verified>no</verified>" not in verify_raw:
                print(f"[Step {current_step_index}] 视觉核查通过。")
                break

            visual_attempts += 1
            print(
                f"[Step {current_step_index}] 视觉核查失败: 题目包含图片中不存在的视觉特征。"
            )
            print(f"Question: {step.question}")
            print(f"Reason: {verify_raw}")
            if visual_attempts > max_visual_revisions:
                print(
                    f"[Step {current_step_index}] 视觉核查失败次数过多，跳过该 step。"
                )
                step = None
                break

            extra_requirements = (
                '- 必须隐藏推理逻辑与引导，不要在题干中出现"根据/因此/由此可知/请先/先…再…"等提示语。\n'
                '- 只给出中性条件与判据，不显式说明计算或分支步骤。'
            )
            revise_prompt = build_revise_prompt(
                context,
                step,
                "visual hallucination",
                f"knowledge_link=({edge.head},{edge.relation},{edge.tail})",
                operate_distinction.draft,
                operate_calculation.draft,
                False,
                visual_summary,
                extra_requirements=extra_requirements,
            )
            step = run_step(revise_prompt, image_path, model, current_step_index)
            step = obfuscate_step_question(step)
            print(f"[Step {current_step_index}] 更新后题目:")
            print(step.question)
            if step.evidence is None:
                step.evidence = edge_to_evidence_payload(edge)
            get_details_logger().log_event(
                "step_result_revised",
                {
                    "step": current_step_index,
                    "reason": "visual_hallucination",
                    "question": step.question,
                    "answer_letter": step.answer_letter,
                    "answer_text": step.answer_text,
                    "reasoning": step.reasoning,
                    "modal_use": step.modal_use,
                    "cross_modal_bridge": step.cross_modal_bridge,
                },
            )

        if step is None:
            continue

        # Evaluate with solvers
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
        ) = evaluate_step_with_solvers(step, image_path, False)

        # Validate and check for revision
        needs_revision, reason = validate_and_check_needs_revision(
            step, False, strong_correct, medium_correct, strong_text_only_correct
        )
        revise_reason = reason if needs_revision else None

        # Additional quality checks
        if not needs_revision and is_low_quality_entity_matching(step.question):
            needs_revision, reason = True, "LOW_QUALITY (entity matching / missing operator)"
        if (
            not needs_revision
            and step.modal_use in {"text", "image"}
            and previous_step.modal_use == step.modal_use
        ):
            needs_revision, reason = True, f"modal_use consecutive pure({step.modal_use})"

        if needs_revision:
            print(f"[Step {current_step_index}] 触发 revise: {reason}")
            revise_prompt = build_revise_prompt(
                context,
                step,
                reason,
                f"knowledge_link=({edge.head},{edge.relation},{edge.tail})",
                operate_distinction.draft,
                operate_calculation.draft,
                False,
                visual_summary,
            )
            step = run_step(revise_prompt, image_path, model, current_step_index)
            step = obfuscate_step_question(step)
            print(f"[Step {current_step_index}] 更新后题目:")
            print(step.question)

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
            ) = evaluate_step_with_solvers(step, image_path, False)

            get_details_logger().log_event(
                "step_result_revised",
                {
                    "step": current_step_index,
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

        # Print results
        print_solver_results(
            current_step_index,
            step,
            medium_raw,
            medium_correct,
            strong_raw,
            strong_correct,
            strong_text_only_correct,
            revise_reason,
        )

        # Review and save if passes
        if step.answer_letter:
            review_and_save_step(
                step,
                current_step_index,
                image_path,
                medium_correct,
                strong_correct,
                medium_letter,
                strong_letter,
                medium_raw,
                strong_raw,
            )

        steps.append(step)
        current_step_index += 1

    return steps
