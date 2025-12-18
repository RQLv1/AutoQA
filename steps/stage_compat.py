from utils.schema import StageResult, StepResult


def derive_stage_results(steps: list[StepResult]) -> tuple[StageResult, StageResult, StageResult]:
    if not steps:
        empty = StageResult(question="", answer="", raw="")
        return empty, empty, empty

    def stage_answer(step: StepResult) -> str:
        return f"{step.answer_letter}；{step.answer_text}" if step.answer_letter else step.answer_text

    stage_1 = StageResult(question=steps[0].question, answer=stage_answer(steps[0]), raw=steps[0].raw)
    stage_2_source = steps[1] if len(steps) > 1 else steps[0]
    stage_3_source = steps[2] if len(steps) > 2 else stage_2_source
    stage_2 = StageResult(
        question=stage_2_source.question, answer=stage_answer(stage_2_source), raw=stage_2_source.raw
    )
    stage_3 = StageResult(
        question=stage_3_source.question, answer=stage_answer(stage_3_source), raw=stage_3_source.raw
    )
    return stage_1, stage_2, stage_3


def step_to_dict(step: StepResult) -> dict[str, object]:
    return {
        "k": step.k,
        "question": step.question,
        "answer_text": step.answer_text,
        "answer_letter": step.answer_letter,
        "evidence": step.evidence,
        "modal_use": step.modal_use,
        "cross_modal_bridge": step.cross_modal_bridge,
        "raw": step.raw,
        "judge_flags": step.judge_flags,
    }
