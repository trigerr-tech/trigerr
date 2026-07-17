# Trigerr

Trigerr is a Python package for quantitative trading research and analysis.
It is being developed as an open-source successor to an earlier internal
package, with an initial focus on dependable offline tools: technical
indicators, OHLCV utilities, market-structure analysis, P&L calculations,
reports, and in-memory backtesting.

## Status

Trigerr is in its initial migration phase. The import namespace and packaging
are ready; the public API is not yet stable. Network-connected data and order
integrations will be redesigned as optional adapters rather than treated as
part of the core package.

Trigerr supports Python 3.10 and newer.

## Installation

```bash
pip install -e .
```

For local development:

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

See [TRIGERR_MIGRATION_PLAN.md](TRIGERR_MIGRATION_PLAN.md) for the phased
migration plan.

## License

Trigerr is released under the [MIT License](LICENSE).
