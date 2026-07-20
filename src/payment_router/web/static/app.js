/* payment-router console — vanilla JS, no external dependencies. */
(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);

  const form = $("#route-form");
  const amountInput = $("#amount-input");
  const sourceSelect = $("#source-select");
  const targetSelect = $("#target-select");
  const swapButton = $("#swap-button");
  const routeButton = $("#route-button");
  const decideButton = $("#decide-button");
  const alertsBox = $("#alerts");
  const warningsBox = $("#warnings");
  const resultsBox = $("#results");
  const sourcesBox = $("#sources");

  const CURRENCY_SYMBOLS = { USD: "$", EUR: "€", GBP: "£", CNY: "¥" };
  const PROVENANCE_LABELS = {
    VERIFIED: "Verified",
    INDUSTRY_AVERAGE: "Industry average",
    ESTIMATED: "Estimated",
  };
  const PROFILE_LABELS = { cheapest: "Cheapest", fastest: "Fastest", balanced: "Balanced" };

  const ICONS = {
    error:
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 7.5V13M12 16.4v.05"/></svg>',
    warning:
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 9v4.5M12 17.2v.05"/><path d="M10.3 3.9 2.7 17a2 2 0 0 0 1.7 3h15.2a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>',
    note:
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6.5 9.5 17 4 11.5"/></svg>',
    arrow: '<span class="flow-arrow" aria-hidden="true"></span>',
    cheapest:
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5v9M14.8 9.2c-.6-1-1.6-1.4-2.8-1.4-1.7 0-2.9.9-2.9 2.2 0 2.9 5.8 1.5 5.8 4.3 0 1.3-1.2 2.2-2.9 2.2-1.3 0-2.3-.5-2.9-1.5"/></svg>',
    fastest:
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2.5 4.5 13.5H11L10 21.5l8.7-11H12.5Z"/></svg>',
    balanced:
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.5v17M5.5 20.5h13M12 6 6 8.2l-2.4 5.6a3.4 3.4 0 0 0 4.8 0L6 8.2M12 6l6 2.2 2.4 5.6a3.4 3.4 0 0 1-4.8 0L18 8.2"/></svg>',
    sparkle:
      '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.5 13.8 9l5.5 1.8-5.5 1.8L12 18.2l-1.8-5.6-5.5-1.8L10.2 9Z"/><path d="M19 3v3.4M20.7 4.7h-3.4M5 17.6v2.8M6.4 19H3.6"/></svg>',
  };

  let aiMeta = null;

  const networkSlots = new Map();

  /* ---------- helpers ---------- */

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function svg(markup) {
    const wrap = document.createElement("template");
    wrap.innerHTML = markup.trim();
    return wrap.content.firstChild;
  }

  function currencySymbol(code) {
    return CURRENCY_SYMBOLS[code] || "";
  }

  function fmtNumber(value) {
    const parsed = Number.parseFloat(value);
    if (!Number.isFinite(parsed)) return String(value);
    return parsed.toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function fmtMoney(value, code) {
    return `${currencySymbol(code)}${fmtNumber(value)}`;
  }

  function fmtSigned(value) {
    const parsed = Number.parseFloat(value);
    if (!Number.isFinite(parsed)) return String(value);
    return `${parsed >= 0 ? "+" : "-"}${fmtNumber(Math.abs(parsed))}`;
  }

  function fmtRate(value) {
    const parsed = Number.parseFloat(value);
    if (!Number.isFinite(parsed)) return String(value);
    return String(Number(parsed.toPrecision(6)));
  }

  function humanizeHours(value) {
    const hours = Number.parseFloat(value);
    if (!Number.isFinite(hours)) return `${value} h`;
    const seconds = hours * 3600;
    if (seconds < 90) return `${Math.round(seconds)} s`;
    if (hours < 1) return `${Math.round(hours * 60)} min`;
    if (hours < 10) return `${Math.round(hours * 10) / 10} h`;
    if (hours < 72) return `${Math.round(hours)} h`;
    return `${Math.round((hours / 24) * 10) / 10} d`;
  }

  function networkSlot(name) {
    const key = String(name).toLowerCase();
    if (!networkSlots.has(key)) {
      const slot = networkSlots.size < 8 ? `var(--series-${networkSlots.size + 1})` : "var(--series-other)";
      networkSlots.set(key, slot);
    }
    return networkSlots.get(key);
  }

  function networkChip(name) {
    const chip = el("span", "network-chip");
    const dot = el("span", "dot");
    dot.style.background = networkSlot(name);
    chip.append(dot, document.createTextNode(name));
    return chip;
  }

  function provenanceBadge(kind) {
    return el("span", `badge badge-${String(kind).toLowerCase()}`, PROVENANCE_LABELS[kind] || kind);
  }

  function pathFragment(path, className) {
    const holder = el("span", className);
    path.forEach((code, index) => {
      if (index > 0) holder.append(el("span", "sep", "→"));
      holder.append(document.createTextNode(code));
    });
    return holder;
  }

  /* ---------- theme ---------- */

  const THEME_KEY = "payment-router-theme";
  const storedTheme = localStorage.getItem(THEME_KEY);
  if (storedTheme === "dark" || storedTheme === "light") {
    document.documentElement.dataset.theme = storedTheme;
  }
  $("#theme-toggle").addEventListener("click", () => {
    const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const current = document.documentElement.dataset.theme || (systemDark ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem(THEME_KEY, next);
  });

  /* ---------- alerts, warnings, loading ---------- */

  function clearFeedback() {
    alertsBox.hidden = true;
    alertsBox.replaceChildren();
    warningsBox.hidden = true;
    warningsBox.replaceChildren();
  }

  function showError(message) {
    const alert = el("div", "alert alert-error");
    alert.append(svg(ICONS.error), el("span", "", message));
    alertsBox.replaceChildren(alert);
    alertsBox.hidden = false;
  }

  function warningList(warnings) {
    const list = el("ul");
    warnings.forEach((warning) => {
      list.append(el("li", "", `${warning.network} ${warning.pair}: ${warning.reason}`));
    });
    return list;
  }

  function showWarnings(warnings) {
    if (!warnings || warnings.length === 0) return;
    const alert = el("div", "alert alert-warning");
    const body = el("div");
    body.append(el("strong", "", "Some providers could not quote every corridor"));
    const visibleCount = 5;
    body.append(warningList(warnings.slice(0, visibleCount)));
    if (warnings.length > visibleCount) {
      const rest = warnings.slice(visibleCount);
      const details = el("details");
      details.append(el("summary", "", `Show ${rest.length} more`));
      details.append(warningList(rest));
      body.append(details);
    }
    alert.append(svg(ICONS.warning), body);
    warningsBox.replaceChildren(alert);
    warningsBox.hidden = false;
  }

  function showSkeleton() {
    const card = el("div", "skeleton");
    ["60%", "38%", "82%", "70%"].forEach((width) => {
      const line = el("div", "shimmer");
      line.style.width = width;
      card.append(line);
    });
    resultsBox.replaceChildren(card);
  }

  function setBusy(busy, activeButton) {
    [routeButton, decideButton].forEach((button) => {
      button.disabled = busy;
    });
    if (busy) {
      activeButton.dataset.label = activeButton.textContent;
      activeButton.replaceChildren(svg('<span class="spinner"></span>'), document.createTextNode(" Working…"));
    } else {
      [routeButton, decideButton].forEach((button) => {
        if (button.dataset.label) {
          button.textContent = button.dataset.label;
          delete button.dataset.label;
        }
      });
    }
  }

  /* ---------- fetch ---------- */

  async function errorDetail(response) {
    try {
      const payload = await response.json();
      if (payload && typeof payload.detail === "string") return payload.detail;
    } catch {
      /* non-JSON error body */
    }
    return `Request failed with status ${response.status}.`;
  }

  async function apiGet(path, params) {
    const query = new URLSearchParams(params);
    const response = await fetch(`${path}?${query}`, { headers: { Accept: "application/json" } });
    if (!response.ok) {
      throw new Error(await errorDetail(response));
    }
    return response.json();
  }

  function currentRequest() {
    return {
      source: sourceSelect.value,
      target: targetSelect.value,
      amount: amountInput.value.trim(),
      profile: form.elements.profile.value,
      top_n: form.elements.top_n.value,
    };
  }

  /* ---------- sharable URL state ---------- */

  function requestToParams(kind, request) {
    const params = new URLSearchParams({
      from: request.source,
      to: request.target,
      amount: request.amount,
    });
    if (kind === "decide") {
      params.set("view", "decide");
    } else {
      params.set("profile", request.profile);
      params.set("top_n", request.top_n);
    }
    return params;
  }

  function requestFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const source = params.get("from");
    const target = params.get("to");
    const amount = params.get("amount");
    if (!source || !target || !amount) return null;
    return {
      kind: params.get("view") === "decide" ? "decide" : "route",
      source: source.toUpperCase(),
      target: target.toUpperCase(),
      amount,
      profile: params.get("profile") || "balanced",
      top_n: params.get("top_n") || "1",
    };
  }

  function applyRequestToForm(request) {
    amountInput.value = request.amount;
    const hasOption = (select, value) =>
      [...select.options].some((option) => option.value === value);
    if (hasOption(sourceSelect, request.source)) sourceSelect.value = request.source;
    if (hasOption(targetSelect, request.target)) targetSelect.value = request.target;
    const profileInput = form.querySelector(
      `input[name="profile"][value="${CSS.escape(request.profile)}"]`
    );
    if (profileInput) profileInput.checked = true;
    const topInput = form.querySelector(
      `input[name="top_n"][value="${CSS.escape(String(request.top_n))}"]`
    );
    if (topInput) topInput.checked = true;
  }

  function syncUrl(kind, request) {
    const next = `${window.location.pathname}?${requestToParams(kind, request)}`;
    const current = `${window.location.pathname}${window.location.search}`;
    if (next !== current) history.pushState(null, "", next);
  }

  /* ---------- recent searches ---------- */

  const RECENTS_KEY = "payment-router-recents";
  const MAX_RECENTS = 5;
  const recentsBox = $("#recents");

  function loadRecents() {
    try {
      const parsed = JSON.parse(localStorage.getItem(RECENTS_KEY) || "[]");
      return Array.isArray(parsed) ? parsed.slice(0, MAX_RECENTS) : [];
    } catch {
      return [];
    }
  }

  function saveRecent(kind, request) {
    const entry = {
      kind,
      source: request.source,
      target: request.target,
      amount: request.amount,
      profile: request.profile,
      top_n: request.top_n,
    };
    const keyOf = (item) => JSON.stringify([
      item.kind,
      item.source,
      item.target,
      item.amount,
      item.profile,
      item.top_n,
    ]);
    const next = [
      entry,
      ...loadRecents().filter((item) => keyOf(item) !== keyOf(entry)),
    ].slice(0, MAX_RECENTS);
    try {
      localStorage.setItem(RECENTS_KEY, JSON.stringify(next));
    } catch {
      /* storage unavailable */
    }
    renderRecents();
  }

  function renderRecents() {
    const recents = loadRecents();
    if (recents.length === 0) {
      recentsBox.hidden = true;
      recentsBox.replaceChildren();
      return;
    }
    recentsBox.replaceChildren(el("span", "recents-label", "Recent"));
    recents.forEach((item) => {
      const chip = el("button", "recent-chip");
      chip.type = "button";
      chip.append(
        document.createTextNode(`${fmtNumber(item.amount)} ${item.source}`),
        el("span", "sep", "→"),
        document.createTextNode(item.target),
        el("span", "sep", "·"),
        document.createTextNode(item.kind === "decide" ? "compare" : item.profile)
      );
      chip.addEventListener("click", () => {
        applyRequestToForm(item);
        runRequest(item.kind, item.kind === "decide" ? decideButton : routeButton);
      });
      recentsBox.append(chip);
    });
    recentsBox.hidden = false;
  }

  /* ---------- quote freshness ---------- */

  function quotesMetaNode(quotes) {
    if (!quotes) return null;
    const wrap = el("div", `quotes-meta${quotes.from_cache ? " cached" : ""}`);
    wrap.setAttribute("role", "status");
    wrap.append(el("span", "dot"));
    const time = new Date(quotes.quoted_at);
    const stamp = Number.isNaN(time.getTime()) ? quotes.quoted_at : time.toLocaleTimeString();
    wrap.append(
      document.createTextNode(
        quotes.from_cache ? `Quotes cached from ${stamp}` : `Quotes fetched at ${stamp}`
      )
    );
    return wrap;
  }

  /* ---------- route rendering ---------- */

  function statTile(label, valueNode, sub) {
    const tile = el("div", "stat-tile");
    tile.append(el("div", "stat-label", label));
    const value = el("div", "stat-value");
    value.append(valueNode);
    tile.append(value);
    if (sub) tile.append(el("div", "stat-sub", sub));
    return tile;
  }

  function valueWithUnit(main, unit) {
    const fragment = document.createDocumentFragment();
    fragment.append(document.createTextNode(main));
    if (unit) fragment.append(el("span", "unit", unit));
    return fragment;
  }

  function flowDiagram(route) {
    const flow = el("div", "flow");
    route.path.forEach((code, index) => {
      if (index > 0) {
        const hop = route.hops[index - 1];
        const edge = el("div", "flow-edge");
        edge.append(networkChip(hop.network));
        edge.append(svg(ICONS.arrow));
        edge.append(
          el(
            "div",
            "flow-edge-meta",
            `fee $${fmtNumber(hop.fee_usd)} · ${humanizeHours(hop.time_hours)}`
          )
        );
        flow.append(edge);
      }
      const isFinal = index === route.path.length - 1;
      const node = el("div", `flow-node${isFinal ? " flow-node-final" : ""}`);
      node.append(el("div", "currency", code));
      node.append(el("div", "amount", `${currencySymbol(code)}${fmtNumber(route.amounts[index])}`));
      flow.append(node);
    });
    return flow;
  }

  function hopTable(route) {
    const wrap = el("div", "hop-table-wrap");
    const table = el("table", "data-table");
    const head = el("thead");
    const headRow = el("tr");
    [
      ["Hop", ""],
      ["Network", ""],
      ["Pair", ""],
      ["Fee (USD)", "num"],
      ["Time", "num"],
      ["FX rate", "num"],
      ["Evidence", ""],
    ].forEach(([label, className]) => {
      headRow.append(el("th", className, label));
    });
    head.append(headRow);
    table.append(head);

    const body = el("tbody");
    route.hops.forEach((hop, index) => {
      const row = el("tr");
      row.append(el("td", "num", String(index + 1)));
      const networkCell = el("td");
      networkCell.append(networkChip(hop.network));
      row.append(networkCell);
      row.append(el("td", "", `${hop.from} → ${hop.to}`));
      row.append(el("td", "num", fmtNumber(hop.fee_usd)));
      row.append(el("td", "num", humanizeHours(hop.time_hours)));
      row.append(el("td", "num", fmtRate(hop.fx_rate)));
      const evidenceCell = el("td");
      const badges = el("div", "badges");
      const kinds = new Set(
        [hop.fee_data_source, hop.time_data_source, hop.fx_data_source].filter(Boolean)
      );
      ["VERIFIED", "INDUSTRY_AVERAGE", "ESTIMATED"].forEach((kind) => {
        if (kinds.has(kind)) badges.append(provenanceBadge(kind));
      });
      evidenceCell.append(badges);
      row.append(evidenceCell);
      body.append(row);
    });
    table.append(body);
    wrap.append(table);
    return wrap;
  }

  function mermaidDetails(route) {
    const details = el("details", "mermaid-details");
    const summary = el("summary", "", "Mermaid diagram source");
    details.append(summary);
    const body = el("div", "mermaid-body");
    const pre = el("pre");
    pre.append(el("code", "", route.mermaid));
    const copy = el("button", "copy-button", "Copy");
    copy.type = "button";
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(route.mermaid);
        copy.textContent = "Copied";
        setTimeout(() => {
          copy.textContent = "Copy";
        }, 1400);
      } catch {
        copy.textContent = "Select & copy";
      }
    });
    body.append(pre, copy);
    details.append(body);
    return details;
  }

  function routeCard(route, rank, showRank) {
    const card = el("article", "panel route-card");

    const header = el("div", "panel-header");
    const title = el("div", "route-title");
    if (showRank) title.append(el("span", "rank-chip", `#${rank}`));
    title.append(pathFragment(route.path, "route-path"));
    header.append(title);
    const badges = el("div", "badges");
    route.provenance.forEach((kind) => badges.append(provenanceBadge(kind)));
    header.append(badges);
    card.append(header);

    const stats = el("div", "stat-row");
    stats.append(
      statTile(
        "Recipient gets",
        valueWithUnit(fmtMoney(route.final_amount, route.target_currency), route.target_currency),
        `from ${fmtMoney(route.source_amount, route.source_currency)} ${route.source_currency} sent`
      )
    );
    stats.append(
      statTile(
        "Total fees",
        valueWithUnit(`$${fmtNumber(route.total_fee_usd)}`, "USD"),
        route.hops.length === 1 ? "1 hop" : `${route.hops.length} hops`
      )
    );
    stats.append(
      statTile(
        "Estimated time",
        valueWithUnit(humanizeHours(route.total_time_hours)),
        `${route.total_time_hours} hours`
      )
    );
    card.append(stats);

    card.append(flowDiagram(route));
    if (route.hops.length > 0) card.append(hopTable(route));
    card.append(mermaidDetails(route));
    return card;
  }

  function renderRoutes(data) {
    const nodes = data.routes.map((route, index) =>
      routeCard(route, index + 1, data.routes.length > 1)
    );
    const meta = quotesMetaNode(data.quotes);
    if (meta) nodes.unshift(meta);
    resultsBox.replaceChildren(...nodes);
  }

  /* ---------- decision rendering ---------- */

  function decisionCard(decision) {
    const route = decision.route;
    const recommended = decision.profile === "balanced";
    const card = el("article", `decision-card${recommended ? " recommended" : ""}`);

    const head = el("div", "decision-head");
    const profile = el("span", "decision-profile");
    profile.append(svg(ICONS[decision.profile] || ICONS.balanced));
    profile.append(document.createTextNode(PROFILE_LABELS[decision.profile] || decision.profile));
    head.append(profile);
    if (recommended) head.append(el("span", "badge badge-recommended", "★ Recommended"));
    card.append(head);

    const body = el("div", "decision-body");
    const receive = el("div", "decision-receive");
    receive.append(
      valueWithUnit(fmtMoney(route.final_amount, route.target_currency), route.target_currency)
    );
    body.append(receive);

    const metrics = el("div", "decision-metrics");
    metrics.append(el("span", "", `fee $${fmtNumber(route.total_fee_usd)}`));
    metrics.append(el("span", "", `eta ${humanizeHours(route.total_time_hours)}`));
    body.append(metrics);

    body.append(pathFragment(route.path, "decision-path"));

    const networks = el("div", "decision-networks");
    [...new Set(route.hops.map((hop) => hop.network))].forEach((name) =>
      networks.append(networkChip(name))
    );
    body.append(networks);

    const badges = el("div", "badges");
    route.provenance.forEach((kind) => badges.append(provenanceBadge(kind)));
    body.append(badges);

    card.append(body);
    return card;
  }

  function compareChart(decisions) {
    const measures = [
      {
        title: "Total fee (USD)",
        value: (decision) => Number.parseFloat(decision.route.total_fee_usd),
        label: (decision) => `$${fmtNumber(decision.route.total_fee_usd)}`,
      },
      {
        title: "Estimated time",
        value: (decision) => Number.parseFloat(decision.route.total_time_hours),
        label: (decision) => humanizeHours(decision.route.total_time_hours),
      },
    ];
    const panel = el("section", "panel");
    const header = el("div", "panel-header");
    header.append(el("h2", "", "Profile comparison"));
    header.append(el("span", "hint", "Same corridor, three optimization targets"));
    panel.append(header);
    const grid = el("div", "compare-grid");
    measures.forEach((measure) => {
      const chart = el("div", "mini-chart");
      chart.append(el("div", "mini-chart-title", measure.title));
      const max = Math.max(...decisions.map(measure.value), 0);
      decisions.forEach((decision) => {
        const row = el(
          "div",
          `bar-row${decision.profile === "balanced" ? " emphasis" : ""}`
        );
        row.append(
          el("span", "bar-label", PROFILE_LABELS[decision.profile] || decision.profile)
        );
        const track = el("div", "bar-track");
        const bar = el("div", "bar");
        const share = max > 0 ? Math.max((measure.value(decision) / max) * 100, 2) : 2;
        bar.style.width = `${share}%`;
        track.append(bar);
        row.append(track);
        row.append(el("span", "bar-value", measure.label(decision)));
        chart.append(row);
      });
      grid.append(chart);
    });
    panel.append(grid);
    return panel;
  }

  function renderDecisions(data) {
    const grid = el("div", "decision-grid");
    data.decisions.forEach((decision) => grid.append(decisionCard(decision)));

    const nodes = [grid];
    const meta = quotesMetaNode(data.quotes);
    if (meta) nodes.unshift(meta);
    if (data.tradeoff && !data.tradeoff.same_route_for_all_profiles) {
      nodes.push(compareChart(data.decisions));
    }
    if (data.tradeoff) {
      const note = el("div", "tradeoff-note");
      const body = el("div");
      body.append(el("strong", "", "Decision note "));
      if (data.tradeoff.same_route_for_all_profiles) {
        body.append(
          document.createTextNode("One route wins on cost, speed, and the balanced profile.")
        );
      } else {
        const target =
          data.decisions.length > 0 ? data.decisions[0].route.target_currency : "";
        const deltaSpan = (value, unit, lowerIsBetter) => {
          const good = lowerIsBetter
            ? Number.parseFloat(value) <= 0
            : Number.parseFloat(value) >= 0;
          return el("span", good ? "delta-positive" : "delta-negative", `${fmtSigned(value)} ${unit}`);
        };
        body.append(
          document.createTextNode("Balanced vs cheapest: fee "),
          deltaSpan(data.tradeoff.balanced_fee_delta_usd, "USD", true),
          document.createTextNode(", time saved "),
          deltaSpan(data.tradeoff.balanced_hours_saved_vs_cheapest, "h", false),
          document.createTextNode(", recipient amount "),
          deltaSpan(data.tradeoff.balanced_receive_delta, target, false),
          document.createTextNode(".")
        );
      }
      note.append(svg(ICONS.note), body);
      nodes.push(note);
    }
    resultsBox.replaceChildren(...nodes);
  }

  /* ---------- sources rendering ---------- */

  function renderSources(records) {
    const wrap = el("div", "hop-table-wrap");
    const table = el("table", "data-table");
    const head = el("thead");
    const headRow = el("tr");
    ["Evidence", "Network", "Metric & value", "Class", "Checked", "Reference"].forEach((label) => {
      headRow.append(el("th", "", label));
    });
    head.append(headRow);
    table.append(head);

    const body = el("tbody");
    records.forEach((record) => {
      const row = el("tr");
      row.append(el("td", "", record.evidence_id));
      row.append(el("td", "", record.network));
      const metricCell = el("td");
      metricCell.append(document.createTextNode(`${record.metric}: ${record.value}`));
      metricCell.append(el("span", "caveat", record.caveat));
      row.append(metricCell);
      const classCell = el("td");
      classCell.append(provenanceBadge(record.classification));
      row.append(classCell);
      row.append(el("td", "num", record.checked_on));
      const referenceCell = el("td");
      if (record.reference) {
        const link = el("a", "reference-link", "source ↗");
        link.href = record.reference;
        link.target = "_blank";
        link.rel = "noopener";
        referenceCell.append(link);
      } else {
        referenceCell.append(el("span", "caveat", "assumption"));
      }
      row.append(referenceCell);
      body.append(row);
    });
    table.append(body);
    wrap.append(table);
    sourcesBox.replaceChildren(wrap);
  }

  /* ---------- AI insight ---------- */

  function renderAiText(output, text, streaming) {
    output.replaceChildren();
    text.split(/\n{2,}/).forEach((paragraphText) => {
      if (!paragraphText.trim()) return;
      const paragraph = el("p");
      paragraphText.split(/\*\*([^*]+)\*\*/g).forEach((part, index) => {
        if (!part) return;
        paragraph.append(index % 2 === 1 ? el("strong", "", part) : document.createTextNode(part));
      });
      output.append(paragraph);
    });
    if (streaming) {
      const lastParagraph = output.lastElementChild || output.appendChild(el("p"));
      lastParagraph.append(el("span", "ai-caret"));
    }
  }

  async function streamExplanation(kind, data, output) {
    const response = await fetch("/api/explain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, data, lang: navigator.language || "en" }),
    });
    if (!response.ok || !response.body) {
      throw new Error(await errorDetail(response));
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let fullText = "";

    // Coalesce renders to one per animation frame — rebuilding the output
    // on every SSE delta is quadratic over the stream.
    let renderQueued = false;
    const queueRender = () => {
      if (renderQueued) return;
      renderQueued = true;
      requestAnimationFrame(() => {
        renderQueued = false;
        renderAiText(output, fullText, true);
      });
    };

    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop();
      for (const part of parts) {
        if (!part.startsWith("data: ")) continue;
        const event = JSON.parse(part.slice(6));
        if (event.type === "delta") {
          fullText += event.text;
          queueRender();
        } else if (event.type === "done") {
          renderAiText(output, fullText, false);
          return { model: event.model };
        } else if (event.type === "error") {
          throw new Error(event.message || "AI request failed.");
        }
      }
    }
    renderAiText(output, fullText, false);
    return { model: null };
  }

  function appendAiPanel(kind, data) {
    if (!aiMeta || !aiMeta.enabled) return;
    const panel = el("section", "ai-panel");

    const head = el("div", "ai-head");
    const title = el("span", "ai-title");
    title.append(svg(ICONS.sparkle), document.createTextNode("AI insight"));
    head.append(title);
    const button = el("button", "button button-ai", "Explain this result");
    button.type = "button";
    head.append(button);
    panel.append(head);

    const body = el("div", "ai-body");
    body.hidden = true;
    const output = el("div", "ai-output");
    // The results container is aria-live; opting the streamed output out
    // stops screen readers re-announcing the whole text on every delta.
    output.setAttribute("aria-live", "off");
    const footer = el("div", "ai-footer");
    footer.hidden = true;
    body.append(output, footer);
    panel.append(body);

    button.addEventListener("click", async () => {
      button.disabled = true;
      button.replaceChildren(svg('<span class="spinner"></span>'), document.createTextNode(" Thinking…"));
      body.hidden = false;
      footer.hidden = true;
      output.replaceChildren(el("p", "", ""));
      output.firstChild.append(el("span", "ai-caret"));
      try {
        const result = await streamExplanation(kind, data, output);
        footer.textContent =
          `Generated by ${result.model || "Claude"} from the simulated data above — ` +
          "not live quotes, not financial advice.";
        footer.hidden = false;
        button.textContent = "Explain again";
      } catch (error) {
        output.replaceChildren(
          el("p", "ai-error", error instanceof Error ? error.message : "AI request failed.")
        );
        button.textContent = "Retry";
      } finally {
        button.disabled = false;
      }
    });

    resultsBox.append(panel);
  }

  /* ---------- result decoration (motion) ---------- */

  function decorateResults() {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    [...resultsBox.children].forEach((child, index) => {
      child.style.animationDelay = `${Math.min(index * 70, 350)}ms`;
    });
    if (reducedMotion) return;

    resultsBox.querySelectorAll(".stat-value, .decision-receive").forEach((element) => {
      const node = element.firstChild;
      if (!node || node.nodeType !== Node.TEXT_NODE) return;
      const original = node.textContent;
      const match = original.match(/^([^0-9]*)([\d,]+)(\.\d+)?(.*)$/);
      if (!match) return;
      const prefix = match[1];
      const suffix = match[4] || "";
      const decimals = match[3] ? match[3].length - 1 : 0;
      const target = Number.parseFloat(match[2].replace(/,/g, "") + (match[3] || ""));
      if (!Number.isFinite(target)) return;
      const start = performance.now();
      const duration = 620;
      const step = (now) => {
        const t = Math.min((now - start) / duration, 1);
        const eased = 1 - (1 - t) ** 3;
        node.textContent =
          prefix +
          (target * eased).toLocaleString("en-US", {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
          }) +
          suffix;
        if (t < 1) {
          requestAnimationFrame(step);
        } else {
          node.textContent = original;
        }
      };
      requestAnimationFrame(step);
    });
  }

  /* ---------- actions ---------- */

  async function runRequest(kind, activeButton) {
    clearFeedback();
    setBusy(true, activeButton);
    showSkeleton();
    try {
      const request = currentRequest();
      const data =
        kind === "decide"
          ? await apiGet("/api/decide", {
              source: request.source,
              target: request.target,
              amount: request.amount,
            })
          : await apiGet("/api/route", request);
      showWarnings(data.warnings);
      if (kind === "decide") {
        renderDecisions(data);
      } else {
        renderRoutes(data);
      }
      appendAiPanel(kind, data);
      decorateResults();
      saveRecent(kind, request);
      syncUrl(kind, request);
    } catch (error) {
      resultsBox.replaceChildren();
      showError(error instanceof Error ? error.message : "Unexpected error.");
    } finally {
      setBusy(false, activeButton);
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    runRequest("route", routeButton);
  });

  decideButton.addEventListener("click", () => runRequest("decide", decideButton));

  const initialEmptyState = resultsBox.firstElementChild;

  window.addEventListener("popstate", () => {
    const request = requestFromUrl();
    if (request) {
      applyRequestToForm(request);
      runRequest(request.kind, request.kind === "decide" ? decideButton : routeButton);
    } else {
      clearFeedback();
      resultsBox.replaceChildren(initialEmptyState);
    }
  });

  swapButton.addEventListener("click", () => {
    const source = sourceSelect.value;
    sourceSelect.value = targetSelect.value;
    targetSelect.value = source;
  });

  /* ---------- boot ---------- */

  function populateCurrencies(currencies) {
    [sourceSelect, targetSelect].forEach((select) => {
      select.replaceChildren();
      currencies.forEach((code) => {
        const option = el("option", "", code);
        option.value = code;
        select.append(option);
      });
    });
    sourceSelect.value = currencies.includes("USD") ? "USD" : currencies[0];
    const preferredTarget = currencies.find(
      (code) => code !== sourceSelect.value && (code === "CNY" || code === "EUR")
    );
    targetSelect.value =
      preferredTarget || currencies.find((code) => code !== sourceSelect.value) || currencies[0];
  }

  async function boot() {
    renderRecents();
    const metaPromise = apiGet("/api/meta", {});
    const sourcesPromise = apiGet("/api/sources", {});
    try {
      const meta = await metaPromise;
      aiMeta = meta.ai || null;
      populateCurrencies(meta.currencies);
      meta.networks.forEach((network) => networkSlot(network.name));
      const versionChip = $("#version-chip");
      versionChip.textContent = `v${meta.version}`;
      versionChip.hidden = false;
      if (meta.disclaimer) {
        $("#disclaimer-text").textContent = meta.disclaimer;
        $("#disclaimer").hidden = false;
      }
      const urlRequest = requestFromUrl();
      if (urlRequest) {
        applyRequestToForm(urlRequest);
        runRequest(urlRequest.kind, urlRequest.kind === "decide" ? decideButton : routeButton);
      }
    } catch (error) {
      showError(
        error instanceof Error
          ? `Could not load simulator metadata: ${error.message}`
          : "Could not load simulator metadata."
      );
    }
    try {
      const sources = await sourcesPromise;
      renderSources(sources.records);
    } catch {
      sourcesBox.replaceChildren(
        el("div", "empty-state", "The provenance registry could not be loaded.")
      );
    }
  }

  boot();
})();
