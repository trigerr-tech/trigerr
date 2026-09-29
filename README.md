# Trigerr

Trigerr is a Python package for algorithmic trading — technical indicators,
OHLCV utilities, market-structure analysis, P&L calculations, reports,
in-memory backtesting, and network-connected data and order execution
(historical/live market data, backtest/virtual/live order engines, a
canonical-AST strategy framework). It is the successor to an earlier internal
package.

## Status

Trigerr is at v0.7.1 and in production use on the Trigerr white-label trading
platform (live, virtual and backtest order flow; live market data over Redis
Streams). The public API is versioned but still evolving — pin a version in
production and read the changelog before upgrading.

Trigerr supports Python 3.10 and newer.

## Installation

```bash
pip install trigerr
```

For local development from a checkout:

```bash
pip install -e ".[dev]"
python -m pytest
```

## Current configuration API

The existing configuration helpers remain available while the integration
layer is migrated:

```python
import trigerr

trigerr.set_api_key("your-api-key")
trigerr.set_data_url("https://data.example.com/")
trigerr.set_orders_url("https://orders.example.com/")
```

Do not use real trading credentials in examples, tests, or committed files.

## Roadmap

Near-term work is on the platform side rather than the SDK's own shape:
onboarding more brokers to live order execution (Dhan, then Upstox), and
extending the canonical-AST strategy framework (`trigerr.framework`) to more
strategy families. See `PLATFORM_TARGET_ARCHITECTURE.md` in the
`trigerr-trading-strategies` repo for the platform-wide plan this SDK
implements.

## License

Trigerr is released under the [MIT License](LICENSE).
