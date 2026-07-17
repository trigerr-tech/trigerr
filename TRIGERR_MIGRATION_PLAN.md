# Trigerr Migration Plan

This document tracks the phased migration from the earlier `sysstra` package
to the public `trigerr` package.

## Phase 1 — Package foundation

- [x] Rename the import namespace from `sysstra` to `trigerr`, including
  internal absolute imports.
- [x] Replace legacy `setup.py` packaging with `pyproject.toml`.
- [x] Set the initial public version to `0.1.0`.
- [x] Add package, test, build, and CI configuration.
- [x] Establish a concise public README and GitHub ignore rules.

## Phase 2 — Offline quant core

Port and test indicators, OHLCV/timeframe utilities, swing calculations,
brokerage/P&L calculations, reports, and in-memory backtesting without
requiring external services.

## Phase 3 — Public API stabilization

Document dataframe conventions, define public errors and return contracts,
add type hints, regression tests, and runnable examples.

## Phase 4 — Optional integrations

Redesign external data and broker integrations as explicit clients and optional
dependencies. Do not carry direct Redis or MongoDB runtime coupling into the
public core package.

## Phase 5 — Release

Complete security and license review, configure releases, publish `0.1.0`, and
maintain a migration guide for users of the older package.
