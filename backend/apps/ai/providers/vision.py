"""A provider that can be shown one image (IR-852).

Separate and abstract, like `ToolCallingLLM`: every decorator on a task's
chain implements it, so none -- admission above all -- can be skipped by a
default body.
"""

from __future__ import annotations

import base64
from abc import ABC, abstractmethod


class ImageDescribingLLM(ABC):
    @abstractmethod
    def describe_image(self, system: str, user: str, image: bytes, media_type: str) -> str:
        """Answer `user` about `image` under `system`. Raises `LLMUnavailable`
        as `generate` does."""


def require_image_describing(provider) -> ImageDescribingLLM:
    if not isinstance(provider, ImageDescribingLLM):
        raise TypeError(f"{type(provider).__name__} cannot be shown an image")
    return provider


def data_url(image: bytes, media_type: str) -> str:
    return f"data:{media_type};base64,{base64.b64encode(image).decode('ascii')}"
