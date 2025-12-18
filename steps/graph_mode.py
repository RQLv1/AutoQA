from pathlib import Path

from graph.pipeline_graph import build_entity_pool, build_knowledge_edges_cached, edge_to_evidence_payload
from graph.pipeline_path_sampling import sample_path
from prompts import build_graph_1hop_step_prompt, build_revise_prompt, build_stage1_step_prompt
from pipeline.pipeline_solvers import grade_answer, solve_mcq
from steps.runner import run_step, select_model_for_step
from steps.validation import validate_step
from utils.config import MAX_STEPS_PER_ROUND, MIN_HOPS, MODEL_SOLVE_MEDIUM, MODEL_SOLVE_STRONG
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
    if not edges or target_hops <= 0:
        print("[Graph Mode] 知识点链为空或 hop=0，退化为仅 step_0。")
        return steps, cross_modal_used

    entity_pool = build_entity_pool(edges)
    path = sample_path(edges, target_hops)
    if not path:
        print("[Graph Mode] 知识链路径采样失败，退化为仅 step_0。")
        return steps, cross_modal_used

    for k, edge in enumerate(reversed(path), start=1):
        distractors = [e for e in entity_pool if e != edge.head]
        prompt = build_graph_1hop_step_prompt(
            anchor_question=step0.question,
            evidence_snippet=edge.evidence or "",
            head=edge.head,
            relation=edge.relation,
            tail=edge.tail,
            distractor_entities=distractors,
            feedback=feedback,
            force_cross_modal=False,
        )
        model = select_model_for_step(k)
        step = run_step(prompt, image_path, model, k)
        if step.evidence is None:
            step.evidence = edge_to_evidence_payload(edge)

        medium_raw, medium_letter = solve_mcq(context, step.question, image_path, MODEL_SOLVE_MEDIUM)
        strong_raw, strong_letter = solve_mcq(context, step.question, image_path, MODEL_SOLVE_STRONG)
        medium_correct = grade_answer(step.answer_letter or "", medium_letter)
        strong_correct = grade_answer(step.answer_letter or "", strong_letter)
        needs_revision, reason = validate_step(step, False, strong_correct)
        if needs_revision:
            print(f"[Step {k}] 触发 revise: {reason}")
            revise_prompt = build_revise_prompt(
                context,
                step,
                reason,
                f"knowledge_link=({edge.head},{edge.relation},{edge.tail})",
                False,
            )
            step = run_step(revise_prompt, image_path, model, k)
            medium_raw, medium_letter = solve_mcq(context, step.question, image_path, MODEL_SOLVE_MEDIUM)
            strong_raw, strong_letter = solve_mcq(context, step.question, image_path, MODEL_SOLVE_STRONG)
            medium_correct = grade_answer(step.answer_letter or "", medium_letter)
            strong_correct = grade_answer(step.answer_letter or "", strong_letter)

        print(f"[Step {k}] 完成 (Graph Mode, model={model})")
        print(step.question)
        print(f"标准答案: <answer>{step.answer_letter}</answer> | answer_text={step.answer_text}")
        print(f"中求解器: {medium_raw} | correct={medium_correct}")
        print(f"强求解器: {strong_raw} | correct={strong_correct}")

        steps.append(step)

    return steps, cross_modal_used
