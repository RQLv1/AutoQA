from pathlib import Path

from api_client import call_vision_model
from config import (
    MAX_STEPS_PER_ROUND,
    MIN_HOPS,
    MODEL_SOLVE_STRONG,
    MODEL_STAGE_1,
    MODEL_STAGE_2,
    MODEL_STAGE_3,
    REQUIRE_CROSS_MODAL,
)
from parsing import extract_tag_optional, parse_bool, parse_evidence
from pipeline_facts import format_fact_hint, load_fact_candidates
from pipeline_solvers import grade_answer, solve_mcq
from prompts import (
    build_extend_step_prompt,
    build_revise_prompt,
    build_stage1_step_prompt,
    build_stage2_step_prompt,
    build_stage3_step_prompt,
)
from schema import StageResult, StepResult


def select_model_for_step(k: int) -> str:
    if k == 0:
        return MODEL_STAGE_1
    if k % 2 == 1:
        return MODEL_STAGE_2
    return MODEL_STAGE_3


def run_step(prompt: str, image_path: Path, model: str, k: int) -> StepResult:
    raw = call_vision_model(prompt, image_path, model)
    question = extract_tag_optional(raw, "question") or raw.strip()
    answer = extract_tag_optional(raw, "answer") or ""
    evidence = parse_evidence(extract_tag_optional(raw, "evidence"))
    modal_use = extract_tag_optional(raw, "modal_use") or "both"
    cross_modal_bridge = parse_bool(extract_tag_optional(raw, "cross_modal_bridge"))
    return StepResult(
        k=k,
        question=question,
        answer=answer,
        evidence=evidence,
        modal_use=modal_use,
        cross_modal_bridge=cross_modal_bridge,
        raw=raw,
    )


def validate_step(
    step: StepResult, force_cross_modal: bool, strong_correct: bool
) -> tuple[bool, str]:
    if not step.question or not step.answer:
        return True, "missing question or answer"
    if step.evidence is None:
        return True, "missing evidence"
    if step.modal_use not in {"image", "text", "both"}:
        return True, "invalid modal_use"
    if force_cross_modal and not step.cross_modal_bridge:
        return True, "cross-modal required"
    if not strong_correct:
        return True, "strong solver failed"
    return False, ""


def derive_stage_results(steps: list[StepResult]) -> tuple[StageResult, StageResult, StageResult]:
    if not steps:
        empty = StageResult(question="", answer="", raw="")
        return empty, empty, empty
    stage_1 = StageResult(question=steps[0].question, answer=steps[0].answer, raw=steps[0].raw)
    stage_2_source = steps[1] if len(steps) > 1 else steps[0]
    stage_3_source = steps[2] if len(steps) > 2 else stage_2_source
    stage_2 = StageResult(
        question=stage_2_source.question, answer=stage_2_source.answer, raw=stage_2_source.raw
    )
    stage_3 = StageResult(
        question=stage_3_source.question, answer=stage_3_source.answer, raw=stage_3_source.raw
    )
    return stage_1, stage_2, stage_3


def step_to_dict(step: StepResult) -> dict[str, object]:
    return {
        "k": step.k,
        "question": step.question,
        "answer": step.answer,
        "evidence": step.evidence,
        "modal_use": step.modal_use,
        "cross_modal_bridge": step.cross_modal_bridge,
        "raw": step.raw,
        "judge_flags": step.judge_flags,
    }


def generate_steps(
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
        strong_raw, strong_letter = solve_mcq(context, step.question, image_path, MODEL_SOLVE_STRONG)
        strong_correct = grade_answer(step.answer, strong_letter)
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
