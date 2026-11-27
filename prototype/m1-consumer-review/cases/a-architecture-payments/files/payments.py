"""Fixture payment adapter: the only place that may talk to the PSP."""
from __future__ import annotations


class PaymentDeclined(RuntimeError):
    """Raised when the PSP declines the authorization."""


def authorize(amount_minor: int, currency: str, token: str) -> str:
    """Return an authorization id; never persists card data."""
    if amount_minor <= 0:
        raise ValueError("amount_minor must be positive")
    if not token:
        raise PaymentDeclined("missing payment token")
    return f"auth-{currency.lower()}-{amount_minor}"
