"""Provider compatibility helpers for OpenAI-compatible chat APIs."""
from __future__ import annotations

import inspect
import time
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

import openai
from openai.types.chat import ChatCompletion


class ProviderResponseError(Exception):
    """A provider response could not be normalized into a chat completion."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def is_spark_provider(base_url: str) -> bool:
    hostname = (urlsplit(str(base_url or "")).hostname or "").casefold()
    return hostname == "spark-api-open.xf-yun.com"


def normalize_spark_chat_response(payload: Mapping[str, Any], model: str) -> ChatCompletion:
    normalized = dict(payload)
    code = normalized.get("code")
    if code not in (None, 0):
        detail = str(normalized.get("message") or "讯飞模型返回错误")
        raise ProviderResponseError(detail)

    choices = normalized.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderResponseError("模型响应缺少 choices")
    normalized_choices: list[dict[str, Any]] = []
    for index, choice in enumerate(choices):
        if not isinstance(choice, Mapping):
            raise ProviderResponseError("模型响应的 choices 格式无效")
        normalized_choice = dict(choice)
        normalized_choice.setdefault("index", index)
        normalized_choice.setdefault("finish_reason", "stop")
        normalized_choices.append(normalized_choice)
    normalized["choices"] = normalized_choices
    normalized.setdefault("id", str(normalized.get("sid") or f"spark-{int(time.time() * 1000)}"))
    normalized.setdefault("created", int(time.time()))
    normalized.setdefault("model", model)
    normalized.setdefault("object", "chat.completion")
    return ChatCompletion.model_validate(normalized)


async def create_chat_completion(
    *,
    api_key: str,
    base_url: str,
    model: str,
    messages: Iterable[Mapping[str, Any]],
    client_class: type[Any] | None = None,
    **kwargs: Any,
) -> ChatCompletion:
    client_type = client_class or openai.AsyncOpenAI
    client = client_type(api_key=api_key, base_url=base_url)
    try:
        if is_spark_provider(base_url):
            raw_response = await client.chat.completions.with_raw_response.create(
                model=model,
                messages=messages,
                **kwargs,
            )
            payload = raw_response.json()
            if not isinstance(payload, Mapping):
                raise ProviderResponseError("模型响应格式无效")
            return normalize_spark_chat_response(payload, model)
        return await client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs,
        )
    finally:
        close = getattr(client, "close", None)
        if close:
            result = close()
            if inspect.isawaitable(result):
                await result
