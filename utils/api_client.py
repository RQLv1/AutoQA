import base64
import time
from pathlib import Path

from openai import OpenAI

from utils.config import (
    API_BASE_URL,
    API_KEY,
    API_RECONNECT_RETRIES,
    API_RECONNECT_SLEEP_SECONDS,
    DEFAULT_TEMPERATURE,
)


def encode_image(image_path: Path) -> str:
    with image_path.open("rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _sleep_before_retry(attempt: int, error: Exception) -> None:
    max_attempts = max(5, int(API_RECONNECT_RETRIES))
    if attempt >= max_attempts:
        return
    seconds = max(10, int(API_RECONNECT_SLEEP_SECONDS))
    if seconds <= 0:
        return
    print(
        f"[api_client] call failed (attempt {attempt}/{max_attempts}), retry in {seconds}s: {type(error).__name__}: {error}",
        flush=True,
    )
    time.sleep(seconds)


def _format_response_for_error(resp: object) -> str:
    if hasattr(resp, "model_dump"):
        try:
            return str(resp.model_dump())
        except Exception:
            pass
    if isinstance(resp, dict):
        return str(resp)
    return repr(resp)


def _extract_response_text(resp: object) -> str:
    choices = getattr(resp, "choices", None)
    if choices is None and isinstance(resp, dict):
        choices = resp.get("choices")
    if not choices:
        raise RuntimeError(f"响应缺少 choices: {_format_response_for_error(resp)}")

    choice0 = choices[0]
    message = getattr(choice0, "message", None)
    if message is None and isinstance(choice0, dict):
        message = choice0.get("message")
    if message is None:
        raise RuntimeError(f"响应缺少 message: {_format_response_for_error(resp)}")

    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")

    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    parts.append(str(part.get("text", "")))
            elif isinstance(part, str):
                parts.append(part)
        content = "".join(parts).strip()

    if content is None:
        raise RuntimeError(f"响应缺少 content: {_format_response_for_error(resp)}")

    if not isinstance(content, str):
        content = str(content)
    return content


def call_vision_model(
    prompt: str,
    image_path: Path,
    model: str,
    *,
    temperature: float = DEFAULT_TEMPERATURE,
) -> str:
    if not API_KEY:
        raise RuntimeError("缺少 API_KEY 配置，无法调用接口。")

    base64_image = encode_image(image_path)

    kwargs: dict[str, object] = {}
    # if max_tokens is not None:
    #     kwargs["max_tokens"] = max_tokens

    last_error: Exception | None = None
    max_attempts = max(5, int(API_RECONNECT_RETRIES))
    for attempt in range(1, max_attempts + 1):
        try:
            client = OpenAI(api_key=API_KEY, base_url=API_BASE_URL)
            resp = client.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{base64_image}"},
                            },
                        ],
                    }
                ],
                **kwargs,
            )
            return _extract_response_text(resp)
        except Exception as e:
            last_error = e
            _sleep_before_retry(attempt, e)
    raise last_error  # type: ignore[misc]


def call_text_model(
    prompt: str,
    model: str,
    *,
    max_tokens: int | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
) -> str:
    if not API_KEY:
        raise RuntimeError("缺少 API_KEY 配置，无法调用接口。")

    kwargs: dict[str, object] = {}
    # if max_tokens is not None:
    #     kwargs["max_tokens"] = max_tokens

    last_error: Exception | None = None
    max_attempts = max(5, int(API_RECONNECT_RETRIES))
    for attempt in range(1, max_attempts + 1):
        try:
            client = OpenAI(api_key=API_KEY, base_url=API_BASE_URL)
            resp = client.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )
            return _extract_response_text(resp)
        except Exception as e:
            last_error = e
            _sleep_before_retry(attempt, e)
    raise last_error  # type: ignore[misc]


def call_no_image_model(
    prompt: str,
    model: str,
    *,
    max_tokens: int | None = None,
    temperature: float = 0,
) -> str:
    return call_text_model(prompt, model, max_tokens=max_tokens, temperature=temperature)
