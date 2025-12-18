from pathlib import Path

from prompts import (
    build_extend_step_prompt,
    build_revise_prompt,
    build_stage1_step_prompt,
    build_stage2_step_prompt,
    build_stage3_step_prompt,
)
from pipeline.pipeline_facts import format_fact_hint, load_fact_candidates
from pipeline.pipeline_solvers import grade_answer, solve_mcq
from steps.runner import run_step, select_model_for_step
from steps.validation import validate_step
from utils.config import MAX_STEPS_PER_ROUND, MIN_HOPS, MODEL_SOLVE_STRONG, REQUIRE_CROSS_MODAL
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

        if k == 0:
            prompt = build_stage1_step_prompt(context, feedback, previous_final_question)
        elif k == 1:
            prompt = build_stage2_step_prompt(
                context, steps[-1], fact_hint, feedback, force_cross_modal
            )
        elif k == 2:
            prompt = build_stage3_step_prompt(
                context, steps[-1], fact_hint, feedback, force_cross_modal
            )
        else:
            prompt = build_extend_step_prompt(
                context, steps[-1], fact_hint, feedback, force_cross_modal
            )

        step = run_step(prompt, image_path, model, k)
        _, strong_letter = solve_mcq(context, step.question, image_path, MODEL_SOLVE_STRONG)
        strong_correct = grade_answer(step.answer_letter or "", strong_letter)
        needs_revision, reason = validate_step(step, force_cross_modal, strong_correct)

        if needs_revision:
            revise_prompt = build_revise_prompt(
                context, step, reason, fact_hint, force_cross_modal
            )
            step = run_step(revise_prompt, image_path, model, k)

        steps.append(step)
        cross_modal_used = cross_modal_used or step.cross_modal_bridge

        if k + 1 >= min_steps and (not REQUIRE_CROSS_MODAL or cross_modal_used):
            break

    return steps, cross_modal_used
