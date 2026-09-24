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
- regression coverage for a known analytic crossing at two fixed-fee levels, so
  the sampled boundary has to move with the fee rather than merely land
  somewhere plausible, plus deterministic graph-build counts, four-neighbour
  connectivity, the API worker-thread boundary, CLI output, deep links, and the
  AI payload contract;
- a console **candidate comparison** table above Top-3/Top-5 results: rank,
  route and networks, recipient amount with its difference to #1, fees, time,
  and evidence class, with each row jumping to that route's breakdown. Route
  cards also show the effective rate, derived only from the amounts on screen;
- a console **scan range** for the break-even and regime views (the API's
  `min`/`max`), kept in the shareable URL, plus a "your amount" marker on the
  break-even strip and a scenario crosshair on the regime map. Both follow the
  form without re-running the scan and describe only observed samples: an
  amount inside a crossover bracket says either route may win, and the regime
  note names the nearest sampled cell rather than inventing a value between
  cells;
- a Cancel button (and Esc) for a running request, which restores the previous
  view, and decade tick labels on the logarithmic amount axes;
- a Simplified Chinese console (中文界面) beside English. It follows the
  browser language, is switched from the top bar and remembered, and redraws
  the results on screen from the data already received. Caveats and errors are
  translated from stable codes rather than by parsing prose: every caveat is an
  `analysis.Caveat`, a `str` that also carries a code and its parameters, the
  analysis JSON adds `caveat_codes` index-aligned with `caveats`, API errors add
  `code` and `params` beside the unchanged English `detail`, and warnings add a
  `code` for the simulator's own statements. When a translation lacks a figure
  the server sent, the English sentence is shown instead. Provenance registry
  entries are translated by evidence id; the English entry stays
  authoritative, is shown on hover, and every figure it gives must reappear
  in the translation;
- amount presets sized to the source currency: `/api/meta` returns
  `quick_amounts`, a USD ladder converted at the active mid-rate and snapped to
  a round figure, so a CNY sender is offered 2,000–50,000 rather than 250;
  on a phone too narrow for five full figures they read 2K or 1万 instead
  of clipping the last preset;
- browser tests of the console (`tests/web/test_console_e2e.py`, Playwright as
  a development-only dependency) against a real server: hidden elements, the
  candidate table, grouped warnings, the break-even profile and marker, amount
  and field validation, Cancel, history navigation, quick amounts, language
  switching, and the phone layout. They skip without Chromium unless
  `PAYMENT_ROUTER_E2E=1`, which the CI job that installs Chromium sets; catalog
  tests keep both languages' keys and placeholders in step and require a
  Chinese template for every caveat and error code the backend can emit.

### Fixed

- a break-even region no longer claims amounts at which no route was
  observed. Regions used to start at the requested minimum even when the
  smallest samples could not be routed (a USD→CNY scan reported CIPS from 10.00
  although nothing routed below 23.10), and an unroutable sample between two
  winners merged them into one region, hiding the route that won above it.
  Regions now cover only runs of routable samples, never bridge an unroutable
  one, and a lone routable sample is kept as a single-amount region instead of
  being reported as no route at all. The console draws the gaps as hatched
  "no route observed" spans;
- break-even, regime, and rate-date comparison results now disclose provider
  failures. Their scans discarded every build's warnings, so a provider that
  was down silently changed which route could win. `BreakevenReport`,
  `RegimeMap`, and `ComparisonReport` carry the failures once each, the API
  returns them as `warnings`, the CLI prints them, and the AI system prompt
  says a result computed without a provider must not be called the best
  available;
- the console's **Break-even** and **rate-date comparison** now use the selected
  cost/time profile; both silently ran the balanced profile whatever was
  chosen. The profile is part of their URL, stale check, and recent searches;
- elements marked `hidden` stayed visible when a component rule set `display`:
  an empty "Recent" bar showed on a first visit and a blank disclaimer flashed
  before metadata loaded;
- an AI explanation kept streaming in the background after new results
  replaced its panel, and a run that superseded another left "Working…" as a
  button's permanent label;
- break-even bisection that met a third winner inside one sampled interval
  reported only the first change of winner and labelled the third route's
  amounts with the route that won at the next coarse sample. Both halves are
  now located separately, each change becomes its own crossover, and the
  observed midpoints represent the regions they fall in;
- sensitivity timing caveats named only the currency path, so two rails on the
  same path printed the same warning twice. They now name the networks too;
- the regime map's vertical axis title collapsed in Chinese: characters could
  wrap between any two glyphs and, without a font's vertical metrics, stacked
  on top of each other. It is kept on one line and set sideways in every
  language;
- a rate date outside the published series blocked every route search: the
  browser's own form validation stopped **Find routes** with an untranslated
  message, although only the rate-date comparison reads that field. Each
  request is now validated by the fields it uses;
- times under an hour lost precision: hours were rounded to three decimals, so
  SEPA Instant's ten seconds (0.003 h) read back as eleven. Below one hour the
  API, CLI, and Mermaid output keep six decimals (0.002778 h);
- a route without a modelled time band repeated its headline in raw hours
  ("20.0 hours" under "20 h"); the tile now says that no range is modelled;
- evidence badges in the source registry stacked one Chinese glyph per line in
  their narrow column, and on a phone a very large figure squeezed the tile
  beside it to a sliver. Badges stay on one line and figures wrap inside
  their own tile;
- the scenario summary echoed an amount the form rejects; it shows a dash
  until the amount is valid;
- the sensitivity strip left its last sampling step empty: regions list the
  sampled weights they won, one step apart, and were drawn at exactly that
  width, so a 0–1 axis ended short of its right edge. Each boundary is now
  drawn midway between the two samples it separates; titles keep the sampled
  ranges;
- an inverted scan range was reported with internal parameter names
  ("min_amount must be below max_amount"); the message now states both
  amounts;
- the Chinese console still showed provider failures ("Wise quote request
  failed"), the FX source's tooltip, rate-date and scan-range errors, and the
  cause quoted by the comparison errors in English. Each now carries a stable
  code and parameters: `WiseAPIError`, the graph's `QuoteTimeoutError`,
  `FxLiveUnavailableError`, the new `FxDateError`, build warnings (`params`
  beside `code`), and the FX status in `/api/meta` (`code`, `params`). A
  comparison error quotes the live-rate failure as `reason`, `reason_code`
  and `reason_*` parameters, so the quoted cause is translated too; its
  English now names that cause instead of repeating the fallback sentence.
  Text quoted from a provider or HTTP client (an HTTP status line) stays
  verbatim.

### Changed

- the scan performs exactly one graph build per amount sample, then reuses that
  immutable router for every cost/time weight. The default 12-by-61 grid
  therefore performs 12 graph builds, not 732; the actual count is disclosed
  by the CLI, API, and console;
- the terminal grid merges consecutive cost weights whose rows are identical
  and labels the merged band with its weight range, matching how `sensitivity`
  and `breakeven` compress their axes. The default 61 weights are all still
  sampled; a map with one region now prints one row instead of 61, and the
  footer reports both counts;
- regime boundaries are described only as lying between adjacent sampled
  amounts or weights. No interpolation or smoothing is applied, each amount is
  quoted independently, and boundaries driven by scenario-assumption fees are
  labelled as properties of the model rather than measured market facts;
- `sensitivity` and `breakeven` now share one route-signature primitive without
  changing either module's existing public import surface. The regime analysis
  introduces no rates, timings, fees, or provenance records;
- provider warnings are grouped by network and reason: an unreachable provider
  shows one line with its affected corridors instead of dozens of identical
  rows;
- the amount accepts thousands separators ("1,000.50", "10 000"). A separator
  is only read as grouping between three-digit groups, so an ambiguous "1,5"
  is rejected rather than silently read as fifteen;
- the rate date and scan range validate inline beside their inputs, move focus
  to the field at fault, and pressing Enter in them runs their own analysis
  instead of a route search. The comparison button reads "Compare with latest",
  matching its baseline;
- request errors are readable: FastAPI validation details are listed by field,
  and an unreachable server says to check `remit serve` instead of "Failed to
  fetch";
- the form puts **Find routes** beside the profile and groups the analyses by
  whether they use the entered amount, removing a large empty area that wrapped
  buttons used to leave. Focus returns to the control that started a request,
  results scroll into view when they finish below the fold, and the page title
  names the active view;
- on phones the top bar stays one row, route flows run vertically, stat tiles
  use two columns, panel headers stack, and wide tables show scroll shadows;
  the recipient amount and its difference to #1 stay visible without
  scrolling. Recent searches can be cleared. The FX source moves from the top
  bar into the disclaimer so the one-row bar has room for the language switch;
- the CLI groups provider warnings by network and reason, like the console:
  an unreachable provider is one row with a count and a sample of corridors
  instead of one row per corridor;
- AI explanations answer in the console's language rather than the browser's.

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
