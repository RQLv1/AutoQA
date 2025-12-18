import json

from prompts import build_fact_extraction_prompt
from utils.api_client import call_text_model
from utils.config import MODEL_STAGE_2


def number_context_lines(context: str) -> str:
    lines = [line.strip() for line in context.splitlines() if line.strip()]
    return "\n".join(f"L{idx + 1}: {line}" for idx, line in enumerate(lines))


def strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    return cleaned


def fallback_fact_candidates(context: str, max_facts: int) -> list[dict[str, str]]:
    lines = [line.strip() for line in context.splitlines() if line.strip()]
    facts = []
    for idx, line in enumerate(lines[:max_facts], start=1):
        facts.append({"fact": line, "source": f"L{idx}"})
    return facts


def load_fact_candidates(context: str, max_facts: int) -> list[dict[str, str]]:
    if max_facts <= 0:
        return []
    prompt = build_fact_extraction_prompt(number_context_lines(context), max_facts)
    try:
        raw = call_text_model(prompt, MODEL_STAGE_2)
        cleaned = strip_code_fence(raw)
        data = json.loads(cleaned)
        if not isinstance(data, list):
            raise ValueError("fact extraction returned non-list")
        results: list[dict[str, str]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            fact = str(item.get("fact", "")).strip()
            source = str(item.get("source", "")).strip()
            if fact:
                results.append({"fact": fact, "source": source or "L?"})
        return results if results else fallback_fact_candidates(context, max_facts)
    except Exception:
        return fallback_fact_candidates(context, max_facts)


def format_fact_hint(fact: dict[str, str] | None) -> str:
    if not fact:
        return "暂无可用事实(请从文档中自行抽取并标注行号)"
    return f"{fact.get('fact', '').strip()} (source: {fact.get('source', 'L?')})"
