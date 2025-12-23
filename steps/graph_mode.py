from pathlib import Path
import random

from graph.pipeline_graph import build_entity_pool, build_knowledge_edges_cached, edge_to_evidence_payload
from graph.pipeline_path_sampling import sample_path
from prompts import build_graph_1hop_step_prompt, build_revise_prompt, build_stage1_step_prompt
from prompts.review import build_visual_verification_prompt
from pipeline.pipeline_review import review_question
from pipeline.pipeline_solvers import (
    grade_answer,
    solve_mcq,
    solve_mcq_no_image,
    solve_mcq_text_only,
)
from utils.api_client import call_vision_model
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
)
from utils.genqa import save_genqa_item
from utils.schema import StepResult


def generate_steps_graph_mode(
    context: str,
    image_path: Path,
    feedback: str,
    previous_final_question: str | None,
) -> tuple[list[StepResult], bool]:
    steps: list[StepResult] = []
    cross_modal_used = True

    target_hops = min(MAX_STEPS_PER_ROUND - 1, max(MIN_HOPS, 2))
    edges = build_knowledge_edges_cached(context)

    step0 = run_step(
        build_stage1_step_prompt(context, feedback, previous_final_question),
        image_path,
        select_model_for_step(0),
        0,
    )
    steps.append(step0)
    print("[Step 0] 完成 (Graph Mode anchor)")
    print(step0.question)
    print(f"标准答案: <answer>{step0.answer_letter}</answer> | answer_text={step0.answer_text}")
    if step0.answer_letter:
        medium_raw, medium_letter = solve_mcq(step0.question, image_path, MODEL_SOLVE_MEDIUM)
        medium_correct = grade_answer(step0.answer_letter or "", medium_letter)
        print(f"中求解器: {medium_raw} | correct={medium_correct}")
        
        strong_raw = None
        strong_letter = None
        strong_correct = None
        
        if not medium_correct:
            strong_raw, strong_letter = solve_mcq(step0.question, image_path, MODEL_SOLVE_STRONG)
            strong_correct = grade_answer(step0.answer_letter or "", strong_letter)
            print(f"强求解器: {strong_raw} | correct={strong_correct}")
        else:
            print("中求解器答对，跳过强求解器。")

        if not (medium_correct and strong_correct) and step0.reasoning:
            print(f"推理过程: <reasoning>{step0.reasoning}</reasoning>")
        if not medium_correct:
            review_raw, review_passed = review_question(
                step0.question,
                step0.answer_letter,
                step0.reasoning,
                image_path,
            )
            if review_passed is True:
                strong_text_only_raw, strong_text_only_letter = solve_mcq_text_only(
                    step0.question, MODEL_SOLVE_STRONG
                )
                strong_no_image_raw, strong_no_image_letter = solve_mcq_no_image(
                    step0.question, MODEL_SOLVE_STRONG
                )
                strong_text_only_correct = grade_answer(
                    step0.answer_letter or "", strong_text_only_letter
                )
                strong_no_image_correct = grade_answer(
                    step0.answer_letter or "", strong_no_image_letter
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
                    "cross_modal_used": step0.cross_modal_bridge,
                    "num_hops": step0.k,
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
                    print("[Review] Step 0 结果: text-only/no-image 可解，跳过入库")
                else:
                    target_path = (
                        Path(GENQA_SIMPLE_PATH) if strong_correct else Path(GENQA_HARD_PATH)
                    )
                    print(f"[Review] Step 0 结果: correct -> {target_path}")
                    save_genqa_item(
                        target_path,
                        {
                            "source": "step",
                            "step_k": 0,
                            "question": step0.question,
                            "answer": step0.answer_letter,
                            "reasoning": step0.reasoning,
                            "difficulty_metrics": step_metrics,
                            "review_decision": "correct",
                            "review_raw": review_raw,
                        },
                    )
            elif review_passed is False:
                print("[Review] Step 0 结果: incorrect")
            else:
                print("[Review] Step 0 结果: unknown")
    if not edges or target_hops <= 0:
        print("[Graph Mode] 知识点链为空或 hop=0，退化为仅 step_0。")
        return steps, cross_modal_used

    entity_pool = build_entity_pool(edges)
    path = sample_path(edges, target_hops)
    if not path:
        print("[Graph Mode] 知识链路径采样失败，退化为仅 step_0。")
        return steps, cross_modal_used

    current_step_index = 1
    for edge in path:
        target_side = "tail"
        distractors = [e for e in entity_pool if e != edge.tail]
        branch_candidates = [
            e for e in edges if e.head == edge.head and e.tail != edge.tail
        ]
        branch_hint = ""
        if branch_candidates:
            branch_edge = random.choice(branch_candidates)
            branch_hint = (
                "\n[Branch/Contrast Knowledge]: "
                f"{branch_edge.head} --[{branch_edge.relation}]--> {branch_edge.tail} "
            )
        operate_fact_hint = (
            f"evidence_snippet={edge.evidence or ''}\n"
            f"knowledge_link: head={edge.head} ; relation={edge.relation} ; tail={edge.tail}"
            f"{branch_hint}"
        )
        operate_distinction = run_operate_distinction_agent(
            context=context,
            image_path=image_path,
            previous_step=steps[-1],
            fact_hint=operate_fact_hint,
            feedback=feedback,
            force_cross_modal=False,
            forbidden_terms=[edge.tail],
        )
        operate_calculation = run_operate_calculation_agent(
            context=context,
            image_path=image_path,
            previous_step=steps[-1],
            fact_hint=operate_fact_hint,
            feedback=feedback,
            force_cross_modal=False,
            forbidden_terms=[edge.tail],
        )
        prompt = build_graph_1hop_step_prompt(
            anchor_question=step0.question,
            previous_step=steps[-1],
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
        )
        model = select_model_for_step(current_step_index)
        step = run_step(prompt, image_path, model, current_step_index)
        if step.evidence is None:
            step.evidence = edge_to_evidence_payload(edge)

        print(f"[Step {current_step_index}] 正在进行视觉幻觉核查...")
        verify_prompt = build_visual_verification_prompt(step.question)
        try:
            verify_raw = call_vision_model(verify_prompt, image_path, MODEL_SOLVE_STRONG)
            if "<verified>no</verified>" in verify_raw:
                print(
                    f"[Step {current_step_index}] 视觉核查失败: 题目包含图片中不存在的视觉特征。"
                )
                print(f"Question: {step.question}")
                print(f"Reason: {verify_raw}")
                continue
            print(f"[Step {current_step_index}] 视觉核查通过。")
        except Exception as exc:
            print(f"[Step {current_step_index}] 视觉核查调用出错: {exc}。默认放行。")

        medium_raw, medium_letter = solve_mcq(step.question, image_path, MODEL_SOLVE_MEDIUM)
        medium_correct = grade_answer(step.answer_letter or "", medium_letter)

        strong_raw = None
        strong_letter = None
        strong_correct = None

        if not medium_correct:
            strong_raw, strong_letter = solve_mcq(step.question, image_path, MODEL_SOLVE_STRONG)
            strong_correct = grade_answer(step.answer_letter or "", strong_letter)

        needs_revision, reason = validate_step(step, False, strong_correct)
        if not needs_revision and is_low_quality_entity_matching(step.question):
            needs_revision, reason = True, "LOW_QUALITY (entity matching / missing operator)"
        if (
            not needs_revision
            and step.modal_use in {"text", "image"}
            and steps[-1].modal_use == step.modal_use
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
            )
            step = run_step(revise_prompt, image_path, model, current_step_index)
            medium_raw, medium_letter = solve_mcq(step.question, image_path, MODEL_SOLVE_MEDIUM)
            medium_correct = grade_answer(step.answer_letter or "", medium_letter)

            strong_raw = None
            strong_letter = None
            strong_correct = None

            if not medium_correct:
                strong_raw, strong_letter = solve_mcq(step.question, image_path, MODEL_SOLVE_STRONG)
                strong_correct = grade_answer(step.answer_letter or "", strong_letter)

        print(f"[Step {current_step_index}] 完成 (Graph Mode, model={model})")
        print(step.question)
        print(f"标准答案: <answer>{step.answer_letter}</answer> | answer_text={step.answer_text}")
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
                    print(
                        f"[Review] Step {current_step_index} 结果: text-only/no-image 可解，跳过入库"
                    )
                else:
                    target_path = (
                        Path(GENQA_SIMPLE_PATH) if strong_correct else Path(GENQA_HARD_PATH)
                    )
                    print(f"[Review] Step {current_step_index} 结果: correct -> {target_path}")
                    save_genqa_item(
                        target_path,
                        {
                            "source": "step",
                            "step_k": current_step_index,
                            "question": step.question,
                            "answer": step.answer_letter,
                            "reasoning": step.reasoning,
                            "difficulty_metrics": step_metrics,
                            "review_decision": "correct",
                            "review_raw": review_raw,
                        },
                    )
            elif review_passed is False:
                print(f"[Review] Step {current_step_index} 结果: incorrect")
            else:
                print(f"[Review] Step {current_step_index} 结果: unknown")

        steps.append(step)
        current_step_index += 1

    return steps, cross_modal_used
