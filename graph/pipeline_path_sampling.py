import random

from graph.pipeline_graph import KnowledgeEdge, group_edges_by_head
from utils.config import MAX_SHORTCUT_EDGES, PATH_SAMPLER, REQUIRE_DISTINCT_SOURCES


def sample_path(
    edges: list[KnowledgeEdge],
    length: int,
    *,
    require_distinct_sources: bool = REQUIRE_DISTINCT_SOURCES,
    sampler: str = PATH_SAMPLER,
    max_shortcut_edges: int = MAX_SHORTCUT_EDGES,
) -> list[KnowledgeEdge]:
    if length <= 0:
        return []
    if not edges:
        return []

    if sampler not in {"rbfs", "random_walk"}:
        sampler = "rbfs"

    by_head = group_edges_by_head(edges)
    heads = list(by_head.keys())
    random.shuffle(heads)

    def is_shortcut(edge_a: KnowledgeEdge, edge_b: KnowledgeEdge) -> bool:
        if edge_a.source_id is None or edge_b.source_id is None:
            return False
        return edge_a.source_id == edge_b.source_id

    for start in heads:
        path: list[KnowledgeEdge] = []
        used_sources: set[int] = set()
        shortcut_edges = 0
        current = start

        for _ in range(length):
            candidates = by_head.get(current, [])
            if require_distinct_sources:
                candidates = [
                    edge
                    for edge in candidates
                    if edge.source_id is None or edge.source_id not in used_sources
                ]
            if not candidates:
                break
            edge = random.choice(candidates)
            if path and is_shortcut(path[-1], edge):
                shortcut_edges += 1
                if shortcut_edges > max_shortcut_edges:
                    break
            path.append(edge)
            if edge.source_id is not None:
                used_sources.add(edge.source_id)
            current = edge.tail

        if len(path) == length:
            return path

    shuffled = edges[:]
    random.shuffle(shuffled)
    return shuffled[:length]
