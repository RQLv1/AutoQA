from pathlib import Path

from graph.pipeline_graph import build_entity_pool, build_triplets_cached, triplet_to_evidence_payload
from graph.pipeline_path_sampling import sample_path
from prompts import build_graph_1hop_step_prompt, build_revise_prompt, build_stage1_step_prompt
from pipeline.pipeline_solvers import grade_answer, solve_mcq
from steps.runner import run_step, select_model_for_step
from steps.validation import validate_step
from utils.config import DOC_CHUNK_WORDS, MAX_STEPS_PER_ROUND, MIN_HOPS, MODEL_SOLVE_STRONG
from utils.schema import StepResult


def generate_steps_graph_mode(
    context: str,
    image_path: Path,
    feedback: str,
    previous_final_question: str | None,
) -> tuple[list[StepResult], bool]:
    steps: list[StepResult] = []

    step0 = run_step(
        build_stage1_step_prompt(context, feedback, previous_final_question),
        image_path,
        select_model_for_step(0),
        0,
    )
    steps.append(step0)
    cross_modal_used = True

    target_hops = min(MAX_STEPS_PER_ROUND - 1, max(MIN_HOPS, 2))
    chunks, triplets = build_triplets_cached(context, DOC_CHUNK_WORDS, max_chunks=20)
    if not triplets or target_hops <= 0:
        return steps, cross_modal_used

    entity_pool = build_entity_pool(triplets)
    path = sample_path(triplets, target_hops)
    if not path:
        return steps, cross_modal_used

    for k, edge in enumerate(reversed(path), start=1):
        chunk_text = next((c.text for c in chunks if c.chunk_id == edge.chunk_id), "")
        distractors = [e for e in entity_pool if e != edge.head]
        prompt = build_graph_1hop_step_prompt(
            anchor_question=step0.question,
            chunk_id=edge.chunk_id,
            chunk_text=chunk_text,
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
            step.evidence = triplet_to_evidence_payload(edge, chunks)

        _, strong_letter = solve_mcq(context, step.question, image_path, MODEL_SOLVE_STRONG)
        strong_correct = grade_answer(step.answer_letter or "", strong_letter)
        needs_revision, reason = validate_step(step, False, strong_correct)
        if needs_revision:
            revise_prompt = build_revise_prompt(
                context,
                step,
                reason,
                f"chunk:{edge.chunk_id} triple=({edge.head},{edge.relation},{edge.tail})",
                False,
            )
            step = run_step(revise_prompt, image_path, model, k)

        steps.append(step)

    return steps, cross_modal_used
