"""Graph mode main entry: orchestrates knowledge graph-based question generation."""

from pathlib import Path

from graph.pipeline_graph import KnowledgeEdge, build_entity_pool, build_knowledge_edges_cached
from steps.graph_mode_step0 import generate_step0
from steps.graph_mode_step_chain import generate_step_chain
from steps.graph_mode_utils import merge_edges_with_visual, sample_path_with_visual
from utils.config import MAX_STEPS_PER_ROUND, MIN_HOPS
from utils.details_logger import get_details_logger
from utils.schema import StepResult


def generate_steps_graph_mode(
    context: str,
    image_path: Path,
    feedback: str,
    previous_final_question: str | None,
    visual_summary: str | None,
    visual_edges: list[KnowledgeEdge] | None,
    mode: str = "multi_select",
) -> tuple[list[StepResult], bool]:
    """
    Generate multi-hop reasoning steps using knowledge graph mode.

    Args:
        context: Reference text for fact extraction
        image_path: Path to input image
        feedback: User feedback for generation
        previous_final_question: Optional question from previous round to extend
        visual_summary: Optional visual description of image
        visual_edges: Optional knowledge edges extracted from image

    Returns:
        Tuple of (steps, cross_modal_used):
            - steps: List of StepResults representing reasoning chain
            - cross_modal_used: Always True in graph mode
    """
    steps: list[StepResult] = []
    cross_modal_used = True

    # Build knowledge graph
    target_hops = min(MAX_STEPS_PER_ROUND - 1, max(MIN_HOPS, 2))
    text_edges = build_knowledge_edges_cached(context)
    all_edges = merge_edges_with_visual(text_edges, visual_edges)

    # Generate Step 0 (anchor step)
    step0 = generate_step0(
        context,
        image_path,
        feedback,
        previous_final_question,
        visual_summary,
        all_edges,
        mode=mode,
    )
    steps.append(step0)

    # Early exit if no edges or target_hops is 0
    if not all_edges or target_hops <= 0:
        print("[Graph Mode] 知识点链为空或 hop=0，退化为仅 step_0。")
        return steps, cross_modal_used

    # Sample path through knowledge graph
    entity_pool = build_entity_pool(all_edges)
    require_visual = any(edge.source_type == "image" for edge in all_edges)
    path = sample_path_with_visual(all_edges, target_hops, require_visual)
    if not path:
        print("[Graph Mode] 知识链路径采样失败，退化为仅 step_0。")
        return steps, cross_modal_used

    get_details_logger().log_event(
        "graph_path",
        {
            "target_hops": target_hops,
            "require_visual": require_visual,
            "edges": [
                {
                    "head": edge.head,
                    "relation": edge.relation,
                    "tail": edge.tail,
                    "evidence": edge.evidence,
                    "source_id": edge.source_id,
                    "source_type": edge.source_type,
                }
                for edge in path
            ],
        },
    )

    # Generate steps 1+ along the path
    subsequent_steps = generate_step_chain(
        context,
        image_path,
        feedback,
        visual_summary,
        step0,
        path,
        all_edges,
        mode=mode,
    )
    steps.extend(subsequent_steps)

    return steps, cross_modal_used
