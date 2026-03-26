"""Shared formatting utilities for Claude Usage Tray."""


def fmt_tokens(n: int) -> str:
    """Format a token count with K/M/B/T abbreviation for readability."""
    for threshold, suffix in ((1_000_000_000_000, "T"), (1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if n >= threshold:
            v = n / threshold
            return f"{v:.1f}{suffix}" if v < 100 else f"{v:.0f}{suffix}"
    return str(n)
