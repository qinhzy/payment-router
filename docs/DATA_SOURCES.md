# Data sources and assumptions

This document is the human-readable audit trail for every external fact and
teaching assumption that affects a route. It is part of the product contract,
not background reading.

Last reviewed: **2026-07-18**

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

| Evidence ID | Network | Metric | Class | Model value | Primary reference | Caveat |
|---|---|---|---|---|---|---|
| `wise-live-quote` | Wise | Provider rate, source-currency fee, delivery estimate | `VERIFIED` | Live response | [Wise unauthenticated quote guide](https://docs.wise.com/guides/product/send-money/quotes/unauthenticated-quote) | Display and estimation only; rates expire and cannot create a transfer |
| `fx-frozen-table` | Shared FX | USD normalization | `ESTIMATED` | USD 1.00; EUR 1.08; GBP 1.27; CNY 0.14 | None | Frozen for reproducibility; not current market pricing |
| `sepa-sct-time` | SEPA | Maximum execution time | `VERIFIED` | One banking business day, modelled as 24 hours | [EPC SEPA Credit Transfer](https://www.europeanpaymentscouncil.eu/what-we-do/sepa-credit-transfer) | Holidays and bank cut-off times are not modelled |
| `sepa-sct-fee` | SEPA | Sender fee | `ESTIMATED` | EUR 0.25 | None | The EPC scheme does not set customer pricing |
| `sepa-instant-time` | SEPA Instant | Maximum execution time | `VERIFIED` | 10 seconds | [EPC SEPA Instant Credit Transfer](https://www.europeanpaymentscouncil.eu/what-we-do/sepa-instant-credit-transfer) | Both payment service providers must participate |
| `sepa-instant-fee` | SEPA Instant | Sender fee | `ESTIMATED` | EUR 0.50 | None | The EPC scheme does not set customer pricing |
| `swift-topology` | SWIFT | Correspondent-banking structure | `VERIFIED` | Interbank messaging across correspondent relationships | [SWIFT correspondent banking](https://www.swift.com/payments/correspondent-banking) | SWIFT is messaging infrastructure, not one priced rail |
| `swift-model-parameters` | SWIFT | Hops, fees, time, FX spread | `ESTIMATED` | 3 hops; USD 20 + 0.2%; 18 hours; 1% spread per hop | None | Scenario parameters, not a bank quote or documented median |

## How classifications flow into quotes

| Network | Fee | Time | FX | Quote summary |
|---|---|---|---|---|
| Wise | `ESTIMATED` after frozen-table USD normalization | `VERIFIED` live response | `VERIFIED` live response | `ESTIMATED` |
| SEPA | `ESTIMATED` | `VERIFIED` scheme rule | `VERIFIED` identity rate | `ESTIMATED` |
| SEPA Instant | `ESTIMATED` | `VERIFIED` scheme rule | `VERIFIED` identity rate | `ESTIMATED` |
| SWIFT scenario | `ESTIMATED` | `ESTIMATED` | `ESTIMATED` | `ESTIMATED` |

The Wise source-currency fee is live. The current `NetworkQuote` exposes a
normalized `fee_usd`, however, so that field is conservatively classified as
`ESTIMATED` whenever the frozen FX table participates in its derivation.

## Update policy

A pull request that changes a rate, fee, timing rule, corridor, or source must:

1. update the code and this registry together;
2. link a primary source when claiming `VERIFIED` or `INDUSTRY_AVERAGE`;
3. update the checked date and explain the exact field supported by the source;
4. add or update deterministic tests;
5. downgrade the classification to `ESTIMATED` when the evidence is incomplete.

Run `uv run remit sources` for the machine-shipped registry summary.
