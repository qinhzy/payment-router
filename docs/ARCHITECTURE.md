# Architecture

## Goal and boundary

`payment-router` is a bounded teaching simulator for four currencies and three
payment-system models. It explains route trade-offs; it does not execute money
movement, determine legal availability, or promise a quote.

## Data flow

1. A network adapter receives a source-equivalent amount for a currency pair.
2. `PaymentGraph` requests quotes concurrently with a per-quote timeout.
3. Valid quotes become parallel `NetworkEdge` values in a `MultiDiGraph`.
4. `PaymentRouter` scores fee plus non-negative FX spread against time.
5. A candidate route is replayed hop by hop against its live simulated balance.
6. The CLI renders cost, time, recipient amount, provenance, and diagrams.

Provider failures are recorded per corridor and sorted deterministically. A bad
or stalled provider does not discard healthy edges from other providers.

## Graph model

Currency codes are graph nodes. A directed edge is one provider quote for one
currency pair. Parallel edges are intentionally preserved because Wise and a
SWIFT scenario can quote the same pair with different trade-offs.

Same-currency quotes are self-loops. They let `EUR -> EUR` requests compare
SEPA, SEPA Instant, and other eligible rails instead of returning a fictional
free transfer. When a graph has no same-currency rail at all, the library keeps
the legacy zero-hop identity result for pure conversion use cases.

## Scoring

For edge `e`, the normalized score is:

```text
score(e) = alpha * cost(e) / max_cost + beta * time(e) / max_time
```

`alpha` and `beta` are normalized from the requested preference. `cost(e)` is
the USD-normalized fee plus the non-negative loss implied by the edge rate
relative to the frozen mid-rate table. The scoring inputs retain their own data
classifications; normalization does not turn an estimate into verified data.

## Route algorithms

- Single-route lookup uses NetworkX weighted shortest-path selection. If the
  statically best path cannot pay a hop fee, routing continues to the next
  feasible candidate.
- Top-N lookup expands every original payment edge into an intermediate graph
  node. NetworkX can then enumerate simple paths while keeping parallel
  providers distinct. The expanded nodes are removed when constructing the
  public `Route`.
- `max_hops` counts payment edges, not expanded implementation nodes.
- Same-currency lookup ranks the explicit self-loop edges directly.

The four-currency MVP bounds graph size. A future broad-currency version will
need additional candidate limits and performance benchmarks.

## Monetary replay

At every hop:

```text
fee_in_source_currency = fee_usd * USD_to_source_mid_rate
next_amount = (current_amount - fee_in_source_currency) * quoted_fx_rate
```

A path is rejected when the current balance cannot strictly cover its fee. The
visualizer uses the same recurrence, so intermediate diagram balances match the
router rather than a cumulative-fee approximation.

## Frontends

The CLI and the web console are thin rendering layers over one shared service
module (`service.py`). It owns request validation, network instantiation,
graph construction, and profile-to-preference mapping, so both frontends
always agree on routing behavior and error messages.

- `cli.py` renders Rich tables, panels, and Mermaid source in the terminal.
- `web/app.py` is a FastAPI application (optional `web` extra) exposing
  `/api/meta`, `/api/route`, `/api/decide`, and `/api/sources`, and serving the
  static single-page console from `web/static/`. JSON amounts reuse the exact
  CLI formatting helpers, so both frontends display identical numbers.
- The web app keeps a short-lived cache of built routing sessions (default
  60 seconds, keyed by source, target, and amount) so switching preference or
  top-N reuses the same quotes instead of re-querying live providers. Only
  successful builds are cached, responses expose `quoted_at`/`from_cache`
  metadata, and a TTL of zero disables the cache. The CLI always builds fresh.

The web console is a local tool started with `remit serve`; it is not a
deployment target and adds no authentication, persistence, or payment
initiation surface.

## Invariants

- amounts and numeric quote values are finite and non-negative;
- FX rates are positive;
- quote summary provenance equals its least-trusted numeric component;
- unsupported or malformed provider responses never become edges;
- provider warnings and edge tie-breaking are deterministic;
- all public changes pass tests, lint, formatting, and package build checks.
