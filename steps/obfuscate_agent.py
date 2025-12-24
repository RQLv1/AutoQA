import re

from prompts import build_obfuscate_prompt
from utils.api_client import call_text_model
from utils.config import DEFAULT_TEMPERATURE, MODEL_OBFUSCATE
from utils.parsing import extract_option_text, extract_tag_optional
from utils.schema import StepResult


_OPTION_START_RE = re.compile(r"([A-D])[\\.、:：)]\\s*")
_VISUAL_ANCHORS = ("图中", "图示", "图像", "图片")


def _split_question(question: str) -> tuple[str, str]:
    matches = list(_OPTION_START_RE.finditer(question))
    if not matches:
        return question.strip(), ""
    first = matches[0].start()
    stem = question[:first].strip()
    options = question[first:].strip()
    return stem, options


def _ensure_visual_anchor(text: str) -> str:
    if any(anchor in text for anchor in _VISUAL_ANCHORS):
        return text
    return f"图中{text}"


def obfuscate_question(question: str, *, model: str = MODEL_OBFUSCATE) -> str:
    if not question or not question.strip():
        return question
    stem, options = _split_question(question)
    if not stem:
        return question
    prompt = build_obfuscate_prompt(stem)
    raw = call_text_model(prompt, model, temperature=DEFAULT_TEMPERATURE)
    rewritten = extract_tag_optional(raw, "stem") or raw.strip()
    rewritten = rewritten.strip()
    if not rewritten:
        return question
    rewritten = _ensure_visual_anchor(rewritten)
    if options:
        return f"{rewritten}\n{options}"
    return rewritten


def obfuscate_step_question(step: StepResult, *, model: str = MODEL_OBFUSCATE) -> StepResult:
    obfuscated = obfuscate_question(step.question, model=model)
    step.question = obfuscated
    if step.answer_letter and not step.answer_text:
        inferred = extract_option_text(step.question, step.answer_letter)
        if inferred:
            step.answer_text = inferred
    return step
