"""Queue class for Satel Integra"""

import asyncio
from collections.abc import Callable
from collections import deque

import logging
import time
from collections.abc import Awaitable

from satel_integra_enh.commands import SatelReadCommand
from satel_integra_enh.const import (
    MESSAGE_RESPONSE_TIMEOUT,
    MIN_REQUEST_INTERVAL,
    MIN_FAILURE_DELAY,
    RATE_LIMIT_MAX_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
    REQUEST_FAILURE_THRESHOLD,
    REQUEST_COOLDOWN_PERIOD,
)
from satel_integra_enh.messages import SatelReadMessage, SatelWriteMessage

_LOGGER = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter using sliding window algorithm.

    Prevents overwhelming the ETHM-1 module by limiting how many
    requests can be sent within a time window.
    """

    def __init__(
        self,
        max_requests: int = RATE_LIMIT_MAX_REQUESTS,
        window_seconds: float = RATE_LIMIT_WINDOW_SECONDS,
        min_interval: float = MIN_REQUEST_INTERVAL,
    ):
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._min_interval = min_interval
        self._request_times: deque[float] = deque()
        self._last_request_time: float = 0

    def _cleanup_old_requests(self):
        """Remove requests outside the sliding window."""
        cutoff = time.monotonic() - self._window_seconds
        while self._request_times and self._request_times[0] < cutoff:
            self._request_times.popleft()

    async def acquire(self) -> None:
        """Wait until a request is allowed, then record it.

        This ensures:
        1. Minimum interval between consecutive requests
        2. Maximum requests within the sliding window
        """
        now = time.monotonic()

        # Enforce minimum interval between requests
        time_since_last = now - self._last_request_time
        if time_since_last < self._min_interval:
            wait_time = self._min_interval - time_since_last
            _LOGGER.debug(
                "Rate limiter: waiting %.2fs for minimum interval",
                wait_time
            )
            await asyncio.sleep(wait_time)
            now = time.monotonic()

        # Enforce sliding window limit
        self._cleanup_old_requests()
        while len(self._request_times) >= self._max_requests:
            # Wait until oldest request falls out of window
            oldest = self._request_times[0]
            wait_time = (oldest + self._window_seconds) - now + 0.1
            if wait_time > 0:
                _LOGGER.warning(
                    "Rate limiter: at capacity (%d/%d requests in window) - waiting %.2fs",
                    len(self._request_times),
                    self._max_requests,
                    wait_time
                )
                await asyncio.sleep(wait_time)
                now = time.monotonic()
            self._cleanup_old_requests()

        # Record this request
        self._request_times.append(now)
        self._last_request_time = now

    def get_stats(self) -> dict:
        """Get rate limiter statistics."""
        self._cleanup_old_requests()
        return {
            "requests_in_window": len(self._request_times),
            "max_requests": self._max_requests,
            "window_seconds": self._window_seconds,
        }


class RequestCircuitBreaker:
    """Circuit breaker for request failures.

    If too many consecutive requests fail (timeout/error), enters
    cooldown mode to give the ETHM-1 time to recover.
    """

    def __init__(
        self,
        failure_threshold: int = REQUEST_FAILURE_THRESHOLD,
        cooldown_period: float = REQUEST_COOLDOWN_PERIOD,
    ):
        self._failure_threshold = failure_threshold
        self._cooldown_period = cooldown_period
        self._consecutive_failures = 0
        self._cooldown_until: float = 0

    @property
    def in_cooldown(self) -> bool:
        """Check if we're in cooldown period."""
        if self._cooldown_until == 0:
            return False
        if time.monotonic() >= self._cooldown_until:
            _LOGGER.info("Request cooldown period ended - resuming normal operation")
            self._cooldown_until = 0
            self._consecutive_failures = 0
            return False
        return True

    @property
    def cooldown_remaining(self) -> float:
        """Get remaining cooldown time in seconds."""
        if not self.in_cooldown:
            return 0
        return self._cooldown_until - time.monotonic()

    def record_success(self):
        """Record a successful request."""
        if self._consecutive_failures > 0:
            _LOGGER.debug(
                "Request succeeded - resetting failure count (was %d)",
                self._consecutive_failures
            )
        self._consecutive_failures = 0

    def record_failure(self):
        """Record a failed request."""
        self._consecutive_failures += 1
        _LOGGER.warning(
            "Request failure %d/%d",
            self._consecutive_failures,
            self._failure_threshold
        )

        if self._consecutive_failures >= self._failure_threshold:
            self._cooldown_until = time.monotonic() + self._cooldown_period
            _LOGGER.error(
                "Request circuit breaker triggered after %d failures - "
                "entering %.0fs cooldown to protect ETHM-1",
                self._consecutive_failures,
                self._cooldown_period
            )

    async def wait_if_needed(self) -> bool:
        """Wait for cooldown if needed. Returns True if waited."""
        if self.in_cooldown:
            remaining = self.cooldown_remaining
            _LOGGER.warning(
                "Request circuit breaker active - waiting %.1fs",
                remaining
            )
            await asyncio.sleep(remaining)
            return True
        return False


class QueuedMessage:
    def __init__(self, message: SatelWriteMessage, wait_for_result: bool):
        self.message = message
        self.return_result = wait_for_result

        self.processed_future: asyncio.Future[SatelReadMessage] = (
            asyncio.get_running_loop().create_future()
        )

        # Determine the expected response
        self.expected_result_command = (
            message.cmd
            if getattr(message.cmd, "expects_same_cmd_response", False)
            else SatelReadCommand.RESULT
        )


class SatelMessageQueue:
    """Queue ensuring write commands are sent sequentially and wait for a result.

    Includes rate limiting and circuit breaker protection to prevent
    overwhelming the ETHM-1 module.
    """

    def __init__(self, send_func: Callable[[SatelWriteMessage], Awaitable[None]]):
        """
        Args:
            send_func: coroutine function to send a frame, e.g. AsyncSatel._send_data
        """
        self._send_func: Callable[[SatelWriteMessage], Awaitable[None]] = send_func
        self._queue: asyncio.Queue[QueuedMessage] = asyncio.Queue()

        self._current_message: QueuedMessage | None = None
        self._process_task: asyncio.Task | None = None
        self._closed = False

        # Rate limiting and circuit breaker for ETHM-1 protection
        self._rate_limiter = RateLimiter()
        self._circuit_breaker = RequestCircuitBreaker()

    async def start(self):
        """Start processing the queue."""
        if self._process_task:
            return  # already running
        self._process_task = asyncio.create_task(self._process_queue())

    @property
    def in_cooldown(self) -> bool:
        """Check if request circuit breaker is in cooldown."""
        return self._circuit_breaker.in_cooldown

    def get_stats(self) -> dict:
        """Get queue statistics including rate limiter stats."""
        return {
            "rate_limiter": self._rate_limiter.get_stats(),
            "circuit_breaker_cooldown": self._circuit_breaker.in_cooldown,
            "cooldown_remaining": self._circuit_breaker.cooldown_remaining,
        }

    async def stop(self):
        """Stop the queue gracefully."""
        self._closed = True
        if self._process_task:
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass
            self._process_task = None

    async def add_message(self, msg: SatelWriteMessage, wait_for_result: bool = False):
        """
        Queue a message. If wait_for_result is True, wait for and return the result.
        Otherwise, just queue the message and return None
        """
        if self._closed:
            raise RuntimeError("Queue is stopped")

        _LOGGER.debug("Queueing message: %s", msg)

        queued = QueuedMessage(msg, wait_for_result)
        await self._queue.put(queued)

        if wait_for_result:
            return await queued.processed_future
        return None

    async def _process_queue(self) -> None:
        """Process queued commands sequentially."""
        _LOGGER.debug("Message queue worker started")

        while not self._closed:
            try:
                self._current_message = await self._get_next_message()
                if self._current_message is None:
                    continue

                await self._send_and_wait_response(self._current_message)

            except Exception as e:
                _LOGGER.exception("Unexpected error in queue processing: %s", e)

            finally:
                self._current_message = None

        _LOGGER.debug("Command queue worker stopped")

    async def _get_next_message(self) -> QueuedMessage | None:
        """Get next message from queue with timeout."""
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            return None

    async def _send_and_wait_response(self, queued: QueuedMessage) -> None:
        """Send a queued message and wait for the panel RESULT.

        Includes rate limiting and circuit breaker protection.
        """
        # Wait for circuit breaker cooldown if needed
        await self._circuit_breaker.wait_if_needed()

        # Apply rate limiting before sending
        await self._rate_limiter.acquire()

        try:
            _LOGGER.debug("Sending message: %s", queued.message)
            await self._send_func(queued.message)
        except Exception as exc:
            _LOGGER.exception("Error while sending message: %s", exc)
            self._circuit_breaker.record_failure()
            if not queued.processed_future.done():
                queued.processed_future.set_exception(exc)

            # Add extra delay after failure
            await asyncio.sleep(MIN_FAILURE_DELAY)
            return

        # Wait for the RESULT (the future will be completed by on_message_received).
        try:
            await asyncio.wait_for(
                queued.processed_future, timeout=MESSAGE_RESPONSE_TIMEOUT
            )
            # Success - reset circuit breaker
            self._circuit_breaker.record_success()
        except asyncio.TimeoutError:
            _LOGGER.error(
                "No response received from panel within %ss", MESSAGE_RESPONSE_TIMEOUT
            )
            self._circuit_breaker.record_failure()
            # Add extra delay after timeout
            await asyncio.sleep(MIN_FAILURE_DELAY)
            return

    def on_message_received(self, result: SatelReadMessage):
        """Called by AsyncSatel when a RESULT message is received."""
        if not self._current_message:
            # Received result but no message is being processed, standard read message due to monitoring
            return

        if self._current_message.processed_future.done():
            _LOGGER.warning(
                "Received result but future is already done (likely timed out)"
            )
            return

        if self._current_message.expected_result_command != result.cmd:
            # Only warn if this looks like it could be a response (not a monitoring message)
            # Monitoring messages (zones violated, outputs, partitions, etc.) are expected
            # and should be silently ignored by the queue
            potential_responses = {
                SatelReadCommand.RESULT,
                SatelReadCommand.READ_DEVICE_NAME,
                SatelReadCommand.READ_ZONE_TEMPERATURE,
            }
            if result.cmd in potential_responses:
                _LOGGER.warning(
                    "Received %s but expected %s",
                    result.cmd,
                    self._current_message.expected_result_command
                )
            return

        self._current_message.processed_future.set_result(result)
