from pathlib import Path

from prompts import build_operate_calculation_prompt
from utils.api_client import call_vision_model
from utils.config import MODEL_OPERATE_CALCULATION
from utils.parsing import extract_tag_optional
from utils.schema import OperateResult, StepResult


def run_operate_calculation_agent(
    *,
    context: str,
    image_path: Path,
    previous_step: StepResult,
    fact_hint: str,
    feedback: str,
    force_cross_modal: bool,
    forbidden_terms: list[str] | None = None,
) -> OperateResult:
    prompt = build_operate_calculation_prompt(
        context=context,
        previous_step=previous_step,
        fact_hint=fact_hint,
        feedback=feedback,
        force_cross_modal=force_cross_modal,
        forbidden_terms=forbidden_terms,
    )
    raw = call_vision_model(prompt, image_path, MODEL_OPERATE_CALCULATION, max_tokens=1200, temperature=0)
    draft = (extract_tag_optional(raw, "draft") or raw.strip()).strip()
    return OperateResult(operator_type="calculation", draft=draft, raw=raw)

