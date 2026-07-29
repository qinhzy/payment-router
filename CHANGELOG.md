# Changelog

All notable user-visible changes are recorded here. The project follows
[Semantic Versioning](https://semver.org/) while it approaches a stable API.

## [0.9.0] - Unreleased

### Added

- a two-dimensional regime map across transfer amount and cost/time weight.
  `remit regime SOURCE TARGET [--min A --max B] [--amount-samples N]
  [--weight-steps M]`, `GET /api/regime`, and the console **Regime map** view
  show the sampled combinations where each route signature wins;
- four-neighbour connected-component summaries over the observed grid. The
  terminal renders one coloured character per route signature with a legend;
  the self-contained Web view uses the existing `--series-N` palette in both
  themes and is deep-linkable with `view=regime`;
- regression coverage for a known analytic crossing, deterministic graph-build
  counts, four-neighbour connectivity, the API worker-thread boundary, CLI
  output, deep links, and the AI payload contract.

### Changed

- the scan performs exactly one graph build per amount sample, then reuses that
  immutable router for every cost/time weight. The default 12-by-61 grid
  therefore performs 12 graph builds, not 732; the actual count is disclosed
  by the CLI, API, and console;
- regime boundaries are described only as lying between adjacent sampled
  amounts or weights. No interpolation or smoothing is applied, each amount is
  quoted independently, and boundaries driven by scenario-assumption fees are
  labelled as properties of the model rather than measured market facts;
- `sensitivity` and `breakeven` now share one route-signature primitive without
  changing either module's existing public import surface. The regime analysis
  introduces no rates, timings, fees, or provenance records.

## [0.8.0] - Unreleased

### Added

- break-even analysis across the amount axis. `remit breakeven SOURCE TARGET
  [--min A --max B]`, `GET /api/breakeven`, and a console **Break-even** view
  report which route wins at which size of transfer, and the amount brackets
  where the winner changes. A fixed fee dominates a small transfer while FX
  spread dominates a large one, so rails that lean on different parts of the
  fee structure cross somewhere in between; nothing else in the simulator
  looked along that axis.
- the search samples geometrically and then bisects only the boundaries it
  found, because every sampled amount needs its own graph and, with a live
  provider, its own quote round. Locating a crossing to within a few currency
  units costs roughly 20 builds rather than the thousands a dense scan of the
  same precision would need.

### Changed

- a crossover is always reported as a bracket. The exact crossing is never
  observed, only bracketed, so the figure is presented as a range and the
  caveat says why. The report also states when the fees producing a crossing
  are scenario assumptions, making the boundary a property of the model
  rather than a measured market fact.

`0.7.0` is the first tagged release. Versions `0.2.0` through `0.6.0` were
developed in the open but never tagged, so their entries are kept below for
history and everything they describe ships in `0.7.0`.

## [0.7.0] - 2026-07-25

### Added

- historical ECB rate dates. `--fx`-style sourcing gains a third mode that
  fetches the fixing published for a named past date, classified `VERIFIED`.
  A past fixing never changes, so its snapshot is cached per date and reused
  without revalidation. ECB publishes on business days only, so a weekend or
  holiday request resolves to the preceding publication and both the
  requested and the returned date are disclosed;
- `remit compare SOURCE TARGET AMOUNT --on <date> [--against <date>]` and
  `GET /api/compare`: route one corridor under two rate dates and report the
  mid-rate, fee, timing, and recipient-amount deltas between them. The
  baseline defaults to the latest published fixing;
- a console **rate-date comparison** view with a date picker, side-by-side
  cards, the deltas, and the caveats, deep-linkable via `view=compare&on=`;
- `fx-historical-ecb` provenance record and registry entry;
- periodic live-rate refresh while serving. A long-running
  `remit serve --fx live` re-checks the ECB source on an interval (default
  30 minutes, `--fx-refresh-minutes 0` disables it) and re-fetches only when
  the active snapshot predates today, so the console stops reporting a rate
  date it has outgrown. A refresh is committed only when it does not move
  backwards: it will not leave live mode and will not install an older
  publication than the one already active, so a transient failure can never
  replace published ECB rates with `ESTIMATED` teaching values.

### Changed

- the active rate table, its disclosure, and the cache-invalidation counter
  are replaced as one immutable snapshot. Assigning them separately let a
  reader on another thread pair rates that had already been swapped with the
  disclosure describing the previous ones, so the console could report a rate
  date that routing had stopped using — the one thing the FX disclosure exists
  to prevent.
- the AI system prompt describes every payload the console can send. It named
  only `route` and `decide` while the console had grown `sensitivity` and
  `compare`, leaving the model to guess at shapes it was never told about, and
  in particular free to read a rate-date comparison as what a transfer had
  actually cost. It now states that boundary and treats a payload's `caveats`
  list as the authoritative limits of the result.
- `remit serve` warns when asked to bind a non-loopback address: the console
  has no authentication, makes outbound provider requests for whoever reaches
  it, and spends the operator's Anthropic credentials if the AI panel is used.
- payment networks declare whether they quote at request time. A live-quoting
  adapter cannot answer for a past date, so it is excluded from a historical
  run — and from the baseline of a comparison as well, so that both sides see
  the same providers. Leaving it on one side only would let a provider-set
  difference appear in the deltas as though it were a rate effect. The
  exclusion is disclosed rather than silent.
- switching the process-wide FX source is serialized. A comparison swaps the
  active source twice and restores it, so the refresh loop takes the same lock
  and cannot substitute rates underneath an in-flight comparison. The blocking
  rate fetches also moved off the event loop.
- every test subset runs on its own. `Route` resolves a forward reference to
  `RoutingPreference` on `router` import, so `pytest tests/core/` could not
  construct a `Route` at all; a `conftest` import makes each subset behave
  like the full run.
- a historical rate request has no fallback. Live mode degrades to the frozen
  teaching table when the network is unavailable, but the frozen table is not
  the rate that applied on a past date, so an unavailable fixing raises
  instead of substituting one.

## [0.6.0] - Unreleased

### Added

- a configurable CIPS teaching scenario for CNY-destination corridors. CIPS's
  cross-border RMB role, direct/indirect participant structure, and 5×24+4
  operating window are source-backed; hop count, fees, timing range, and FX
  spread remain explicitly `ESTIMATED`;
- HKD and SGD across the frozen teaching FX table, Wise live quote candidates,
  the SWIFT scenario, CLI, API, and local console;
- deterministic CIPS unit, routing, CLI, Web API, timing-bound, and parameter
  validation coverage;
- `cips-topology` and `cips-model-parameters` evidence records, with matching
  machine-readable and human-readable registry entries.

### Changed

- the shared default network factory now registers CIPS once so the CLI, Web
  API, console, decision board, and sensitivity view discover it without
  frontend network lists;
- the Frankfurter request derives HKD and SGD from the expanded supported
  currency set; no provider-specific branch or new runtime dependency is used;
- the wider corridor set was re-measured against the top-N candidate budget
  added in 0.5.1. With every provider quoting (80 edges), the worst case — a
  small amount where most paths cannot cover their fees — takes 0.26 s, versus
  2.6 s on the same six-currency graph without the budget. Healthy corridors
  are unaffected and still return a full top-N in single-digit milliseconds.

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
- Wise delivery labels are parsed without depending on the host locale.
  `datetime.strptime` reads `%A`/`%B` from `LC_TIME`, so a machine configured
  for another language rejected the English labels the request explicitly asks
  for (`Accept-Language: en`) and dropped every affected quote with a provider
  warning. Month and weekday names are now matched against explicit English
  tables.
- Wise delivery labels naming 29 February are parsed instead of rejected.
  `strptime` defaults to year 1900, which is not a leap year, so the label
  failed to parse at all during any leap year. Dates now resolve to the next
  real occurrence of the named month and day, so a leap day is never quietly
  reported as 28 February.
- sensitivity regions no longer merge across a weight that produced no route.
  A gap used to be absorbed into the surrounding interval, which claimed a
  route won over weights where it did not.
- the console ignores superseded requests. Buttons disable themselves while a
  request is open, but history navigation does not go through them, so holding
  the back button could let a slow earlier response overwrite a newer view and
  rewrite the address bar to match it. In-flight requests are now aborted and
  late responses discarded.

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
- `/api/meta` reads the FX disclosure per request rather than snapshotting it
  at startup, so the console can never show a source the router is not using.
- the CLI's sensitivity stability panel names the winning route and its
  networks, matching what the web console already showed.

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
