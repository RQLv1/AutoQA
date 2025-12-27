from pathlib import Path

from graph.pipeline_graph import KnowledgeEdge
from steps.graph_mode import generate_steps_graph_mode
from steps.prompt_driven import generate_steps_prompt_driven
from utils.config import ENABLE_GRAPH_MODE
from utils.schema import StepResult


def generate_steps(
    context: str,
    image_path: Path,
    feedback: str,
    previous_final_question: str | None,
    visual_summary: str | None,
    visual_edges: list[KnowledgeEdge] | None,
) -> tuple[list[StepResult], bool]:
    if ENABLE_GRAPH_MODE:
        return generate_steps_graph_mode(
            context,
            image_path,
            feedback,
            previous_final_question,
            visual_summary,
            visual_edges,
        )
    return generate_steps_prompt_driven(
        context,
        image_path,
        feedback,
        previous_final_question,
        visual_summary,
    )
