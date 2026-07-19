# payment-router

[![CI](https://github.com/qinhzy/payment-router/actions/workflows/ci.yml/badge.svg)](https://github.com/qinhzy/payment-router/actions/workflows/ci.yml)
![Python 3.11-3.13](https://img.shields.io/badge/Python-3.11--3.13-3776AB)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/qinhzy/payment-router/blob/main/LICENSE)

Explainable, multi-objective routing simulator for cross-border payments.

Given a source currency, target currency, amount, and cost/time preference, the
simulator builds a payment graph across Wise quotes, SEPA transfers, and an
explicit SWIFT correspondent-banking scenario. It then compares direct and
multi-hop routes without hiding where the numbers came from.

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
uv run remit route EUR EUR 1000 --top-n=3
uv run remit sources
```

The CLI renders a selected route, hop-by-hop fees and timing, recipient amount,
and a Mermaid diagram. `decide` compares cheapest, fastest, and balanced
profiles against the same graph.

## What is implemented

- **Wise:** live unauthenticated quote fields from the public guest quote API.
- **SEPA:** EUR-to-EUR SCT model with a source-backed one-business-day target
  and an explicitly estimated sender fee.
- **SEPA Instant:** EUR-to-EUR SCT Inst model with the source-backed 10-second
  maximum and an explicitly estimated sender fee.
- **SWIFT scenario:** configurable correspondent-hop simulation. The topology
  is source-backed; all numeric hop parameters are labelled `ESTIMATED`.
- **Routing:** normalized cost/time Dijkstra selection plus edge-expanded top-N
  enumeration that preserves parallel payment networks.
- **Resilience:** bounded concurrent quote collection, deterministic warnings,
  invalid-response isolation, and fallback to the next fundable route.
- **Explanations:** terminal decision board, Markdown comparisons, and Mermaid
  route diagrams.
- **Quality:** Python 3.11-3.13 CI, strict pytest configuration, expanded Ruff
  rules, package-build validation, and 100 automated tests.

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
|-- networks/          # Wise, SEPA, and SWIFT adapters/models
|-- core/
|   |-- models.py      # quote, hop, route, and metric provenance models
|   |-- fx.py          # frozen FX normalization table
|   `-- graph.py       # concurrent MultiDiGraph construction
|-- router.py          # single-route and edge-distinct top-N routing
|-- decision.py        # cheapest/fastest/balanced comparison
|-- provenance.py      # auditable evidence registry
|-- visualizer.py      # Mermaid and Markdown rendering
`-- cli.py             # Typer/Rich command-line interface
```

The detailed algorithm, invariants, and boundaries are documented in
[Architecture](https://github.com/qinhzy/payment-router/blob/main/docs/ARCHITECTURE.md).

## Known limitations

- Only `USD`, `EUR`, `GBP`, and `CNY` are supported.
- Frozen FX mid-rates make runs reproducible but not market-current.
- The graph quotes each corridor at the source-equivalent amount; later-hop
  live quotes can differ because the actual arriving amount is path-dependent.
- Wise delivery estimates for an already funded balance can understate the time
  of later hops in a simulated multi-hop route.
- SEPA and SWIFT fees are scenario assumptions, not bank tariffs.
- Geography, bank participation, compliance, holidays, cut-off times, and
  liquidity are outside the MVP model.

## Roadmap

- **v0.3:** pluggable ECB/Frankfurter FX provider with cached, reproducible
  snapshots and explicit fallback behavior.
- **v0.4:** independent multi-hop timing model and sensitivity analysis.
- **v0.5:** source-backed corridor expansion and an RMB-focused CIPS scenario.
- **v0.6:** historical comparison without turning the simulator into an online
  payment service.

## Contributing and security

Contributions are welcome. Read [CONTRIBUTING.md](https://github.com/qinhzy/payment-router/blob/main/CONTRIBUTING.md), especially
the evidence requirements for financial assumptions. Security reports should
follow [SECURITY.md](https://github.com/qinhzy/payment-router/blob/main/SECURITY.md). User-visible changes are recorded in
[CHANGELOG.md](https://github.com/qinhzy/payment-router/blob/main/CHANGELOG.md).

## License

[MIT](https://github.com/qinhzy/payment-router/blob/main/LICENSE)
