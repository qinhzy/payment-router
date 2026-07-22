# Architecture

## Goal and boundary

`payment-router` is a bounded teaching simulator for six currencies and four
payment-system families. It explains route trade-offs; it does not execute
money movement, determine legal availability, or promise a quote.

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
relative to the active FX source's mid-rate table — the frozen teaching table
by default, or a cached ECB reference-rate snapshot under `--fx live`. The
scoring inputs retain their own data classifications; normalization does not
turn an estimate into verified data, and fee labels inherit the FX source's
class when a conversion participates.

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

The six-currency scope bounds graph size. A future broad-currency version will
need additional candidate limits and performance benchmarks.

## Scenario-network boundaries

SWIFT and CIPS are intentionally comparative scenarios, not provider adapters.
The SWIFT model can produce an edge for every supported pair and represents a
configurable correspondent-bank chain. The CIPS model produces edges only when
the target is CNY; its default two-hop path compresses the source-side on-ramp
and participant path into a teaching abstraction. It does not assert that the
originating institution is a CIPS participant or that a particular corridor is
legally or operationally available.

CIPS's role in cross-border RMB clearing, its direct/indirect participant
structure, and its 5×24+4-hour operating window are `VERIFIED`. Its hop count,
fee formula, expected delay, `[min, max]` timing band, and FX spread are all
`ESTIMATED`. In particular, a system operating window is not evidence of an
end-to-end arrival time. Defaults are deliberately shorter and faster than the
SWIFT scenario so students can inspect the trade-off without treating either
scenario as a bank quote.

## Timing model and sensitivity

Every quote, hop, and route carries a `[time_min, time_max]` window around the
expected time. Bounds default to the expected value when a network has nothing
better to claim, and model validation enforces `min <= expected <= max`:

- SEPA rails use scheme-maximum semantics: the published maximum execution
  time is the upper bound and settlement may complete any time before it
  (`min = 0`);
- the SWIFT scenario carries a per-hop 6-48 hour band registered as
  `ESTIMATED` in the provenance registry;
- the CIPS scenario carries a per-hop 1-12 hour band, also registered as
  `ESTIMATED`; its published operating schedule does not upgrade this band;
- Wise live delivery estimates remain point values until a source-backed
  band exists.

The bounds are display-and-analysis data only: route ranking still uses the
expected time, so adding a band never changes which route wins.

`sensitivity.py` sweeps the cost/time weight `alpha` from 0 (all-time) to 1
(all-cost) in uniform steps, routes at each weight, and merges consecutive
weights that pick the same route into weight regions. The report includes the
region containing the balanced 0.5/0.5 weight (how far the weight can drift
before the choice flips) and qualitative caveats: later-hop `VERIFIED`
delivery estimates that assume an already-funded balance, and `ESTIMATED`
timing bands that are scenario values. Caveats stay qualitative because the
registry has no evidence for a numeric later-hop correction; inventing one
would violate the provenance contract.

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
  `/api/meta`, `/api/route`, `/api/decide`, `/api/sensitivity`, and
  `/api/sources`, and serving the static single-page console from
  `web/static/`. JSON amounts reuse the exact CLI formatting helpers, so both
  frontends display identical numbers.
- The web app keeps a short-lived cache of built routing sessions (default
  60 seconds, keyed by source, target, and amount) so switching preference or
  top-N reuses the same quotes instead of re-querying live providers. Only
  successful builds are cached, responses expose `quoted_at`/`from_cache`
  metadata, and a TTL of zero disables the cache. The CLI always builds fresh.

- `web/ai.py` is the optional AI layer: when Anthropic credentials resolve,
  `POST /api/explain` streams a Claude-generated reading of the displayed
  result over server-sent events. The prompt grounds the model strictly in
  the console's JSON, surfaces provenance caveats, and pins the simulator
  disclaimer; without credentials the endpoint returns 503 and the console
  hides the panel.

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
