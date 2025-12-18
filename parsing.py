import json
import re
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


def parse_option_letter(text: str) -> str:
    match = re.search(r"[A-D]", text)
    if not match:
        raise ValueError(f"未能解析选项字母: {text}")
    return match.group(0)


def parse_option_letter_optional(text: str) -> str | None:
    match = re.search(r"[A-D]", text)
    if not match:
        return None
    return match.group(0)


def parse_bool(text: str | None) -> bool:
    if text is None:
        return False
    return text.strip().lower() in {"1", "true", "yes", "y", "是"}


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
