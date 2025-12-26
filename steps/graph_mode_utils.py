"""Graph mode utilities: edge processing and path sampling helpers."""

from graph.pipeline_graph import KnowledgeEdge
from graph.pipeline_path_sampling import sample_path


def normalize_edges(
    edges: list[KnowledgeEdge] | None, default_source_type: str
) -> list[KnowledgeEdge]:
    """Normalize edges by ensuring all have a source_type."""
    if not edges:
        return []
    normalized: list[KnowledgeEdge] = []
    for edge in edges:
        normalized.append(
            KnowledgeEdge(
                head=edge.head,
                relation=edge.relation,
                tail=edge.tail,
                evidence=edge.evidence,
                source_id=edge.source_id,
                source_type=edge.source_type or default_source_type,
            )
        )
    return normalized


def merge_edges_with_visual(
    text_edges: list[KnowledgeEdge], visual_edges: list[KnowledgeEdge] | None
) -> list[KnowledgeEdge]:
    """Merge text and visual edges with remapped source IDs."""
    normalized_text = normalize_edges(text_edges, "text")
    normalized_visual = normalize_edges(visual_edges, "image")
    if not normalized_visual:
        return normalized_text

    max_source_id = max((edge.source_id or 0) for edge in normalized_text) if normalized_text else 0
    offset = max_source_id + 1000
    remapped_visual: list[KnowledgeEdge] = []
    for idx, edge in enumerate(normalized_visual, start=1):
        source_id = edge.source_id
        if source_id is None:
            source_id = offset + idx
        else:
            source_id = offset + source_id
        remapped_visual.append(
            KnowledgeEdge(
                head=edge.head,
                relation=edge.relation,
                tail=edge.tail,
                evidence=edge.evidence,
                source_id=source_id,
                source_type="image",
            )
        )
    return [*normalized_text, *remapped_visual]


def sample_path_with_visual(
    edges: list[KnowledgeEdge], length: int, require_visual: bool
) -> list[KnowledgeEdge]:
    """Sample a path from edges, preferring visual edges if required."""
    if not require_visual:
        return sample_path(edges, length)
    for _ in range(6):
        path = sample_path(edges, length)
        if any(edge.source_type == "image" for edge in path):
            return path
    return sample_path(edges, length)


def edge_source_label(edge: KnowledgeEdge) -> str:
    """Get display label for edge source type."""
    return "图片视觉分析" if edge.source_type == "image" else "参考信息"
