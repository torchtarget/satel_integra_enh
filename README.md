# Satel Integra Enhanced: Asynchronous python client for Satel Integra

[![Licence](https://img.shields.io/github/license/c-soft/satel_integra)](LICENSE)

**This is an enhanced fork of [c-soft/satel_integra](https://github.com/c-soft/satel_integra)** that adds additional features from the Satel Integra protocol that are useful for home automation and comprehensive monitoring.

## About

Enhanced communication library for Satel Integra alarm system via TCP/IP protocol (ETHM-1/ETHM-1 Plus modules). This fork extends the original library with additional monitoring capabilities:

- **Zone temperature reading** - Monitor temperature from temperature-enabled zones
- **Zone tamper detection** - Detect physical tampering with sensors
- **System trouble monitoring** - AC power loss, battery status, communication issues
- **Zone bypass status** - Track which zones are currently bypassed
- **Alarm memory** - Historical alarm information
- **Enhanced zone states** - Long violation, no violation troubles

### Why This Fork?

The original `satel_integra` library provides excellent basic functionality for zone violation monitoring, partition arming/disarming, and output control. However, the Satel Integra protocol supports many more features that are valuable for comprehensive home monitoring:

- **Environmental monitoring** (temperature sensing)
- **Security monitoring** (tamper detection, bypass status)
- **System health** (power, battery, communication troubles)
- **Historical data** (alarm memory, trouble memory)

This fork aims to expose these additional capabilities while maintaining backward compatibility with the original library.

## Installation

### From Source (Development)

```bash
git clone https://github.com/torchtarget/satel_integra_enh.git
cd satel_integra_enh
pip install -e .
```

### From GitHub

```bash
pip install git+https://github.com/torchtarget/satel_integra_enh.git
```

## Usage

Basic usage is identical to the original library:

```python
from satel_integra import AsyncSatel

# Connect to your Satel Integra system
satel = AsyncSatel(
    host="192.168.1.100",
    port=7094,
    monitored_zones=[1, 2, 3],
    monitored_outputs=[1, 2],
    partitions=[1]
)

await satel.start(enable_monitoring=True)

# Access enhanced features
temperature = await satel.get_zone_temperature(zone_number=5)
tamper_zones = satel.zones_tamper
bypass_zones = satel.zones_bypass
```

For complete examples, look into the [examples](examples/) folder.

## Features

### Core Features (from original library)
- ✅ Zone violation monitoring
- ✅ Partition arming/disarming (modes 0-3)
- ✅ Output control (on/off)
- ✅ Alarm clearing
- ✅ Real-time status updates via callbacks
- ✅ Encrypted communication support (integration key)

### Enhanced Features (this fork)
- ✅ **Zone temperature reading** - Read temperature from temperature-capable zones
- ✅ **Connection protection** - Circuit breaker and exponential backoff prevent overwhelming ETHM-1
- ✅ **Request rate limiting** - Prevents request flooding that can lock out the ethernet module
- 🚧 **Zone tamper detection** - Planned
- 🚧 **System trouble monitoring** - Planned
- 🚧 **Zone bypass status** - Planned
- 🚧 **Alarm memory** - Planned
- 🚧 **Enhanced zone states** - Planned

### ETHM-1 Protection Features

The ETHM-1 module can become unresponsive or blocked if overwhelmed with requests. This library includes multiple protection layers:

```python
from satel_integra_enh import AsyncSatel, CircuitBreakerState

satel = AsyncSatel(host="192.168.1.100", port=7094, ...)

# Check health status
status = satel.get_health_status()
print(status)
# {
#   'connected': True,
#   'connection_circuit_breaker': 'CLOSED',
#   'request_circuit_breaker_active': False,
#   'queue_stats': {'requests_in_window': 2, 'max_requests': 10, ...}
# }

# Check circuit breaker state
if satel.connection_circuit_breaker_state == CircuitBreakerState.OPEN:
    print("Too many connection failures - connections blocked temporarily")
```

**Protection mechanisms:**
- **Connection Circuit Breaker**: Opens after 5 consecutive failures, blocks for 5 minutes
- **Exponential Backoff**: Reconnection delays increase (5s → 10s → 20s → ... up to 5 min)
- **Request Rate Limiter**: Max 10 requests per 10 seconds, min 0.5s between requests
- **Request Circuit Breaker**: Stops requests for 60s after 3 consecutive timeouts

### Protocol Coverage

Based on the [Satel Integra INT-RS/ETHM-1 protocol](https://www.satel.eu/en/download/instrukcje/ethm1_plus_en_a1951078.pdf), this library currently implements:

**Monitoring Commands:**
- 0x00 - Zones violation ✅
- 0x01 - Zones tamper 🚧
- 0x06 - Zones bypass 🚧
- 0x09-0x16 - Partition states ✅
- 0x17 - Outputs state ✅
- 0x1A - RTC and basic status 🚧
- 0x1B-0x1F - System troubles 🚧
- 0x7D - Zone temperature ✅

**Control Commands:**
- 0x80-0x83 - Partition arming (modes 0-3) ✅
- 0x84 - Partition disarm ✅
- 0x85 - Clear alarm ✅
- 0x88-0x89 - Outputs control ✅

✅ = Implemented | 🚧 = Planned

## Contributing

Contributions are welcome! If you want to contribute, have a look at [the contribution file](CONTRIBUTING.md).

This fork aims to maintain compatibility with the original library while adding new features. When contributing:
- Keep backward compatibility
- Follow the existing code style
- Add tests for new features
- Update documentation

## License

Refer to the [licence file](LICENCE).

## Credits

Original creator of the library is [Krzysztof Machelski](https://github.com/c-soft)

All contributors are listed on [the contributor's page](https://github.com/c-soft/satel_integra/graphs/contributors)
