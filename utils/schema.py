from dataclasses import dataclass
from typing import Any


@dataclass
class StageResult:
    question: str
    answer: str
    raw: str


@dataclass
class StepResult:
    k: int
    question: str
    answer_text: str
    answer_letter: str | None
    evidence: Any
    modal_use: str
    cross_modal_bridge: bool
    raw: str
    judge_flags: dict[str, bool] | None = None


@dataclass
class EpisodeResult:
    stage_1: StageResult
    stage_2: StageResult
    stage_3: StageResult
    stage_final: StageResult
    steps: list[StepResult]
    difficulty_metrics: dict[str, Any]
    judge_flags: dict[str, bool] | None = None
