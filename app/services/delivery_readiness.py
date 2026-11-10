"""Guard workflow processing until an email delivery integration exists."""

_requires_reconciliation = False


def close_for_reconciliation() -> None:
    """Record an uncertain side effect and retain the default-closed gate."""
    global _requires_reconciliation
    _requires_reconciliation = True


def requires_reconciliation() -> bool:
    """Report whether this process has observed an uncertain outcome."""
    return _requires_reconciliation


def is_delivery_ready() -> bool:
    """Return whether a verified email delivery integration is available."""
    return False
