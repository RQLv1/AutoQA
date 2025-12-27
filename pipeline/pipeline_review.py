from pathlib import Path

from prompts import build_review_prompt
from utils.api_client import call_vision_model
from utils.config import DEFAULT_TEMPERATURE, MODEL_REVIEW
from utils.parsing import extract_tag_optional, parse_review_decision


def review_question(
    question: str,
    answer: str,
    reasoning: str | None,
    image_path: Path,
    mode: str = "multi_select",
) -> tuple[str, bool | None, str | None]:
    """
    Review a question and return (raw_output, decision, reason).
    - raw_output: 原始模型输出
    - decision: True (correct) / False (incorrect) / None (unknown)
    - reason: 如果 decision 为 False，返回错误原因；否则为 None
    """
    prompt = build_review_prompt(question, answer, reasoning or "", mode)
    raw = call_vision_model(
        prompt,
        image_path,
        MODEL_REVIEW,
        temperature=DEFAULT_TEMPERATURE,
    )
    decision = parse_review_decision(raw)

    # 提取错误原因（仅在 incorrect 时存在）
    reason = None
    if decision is False:
        reason = extract_tag_optional(raw, "reason")

    return raw, decision, reason
