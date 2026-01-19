# Changelog

## [0.6.3] - 2026-01-19

### Added
-   **Connection Circuit Breaker** - Prevents overwhelming ETHM-1 with rapid reconnection attempts
    -   Opens after 5 consecutive connection failures
    -   Blocks connections for 5 minutes to protect the ETHM-1 module
    -   HALF_OPEN state tests if connections work again
-   **Exponential Backoff for Reconnections** - Gradually increases delay between retries
    -   Initial delay: 5 seconds
    -   Maximum delay: 5 minutes (300s)
    -   Multiplier: 2x per failure
-   **Request Rate Limiter** - Prevents request flooding
    -   Maximum 10 requests per 10-second sliding window
    -   Minimum 0.5 second interval between consecutive requests
    -   Extra 2 second delay after failures
-   **Request Circuit Breaker** - Stops all requests when ETHM-1 appears overwhelmed
    -   Opens after 3 consecutive request timeouts/failures
    -   60 second cooldown period
-   **Health Status API** - New `get_health_status()` method on AsyncSatel
    -   Returns connection state, circuit breaker states, and rate limiter stats
-   **New Properties on AsyncSatel**:
    -   `connection_circuit_breaker_state` - Returns CLOSED/OPEN/HALF_OPEN
    -   `request_circuit_breaker_active` - Returns True if in cooldown
-   Exported `CircuitBreakerState` enum from package

### Changed
-   Connection retry logic now uses exponential backoff instead of fixed delay
-   All requests now go through rate limiter before being sent

### Fixed
-   **Critical bug**: Integration could permanently block ETHM-1 ethernet port during outage recovery
    -   Root cause: Rapid reconnection attempts + temperature polling overwhelmed the module
    -   Fix: Multiple layers of protection prevent request storms

## [0.4.0] - 2025-11-14

### Added
-   **Zone temperature reading** - New `get_zone_temperature()` method to read temperature from temperature-capable zones
    -   Returns temperature in Celsius (range: -55°C to +125°C, 0.5°C increments)
    -   Proper timeout handling (5 second default per protocol spec)
    -   Handles non-temperature zones gracefully (returns None)
    -   Handles undetermined temperature values (0xFFFF)
-   Added `READ_ZONE_TEMPERATURE` command constants (0x7D) to both read and write command enums
-   Enhanced README with fork purpose, features comparison, and protocol coverage table

### Changed
-   Updated README to clarify this is an enhanced fork with additional monitoring capabilities
-   Added comprehensive documentation for temperature monitoring feature

## [0.3.7](https://github.com/c-soft/satel_integra/compare/0.3.6...0.3.7) -2022-07-05

-   Integrated fix for Python 3.10 compatibility

## 0.3.3 - 2019-03-07

-   Added ENTRY_TIME status to display "DISARMING" status in HA
-   Fixed issue with unhandled connection error causing HomeAssistant to give up on coommunication with eth module completely

## 0.3.2 - 2019-02-18

-   Fixed status issues
-   Introduced "pending status"

## 0.3.1 - 2019-02-13

-   improved robustness when connection disappears
-   fixed issues with "status unknown" which caused blocking of the functionality in HA
-   still existing issues with alarm status - to be fixed

## 0.2.0 - 2018-12-20

-   Integrated changes from community: added monitoring of ouitputs.
-   Attempt at fixing issue with "state unknown" of the alarm. Unfortunately unsuccessful.

## 0.1.0 - 2017-08-24

-   First release on PyPI.
