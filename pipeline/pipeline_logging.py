from pathlib import Path

from utils.genqa import save_genqa_item
from utils.schema import EpisodeResult


def save_round_questions(
    log_path: Path,
    round_idx: int,
    episode: EpisodeResult,
    solver_final_pred: str | None = None,
    solver_final_raw: str | None = None,
    reflect_feedback: str | None = None,
    stop_reason: str | None = None,
) -> None:
    # Logging to question_log.* disabled.
    return None


def save_genqa_question(
    genqa_path: Path,
    episode: EpisodeResult,
    review_raw: str | None = None,
    review_decision: str | None = None,
) -> None:
    payload = {
        "question": episode.stage_final.question,
        "answer": episode.stage_final.answer,
        "reasoning": episode.stage_final.reasoning,
        "difficulty_metrics": episode.difficulty_metrics,
        "review_decision": review_decision,
        "review_raw": review_raw,
    }
    save_genqa_item(genqa_path, payload)
