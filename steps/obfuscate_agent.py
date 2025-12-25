import re

from prompts import build_obfuscate_prompt
from utils.api_client import call_text_model
from utils.config import DEFAULT_TEMPERATURE, MODEL_OBFUSCATE
from utils.parsing import extract_option_text, extract_tag_optional
from utils.schema import StepResult


_OPTION_PUNCT = r"[\\.．、:：)）]"
_OPTION_INLINE_RE = re.compile(rf"([A-DＡ-Ｄ]){_OPTION_PUNCT}\\s*")
_OPTION_LINE_RE = re.compile(
    rf"(?m)^\\s*[\\(（【]?[A-DＡ-Ｄ][\\)）】]?\\s*(?:{_OPTION_PUNCT}\\s*)?[^\\n]+"
)
_OPTION_HINT_RE = re.compile(
    rf"(?:[A-DＡ-Ｄ]\\s*{_OPTION_PUNCT}|\\([A-DＡ-Ｄ]\\)|（[A-DＡ-Ｄ]）|^\\s*[A-DＡ-Ｄ]\\s+[^\\n]+)",
    flags=re.MULTILINE,
)
_VISUAL_ANCHORS = ("图中", "图示", "图像", "图片")


def _normalize_letter(letter: str) -> str:
    return (
        letter.strip()
        .upper()
        .replace("Ａ", "A")
        .replace("Ｂ", "B")
        .replace("Ｃ", "C")
        .replace("Ｄ", "D")
    )


def _extract_leading_letter(text: str) -> str | None:
    match = re.match(r"^\\s*[\\(（【]?(?P<letter>[A-DＡ-Ｄ])", text)
    if not match:
        return None
    return _normalize_letter(match.group("letter"))


def _distinct_option_letters(matches: list[re.Match[str]]) -> int:
    letters = set()
    for match in matches:
        if match.lastindex:
            letter = match.group(1)
            if not letter:
                continue
            letters.add(_normalize_letter(letter))
            continue
        letter = _extract_leading_letter(match.group(0))
        if not letter:
            continue
        letters.add(letter)
    return len(letters)


def _extract_option_block(text: str) -> str:
    lines = text.splitlines()
    option_lines: list[str] = []
    letters = set()
    for line in lines:
        if not _OPTION_LINE_RE.match(line):
            if option_lines:
                break
            continue
        leading = _extract_leading_letter(line)
        if leading:
            letters.add(leading)
        option_lines.append(line.strip())
    if len(option_lines) >= 2 and len(letters) >= 2:
        return "\n".join(option_lines)
    return ""


def _split_question(question: str) -> tuple[str, str, bool]:
    for pattern in (_OPTION_LINE_RE, _OPTION_INLINE_RE):
        matches = list(pattern.finditer(question))
        if len(matches) >= 2 and _distinct_option_letters(matches) >= 2:
            first = matches[0].start()
            stem = question[:first].strip()
            options = question[first:].strip()
            return stem, options, True
    return question.strip(), "", False


def _ensure_visual_anchor(text: str) -> str:
    if any(anchor in text for anchor in _VISUAL_ANCHORS):
        return text
    return f"图中{text}"


def obfuscate_question(
    question: str, *, raw: str | None = None, model: str = MODEL_OBFUSCATE
) -> str:
    if not question or not question.strip():
        return question
    stem, options, has_options = _split_question(question)
    if not has_options and raw:
        recovered = _extract_option_block(raw)
        if recovered:
            options = recovered
            has_options = True
    if not stem:
        return question
    if not has_options and _OPTION_HINT_RE.search(question):
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
    obfuscated = obfuscate_question(step.question, raw=step.raw, model=model)
    step.question = obfuscated
    if step.answer_letter and not step.answer_text:
        inferred = extract_option_text(step.question, step.answer_letter)
        if inferred:
            step.answer_text = inferred
    return step
