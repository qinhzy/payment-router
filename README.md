# payment-router

Multi-objective routing simulator for cross-border payments.

Given a source currency, target currency, amount, and a cost/time preference, this tool builds a payment graph across Wise, SEPA, and SWIFT, then finds the best route with a weighted shortest-path search.

Not a production system. Every quote carries a `DataSource` label (`VERIFIED`, `INDUSTRY_AVERAGE`, or `ESTIMATED`) so the simulator explains where its numbers come from; the design goal is transparency over cleverness.

## Demo

```bash
$ uv run remit route USD CNY 100
+------------------------------ Selected Route -------------------------------+
| Path: USD -> GBP -> CNY                                                     |
| Total fee: $10.64                                                           |
| Total time: 30.642 hours                                                    |
| Final amount: 605.80 CNY                                                    |
+-----------------------------------------------------------------------------+
                   Hop Breakdown
+-------------------------------------------------+
| Hop | Network | Pair     | Fee (USD) | Time (h) |
|-----+---------+----------+-----------+----------|
| 1   | wise    | USD->GBP | $7.33     | 30.642   |
| 2   | wise    | GBP->CNY | $3.31     | 0.0      |
+-------------------------------------------------+
+---------------------------------- Mermaid ----------------------------------+
| flowchart LR                                                                |
|     USD["USD<br/>100.00"]                                                   |
|     GBP["GBP<br/>68.20"]                                                    |
|     CNY["CNY<br/>605.80"]                                                   |
|     USD -->|"wise<br/>fee: $7.33<br/>30.642h"| GBP                          |
|     GBP -->|"wise<br/>fee: $3.31<br/>0.0h"| CNY                             |
+-----------------------------------------------------------------------------+
```

The router discovered that a two-hop Wise path (`USD -> GBP -> CNY`) is about 6x cheaper than direct SWIFT for this amount; that is not a hardcoded rule, but the natural result of graph construction plus Dijkstra-based search.

### Rendered route diagram

```mermaid
flowchart LR
    USD["USD<br/>100.00"]
    GBP["GBP<br/>68.20"]
    CNY["CNY<br/>605.80"]
    USD -->|"wise<br/>fee: $7.33<br/>30.642h"| GBP
    GBP -->|"wise<br/>fee: $3.31<br/>0.0h"| CNY
```

## Why this exists

- SWIFT is not a single payment rail. It is a correspondent-bank chain where each hop can add fixed fees, percentage fees, FX spread, and delay, so headline transfer cost is often understated.
- The best route can be indirect. A multi-hop Wise path can beat a direct SWIFT path on total cost, and a simple one-network price lookup will miss that structure.
- Cost and speed trade off against each other. SEPA Instant can settle in about 10 seconds but only for `EUR -> EUR`, so users need a preference slider, not a single universal answer.

## Features

- Models three payment networks: Wise via the public guest quote API, SEPA as a rules engine, and SWIFT as a correspondent-bank simulator.
- Uses multi-objective Dijkstra routing with adjustable `cost_weight` and `time_weight`, with normalization so fee and time stay comparable.
- Enumerates top-N candidate routes with `shortest_simple_paths` for side-by-side comparison.
- Generates Mermaid flowcharts that can be pasted directly into GitHub or Notion.
- Attaches a `DataSource` label to every quote so data provenance remains explicit.
- Uses banker's rounding (`ROUND_HALF_EVEN`) for shared FX normalization, matching standard financial rounding practice.
- Ships with 63 passing tests: Wise 5, SEPA 6, SWIFT 8, graph 8, FX 7, router 13, CLI 6, visualizer 5, plus models 3 and base 2.

## Quick start

```bash
git clone https://github.com/qinhzy/payment-router.git
cd payment-router
uv sync --dev
uv run remit route USD CNY 100
uv run remit route GBP EUR 500 --prefer=cheapest
uv run remit route USD CNY 10000 --top-n=3
uv run remit networks
```

## Architecture

```text
src/payment_router/
|-- __init__.py        # package marker
|-- networks/          # PaymentNetwork implementations
|   |-- __init__.py    # package marker
|   |-- base.py        # abstract interface
|   |-- wise.py        # live Wise guest quote API
|   |-- sepa.py        # SEPA rules engine (SCT + SCT Instant)
|   `-- swift.py       # SWIFT correspondent bank model
|-- core/              # shared models and graph construction
|   |-- __init__.py    # package marker
|   |-- models.py      # Quote, Route, Hop (pydantic v2)
|   |-- fx.py          # unified mid-rate source
|   `-- graph.py       # PaymentGraph (networkx MultiDiGraph)
|-- router.py          # multi-objective Dijkstra routing
|-- visualizer.py      # Mermaid + Markdown table generation
`-- cli.py             # Typer CLI with Rich output
```

## Data sources & honesty

Every quote in the system carries a `data_source` field. The simulator does not pretend all numbers are equally trustworthy, and it does not hide when a result comes from a live API versus an industry median.

| Source | Meaning | Example |
|---|---|---|
| VERIFIED | From a live public API | Wise guest quote endpoint |
| INDUSTRY_AVERAGE | Documented median of published industry data | SWIFT correspondent bank fees, SEPA SCT median |
| ESTIMATED | Reasoned projection with caveats | Reserved for future extensions |

No quote is synthesized without disclosure.

## Known limitations

- **Wise multi-hop time estimation**: In multi-hop Wise routes, the second hop and beyond can show `time_hours = 0` because the Wise API returns delivery timing relative to an already funded balance. The current implementation can therefore slightly underestimate total multi-hop Wise time. Future fix plan: add an independent time estimation layer under `core/` in v2.
- **Four supported currencies**: The current MVP only supports `USD`, `EUR`, `GBP`, and `CNY`. Adding a new currency is mechanically small in `core/fx.py`, but every new corridor still needs verified source coverage. Future fix plan: expand the currency set only alongside source-backed corridor validation.
- **Static FX mid-rates**: The mid-rates in `core/fx.py` are manually checked and then frozen for repeatable simulation. That is acceptable for ranking paths, but not for production pricing. Future fix plan: plug in a live FX provider such as Frankfurter or ECB reference rates.

## Roadmap

- **v0.2**: Integrate Frankfurter live FX rates so route ranking can use current market references.
- **v0.3**: Add a historical volatility overlay to compare route quality under changing FX conditions.
- **v0.4**: Introduce a CIPS network model for RMB-focused corridor analysis.
- **v0.5**: Add a web UI with FastAPI and HTMX for interactive exploration and sharing.

## Tech stack

Python 3.11 / uv / pydantic v2 / networkx / typer / httpx / pytest / ruff

## License

MIT - see LICENSE.
