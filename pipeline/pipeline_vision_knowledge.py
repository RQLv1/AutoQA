from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from graph.pipeline_graph import KnowledgeEdge, extract_edges_from_context
from utils.api_client import call_vision_model
from utils.config import DEFAULT_TEMPERATURE, MODEL_VISION_KNOWLEDGE
from utils.details_logger import get_details_logger
from utils.parsing import extract_tag_optional


@dataclass(frozen=True)
class VisionKnowledge:
    description: str
    summary: str
    edges: list[KnowledgeEdge]
    raw: str


_VISION_CACHE: dict[str, VisionKnowledge] = {}


def _hash_image(image_path: Path) -> str:
    payload = image_path.read_bytes()
    return hashlib.sha1(payload).hexdigest()


def _build_visual_description_prompt() -> str:
    return (
        "Provide a deep visual analysis of the input image with objective, fine-grained facts\n"
        "that can be used for knowledge extraction.\n"
        "Requirements:\n"
        "- Cover objects/entities, spatial relations, text/numeric readings, chart trends, and color/state changes.\n"
        "- Use short bullet-like sentences; avoid subjective guesses or background assumptions.\n"
        "- You may state explicit spatial relations (e.g., A is to the right of B / above / inside).\n"
        "- Include visible labels/axes/symbols/units, but do not invent any missing elements.\n"
        "- The description must support extracting entity-relation-entity chains.\n"
        "\n"
        "Only output in the following format:\n"
        "<description>\n"
        "List detailed visual statements\n"
        "</description>\n"
        "<summary>\n"
        "Provide a concise summary within 12 lines\n"
        "</summary>\n"
    )


def _summarize_description(text: str, max_lines: int = 12, max_chars: int = 800) -> str:
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    summary = "\n".join(lines[:max_lines])
    if len(summary) > max_chars:
        summary = summary[:max_chars].rstrip()
    return summary


def build_visual_knowledge(image_path: Path) -> VisionKnowledge:
    cache_key = _hash_image(image_path)
    cached = _VISION_CACHE.get(cache_key)
    if cached:
        return cached

    prompt = _build_visual_description_prompt()
    raw = call_vision_model(
        prompt,
        image_path,
        MODEL_VISION_KNOWLEDGE,
        temperature=DEFAULT_TEMPERATURE,
    )
    description = extract_tag_optional(raw, "description") or raw.strip()
    summary = extract_tag_optional(raw, "summary") or _summarize_description(description)
    edges = extract_edges_from_context(description, source_type="image")
    get_details_logger().log_event(
        "visual_knowledge",
        {
            "image_path": str(image_path),
            "description": description.strip(),
            "summary": summary.strip(),
            "edges": [
                {
                    "head": edge.head,
                    "relation": edge.relation,
                    "tail": edge.tail,
                    "evidence": edge.evidence,
                    "source_id": edge.source_id,
                    "source_type": edge.source_type,
                }
                for edge in edges
            ],
        },
    )
    result = VisionKnowledge(
        description=description.strip(),
        summary=summary.strip(),
        edges=edges,
        raw=raw,
    )
    _VISION_CACHE[cache_key] = result
    return result
