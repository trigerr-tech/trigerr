# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [0.7.9] - 2026-11-17

### Fixed
- Position manager: status checks and cancels now say whose order it is (request id, user id, strategy id), as placing
  already did. Before, they relied on the caller's logging context, so a caller without one left the order service's
  ledger notes for status and cancel untagged, and a search by request id missed them.

---

## [0.7.8] - 2026-11-15

### Added
- `protect_position(handle, reason, trigger_price, limit_price)`: keeps one protective stop-limit exit resting at the
  broker for all that is held. `reduce_position` takes it off, exits and puts it back for what is left; `close_position`
  takes it off first. Answers carry `protected` and `protection_lost`. The stop is not counted in `working_exit`.
- `place_lt_order(request_id=, user_id=, strategy_id=)`: whose order it is, passed on to the order service. The position
  manager sends them, so the order service's count of entries per run is per run.
- The position manager marks `position_watch:{request_id}` in the state Redis each time a run looks at its position, for
  the guard service.
- `place_lt_order(trade_action=...)`: "ENTRY" or "EXIT", sent with the order for the order service's risk engine. Never
  sent to a broker; an older order service ignores it. The position manager and the shared execution code send it.

---

## [0.7.7] - 2026-11-14

### Fixed
- `convert_to_trades` ends a trade on an exit that leaves nothing open (`quantity_left` 0), as well as on an exit named in
  `order_exit_levels`. The lots of a position are split between the targets in whole numbers and the leftover goes to the first
  target, so with few lots (one lot, or a big share at the first target) the first target sells the whole position. That trade
  was never closed, and the strategies' `convert_to_trades(...)[-1]` raised `IndexError` and lost its record. An exit that carries
  no `quantity_left` is judged by its name alone, as before. New helper `orders_utils.closes_trade`.

---

## [0.7.6] - 2026-11-12

### Added
- `trigerr.orders.positions`, the position manager: the one place a live position's orders are sent, followed and
  recorded. `open_position`, `reduce_position`, `close_position`, `cancel_working` and `sync_position` each return at
  once with what happened (done, part, nothing, working, unknown, busy). Each order's key is written to the position's
  book in the state Redis before it is sent; an exit is never sent for more than what is held less the exits not yet
  recorded, and an order whose result is not known counts in full. Live only; no strategy uses it yet.
- `find_live_order` (what became of a placement, by its idempotency key) and `order_status_now` (one look at an order).
  `placed_order_id` also counts a piece the OMS reports as `UNKNOWN`. Need the OMS release with `/find_order`.
- `settle_live_order`: waits for a placed order to end (60 s), cancels what is still open of it, waits once more, and
  answers `(settled, order_response)`. An answer from the OMS that does not say does not end the wait. Not settled means
  the order may yet fill: the caller must not send another for the same quantity until a later call says it has ended.
- `cancel_live_order` (the SDK had no cancel call), `placed_order_id` (the order id when at least one piece is at the
  broker, also when the OMS answered ERROR for a refused piece) and `filled_lots`.
- `poll_order_status` returns `("partial", order_response)` for the OMS's new `PARTIAL` status (every piece ended, only
  part of the quantity filled). Needs the OMS release that carries `PARTIAL`.

### Changed
- `save_lt_order` tries the Mongo insert and the Redis write three times each and says where the record is: `"success"`
  (both), `"db_failed"` (in the request's Redis orders list, not in Mongo) or `"failed"` (not in the Redis list, so the
  trading loop does not know the order). It used to answer `"success"` when the Redis write had failed, and `"failed"`
  when only the order alert had. A try whose answer was lost is not saved twice.
- `save_lt_trade` returns True/False for the Mongo save (it returned nothing) and retries it; the Redis copy is written
  either way. `add_order_to_redis` returns True/False.

### Fixed
- Live order calls to the OMS carry a time limit (120 s to place, 60 s for the rest, the funds read included); a stuck
  connection used to hold a strategy mid-order with no end.
- A placement that got no answer (a timeout, or a 5xx from the proxy while the OMS restarts) is resent under the same
  idempotency key, and while the OMS answers that the first send is still in progress the same key is asked again (150 s
  at most) for its result.
- `poll_order_status` keeps waiting when a status call gets no answer; it used to return "failed" while the order could
  still fill at the broker.

---

## [0.7.5] - 2026-10-30

### Added
- `convert_to_trades`: every trade now carries `capital_used`, what its entry really put to work, next to `investment`,
  the capital set aside for it (always a little more, since only whole lots are bought). It is the position value over the
  order's `leverage` (1 when the order carries none): `quantity` counts units for spot and futures and lots for everything
  else, the same rule the P&L is priced with. A strategy that sizes with leverage should put `leverage` in its order
  params. New helper `orders_utils.capital_used(order, market_type)`. Dashboards and backends read the saved figure
  instead of working it out from the price, which was only right for options.

---

## [0.7.4] - 2026-10-13

### Fixed
- `calculate_brokerage`, India: a SHORT position was charged with its legs swapped. Callers pass the entry as `buy_price`
  and the exit as `sell_price` whatever the side (`net_pl` relies on it), but STT, which falls on the sale, and stamp duty,
  which falls on the purchase, were taken from those names as given. A short pays STT on the premium it sold first and stamp
  duty on the premium it bought back, so every SHORT trade (a SELLER request, vt or lt) was charged STT on the wrong leg:
  too much when the position lost, too little when it won, by about 0.15% x (exit - entry) x units. Example: short at 85.5,
  bought back at 95.05, 17 lots of 65: brokerage 291.92 -> 276.24. `net_pnl` already had the right direction. LONG trades,
  and the OMS manual-exit trades (which pass the real legs on the default side), are unchanged. Trades already recorded keep
  their old figures. Not changed: delivery equity (it cannot be short), and the US and crypto branches, which have the same
  entry/exit naming (Schwab equities' SEC fee, Binance futures' position size) but are out of go-live scope.

---

## [0.7.3] - 2026-10-09

### Added
- `calculate_brokerage` prices `upstox` and `dhan` for the Indian market (it returned `None` for both, so no trade record
  could be built). Statutory charges are the same as Zerodha's; brokerage follows each broker's published schedule -
  Upstox: Rs 20 an order for options, the lower of Rs 20 and 0.05% for futures, the lower of Rs 20 and 0.1% for intraday
  equity, Rs 20 an order plus Rs 20 DP for delivery; Dhan: flat Rs 20 an order for futures and options, the lower of Rs 20 and
  0.03% for intraday equity, nil brokerage plus Rs 12.50 DP for delivery. Zerodha's results are unchanged by this entry.

### Changed
- `calculate_brokerage`, India (`zerodha`): the statutory charges are brought to the rates in force since 1 April 2026 -
  STT on futures sold 0.02% -> 0.05% and on option premium sold 0.1% -> 0.15% (Budget 2026); NSE exchange charges for cash
  0.00297% -> 0.00307%, futures 0.00173% -> 0.00183% and options 0.03503% -> 0.03553% (NSE/FA/73061, from 1 March 2026).
  The `brokerage` of every trade recorded after the release comes out higher, and its `net_pnl` lower, by that much (an option
  round trip of 44 lots at 90 -> 100: charges 246.81 -> 303.04).

### Fixed
- `calculate_brokerage` priced an order placed on `NFO` (how the strategies route NSE options and futures) at the BSE rates:
  options at 0.0325% instead of NSE's, futures with no exchange charge at all. `NFO` and `XNSE` now count as NSE.

---

## [0.7.2] - 2026-10-06

### Added
- `trigerr.framework.memory_state_cursor()`: an in-process stand-in for the state Redis, so a backtest runs
  hermetically (no real Redis key can be read or written).
- `trigerr.orders.place_bt_leg_order(...)`: a backtest order in exactly `place_vt_order`'s document shape,
  stamped from the replayed candle, with no database write, no alert, and no swallowed errors. The legacy
  `place_bt_order` is unchanged.

### Removed
- The `mongo_collection` and `pickled_model` data-feed kinds. `mongo_collection` let a strategy name any collection
  in the tenant database, and `pickled_model` unpickled a path (remote code execution on a multi-tenant host).
  Neither could run: the harness never provisioned `ctx["collections"]` or `ctx["models"]`. A strategy that names
  either kind is now refused when it is compiled.

### Changed
- `compile_strategy` reports `feed 'x' has unknown kind 'k' (known: ...)` for a base feed whose kind is not
  registered, instead of a `KeyError` in the middle of a run. A feed with no kind at all is unchanged.
- `framework.execution_core`: `bt` is now a first-class mode. Entry, exit, unwind, manual exit and trade
  conversion each name `vt`, `lt` and `bt` explicitly and raise `ValueError` on any other mode. Previously
  "not vt" meant live, so a backtest that got past its price read would have reached `place_lt_order` and
  written to the real `lt_trades`. The `vt` and `lt` branch bodies are unchanged. A backtest's ctx takes
  `rdb_cursor=None` and a `memory_state_cursor()` as `state_cursor`; its trades collect in `ctx["bt_trades"]`.
- `_entry_pricing_window_ok` takes an optional `day`, so a backtest checks the pricing window of the day it is
  replaying rather than the wall-clock weekday.
- Backtest legs are priced off the clock candle; derivative (option/futures) legs still need the live expiry map
  and stop with a `KeyError` in a backtest until historical option pricing lands.

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
