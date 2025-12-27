import re

from utils.parsing import parse_option_letter_optional


_OPTION_MARKER = re.compile(r"(?i)(?P<letter>[A-H])\s*[\.．、】【\)]\s*")
_UNIT_RE = re.compile(
    r"(?i)\b(%|℃|°c|kpa|mpa|pa|kv|v|ma|a|mw|kw|w|nm|um|mm|cm|m|kg|g|mg|s|min|h)\b"
)
_NUMBER_RE = re.compile(r"(?i)(?P<num>[\+\-]?\d+(?:\.\d+)?)")


def _extract_options(question: str) -> dict[str, str]:
    matches = list(_OPTION_MARKER.finditer(question))
    if not matches:
        return {}

    options: dict[str, str] = {}
    for idx, match in enumerate(matches):
        letter = match.group("letter").upper()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(question)
        chunk = question[start:end].strip()
        if letter not in options:
            options[letter] = chunk
    return options


def _extract_unit(option_text: str) -> str | None:
    if not option_text:
        return None
    matches = _UNIT_RE.findall(option_text)
    if not matches:
        return None
    return matches[-1].lower()


def _extract_decimal_places(option_text: str) -> int | None:
    if not option_text:
        return None
    match = _NUMBER_RE.search(option_text)
    if not match:
        return None
    num = match.group("num")
    if "." not in num:
        return 0
    return len(num.split(".", 1)[1])


def judge_mcq(question: str, answer: str) -> dict[str, bool]:
    options = _extract_options(question)
    correct = parse_option_letter_optional(answer) or ""
    correct_letters = set(correct)

    flags: dict[str, bool] = {}
    flags["missing_options"] = len(options) < 4
    flags["correct_option_longest"] = False
    flags["option_length_bias"] = False
    flags["option_length_variance_20pct"] = False
    flags["unit_inconsistent"] = False
    flags["decimal_places_inconsistent"] = False

    if options:
        lengths = {k: len(v) for k, v in options.items() if v}
        if lengths:
            max_len = max(lengths.values())
            min_len = min(lengths.values())
            flags["option_length_bias"] = (min_len > 0) and (max_len / min_len >= 2.5)
            flags["option_length_variance_20pct"] = (min_len > 0) and (max_len / min_len >= 1.2)
            if len(correct_letters) == 1 and max_len > 0:
                letter = next(iter(correct_letters))
                if letter in lengths:
                    flags["correct_option_longest"] = lengths[letter] == max_len

        units = {k: _extract_unit(v) for k, v in options.items()}
        present_units = [u for u in units.values() if u]
        flags["unit_inconsistent"] = len(set(present_units)) >= 2 if present_units else False

        decimals = {k: _extract_decimal_places(v) for k, v in options.items()}
        present_decimals = [d for d in decimals.values() if d is not None]
        flags["decimal_places_inconsistent"] = (
            len(set(present_decimals)) >= 2 if len(present_decimals) >= 3 else False
        )

    return flags
