# Sysstra Package Documentation

**Version**: 0.1.4.6.3  
**Author**: Anurag Singh Kushwah  
**Python Support**: 3.9+  
**License**: MIT

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Module Structure](#module-structure)
4. [Public API Reference](#public-api-reference)
5. [Data Models & Conventions](#data-models--conventions)
6. [Configuration](#configuration)
7. [Integration Points](#integration-points)
8. [Core Algorithms](#core-algorithms)
9. [Dependencies](#dependencies)
10. [Development & Distribution](#development--distribution)

---

## Overview

**Sysstra** is a Python library for end-to-end algorithmic trading workflows. It provides:

- **Unified interfaces** for multi-asset, multi-exchange trading (equities, derivatives, commodities, crypto)
- **Historical and live market data** fetching with flexible granularity
- **Order execution** across three modes: live trading, paper trading (virtual), and backtesting
- **Technical analysis** with 40+ indicators (vendored pandas_ta + custom indicators)
- **Advanced analytics**: swing detection, brokerage calculation, performance reporting
- **Global market support**: NSE/BSE (India), NYSE/NASDAQ (US), Binance/CoinDCX (Crypto)

The library acts as a **client to two backend services**:
- **Data API** (https://api.data.sysstra.com/): Historical and live market data
- **Orders API** (https://api.orders.sysstra.com/): Order placement and position tracking

---

## Architecture

### Design Principles

1. **API-Driven**: All data fetching and order operations delegate to backend services via REST APIs
2. **Configuration-Centric**: Central config (`sysstra/config.py`) holds API credentials and service URLs
3. **Framework-Agnostic**: Uses standard Python libraries (requests, pandas, numpy)
4. **Multi-Asset Support**: Abstracts away asset-type differences (EQUITY, OPTIONS, FUTURES) into unified function signatures
5. **Lazy Loading**: TA module (pandas_ta) is vendored and loaded on demand

### High-Level Data Flow

```
User Code
  ↓
Public API Functions (sysstra.set_api_key, sysstra.data.*, sysstra.orders.*)
  ↓
Configuration (sysstra/config.py)
  ↓
HTTP Requests (Data API / Orders API)
  ↓
Backend Services (Redis cache + MongoDB persistence)
```

---

## Module Structure

### Core Modules

```
sysstra/
├── __init__.py                  # Public API: set_api_key(), set_data_url(), set_orders_url()
├── config.py                    # Central configuration dictionary
├── sysstra_utils.py             # Core utility functions (1043 lines)
├── custom_indicators.py         # Custom indicators (44.8 KB)
├── data/                        # Data fetching
│   ├── __init__.py
│   ├── historical.py            # EOD, index, futures, options historical data
│   └── live.py                  # Real-time market data streaming
├── orders/                      # Order execution (3 modes)
│   ├── __init__.py
│   ├── live.py                  # Live trading order placement
│   ├── virtual.py               # Paper trading simulation
│   ├── backtest.py              # Backtesting engine
│   └── orders_utils.py          # Shared order utilities (Redis/MongoDB)
└── ta/                          # Technical Analysis (vendored pandas_ta v0.3.81b0)
    ├── __init__.py              # Exports all indicators, flat + categorized access
    ├── core.py                  # DataFrame extension (AnalysisIndicators)
    ├── custom.py                # Import/export external indicators
    ├── maps.py                  # Exchange timezones, rate constants
    ├── ma.py                    # Moving average modes (SMA, EMA, WMA, etc.)
    ├── candle/                  # Candle pattern indicators
    ├── cycle/                   # Cycle indicators
    ├── momentum/                # RSI, MACD, Stochastic, etc. (48 indicators)
    ├── overlap/                 # EMA, SMA, Bollinger Bands, etc. (40 indicators)
    ├── performance/             # Performance metrics
    ├── statistics/              # STDEV, MAD, Skew, Quantile
    ├── trend/                   # ADX, Aroon, MACD Histogram, etc. (25 indicators)
    ├── utils/                   # Utility functions
    ├── volatility/              # ATR, NATR, etc. (20 indicators)
    └── volume/                  # OBV, AD, CMF, etc. (24 indicators)
```

### File Purposes

| File | Lines | Purpose |
|------|-------|---------|
| `sysstra_utils.py` | ~1043 | Core trading utilities: swing calc, granularity conversion, PnL calc, reporting |
| `custom_indicators.py` | ~1300 | Custom indicators (Stochastic, VFI, Swing calcs) not in pandas_ta |
| `data/historical.py` | ~100 | Fetch historical candles (EOD, index, futures, options) from Data API |
| `data/live.py` | ~50 | Real-time streaming market data |
| `orders/live.py` | ~500 | Place live orders via broker APIs, manage order state |
| `orders/virtual.py` | ~200 | Simulate order execution with virtual balance tracking |
| `orders/backtest.py` | ~100 | Backtesting order placement and report saving |
| `orders/orders_utils.py` | ~200 | Shared: Redis cache, MongoDB persistence, order polling |
| `ta/` | 88+ KB | Vendored pandas_ta library v0.3.81b0 with DataFrame extension |

---

## Public API Reference

### Configuration Functions

All configuration functions are exposed at package level via `sysstra.__init__.py`:

```python
import sysstra

# Set API authentication
sysstra.set_api_key("your-api-key")

# Override service URLs (optional, defaults in config.py)
sysstra.set_data_url("https://custom-data-api.com/")
sysstra.set_orders_url("https://custom-orders-api.com/")
```

**Configuration Storage**: `sysstra/config.py` (dict-based, single source of truth)

---

### Data Fetching: Historical

All functions return JSON lists from the Data API. Dates as strings (YYYY-MM-DD) or datetime.date objects.

#### Equities & Indices

```python
from sysstra.data import fetch_eod_candles, fetch_index_candles

# End-of-day candles (NSE/BSE)
eod_data = fetch_eod_candles(
    symbol="SBIN",
    start_date="2024-01-01",
    end_date="2024-12-31",
    exchange="XNSE"  # Default: XNSE (NSE)
)
# Returns: List[{timestamp, open, high, low, close, volume, ...}]

# Intraday candles (1min, 5min, 15min, hourly, etc.)
intra_data = fetch_index_candles(
    symbol="NIFTY 50",
    start_date="2024-01-01",
    end_date="2024-12-31",
    granularity=1,  # 1=1min, 5=5min, 15=15min, 60=1hour
    exchange="XNSE"
)
```

#### Derivatives

```python
from sysstra.data import fetch_futures_candle, fetch_option_candles, fetch_option_candles_by_symbol, fetch_option_candles_by_date

# Futures historical data
fut_data = fetch_futures_candle(
    underlying="NIFTY",
    start_date="2024-01-01",
    end_date="2024-12-31",
    granularity=1,
    exchange="XNSE"
)

# Options by strike & expiry
opt_data = fetch_option_candles(
    underlying="NIFTY",
    start_date="2024-01-01",
    end_date="2024-12-31",
    option_type="CE",  # CE or PE
    strike_price=25000,
    expiry="2024-01-31",  # or "current" for current month
    granularity=1,
    exchange="XNSE"
)

# Options by symbol (e.g., "NIFTY24JAN25000CE")
opt_by_sym = fetch_option_candles_by_symbol(
    underlying="NIFTY",
    symbol="NIFTY24JAN25000CE",
    start_date="2024-01-01",
    end_date="2024-12-31",
    granularity=1,
    exchange="XNSE"
)

# Options chain by date (all strikes for underlying on date range)
chain_data = fetch_option_candles_by_date(
    underlying="NIFTY",
    start_date="2024-01-01",
    end_date="2024-12-31",
    granularity=1,
    exchange="XNSE"
)
```

---

### Order Execution: Live Trading

```python
from sysstra.orders import place_lt_order

# Basic market order
status, response = place_lt_order(
    symbol="SBIN",
    exchange="NSE",
    quantity=1,
    transaction_type="BUY",  # BUY or SELL
    order_type="MARKET",  # MARKET, LIMIT, STOPLOSS
    asset_type="EQUITY",  # EQUITY, OPTIONS, FUTURES
    credential_id="broker-cred-id"
)
# Returns: ("success" | "error" | "failed", response_dict)

# Limit order
status, response = place_lt_order(
    symbol="SBIN",
    exchange="NSE",
    quantity=1,
    transaction_type="BUY",
    order_type="LIMIT",
    order_price=550.50,
    credential_id="broker-cred-id"
)

# Stop-loss order
status, response = place_lt_order(
    symbol="SBIN",
    exchange="NSE",
    quantity=1,
    transaction_type="SELL",
    order_type="STOPLOSS",
    trigger_price=540.00,
    credential_id="broker-cred-id"
)

# Options order
status, response = place_lt_order(
    symbol="NIFTY24JAN25000CE",
    exchange="NSE",
    quantity=1,
    transaction_type="BUY",
    order_type="MARKET",
    asset_type="OPTIONS",
    option_type="CE",
    strike_price=25000,
    underlying="NIFTY",
    expiry_date="2024-01-31",
    credential_id="broker-cred-id"
)

# Futures order
status, response = place_lt_order(
    underlying="NIFTY",
    exchange="NSE",
    quantity=1,
    transaction_type="BUY",
    order_type="MARKET",
    asset_type="FUTURES",
    credential_id="broker-cred-id"
)
```

**Live Order Placement Flow**:
1. `place_lt_order()` validates and formats order parameters
2. Calls `place_live_order()` (internal) to send to Orders API
3. Backend returns status (SUCCESS/FAILURE)
4. Response saved to Redis (cache) and MongoDB (persistence)
5. Returns (status_string, response_dict) to caller

---

### Order Execution: Paper Trading (Virtual)

```python
from sysstra.orders import place_virtual_order, fetch_orders_list, add_order_to_redis

# Place simulated order (no actual execution)
status, response = place_virtual_order(
    symbol="SBIN",
    quantity=1,
    transaction_type="BUY",
    order_type="MARKET",
    # ... same parameters as place_lt_order
)

# Fetch active orders
orders = fetch_orders_list(redis_cursor, user_id="user-123")
# Returns: List of order dicts from Redis cache

# Add order to Redis cache (internal utility)
add_order_to_redis(redis_cursor, order_dict)
```

---

### Order Execution: Backtesting

```python
from sysstra.orders import place_bt_order, save_bt_report

# Place order during backtest (simulated with historical candles)
orders_list = []
orders_list = place_bt_order(
    order_candle=candle_dict,  # OHLCV candle from historical data
    quantity=1,
    position_type="LONG",  # LONG or SHORT
    transaction_type="BUY",
    order_type="MARKET",
    trade_action="ENTRY",  # ENTRY or EXIT
    exit_type="TARGET",  # TARGET, STOPLOSS, TIME_EXIT, SIGNAL_EXIT
    orders_list=orders_list,
    user_id="strategy-123",
    strategy_id="strat-001",
    request_id="req-xyz"
)

# Save backtest report to MongoDB
save_bt_report(app_db_cursor, report_dict={
    "request_id": "req-xyz",
    "total_trades": 50,
    "win_rate": 0.65,
    "max_drawdown": 0.15,
    # ... other metrics
})
```

---

### Technical Analysis: Indicators

**Two access patterns** (both equivalent):

```python
from sysstra import ta

# Flat access (preferred)
ema_result = ta.ema(data_series, length=20)
rsi_result = ta.rsi(data_series, length=14)

# Categorized access
ema_result = ta.overlap.ema(data_series, length=20)
rsi_result = ta.momentum.rsi(data_series, length=14)
```

#### Supported Indicators (40+ total)

**Overlap** (moving averages & smoothing):
- EMA, SMA, WMA, DEMA, TEMA, T3, KAMA, LINREG, MIDPOINT, SINE, TRADESTATION MA, ZLMA, HMA, etc.

**Momentum** (trend-following):
- RSI, MACD, Stochastic, CCI, KDJ, ROC, MOM, Awesome Oscillator, Williams %R, etc.

**Trend** (directional):
- ADX, Aroon, MACD Histogram, Supertrend, Ichimoku, PSAR, VORTEX, etc.

**Volatility**:
- ATR (Average True Range), NATR (Normalized ATR), Bollinger Bands, Keltner Channels, etc.

**Volume**:
- OBV, AD (Accumulation/Distribution), CMF (Chaikin Money Flow), VPTC, etc.

**Cycle** & **Candle** patterns, **Statistics** (STDEV, Skew, Quantile).

#### DataFrame Extension (ta accessor)

```python
import pandas as pd
from sysstra import ta

df = pd.DataFrame({"open": [...], "high": [...], "low": [...], "close": [...], "volume": [...]})

# Use ta accessor for bulk operations
df.ta.sma(length=20, append=True)  # Adds 'SMA_20' column
df.ta.rsi(length=14, append=True)  # Adds 'RSI_14' column
df.ta.macd(append=True)             # Adds MACD columns
```

---

### Core Utilities

```python
from sysstra.sysstra_utils import (
    change_granularity,
    calculate_swing,
    apply_indicators,
    calculate_brokerage,
    generate_mt_report,
    round_to_tick_multiple,
    calculate_liquidation_price
)

# Convert minute-level data to higher timeframe
df_1min = pd.DataFrame([...])  # 1-minute OHLCV candles
df_5min = change_granularity(df_1min, granularity=5)
df_1hr = change_granularity(df_1min, granularity=60)

# Calculate swing highs/lows (market structure)
df_with_swing = calculate_swing(df_1hr, swing_setup=2, ignore_last_bar=False)
# Adds columns: 'swing' (UP/DOWN), 'swing_change' (boolean)

# Apply multiple indicators at once
indicators_dict = {
    "EMA": {"length": 20},
    "RSI": {"length": 14},
    "ADX": {"length": 14},
    "ATR": {"length": 14}
}
df_with_indicators = apply_indicators(df, indicators_dict)
# Adds EMA_20, RSI_14, ADX_14, ATRLEN_14 columns

# Calculate brokerage and net PnL
total_charges, net_pnl = calculate_brokerage(
    buy_price=100.50,
    sell_price=105.75,
    quantity=100,
    broker="zerodha",  # zerodha, binance, coindcx, schwab
    market_type="equity"
)
# Accounts for: STT, transaction fees, GST, SEBI charges, stamp duty

# Generate backtest report (MetaTrader-style)
report = generate_mt_report(
    report_df=trades_df,
    pnl_column="pnl"
)
# Returns: {total_trades, wins, losses, win_rate, profit_factor, max_drawdown, ...}

# Round price to NSE tick size (0.05 rupees)
rounded = round_to_tick_multiple(549.53)  # Returns 549.55

# Calculate liquidation price (futures/margin positions)
liq_price = calculate_liquidation_price(
    entry_price=100,
    leverage=10,
    position_type="LONG"
)
```

---

## Data Models & Conventions

### OHLCV DataFrame Format

All historical data functions return JSON responses that are converted to DataFrames with this schema:

```python
{
    "timestamp": datetime,      # Candle close time
    "date": datetime,           # Trading date
    "open": float,
    "high": float,
    "low": float,
    "close": float,
    "volume": int,
    "oi": int,                  # Open Interest (futures/options only)
    "previous_day_close": float,  # Reference price
    "curr_day_open": float,
    
    # Asset-specific fields:
    "symbol": str,              # Trading symbol (equities/index)
    "underlying_stock": str,    # Underlying name (options)
    "strike": float,            # Strike price (options)
    "option_type": str,         # CE or PE
    "expiry": str               # Expiry date (options/futures)
}
```

### Order Dictionary Format

Orders stored in Redis/MongoDB follow this structure:

```python
{
    "market": "IN",             # Market code (IN, US, etc.)
    "tradingsymbol": str,
    "exchange": "NSE",
    "user_id": str,
    "strategy_id": str,
    "request_id": str,
    "quantity": int,
    "quantity_left": int,       # For partial fills
    "position_type": "LONG" | "SHORT",
    "transaction_type": "BUY" | "SELL",
    "trade_action": "ENTRY" | "EXIT",
    "order_type": "MARKET" | "LIMIT" | "STOPLOSS",
    "asset_type": "EQUITY" | "OPTIONS" | "FUTURES",
    "exit_type": "TARGET" | "STOPLOSS" | "TIME_EXIT" | "SIGNAL_EXIT",
    "lot_size": int,
    "max_qpo": int,
    "exchange_timestamp": str,
    "status": "COMPLETE" | "PENDING" | "REJECTED" | "CANCELLED",
    "trigger_price": float,     # For STOPLOSS orders
    "order_id": str,
    "validity": "DAY" | "IOC" | "GTC",
    "holding_type": "INTRADAY" | "DELIVERY",
    "market_type": "equity" | "options" | "futures",
    
    # Options/Futures specific:
    "option_type": "CE" | "PE",
    "strike_price": float,
    "underlying": str,
    "expiry_date": str
}
```

### Backtest Report Format

```python
{
    "request_id": str,
    "total_trades": int,
    "winning_trades": int,
    "losing_trades": int,
    "win_rate": float,          # winning_trades / total_trades
    "profit_factor": float,     # gross_profit / abs(gross_loss)
    "max_drawdown": float,      # Peak-to-trough decline (%)
    "sharpe_ratio": float,      # Risk-adjusted return
    "consecutive_wins": int,    # Max consecutive winning trades
    "consecutive_losses": int,
    "avg_win": float,
    "avg_loss": float,
    "total_pnl": float,
    "status": "done"
}
```

---

## Configuration

### Central Config File: `sysstra/config.py`

```python
config = {
    "api_key": None,                                  # User-set via set_api_key()
    "orders_url": "https://orders.api.sysstra.com/",  # Live trading orders API
    "data_url": "https://api.data.sysstra.com/"       # Historical/live data API
}
```

**Dynamic Override** (for local development):
```python
# Uncomment in config.py to use local services
# "orders_url": "http://127.0.0.1:5001/",
# "data_url": "http://127.0.0.1:5001/"
```

### Runtime Configuration

```python
import sysstra

# All configuration is optional (defaults in config.py)
sysstra.set_api_key("your-api-key")
sysstra.set_data_url("https://custom-api.com/data/")
sysstra.set_orders_url("https://custom-api.com/orders/")
```

**Scope**: Configuration is global (module-level dict). Changes affect all subsequent calls.

---

## Integration Points

### External Services

1. **Data API** (`https://api.data.sysstra.com/`)
   - Endpoints: `/fetch-eod-data`, `/fetch-index-data`, `/fetch-futures-data`, `/fetch-options-data`, `/fetch-options-data-by-symbol`, `/fetch-options-data-by-date`
   - Authentication: `x-api-key` header
   - Request format: `{"symbol", "exchange", "from_date", "to_date", "granularity", ...}`
   - Response format: JSON array of candle objects

2. **Orders API** (`https://api.orders.sysstra.com/`)
   - Endpoints: `/place-order`, `/order-status`, `/order-list`, `/cancel-order`
   - Authentication: `x-api-key` header
   - Request format: `{"symbol", "exchange", "quantity", "order_type", "credential_id", ...}`
   - Response format: `{"status": "SUCCESS" | "FAILURE", "order_id": str, ...}`

3. **Backend Database** (via Orders API)
   - Redis: Order cache (fast lookups)
   - MongoDB: Order persistence

### Authentication Flow

1. User calls `sysstra.set_api_key(key)`
2. Key stored in `config["api_key"]`
3. All requests to Data API and Orders API include header: `{"x-api-key": config["api_key"]}`
4. Backend validates and returns data/confirmation

### Error Handling

- **Data Fetching**: Functions catch exceptions, print messages, return empty list `[]` on failure
- **Order Placement**: Catches exceptions, returns `("failed", None)` tuple
- **Utilities**: Most functions catch exceptions, print traceback, return transformed data or original input

---

## Core Algorithms

### 1. Swing Detection (`calculate_swing()`)

**Purpose**: Identify market structure (swing highs/lows) and trend direction.

**Algorithm** (simplified):
1. Iterate through OHLCV DataFrame
2. Classify each bar as part of UP swing or DOWN swing based on close relative to highs/lows
3. Detect swings using configurable `swing_setup` (e.g., 2 = 2-bar confirmation)
4. Handle outside bars (bar with both higher high and lower low than previous)
5. Mark reversals with `swing_change` boolean flag

**Output columns**:
- `swing`: "UP" or "DOWN"
- `swing_change`: True on reversal, False otherwise

**Key Parameters**:
- `swing_setup`: Sensitivity (default=2, range 1-5)
- `ignore_last_bar`: If True, skip the most recent bar (for live data)

### 2. Granularity Conversion (`change_granularity()`)

**Purpose**: Aggregate minute-level candles to higher timeframes (5min, hourly, daily, etc.).

**Algorithm**:
1. Group candles by trading symbol (if multi-symbol input)
2. Aggregate N candles:
   - OPEN = first candle's open
   - CLOSE = last candle's close
   - HIGH = max high across N candles
   - LOW = min low across N candles
   - VOLUME = sum of volumes
   - OI = sum (for futures/options)
3. Preserve asset-specific fields (strike, expiry, underlying)
4. Return new DataFrame with aggregated candles

**Input Granularity**: Minutes (API returns 1-minute data)  
**Output Granularity**: Configurable (5, 15, 60 minutes, daily via intraday, etc.)

### 3. Indicator Application (`apply_indicators()`)

**Purpose**: Batch apply multiple indicators to OHLCV DataFrame.

**Algorithm**:
1. Accept dict of `{indicator_name: {param_dict}}`
2. For each indicator:
   - Call `ta.<indicator_name>(df[close], **params)`
   - Append result as new column to DataFrame
   - Column named: `{INDICATOR}_{PARAM_VALUE}` (e.g., `EMA_20`, `RSI_14`)
3. Return modified DataFrame (in-place modification)

### 4. Brokerage Calculation (`calculate_brokerage()`)

**Purpose**: Calculate fees and net profit for a trade.

**Supported Brokers**: Zerodha, Binance, CoinDCX, Schwab

**Calculation** (Zerodha example for equities):
```
buy_value = buy_price * quantity
sell_value = sell_price * quantity

brokerage = min(20, 0.03% of buy_value + sell_value)
stt = 0.1% of sell_value (equities only)
transaction_fee = 0.00325% of (buy_value + sell_value)
gst = 18% of (brokerage + transaction_fee)
sebi_charges = 10 ÷ crore (10 per crore)
stamp_duty = varies by state

total_charges = brokerage + stt + transaction_fee + gst + sebi_charges + stamp_duty
net_pnl = (sell_value - buy_value) - total_charges

Returns: (total_charges, net_pnl)
```

---

## Dependencies

### Core Dependencies (required)

```
requests      # HTTP client for API calls
numpy         # Numerical computation
pandas        # Data manipulation and analysis
redis         # Cache layer for orders
```

**Versions**:
- numpy >= 1.26.0
- pandas >= 2.0.0
- Python >= 3.9

### Vendored Dependencies

- **pandas_ta** (v0.3.81b0): Technical analysis indicators library, vendored directly in `sysstra/ta/`

### Optional Dependencies

- `redis-py`: For order caching (already in install_requires)
- `pymongo`: For persistent order storage (referenced but not in install_requires — assumed available)

---

## Development & Distribution

### Installation (Development)

```bash
# Clone repository
git clone https://github.com/sysstra/sysstra.git
cd sysstra

# Install in editable mode with dependencies
pip install -e .

# Install development dependencies
pip install -r requirements.txt
```

### Building Distribution Packages

```bash
# Generate source distribution and wheel
python setup.py sdist bdist_wheel

# Output files:
# dist/sysstra-0.1.4.6.3.tar.gz
# dist/sysstra-0.1.4.6.3-py3-none-any.whl
```

### Installation from Distribution

```bash
# Install from source tarball
pip install dist/sysstra-0.1.4.6.3.tar.gz

# Or from PyPI
pip install sysstra
```

### Package Metadata

- **Name**: sysstra
- **Version**: 0.1.4.6.3 (semver-like, component-based)
- **Author**: Anurag Singh Kushwah
- **Email**: anurag@sysstra.com
- **Homepage**: https://github.com/sysstra/sysstra
- **License**: MIT
- **Classifiers**: Python 3, OS-independent, MIT License

### Running Examples

```bash
# Test order execution examples
python examples/orders_test.py
```

---

## Key Design Decisions

### 1. Vendored pandas_ta

**Decision**: Include pandas_ta as vendored code in `sysstra/ta/` rather than external dependency.

**Rationale**:
- Avoids version conflicts and breaking changes in pandas_ta
- Enables customization and fixes specific to Sysstra
- Single-source-of-truth for indicator implementations
- Users don't need to manage pandas_ta separately

**Trade-off**: Larger package size, but more stable and predictable.

### 2. API-Driven Architecture

**Decision**: All data and orders delegated to backend REST APIs, not computed locally.

**Rationale**:
- Centralized data source (single source of truth)
- Scalability (backend handles heavy computation)
- Security (API keys validated server-side)
- Consistency (same data for all clients)

**Trade-off**: Requires network connectivity, depends on external services.

### 3. Global Configuration

**Decision**: Central mutable dict in `sysstra/config.py` for runtime configuration.

**Rationale**:
- Simple, lightweight (no files or environment variables)
- Supports dynamic reconfiguration
- Familiar to traders (analogous to broker configuration)

**Trade-off**: Global state (not thread-safe by default), not explicit dependency injection.

### 4. Multiple Order Modes (Live / Virtual / Backtest)

**Decision**: Three separate order execution paths with unified signatures.

**Rationale**:
- Traders can test strategies in virtual mode before going live
- Backtesting uses historical data (no API calls)
- Same code structure for all modes (easy to transition)

**Trade-off**: More code to maintain, subtle differences in behavior (e.g., live has async fills, backtest is instant).

---

## Common Use Cases

### 1. Backtest a Simple EMA Crossover Strategy

```python
import pandas as pd
from sysstra.data import fetch_eod_candles
from sysstra.sysstra_utils import apply_indicators, calculate_swing

# Fetch data
data = fetch_eod_candles("SBIN", "2024-01-01", "2024-12-31", "XNSE")
df = pd.DataFrame(data)

# Apply indicators
indicators = {"EMA": {"length": 20}, "EMA": {"length": 50}}
df = apply_indicators(df, indicators)

# Generate signals (EMA_20 > EMA_50 = BUY)
df["signal"] = (df["EMA_20"] > df["EMA_50"]).astype(int)

# Execute backtest logic
# ... (user implements order placement logic using place_bt_order)
```

### 2. Live Trade with Swing-Based Entry

```python
import sysstra
from sysstra.data import fetch_index_candles
from sysstra.sysstra_utils import calculate_swing
from sysstra.orders import place_lt_order

sysstra.set_api_key("my-key")

# Fetch live data
data = fetch_index_candles("NIFTY 50", "2025-01-01", "2025-01-10", granularity=15)
df = pd.DataFrame(data)

# Detect swings
df = calculate_swing(df, swing_setup=2)

# Entry condition: swing reversal
if df.iloc[-1]["swing_change"]:
    status, response = place_lt_order(
        symbol="NIFTY24FEB25000CE",
        exchange="NSE",
        quantity=1,
        transaction_type="BUY",
        order_type="MARKET",
        asset_type="OPTIONS",
        credential_id="my-broker-cred"
    )
```

### 3. Analyze Options Chain

```python
from sysstra.data import fetch_option_candles_by_date

# Fetch all strikes for NIFTY on a date range
chain_data = fetch_option_candles_by_date(
    underlying="NIFTY",
    start_date="2024-01-01",
    end_date="2024-01-31"
)

df = pd.DataFrame(chain_data)
# Analyze: IV, volume, open interest, etc.
```

---

## Troubleshooting

### Authentication Failures

- **Symptom**: Empty responses or "Unauthorized" errors
- **Check**: `sysstra.set_api_key()` called before any API function
- **Verify**: API key is valid and not expired

### Data API Latency

- **Symptom**: Slow historical data fetches (for large date ranges)
- **Optimize**: Fetch data in 3-month chunks and concatenate
- **Consider**: Caching results locally (pickle or parquet)

### Order Execution Timeouts

- **Symptom**: `place_lt_order()` hangs or returns "failed"
- **Check**: Orders API is accessible (no firewall/proxy issues)
- **Verify**: Broker credential is valid and has trading permission
- **Monitor**: Backend logs for order rejection reasons

### Redis/MongoDB Errors

- **Symptom**: Orders not persisting across sessions
- **Check**: Redis and MongoDB services running and accessible
- **Verify**: Connection strings in backend configuration

---

## Future Development Notes

- [ ] Add WebSocket support for real-time data streaming
- [ ] Implement order book depth visualization
- [ ] Add portfolio-level risk management (Greeks, VaR, stress testing)
- [ ] Support more brokers (Interactive Brokers, TD Ameritrade, etc.)
- [ ] Implement strategy backtesting framework with walk-forward analysis
- [ ] Add sentiment analysis integration (news, social media)
- [ ] Support algorithmic order placement (TWAP, VWAP, etc.)
- [ ] Create web dashboard for portfolio monitoring

---

## Version History

- **0.1.4.6.3** (Current): Production-ready with all core features
  - Vendored pandas_ta v0.3.81b0
  - Multi-asset order execution (EQUITY, OPTIONS, FUTURES)
  - Global market support (NSE, BSE, NYSE, NASDAQ, Binance, CoinDCX)
  - Advanced analytics (swings, brokerage, reporting)
  - Paper trading and backtesting modes

---

## License

MIT License — See LICENSE file in repository.

---

## Contact & Support

- **Author**: Anurag Singh Kushwah
- **Email**: anurag@sysstra.com
- **GitHub**: https://github.com/sysstra/sysstra
- **Issues**: https://github.com/sysstra/sysstra/issues
