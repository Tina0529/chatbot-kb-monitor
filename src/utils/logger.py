"""Logging configuration for the KB monitor application."""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional

from .config_loader import AppConfig, get_config_dir


class ColoredFormatter(logging.Formatter):
    """Colored console log formatter for better readability."""

    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
    }
    RESET = '\033[0m'

    def format(self, record):
        # Add color to levelname
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.RESET}"
        return super().format(record)


class SensitiveDataFilter(logging.Filter):
    """Filter to prevent sensitive data from being logged."""

    SENSITIVE_PATTERNS = [
        'password',
        'token',
        'secret',
        'credential',
        'webhook',
        'authorization',
        'bearer',
    ]

    def filter(self, record):
        # Redact sensitive data in log messages
        msg = record.getMessage()
        lower_msg = msg.lower()

        for pattern in self.SENSITIVE_PATTERNS:
            if pattern in lower_msg:
                # Replace sensitive values with asterisks
                record.msg = self._redact_value(record.msg)
                if record.args:
                    record.args = tuple(
                        self._redact_value(str(arg)) if isinstance(arg, str) else arg
                        for arg in record.args
                    )
        return True

    def _redact_value(self, value: str) -> str:
        """Redact sensitive values in a string."""
        import re

        # Pattern to match key: value or key=value pairs
        pattern = r'["\']?([a-zA-Z_]+(?:password|token|secret|credential|webhook|authorization|bearer)["\']?)\s*[:=]\s*["\']?([^"\':\s,}]+)'

        def replace_match(match):
            key = match.group(1)
            value = match.group(2)
            # Show first 2 and last 2 characters
            if len(value) > 4:
                redacted = f"{value[:2]}...{value[-2:]}"
            else:
                redacted = "*" * len(value)
            return f'{key}: {redacted}'

        return re.sub(pattern, replace_match, value, flags=re.IGNORECASE)


def setup_logger(
    name: str = "kb_monitor",
    config: Optional[AppConfig] = None,
    log_file: Optional[Path] = None,
    level: Optional[str] = None
) -> logging.Logger:
    """
    Set up logging with file and console handlers.

    Args:
        name: Logger name
        config: Application configuration (optional)
        log_file: Specific log file path (optional, overrides config)
        level: Log level (optional, overrides config)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    # Determine log level
    if level:
        log_level = getattr(logging, level.upper(), logging.INFO)
    elif config:
        log_level = getattr(logging, config.logging.level, logging.INFO)
    else:
        log_level = logging.INFO

    logger.setLevel(log_level)

    # Create formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    colored_formatter = ColoredFormatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(colored_formatter)
    logger.addHandler(console_handler)

    # File handler with rotation
    if config or log_file:
        if log_file:
            log_path = log_file
            max_bytes = 10 * 1024 * 1024  # 10MB default
            backup_count = 5
        else:
            base_dir = get_config_dir().parent
            log_path = base_dir / config.logging.file
            max_bytes = config.logging.max_bytes
            backup_count = config.logging.backup_count

        # Ensure log directory exists
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Add sensitive data filter
    sensitive_filter = SensitiveDataFilter()
    logger.addFilter(sensitive_filter)

    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get an existing logger instance.

    Args:
        name: Logger name (defaults to 'kb_monitor')

    Returns:
        Logger instance
    """
    if name is None:
        name = "kb_monitor"
    return logging.getLogger(name)


class LoggerContext:
    """Context manager for temporary logger configuration changes."""

    def __init__(self, logger: logging.Logger, level: int):
        self.logger = logger
        self.new_level = level
        self.old_level = None

    def __enter__(self):
        self.old_level = self.logger.level
        self.logger.setLevel(self.new_level)
        return self.logger

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.old_level is not None:
            self.logger.setLevel(self.old_level)
        return False


def log_function_call(logger: Optional[logging.Logger] = None):
    """
    Decorator to log function calls with parameters.

    Args:
        logger: Logger instance to use (creates new if None)
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            if logger is None:
                func_logger = get_logger(func.__module__)
            else:
                func_logger = logger

            func_logger.debug(
                f"Calling {func.__name__} with args={args}, kwargs={kwargs}"
            )
            try:
                result = func(*args, **kwargs)
                func_logger.debug(f"{func.__name__} completed successfully")
                return result
            except Exception as e:
                func_logger.error(f"{func.__name__} raised {type(e).__name__}: {e}")
                raise

        return wrapper
    return decorator
