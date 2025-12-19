import re

from utils.parsing import parse_option_letter_optional


_OPTION_MARKER = re.compile(r"(?i)(?P<letter>[A-D])\s*[\.．、】【\)]\s*")


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


def judge_mcq(question: str, answer: str) -> dict[str, bool]:
    options = _extract_options(question)
    correct = parse_option_letter_optional(answer) or ""

    flags: dict[str, bool] = {}
    flags["missing_options"] = len(options) < 4

    if options:
        lengths = {k: len(v) for k, v in options.items() if v}
        if lengths:
            max_len = max(lengths.values())
            min_len = min(lengths.values())
            flags["option_length_bias"] = (min_len > 0) and (max_len / min_len >= 2.5)
            if correct and correct in lengths:
                flags["correct_option_longest"] = lengths[correct] == max_len and max_len > 0
    else:
        flags["option_length_bias"] = False
        flags["correct_option_longest"] = False

    return flags
