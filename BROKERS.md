# Supported Brokers

This document provides detailed information about all brokers supported by Sysstra for brokerage calculation and order execution.

---

## Table of Contents

- [Indian Brokers](#indian-brokers)
  - [Zerodha](#zerodha)
- [US Brokers](#us-brokers)
  - [Interactive Brokers](#interactive-brokers)
  - [Charles Schwab](#charles-schwab)
- [Crypto Exchanges](#crypto-exchanges)
  - [Binance](#binance)
  - [CoinDCX](#coindcx)
- [Fee Comparison](#fee-comparison)

---

## Indian Brokers

### Zerodha

**Broker Code**: `"zerodha"`

**Supported Markets**: Indian equities, F&O (Futures & Options)

#### Fee Structure

##### Equity Delivery
- **Brokerage**: ₹0 (Free)
- **STT/CTT**: 0.1% on buy & sell
- **Transaction Charges**: 
  - NSE: 0.00297%
  - BSE: 0.00375%
- **GST**: 18% on (brokerage + transaction charges)
- **SEBI Charges**: ₹10 per crore
- **Stamp Duty**: 0.015% on buy side

##### Equity Intraday
- **Brokerage**: ₹20 per order or 0.03% (whichever is lower)
- **STT/CTT**: 0.025% on sell side
- **Transaction Charges**: 
  - NSE: 0.00297%
  - BSE: 0.00375%
- **GST**: 18% on (brokerage + transaction charges)
- **SEBI Charges**: ₹10 per crore
- **Stamp Duty**: 0.003% on buy side

##### Futures
- **Brokerage**: ₹20 per order or 0.03% (whichever is lower)
- **STT/CTT**: 0.02% on sell side (on premium)
- **Transaction Charges**: NSE: 0.00173%
- **GST**: 18% on (brokerage + transaction charges)
- **SEBI Charges**: ₹10 per crore
- **Stamp Duty**: 0.002% on buy side

##### Options
- **Brokerage**: ₹20 per order (flat)
- **STT/CTT**: 0.1% on sell side (on premium)
- **Transaction Charges**: 
  - NSE: 0.03503%
  - BSE: 0.0325%
- **GST**: 18% on (brokerage + transaction charges)
- **SEBI Charges**: ₹10 per crore
- **Stamp Duty**: 0.003% on buy side

#### Usage Example

```python
from sysstra.sysstra_utils import calculate_brokerage

# Equity Intraday
charges, net_pnl = calculate_brokerage(
    buy_price=1000,
    sell_price=1050,
    quantity=100,
    broker="zerodha",
    market_type="equity",
    holding_type="intraday",
    position_type="LONG",
    no_of_orders=2,
    market="IN",
    exchange="NSE"
)

# Options Trading
charges, net_pnl = calculate_brokerage(
    buy_price=100,
    sell_price=150,
    quantity=75,  # 1 lot
    broker="zerodha",
    market_type="options",
    position_type="LONG",
    no_of_orders=2,
    exchange="NSE"
)

# Futures Trading
charges, net_pnl = calculate_brokerage(
    buy_price=18000,
    sell_price=18200,
    quantity=50,  # 1 lot
    broker="zerodha",
    market_type="futures",
    position_type="LONG",
    no_of_orders=2,
    exchange="NSE"
)
```

#### Order Execution

```python
from sysstra.orders import place_lt_order

# Place equity order
status, response = place_lt_order(
    symbol="RELIANCE",
    exchange="NSE",
    quantity=10,
    lot_size=1,
    transaction_type="BUY",
    order_type="MARKET",
    asset_type="EQUITY",
    holding_type="INTRADAY",
    credential_id="your-zerodha-credential-id"
)

# Place options order
status, response = place_lt_order(
    symbol="NIFTY24DECFUT",
    exchange="NFO",
    quantity=1,
    lot_size=50,
    transaction_type="BUY",
    order_type="LIMIT",
    order_price=45500,
    asset_type="OPTIONS",
    option_type="CE",
    strike_price=24000,
    underlying="NIFTY",
    expiry_date="2024-12-26",
    holding_type="INTRADAY",
    credential_id="your-zerodha-credential-id"
)
```

#### Notes
- Maximum 5 orders per second per credential
- Zerodha credentials are required for live trading
- Paper trading available without broker credentials

---

## US Brokers

### Interactive Brokers

**Broker Code**: `"interactive_brokers"` or `"ibkr"`

**Supported Markets**: US equities, options, futures

#### Fee Structure

##### Equities (Tiered Pricing)
- **Commission**: $0.0035 per share
- **Minimum**: $0.35 per order
- **Maximum**: 0.5% of trade value
- **SEC Fee**: $27.80 per $1,000,000 of sale (sell side only)
- **FINRA TAF**: $0.000166 per share (sell side only, max $8.30)

##### Options
- **Commission**: $0.65 per contract
- **Minimum**: $0.50 per order
- **Options Regulatory Fee (ORF)**: $0.0455 per contract
- **FINRA TAF**: $0.002 per contract (sell side only, max $5.95)
- **SEC Fee**: $27.80 per $1,000,000 of sale

##### Futures
- **Commission**: $0.85 per contract (US futures)
- **Exchange Fees**: Varies by exchange (~$1.50 per contract typical for CME)
- **NFA Fee**: $0.02 per contract

#### Usage Example

```python
from sysstra.sysstra_utils import calculate_brokerage

# US Equities
charges, net_pnl = calculate_brokerage(
    buy_price=150.50,
    sell_price=155.75,
    quantity=100,
    broker="interactive_brokers",
    market_type="equity",
    position_type="LONG",
    market="US"
)

# US Options
charges, net_pnl = calculate_brokerage(
    buy_price=5.50,
    sell_price=7.20,
    quantity=100,  # 1 contract = 100 shares
    lot_size=100,
    broker="ibkr",
    market_type="options",
    position_type="LONG",
    market="US"
)

# US Futures
charges, net_pnl = calculate_brokerage(
    buy_price=4500,
    sell_price=4550,
    quantity=1,
    lot_size=1,
    broker="interactive_brokers",
    market_type="futures",
    position_type="LONG",
    market="US"
)
```

#### Order Execution

```python
from sysstra.orders import place_lt_order

# Place equity order
status, response = place_lt_order(
    symbol="AAPL",
    exchange="NASDAQ",
    quantity=100,
    lot_size=1,
    transaction_type="BUY",
    order_type="LIMIT",
    order_price=150.50,
    asset_type="EQUITY",
    credential_id="your-ibkr-credential-id"
)
```

#### Notes
- IBKR Pro account required for these rates
- IBKR Lite has $0 commissions but limited features
- Real-time market data subscription may be required (separate fee)
- Minimum account balance: $0 for cash accounts, $25,000 for pattern day traders

---

### Charles Schwab

**Broker Code**: `"schwab"`

**Supported Markets**: US equities, options

#### Fee Structure

##### Equities
- **Commission**: $0 (commission-free)
- **SEC Fee**: $27.80 per $1,000,000 of sale
- **FINRA TAF**: $0.000166 per share (max $8.30 per trade)

##### Options
- **Commission**: $0 per trade + $0.65 per contract
- **Regulatory Fee**: $0.04 per contract (sell side only)

#### Usage Example

```python
from sysstra.sysstra_utils import calculate_brokerage

# US Equities
charges, net_pnl = calculate_brokerage(
    buy_price=50.00,
    sell_price=55.00,
    quantity=200,
    broker="schwab",
    market_type="equity",
    position_type="LONG",
    market="US"
)

# US Options
charges, net_pnl = calculate_brokerage(
    buy_price=3.50,
    sell_price=4.80,
    quantity=100,
    lot_size=100,
    broker="schwab",
    market_type="options",
    position_type="LONG",
    market="US"
)
```

#### Notes
- No minimum account balance for standard accounts
- Pattern day trading rules apply ($25,000 minimum)
- Real-time quotes included for free
- No inactivity fees

---

## Crypto Exchanges

### Binance

**Broker Code**: `"binance"`

**Supported Markets**: Crypto spot and futures

#### Fee Structure

##### Spot Trading
- **Maker Fee**: 0.1%
- **Taker Fee**: 0.1%
- **Fee Discount**: Available with BNB (25% off)

##### Futures Trading
- **Maker Fee**: 0.02%
- **Taker Fee**: 0.04%
- **Funding Rate**: Varies (typically 0.01% every 8 hours for perpetual futures)

#### Usage Example

```python
from sysstra.sysstra_utils import calculate_brokerage

# Spot Trading
charges, net_pnl = calculate_brokerage(
    buy_price=45000,  # BTC price
    sell_price=47000,
    quantity=0.5,  # 0.5 BTC
    broker="binance",
    market_type="spot",
    order_type="MARKET",  # or "LIMIT" for maker fees
    position_type="LONG"
)

# Futures Trading
charges, net_pnl = calculate_brokerage(
    buy_price=45000,
    sell_price=47000,
    quantity=1,  # 1 BTC contract
    broker="binance",
    market_type="futures",
    order_type="LIMIT",  # Maker
    position_type="LONG"
)
```

#### Notes
- VIP levels available with reduced fees for high-volume traders
- Leverage up to 125x on futures (region dependent)
- Funding rates apply to perpetual futures positions held across funding times
- Market orders are always takers

---

### CoinDCX

**Broker Code**: `"coindcx"`

**Supported Markets**: Indian crypto exchange

#### Fee Structure

- **Trading Fee**: 0.5% (both buy and sell)
- **Maker/Taker**: Same fee for both

#### Usage Example

```python
from sysstra.sysstra_utils import calculate_brokerage

# Crypto Trading
charges, net_pnl = calculate_brokerage(
    buy_price=3500000,  # BTC in INR
    sell_price=3700000,
    quantity=0.1,  # 0.1 BTC
    broker="coindcx",
    position_type="LONG"
)
```

#### Notes
- Flat fee structure (no maker/taker difference)
- INR deposits/withdrawals may have additional bank charges
- KYC verification required
- Subject to Indian crypto regulations

---

## Fee Comparison

### Equity Trading (100 shares @ $100, sold @ $110)

| Broker | Market | Type | Commission | Other Fees | Total Charges | Net P&L |
|--------|--------|------|------------|------------|---------------|---------|
| Zerodha | India | Intraday | ₹40 | ~₹45 | ~₹85 | ~₹915 |
| IBKR | US | Cash | $0.70 | ~$0.50 | ~$1.20 | ~$998.80 |
| Schwab | US | Cash | $0 | ~$0.20 | ~$0.20 | ~$999.80 |

### Options Trading (1 contract bought @ $5, sold @ $7)

| Broker | Market | Commission | Regulatory | Total Charges | Net P&L |
|--------|--------|------------|------------|---------------|---------|
| Zerodha | India (75 qty) | ₹40 | ~₹135 | ~₹175 | ~₹14,825 |
| IBKR | US (100 qty) | $1.30 | ~$5.00 | ~$6.30 | ~$193.70 |
| Schwab | US (100 qty) | $1.30 | ~$0.10 | ~$1.40 | ~$198.60 |

### Crypto Trading (0.1 BTC bought @ $45,000, sold @ $47,000)

| Broker | Type | Fee | Total Charges | Net P&L |
|--------|------|-----|---------------|---------|
| Binance | Spot (Taker) | 0.1% + 0.1% | ~$9.20 | ~$190.80 |
| Binance | Futures (Maker) | 0.02% + 0.04% | ~$2.76 | ~$197.24 |
| CoinDCX | Spot | 0.5% + 0.5% | ~$46 | ~$154 |

*Note: Calculations are approximate and may vary based on exact trade parameters.*

---

## Important Notes

### API Keys and Security

- Never share or commit API keys to version control
- Use environment variables or secure credential management
- Enable IP whitelisting when available
- Use read-only API keys for market data
- Separate credentials for trading (write access)

### Market Data Requirements

- **Zerodha**: Requires active trading account
- **IBKR**: May require market data subscription ($10-30/month depending on exchanges)
- **Schwab**: Free real-time quotes included
- **Binance/CoinDCX**: Free market data with API access

### Credential Setup

Each broker requires specific credential setup through the Sysstra orders API:

```python
# Credentials are managed through the orders API
# Contact your broker for API access
credential_id = "your-credential-id-from-sysstra-dashboard"
```

### Regulatory Compliance

- **India**: SEBI regulations apply. PAN card and KYC verification required.
- **US**: SEC and FINRA regulations. Pattern Day Trader rules apply for accounts under $25,000 making 4+ day trades in 5 days.
- **Crypto**: Regulations vary by jurisdiction. Tax implications apply.

### Support

For broker-specific issues:
- Zerodha: https://support.zerodha.com
- Interactive Brokers: https://www.interactivebrokers.com/support
- Schwab: https://www.schwab.com/contact-us
- Binance: https://www.binance.com/support
- CoinDCX: https://support.coindcx.com

For Sysstra integration issues, please open an issue on GitHub or contact support@sysstra.com.
