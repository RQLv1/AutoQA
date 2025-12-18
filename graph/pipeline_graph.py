import hashlib
import json
from dataclasses import dataclass
from typing import Any

from utils.api_client import call_text_model
from utils.config import MODEL_JUDGE


@dataclass(frozen=True)
class DocChunk:
    chunk_id: int
    text: str


@dataclass(frozen=True)
class Triplet:
    head: str
    relation: str
    tail: str
    chunk_id: int
    evidence: str | None = None


_TRIPLET_CACHE: dict[str, list[Triplet]] = {}
_CHUNK_CACHE: dict[str, list[DocChunk]] = {}


def chunk_context(context: str, target_words: int) -> list[DocChunk]:
    paragraphs = [p.strip() for p in context.split("\n\n") if p.strip()]
    chunks: list[DocChunk] = []
    buf: list[str] = []
    buf_words = 0
    chunk_id = 0

    def flush() -> None:
        nonlocal chunk_id, buf, buf_words
        if not buf:
            return
        chunk_id += 1
        chunks.append(DocChunk(chunk_id=chunk_id, text="\n\n".join(buf).strip()))
        buf = []
        buf_words = 0

    for para in paragraphs:
        words = len(para.split())
        if buf and buf_words + words > target_words:
            flush()
        buf.append(para)
        buf_words += words
    flush()
    return chunks


def _cache_key(context: str, target_words: int) -> str:
    payload = f"{target_words}\n{context}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


def get_chunks_cached(context: str, target_words: int) -> list[DocChunk]:
    key = _cache_key(context, target_words)
    if key not in _CHUNK_CACHE:
        _CHUNK_CACHE[key] = chunk_context(context, target_words)
    return _CHUNK_CACHE[key]


def _triplet_extraction_prompt(chunk: DocChunk) -> str:
    return (
        "从下述文本中抽取最多 12 条三元组 (head, relation, tail)，用于构建本地知识图谱。\n"
        "要求:\n"
        "- head/tail 尽量是短实体/短短语（<= 20 字），不要用代词。\n"
        "- relation 用短谓词（<= 12 字），不要写长句。\n"
        "- 每条都要能在该 chunk 内找到依据。\n"
        "- 只输出 JSON 数组，元素格式:\n"
        '  {"head":"...","relation":"...","tail":"...","evidence":"原文片段(<=40字)"}\n'
        f"\nchunk_id={chunk.chunk_id}\n"
        f"文本:\n{chunk.text.strip()}\n"
    )


def extract_triplets_from_chunk(chunk: DocChunk) -> list[Triplet]:
    prompt = _triplet_extraction_prompt(chunk)
    raw = call_text_model(prompt, MODEL_JUDGE, max_tokens=800, temperature=0)
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return []

    triplets: list[Triplet] = []
    if not isinstance(data, list):
        return triplets
    for item in data:
        if not isinstance(item, dict):
            continue
        head = str(item.get("head", "")).strip()
        relation = str(item.get("relation", "")).strip()
        tail = str(item.get("tail", "")).strip()
        evidence = str(item.get("evidence", "")).strip() or None
        if not head or not relation or not tail:
            continue
        triplets.append(
            Triplet(head=head, relation=relation, tail=tail, chunk_id=chunk.chunk_id, evidence=evidence)
        )
    return triplets


def build_triplets_cached(
    context: str, target_words: int, max_chunks: int = 20
) -> tuple[list[DocChunk], list[Triplet]]:
    key = f"{_cache_key(context, target_words)}:{max_chunks}"
    if key in _TRIPLET_CACHE:
        chunks = get_chunks_cached(context, target_words)
        return chunks, _TRIPLET_CACHE[key]

    chunks = get_chunks_cached(context, target_words)
    triplets: list[Triplet] = []
    for chunk in chunks[:max_chunks]:
        triplets.extend(extract_triplets_from_chunk(chunk))
    _TRIPLET_CACHE[key] = triplets
    return chunks, triplets


def build_entity_pool(triplets: list[Triplet]) -> list[str]:
    entities: set[str] = set()
    for t in triplets:
        entities.add(t.head)
        entities.add(t.tail)
    return sorted(entities)


def group_triplets_by_head(triplets: list[Triplet]) -> dict[str, list[Triplet]]:
    grouped: dict[str, list[Triplet]] = {}
    for t in triplets:
        grouped.setdefault(t.head, []).append(t)
    return grouped


def group_triplets_by_tail(triplets: list[Triplet]) -> dict[str, list[Triplet]]:
    grouped: dict[str, list[Triplet]] = {}
    for t in triplets:
        grouped.setdefault(t.tail, []).append(t)
    return grouped


def triplet_to_evidence_payload(triplet: Triplet, chunks: list[DocChunk]) -> dict[str, Any]:
    chunk_text = ""
    for c in chunks:
        if c.chunk_id == triplet.chunk_id:
            chunk_text = c.text
            break
    snippet = triplet.evidence or (chunk_text.strip()[:120] if chunk_text else "")
    return {
        "chunk_id": triplet.chunk_id,
        "doc_spans": [f"chunk:{triplet.chunk_id}"],
        "snippet": snippet,
        "image_regions": ["中心区域(参照 step_0 视觉锚点)"],
    }
