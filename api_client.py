import base64
from pathlib import Path

from openai import OpenAI

from config import API_BASE_URL, API_KEY


def encode_image(image_path: Path) -> str:
    with image_path.open("rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_vision_model(
    prompt: str,
    image_path: Path,
    model: str,
    *,
    max_tokens: int | None = None,
    temperature: float = 0,
) -> str:
    if not API_KEY:
        raise RuntimeError("缺少 API_KEY 配置，无法调用接口。")

    client = OpenAI(api_key=API_KEY, base_url=API_BASE_URL)
    base64_image = encode_image(image_path)

    kwargs: dict[str, object] = {}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

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
    return resp.choices[0].message.content or ""


def call_text_model(
    prompt: str,
    model: str,
    *,
    max_tokens: int | None = None,
    temperature: float = 0,
) -> str:
    if not API_KEY:
        raise RuntimeError("缺少 API_KEY 配置，无法调用接口。")

    client = OpenAI(api_key=API_KEY, base_url=API_BASE_URL)
    kwargs: dict[str, object] = {}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
        **kwargs,
    )
    return resp.choices[0].message.content or ""
