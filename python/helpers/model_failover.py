"""
Model Failover Helper for Agent Zero
======================================
Provides automatic failover between LLM providers when the primary
model fails, times out, or hits rate limits.

Usage:
    from python.helpers.model_failover import call_with_failover

    result = await call_with_failover(
        messages=messages,
        primary_provider="openrouter",
        primary_model="anthropic/claude-sonnet-4",
        failover_chain="openai:gpt-4o, ollama:llama3",
    )
"""

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("agent-zero.failover")


# Error patterns that trigger failover (transient / retriable)
_FAILOVER_PATTERNS = [
    "rate_limit",
    "rate limit",
    "429",
    "quota",
    "overloaded",
    "service_unavailable",
    "503",
    "502",
    "timeout",
    "timed out",
    "connection",
    "temporarily unavailable",
    "capacity",
    "too many requests",
]


def _is_retriable(error: Exception) -> bool:
    """Check if an error is retriable (should trigger failover)."""
    error_str = str(error).lower()
    return any(pattern in error_str for pattern in _FAILOVER_PATTERNS)


def parse_failover_chain(chain_str: str) -> List[Tuple[str, str]]:
    """
    Parse a failover chain string into a list of (provider, model) tuples.

    Format: "provider:model, provider:model, ..."
    Example: "openrouter:anthropic/claude-sonnet-4, openai:gpt-4o, ollama:llama3"
    """
    if not chain_str or not chain_str.strip():
        return []

    results = []
    for entry in chain_str.split(","):
        entry = entry.strip()
        if ":" in entry:
            provider, model = entry.split(":", 1)
            results.append((provider.strip(), model.strip()))
        else:
            logger.warning(f"Invalid failover entry (no ':' separator): {entry}")
    return results


async def call_with_failover(
    call_fn: Callable,
    primary_provider: str,
    primary_model: str,
    failover_chain: str = "",
    failover_enabled: bool = True,
    max_retries_per_model: int = 1,
    base_backoff: float = 1.0,
    **call_kwargs,
) -> Any:
    """
    Call an LLM function with automatic failover.

    Args:
        call_fn: Async function that makes the LLM call.
                 Must accept (provider, model, **kwargs) signature.
        primary_provider: Primary LLM provider name.
        primary_model: Primary model name.
        failover_chain: Comma-separated "provider:model" pairs for fallback.
        failover_enabled: Whether failover is active.
        max_retries_per_model: Number of retries per model before moving on.
        base_backoff: Base backoff seconds between retries.
        **call_kwargs: Additional kwargs passed to call_fn.

    Returns:
        The result from whichever model succeeds.

    Raises:
        The last exception if all models fail.
    """
    # Build the full chain: primary first, then failover models
    models_to_try = [(primary_provider, primary_model)]
    if failover_enabled and failover_chain:
        models_to_try.extend(parse_failover_chain(failover_chain))

    last_error = None

    for idx, (provider, model) in enumerate(models_to_try):
        for attempt in range(max_retries_per_model):
            try:
                start_time = time.time()
                result = await call_fn(
                    provider=provider,
                    model=model,
                    **call_kwargs,
                )
                elapsed = time.time() - start_time

                if idx > 0:
                    logger.info(
                        f"Failover succeeded: {provider}:{model} "
                        f"(attempt {attempt + 1}, {elapsed:.1f}s)"
                    )

                return result

            except Exception as e:
                last_error = e
                elapsed = time.time() - start_time

                if not _is_retriable(e):
                    logger.error(
                        f"Non-retriable error from {provider}:{model}: {e}"
                    )
                    # Still try next model in chain for non-retriable errors
                    break

                logger.warning(
                    f"Retriable error from {provider}:{model} "
                    f"(attempt {attempt + 1}/{max_retries_per_model}, "
                    f"{elapsed:.1f}s): {e}"
                )

                if attempt < max_retries_per_model - 1:
                    wait_time = base_backoff * (2 ** attempt)
                    await asyncio.sleep(wait_time)

        if idx < len(models_to_try) - 1:
            next_provider, next_model = models_to_try[idx + 1]
            logger.info(
                f"Failing over from {provider}:{model} → "
                f"{next_provider}:{next_model}"
            )

    # All models failed
    logger.error(
        f"All {len(models_to_try)} models failed. "
        f"Last error: {last_error}"
    )
    raise last_error


class FailoverStats:
    """Track failover statistics for monitoring."""

    def __init__(self):
        self._stats: Dict[str, Dict[str, int]] = {}

    def record_success(self, provider: str, model: str):
        key = f"{provider}:{model}"
        if key not in self._stats:
            self._stats[key] = {"success": 0, "failure": 0, "failover_to": 0}
        self._stats[key]["success"] += 1

    def record_failure(self, provider: str, model: str):
        key = f"{provider}:{model}"
        if key not in self._stats:
            self._stats[key] = {"success": 0, "failure": 0, "failover_to": 0}
        self._stats[key]["failure"] += 1

    def record_failover(self, provider: str, model: str):
        key = f"{provider}:{model}"
        if key not in self._stats:
            self._stats[key] = {"success": 0, "failure": 0, "failover_to": 0}
        self._stats[key]["failover_to"] += 1

    def get_stats(self) -> Dict[str, Dict[str, int]]:
        return dict(self._stats)

    def reset(self):
        self._stats.clear()


# Global stats instance
failover_stats = FailoverStats()
