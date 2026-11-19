"""HTTP client extensions."""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

_DEFAULT_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})


class _RetryableStatusError(Exception):
    """Internal exception used to trigger tenacity retries on status codes."""

    def __init__(self, response: httpx.Response):
        super().__init__(f"retryable status: {response.status_code}")
        self.response = response


def _is_retryable_error(exc: BaseException) -> bool:
    """Decide whether an exception is retryable."""
    if isinstance(exc, _RetryableStatusError):
        return True
    return isinstance(exc, (httpx.NetworkError, httpx.TimeoutException, httpx.RemoteProtocolError))


class RetryAsyncClient(httpx.AsyncClient):
    """Async HTTP client with retry support.

    Subclasses ``httpx.AsyncClient`` and adds tenacity exponential-backoff retries to ``request``.
    By default retries are only enabled for idempotent methods, to avoid resubmitting non-idempotent requests such as sending SMS or submitting forms.

    Attributes:
            retry_attempts: Maximum number of attempts (including the first request).
            retry_wait_min: Minimum exponential-backoff wait, in seconds.
            retry_wait_max: Maximum exponential-backoff wait, in seconds.
            retry_wait_multiplier: Exponential-backoff multiplier.
            retry_statuses: Set of HTTP status codes that trigger a retry.
            retry_non_idempotent: Whether to allow retries for non-idempotent methods.
    """

    def __init__(
        self,
        *args: Any,
        retry_attempts: int = 3,
        retry_wait_min: float = 0.2,
        retry_wait_max: float = 2.0,
        retry_wait_multiplier: float = 0.5,
        retry_statuses: Collection[int] = _DEFAULT_RETRY_STATUSES,
        retry_non_idempotent: bool = False,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.retry_attempts = retry_attempts
        self.retry_wait_min = retry_wait_min
        self.retry_wait_max = retry_wait_max
        self.retry_wait_multiplier = retry_wait_multiplier
        self.retry_statuses = frozenset(retry_statuses)
        self.retry_non_idempotent = retry_non_idempotent

    async def request(
        self, method: str, url: str | httpx.URL, *args: Any, **kwargs: Any
    ) -> httpx.Response:
        """Send the request, retrying automatically according to the policy."""
        method_upper = method.upper()
        allow_retry = self.retry_non_idempotent or method_upper in _IDEMPOTENT_METHODS
        if self.retry_attempts <= 1 or not allow_retry:
            return await super().request(method, url, *args, **kwargs)

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self.retry_attempts),
                wait=wait_exponential(
                    multiplier=self.retry_wait_multiplier,
                    min=self.retry_wait_min,
                    max=self.retry_wait_max,
                ),
                retry=retry_if_exception(_is_retryable_error),
                reraise=True,
            ):
                with attempt:
                    response = await super().request(method, url, *args, **kwargs)
                    if response.status_code in self.retry_statuses:
                        raise _RetryableStatusError(response)
                    return response
        except _RetryableStatusError as exc:
            return exc.response

        # Should never be reached in theory; kept as a fallback to satisfy type checking.
        return await super().request(method, url, *args, **kwargs)
