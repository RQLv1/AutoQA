import random

from graph.pipeline_graph import Triplet, group_triplets_by_head
from utils.config import MAX_SHORTCUT_EDGES, PATH_SAMPLER, REQUIRE_DISTINCT_SOURCES


def sample_path(
    triplets: list[Triplet],
    length: int,
    *,
    require_distinct_sources: bool = REQUIRE_DISTINCT_SOURCES,
    sampler: str = PATH_SAMPLER,
    max_shortcut_edges: int = MAX_SHORTCUT_EDGES,
) -> list[Triplet]:
    if length <= 0:
        return []
    if not triplets:
        return []

    if sampler not in {"rbfs", "random_walk"}:
        sampler = "rbfs"

    by_head = group_triplets_by_head(triplets)
    heads = list(by_head.keys())
    random.shuffle(heads)

    def is_shortcut(edge_a: Triplet, edge_b: Triplet) -> bool:
        # Minimal heuristic: consider it a shortcut if both edges come from same chunk.
        return edge_a.chunk_id == edge_b.chunk_id

    for start in heads:
        path: list[Triplet] = []
        used_chunks: set[int] = set()
        shortcut_edges = 0
        current = start

        for _ in range(length):
            candidates = by_head.get(current, [])
            if require_distinct_sources:
                candidates = [t for t in candidates if t.chunk_id not in used_chunks]
            if not candidates:
                break
            edge = random.choice(candidates)
            if path and is_shortcut(path[-1], edge):
                shortcut_edges += 1
                if shortcut_edges > max_shortcut_edges:
                    break
            path.append(edge)
            used_chunks.add(edge.chunk_id)
            current = edge.tail

        if len(path) == length:
            return path

    shuffled = triplets[:]
    random.shuffle(shuffled)
    return shuffled[:length]
