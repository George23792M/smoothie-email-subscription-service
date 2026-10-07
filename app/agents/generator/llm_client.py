import logging
from typing import Optional
from langchain_openai import ChatOpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

"""
LLM client with retry logic and token tracking.

Handles:
- ChatOpenAI singleton (reuse connection)
- Retry logic: exponential backoff on transient errors, fail-fast on auth errors
- LangSmith tracing (automatic via environment variables)
- Token counting and cost calculation
"""
# Singleton LLM client (reuse connection across calls)
_llm_client: dict[str, ChatOpenAI] = {}


def _get_llm_client(model: str) -> ChatOpenAI:
    """
    Get or create ChatOpenAI singleton.

    Reusing the same client connection improves performance and
    enables LangSmith tracing to track costs across calls.

    Returns:
        ChatOpenAI instance configured with settings
    """
    global _llm_client

    if model not in _llm_client:
        _llm_client[model] = ChatOpenAI(
            model=model,
            api_key=settings.OPENAI_API_KEY,
            temperature=0.7,  # creativity
            timeout=30,  # 30 seconds timeout configured per call
            max_retries=0,  # retry handled by @retry decorator
        )
        logger.info(f"Initialized ChatOpenAI client ({model})")

    return _llm_client[model]


@retry(
    stop=stop_after_attempt(settings.MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    retry=retry_if_exception_type((TimeoutError, ConnectionError)),
    reraise=True,
)
async def call_llm_with_retry(
    prompt: str, correlation_id: str, model: str = "gpt-4-turbo"
) -> str:
    """
    Call LLM with retry logic and LangSmith tracing.

    Retry Strategy:
    - Retries: Up to MAX_RETRIES times
    - On: TimeoutError, ConnectionError (transient)
    - NOT on: 401, 403 (auth errors - fail fast)
    - Backoff: Exponential (1s → 2s → 4s... max 30s)
    - Timeout: 30 seconds per call

    LangSmith Tracing:
    - Automatic if LANGSMITH_ENABLED=true and env vars set
    - Tracks: latency, tokens, cost, errors, full prompt/response
    - View at: https://smith.langchain.com

    Args:
        prompt: Full rendered prompt (from render_generation_prompt)
        correlation_id: Workflow correlation ID for tracing

    Returns:
        LLM response text (content field)

    Raises:
        ValueError: If response missing content or is empty
        Exception: On max retries exceeded (TimeoutError/ConnectionError)
                   or other errors (auth, rate limit, etc.)
    """
    try:
        llm = _get_llm_client(model)

        # Call LLM async for non-blocking I/O
        # Langsmith tracing is enabled
        response = await llm.ainvoke(prompt)

        # Validate response
        if not response.content:
            raise ValueError(
                f"LLM returned empty response (model={model},correlation_id={correlation_id})"
            )

        logger.debug(
            f"LLM call successful (model={model},correlation_id={correlation_id})",
            extra={"correlation_id": correlation_id},
        )

        return response.content

    except Exception as e:
        # log before re-sending for tenacity to retry
        logger.warning(
            f"LLM call failed: {type(e).__name__}: {str(e)}"
            f"(model={model},correlation_id={correlation_id})",
            extra={"correlation_id": correlation_id},
        )
        raise


def get_llm_client(model: str) -> ChatOpenAI:
    """
    Get ChatOpenAI client for direct use (if bypassing retry logic).

    Normally use call_llm_with_retry() instead.
    This is exposed for advanced use cases (e.g., streaming).

    Returns:
        ChatOpenAI instance
    """
    return _get_llm_client(model)
