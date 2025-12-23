from pathlib import Path

from prompts import build_review_prompt
from utils.api_client import call_vision_model
from utils.config import DEFAULT_TEMPERATURE, MODEL_REVIEW
from utils.parsing import parse_review_decision


def review_question(
    question: str,
    answer: str,
    reasoning: str | None,
    image_path: Path,
) -> tuple[str, bool | None]:
    prompt = build_review_prompt(question, answer, reasoning)
    raw = call_vision_model(
        prompt,
        image_path,
        MODEL_REVIEW,
        temperature=DEFAULT_TEMPERATURE,
    )
    decision = parse_review_decision(raw)
    return raw, decision
