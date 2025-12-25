from pathlib import Path
import random

from graph.pipeline_graph import (
    KnowledgeEdge,
    build_entity_pool,
    build_knowledge_edges_cached,
    edge_to_evidence_payload,
)
from graph.pipeline_path_sampling import sample_path
from prompts import (
    build_extend_step_prompt,
    build_graph_1hop_step_prompt,
    build_revise_prompt,
    build_stage1_step_prompt,
)
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
from steps.obfuscate_agent import obfuscate_step_question
from steps.quality import is_low_quality_entity_matching
from steps.runner import run_step, select_model_for_step
from steps.validation import validate_step
from utils.config import (
    GENQA_HARD_PATH,
    GENQA_SIMPLE_PATH,
    MAX_STEPS_PER_ROUND,
    MIN_HOPS,
    MODEL_REVIEW,
    MODEL_SOLVE_MEDIUM,
    MODEL_SOLVE_STRONG,
)
from utils.details_logger import get_details_logger
from utils.genqa import save_genqa_item
from utils.schema import StepResult
from utils.terminal import print_step_input, print_step_summary


def _normalize_edges(
    edges: list[KnowledgeEdge] | None, default_source_type: str
) -> list[KnowledgeEdge]:
    if not edges:
        return []
    normalized: list[KnowledgeEdge] = []
    for edge in edges:
        normalized.append(
            KnowledgeEdge(
                head=edge.head,
                relation=edge.relation,
                tail=edge.tail,
                evidence=edge.evidence,
                source_id=edge.source_id,
                source_type=edge.source_type or default_source_type,
            )
        )
    return normalized


def _merge_edges_with_visual(
    text_edges: list[KnowledgeEdge], visual_edges: list[KnowledgeEdge] | None
) -> list[KnowledgeEdge]:
    normalized_text = _normalize_edges(text_edges, "text")
    normalized_visual = _normalize_edges(visual_edges, "image")
    if not normalized_visual:
        return normalized_text

    max_source_id = max((edge.source_id or 0) for edge in normalized_text) if normalized_text else 0
    offset = max_source_id + 1000
    remapped_visual: list[KnowledgeEdge] = []
    for idx, edge in enumerate(normalized_visual, start=1):
        source_id = edge.source_id
        if source_id is None:
            source_id = offset + idx
        else:
            source_id = offset + source_id
        remapped_visual.append(
            KnowledgeEdge(
                head=edge.head,
                relation=edge.relation,
                tail=edge.tail,
                evidence=edge.evidence,
                source_id=source_id,
                source_type="image",
            )
        )
    return [*normalized_text, *remapped_visual]


def _sample_path_with_visual(
    edges: list[KnowledgeEdge], length: int, require_visual: bool
) -> list[KnowledgeEdge]:
    if not require_visual:
        return sample_path(edges, length)
    for _ in range(6):
        path = sample_path(edges, length)
        if any(edge.source_type == "image" for edge in path):
            return path
    return sample_path(edges, length)


def _edge_source_label(edge: KnowledgeEdge) -> str:
    return "图片视觉分析" if edge.source_type == "image" else "参考信息"


def generate_steps_graph_mode(
    context: str,
    image_path: Path,
    feedback: str,
    previous_final_question: str | None,
    visual_summary: str | None,
    visual_edges: list[KnowledgeEdge] | None,
) -> tuple[list[StepResult], bool]:
    steps: list[StepResult] = []
    cross_modal_used = True

    target_hops = min(MAX_STEPS_PER_ROUND - 1, max(MIN_HOPS, 2))
    text_edges = build_knowledge_edges_cached(context)
    all_edges = _merge_edges_with_visual(text_edges, visual_edges)

    prompt = ""
    model = select_model_for_step(0)
    operate_distinction = None
    operate_calculation = None
    fact_hint_for_revision = "请基于图片进行综合推断。"

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
            source_label = _edge_source_label(edge)
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
        )
    else:
        prompt = build_stage1_step_prompt(
            context,
            feedback,
            previous_final_question,
            visual_summary,
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
    print("[Step 0] 完成 (Graph Mode anchor)")
    print(step0.question)
    print(f"标准答案: <answer>{step0.answer_letter}</answer> | answer_text={step0.answer_text}")
    if step0.answer_letter:
        medium_raw, medium_letter = solve_mcq(step0.question, image_path, MODEL_SOLVE_MEDIUM)
        medium_correct = grade_answer(step0.answer_letter or "", medium_letter)
        
        strong_raw = None
        strong_letter = None
        strong_correct = None
        strong_text_only_raw = None
        strong_text_only_letter = None
        strong_text_only_correct = None
        
        if not medium_correct:
            strong_text_only_raw, strong_text_only_letter = solve_mcq_text_only(
                step0.question, MODEL_SOLVE_STRONG
            )
            strong_text_only_correct = grade_answer(
                step0.answer_letter or "", strong_text_only_letter
            )
            strong_raw, strong_letter = solve_mcq(step0.question, image_path, MODEL_SOLVE_STRONG)
            strong_correct = grade_answer(step0.answer_letter or "", strong_letter)

        needs_revision, reason = validate_step(
            step0, False, strong_correct, medium_correct, strong_text_only_correct
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
            )
            step0 = run_step(revise_prompt, image_path, model, 0)
            step0 = obfuscate_step_question(step0)
            print("[Step 0] 更新后题目:")
            print(step0.question)
            medium_raw, medium_letter = solve_mcq(step0.question, image_path, MODEL_SOLVE_MEDIUM)
            medium_correct = grade_answer(step0.answer_letter or "", medium_letter)

            strong_raw = None
            strong_letter = None
            strong_correct = None
            strong_text_only_raw = None
            strong_text_only_letter = None
            strong_text_only_correct = None

            if not medium_correct:
                strong_text_only_raw, strong_text_only_letter = solve_mcq_text_only(
                    step0.question, MODEL_SOLVE_STRONG
                )
                strong_text_only_correct = grade_answer(
                    step0.answer_letter or "", strong_text_only_letter
                )
                strong_raw, strong_letter = solve_mcq(step0.question, image_path, MODEL_SOLVE_STRONG)
                strong_correct = grade_answer(step0.answer_letter or "", strong_letter)
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

        print_step_summary(
            step=step0,
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
        if not (medium_correct and strong_correct) and step0.reasoning:
            print(f"推理过程: <reasoning>{step0.reasoning}</reasoning>")
        if not medium_correct:
            review_raw, review_passed, review_reason = review_question(
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
                    if strong_correct:
                        target_path = Path(GENQA_HARD_PATH)
                        print(f"[Review] Step 0 结果: correct -> {target_path} (Hard: Medium=X, Strong=O)")
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
                    else:
                        print(f"[Review] Step 0 结果: Strong Solver 也失败，视为无效/超难题，跳过入库")
            elif review_passed is False:
                print("[Review] Step 0 结果: incorrect")
                if review_reason:
                    print(f"[Review] 错误原因: {review_reason}")
            else:
                print("[Review] Step 0 结果: unknown")
    steps.append(step0)

    if not all_edges or target_hops <= 0:
        print("[Graph Mode] 知识点链为空或 hop=0，退化为仅 step_0。")
        return steps, cross_modal_used

    entity_pool = build_entity_pool(all_edges)
    require_visual = any(edge.source_type == "image" for edge in all_edges)
    path = _sample_path_with_visual(all_edges, target_hops, require_visual)
    if not path:
        print("[Graph Mode] 知识链路径采样失败，退化为仅 step_0。")
        return steps, cross_modal_used
    get_details_logger().log_event(
        "graph_path",
        {
            "target_hops": target_hops,
            "require_visual": require_visual,
            "edges": [
                {
                    "head": edge.head,
                    "relation": edge.relation,
                    "tail": edge.tail,
                    "evidence": edge.evidence,
                    "source_id": edge.source_id,
                    "source_type": edge.source_type,
                }
                for edge in path
            ],
        },
    )

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
            branch_label = _edge_source_label(branch_edge)
            branch_hint = (
                "\n[Branch/Contrast Knowledge]"
                f"[来源: {branch_label}]: "
                f"{branch_edge.head} --[{branch_edge.relation}]--> {branch_edge.tail}"
            )
        source_label = _edge_source_label(edge)
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
            knowledge_source_label=source_label,
            knowledge_source_prefix=source_prefix,
            visual_summary=visual_summary,
        )
        model = select_model_for_step(current_step_index)
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
                "- 必须隐藏推理逻辑与引导，不要在题干中出现“根据/因此/由此可知/请先/先…再…”等提示语。\n"
                "- 只给出中性条件与判据，不显式说明计算或分支步骤。"
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
            step, False, strong_correct, medium_correct, strong_text_only_correct
        )
        revise_reason = reason if needs_revision else None
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
                visual_summary,
            )
            step = run_step(revise_prompt, image_path, model, current_step_index)
            step = obfuscate_step_question(step)
            print(f"[Step {current_step_index}] 更新后题目:")
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

        print(f"[Step {current_step_index}] 完成 (Graph Mode, model={model})")
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
            review_raw, review_passed, review_reason = review_question(
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
                    # 逻辑修改：Strong 错 -> Hard; Strong 对 -> Simple
                    if not strong_correct:
                        target_path = Path(GENQA_HARD_PATH)
                        print(f"[Review] Step {current_step_index} 结果: correct -> {target_path} (Hard: Medium=X, Strong=X)")
                    else:
                        target_path = Path(GENQA_SIMPLE_PATH)
                        print(f"[Review] Step {current_step_index} 结果: correct -> {target_path} (Simple: Medium=X, Strong=O)")

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
                if review_reason:
                    print(f"[Review] 错误原因: {review_reason}")
            else:
                print(f"[Review] Step {current_step_index} 结果: unknown")

        steps.append(step)
        current_step_index += 1

    return steps, cross_modal_used
