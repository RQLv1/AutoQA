import json
import re
import unicodedata
from typing import Any


def extract_tag(content: str, tag: str) -> str:
    start_tag = f"<{tag}>"
    end_tag = f"</{tag}>"
    start = content.find(start_tag)
    end = content.find(end_tag)
    if start == -1 or end == -1:
        raise ValueError(f"响应中缺少 {start_tag} 或 {end_tag} 标签: {content}")
    return content[start + len(start_tag) : end].strip()


def extract_tag_optional(content: str, tag: str) -> str | None:
    start_tag = f"<{tag}>"
    end_tag = f"</{tag}>"
    start = content.find(start_tag)
    end = content.find(end_tag)
    if start == -1 or end == -1:
        return None
    return content[start + len(start_tag) : end].strip()


def extract_question_and_selections(content: str) -> tuple[str, str | None]:
    """
    从模型输出中提取题干和选项。
    返回 (question_text, selections_text)
    如果没有 <selections> 标签，尝试从 <question> 中分离。
    """
    question = extract_tag_optional(content, "question")
    selections = extract_tag_optional(content, "selections")

    if question is None:
        # 兼容旧格式：没有 <question> 标签，直接使用原文
        question = content.strip()

    if selections is None and question:
        # 尝试从 question 中分离选项
        selections = _try_extract_selections_from_text(question)
        if selections:
            # 从 question 中移除选项部分
            question = _remove_selections_from_text(question, selections)

    return question, selections


def _try_extract_selections_from_text(text: str) -> str | None:
    """尝试从文本中提取选项块"""
    import re
    # 匹配类似 A. xxx B. xxx C. xxx D. xxx 的模式
    pattern = re.compile(r'(?:^|\n)\s*[A-D][\s\.、:：)）]', re.MULTILINE)
    matches = list(pattern.finditer(text))
    if len(matches) >= 2:
        # 找到至少2个选项，提取选项块
        first_match = matches[0]
        return text[first_match.start():].strip()
    return None


def _remove_selections_from_text(text: str, selections: str) -> str:
    """从文本中移除选项部分"""
    if selections in text:
        text = text.replace(selections, '').strip()
    else:
        # 尝试找到选项开始的位置
        import re
        pattern = re.compile(r'(?:^|\n)\s*[A-D][\s\.、:：)）]', re.MULTILINE)
        match = pattern.search(text)
        if match:
            text = text[:match.start()].strip()
    return text


def extract_labeled_value(content: str, label: str) -> str | None:
    if not content:
        return None
    pattern = rf"(?im)^{re.escape(label)}\s*[:=]\s*(.+)$"
    match = re.search(pattern, content)
    if not match:
        return None
    return match.group(1).strip()


def extract_option_text(question: str, letter: str) -> str | None:
    if not question or not letter:
        return None
    pattern = re.compile(r"(?s)(^|\s)([A-D])\s*[\\.、:：)]\s*")
    matches = list(pattern.finditer(question))
    if not matches:
        pattern = re.compile(r"(?m)^\\s*([A-D])\\s+")
        matches = list(pattern.finditer(question))
    if not matches:
        return None
    for idx, match in enumerate(matches):
        opt = match.group(2) if match.lastindex and match.lastindex >= 2 else match.group(1)
        if opt != letter:
            continue
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(question)
        return question[start:end].strip()
    return None


def _normalize_option_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def _find_option_letter(text: str) -> str | None:
    if not text:
        return None
    normalized = _normalize_option_text(text)
    match = re.search(r"[A-D]", normalized, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(0).upper()


def parse_option_letter(text: str) -> str:
    letter = _find_option_letter(text)
    if not letter:
        raise ValueError(f"未能解析选项字母: {text}")
    return letter


def parse_option_letter_optional(text: str) -> str | None:
    if not text:
        return None
    tagged = extract_tag_optional(text, "answer")
    if tagged:
        letter = _find_option_letter(tagged)
        if letter:
            return letter
    normalized = _normalize_option_text(text)
    head_match = re.match(r"\s*([A-D])\b", normalized, flags=re.IGNORECASE)
    if head_match:
        return head_match.group(1).upper()
    patterns = [
        r"(?:正确答案|答案)\s*[为是:：]\s*([A-D])",
        r"(?:Correct|Answer)\s*(?:is|:)\s*([A-D])",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, normalized, flags=re.IGNORECASE)
        if matches:
            return matches[-1].upper()
    letters = re.findall(r"[A-D]", normalized, flags=re.IGNORECASE)
    if letters:
        return letters[-1].upper()
    return None


def parse_tagged_option_letter(text: str, tag: str = "answer") -> str | None:
    if not text:
        return None
    tagged = extract_tag_optional(text, tag)
    if tagged:
        letter = _find_option_letter(tagged)
        if letter:
            return letter

    start_tag = f"<{tag}>"
    start = text.find(start_tag)
    if start == -1:
        return parse_option_letter_optional(text)
    after = text[start + len(start_tag) :]
    letter = _find_option_letter(after)
    if letter:
        return letter
    return parse_option_letter_optional(text)


def parse_bool(text: str | None) -> bool:
    if text is None:
        return False
    return text.strip().lower() in {"1", "true", "yes", "y", "是"}


def parse_review_decision(text: str | None) -> bool | None:
    if text is None:
        return None
    tagged = extract_tag_optional(text, "answer")
    if tagged is None:
        tagged = extract_tag_optional(text, "review")
    content = tagged if tagged is not None else text
    normalized = content.strip().lower()
    if normalized in {"correct", "true", "yes", "y", "是", "正确"}:
        return True
    if normalized in {"incorrect", "false", "no", "n", "否", "错误"}:
        return False
    if "incorrect" in normalized or "错误" in normalized:
        return False
    if "correct" in normalized or "正确" in normalized:
        return True
    return None


def parse_evidence(raw: str | None) -> Any:
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    if cleaned.startswith("{") or cleaned.startswith("["):
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return raw
    return raw
