# SysStra Project: Architecture Overview

**Last Updated**: 2025-06-20  
**Scope**: System-wide architecture for 12 interconnected repositories  
**Audience**: Developers, architects, devops engineers  

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Repository Inventory](#repository-inventory)
3. [Architecture Diagram](#architecture-diagram)
4. [Data Flow](#data-flow)
5. [Integration Matrix](#integration-matrix)
6. [Deployment Topology](#deployment-topology)
7. [Shared Concepts & Patterns](#shared-concepts--patterns)
8. [Technology Stack](#technology-stack)
9. [Security Model](#security-model)
10. [Version Compatibility](#version-compatibility)
11. [Development Workflow](#development-workflow)

---

## System Overview

### What is SysStra?

**SysStra** is an end-to-end **algorithmic trading platform** enabling traders and developers to:
- Build, backtest, and deploy trading strategies across multiple asset classes and exchanges
- Access historical and real-time market data with unified API
- Execute orders in live, paper-trading, and backtesting modes
- Analyze performance with advanced reporting and analytics

### Core Capabilities

| Capability | Owned By | Key Features |
|------------|----------|--------------|
| **Strategy Development** | sysstra-core (lib) | 40+ indicators, swing detection, PnL calculations |
| **Historical Data** | sysstra-data-api | EOD, intraday, futures, options (multiple exchanges) |
| **Live Data Streaming** | sysstra-live-streaming | Real-time price feeds, websocket, low latency |
| **Order Execution** | sysstra-orders-api | Multi-broker, multi-asset, multiple order types |
| **Backtesting** | sysstra-backtest-runner | Historical simulation, walk-forward, Monte Carlo |
| **Broker Integration** | sysstra-broker-gateway | Zerodha, Interactive Brokers, Schwab, Binance |
| **Analytics & Reporting** | sysstra-analytics | Performance metrics, drawdown, equity curve |
| **Authentication** | sysstra-auth-service | API key management, rate limiting, audit logs |
| **Caching & Performance** | sysstra-cache-layer | Redis wrapper, session management |
| **Data Persistence** | sysstra-database | MongoDB schema, migrations, backups |
| **User Interface** | sysstra-web-dashboard | Web-based monitoring, strategy management |
| **Developer Tools** | sysstra-cli | Command-line interface, local testing |

### Design Principles

1. **Separation of Concerns**: Each repo owns specific domain (data, orders, auth, etc.)
2. **API-First**: Services communicate via REST APIs with clear contracts
3. **Stateless Services**: Horizontal scaling through load balancers
4. **Single Source of Truth**: Data stored in MongoDB, cached in Redis
5. **Event-Driven**: Services emit events (order_placed, position_updated) via message queue
6. **Multi-Tenant Ready**: User isolation, role-based access, audit logging

---

## Repository Inventory

### 12 Core Repositories

| Repo | Role | Language | Type | Primary Function |
|------|------|----------|------|-----------------|
| **sysstra-core** | Client Library | Python | Library | Strategy coding, indicators, utilities |
| **sysstra-data-api** | Backend Service | Python | FastAPI | Historical market data fetching |
| **sysstra-live-streaming** | Backend Service | Go | WebSocket | Real-time price feeds, tick data |
| **sysstra-orders-api** | Backend Service | Python | FastAPI | Order placement, execution, management |
| **sysstra-broker-gateway** | Backend Service | Python | FastAPI | Broker connectivity (Zerodha, IB, Schwab, Binance) |
| **sysstra-backtest-runner** | Backend Service | Python | Flask | Backtesting engine, strategy simulation |
| **sysstra-analytics** | Backend Service | Python | FastAPI | Performance metrics, reporting, analytics |
| **sysstra-auth-service** | Backend Service | Python | FastAPI | API key validation, user management, RBAC |
| **sysstra-cache-layer** | Backend Service | Node.js | Express | Redis wrapper, session management |
| **sysstra-database** | Infrastructure | SQL/Scripts | Migrations | MongoDB schema, indexes, backups |
| **sysstra-web-dashboard** | Frontend | React/TypeScript | Web App | Strategy management, portfolio monitoring |
| **sysstra-cli** | Developer Tool | Python | CLI | Local testing, strategy scaffolding, debugging |

---

## Architecture Diagram

### High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           END USERS                                  │
│  (Traders, Quants, Developers)                                       │
└────────┬────────────────────────────────┬────────────────────────────┘
         │                                │
         ▼                                ▼
┌────────────────────┐        ┌──────────────────────┐
│  sysstra-cli       │        │  sysstra-web-       │
│  (Command Line)    │        │  dashboard          │
│                    │        │  (Web UI)           │
└────────┬───────────┘        └──────────┬──────────┘
         │                               │
         │   ┌─────────────────────────┼─────────────────────┐
         │   │                         │                     │
         │   ▼                         ▼                     ▼
         │  ┌──────────────────────────────────────────────────┐
         │  │         sysstra-core (Python Library)           │
         │  │  ┌────────────────────────────────────────────┐ │
         │  │  │ • 40+ Indicators (EMA, RSI, MACD, ADX...) │ │
         │  │  │ • Swing Detection & Market Structure      │ │
         │  │  │ • PnL Calculations & Brokerage           │ │
         │  │  │ • Granularity Conversion                 │ │
         │  │  │ • Performance Reporting                  │ │
         │  │  │ • Vendored pandas_ta (v0.3.81b0)        │ │
         │  │  └────────────────────────────────────────────┘ │
         │  └─────────────────┬────────────────────────────────┘
         │                    │
         │    ┌───────────────┼───────────────┬───────────────┐
         │    │               │               │               │
         ▼    ▼               ▼               ▼               ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ sysstra-         │  │ sysstra-orders   │  │ sysstra-backtest │  │ sysstra-         │
│ data-api         │  │ -api             │  │ -runner          │  │ analytics        │
│                  │  │                  │  │                  │  │                  │
│ Historical Data  │  │ Order Management │  │ Strategy Testing │  │ Performance      │
│ Fetching         │  │ Position Tracking│  │ Walk-Forward     │  │ Reporting        │
│                  │  │ State Machine    │  │ Monte Carlo      │  │ Risk Analysis    │
└──────┬───────────┘  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
       │                       │                     │                     │
       │                       ▼                     │                     │
       │              ┌──────────────────┐          │                     │
       │              │ sysstra-broker   │          │                     │
       │              │ -gateway         │          │                     │
       │              │                  │          │                     │
       │              │ Multi-Broker     │          │                     │
       │              │ Integration      │          │                     │
       │              │ (Zerodha, IB,    │          │                     │
       │              │  Schwab, Binance)│          │                     │
       │              └────────┬─────────┘          │                     │
       │                       │                    │                     │
       │    ┌──────────────────┼────────────────┬───┘                    │
       │    │                  │                │                        │
       │    ▼                  ▼                ▼                        │
       │  ┌─────────────────────────────────────────────┐              │
       │  │       BACKEND DATA SERVICES                 │              │
       │  │  ┌──────────────────────────────────────┐  │              │
       │  │  │ sysstra-live-streaming (Go/WebSocket)  │  │              │
       │  │  │ • Real-time price feeds               │  │              │
       │  │  │ • Tick data streaming                 │  │              │
       │  │  │ • Multiple exchange connectors        │  │              │
       │  │  └──────────────────────────────────────┘  │              │
       │  └─────────────────┬──────────────────────────┘              │
       │                    │                                         │
       │    ┌───────────────┼───────────────┐                        │
       │    │               │               │                        │
       │    ▼               ▼               ▼                        │
       │  ┌──────────────────┐  ┌──────────────────┐   ┌────────────┴──────┐
       │  │ sysstra-auth-    │  │ sysstra-cache    │   │ sysstra-database  │
       │  │ service          │  │ -layer           │   │ (MongoDB Schema)  │
       │  │                  │  │                  │   │                   │
       │  │ • API Key Mgmt   │  │ • Redis Wrapper  │   │ • User Data       │
       │  │ • Rate Limiting  │  │ • Session Mgmt   │   │ • Orders & Trades │
       │  │ • RBAC           │  │ • Order Cache    │   │ • Strategies      │
       │  │ • Audit Logs     │  │ • Price Cache    │   │ • Analytics Data  │
       │  └──────────────────┘  └──────────────────┘   └───────────────────┘
       │
       └──────────────────────────────┐
                                      ▼
                        ┌──────────────────────┐
                        │  EXTERNAL SERVICES   │
                        │  • NSE/BSE (India)   │
                        │  • NYSE/NASDAQ (US)  │
                        │  • Binance (Crypto)  │
                        │  • CoinDCX (Crypto)  │
                        │  • Brokers (APIs)    │
                        └──────────────────────┘
```

### Component Responsibilities

```
FRONTEND LAYER
├── sysstra-cli ........................ Command-line tools for local dev
└── sysstra-web-dashboard ............. React web app for portfolio mgmt

CLIENT LIBRARY LAYER
└── sysstra-core ....................... Python lib: indicators, swing, utils

API GATEWAY LAYER
├── Authentication/Rate Limiting (sysstra-auth-service)
└── Load Balancing (reverse proxy, not in repos)

BACKEND SERVICES LAYER
├── Data Services
│   ├── sysstra-data-api ............... Historical OHLCV data
│   └── sysstra-live-streaming ........ Real-time price feeds
├── Execution Services
│   ├── sysstra-orders-api ............ Order placement & tracking
│   └── sysstra-broker-gateway ........ Broker connectivity
├── Analysis Services
│   ├── sysstra-backtest-runner ....... Backtesting engine
│   └── sysstra-analytics ............. Performance reporting
└── Infrastructure Services
    ├── sysstra-cache-layer ............ Redis wrapper
    └── sysstra-database ............... MongoDB schema

DATA LAYER
├── MongoDB ............................ Persistent storage (orders, strategies, user data)
├── Redis ............................. Cache layer (order state, prices, sessions)
└── External Data Providers ........... NSE, BSE, Binance, brokers
```

---

## Data Flow

### 1. Strategy Development & Backtesting Flow

```
Developer writes strategy in Python
           ↓
    sysstra-core (library)
           ↓
   fetch_eod_candles()
           ↓
    sysstra-data-api
           ↓
    MongoDB (historical data)
           ↓
    DataFrame with OHLCV
           ↓
   apply_indicators()
           ↓
   calculate_swing()
           ↓
   Strategy logic (generate signals)
           ↓
   Execute via place_bt_order()
           ↓
    sysstra-backtest-runner
           ↓
    Simulate fills (FIFO, market impact)
           ↓
    Track positions & PnL
           ↓
    sysstra-analytics
           ↓
    generate_mt_report()
           ↓
    Performance metrics (Sharpe, drawdown, win rate)
           ↓
    Return to developer
```

### 2. Live Trading Flow

```
Trader deploys strategy (sysstra-cli or web-dashboard)
           ↓
    sysstra-core (library)
           ↓
   fetch_index_candles() [1-min granularity]
           ↓
    sysstra-live-streaming (WebSocket)
           ↓
    Real-time price data
           ↓
   Strategy logic generates BUY signal
           ↓
   place_lt_order(symbol, quantity, ...)
           ↓
    sysstra-orders-api
           ↓
    Validate order (size, risk limits)
           ↓
    sysstra-broker-gateway
           ↓
    Forward to broker API (Zerodha, IB, Schwab)
           ↓
    Broker executes order
           ↓
    Order confirmation returned
           ↓
    Save to MongoDB (persistent)
           ↓
    Cache in Redis (fast lookups)
           ↓
    Send event: "order_placed"
           ↓
    Update portfolio in sysstra-analytics
           ↓
    Push notification to web-dashboard
           ↓
    Trader sees position update in real-time
```

### 3. Authentication & Authorization Flow

```
Developer calls API (e.g., POST /fetch-eod-data)
           ↓
    Request includes x-api-key header
           ↓
    sysstra-auth-service
           ↓
    Validate API key against MongoDB
           ↓
    Check user's rate limit quota (Redis)
           ↓
    Validate against RBAC policy (viewer/trader/admin)
           ↓
    If valid:
        ├─ Increment rate limit counter (Redis)
        ├─ Forward to target service (data-api, orders-api, etc.)
        ├─ Log access for audit trail
        └─ Return response
           ↓
    If invalid:
        ├─ Log security event
        └─ Return 401/403 error
```

### 4. Real-Time Price Update Flow

```
Market open
           ↓
    NSE/BSE/Binance sends price tick
           ↓
    sysstra-live-streaming (Go service)
           ↓
    Connect via WebSocket/FIX/API
           ↓
    Receive tick (symbol, price, time, volume)
           ↓
    Validate tick (no duplicates, correct sequence)
           ↓
    Write to Redis (price cache, latest price per symbol)
           ↓
    Publish event to WebSocket subscribers
           ↓
    Clients (web-dashboard, traders using sysstra-core)
           ↓
    Receive real-time price update
           ↓
    Update local candle (OHLCV for 1-min bar)
           ↓
    Trigger strategy logic (if price crosses threshold)
           ↓
    Potentially place order
```

---

## Integration Matrix

### Service-to-Service Communication

| Source | → | Target | Protocol | Purpose | Auth |
|--------|---|--------|----------|---------|------|
| sysstra-core | → | sysstra-data-api | REST | Fetch historical data | API key |
| sysstra-core | → | sysstra-orders-api | REST | Place orders | API key |
| sysstra-core | → | sysstra-live-streaming | WebSocket | Subscribe to price feeds | API key |
| sysstra-orders-api | → | sysstra-broker-gateway | REST | Execute on broker | Internal JWT |
| sysstra-orders-api | → | sysstra-auth-service | REST | Validate user | Service-to-service |
| sysstra-backtest-runner | → | sysstra-data-api | REST | Fetch historical data | Service token |
| sysstra-backtest-runner | → | sysstra-analytics | REST | Send backtest results | Service token |
| sysstra-analytics | → | sysstra-database | MongoDB Driver | Store reports | Direct connection |
| sysstra-cache-layer | → | Redis | Redis Protocol | Cache operations | Local connection |
| sysstra-database | → | MongoDB | MongoDB Driver | Data persistence | Direct connection |
| sysstra-live-streaming | → | Redis | Redis Protocol | Publish price updates | Local connection |
| sysstra-web-dashboard | → | sysstra-auth-service | REST | Login & token refresh | OAuth2 / JWT |
| sysstra-web-dashboard | → | sysstra-analytics | REST | Fetch portfolio data | JWT |
| sysstra-cli | → | sysstra-core | Python Import | Strategy execution | Local |
| sysstra-cli | → | sysstra-backtest-runner | REST | Submit backtest job | API key |

### External Service Dependencies

| Service | Type | Used By | Purpose |
|---------|------|---------|---------|
| NSE API | REST | sysstra-data-api, sysstra-live-streaming | Equity data, live prices |
| BSE API | REST | sysstra-data-api, sysstra-live-streaming | Equity data, live prices |
| Zerodha API | REST | sysstra-broker-gateway | Order execution, position mgmt |
| Interactive Brokers API | REST/Socket | sysstra-broker-gateway | Order execution, real-time data |
| Schwab API | REST | sysstra-broker-gateway | US equity/options orders |
| Binance API | REST/WebSocket | sysstra-broker-gateway, sysstra-live-streaming | Crypto orders & prices |
| CoinDCX API | REST | sysstra-broker-gateway | Crypto orders |
| MongoDB | Native | All backend services | Data persistence |
| Redis | Native | sysstra-cache-layer, all services | Cache & session mgmt |

---

## Deployment Topology

### Development Environment (Local)

```
Developer Laptop
│
├── sysstra-cli (Python)
│   └── → localhost:8000 (local backend services)
│
├── sysstra-core (Python lib)
│   └── → import locally
│
├── Backend Services (Docker containers)
│   ├── sysstra-data-api:8001
│   ├── sysstra-orders-api:8002
│   ├── sysstra-backtest-runner:8003
│   ├── sysstra-analytics:8004
│   ├── sysstra-auth-service:8005
│   ├── sysstra-live-streaming:8006
│   └── sysstra-cache-layer:8007
│
├── Databases (Docker containers)
│   ├── MongoDB (port 27017)
│   └── Redis (port 6379)
│
└── External (real or mock)
    ├── NSE test API (staging)
    ├── Zerodha test API (sandbox)
    └── Binance testnet
```

**Start Script**:
```bash
cd sysstra-development
docker-compose up -d
# Brings up all services with shared MongoDB & Redis
```

### Staging Environment (Shared Server)

```
Staging Server (EC2 / DigitalOcean)
│
├── Load Balancer (Nginx)
│   │
│   ├── sysstra-data-api:3
│   ├── sysstra-orders-api:3
│   ├── sysstra-backtest-runner:2
│   ├── sysstra-analytics:2
│   ├── sysstra-auth-service:2
│   └── sysstra-live-streaming:1 (stateful)
│
├── Shared Databases
│   ├── MongoDB (3-node replica set)
│   └── Redis (sentinel + replicas)
│
└── Monitoring
    ├── Prometheus (metrics)
    └── Grafana (dashboards)
```

**Deployment**:
```bash
# Update image in docker-compose.yml
docker pull registry.sysstra.com/sysstra-data-api:v0.1.4
docker-compose -f docker-compose.staging.yml up -d
```

### Production Environment (Kubernetes)

```
Kubernetes Cluster
│
├── Namespace: sysstra-prod
│   │
│   ├── Deployment: sysstra-data-api (replicas: 5)
│   ├── Deployment: sysstra-orders-api (replicas: 5)
│   ├── Deployment: sysstra-backtest-runner (replicas: 3)
│   ├── Deployment: sysstra-analytics (replicas: 3)
│   ├── Deployment: sysstra-auth-service (replicas: 3)
│   ├── StatefulSet: sysstra-live-streaming (replicas: 2)
│   └── Deployment: sysstra-cache-layer (replicas: 2)
│
├── Ingress: API Gateway (TLS, rate limiting)
│
├── StatefulSets (Databases)
│   ├── MongoDB (5-node replica set, persistent volumes)
│   └── Redis (3-node cluster, persistent volumes)
│
├── ConfigMaps & Secrets
│   ├── config.yaml (service configs)
│   ├── secrets.yaml (API keys, DB credentials)
│   └── RBAC (roles and permissions)
│
└── Monitoring & Logging
    ├── Prometheus (metrics collection)
    ├── Grafana (dashboards)
    ├── ELK Stack (logging)
    └── Alert Manager (PagerDuty integration)
```

**Deployment**:
```bash
# Build and push image
docker build -t registry.sysstra.com/sysstra-data-api:v0.1.4 .
docker push registry.sysstra.com/sysstra-data-api:v0.1.4

# Update Kubernetes deployment
kubectl set image deployment/sysstra-data-api \
  sysstra-data-api=registry.sysstra.com/sysstra-data-api:v0.1.4 \
  -n sysstra-prod

# Verify rollout
kubectl rollout status deployment/sysstra-data-api -n sysstra-prod
```

---

## Shared Concepts & Patterns

### 1. API Response Format

**Success Response** (2xx):
```json
{
  "status": "success",
  "data": { /* actual response data */ },
  "timestamp": "2025-06-20T10:30:00Z",
  "request_id": "req-abc123"
}
```

**Error Response** (4xx/5xx):
```json
{
  "status": "error",
  "error": {
    "code": "INSUFFICIENT_BALANCE",
    "message": "Account has insufficient balance for this order",
    "details": {
      "required": 50000,
      "available": 45000
    }
  },
  "timestamp": "2025-06-20T10:30:00Z",
  "request_id": "req-abc123"
}
```

### 2. Authentication & Authorization

**Header-Based API Key**:
```
GET /api/data/fetch-eod
Authorization: Bearer <api-key>
x-api-key: <api-key>
x-client-id: client-123
```

**JWT Token** (for service-to-service):
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**RBAC Roles**:
- `admin`: Full access, user management, system config
- `trader`: Create/execute orders, view portfolio, access data
- `viewer`: Read-only access to data and analytics
- `analyst`: Access to historical data and backtesting, no order placement
- `api_user`: Programmatic access (rate-limited)

### 3. Error Codes (Unified)

| Code | HTTP | Meaning | Recoverable |
|------|------|---------|-------------|
| `INVALID_API_KEY` | 401 | API key missing or invalid | Yes (refresh key) |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests | Yes (wait) |
| `INSUFFICIENT_BALANCE` | 400 | Account balance too low | Yes (deposit funds) |
| `ORDER_REJECTED_BY_BROKER` | 400 | Broker rejected order | Maybe (retry with different params) |
| `MARKET_CLOSED` | 400 | Trading hours not active | Yes (wait for market open) |
| `INVALID_SYMBOL` | 400 | Symbol not found | No (check symbol) |
| `INTERNAL_SERVER_ERROR` | 500 | Backend error | Yes (retry with backoff) |
| `SERVICE_UNAVAILABLE` | 503 | Service down for maintenance | Yes (retry later) |

### 4. Data Format Conventions

**OHLCV Candle** (consistent across all services):
```json
{
  "timestamp": "2025-06-20T09:15:00Z",
  "date": "2025-06-20",
  "open": 100.50,
  "high": 102.75,
  "low": 100.25,
  "close": 101.00,
  "volume": 1500000,
  "oi": null,
  "symbol": "SBIN"
}
```

**Order Object** (MongoDB document):
```json
{
  "_id": "order-12345",
  "user_id": "user-xyz",
  "symbol": "SBIN",
  "quantity": 100,
  "transaction_type": "BUY",
  "order_type": "MARKET",
  "status": "FILLED",
  "filled_quantity": 100,
  "filled_price": 550.25,
  "created_at": "2025-06-20T09:30:00Z",
  "filled_at": "2025-06-20T09:30:01Z"
}
```

**Position Object** (portfolio state):
```json
{
  "symbol": "SBIN",
  "quantity": 100,
  "entry_price": 550.00,
  "current_price": 555.00,
  "position_type": "LONG",
  "unrealized_pnl": 500.00,
  "unrealized_pnl_percent": 0.91
}
```

### 5. Event Formats

**Event: Order Placed**:
```json
{
  "event_type": "order_placed",
  "timestamp": "2025-06-20T09:30:00Z",
  "order_id": "order-12345",
  "user_id": "user-xyz",
  "symbol": "SBIN",
  "quantity": 100,
  "order_type": "MARKET",
  "metadata": { /* order details */ }
}
```

**Event: Position Updated**:
```json
{
  "event_type": "position_updated",
  "timestamp": "2025-06-20T09:30:01Z",
  "user_id": "user-xyz",
  "symbol": "SBIN",
  "quantity": 100,
  "unrealized_pnl": 500.00,
  "metadata": { /* position details */ }
}
```

**Event Stream**: Published to Redis pub/sub for real-time subscribers.

### 6. Retry & Backoff Strategy

**Exponential Backoff**:
```
Attempt 1: immediate
Attempt 2: wait 1s + random(0-100ms)
Attempt 3: wait 2s + random(0-100ms)
Attempt 4: wait 4s + random(0-100ms)
Attempt 5: wait 8s + random(0-100ms)
Max: 5 attempts, ~15 seconds total
```

**Idempotency Keys** (for order placement):
```
x-idempotency-key: order-2025-06-20-001
# Server deduplicates duplicate requests within 24 hours
```

### 7. Logging Standards

**Log Format** (structured):
```json
{
  "timestamp": "2025-06-20T09:30:00.123Z",
  "level": "INFO",
  "service": "sysstra-orders-api",
  "request_id": "req-abc123",
  "user_id": "user-xyz",
  "message": "Order placed successfully",
  "data": {
    "order_id": "order-12345",
    "symbol": "SBIN",
    "quantity": 100
  },
  "duration_ms": 45
}
```

**Log Levels**:
- `DEBUG`: Detailed diagnostic info (local dev only)
- `INFO`: Normal operations (order placed, user logged in)
- `WARN`: Potentially harmful (rate limit approaching, slow query)
- `ERROR`: Error condition (order rejected, database unavailable)
- `FATAL`: System-level failure (database crash, core service down)

### 8. Version Compatibility Matrix

| sysstra-core | data-api | orders-api | auth-service | live-streaming | backtest-runner |
|--------------|----------|-----------|--------------|-----------------|-----------------|
| 0.1.4.6.3 | 0.2.x | 0.3.x | 0.1.x | 0.1.x | 0.2.x |
| 0.1.5.x | 0.3.x | 0.4.x | 0.2.x | 0.2.x | 0.3.x |

---

## Technology Stack

### Languages & Runtimes

| Language | Used By | Reason |
|----------|---------|--------|
| Python 3.9+ | sysstra-core, data-api, orders-api, analytics, auth, backtest, cli | Rich ecosystem (pandas, numpy), rapid development |
| Go 1.19+ | sysstra-live-streaming | High concurrency, low-latency WebSocket handling |
| TypeScript | sysstra-web-dashboard | Type safety, React ecosystem |
| JavaScript/Node.js | sysstra-cache-layer | Lightweight, event-driven, Redis client |
| SQL/Shell | sysstra-database | Schema management, backups, migrations |

### Web Frameworks

| Framework | Service | Reason |
|-----------|---------|--------|
| FastAPI | data-api, orders-api, analytics, auth | Fast, async, OpenAPI auto-docs |
| Flask | backtest-runner | Lightweight, job queue compatible |
| Express | cache-layer | Simple, event-driven |
| React | web-dashboard | Component-based, real-time updates |

### Data Stores

| Store | Primary Use | Secondary Use |
|-------|-------------|----------------|
| MongoDB | Orders, users, strategies, analytics | Audit logs, backtest reports |
| Redis | Price cache, session mgmt, order state | Rate limiting, real-time events |
| PostgreSQL | (Optional) Time-series data | Backtest results, performance metrics |

### Message Queue (Optional but Recommended)

| Queue | Use Case |
|-------|----------|
| Redis Pub/Sub | Real-time events (order placed, price updated) |
| RabbitMQ | (Optional) Job queues for backtest runner |
| Kafka | (Optional future) High-volume event streaming |

### Monitoring & Observability

| Tool | Purpose |
|------|---------|
| Prometheus | Metrics collection (request latency, error rate, CPU/memory) |
| Grafana | Dashboards and alerting |
| ELK Stack (Elasticsearch, Logstash, Kibana) | Centralized logging |
| Jaeger | Distributed tracing (request flow across services) |
| PagerDuty | On-call incident management |

---

## Security Model

### Authentication Layers

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ API Key / JWT
       ▼
┌──────────────────┐
│ Reverse Proxy    │
│ (TLS, Rate Limit)│
└──────┬───────────┘
       │
       ▼
┌──────────────────────┐
│ sysstra-auth-service │
│ (Key validation,     │
│  RBAC check)         │
└──────┬───────────────┘
       │
       ▼
┌──────────────────┐
│ Target Service   │
│ (Business Logic) │
└──────────────────┘
```

### Secrets Management

| Secret | Storage | Access | Rotation |
|--------|---------|--------|----------|
| API Keys | MongoDB (hashed) | auth-service | No (issued per user) |
| DB Password | Kubernetes Secret | Services via env var | Annual |
| Broker API Keys | Kubernetes Secret | broker-gateway via env var | Annual or on compromise |
| JWT Secret | Kubernetes Secret | auth-service | 90 days |
| TLS Certificate | Kubernetes Secret | Load balancer | Annual (auto-renewal) |

### Audit Logging

**Audit Trail** (all actions logged):
```json
{
  "timestamp": "2025-06-20T09:30:00Z",
  "action": "order_placed",
  "actor": "user-xyz",
  "resource": "order-12345",
  "details": { /* full order details */ },
  "ip_address": "192.168.1.1",
  "status": "success"
}
```

**Retention**: 7 years (regulatory requirement)

---

## Version Compatibility

### Python Versions

- **sysstra-core**: Python 3.9, 3.10, 3.11, 3.12
- **Backend services**: Python 3.11+ (security patches)
- **Development**: Python 3.12 (latest features)

### API Versioning

- **v1**: Current (stable)
- **v2**: Under development (breaking changes)
- **Deprecation**: v0 removed in 2025-Q3

**Compatibility Policy**:
```
v1 responses always include:
- status: success | error
- data: response payload
- timestamp: ISO 8601
- request_id: request tracking

Breaking changes only in major version (v2, v3, ...)
Minor version: new endpoints, new fields (backwards compatible)
Patch version: bug fixes, security patches
```

### Dependency Updates

| Package | Current | Policy |
|---------|---------|--------|
| requests | 2.32.3 | Minor updates within 3 months |
| pandas | 2.2.0 | Major updates within 6 months |
| numpy | 1.26.4 | Major updates within 6 months |
| FastAPI | 0.115.0 | Latest (auto-updated weekly) |
| MongoDB driver | 4.10.1 | Latest (auto-updated weekly) |

---

## Development Workflow

### Git Branching Strategy

```
main (stable, production releases)
  ├── staging (integration testing)
  │    └─ feature/xxxx (developer branches)
  │    └─ bugfix/xxxx
  │    └─ hotfix/xxxx
  │
  └── release/v0.2.0 (release candidates)
```

**Branching Rules**:
- `feature/*`: New features, must pass CI/CD
- `bugfix/*`: Bug fixes, must include test
- `hotfix/*`: Production patches, require immediate merge to main
- `staging`: Integration branch, all PRs merge here first
- `main`: Only releases and hotfixes

### Pull Request Workflow

1. Developer creates branch (`git checkout -b feature/new-feature`)
2. Commits code with tests
3. Opens PR against `staging` with:
   - Description of changes
   - Link to issue/ticket
   - Test plan (manual verification steps)
4. Automated checks run:
   - Unit tests (`pytest`)
   - Integration tests
   - Code quality (`black`, `mypy`)
   - Security scan
5. Code review (minimum 2 approvals)
6. Merge to `staging`
7. On release:
   - Create release branch (`release/v0.2.0`)
   - Bump version (MAJOR.MINOR.PATCH)
   - Tag commit (`git tag v0.2.0`)
   - Merge to `main`
   - CI/CD triggers deployment

### Release Process

**Release Cadence**: Monthly (first Friday of month)

**Steps**:
1. Freeze feature development (Friday morning)
2. Code review of all pending PRs
3. Testing on staging environment (1 day)
4. Create release notes (CHANGELOG)
5. Tag and merge to main (Friday afternoon)
6. Deploy to production (Saturday early morning, lower traffic)
7. Monitor for 24 hours
8. Announce release (Monday)

### Documentation Updates

- **Breaking Changes**: Update all docs immediately
- **New Features**: Document in sysstra_package_*.md
- **API Changes**: Update OpenAPI schema
- **Examples**: Add to `/examples` directory
- **Migration Guide**: If breaking change, provide examples

---

## Cross-Repo Communication Best Practices

### When to Add a New Repo

**Good Reasons**:
- Service has distinct deployment lifecycle
- Owns specific data domain (no shared state)
- Team ownership differs (different team manages it)
- Technology stack differs (Go vs Python, etc.)

**Bad Reasons**:
- To organize code by layer (use packages instead)
- "Might be useful someday" (wait until needed)
- To enforce separation (use module boundaries)

### Avoiding Circular Dependencies

```
GOOD:
sysstra-core → data-api
sysstra-core → orders-api
data-api → sysstra-database
orders-api → broker-gateway

BAD:
sysstra-core ↔ sysstra-data-api (circular)
data-api → orders-api → data-api (circular)
```

**Resolution**: If circular dependency appears, one service needs refactoring.

### Service Discovery

**Static Routing** (recommended for small systems):
```
sysstra-data-api:     http://data-api.sysstra.local:8001
sysstra-orders-api:   http://orders-api.sysstra.local:8002
sysstra-live-stream:  ws://live.sysstra.local:8006
```

**Dynamic Discovery** (if scaling):
```
All services register with Consul/Eureka on startup
Services query Consul for peer addresses
Load balancer automatically adds/removes instances
```

---

## Appendix: Quick Reference

### Key Files Location

| What | Location |
|------|----------|
| Architecture diagram | `ARCHITECTURE_OVERVIEW.md` (this file) |
| Per-repo docs | `sysstra_package_<repo-name>.md` in each repo |
| API documentation | Each service's `/docs` endpoint (OpenAPI) |
| Database schema | `sysstra-database/schema.mongodb.js` |
| Docker setup | `docker-compose.yml` in each repo |
| Kubernetes manifests | `k8s/` directory in `sysstra-infrastructure` repo |

### Common Commands

```bash
# Local dev setup
git clone https://github.com/sysstra/sysstra-core.git
pip install -e .
docker-compose up -d

# Run tests
pytest tests/

# Format code
black .

# Type check
mypy .

# Build Docker image
docker build -t registry.sysstra.com/sysstra-core:v0.1.4.6.3 .

# Deploy to Kubernetes
kubectl apply -f k8s/deployment.yaml
```

### Contact & Escalation

- **Platform Issues**: Slack #sysstra-platform-eng
- **Data Issues**: Slack #sysstra-data-team
- **On-Call**: PagerDuty (check schedule)
- **Architecture Questions**: Wiki or email arch-team@sysstra.com

---

## Document Versioning

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-06-20 | Initial architecture overview for 12-repo project |

**Last Updated**: 2025-06-20  
**Next Review**: 2025-09-20 (quarterly)
