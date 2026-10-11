"""Safe diagnostic logging helpers for transient Cloud troubleshooting."""

from __future__ import annotations

import logging
import os


_SENSITIVE_ENVIRONMENT_KEYS = (
    "GOOGLE_API_KEY",
    "TAVILY_API_KEY",
    "MARKETAUX_API_KEY",
)


def safe_exception_message(error: Exception) -> str:
    """Return exception text with configured provider secrets redacted."""
    message = str(error)
    for key in _SENSITIVE_ENVIRONMENT_KEYS:
        secret = os.environ.get(key)
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return message


def log_exception(logger: logging.Logger, stage: str, error: Exception) -> None:
    logger.error(
        "%s failed: exception_type=%s message=%s",
        stage,
        type(error).__name__,
        safe_exception_message(error),
    )
