"""Static USD price estimates per 1M tokens (prompt / completion).

These are approximate list prices for reporting — not invoices.
Override via LLM_PRICE_<PROVIDER>_<MODEL>_IN / _OUT env vars later if needed.
"""

from __future__ import annotations

# (prompt_usd_per_1m, completion_usd_per_1m)
_PRICE_TABLE: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "o1-mini": (1.10, 4.40),
    "o3-mini": (1.10, 4.40),
    "claude-3-5-haiku-latest": (0.80, 4.00),
    "claude-3-5-sonnet-latest": (3.00, 15.00),
    "claude-3-haiku-20240307": (0.25, 1.25),
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
}

_DEFAULT = (1.00, 3.00)


def estimate_cost_usd(
    *,
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    key = (model or "").strip().lower()
    prompt_rate, completion_rate = _PRICE_TABLE.get(key, _DEFAULT)
    # Fuzzy match when exact key missing (e.g. dated Claude ids)
    if key not in _PRICE_TABLE:
        for name, rates in _PRICE_TABLE.items():
            if name in key or key in name:
                prompt_rate, completion_rate = rates
                break
    cost = (max(0, prompt_tokens) / 1_000_000.0) * prompt_rate
    cost += (max(0, completion_tokens) / 1_000_000.0) * completion_rate
    return round(cost, 8)


def estimate_tokens_from_text(text: str) -> int:
    """Rough fallback when the provider omits usage (~4 chars/token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)
