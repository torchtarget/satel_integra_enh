"""Constants for the Satel Integra integration."""

FRAME_START = bytes([0xFE, 0xFE])
FRAME_END = bytes([0xFE, 0x0D])

FRAME_SPECIAL_BYTES = bytes([0xFE])
FRAME_SPECIAL_BYTES_REPLACEMENT = bytes([0xFE, 0xF0])

MESSAGE_RESPONSE_TIMEOUT = 5

# =============================================================================
# Rate Limiting & Circuit Breaker Constants
# These protect the ETHM-1 module from being overwhelmed by too many requests
# =============================================================================

# Minimum delay between consecutive requests (seconds)
# ETHM-1 needs time to process each request - too fast = overwhelm
MIN_REQUEST_INTERVAL = 0.5

# Minimum delay after a failed request before retrying (seconds)
MIN_FAILURE_DELAY = 2.0

# Maximum requests allowed in a sliding window
RATE_LIMIT_MAX_REQUESTS = 10
RATE_LIMIT_WINDOW_SECONDS = 10.0

# =============================================================================
# Connection Circuit Breaker
# Prevents rapid reconnection attempts that can lock out the ETHM-1
# =============================================================================

# Initial delay before first reconnection attempt (seconds)
RECONNECT_INITIAL_DELAY = 5.0

# Maximum delay between reconnection attempts (seconds)
RECONNECT_MAX_DELAY = 300.0  # 5 minutes

# Multiplier for exponential backoff
RECONNECT_BACKOFF_MULTIPLIER = 2.0

# Number of consecutive failures before circuit breaker opens
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5

# How long the circuit breaker stays open (seconds)
CIRCUIT_BREAKER_RESET_TIMEOUT = 300.0  # 5 minutes

# =============================================================================
# Request Circuit Breaker
# Stops all requests if ETHM-1 appears overwhelmed
# =============================================================================

# Number of consecutive request timeouts before stopping
REQUEST_FAILURE_THRESHOLD = 3

# Cooldown period after request failures (seconds)
REQUEST_COOLDOWN_PERIOD = 60.0
