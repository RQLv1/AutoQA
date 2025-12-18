import re


def extract_tag(content: str, tag: str) -> str:
    start_tag = f"<{tag}>"
    end_tag = f"</{tag}>"
    start = content.find(start_tag)
    end = content.find(end_tag)
    if start == -1 or end == -1:
        raise ValueError(f"响应中缺少 {start_tag} 或 {end_tag} 标签: {content}")
    return content[start + len(start_tag) : end].strip()


def parse_option_letter(text: str) -> str:
    match = re.search(r"[A-D]", text)
    if not match:
        raise ValueError(f"未能解析选项字母: {text}")
    return match.group(0)
