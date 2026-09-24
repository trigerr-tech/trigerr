# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.6.0] - 2026-09-24

### Changed
- `framework.execution_core` sends every order, trade, orders-list and
  investment call to `ctx["state_cursor"]` (the tenant's state Redis) instead
  of `ctx["rdb_cursor"]`, which now carries market data only. Framework
  harnesses must put both cursors in ctx. Breaking for any harness that sets
  only `rdb_cursor`.

---

## [0.3.0] - 2026-07-21

### Added
- `trigerr.crypto_utils`: shared envelope encryption (Fernet/MultiFernet) for
  broker credential values — `load_key()`, `encrypt_input()`/`decrypt_input()`,
  `is_encrypted()`. Used by trigerr-oms and trigerr-broker-automation so
  `broker_credentials` is encrypted at rest with one shared, correct
  implementation instead of two independent ones.
- `orders/live.py`: `validate_credential(credential_id)` — thin wrapper for
  OMS's `/validate_broker_credentials`, letting callers (the trading engine)
  check a credential is live before dispatching a run, without ever handling
  plaintext credential values themselves.

---

## [0.2.0] - 2026-07-20

### Added
- `trigerr.logging_utils`: shared stdlib-only structured (JSON-line) logging —
  `get_logger()`, context propagation (`bind`/`bound`/`clear_context`/`get_context`),
  a credential-scrubbing log filter, and `redirect_stdout_to()` to capture existing
  `print()` call sites without editing them. Part of the platform's centralized
  logging rollout.
- `orders/live.py`: `place_live_order`, `modify_live_order`, `check_order_status`,
  and `poll_order_status` accept optional `request_id`/`user_id`/`strategy_id`,
  falling back to the ambient logging context when not passed explicitly, so
  order calls made from a bound context are automatically correlated end to end
  with the receiving OMS. Fields are omitted from the request body when unset —
  fully backward compatible with OMS deployments on older SDK versions.

---

## [0.1.4.4.1] - 2026-05-06

### Added
- Interactive Brokers (IBKR) brokerage calculation support
  - Equities with tiered pricing model
  - Options with per-contract fees
  - Futures with exchange fees
- Comprehensive broker fee documentation in BROKERS.md
- Complete technical indicators reference in INDICATORS.md
- Enhanced README with detailed usage examples
- CLAUDE.md for AI-assisted development

### Changed
- Updated `calculate_brokerage()` to accept both "interactive_brokers" and "ibkr" as broker codes
- Improved options data fetching with better error handling
- Enhanced swing calculation algorithm for better accuracy

### Fixed
- Resolved bugs in live orders placement for options
- Fixed granularity conversion edge cases
- Corrected brokerage calculation for futures on BSE exchange

---

## [0.1.4.4] - 2025-10-30

### Added
- Custom indicators: RDX, MTI, NETVOLUME
- Smoothed ADX (SADX) indicator
- BBW range calculation
- Volume slope indicator

### Changed
- Optimized `apply_indicators()` performance by 30%
- Improved swing detection for outside bars

### Fixed
- Fixed VWAP calculation for multi-day data
- Resolved pandas deprecation warnings

---

## [0.1.4] - 2025-05-16

### Added
- Multi-broker support:
  - Zerodha (India)
  - Charles Schwab (US)
  - Binance (Crypto)
  - CoinDCX (India Crypto)
- 40+ technical indicators via `apply_indicators()`
- Live trading integration with broker APIs
- Virtual trading (paper trading) module
- Comprehensive backtesting engine
- MetaTrader-style performance reports
- Support for futures and options data
- Granularity conversion utility

### Changed
- Migrated to pandas_ta for technical indicators
- Restructured project into modular architecture
- Improved API authentication handling

### Deprecated
- Old indicator functions (replaced by `apply_indicators()`)

---

## [0.1.3] - 2025-03-17

### Added
- Options chain data fetching
- Strike price utilities
- Opening Range Breakout (ORB) indicator
- Liquidation price calculator for leveraged positions

### Changed
- Enhanced options data API with symbol-based fetching
- Improved error handling for missing market data

### Fixed
- Fixed timezone issues in live data streaming
- Resolved API rate limiting problems

---

## [0.1.2] - 2025-01-23

### Added
- Live data streaming support
- Redis integration for order caching
- Position tracking in MongoDB
- Brokerage calculation for Indian brokers
- ROI percentage calculator

### Changed
- Updated API endpoints for better performance
- Improved order response handling

### Fixed
- Fixed memory leak in live data subscriptions
- Resolved concurrent order placement issues

---

## [0.1.1] - 2024-12-29

### Added
- Historical data fetching for indices
- Futures data API
- Basic technical indicators (EMA, SMA, RSI, MACD)
- Swing detection algorithm

### Changed
- Optimized data fetching for large date ranges
- Improved DataFrame column naming consistency

### Fixed
- Fixed date format inconsistencies
- Resolved API authentication errors

---

## [0.1.0] - 2024-12-24

### Added
- Initial release
- Core library structure
- Basic historical data fetching (EOD candles)
- Configuration management for API keys
- Support for NSE and BSE exchanges
- Basic order placement functionality
- Example scripts

---

## Upgrade Guide

### Upgrading to 0.1.4+

**Breaking Changes:**
- Indicator functions now require dictionary parameters instead of individual arguments
- Column names in DataFrames are now lowercase (`close` instead of `Close`)

**Migration:**

Old code:
```python
df = calculate_ema(df, period=20)
df = calculate_rsi(df, period=14)
```

New code:
```python
indicators = {
    "EMA": {"length": 20},
    "RSI": {"length": 14}
}
df = apply_indicators(df, indicators)
```

### Upgrading to 0.1.3+

**Breaking Changes:**
- `fetch_option_candles()` now requires `expiry` parameter
- Options data structure changed to include `expiry_date` field

**Migration:**
```python
# Old
data = fetch_option_candles(underlying, start, end, "CE", strike)

# New
data = fetch_option_candles(underlying, start, end, "CE", strike, expiry="current")
```

### Upgrading to 0.1.2+

**Breaking Changes:**
- Order placement now requires `credential_id` parameter
- Redis connection required for order management

**Migration:**
```python
# Old
place_lt_order(symbol, exchange, quantity, transaction_type)

# New
place_lt_order(symbol, exchange, quantity, transaction_type, credential_id="your-id")
```

---

## Planned Features

### v0.2.0 (Upcoming)
- [ ] Websocket support for live data
- [ ] Multi-leg options strategies
- [ ] Portfolio management module
- [ ] Risk management utilities
- [ ] Backtesting optimization tools
- [ ] Machine learning integration helpers

### v0.3.0 (Future)
- [ ] Advanced order types (bracket, cover orders)
- [ ] Strategy marketplace
- [ ] Cloud backtesting service
- [ ] Mobile app integration
- [ ] Telegram/Discord bot support

---

## Version History

| Version | Release Date | Status | Major Changes |
|---------|-------------|--------|---------------|
| 0.1.4.4.1 | 2026-05-06 | Current | IBKR support, enhanced docs |
| 0.1.4.4 | 2025-10-30 | Stable | Custom indicators |
| 0.1.4 | 2025-05-16 | Stable | Multi-broker support |
| 0.1.3 | 2025-03-17 | Legacy | Options support |
| 0.1.2 | 2025-01-23 | Legacy | Live trading |
| 0.1.1 | 2024-12-29 | Legacy | Technical indicators |
| 0.1.0 | 2024-12-24 | Legacy | Initial release |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to contribute to this changelog.

When adding entries:
1. Add new versions at the top
2. Use the sections: Added, Changed, Deprecated, Removed, Fixed, Security
3. Include issue numbers when relevant
4. Keep entries concise but descriptive
5. Date format: YYYY-MM-DD

---

## Support

For questions about specific versions or upgrade issues:
- Check the [documentation](https://trigerr.com/docs)
- Open an issue on [GitHub](https://github.com/trigerr/trigerr/issues)
- Email support@trigerr.com

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
