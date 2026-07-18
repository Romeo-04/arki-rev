from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
from pathlib import Path
from typing import Any, Callable, Protocol

from pydantic import ValidationError

from arkirev.models import RevisionAnalysis
from arkirev.prompts import VISION_SYSTEM_PROMPT, VISION_USER_PROMPT

ImageInput = str | Path | bytes
DEFAULT_OPENAI_MODEL = "gpt-4o"


class VisionProvider(Protocol):
    def compare_revisions(
        self,
        before_image: ImageInput,
        after_image: ImageInput,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str | dict[str, Any] | RevisionAnalysis:
        ...


def compare_revisions(
    before_image: ImageInput,
    after_image: ImageInput,
    provider: VisionProvider | Callable[..., str | dict[str, Any] | RevisionAnalysis] | None = None,
) -> RevisionAnalysis:
    """Run optional AI revision comparison.

    If no provider is supplied, this uses OpenAI credentials from the local
    environment. Deterministic budget and schedule functions do not depend on it.
    """
    if provider is None:
        provider = OpenAIRevisionProvider.from_env()

    response = _call_provider(provider, before_image, after_image)
    if isinstance(response, RevisionAnalysis):
        return response
    if isinstance(response, dict):
        return _validate_analysis(response)
    if isinstance(response, str):
        return parse_revision_analysis(response)
    raise ValueError(f"Vision provider returned unsupported response type: {type(response).__name__}")


def parse_revision_analysis(raw_response: str) -> RevisionAnalysis:
    """Parse strict or fenced JSON into RevisionAnalysis."""
    payload = _extract_json(raw_response)
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed AI response JSON: {exc.msg}") from exc
    return _validate_analysis(parsed)


class OpenAIRevisionProvider:
    """OpenAI Responses API provider for optional revision analysis."""

    def __init__(self, client: Any, model: str = DEFAULT_OPENAI_MODEL, detail: str = "high") -> None:
        self.client = client
        self.model = model
        self.detail = detail

    @classmethod
    def from_env(cls) -> OpenAIRevisionProvider:
        _load_dotenv_if_available()
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        model = os.getenv("OPENAI_MODEL") or os.getenv("OPENAI_model") or DEFAULT_OPENAI_MODEL
        base_url = os.getenv("OPENAI_BASE_URL")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ValueError("OpenAI SDK is required. Install it with: pip install openai") from exc

        kwargs: dict[str, str] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        return cls(OpenAI(**kwargs), model=model)

    def compare_revisions(
        self,
        before_image: ImageInput,
        after_image: ImageInput,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        response = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": user_prompt},
                        {
                            "type": "input_image",
                            "image_url": _image_to_data_url(before_image),
                            "detail": self.detail,
                        },
                        {
                            "type": "input_image",
                            "image_url": _image_to_data_url(after_image),
                            "detail": self.detail,
                        },
                    ],
                },
            ],
            text={"format": {"type": "json_object"}},
        )
        output_text = getattr(response, "output_text", None)
        if not output_text:
            raise ValueError("OpenAI response did not include output_text")
        return str(output_text)


def _call_provider(
    provider: VisionProvider | Callable[..., str | dict[str, Any] | RevisionAnalysis],
    before_image: ImageInput,
    after_image: ImageInput,
) -> str | dict[str, Any] | RevisionAnalysis:
    kwargs = {
        "system_prompt": VISION_SYSTEM_PROMPT,
        "user_prompt": VISION_USER_PROMPT,
    }
    if callable(provider):
        return provider(before_image, after_image, **kwargs)
    return provider.compare_revisions(before_image, after_image, **kwargs)


def _extract_json(raw_response: str) -> str:
    text = raw_response.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    return text


def _validate_analysis(payload: dict[str, Any]) -> RevisionAnalysis:
    try:
        return RevisionAnalysis.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid RevisionAnalysis payload: {exc}") from exc


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def _image_to_data_url(image: ImageInput) -> str:
    if isinstance(image, bytes):
        encoded = base64.b64encode(image).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    image_text = str(image)
    if image_text.startswith(("http://", "https://", "data:")):
        return image_text

    image_path = Path(image)
    if not image_path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
