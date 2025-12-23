from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from utils.api_client import call_text_model, call_vision_model
from utils.config import MODEL_STAGE_1, MODEL_STAGE_2

DEFAULT_TEXT_PROMPT = "Say hello in one sentence."
DEFAULT_VISION_PROMPT = "Describe the main objects in the image in one sentence."
DEFAULT_IMAGE_PATH = Path("test.png")


def _run_text_test(
    prompt: str,
    model: str,
    *,
    max_tokens: int | None,
    temperature: float,
) -> dict[str, Any]:
    start = time.time()
    response = call_text_model(
        prompt,
        model,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    latency = round(time.time() - start, 3)
    return {
        "mode": "text",
        "model": model,
        "latency_s": latency,
        "response": response,
    }


def _run_vision_test(
    prompt: str,
    image_path: Path,
    model: str,
    *,
    max_tokens: int | None,
    temperature: float,
) -> dict[str, Any]:
    if not image_path.exists():
        raise FileNotFoundError(f"image not found: {image_path}")
    start = time.time()
    response = call_vision_model(
        prompt,
        image_path,
        model,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    latency = round(time.time() - start, 3)
    return {
        "mode": "vision",
        "model": model,
        "latency_s": latency,
        "response": response,
    }


def _print_results(results: list[dict[str, Any]], json_output: bool) -> None:
    if json_output:
        payload: Any = results[0] if len(results) == 1 else results
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    for idx, result in enumerate(results, start=1):
        if idx > 1:
            print("-" * 40)
        print(
            f"[{result['mode']}] model={result['model']} latency={result['latency_s']}s"
        )
        print(result["response"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple API connectivity test.")
    parser.add_argument(
        "--mode",
        choices=("text", "vision", "both"),
        default="both",
        help="Which test to run.",
    )
    parser.add_argument(
        "--text-model",
        default=MODEL_STAGE_2,
        help="Model name for text test.",
    )
    parser.add_argument(
        "--vision-model",
        default=MODEL_STAGE_1,
        help="Model name for vision test.",
    )
    parser.add_argument(
        "--text-prompt",
        default=DEFAULT_TEXT_PROMPT,
        help="Prompt for the text model.",
    )
    parser.add_argument(
        "--vision-prompt",
        default=DEFAULT_VISION_PROMPT,
        help="Prompt for the vision model.",
    )
    parser.add_argument(
        "--image",
        type=Path,
        default=DEFAULT_IMAGE_PATH,
        help="Image path for the vision test.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Optional max tokens to limit the response.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0,
        help="Sampling temperature.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the result as JSON.",
    )
    args = parser.parse_args()

    results: list[dict[str, Any]] = []
    if args.mode in {"text", "both"}:
        results.append(
            _run_text_test(
                args.text_prompt,
                args.text_model,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
            )
        )
    if args.mode in {"vision", "both"}:
        results.append(
            _run_vision_test(
                args.vision_prompt,
                args.image,
                args.vision_model,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
            )
        )

    _print_results(results, args.json)


if __name__ == "__main__":
    main()
