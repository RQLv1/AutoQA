import json
from pathlib import Path
from typing import Any


def save_genqa_item(genqa_path: Path, payload: dict[str, Any]) -> None:
    genqa_path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, object]] = []
    if genqa_path.exists():
        try:
            loaded = json.loads(genqa_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                existing = loaded  # type: ignore[assignment]
            elif isinstance(loaded, dict):
                existing = [loaded]  # type: ignore[list-item]
            else:
                existing = []
        except json.JSONDecodeError:
            existing = []
    existing.append(payload)
    genqa_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
