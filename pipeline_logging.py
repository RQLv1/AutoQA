import json
from pathlib import Path

from pipeline_steps import step_to_dict
from schema import EpisodeResult


def save_round_questions(
    log_path: Path,
    round_idx: int,
    episode: EpisodeResult,
    solver_final_pred: str | None = None,
    reflect_feedback: str | None = None,
    stop_reason: str | None = None,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "round": round_idx,
        "stage_1": {
            "question": episode.stage_1.question,
            "answer": episode.stage_1.answer,
            "raw": episode.stage_1.raw,
        },
        "stage_2": {
            "question": episode.stage_2.question,
            "answer": episode.stage_2.answer,
            "raw": episode.stage_2.raw,
        },
        "stage_3": {
            "question": episode.stage_3.question,
            "answer": episode.stage_3.answer,
            "raw": episode.stage_3.raw,
        },
        "stage_final": {
            "question": episode.stage_final.question,
            "answer": episode.stage_final.answer,
            "raw": episode.stage_final.raw,
        },
        "steps": [step_to_dict(step) for step in episode.steps],
        "difficulty_metrics": episode.difficulty_metrics,
        "solver_final_pred": solver_final_pred,
        "reflect_feedback": reflect_feedback,
        "stop_reason": stop_reason,
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    pretty_path = log_path.with_suffix(".json")
    existing: list[dict[str, object]] = []
    if pretty_path.exists():
        try:
            existing = json.loads(pretty_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = []
    existing.append(payload)
    pretty_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
