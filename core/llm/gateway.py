"""Unified Azure OpenAI access — every LLM call in the system goes through here.

Responsibilities:
  - Render prompts via PromptLoader (auto-injects shared boilerplate).
  - Hash inputs for cache + trace.
  - Call Azure with `response_format=json_schema strict` for structured outputs.
  - Validate response against the bound Pydantic schema; one retry with "fix your JSON" addendum.
  - Track cost, enforce session budget cap, write trace events.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import TypeVar
from uuid import UUID

from openai import AsyncAzureOpenAI
from pydantic import BaseModel, ValidationError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.config import get_settings
from core.llm.cache import llm_get, llm_set, make_llm_key
from core.llm.cost import BudgetExceeded, add_cost, get_pricing
from core.llm.structured import schema_for_response_format
from core.prompts.loader import get_prompt_loader
from observability.trace import log_event, stopwatch

T = TypeVar("T", bound=BaseModel)


class LLMGatewayError(RuntimeError):
    """Wraps non-retryable failures from the gateway."""


class StructuredOutputParseError(LLMGatewayError):
    """Raised when the model output cannot be coerced into the bound schema after retry."""


_RETRYABLE = (TimeoutError, ConnectionError)


def _client() -> AsyncAzureOpenAI:
    s = get_settings()
    return AsyncAzureOpenAI(
        api_key=s.AZURE_OPENAI_API_KEY.get_secret_value(),
        api_version=s.AZURE_OPENAI_API_VERSION,
        azure_endpoint=s.AZURE_OPENAI_ENDPOINT,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def call_structured(
    *,
    prompt_name: str,
    variables: dict | None,
    output_schema: type[T],
    session_id: UUID,
    agent_name: str | None = None,
    prompt_version: str | None = None,
    temperature: float = 0.0,
    use_cache: bool = True,
) -> T:
    """Render a prompt, call Azure with structured-output enforcement, return parsed Pydantic."""
    loader = get_prompt_loader()
    rendered = loader.render(prompt_name, variables=variables, version=prompt_version)
    schema_payload = schema_for_response_format(output_schema)
    cache_key = make_llm_key(
        rendered.agent_name, rendered.version, variables, output_schema.__name__
    )

    # ---------------- cache hit ----------------
    if use_cache:
        cached = llm_get(cache_key)
        if cached is not None:
            log_event(
                session_id=session_id,
                agent_name=agent_name or rendered.agent_name,
                input_hash=_hash_from_key(cache_key),
                prompt_name=rendered.agent_name,
                prompt_version=rendered.version,
                output_size=len(cached),
                cache_hit=True,
            )
            return output_schema.model_validate_json(cached)

    # ---------------- live call ----------------
    settings = get_settings()
    client = _client()

    with stopwatch() as elapsed:
        try:
            response = await _invoke_with_retry(
                client=client,
                deployment=settings.AZURE_OPENAI_DEPLOYMENT,
                rendered_text=rendered.text,
                response_format=schema_payload,
                temperature=temperature,
            )
        except Exception as exc:
            log_event(
                session_id=session_id,
                agent_name=agent_name or rendered.agent_name,
                input_hash=_hash_from_key(cache_key),
                prompt_name=rendered.agent_name,
                prompt_version=rendered.version,
                latency_ms=elapsed(),
                error=f"{type(exc).__name__}: {exc}",
            )
            raise

        msg = response.choices[0].message
        raw = msg.content or ""
        usage = response.usage
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0

        # ---------------- parse + repair ----------------
        try:
            parsed = output_schema.model_validate_json(raw)
        except ValidationError as first_err:
            repair_prompt = (
                f"{rendered.text}\n\n"
                f"Your previous response failed schema validation:\n{first_err}\n\n"
                f"Return only valid JSON matching the declared schema. No prose."
            )
            response = await _invoke_with_retry(
                client=client,
                deployment=settings.AZURE_OPENAI_DEPLOYMENT,
                rendered_text=repair_prompt,
                response_format=schema_payload,
                temperature=0.0,
            )
            raw = response.choices[0].message.content or ""
            usage = response.usage
            prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
            completion_tokens += getattr(usage, "completion_tokens", 0) or 0
            try:
                parsed = output_schema.model_validate_json(raw)
            except ValidationError as second_err:
                cost = get_pricing().chat_cost(prompt_tokens, completion_tokens)
                _try_add_cost(session_id, cost)
                log_event(
                    session_id=session_id,
                    agent_name=agent_name or rendered.agent_name,
                    input_hash=_hash_from_key(cache_key),
                    prompt_name=rendered.agent_name,
                    prompt_version=rendered.version,
                    output_size=len(raw),
                    tokens_in=prompt_tokens,
                    tokens_out=completion_tokens,
                    cost_usd=cost,
                    latency_ms=elapsed(),
                    error=f"schema parse failed twice: {second_err}",
                )
                raise StructuredOutputParseError(str(second_err)) from second_err

        cost = get_pricing().chat_cost(prompt_tokens, completion_tokens)
        _try_add_cost(session_id, cost)

        if use_cache:
            llm_set(cache_key, parsed.model_dump_json())

        log_event(
            session_id=session_id,
            agent_name=agent_name or rendered.agent_name,
            input_hash=_hash_from_key(cache_key),
            prompt_name=rendered.agent_name,
            prompt_version=rendered.version,
            output_size=len(raw),
            tokens_in=prompt_tokens,
            tokens_out=completion_tokens,
            cost_usd=cost,
            latency_ms=elapsed(),
            cache_hit=False,
        )

    return parsed


async def call_text(
    *,
    prompt_name: str,
    variables: dict | None,
    session_id: UUID,
    agent_name: str | None = None,
    prompt_version: str | None = None,
    temperature: float = 0.7,
    use_cache: bool = True,
) -> str:
    """Plain text call — for cases where structured output is not desired."""
    loader = get_prompt_loader()
    rendered = loader.render(prompt_name, variables=variables, version=prompt_version)
    cache_key = make_llm_key(rendered.agent_name, rendered.version, variables, "text")

    if use_cache:
        cached = llm_get(cache_key)
        if cached is not None:
            log_event(
                session_id=session_id,
                agent_name=agent_name or rendered.agent_name,
                input_hash=_hash_from_key(cache_key),
                prompt_name=rendered.agent_name,
                prompt_version=rendered.version,
                output_size=len(cached),
                cache_hit=True,
            )
            return cached

    settings = get_settings()
    client = _client()
    with stopwatch() as elapsed:
        response = await _invoke_with_retry(
            client=client,
            deployment=settings.AZURE_OPENAI_DEPLOYMENT,
            rendered_text=rendered.text,
            response_format=None,
            temperature=temperature,
        )
        text = response.choices[0].message.content or ""
        usage = response.usage
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        cost = get_pricing().chat_cost(prompt_tokens, completion_tokens)
        _try_add_cost(session_id, cost)
        if use_cache:
            llm_set(cache_key, text)
        log_event(
            session_id=session_id,
            agent_name=agent_name or rendered.agent_name,
            input_hash=_hash_from_key(cache_key),
            prompt_name=rendered.agent_name,
            prompt_version=rendered.version,
            output_size=len(text),
            tokens_in=prompt_tokens,
            tokens_out=completion_tokens,
            cost_usd=cost,
            latency_ms=elapsed(),
            cache_hit=False,
        )
    return text


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


async def _invoke_with_retry(
    *,
    client: AsyncAzureOpenAI,
    deployment: str,
    rendered_text: str,
    response_format: dict | None,
    temperature: float,
):
    kwargs: dict = {
        "model": deployment,
        "messages": [{"role": "user", "content": rendered_text}],
        "temperature": temperature,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format

    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(_RETRYABLE),
        reraise=True,
    ):
        with attempt:
            return await client.chat.completions.create(**kwargs)


def _hash_from_key(cache_key: str) -> str:
    """Cache key already contains the sha256; strip prefix for the trace `input_hash` column."""
    return cache_key.split(":")[-1]


def _try_add_cost(session_id: UUID, cost: Decimal) -> None:
    try:
        add_cost(session_id, cost)
    except BudgetExceeded:
        # Re-raise — this is a hard cap, callers should know.
        raise
    except Exception:
        # Redis hiccup shouldn't kill the call. Cost will be slightly under-tracked.
        import logging

        logging.getLogger("core.llm.cost").exception("add_cost failed")
