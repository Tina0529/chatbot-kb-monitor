"""Retry logic with exponential backoff for KB monitoring."""

import asyncio
import time
from enum import Enum
from typing import Optional, Callable, Any, TypeVar, Coroutine
from dataclasses import dataclass

from utils import get_logger, AppConfig


T = TypeVar('T')


class ErrorType(Enum):
    """Classification of error types for retry decisions."""

    # Permanent errors - should not retry
    AUTHENTICATION_FAILED = "authentication_failed"
    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"
    INVALID_INPUT = "invalid_input"

    # Temporary errors - safe to retry
    NETWORK_TIMEOUT = "network_timeout"
    RATE_LIMITED = "rate_limited"
    SERVER_ERROR = "server_error"
    BROWSER_CRASHED = "browser_crashed"
    UNKNOWN = "unknown"


@dataclass
class RetryResult:
    """Result of a retry attempt."""
    success: bool
    attempts: int
    total_time: float
    error: Optional[str] = None


class RetryHandler:
    """
    Handles retry logic with exponential backoff.

    Classifies errors and determines whether retries are appropriate.
    """

    # Error messages that indicate permanent failures
    PERMANENT_ERROR_PATTERNS = [
        "authentication",
        "auth",
        "permission",
        "forbidden",
        "401",
        "403",
        "not found",
        "404",
        "invalid",
    ]

    # Error messages that indicate temporary failures
    TEMPORARY_ERROR_PATTERNS = [
        "timeout",
        "timed out",
        "rate limit",
        "429",
        "500",
        "502",
        "503",
        "504",
        "connection",
        "network",
        "target closed",
        "browser",
        "playwright",
    ]

    def __init__(self, config: AppConfig):
        """
        Initialize retry handler.

        Args:
            config: Application configuration
        """
        self.config = config
        self.logger = get_logger("retry_handler")

        self.max_attempts = config.monitoring.retry.max_attempts
        self.backoff_base = config.monitoring.retry.backoff_base
        self.initial_delay = config.monitoring.retry.initial_delay

    def classify_error(self, error: Exception) -> ErrorType:
        """
        Classify an error to determine retry strategy.

        Args:
            error: Exception to classify

        Returns:
            ErrorType classification
        """
        error_message = str(error).lower()
        error_type_name = type(error).__name__.lower()

        # Check for permanent errors
        for pattern in self.PERMANENT_ERROR_PATTERNS:
            if pattern in error_message or pattern in error_type_name:
                if "auth" in pattern:
                    return ErrorType.AUTHENTICATION_FAILED
                if "permission" in pattern or "forbidden" in pattern or "403" in pattern:
                    return ErrorType.PERMISSION_DENIED
                if "not found" in pattern or "404" in pattern:
                    return ErrorType.NOT_FOUND
                return ErrorType.INVALID_INPUT

        # Check for temporary errors
        for pattern in self.TEMPORARY_ERROR_PATTERNS:
            if pattern in error_message or pattern in error_type_name:
                if "timeout" in pattern:
                    return ErrorType.NETWORK_TIMEOUT
                if "rate limit" in pattern or "429" in pattern:
                    return ErrorType.RATE_LIMITED
                if "500" in pattern or "502" in pattern or "503" in pattern or "504" in pattern:
                    return ErrorType.SERVER_ERROR
                if "browser" in pattern or "playwright" in pattern or "target closed" in pattern:
                    return ErrorType.BROWSER_CRASHED
                return ErrorType.NETWORK_TIMEOUT

        return ErrorType.UNKNOWN

    def should_retry(self, error: Exception, attempt: int) -> bool:
        """
        Determine if an operation should be retried.

        Args:
            error: Exception that occurred
            attempt: Current attempt number (1-indexed)

        Returns:
            True if operation should be retried
        """
        if attempt >= self.max_attempts:
            self.logger.warning(f"Max retry attempts ({self.max_attempts}) reached")
            return False

        error_type = self.classify_error(error)

        # Don't retry permanent errors
        if error_type in (
            ErrorType.AUTHENTICATION_FAILED,
            ErrorType.PERMISSION_DENIED,
            ErrorType.NOT_FOUND,
            ErrorType.INVALID_INPUT,
        ):
            self.logger.info(f"Permanent error ({error_type.value}): not retrying")
            return False

        # Retry temporary errors
        self.logger.debug(f"Temporary error ({error_type.value}): will retry")
        return True

    def get_backoff_delay(self, attempt: int) -> float:
        """
        Calculate exponential backoff delay.

        Args:
            attempt: Attempt number (1-indexed)

        Returns:
            Delay in seconds
        """
        # Exponential backoff: base_delay * (backoff_base ^ (attempt - 1))
        delay = self.initial_delay * (self.backoff_base ** (attempt - 1))
        return min(delay, 60)  # Cap at 60 seconds

    async def retry_async(
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        **kwargs: Any
    ) -> RetryResult:
        """
        Retry an async function with exponential backoff.

        Args:
            func: Async function to retry
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            RetryResult with success status and result
        """
        start_time = time.time()
        last_error = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                self.logger.debug(f"Attempt {attempt}/{self.max_attempts}")
                result = await func(*args, **kwargs)

                elapsed = time.time() - start_time
                if attempt > 1:
                    self.logger.info(f"Success on attempt {attempt} after {elapsed:.1f}s")

                return RetryResult(
                    success=True,
                    attempts=attempt,
                    total_time=elapsed
                )

            except Exception as e:
                last_error = e
                self.logger.warning(f"Attempt {attempt} failed: {e}")

                if not self.should_retry(e, attempt):
                    break

                # Calculate and wait backoff delay
                delay = self.get_backoff_delay(attempt)
                self.logger.debug(f"Waiting {delay:.1f}s before retry...")
                await asyncio.sleep(delay)

        # All attempts failed
        elapsed = time.time() - start_time
        error_type = self.classify_error(last_error) if last_error else ErrorType.UNKNOWN

        return RetryResult(
            success=False,
            attempts=self.max_attempts,
            total_time=elapsed,
            error=f"{error_type.value}: {str(last_error)}"
        )

    def retry_sync(
        self,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any
    ) -> RetryResult:
        """
        Retry a synchronous function with exponential backoff.

        Args:
            func: Function to retry
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            RetryResult with success status and result
        """
        start_time = time.time()
        last_error = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                self.logger.debug(f"Attempt {attempt}/{self.max_attempts}")
                result = func(*args, **kwargs)

                elapsed = time.time() - start_time
                if attempt > 1:
                    self.logger.info(f"Success on attempt {attempt} after {elapsed:.1f}s")

                return RetryResult(
                    success=True,
                    attempts=attempt,
                    total_time=elapsed
                )

            except Exception as e:
                last_error = e
                self.logger.warning(f"Attempt {attempt} failed: {e}")

                if not self.should_retry(e, attempt):
                    break

                # Calculate and wait backoff delay
                delay = self.get_backoff_delay(attempt)
                self.logger.debug(f"Waiting {delay:.1f}s before retry...")
                time.sleep(delay)

        # All attempts failed
        elapsed = time.time() - start_time
        error_type = self.classify_error(last_error) if last_error else ErrorType.UNKNOWN

        return RetryResult(
            success=False,
            attempts=self.max_attempts,
            total_time=elapsed,
            error=f"{error_type.value}: {str(last_error)}"
        )


def with_retry(config: AppConfig):
    """
    Decorator to add retry logic to a function.

    Args:
        config: Application configuration

    Returns:
        Decorator function
    """
    handler = RetryHandler(config)

    def decorator(func: Callable[..., T]) -> Callable[..., RetryResult]:
        import asyncio
        import inspect

        if asyncio.iscoroutinefunction(func):
            async def async_wrapper(*args, **kwargs):
                return await handler.retry_async(func, *args, **kwargs)
            return async_wrapper
        else:
            def sync_wrapper(*args, **kwargs):
                return handler.retry_sync(func, *args, **kwargs)
            return sync_wrapper

    return decorator
