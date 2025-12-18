import base64
from pathlib import Path

from openai import OpenAI

from config import API_BASE_URL, API_KEY


def encode_image(image_path: Path) -> str:
    with image_path.open("rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_vision_model(prompt: str, image_path: Path, model: str) -> str:
    if not API_KEY:
        raise RuntimeError("缺少 API_KEY 配置，无法调用接口。")

    client = OpenAI(api_key=API_KEY, base_url=API_BASE_URL)
    base64_image = encode_image(image_path)

    resp = client.chat.completions.create(
        model=model,
        temperature=0,
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
    )
    return resp.choices[0].message.content


def call_text_model(prompt: str, model: str) -> str:
    if not API_KEY:
        raise RuntimeError("缺少 API_KEY 配置，无法调用接口。")

    client = OpenAI(api_key=API_KEY, base_url=API_BASE_URL)
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content
