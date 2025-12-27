import re

_OPTION_RE = re.compile(r"(^|\n)\s*([A-H])[\.、:：\)]\s*\S+", re.MULTILINE)


def _longest_consecutive_run(letters: list[str]) -> int:
    longest = 0
    for idx, letter in enumerate(letters):
        current_len = 1
        current_code = ord(letter)
        for next_letter in letters[idx + 1 :]:
            next_code = ord(next_letter)
            if next_code == current_code + 1:
                current_len += 1
                current_code = next_code
            else:
                break
        longest = max(longest, current_len)
    return longest


def has_valid_options(question: str) -> bool:
    ordered_letters: list[str] = []
    for match in _OPTION_RE.finditer(question or ""):
        letter = match.group(2).upper()
        if not ordered_letters or ordered_letters[-1] != letter:
            ordered_letters.append(letter)
    if len(ordered_letters) < 4:
        return False
    return _longest_consecutive_run(ordered_letters) >= 4
