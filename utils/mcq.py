import re

_OPTION_RE = re.compile(r"(^|\\n)\\s*([A-D])[\\.|\\)|、|:：]\\s*\\S+", re.MULTILINE)


def has_abcd_options(question: str) -> bool:
    letters = {match.group(2) for match in _OPTION_RE.finditer(question or "")}
    return {"A", "B", "C", "D"}.issubset(letters)

