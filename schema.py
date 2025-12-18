from dataclasses import dataclass


@dataclass
class StageResult:
    question: str
    answer: str
    raw: str
