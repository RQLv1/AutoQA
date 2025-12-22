import json
from pathlib import Path

from steps import step_to_dict
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
    if reflect_feedback is None:
        reflect_feedback = episode.reflect_feedback
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "round": round_idx,
        "stage_1": {
            "question": episode.stage_1.question,
            "answer": episode.stage_1.answer,
            "reasoning": episode.stage_1.reasoning,
            "raw": episode.stage_1.raw,
        },
        "stage_2": {
            "question": episode.stage_2.question,
            "answer": episode.stage_2.answer,
            "reasoning": episode.stage_2.reasoning,
            "raw": episode.stage_2.raw,
        },
        "stage_3": {
            "question": episode.stage_3.question,
            "answer": episode.stage_3.answer,
            "reasoning": episode.stage_3.reasoning,
            "raw": episode.stage_3.raw,
        },
        "stage_final": {
            "question": episode.stage_final.question,
            "answer": episode.stage_final.answer,
            "reasoning": episode.stage_final.reasoning,
            "raw": episode.stage_final.raw,
        },
        "final_question": episode.stage_final.question,
        "final_answer": episode.stage_final.answer,
        "final_reasoning": episode.stage_final.reasoning,
        "steps": [step_to_dict(step) for step in episode.steps],
        "difficulty_metrics": episode.difficulty_metrics,
        "solver_final_pred": solver_final_pred,
        "solver_final_raw": solver_final_raw,
        "reflect_feedback": reflect_feedback,
        "stop_reason": stop_reason,
        "judge_flags": episode.judge_flags,
    }
    if log_path.suffix == ".json":
        jsonl_path = log_path.with_suffix(".jsonl")
        pretty_path = log_path
    else:
        jsonl_path = log_path
        pretty_path = log_path.with_suffix(".json")

    with jsonl_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    existing: list[dict[str, object]] = []
    if pretty_path.exists():
        try:
            loaded = json.loads(pretty_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                existing = loaded  # type: ignore[assignment]
            elif isinstance(loaded, dict):
                existing = [loaded]  # type: ignore[list-item]
            else:
                existing = []
        except json.JSONDecodeError:
            existing = []
    existing.append(payload)
    pretty_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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
