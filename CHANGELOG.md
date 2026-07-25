# Changelog

All notable user-visible changes are recorded here. The project follows
[Semantic Versioning](https://semver.org/) while it approaches a stable API.

## [0.5.1] - Unreleased

### Fixed

- bounded top-N candidate enumeration. A corridor that could not yield
  `top_n` fundable routes previously walked every simple path in the
  expanded graph, which grows combinatorially with the corridor set: a
  six-currency graph took roughly 27 seconds and an eight-currency graph did
  not finish. `MAX_CANDIDATE_PATHS` now caps the candidates inspected, so the
  same searches complete in about 0.25 s and 0.36 s. Candidates are generated
  in increasing weight order, so the cap can only return fewer routes than
  requested — it never reorders or downgrades the routes that were found, and
  healthy corridors are unaffected.
- Wise delivery labels naming 29 February are parsed instead of rejected.
  `strptime` defaults to year 1900, which is not a leap year, so the label
  failed to parse and the whole quote was dropped with a provider warning
  during any leap year. Labels that then roll into a common year resolve to
  28 February rather than raising.
- sensitivity regions no longer merge across a weight that produced no route.
  A gap used to be absorbed into the surrounding interval, which claimed a
  route won over weights where it did not.

### Changed

- `/api/sensitivity` runs its weight sweep in a worker thread. The sweep is
  `steps + 1` back-to-back route selections with no awaits, so running it
  inline stalled every other request on the event loop for its duration.
- the router caches the cost and time maxima used for score normalization.
  They depend only on the graph and the active FX source, never on the
  preference, so a sweep rescanned every edge once per step. The cache is
  invalidated by a graph rebuild or an FX source switch (`fx.generation()`).
  A 200-step sweep saves about 5% at today's four-currency graph and about
  50% at the 120-280 edge sizes a wider corridor set would reach.
- the web session cache normalizes the amount's scale, so `1000`, `1000.0`,
  and `1000.00` share one entry instead of re-quoting every provider.

## [0.5.0] - Unreleased

### Added

- per-hop timing bounds: every quote and hop now carries a `[min, max]`
  time window alongside the expected value. SEPA rails use scheme-maximum
  semantics (`0 <= expected <= scheme maximum`); the SWIFT scenario carries a
  registered 6-48 hour per-hop band; Wise live estimates stay point values
  until a source-backed band exists;
- route-level timing ranges: totals aggregate hop bounds, the CLI prints a
  `Time range` line, and the console's ETA tile shows the range under the
  expected value;
- `remit sensitivity SOURCE TARGET AMOUNT [--steps N]`: sweeps the
  cost/time weight from all-time to all-cost, prints every weight region
  with its winning route, and reports how stable the balanced (0.5/0.5)
  choice is before the ranking flips;
- `/api/sensitivity` endpoint and a console **Sensitivity** view: a regime
  strip showing which route wins across the weight axis, per-route timing
  range bars, a balanced-stability note, and qualitative timing caveats;
- timing caveats are structural, not invented numbers: the analysis flags
  later-hop `VERIFIED` delivery estimates that assume an already-funded
  balance, and marks `ESTIMATED` timing bands as scenario values.

### Changed

- the SWIFT scenario registers its per-hop timing band (6-48 hours) in the
  provenance registry; the band feeds displayed ranges only and does not
  change how routes are ranked.

## [0.4.0] - Unreleased

### Added

- pluggable FX rate sources: the frozen teaching table stays the default,
  and `--fx live` (or `PAYMENT_ROUTER_FX=live`) activates ECB euro reference
  rates via the Frankfurter API, classified `VERIFIED`;
- on-disk FX snapshot cache: same-day reruns reuse the snapshot without a
  network call, refresh failures fall back to the stale snapshot, and a
  missing snapshot falls back to the frozen table with an explicit warning;
- FX disclosure everywhere: a CLI status line, an `fx` block in `/api/meta`,
  and a console topbar chip showing source, rate date, and fallback state;
- `fx-live-ecb` provenance record and registry documentation.

### Changed

- Wise's normalized `fee_usd` classification now follows the active FX
  source: `VERIFIED` under live ECB rates, `ESTIMATED` under the frozen
  table (the quote summary upgrades with it).

## [0.3.0] - Unreleased

### Added

- local web console (`remit serve`): corridor form, per-route stat tiles,
  hop-by-hop flow diagram with intermediate balances, decision board,
  provenance badges, provider warnings, sources registry, light/dark themes;
- FastAPI JSON API (`/api/meta`, `/api/route`, `/api/decide`, `/api/sources`)
  behind an optional `web` extra, with OpenAPI docs at `/api/docs`;
- shared `service` layer owning request validation, network instantiation, and
  graph construction for both the CLI and the web API;
- short-lived quote session cache (default 60 s, configurable, zero disables)
  with stampede protection; responses carry `quoted_at`/`from_cache` metadata
  and the console shows quote freshness;
- shareable console URLs with browser history support, recent-search chips,
  and a fee/time profile-comparison chart when profiles disagree;
- `remit serve --open` flag and `python -m payment_router` entry point;
- optional AI insight panel: `POST /api/explain` streams a Claude-generated,
  provenance-aware reading of the displayed result over server-sent events,
  grounded strictly in the console's JSON and carrying the simulator
  disclaimer; enabled only when Anthropic credentials resolve (default model
  `claude-opus-4-8`, override with `PAYMENT_ROUTER_AI_MODEL`);
- console motion polish: entrance animations, stat count-ups, animated flow
  arrows, and hover elevation, all disabled under reduced-motion preferences;
- web API test suite with injectable fake networks and explainers (21 cases)
  and a service-layer unit test suite (12 cases).

### Changed

- CLI internals now delegate to the shared service layer; behavior and output
  are unchanged;
- provider warning labels use the human-readable network name (`Wise` instead
  of `WiseNetwork`);
- amount and hour formatting helpers are shared between the CLI, Mermaid
  output, and the web API so all frontends render identical numbers.

## [0.2.0] - Unreleased

### Added

- terminal decision board for cheapest, fastest, and balanced profiles;
- edge-distinct top-N routing across parallel payment networks;
- same-currency rail comparison for SEPA, SEPA Instant, and SWIFT scenarios;
- metric-level fee, time, and FX provenance validation;
- auditable provenance registry and `remit sources` command;
- Python 3.11-3.13 CI, formatting checks, and package-build validation;
- contribution, security, architecture, and source-assumption documentation.

### Fixed

- rank fees in a common USD unit and account for non-negative FX spread;
- reject routes whose live hop balance cannot cover the next fee;
- preserve parallel graph edges and deterministic provider warnings;
- bound stalled quote collection without discarding healthy providers;
- calculate Mermaid intermediate balances with the routing recurrence;
- resolve `--version` from installed package metadata instead of a source-only
  `pyproject.toml` path.

### Changed

- relabel unsupported SEPA and SWIFT numeric assumptions as `ESTIMATED`;
- conservatively label Wise USD fee normalization as `ESTIMATED` while retaining
  `VERIFIED` rate and delivery provenance.

## [0.1.0] - 2026-04-19

- initial Wise, SEPA, and SWIFT models;
- concurrent payment graph, multi-objective routing, CLI, and Mermaid output;
- initial automated test suite and MIT license.
