# Sysstra Re-Architecture Plan: Centralized Core for White-Label Deployments

**Date:** 2026-07-10
**Status:** Proposal
**Scope:** `sysstra` package (PyPI 0.1.4.6.8) and its consumer ecosystem
**Prime directive:** Zero breakage for existing consumers at every phase.

---

## Part 1 — Ground Truth (What Actually Exists)

> Note: the existing `ARCHITECTURE_OVERVIEW.md` describes an aspirational 12-repo
> system (Go streaming, auth-service, Kubernetes, Node cache layer). That is a
> target-state sketch, not reality. This plan is based on what is on disk today.

### 1.1 The package (v0.1.4.6.8, public on PyPI)

| Module | LOC | What it really is |
|---|---|---|
| `config.py` + `__init__.py` | 23 | Global mutable dict; `set_api_key()/set_data_url()/set_orders_url()` |
| `data/historical.py` | 124 | REST client → data API (`x-api-key`), returns raw JSON |
| `data/live.py` | 158 | **Direct Redis reads** of platform key schema (`all_symbols:{sym}`, `{sym}_{strike}_{type}`) |
| `orders/live.py` | 272 | REST → orders API **plus direct MongoDB writes** (`lt_orders`) + Redis pub/sub + alerts |
| `orders/virtual.py` | 103 | Paper trading: direct Mongo (`vt_orders`) + Redis |
| `orders/backtest.py` | 57 | In-memory order list |
| `orders/orders_utils.py` | 286 | Open-position aggregation, orders→trades, brokerage hookup |
| `sysstra_utils.py` | 2,141 | Kitchen sink: `apply_indicators` (518-line dispatcher), `calculate_swing`, granularity, MT reports, brokerage (Zerodha/Binance/CoinDCX/Schwab/IBKR), margin/liquidation, Mongo logging, funds, alerts |
| `custom_indicators.py` | 1,165 | ~35 proprietary indicators |
| `ta/` | 182 files | **Vendored pandas_ta 0.3.81b0** (good call — ends the numpy-compat hell) |
| `tests/` | **empty** | Zero automated tests in the core repo |

Dependencies: `requests`, `numpy>=1.26`, `pandas>=2.0`, `redis==5.0.8` (hard pin), `pymongo>=4`, `numba`, `tqdm`.

### 1.2 The consumers on this machine

| Repo | Pin | Role | Notes |
|---|---|---|---|
| `sysstra-trading-strategies` | `~=0.1.4.6.8` | **Production live/VT runner** — 21 strategies, Celery + Docker, markets IN/US/CRYPTO/MCX | Has its own SDK contract tests (`tests/sdk_registry.py`, signature checks, AST lint) |
| `sysstra-backtesting-strategies` | `==0.1.4.3.3` | 32 backtest strategies | **5 patch-trains behind** — version skew is already live |
| `sysstra-quantgpt`, `quantgpt_poc` | `>=0.1.4` | AI strategy product | Uses data fetch, `apply_indicators`, `create_report` |
| `sysstra-orders-api` | (env install) | **Backend service** | Imports `calculate_brokerage` **from the client SDK** → platform↔SDK circular dependency |
| `sysstra-data-collection-us` | — | Data preloading | `fetch_eod_candles` |
| `trading_strategies`, `interns_task` | — | Research scratch | Some reference **dead APIs** (`sysstra.utils`, `config.Settings`) — casualties of past breaking renames |
| `sysstra-demo` | — | Demo/onboarding | Good canary candidate |

Import style is dominated by `from sysstra.X import *` — **the effective public API
is every symbol in every module.** Any rename anywhere is a breaking change.

### 1.3 Why this package exists (reconstructed intent)

1. **Single source of truth** for strategy-facing primitives: one brokerage formula, one swing algorithm, one report format — shared by backtest, paper, and live paths so results are comparable across modes.
2. **Insulation from dependency hell** — vendoring pandas_ta after repeated numpy/Ubuntu breakage (see git: "Vendor pandas_ta library directly into sysstra").
3. **Distribution channel** — PyPI lets every runner, collector, and product repo `pip install` the same engine.

The intent is right. The problem is that three different libraries are fused into
one namespace, configured by one process-global dict.

---

## Part 2 — Findings That Drive the Design

These are the issues *my own analysis* surfaced — several are more urgent than
white-labeling itself, and the white-label design falls out of fixing them.

### F1. Process-global config makes multi-tenant impossible (blocker)
`config` is one mutable dict per process. Two brands = two API keys = two order
URLs **cannot coexist in one Python process**. Worse, `data/historical.py` does
`api_key = config.get("api_key")` **at import time** — calling `set_api_key()`
after importing the data module silently sends `api_key: None`. Today it only
works because `sts_common.py` happens to call `set_api_key()` *before* the
star-imports. Import order is load-bearing. This is the single most important
thing to fix, and fixing it *is* the white-label enabler.

### F2. The package is three libraries wearing one trench coat
- **Quant core** (pure functions): indicators, ta, swing, granularity, brokerage math, reports. No I/O. This is the crown jewel and the true "centralized package."
- **Public client SDK** (REST): historical data, order placement via API.
- **Platform runtime glue** (privileged): direct Mongo writes, Redis key-schema access, alert plumbing. Requires DB credentials in every strategy process.

These have different consumers, different stability needs, and — critically —
different **confidentiality** needs.

### F3. Internal platform surface is published on public PyPI
Anyone can `pip install sysstra` and read your MongoDB collection names
(`lt_orders`, `vt_trades`), Redis key schema, and internal endpoint names.
White-labeling multiplies the blast radius (per-brand infra details would leak too).

### F4. Platform depends on its own client SDK
`sysstra-orders-api` imports `calculate_brokerage` from the SDK. A bad SDK
release can take down the orders backend. The quant core must be separable so
services depend on math, not on the whole SDK.

### F5. Silent failure in a trading system
Nearly every function is `try/except → print → return None/[]`. A failed live
order save is indistinguishable from success at the call site. Any
re-architecture must introduce structured errors — but **opt-in**, because
consumers today depend on the swallow-and-continue behavior.

### F6. No safety net
Core repo has zero tests; the *consumer* built signature tests to protect itself
(`sdk_registry.py`). That's inverted. Golden-master tests must exist **before**
any code moves.

### F7. Versioning and pinning hygiene
Five-segment versions (`0.1.4.6.8`) defeat `~=` semantics and semver tooling.
`redis==5.0.8` hard pin in a *library* forces that exact version on every
consumer app. Three consumers are on three different pins with no compat matrix.

### F8. Hardcoded business rules block white-labeling
Brokerage fee tables, alert routing (`send_notification` on the orders API),
report formatting, and market calendars are hardcoded. A white-label brand with
a different broker set, fee schedule, or notification channel requires editing
core code today.

---

## Part 3 — Target Architecture

### 3.1 Shape: one repo, one namespace, three layers, two distributions

Keep **a single centralized repo** (explicit requirement) and a single
importable `sysstra` namespace (backward compat). Internally, enforce layers:

```
sysstra/  (monorepo, single git repo)
│
├── src/sysstra/
│   ├── core/                    # LAYER 1 — pure quant, zero I/O
│   │   ├── indicators/          #   registry + custom indicators
│   │   ├── ta/                  #   vendored pandas_ta (moves here)
│   │   ├── swing.py             #   calculate_swing, rolling swing
│   │   ├── candles.py           #   granularity, HKA, merge, patterns
│   │   ├── fees/                #   brokerage engine + fee schedules (data files)
│   │   │   ├── engine.py
│   │   │   └── schedules/       #   zerodha.yaml, ibkr.yaml, binance.yaml, ...
│   │   ├── risk.py              #   margin, liquidation, distribution, quantities
│   │   └── reports.py           #   generate_mt_report, create_report
│   │
│   ├── client/                  # LAYER 2 — public SDK (REST only, no DB creds)
│   │   ├── config.py            #   SysstraConfig (frozen dataclass)
│   │   ├── session.py           #   SysstraClient: retries, timeouts, errors
│   │   ├── data.py              #   historical endpoints
│   │   └── orders.py            #   place/modify/status/poll via API
│   │
│   ├── runtime/                 # LAYER 3 — privileged platform glue (private)
│   │   ├── live_cache.py        #   Redis candle reads (key schema lives here only)
│   │   ├── order_store.py       #   Mongo/Redis order persistence (lt/vt)
│   │   ├── alerts.py            #   alert provider interface + default impl
│   │   └── logging.py           #   mg_insert_log etc.
│   │
│   ├── tenancy/                 # WHITE-LABEL LAYER
│   │   ├── tenant.py            #   TenantContext (see 3.3)
│   │   └── loader.py            #   load tenant.yaml / env / dict
│   │
│   └── [legacy facades]         # sysstra_utils.py, custom_indicators.py,
│       ...                      # data/, orders/, config.py — re-export shims,
│                                # byte-for-byte API compatible (see 3.4)
│
├── tenants/                     # declarative brand packs (see 3.3)
│   ├── _default/tenant.yaml     # == today's sysstra.com behavior
│   └── <brand>/tenant.yaml
│
├── tests/                       # see Part 4
├── tools/                       # release, compat-check, golden-master recorder
└── pyproject.toml               # replaces setup.py
```

**Distributions (Phase 4, not day 1):**
- `sysstra` (public PyPI): `core` + `client` + `tenancy` + legacy facades for them.
- `sysstra-runtime` (private index / git-install / internal artifact): layer 3.
  Until the split ships, the runtime layer keeps shipping inside `sysstra` so
  nothing breaks; the split is a packaging change only.

**Layer rule (CI-enforced):** `core` imports nothing from `client`/`runtime`;
`client` may import `core`; `runtime` may import both. Import-linter in CI.
This immediately resolves F4: `sysstra-orders-api` depends on `sysstra` but only
imports `sysstra.core.fees` — a pure-math dependency it can't be broken by.

### 3.2 Configuration: from global dict to context object

```python
# NEW canonical API (Phase 1)
from sysstra import SysstraClient

client = SysstraClient(
    api_key="...",
    data_url="https://api.data.brand-x.com/",
    orders_url="https://api.orders.brand-x.com/",
    timeout=10,          # finally: real timeouts
    retries=3,           # exponential backoff
    strict_errors=False, # True → raise SysstraError instead of return-None
)
df = client.data.fetch_eod_candles("SBIN", "2026-01-01", "2026-06-30")
```

**Backward compatibility:** `sysstra.set_api_key()` et al. remain forever; they
now configure a lazily-created module-level *default client*. Every legacy
function (`fetch_eod_candles(...)` at module scope) delegates to the default
client. The import-order footgun disappears because config is read **at call
time**, never at import time. This is a strict bug fix: the only behavior that
changes is a case that today silently sends `None` as the API key.

Two brands in one process is now trivial: two `SysstraClient` instances.

### 3.3 White-label = a data problem, not a code problem

A brand is a **TenantContext**: pure data + registered providers. No code fork,
no repo fork, no package fork.

```yaml
# tenants/brand-x/tenant.yaml
tenant: brand-x
display_name: "BrandX Algo"
endpoints:
  data_url: https://api.data.brand-x.com/
  orders_url: https://api.orders.brand-x.com/
markets: [IN, CRYPTO]            # which market calendars/timings apply
brokers: [zerodha, coindcx]      # allowed brokers → fee schedules from core/fees
fee_overrides:                   # optional per-brand negotiated rates
  zerodha: { flat_fee: 15 }
indicators:
  packs: [standard, brand_x_premium]   # registry packs (see below)
alerts:
  provider: webhook              # webhook | orders_api | slack | noop
  url: https://alerts.brand-x.com/hook
reporting:
  brand_name: "BrandX"
  logo: brandx.png
  disclaimer: "..."
```

```python
from sysstra.tenancy import load_tenant
ctx = load_tenant("brand-x")           # or load_tenant(path=..., env=...)
client = ctx.client()                   # pre-configured SysstraClient
fees   = ctx.fees("zerodha")            # brand-aware fee engine
report = ctx.reports.generate(trades)   # brand-styled MT report
```

Three registries make the "sub-modules" pluggable:

1. **Indicator registry** — `apply_indicators`'s 518-line `if/elif` becomes a
   dict of `name → callable` with a decorator (`@register_indicator("VFI")`).
   The legacy function keeps identical behavior (golden-mastered). Brands ship
   *indicator packs* (entry-point plugins or in-repo packs under `tenants/`)
   without touching core.
2. **Fee-schedule registry** — brokerage moves from a 280-line if/elif to
   data-driven YAML schedules interpreted by one engine. Today's numbers are
   snapshotted into `schedules/*.yaml` and golden-master-verified to the rupee.
   New white-label broker = new YAML file.
3. **Alert/report providers** — small interfaces (`send(alert_dict)`,
   `render(report, branding)`), default implementations preserving today's
   behavior exactly.

**Deploying a white-label sub-module** then is: build one wheel from the one
repo, ship `tenant.yaml` + secrets per deployment (env/K8s secret/config
service). One artifact, N brands. Strategy repos select the tenant with one
line (`SYSSTRA_TENANT=brand-x` or `load_tenant()`).

### 3.4 Backward-compatibility contract (non-negotiables)

1. **Every existing import path keeps working**: `sysstra.sysstra_utils`,
   `sysstra.custom_indicators`, `sysstra.data.historical`, `sysstra.data.live`,
   `sysstra.orders.*`, `sysstra.config`, `from sysstra import ta` — all become
   thin re-export facades over the new layout. Because consumers star-import,
   facades re-export **every public symbol**, including the transitive ones
   (e.g. `fetch_eod_candles` must stay reachable via `sysstra.sysstra_utils`
   — quantgpt imports it from there today).
2. **Every function signature is frozen** — enforced by contract tests seeded
   from `sysstra-trading-strategies/tests/sdk_registry.py` (promote that idea
   into the core repo, covering *all* public functions, not 11).
3. **Every numeric output is frozen** — golden-master fixtures (Part 4).
4. **Global `set_api_key()` family never dies.** Deprecation warnings come late
   (Phase 4+), removal has no date.
5. **Error behavior unchanged by default** — `strict_errors` / structured
   exceptions are opt-in per client/tenant.
6. **`redis` pin relaxed to `>=5.0.8,<6`** in the library; the hard pin moves to
   the apps that need it (a library must not dictate exact versions).
7. **Version scheme**: freeze `0.1.4.6.x` as an LTS train (bugfix-only branch
   `lts/0.1.4.6`). New work releases as **`0.2.0` semver**. Publish a
   compatibility matrix in README. `0.2.x` promises: same API, same numbers,
   plus new client/tenancy APIs. `1.0.0` marks the distribution split.
8. **Resurrect nothing silently**: `sysstra.utils` and `config.Settings` (dead
   APIs some research scripts still reference) get facades **only if** those
   repos matter; otherwise they're documented as already-broken-before-this-plan.

---

## Part 4 — Test Strategy ("check against multiple test parameters")

The safety net comes **first** (Phase 0), against the *current* code, so every
subsequent move is provably behavior-preserving.

### 4.1 Golden-master suite (the backbone)
Record current outputs as fixtures; assert equality forever after.

| Target | Fixture inputs | Assertion |
|---|---|---|
| `calculate_swing` | 20+ real OHLCV frames: trending, choppy, gap, outside-bar, 1-row, DST edges | `swing`/`swing_change` columns byte-equal |
| `apply_indicators` | Every one of the 40+ indicator keys × param grid × IN/US/CRYPTO data | numeric columns `allclose(rtol=0)` vs recorded |
| `calculate_brokerage` | Full grid: 5 brokers × {equity, options, futures, crypto} × {intraday, delivery} × {LONG, SHORT} × {NSE, BSE} × qty/lot edge cases | exact to the paisa |
| `change_granularity` | 1m → {5, 15, 60, day} incl. partial candles, market-open boundaries per market | frame-equal |
| `generate_mt_report` / `create_report` | Recorded trade lists (winning, losing, empty, single-trade, LSL exits) | all metrics equal |
| `convert_to_trades`, `check_open_orders` | Recorded order lists from real vt/lt sessions (scrubbed) | dict-equal |
| risk math (`calculate_liquidation_price`, margin, distributions, tick rounding) | boundary grid | exact |

### 4.2 Contract suite (API freeze)
- **Signature registry**: auto-generated snapshot of every public function's
  `inspect.signature` → test fails on any change. (Generalizes the sts repo's
  `sdk_registry.py`.)
- **Namespace snapshot**: `dir()` of every legacy module recorded; a facade that
  drops a symbol fails CI. This is what protects the star-importers.
- **Import-order test**: `import sysstra.data.historical` *then*
  `set_api_key()` *then* fetch → must send the key (regression test for F1).

### 4.3 Integration suite (fakes, no live infra)
- `fakeredis` for `data/live.py` + `order_store` — seed the exact key schema, verify reads/writes/pub-sub channels.
- `mongomock` for vt/lt order saves — verify collection names + document shape.
- `responses` (HTTP mock) for client layer — verify URL joining, headers, payloads, retry/timeout behavior, and the error-shape contract with both APIs.

### 4.4 The parameter matrix (CI)
GitHub Actions matrix:
- **Python**: 3.9, 3.10, 3.11, 3.12 (setup.py claims >=3.9 — currently unverified)
- **pandas/numpy**: min-pins vs latest
- **Tenant**: `_default` + one synthetic brand (different URLs, fee overrides, indicator pack) — the whole suite runs per tenant
- **Consumer smoke jobs**: for each consumer repo pin (`0.1.4.3.3`, `~=0.1.4.6.8`, `>=0.1.4`), install the new wheel and run that consumer's import + signature tests (the sts repo's suite runs as-is against release candidates)

### 4.5 Tenant conformance gate
`sysstra-verify --tenant brand-x.yaml`: schema-validates the pack, resolves fee
schedules, pings endpoints (auth check), renders a sample report, fires a test
alert to the provider. Run at deploy time for every white-label instance.

---

## Part 5 — Phased Execution Plan

Each phase ships independently, is releasable, and is abortable without debt.

### Phase 0 — Safety net (no code moves) — ~1–2 weeks
1. Add `pyproject.toml` (keep setup.py until 0.2.0), CI, and the **golden-master + contract suites against current code**.
2. Record fixtures from v0.1.4.6.8 (the PyPI truth), not from working tree.
3. Branch `lts/0.1.4.6` for emergency fixes to pinned consumers.
4. Relax `redis` pin; verify consumer smoke jobs pass.
   - **Exit criteria:** CI green on the matrix; coverage of every public function by signature test; golden masters for all pure functions.

### Phase 1 — Kill the config footgun; introduce the client — ~1–2 weeks
1. `SysstraConfig` + `SysstraClient` (client layer), lazy config reads everywhere; legacy globals delegate to a default client.
2. Opt-in `timeout`/`retries`/`strict_errors` on the client only; legacy paths untouched.
3. Release **0.2.0**. Consumers change nothing; `sysstra-trading-strategies` may delete its import-order workaround at leisure.
   - **Exit criteria:** import-order regression test passes; two clients with different keys verified in one process; all Phase 0 suites still green.

### Phase 2 — Internal layering + registries — ~2–3 weeks
1. Move code into `core/` / `client/` / `runtime/`; legacy modules become facades. Namespace-snapshot tests prove nothing dropped.
2. `apply_indicators` → indicator registry (dispatcher preserved, goldens prove equality).
3. Brokerage → fee-schedule YAML + engine (goldens to the paisa).
4. Import-linter enforces layer rules; `sysstra-orders-api` moves its import to `sysstra.core.fees` (one-line change, coordinated).
5. Release **0.3.0**.
   - **Exit criteria:** zero golden-master diffs; consumer smoke matrix green; import-linter clean.

### Phase 3 — Tenancy (white-label enablement) — ~2–3 weeks
1. `TenantContext` + YAML loader + `_default` tenant (== today's behavior, golden-mastered).
2. Alert & report provider interfaces; default providers preserve current behavior.
3. Indicator packs via entry points; `sysstra-verify` CLI; tenant docs + template.
4. Pilot: deploy `sysstra-demo` as the first "brand" with its own tenant.yaml.
5. Release **0.4.0**.
   - **Exit criteria:** same wheel runs `_default` and a pilot brand from config alone; conformance gate wired into the pilot's deploy.

### Phase 4 — Distribution hygiene & 1.0 — ~2 weeks + bake time
1. Split wheels: public `sysstra` (core+client+tenancy) / private `sysstra-runtime` (Mongo/Redis glue) via private index or VCS installs. A public `sysstra` install no longer reveals DB schema. Runners add one dependency line.
2. Rotate anything the public package leaked that is now considered sensitive.
3. Late, gentle deprecations: `DeprecationWarning` on global config *only* when `SYSSTRA_WARN_LEGACY=1`; flip default no earlier than 1.1.
4. Release **1.0.0** + compatibility matrix + migration guide (which is mostly "you don't have to do anything").
   - **Exit criteria:** all consumer repos green on 1.0 in their own CI; LTS branch retired or on life support by agreement.

### Sequencing rationale
Tests → config → layout → tenancy → packaging. Each step's risk is bounded by
the previous step's safety net; white-labeling (the goal) lands on top of fixed
foundations rather than on today's global-state quicksand.

---

## Part 6 — Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A star-importer used a symbol the facade missed | Medium | High (prod strategy crash) | Namespace-snapshot tests generated from *installed 0.1.4.6.8*, not from source reading; consumer smoke jobs |
| Golden masters encode a latent bug as "correct" | Certain (some will) | Low | That's the point — behavior preservation first; fix bugs as *separate, flagged* releases afterward |
| Fee YAML mistranscribes a broker rule | Medium | High (wrong PnL) | Goldens to the paisa across the full broker × market × holding grid before the if/elif is deleted |
| `orders-api` coordination slips | Medium | Medium | Its old import path keeps working via facade; the move is optional until Phase 4 |
| Live-order behavior change from retries/timeouts | Low | Critical | Opt-in only, never default in 0.x; poll/place goldens on mocked HTTP |
| Two-wheel split breaks a Docker build | Medium | Medium | Publish both to the private index first; keep a `sysstra[runtime]` extra as a transition alias |
| Solo-maintainer bandwidth | High | Medium | Phases are independently shippable; stopping after Phase 1 still nets the biggest bug fix; after Phase 3 white-labeling works even without the split |

---

## Part 7 — Explicit Assumptions (flag if wrong)

1. **White-label** means: multiple branded deployments (partners/brands) of the same trading stack — per-brand endpoints, brokers, fees, alerts, report branding — served by one core package. Not multi-user RBAC inside one deployment (that's the backend's job). **[CONFIRMED 2026-07-10]**
2. The backend APIs (`data`, `orders`) stay as-is; this plan doesn't require backend changes except the optional one-line import fix in `sysstra-orders-api`.
3. `sysstra-backtesting-strategies` staying on `0.1.4.3.3` is tolerable short-term; it upgrades to 0.2.x when convenient (LTS covers emergencies).
4. Publishing to public PyPI remains desired for the *public* SDK; if the whole thing should go private, Phase 4 simplifies to "move everything to a private index."
5. The vendored `ta/` stays vendored (it's a stability feature, not debt).
