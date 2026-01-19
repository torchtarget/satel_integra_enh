"""Connection management for Satel Integra panel."""

import asyncio
import logging
import time
from enum import Enum, auto

from satel_integra_enh.transport import (
    SatelBaseTransport,
    SatelEncryptedTransport,
    SatelPlainTransport,
)
from satel_integra_enh.const import (
    RECONNECT_INITIAL_DELAY,
    RECONNECT_MAX_DELAY,
    RECONNECT_BACKOFF_MULTIPLIER,
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CIRCUIT_BREAKER_RESET_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = auto()      # Normal operation - connections allowed
    OPEN = auto()        # Too many failures - connections blocked
    HALF_OPEN = auto()   # Testing if connection works again


class ConnectionCircuitBreaker:
    """Circuit breaker to prevent overwhelming ETHM-1 with connection attempts.

    When too many connection attempts fail in a row, the circuit breaker
    opens and blocks all connection attempts for a cooldown period.
    This prevents the scenario where rapid reconnection attempts
    permanently block the ETHM-1 ethernet port.
    """

    def __init__(
        self,
        failure_threshold: int = CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        reset_timeout: float = CIRCUIT_BREAKER_RESET_TIMEOUT,
    ):
        self._failure_threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._failure_count = 0
        self._state = CircuitBreakerState.CLOSED
        self._last_failure_time: float = 0
        self._opened_at: float = 0

    @property
    def state(self) -> CircuitBreakerState:
        """Get current state, checking if reset timeout has elapsed."""
        if self._state == CircuitBreakerState.OPEN:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self._reset_timeout:
                _LOGGER.info(
                    "Circuit breaker reset timeout elapsed (%.0fs) - moving to HALF_OPEN",
                    elapsed
                )
                self._state = CircuitBreakerState.HALF_OPEN
        return self._state

    def can_attempt(self) -> bool:
        """Check if a connection attempt is allowed."""
        state = self.state  # This updates state if timeout elapsed
        if state == CircuitBreakerState.OPEN:
            remaining = self._reset_timeout - (time.monotonic() - self._opened_at)
            _LOGGER.warning(
                "Circuit breaker OPEN - connection attempt blocked (%.0fs remaining)",
                remaining
            )
            return False
        return True

    def record_success(self):
        """Record a successful connection."""
        if self._state == CircuitBreakerState.HALF_OPEN:
            _LOGGER.info("Connection succeeded in HALF_OPEN - circuit breaker CLOSED")
        self._failure_count = 0
        self._state = CircuitBreakerState.CLOSED

    def record_failure(self):
        """Record a failed connection attempt."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._failure_count >= self._failure_threshold:
            if self._state != CircuitBreakerState.OPEN:
                _LOGGER.error(
                    "Circuit breaker OPEN after %d consecutive failures - "
                    "blocking connections for %.0fs to protect ETHM-1",
                    self._failure_count,
                    self._reset_timeout
                )
            self._state = CircuitBreakerState.OPEN
            self._opened_at = time.monotonic()
        else:
            _LOGGER.warning(
                "Connection failure %d/%d - circuit breaker still CLOSED",
                self._failure_count,
                self._failure_threshold
            )

    def get_backoff_delay(self) -> float:
        """Calculate exponential backoff delay based on failure count."""
        if self._failure_count == 0:
            return RECONNECT_INITIAL_DELAY

        delay = RECONNECT_INITIAL_DELAY * (
            RECONNECT_BACKOFF_MULTIPLIER ** (self._failure_count - 1)
        )
        delay = min(delay, RECONNECT_MAX_DELAY)

        _LOGGER.debug(
            "Backoff delay: %.1fs (failure count: %d)",
            delay,
            self._failure_count
        )
        return delay


class SatelConnection:
    """Manages TCP connection and I/O for the Satel Integra panel."""

    def __init__(
        self,
        host: str,
        port: int,
        reconnection_timeout: int = 15,
        integration_key: str | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._reconnection_timeout = reconnection_timeout
        self._connection: SatelBaseTransport = (
            SatelEncryptedTransport(host, port, integration_key)
            if integration_key
            else SatelPlainTransport(host, port)
        )

        # Circuit breaker to prevent overwhelming ETHM-1
        self._circuit_breaker = ConnectionCircuitBreaker()

    @property
    def connected(self) -> bool:
        """Return True if connected to the panel."""
        return self._connection.connected

    @property
    def closed(self) -> bool:
        """Return True if the connection is closed."""
        return self._connection.closed

    async def connect(self) -> bool:
        """Establish TCP connection with circuit breaker protection."""
        if self.closed:
            _LOGGER.debug("Connection is closed, skipping connection")
            return False

        # Check circuit breaker before attempting connection
        if not self._circuit_breaker.can_attempt():
            return False

        _LOGGER.debug("Connecting to Satel Integra at %s:%s...", self._host, self._port)

        if not await self._connection.connect():
            _LOGGER.warning("Unable to establish TCP connection.")
            self._circuit_breaker.record_failure()
            return False

        _LOGGER.debug("TCP connection established, verifying panel responsiveness...")

        if not await self._connection.check_connection():
            _LOGGER.warning("Panel not responsive or busy.")
            await self._connection.close()
            self._circuit_breaker.record_failure()
            return False

        else:
            _LOGGER.info("Connected to Satel Integra.")
            self._circuit_breaker.record_success()
            return True

    async def read_frame(self) -> bytes | None:
        """Read a raw frame from the panel."""
        return await self._connection.read_frame()

    async def send_frame(self, frame: bytes) -> bool:
        """Send a raw frame to the panel."""
        return await self._connection.send_frame(frame)

    async def ensure_connected(self) -> bool:
        """Reconnect automatically if disconnected, with exponential backoff.

        Uses circuit breaker pattern to prevent overwhelming the ETHM-1
        module with rapid reconnection attempts during outages.
        """
        if self.connected:
            return True

        while not self.connected and not self.closed:
            # Check if circuit breaker allows connection attempt
            if not self._circuit_breaker.can_attempt():
                # Wait for circuit breaker reset
                wait_time = min(
                    CIRCUIT_BREAKER_RESET_TIMEOUT,
                    self._circuit_breaker.get_backoff_delay()
                )
                _LOGGER.warning(
                    "Circuit breaker blocking connection - waiting %.0fs",
                    wait_time
                )
                await asyncio.sleep(wait_time)
                continue

            _LOGGER.debug("Not connected, attempting reconnection...")
            success = await self.connect()

            if not success:
                # Use exponential backoff delay
                delay = self._circuit_breaker.get_backoff_delay()
                _LOGGER.warning(
                    "Connection failed, retrying in %.1fs (exponential backoff)...",
                    delay
                )
                await asyncio.sleep(delay)

        return self.connected

    @property
    def circuit_breaker_state(self) -> CircuitBreakerState:
        """Get current circuit breaker state."""
        return self._circuit_breaker.state

    async def close(self) -> None:
        """Close the connection gracefully and clean up."""
        if self.closed or not self.connected:
            return  # already closed, avoid duplicate calls

        _LOGGER.debug("Closing connection...")
        await self._connection.close()
        _LOGGER.info("Connection closed cleanly.")
