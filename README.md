# payment-router

[![CI](https://github.com/qinhzy/payment-router/actions/workflows/ci.yml/badge.svg)](https://github.com/qinhzy/payment-router/actions/workflows/ci.yml)
![Python 3.11-3.13](https://img.shields.io/badge/Python-3.11--3.13-3776AB)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/qinhzy/payment-router/blob/main/LICENSE)

Explainable, multi-objective routing simulator for cross-border payments.

Given a source currency, target currency, amount, and cost/time preference, the
simulator builds a payment graph across Wise quotes, SEPA transfers, an
explicit SWIFT correspondent-banking scenario, and a CNY-bound CIPS scenario.
It then compares direct and multi-hop routes without hiding where the numbers
came from.

> [!IMPORTANT]
> This is an early-stage teaching and research project, not a production quote,
> transfer, compliance, or financial-advice system. Never use its output to
> initiate or promise a real payment.

## Why this exists

Most public comparison tools show one provider's headline quote. Real
cross-border transfers can accumulate fixed fees, percentage fees, FX spread,
and delay across several institutions. `payment-router` makes that structure
inspectable:

- parallel providers remain distinct instead of being collapsed into one edge;
- cost, time, and recipient amount are shown together;
- same-currency rails such as SEPA and SEPA Instant can be compared directly;
- every fee, time, and FX component carries its own provenance classification;
- live, source-backed, and teaching-assumption values are never presented as
  equally certain.

## Example

```bash
uv run remit route USD CNY 1000 --prefer=cheapest
uv run remit route USD CNY 1000 --top-n=3
uv run remit decide USD CNY 1000
uv run remit sensitivity USD CNY 1000
uv run remit route HKD CNY 10000 --top-n=3
uv run remit route EUR EUR 1000 --top-n=3
uv run remit sources
uv run remit serve
```

The CLI renders a selected route, hop-by-hop fees and timing, recipient amount,
and a Mermaid diagram. `decide` compares cheapest, fastest, and balanced
profiles against the same graph. `sensitivity` sweeps the cost/time weight and
shows exactly where the winning route flips.

## Web console

`remit serve` starts a local web console at `http://127.0.0.1:8000` on top of
the same routing engine the CLI uses:

- corridor form with amount, currency swap, cheapest/fastest/balanced
  preference, and top-1/3/5 candidates;
- per-route stat tiles (recipient amount, total fees, estimated time), a
  hop-by-hop flow diagram with live intermediate balances, and copyable
  Mermaid source;
- a side-by-side decision board for the three profiles with the same tradeoff
  note the CLI prints;
- provenance badges on every route and hop, provider warnings, and the full
  auditable source registry;
- a profile-comparison chart when the three profiles pick different routes;
- a **Sensitivity** view: a regime strip showing which route wins as the
  cost/time weight sweeps from all-time to all-cost, per-route timing range
  bars, a balanced-stability note, and qualitative timing caveats;
- shareable URLs (every query updates the address bar and can be bookmarked or
  sent; the back button restores previous results) and recent-search chips;
- a short-lived quote session cache so switching preference or top-N reuses
  the freshly built graph instead of re-querying live providers, with a
  visible fetched/cached freshness indicator;
- light/dark themes; the page itself is fully self-contained with no CDN or
  external requests.

Start it with `uv run remit serve` (add `--open` to launch a browser, or
`--host`/`--port` to change the binding).

### AI insight (optional)

When Anthropic credentials are available to the server process
(`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, or an `ant auth login`
profile), the console shows an **AI insight** panel that streams a
Claude-generated reading of the current result: the bottom-line pick, the
trade-off that matters, and a caveat grounded in the provenance labels. The
explanation is generated strictly from the JSON the console is displaying,
answers in your browser language, and always repeats the simulator
disclaimer. Without credentials the panel is hidden and the console works
exactly as before — no other feature depends on it.

The default model is `claude-opus-4-8`; set `PAYMENT_ROUTER_AI_MODEL` to
override. The API surface is `POST /api/explain` (server-sent events).

The JSON API behind it is documented at `/api/docs` (`/api/meta`, `/api/route`,
`/api/decide`, `/api/sensitivity`, `/api/sources`). The console is a local tool, not a deployment
target: it adds no authentication, persistence, or payment initiation surface.

## What is implemented

- **Wise:** live unauthenticated quote fields from the public guest quote API.
- **SEPA:** EUR-to-EUR SCT model with a source-backed one-business-day target
  and an explicitly estimated sender fee.
- **SEPA Instant:** EUR-to-EUR SCT Inst model with the source-backed 10-second
  maximum and an explicitly estimated sender fee.
- **SWIFT scenario:** configurable correspondent-hop simulation. The topology
  is source-backed; all numeric hop parameters are labelled `ESTIMATED`.
- **CIPS scenario:** CNY-destination teaching model with a deliberately shorter
  default chain than SWIFT. Its cross-border RMB role, direct/indirect
  participant structure, and 5×24+4 operating window are source-backed; every
  numeric parameter remains `ESTIMATED`.
- **FX sources:** a frozen teaching table by default; `--fx live` switches to
  ECB euro reference rates via Frankfurter with an on-disk snapshot cache and
  explicit stale/fallback behavior.
- **Supported currencies:** USD, EUR, GBP, CNY, HKD, and SGD. SEPA remains
  EUR-only, while CIPS is limited to CNY-target corridors.
- **Routing:** normalized cost/time Dijkstra selection plus edge-expanded top-N
  enumeration that preserves parallel payment networks.
- **Timing ranges and sensitivity:** every hop carries a `[min, max]` time
  window (SEPA scheme-maximum semantics plus registered SWIFT and CIPS
  scenario bands), routes aggregate them into displayed ranges, and
  `remit sensitivity` sweeps the cost/time weight to show where the winning
  route flips and how stable the balanced choice is.
- **Resilience:** bounded concurrent quote collection, deterministic warnings,
  invalid-response isolation, and fallback to the next fundable route.
- **Explanations:** terminal decision board, Markdown comparisons, and Mermaid
  route diagrams.
- **Web console:** optional FastAPI backend plus a dependency-free single-page
  frontend sharing the CLI's routing service layer (`remit serve`).
- **Quality:** Python 3.11-3.13 CI, strict pytest configuration, expanded Ruff
  rules, package-build validation, and 180 automated tests.

## Quick start

Prerequisites: Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/qinhzy/payment-router.git
cd payment-router
uv sync --dev
uv run remit --version
uv run remit networks
uv run remit route USD CNY 100
```

Run the full local verification suite:

```bash
uv run pytest -x
uv run ruff check .
uv run ruff format --check .
uv build
uv lock --check
```

## Provenance model

`DataSource` has three deliberately narrow meanings:

| Classification | Meaning |
|---|---|
| `VERIFIED` | Read from a live response or stated by the linked primary source |
| `INDUSTRY_AVERAGE` | A documented aggregate or median with a reproducible citation |
| `ESTIMATED` | A transparent teaching assumption or a value derived using one |

The overall classification of a quote must equal its least-trusted component.
For example, a Wise rate and ETA can be `VERIFIED`, while its normalized USD
fee is `ESTIMATED` because the current simulator uses a frozen FX table for that
conversion. The quote summary is therefore also `ESTIMATED`.

See [Data sources and assumptions](https://github.com/qinhzy/payment-router/blob/main/docs/DATA_SOURCES.md) for the complete
registry, source links, checked dates, values, and caveats. The same registry is
available in the CLI with `remit sources`.

## Architecture

```text
src/payment_router/
|-- networks/          # Wise, SEPA, SWIFT, and CIPS adapters/models
|-- core/
|   |-- models.py      # quote, hop, route, and metric provenance models
|   |-- fx.py          # pluggable FX sources (frozen table / live ECB)
|   `-- graph.py       # concurrent MultiDiGraph construction
|-- router.py          # single-route and edge-distinct top-N routing
|-- decision.py        # cheapest/fastest/balanced comparison
|-- provenance.py      # auditable evidence registry
|-- service.py         # shared request/session layer for CLI and web
|-- visualizer.py      # Mermaid and Markdown rendering
|-- web/
|   |-- app.py         # FastAPI API + static console (optional `web` extra)
|   |-- schemas.py     # JSON views reusing the CLI's number formatting
|   `-- static/        # self-contained single-page frontend
`-- cli.py             # Typer/Rich command-line interface
```

The detailed algorithm, invariants, and boundaries are documented in
[Architecture](https://github.com/qinhzy/payment-router/blob/main/docs/ARCHITECTURE.md).

## Known limitations

- Only `USD`, `EUR`, `GBP`, `CNY`, `HKD`, and `SGD` are supported.
- The default frozen FX mid-rates make runs reproducible but not
  market-current; `--fx live` uses ECB reference rates, which are daily
  indicative fixings rather than tradable quotes.
- The graph quotes each corridor at the source-equivalent amount; later-hop
  live quotes can differ because the actual arriving amount is path-dependent.
- Wise delivery estimates for an already funded balance can understate the time
  of later hops in a simulated multi-hop route.
- SEPA, SWIFT, and CIPS fees are scenario assumptions, not bank tariffs.
- CIPS is modelled only for CNY-target corridors. Its two-hop default is a
  teaching abstraction, and the published operating window is not an
  end-to-end delivery promise.
- Geography, bank participation, compliance, holidays, cut-off times, and
  liquidity are outside the MVP model.

## Roadmap

- **v0.3:** local web console over a shared routing service layer (shipped).
- **v0.4:** pluggable ECB/Frankfurter FX provider with cached, reproducible
  snapshots and explicit fallback behavior (shipped).
- **v0.5:** independent multi-hop timing model and sensitivity analysis
  (shipped).
- **v0.6:** source-backed corridor expansion and an RMB-focused CIPS scenario
  (this release).
- **v0.7:** historical comparison without turning the simulator into an online
  payment service.

## Contributing and security

Contributions are welcome. Read [CONTRIBUTING.md](https://github.com/qinhzy/payment-router/blob/main/CONTRIBUTING.md), especially
the evidence requirements for financial assumptions. Security reports should
follow [SECURITY.md](https://github.com/qinhzy/payment-router/blob/main/SECURITY.md). User-visible changes are recorded in
[CHANGELOG.md](https://github.com/qinhzy/payment-router/blob/main/CHANGELOG.md).

## License

[MIT](https://github.com/qinhzy/payment-router/blob/main/LICENSE)
