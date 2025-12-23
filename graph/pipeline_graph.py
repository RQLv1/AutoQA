import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils.api_client import call_text_model
from utils.config import (
    DEFAULT_TEMPERATURE,
    MODEL_JUDGE,
)


@dataclass(frozen=True)
class KnowledgeEdge:
    head: str
    relation: str
    tail: str
    evidence: str | None = None
    source_id: int | None = None


_EDGE_CACHE: dict[str, list[KnowledgeEdge]] = {}
_DEBUG_GRAPH = os.getenv("GRAPH_DEBUG", "false").lower() in {"1", "true", "yes"}
_DISK_CACHE_VERSION = 3
_DISK_CACHE_PATH = Path(os.getenv("GRAPH_CACHE_PATH", "data/graph_cache.json"))
_DISK_CACHE: dict[str, dict[str, Any]] | None = None


def _debug_log(message: str) -> None:
    if _DEBUG_GRAPH:
        print(message)


def _load_disk_cache() -> dict[str, dict[str, Any]]:
    global _DISK_CACHE
    if _DISK_CACHE is not None:
        return _DISK_CACHE
    if not _DISK_CACHE_PATH.exists():
        _DISK_CACHE = {}
        return _DISK_CACHE
    try:
        payload = json.loads(_DISK_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _debug_log(f"[Graph Mode][Knowledge] disk cache read failed: {exc}")
        _DISK_CACHE = {}
        return _DISK_CACHE
    if isinstance(payload, dict) and isinstance(payload.get("items"), dict):
        _DISK_CACHE = payload["items"]
        return _DISK_CACHE
    if isinstance(payload, dict):
        _DISK_CACHE = payload
        return _DISK_CACHE
    _DISK_CACHE = {}
    return _DISK_CACHE


def _save_disk_cache(items: dict[str, dict[str, Any]]) -> None:
    try:
        _DISK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": _DISK_CACHE_VERSION, "items": items}
        _DISK_CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    except OSError as exc:
        _debug_log(f"[Graph Mode][Knowledge] disk cache write failed: {exc}")


def _serialize_edges(edges: list[KnowledgeEdge]) -> list[dict[str, Any]]:
    return [
        {
            "head": edge.head,
            "relation": edge.relation,
            "tail": edge.tail,
            "evidence": edge.evidence,
            "source_id": edge.source_id,
        }
        for edge in edges
    ]


def _deserialize_edges(data: list[dict[str, Any]]) -> list[KnowledgeEdge]:
    edges: list[KnowledgeEdge] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        head = str(item.get("head", "")).strip()
        relation = str(item.get("relation", "")).strip()
        tail = str(item.get("tail", "")).strip()
        evidence = item.get("evidence")
        if evidence is not None:
            evidence = str(evidence).strip() or None
        if not head or not relation or not tail:
            continue
        source_id = item.get("source_id")
        if source_id is not None:
            try:
                source_id = int(source_id)
            except (TypeError, ValueError):
                source_id = None
        edges.append(
            KnowledgeEdge(
                head=head,
                relation=relation,
                tail=tail,
                evidence=evidence,
                source_id=source_id,
            )
        )
    return edges


def _cache_key(context: str) -> str:
    payload = context.encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


def _chain_extraction_prompt(context: str) -> str:
    return (
        "请从下面全文中总结多条“串联的知识点链”，用于构建本地知识图谱。\n"
        "要求:\n"
        "- 每条知识链由 2-5 个知识点构成，按逻辑顺序排列。\n"
        "- 知识点应是短实体/短短语（<= 20 字），不要用代词。\n"
        "- 相邻知识点之间要有清晰的语义衔接（因果/组成/属性/用途/比较等）。\n"
        "- 可选给出 links 列表，长度应等于 chain 长度-1，用短谓词（<= 12 字）。\n"
        "- 每条都要能在全文中找到依据。\n"
        "- 若无可总结内容，返回空数组 []。\n"
        "- 只输出 JSON 数组，元素格式:\n"
        '  {"chain":["点1","点2","点3"],"links":["关系1","关系2"],"evidence":"原文片段(<=60字)"}\n'
        "- 输出必须是完整且可解析的 JSON，不能包含 Markdown 代码块或任何额外说明。\n"
        "- 不要输出前后缀文字，必须以 [ 开头、以 ] 结尾。\n"
        f"\n全文:\n{context.strip()}\n"
    )


def extract_edges_from_context(context: str) -> list[KnowledgeEdge]:
    prompt = _chain_extraction_prompt(context)
    raw = call_text_model(
        prompt,
        MODEL_JUDGE,
        temperature=DEFAULT_TEMPERATURE,
    )
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        _debug_log(
            f"[Graph Mode][Knowledge] JSON parse failed. raw_snippet={cleaned[:400]!r}"
        )
        return []

    edges: list[KnowledgeEdge] = []
    if not isinstance(data, list):
        _debug_log(f"[Graph Mode][Knowledge] expected list, got {type(data).__name__}.")
        return edges
    seen: set[tuple[str, str, str]] = set()
    edge_id = 0
    for item in data:
        if not isinstance(item, dict):
            continue
        chain = item.get("chain")
        if chain is None:
            chain = item.get("points") or item.get("knowledge_points")
        if not isinstance(chain, list):
            continue
        points = [str(p).strip() for p in chain if str(p).strip()]
        if len(points) < 2:
            continue
        links = item.get("links")
        link_list: list[str] = []
        if isinstance(links, list):
            link_list = [str(l).strip() for l in links]
        elif isinstance(links, str) and links.strip():
            link_list = [links.strip()] * (len(points) - 1)
        evidence = str(item.get("evidence", "")).strip() or None
        for idx in range(len(points) - 1):
            head = points[idx]
            tail = points[idx + 1]
            relation = link_list[idx] if idx < len(link_list) and link_list[idx] else "相关"
            if not head or not tail or head == tail:
                continue
            key = (head, relation, tail)
            if key in seen:
                continue
            seen.add(key)
            edge_id += 1
            edges.append(
                KnowledgeEdge(
                    head=head,
                    relation=relation,
                    tail=tail,
                    evidence=evidence,
                    source_id=edge_id,
                )
            )
    if not edges:
        _debug_log(
            f"[Graph Mode][Knowledge] parsed_list_len={len(data)} but no valid chains."
        )
    return edges


def build_knowledge_edges_cached(context: str) -> list[KnowledgeEdge]:
    key = _cache_key(context)
    if key in _EDGE_CACHE:
        return _EDGE_CACHE[key]

    disk_cache = _load_disk_cache()
    disk_entry = disk_cache.get(key)
    if isinstance(disk_entry, dict):
        cached_version = disk_entry.get("version")
        cached_model = disk_entry.get("model")
        cached_edges = disk_entry.get("edges")
        if (
            cached_version == _DISK_CACHE_VERSION
            and cached_model in (None, MODEL_JUDGE)
            and isinstance(cached_edges, list)
        ):
            edges = _deserialize_edges(cached_edges)
            _EDGE_CACHE[key] = edges
            _debug_log(
                f"[Graph Mode][Knowledge] disk cache hit key={key} edges={len(edges)}"
            )
            return edges

    edges = extract_edges_from_context(context)
    _EDGE_CACHE[key] = edges
    disk_cache[key] = {
        "version": _DISK_CACHE_VERSION,
        "model": MODEL_JUDGE,
        "edges": _serialize_edges(edges),
    }
    _save_disk_cache(disk_cache)
    _debug_log(f"[Graph Mode][Knowledge] total_edges={len(edges)}")
    return edges


def build_entity_pool(edges: list[KnowledgeEdge]) -> list[str]:
    entities: set[str] = set()
    for edge in edges:
        entities.add(edge.head)
        entities.add(edge.tail)
    return sorted(entities)


def group_edges_by_head(edges: list[KnowledgeEdge]) -> dict[str, list[KnowledgeEdge]]:
    grouped: dict[str, list[KnowledgeEdge]] = {}
    for edge in edges:
        grouped.setdefault(edge.head, []).append(edge)
    return grouped


def group_edges_by_tail(edges: list[KnowledgeEdge]) -> dict[str, list[KnowledgeEdge]]:
    grouped: dict[str, list[KnowledgeEdge]] = {}
    for edge in edges:
        grouped.setdefault(edge.tail, []).append(edge)
    return grouped


def edge_to_evidence_payload(edge: KnowledgeEdge) -> dict[str, Any]:
    snippet = edge.evidence or ""
    payload: dict[str, Any] = {
        "doc_spans": ["context"],
        "snippet": snippet,
        "image_regions": ["中心区域(参照 step_0 视觉锚点)"],
    }
    if edge.source_id is not None:
        payload["source_id"] = edge.source_id
    return payload
