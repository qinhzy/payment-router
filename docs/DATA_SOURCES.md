# Data sources and assumptions

This document is the human-readable audit trail for every external fact and
teaching assumption that affects a route. It is part of the product contract,
not background reading.

Last reviewed: **2026-07-21**

## Classification rules

- `VERIFIED`: obtained from a live provider response or stated by the linked
  primary source.
- `INDUSTRY_AVERAGE`: a reproducible aggregate or median with a direct
  citation. No current built-in model relies on this label.
- `ESTIMATED`: a transparent scenario assumption, frozen teaching value, or a
  result derived using either of those.

Each quote labels fee, time, and FX separately. Its summary `data_source` must
equal the least-trusted of those three fields; model validation rejects an
overstated summary.

## Evidence registry

| Evidence ID | Network | Metric | Class | Model value | Checked on | Primary reference | Caveat |
|---|---|---|---|---|---|---|---|
| `wise-live-quote` | Wise | Provider rate, source-currency fee, delivery estimate | `VERIFIED` | Live response | 2026-07-18 | [Wise unauthenticated quote guide](https://docs.wise.com/guides/product/send-money/quotes/unauthenticated-quote) | Display and estimation only; rates expire and cannot create a transfer |
| `fx-frozen-table` | Shared FX | USD normalization (default source) | `ESTIMATED` | USD 1.00; EUR 1.08; GBP 1.27; CNY 0.14; HKD 0.128; SGD 0.74 | 2026-07-21 | None | Frozen for reproducibility; not current market pricing |
| `fx-live-ecb` | Shared FX | USD normalization (`--fx live`) | `VERIFIED` | ECB euro reference rates per fetched snapshot | 2026-07-20 | [Frankfurter API](https://www.frankfurter.dev/) serving [ECB reference rates](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html) | Indicative daily fixings published once per business day, not tradable quotes; HKD and SGD are published reference currencies; offline runs may serve a stale snapshot (surfaced in the CLI/console) |
| `sepa-sct-time` | SEPA | Maximum execution time | `VERIFIED` | One banking business day, modelled as 24 hours | 2026-07-18 | [EPC SEPA Credit Transfer](https://www.europeanpaymentscouncil.eu/what-we-do/sepa-credit-transfer) | Holidays and bank cut-off times are not modelled |
| `sepa-sct-fee` | SEPA | Sender fee | `ESTIMATED` | EUR 0.25 | 2026-07-18 | None | The EPC scheme does not set customer pricing |
| `sepa-instant-time` | SEPA Instant | Maximum execution time | `VERIFIED` | 10 seconds | 2026-07-18 | [EPC SEPA Instant Credit Transfer](https://www.europeanpaymentscouncil.eu/what-we-do/sepa-instant-credit-transfer) | Both payment service providers must participate |
| `sepa-instant-fee` | SEPA Instant | Sender fee | `ESTIMATED` | EUR 0.50 | 2026-07-18 | None | The EPC scheme does not set customer pricing |
| `swift-topology` | SWIFT | Correspondent-banking structure | `VERIFIED` | Interbank messaging across correspondent relationships | 2026-07-18 | [SWIFT correspondent banking](https://www.swift.com/payments/correspondent-banking) | SWIFT is messaging infrastructure, not one priced rail |
| `swift-model-parameters` | SWIFT | Hops, fees, time, FX spread | `ESTIMATED` | 3 hops; USD 20 + 0.2%; 18 hours (sensitivity band 6-48 hours) per hop; 1% spread | 2026-07-20 | None | Scenario parameters, not a bank quote or documented median; the band feeds displayed timing ranges, not the ranking |
| `cips-topology` | CIPS | RMB role, participant structure, operating window | `VERIFIED` | Wholesale cross-border RMB system; direct/indirect participants; 5×24h+4h | 2026-07-21 | [CIPS overview, rules, and participant FAQ](https://www.cips.com.cn/kjjqgs/jrcips/index.shtml) | Structural evidence only; it does not verify corridor availability, customer fees, FX spread, or end-to-end delivery time. |
| `cips-model-parameters` | CIPS | hops, fees, time, FX spread | `ESTIMATED` | 2 hops; $8 + 0.1%; 6h (band 1-12h) per hop; 0.3% spread | 2026-07-21 | None | Scenario assumptions compress an on-ramp and participant path; the published operating window is not an arrival-time guarantee. |

## How classifications flow into quotes

| Network | Fee | Time | FX | Quote summary |
|---|---|---|---|---|
| Wise | Follows the active FX source: `VERIFIED` under `--fx live`, `ESTIMATED` under the frozen table | `VERIFIED` live response | `VERIFIED` live response | Same as fee |
| SEPA | `ESTIMATED` | `VERIFIED` scheme rule | `VERIFIED` identity rate | `ESTIMATED` |
| SEPA Instant | `ESTIMATED` | `VERIFIED` scheme rule | `VERIFIED` identity rate | `ESTIMATED` |
| SWIFT scenario | `ESTIMATED` | `ESTIMATED` | `ESTIMATED` | `ESTIMATED` |
| CIPS scenario | `ESTIMATED` | `ESTIMATED` | `ESTIMATED` | `ESTIMATED` |

The Wise source-currency fee is live. The `NetworkQuote` exposes a normalized
`fee_usd`, so that field inherits the classification of whichever FX source
performed the USD conversion: `VERIFIED` when live ECB reference rates are
active, conservatively `ESTIMATED` when the frozen teaching table is. SEPA,
SWIFT, and CIPS fees remain `ESTIMATED` regardless of FX source because the
fee values themselves are scenario assumptions.

## Corridor coverage

- Wise is offered all six simulator currencies (`USD`, `EUR`, `GBP`, `CNY`,
  `HKD`, `SGD`); the live provider response remains authoritative and an
  unsupported provider corridor produces no edge.
- The SWIFT scenario covers all six currencies as an explicit teaching model.
- SEPA and SEPA Instant remain EUR-to-EUR self-loop rails only.
- The CIPS scenario accepts supported source currencies only when the target is
  CNY (including a CNY-to-CNY cross-border self-loop). This is a simulator
  boundary, not a claim that every institution can access CIPS.

## Update policy

A pull request that changes a rate, fee, timing rule, corridor, or source must:

1. update the code and this registry together;
2. link a primary source when claiming `VERIFIED` or `INDUSTRY_AVERAGE`;
3. update the checked date and explain the exact field supported by the source;
4. add or update deterministic tests;
5. downgrade the classification to `ESTIMATED` when the evidence is incomplete.

Run `uv run remit sources` for the machine-shipped registry summary.
