"""
Structured logging using Python's standard logging module.

Simple, production-grade JSON logging with structured fields.
Uses Python's logging (battle-tested), adds JSON formatting.
"""

import json
import logging
import sys
from typing import Any, Dict, Optional


class JsonFormatter(logging.Formatter):
    """Format log records as JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        """Convert LogRecord to JSON."""
        log_dict = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields (correlation_id, node, etc.)
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            log_dict.update(record.extra)

        # Add exception traceback if present
        if record.exc_info:
            log_dict["exception"] = self.formatException(record.exc_info)

        try:
            return json.dumps(log_dict)
        except (TypeError, ValueError):
            # Fallback if something isn't JSON-serializable
            return json.dumps({**log_dict, "error": "Failed to serialize some fields"})


def setup_structured_logging(
    name: str = "app",
    level: int = logging.INFO,
    format_json: bool = True,
    output: str = "stdout",
) -> logging.Logger:
    """
    Configure structured logging.

    Args:
        name: Logger name (typically __name__ or module name)
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        format_json: If True, output JSON; else plain text
        output: "stdout", "stderr", or file path

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Remove any existing handlers
    logger.handlers = []

    # Choose output handler
    if output == "stdout":
        handler = logging.StreamHandler(sys.stdout)
    elif output == "stderr":
        handler = logging.StreamHandler(sys.stderr)
    else:
        # Assume it's a file path
        handler = logging.FileHandler(output)

    # Choose formatter
    if format_json:
        formatter = JsonFormatter()
    else:
        # Plain text format
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


class MockLogger:
    """
    Mock logger for testing (no I/O, just tracks calls).

    Use in tests to verify what was logged without touching disk/stdout.
    """

    def __init__(self):
        self.info_calls: list[str] = []
        self.error_calls: list[str] = []
        self.debug_calls: list[str] = []
        self.warning_calls: list[str] = []
        self.all_calls: list[str] = []

    def info(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log info level."""
        self.info_calls.append(message)
        self.all_calls.append(f"INFO: {message}")

    def error(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log error level."""
        self.error_calls.append(message)
        self.all_calls.append(f"ERROR: {message}")

    def debug(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log debug level."""
        self.debug_calls.append(message)
        self.all_calls.append(f"DEBUG: {message}")

    def warning(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log warning level."""
        self.warning_calls.append(message)
        self.all_calls.append(f"WARNING: {message}")

    def exception(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log exception level."""
        self.error_calls.append(message)
        self.all_calls.append(f"EXCEPTION: {message}")
