from utils.schema import StepResult, StageResult


def _shorten_text(text: str | None, limit: int = 120) -> str:
    if not text:
        return ""
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)] + "..."


def _fmt_bool(value: bool | None) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "n/a"


def print_step_input(
    *,
    step_index: int,
    model: str,
    mode: str,
    fact_hint: str | None,
    force_cross_modal: bool,
    has_operate_calc: bool,
    has_operate_dist: bool,
) -> None:
    print(f"[Step {step_index}] Input ({mode}, model={model})")
    if fact_hint:
        print(f"  fact_hint: {_shorten_text(fact_hint)}")
    print(
        "  cross_modal="
        f"{'required' if force_cross_modal else 'optional'}"
        f" | operate_calc={_fmt_bool(has_operate_calc)}"
        f" | operate_dist={_fmt_bool(has_operate_dist)}"
    )


def print_step_summary(
    *,
    step: StepResult,
    medium_correct: bool | None,
    strong_correct: bool | None,
    text_only_correct: bool | None,
    revise_reason: str | None,
) -> None:
    validation = "ok" if not revise_reason else f"revised ({revise_reason})"
    print(f"[Step {step.k}] Summary")
    print(
        "  answer="
        f"{step.answer_letter or '?'}"
        f" | modal_use={step.modal_use}"
        f" | cross_modal={_fmt_bool(step.cross_modal_bridge)}"
    )
    print(
        "  solvers="
        f"medium:{_fmt_bool(medium_correct)}"
        f" strong:{_fmt_bool(strong_correct)}"
        f" text_only:{_fmt_bool(text_only_correct)}"
        f" | validation={validation}"
    )


def print_final_input(
    *,
    steps_count: int,
    cross_modal_used: bool,
    refine_attempts: int,
    max_refine_attempts: int,
) -> None:
    print(
        "[Final] Input"
        f" | steps={steps_count}"
        f" | cross_modal={_fmt_bool(cross_modal_used)}"
        f" | refine_attempts={refine_attempts}/{max_refine_attempts}"
    )


def print_final_summary(
    *,
    final: StageResult,
    metrics: dict[str, object],
    review_passed: bool | None,
    refine_attempts: int,
    max_refine_attempts: int,
) -> None:
    print("[Final] Summary")
    print(
        "  medium="
        f"{_fmt_bool(metrics.get('medium_correct'))}"
        f" | strong={_fmt_bool(metrics.get('strong_correct'))}"
        f" | text_only={_fmt_bool(metrics.get('text_only_veto'))}"
        f" | review={_fmt_bool(review_passed)}"
    )
    print(
        "  score="
        f"{metrics.get('difficulty_score', 'n/a')}"
        f" | refine_attempts={refine_attempts}/{max_refine_attempts}"
    )
