"""
Token counting utility for LLM prompts.

Estimates token count before sending to LLM to prevent exceeding context limits.
Uses tiktoken (OpenAI's tokenizer) if available, falls back to heuristic.

PYTHON CONCEPT: Optional imports with fallback
- Try to import specialized library (tiktoken)
- Fall back to heuristic if not available
- Graceful degradation: still works without tiktoken
"""

import logging
from typing import Literal

logger = logging.getLogger(__name__)

# Try to import tiktoken (OpenAI's tokenizer)
try:
    import tiktoken

    _tiktoken_available = True
except ImportError:
    _tiktoken_available = False

# Token limits per model (context window safe margins)
# Using 90% of actual limit to be conservative
TOKEN_LIMITS = {
    "gpt-4-turbo": 115000,  # 128k limit, 90% = 115k
    "gpt-4": 7200,  # 8k limit, 90% = 7.2k
    "gpt-3.5-turbo": 3600,  # 4k limit, 90% = 3.6k
}


def _count_tokens_tiktoken(text: str, model: str) -> int:
    """
    Count tokens using OpenAI's tiktoken tokenizer.

    Accurate tokenization using the same method as OpenAI API.

    Args:
        text: Prompt text
        model: Model name (gpt-4-turbo, gpt-4, etc.)

    Returns:
        Token count

    Raises:
        ValueError: If model encoding not found
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
        tokens = encoding.encode(text)
        return len(tokens)
    except KeyError:
        # Model not found in tiktoken, try by encoding name
        try:
            encoding = tiktoken.get_encoding("cl100k_base")  # Default for GPT-4
            tokens = encoding.encode(text)
            return len(tokens)
        except Exception as e:
            logger.warning(
                f"tiktoken tokenization failed for model {model}: {e}. Using heuristic."
            )
            return _count_tokens_heuristic(text)


def _count_tokens_heuristic(text: str) -> int:
    """
    Estimate tokens using simple heuristic (4 chars ≈ 1 token).

    Fast fallback when tiktoken unavailable.
    Accurate to within ~15% for most prompts.

    Args:
        text: Prompt text

    Returns:
        Estimated token count
    """
    # Industry standard: ~4 characters per token
    # Accounts for word boundaries and special tokens
    return len(text) // 4


def count_tokens(text: str, model: str) -> int:
    """
    Count tokens in prompt text.

    Uses tiktoken for accuracy if available, falls back to heuristic.

    Args:
        text: Prompt text to tokenize
        model: Model name (gpt-4-turbo, gpt-4, gpt-3.5-turbo, etc.)

    Returns:
        Token count (integer)

    Examples:
        >>> text = "Hello, how are you?"
        >>> count = count_tokens(text, "gpt-4-turbo")
        >>> assert count > 0
    """
    if not isinstance(text, str):
        return 0

    if _tiktoken_available:
        return _count_tokens_tiktoken(text, model)
    else:
        return _count_tokens_heuristic(text)


def validate_prompt_tokens(
    prompt: str, model: str, warn_threshold: float = 0.75
) -> tuple[int, bool]:
    """
    Check if prompt token count is within safe limits.

    Logs warning if approaching limit (warn_threshold * limit).

    Args:
        prompt: Prompt text
        model: Model name
        warn_threshold: Log warning if tokens > (warn_threshold * limit)
                       Default 0.75 means warn at 75% of limit

    Returns:
        Tuple of (token_count, is_safe)
        - token_count: Actual token count
        - is_safe: True if under limit, False if exceeds

    Examples:
        >>> prompt = "Hello world" * 100
        >>> count, safe = validate_prompt_tokens(prompt, "gpt-4-turbo")
        >>> assert isinstance(count, int)
        >>> assert isinstance(safe, bool)
    """
    token_count = count_tokens(prompt, model)
    limit = TOKEN_LIMITS.get(model)

    if limit is None:
        logger.debug(f"No token limit defined for model {model}")
        return token_count, True

    is_safe = token_count <= limit

    # Warn if approaching limit
    if token_count > (warn_threshold * limit):
        logger.warning(
            f"Prompt approaching token limit for {model}: "
            f"{token_count:,} / {limit:,} tokens ({100 * token_count / limit:.1f}%)",
            extra={"model": model, "token_count": token_count, "limit": limit},
        )

    # Error if exceeds limit
    if not is_safe:
        logger.error(
            f"Prompt exceeds token limit for {model}: "
            f"{token_count:,} / {limit:,} tokens",
            extra={"model": model, "token_count": token_count, "limit": limit},
        )

    return token_count, is_safe
