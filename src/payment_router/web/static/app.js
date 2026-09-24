/* payment-router console — vanilla JS, no external dependencies. */
(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);

  const form = $("#route-form");
  const amountInput = $("#amount-input");
  const amountError = $("#amount-error");
  const sourceSelect = $("#source-select");
  const targetSelect = $("#target-select");
  const swapButton = $("#swap-button");
  const routeButton = $("#route-button");
  const decideButton = $("#decide-button");
  const sensitivityButton = $("#sensitivity-button");
  const regimeButton = $("#regime-button");
  const compareButton = $("#compare-button");
  const breakevenButton = $("#breakeven-button");
  const onDateInput = $("#on-date");
  const dateError = $("#date-error");
  const rangeMinInput = $("#range-min");
  const rangeMaxInput = $("#range-max");
  const rangeError = $("#range-error");
  const rangeCurrency = $("#range-currency");
  const alertsBox = $("#alerts");
  const warningsBox = $("#warnings");
  const resultsBox = $("#results");
  const resultsStatus = $("#results-status");
  const resultsContext = $("#results-context");
  const rerunButton = $("#rerun-button");
  const sourcesBox = $("#sources");
  const themeToggle = $("#theme-toggle");
  const scenarioSummary = $("#scenario-summary");
  const quickAmountButtons = [...document.querySelectorAll("[data-quick-amount]")];
  const requestControls = [...form.querySelectorAll("input, select, button")];
  const actionButtons = [
    routeButton,
    decideButton,
    sensitivityButton,
    regimeButton,
    compareButton,
    breakevenButton,
  ];

  const TITLE_BASE = document.title;
  const DEFAULT_SCAN = { min: "10", max: "100000" };
  const PROFILES = ["cheapest", "fastest", "balanced"];
  // Cost weight of each profile, matching service.preference_for_profile.
  const PROFILE_COST_WEIGHTS = { cheapest: 1, fastest: 0, balanced: 0.5 };
  const VIEW_KINDS = ["route", "decide", "sensitivity", "compare", "breakeven", "regime"];
  const RANGE_KINDS = ["breakeven", "regime"];
  const VIEW_LABELS = {
    route: "Route search",
    decide: "Profile comparison",
    sensitivity: "Sensitivity analysis",
    compare: "Rate-date comparison",
    breakeven: "Break-even scan",
    regime: "Regime map",
  };
  const ENDPOINTS = {
    route: "/api/route",
    decide: "/api/decide",
    sensitivity: "/api/sensitivity",
    compare: "/api/compare",
    breakeven: "/api/breakeven",
    regime: "/api/regime",
  };

  const CURRENCY_SYMBOLS = {
    USD: "$",
    EUR: "€",
    GBP: "£",
    CNY: "¥",
    HKD: "HK$",
    SGD: "S$",
  };
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
  let resultsAnnouncementFrame = null;
  let lastSuccessfulRun = null;
  // Aborts work owned by the results on screen (an AI stream) once they are
  // replaced. It is separate from the request run, which ends on render.
  let viewController = null;
  // Set by the amount-axis views so the "your scenario" marker can follow
  // the form without re-running the scan: the marker is purely client-side.
  let scenarioMarkerUpdater = null;

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

  function fmtAmountLabel(value) {
    const parsed = Number.parseFloat(value);
    if (!Number.isFinite(parsed)) return String(value);
    return parsed.toLocaleString("en-US", { maximumFractionDigits: 2 });
  }

  function fmtCompact(value) {
    const parsed = Number.parseFloat(value);
    if (!Number.isFinite(parsed)) return String(value);
    return parsed.toLocaleString("en-US", { notation: "compact", maximumFractionDigits: 1 });
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

  // People type grouping separators ("1,000", "10 000"); the API wants a
  // plain decimal. A separator is only accepted between groups of exactly
  // three digits, so an ambiguous "1,5" (a decimal comma?) is rejected by
  // validation instead of being silently read as fifteen.
  const GROUPED_AMOUNT = /^[+]?\d{1,3}([,\s'_])\d{3}(?:\1\d{3})*(?:\.\d*)?$/;
  const DECIMAL_AMOUNT = /^[+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i;

  function normalizeAmount(raw) {
    const text = String(raw ?? "").trim();
    return GROUPED_AMOUNT.test(text) ? text.replace(/[,\s'_]/g, "") : text;
  }

  function parsePositiveAmount(raw) {
    const text = normalizeAmount(raw);
    const value = Number(text);
    if (!DECIMAL_AMOUNT.test(text) || !Number.isFinite(value) || value <= 0) return null;
    return { text, value };
  }

  function canonicalAmount(raw) {
    const parsed = parsePositiveAmount(raw);
    return parsed ? String(parsed.value) : String(raw ?? "");
  }

  function prefersReducedMotion() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function slotColor(index) {
    return index < 8 ? `var(--series-${index + 1})` : "var(--series-other)";
  }

  function routeKey(route) {
    return `${route.path.join(">")}|${route.hops.map((hop) => hop.network).join(">")}`;
  }

  function routeNetworks(route) {
    return [...new Set(route.hops.map((hop) => hop.network))].join(", ");
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
  let storedTheme = null;
  try {
    storedTheme = localStorage.getItem(THEME_KEY);
  } catch {
    /* storage can be unavailable in private or hardened browser contexts */
  }
  if (storedTheme === "dark" || storedTheme === "light") {
    document.documentElement.dataset.theme = storedTheme;
  }

  function currentTheme() {
    const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    return document.documentElement.dataset.theme || (systemDark ? "dark" : "light");
  }

  function syncThemeControl() {
    const isDark = currentTheme() === "dark";
    themeToggle.setAttribute("aria-pressed", String(isDark));
    themeToggle.setAttribute(
      "aria-label",
      isDark ? "Switch to light theme" : "Switch to dark theme"
    );
  }

  syncThemeControl();
  themeToggle.addEventListener("click", () => {
    const current = currentTheme();
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    syncThemeControl();
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      /* the selected theme still applies for this page */
    }
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
    alert.setAttribute("role", "alert");
    alert.append(svg(ICONS.error), el("span", "", message));
    alertsBox.replaceChildren(alert);
    alertsBox.hidden = false;
  }

  function formatPair(pair) {
    return pair === "*->*" ? "all corridors" : String(pair).replace("->", " → ");
  }

  // A provider that is down fails every corridor with the same reason; one
  // line per network and reason keeps thirty identical rows from burying
  // the one failure that differs.
  function groupWarnings(warnings) {
    const groups = new Map();
    warnings.forEach((warning) => {
      const key = `${warning.network}\u0000${warning.reason}`;
      if (!groups.has(key)) {
        groups.set(key, { network: warning.network, reason: warning.reason, pairs: [] });
      }
      groups.get(key).pairs.push(formatPair(warning.pair));
    });
    return [...groups.values()];
  }

  function warningItem(group) {
    const item = el("li");
    item.append(el("strong", "", group.network), document.createTextNode(` — ${group.reason}`));
    if (group.pairs.length === 1) {
      item.append(el("span", "warning-pairs-inline", ` (${group.pairs[0]})`));
    } else {
      const details = el("details", "warning-pairs");
      details.append(el("summary", "", `${group.pairs.length} corridors`));
      details.append(el("p", "", group.pairs.join(", ")));
      item.append(details);
    }
    return item;
  }

  function showWarnings(warnings) {
    if (!warnings || warnings.length === 0) return;
    const groups = groupWarnings(warnings);
    const alert = el("div", "alert alert-warning");
    alert.setAttribute("role", "status");
    const body = el("div");
    body.append(el("strong", "", "Some providers could not quote every corridor"));
    body.append(el("p", "alert-note", "The results below were computed without those quotes."));
    const visibleCount = 4;
    const list = el("ul");
    groups.slice(0, visibleCount).forEach((group) => list.append(warningItem(group)));
    body.append(list);
    if (groups.length > visibleCount) {
      const rest = groups.slice(visibleCount);
      const details = el("details");
      details.append(el("summary", "", `Show ${rest.length} more`));
      const restList = el("ul");
      rest.forEach((group) => restList.append(warningItem(group)));
      details.append(restList);
      body.append(details);
    }
    alert.append(svg(ICONS.warning), body);
    warningsBox.replaceChildren(alert);
    warningsBox.hidden = false;
  }

  function showSkeleton(kind) {
    const card = el("div", "skeleton");
    const head = el("div", "skeleton-head");
    const label = el("span", "skeleton-label");
    label.append(svg('<span class="spinner"></span>'), document.createTextNode(`${VIEW_LABELS[kind]} running…`));
    const cancel = el("button", "button button-ghost button-small", "Cancel");
    cancel.type = "button";
    cancel.title = "Stop this request (Esc)";
    cancel.addEventListener("click", cancelActiveRun);
    head.append(label, cancel);
    card.append(head);
    if (RANGE_KINDS.includes(kind)) {
      card.append(
        el(
          "p",
          "skeleton-note",
          "Every sampled amount needs its own quote round, so a scan takes longer than a single route."
        )
      );
    }
    ["60%", "38%", "82%", "70%"].forEach((width) => {
      const line = el("div", "shimmer");
      line.style.width = width;
      card.append(line);
    });
    resultsBox.replaceChildren(card);
  }

  function announceResults(message) {
    if (resultsAnnouncementFrame !== null) {
      cancelAnimationFrame(resultsAnnouncementFrame);
    }
    resultsStatus.textContent = "";
    resultsAnnouncementFrame = requestAnimationFrame(() => {
      resultsStatus.textContent = message;
      resultsAnnouncementFrame = null;
    });
  }

  function completionMessage(kind, data) {
    const countMessage = (count, singular) =>
      `${count} ${singular}${count === 1 ? "" : "s"} shown.`;
    if (kind === "decide") {
      return `Profile comparison complete. ${countMessage(data.decisions?.length ?? 0, "profile")}`;
    }
    if (kind === "sensitivity") {
      return `Sensitivity analysis complete. ${countMessage(data.regions?.length ?? 0, "preference region")}`;
    }
    if (kind === "regime") {
      return `Regime map complete. ${countMessage(data.regions?.length ?? 0, "connected region")}`;
    }
    if (kind === "compare") {
      return "Historical comparison complete. Baseline and selected rate date are shown.";
    }
    if (kind === "breakeven") {
      return `Break-even analysis complete. ${countMessage(data.regions?.length ?? 0, "amount region")}`;
    }
    return `Route search complete. ${countMessage(data.routes?.length ?? 0, "candidate route")}`;
  }

  function buttonForKind(kind) {
    if (kind === "compare") return compareButton;
    if (kind === "breakeven") return breakevenButton;
    if (kind === "regime") return regimeButton;
    if (kind === "decide") return decideButton;
    if (kind === "sensitivity") return sensitivityButton;
    return routeButton;
  }

  function restoreButtonLabels() {
    actionButtons.forEach((button) => {
      if (button.dataset.label) {
        button.textContent = button.dataset.label;
        delete button.dataset.label;
      }
    });
  }

  // Disabling the focused control drops focus to <body>; remembering it lets
  // a keyboard user continue from the same place once the request settles.
  let focusBeforeBusy = null;

  function restoreFocus(fallback) {
    const previous = focusBeforeBusy;
    focusBeforeBusy = null;
    const active = document.activeElement;
    if (active && active !== document.body) return; // the user already moved on
    const usable = (node) =>
      node && node.isConnected && !node.disabled && !node.closest("[hidden]");
    const target = usable(previous) ? previous : fallback;
    if (usable(target)) target.focus({ preventScroll: true });
  }

  function setBusy(busy, activeButton) {
    if (busy && focusBeforeBusy === null) focusBeforeBusy = document.activeElement;
    requestControls.forEach((control) => {
      control.disabled = busy;
    });
    form.setAttribute("aria-busy", String(busy));
    resultsBox.setAttribute("aria-busy", String(busy));
    // A superseding run may use a different button; only one spinner shows.
    restoreButtonLabels();
    if (busy) {
      activeButton.dataset.label = activeButton.textContent.trim();
      activeButton.replaceChildren(svg('<span class="spinner"></span>'), document.createTextNode(" Working…"));
    } else {
      restoreFocus(activeButton);
    }
  }

  /* ---------- fetch ---------- */

  async function errorDetail(response) {
    try {
      const payload = await response.json();
      const detail = payload ? payload.detail : undefined;
      if (typeof detail === "string") return detail;
      // FastAPI validation errors arrive as a list of {loc, msg}.
      if (Array.isArray(detail) && detail.length > 0) {
        return detail
          .map((issue) => {
            const field = Array.isArray(issue.loc)
              ? issue.loc.filter((part) => part !== "query" && part !== "body").join(".")
              : "";
            return field ? `${field}: ${issue.msg}` : String(issue.msg);
          })
          .join("; ");
      }
    } catch {
      /* non-JSON error body */
    }
    if (response.status >= 500) {
      return `The simulator server failed (HTTP ${response.status}). Check the terminal running remit serve.`;
    }
    return `Request failed with status ${response.status}.`;
  }

  const UNREACHABLE_MESSAGE =
    "Cannot reach the local simulator server. Check that remit serve is still running, then try again.";

  async function send(path, init) {
    try {
      return await fetch(path, init);
    } catch (error) {
      if (isAbort(error)) throw error;
      throw new Error(UNREACHABLE_MESSAGE);
    }
  }

  async function apiGet(path, params, signal) {
    const query = new URLSearchParams(params);
    const response = await send(`${path}?${query}`, {
      headers: { Accept: "application/json" },
      signal,
    });
    if (!response.ok) {
      throw new Error(await errorDetail(response));
    }
    return response.json();
  }

  // The buttons disable themselves while a request is open, but history
  // navigation does not go through them: holding the back button fires
  // popstate repeatedly and starts a run each time. Without this guard the
  // slowest response would win and could contradict the address bar.
  let activeRun = null;

  function beginRun() {
    if (activeRun) activeRun.abort();
    activeRun = new AbortController();
    return activeRun;
  }

  function cancelActiveRun() {
    if (!activeRun) return;
    activeRun.cancelledByUser = true;
    activeRun.abort();
  }

  function isAbort(error) {
    return error instanceof DOMException && error.name === "AbortError";
  }

  function currentRequest() {
    return {
      source: sourceSelect.value,
      target: targetSelect.value,
      amount: normalizeAmount(amountInput.value),
      profile: form.elements.profile.value || "balanced",
      top_n: form.elements.top_n.value || "1",
      on_date: onDateInput.value,
      min_amount: normalizeAmount(rangeMinInput.value),
      max_amount: normalizeAmount(rangeMaxInput.value),
    };
  }

  function updateScenarioSummary() {
    const parsed = parsePositiveAmount(amountInput.value);
    const amountLabel = parsed
      ? parsed.value.toLocaleString("en-US", { maximumFractionDigits: 2 })
      : amountInput.value.trim() || "—";
    const profile = PROFILE_LABELS[form.elements.profile.value] || "Balanced";
    const candidateCount = form.elements.top_n.value;
    const candidates = candidateCount === "1" ? "Best route" : `Top ${candidateCount} routes`;
    scenarioSummary.textContent =
      `${amountLabel} ${sourceSelect.value || "—"} → ${targetSelect.value || "—"}` +
      ` · ${profile} · ${candidates}`;
    rangeCurrency.textContent = sourceSelect.value || "";

    quickAmountButtons.forEach((button) => {
      const active = parsed !== null && parsed.value === Number(button.dataset.quickAmount);
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });

    if (scenarioMarkerUpdater) scenarioMarkerUpdater(currentRequest());
  }

  /* ---------- validation ---------- */

  function setFieldError(input, errorNode, message) {
    if (message) {
      input.setAttribute("aria-invalid", "true");
      errorNode.textContent = message;
      errorNode.hidden = false;
    } else {
      input.removeAttribute("aria-invalid");
      errorNode.textContent = "";
      errorNode.hidden = true;
    }
  }

  function clearRangeError() {
    rangeMinInput.removeAttribute("aria-invalid");
    setFieldError(rangeMaxInput, rangeError, "");
  }

  function clearFieldErrors() {
    setFieldError(amountInput, amountError, "");
    setFieldError(onDateInput, dateError, "");
    clearRangeError();
  }

  function validateAmount() {
    if (parsePositiveAmount(amountInput.value)) return true;
    setFieldError(
      amountInput,
      amountError,
      "Enter an amount greater than zero, such as 1000 or 1,000.50."
    );
    amountInput.focus();
    return false;
  }

  function validateRange() {
    const low = parsePositiveAmount(rangeMinInput.value);
    const high = parsePositiveAmount(rangeMaxInput.value);
    let culprit = null;
    let message = "";
    if (!low) {
      culprit = rangeMinInput;
      message = "Enter a smallest scan amount greater than zero.";
    } else if (!high) {
      culprit = rangeMaxInput;
      message = "Enter a largest scan amount greater than zero.";
    } else if (low.value >= high.value) {
      culprit = rangeMaxInput;
      message = "The scan range must end above where it starts.";
    }
    if (!culprit) return true;
    culprit.setAttribute("aria-invalid", "true");
    rangeError.textContent = message;
    rangeError.hidden = false;
    culprit.focus();
    return false;
  }

  function validateDate() {
    const value = onDateInput.value;
    let message = "";
    if (!value) {
      message = "Pick a past rate date to compare with the latest ECB fixing.";
    } else if (onDateInput.min && value < onDateInput.min) {
      message = `ECB reference rates start on ${onDateInput.min}.`;
    } else if (onDateInput.max && value > onDateInput.max) {
      message = "Pick a date that is not in the future.";
    }
    if (!message) return true;
    setFieldError(onDateInput, dateError, message);
    onDateInput.focus();
    return false;
  }

  function validateRequest(kind) {
    clearFieldErrors();
    if (RANGE_KINDS.includes(kind)) return validateRange();
    if (!validateAmount()) return false;
    return kind === "compare" ? validateDate() : true;
  }

  form.addEventListener("input", (event) => {
    if (event.target === amountInput) setFieldError(amountInput, amountError, "");
    if (event.target === rangeMinInput || event.target === rangeMaxInput) clearRangeError();
    if (event.target === onDateInput) setFieldError(onDateInput, dateError, "");
    updateScenarioSummary();
    markResultsStale();
  });
  form.addEventListener("change", () => {
    updateScenarioSummary();
    markResultsStale();
  });
  quickAmountButtons.forEach((button) => {
    button.addEventListener("click", () => {
      amountInput.value = button.dataset.quickAmount;
      setFieldError(amountInput, amountError, "");
      updateScenarioSummary();
      markResultsStale();
    });
  });

  /* ---------- sharable URL state ---------- */

  function requestToParams(kind, request) {
    const params = new URLSearchParams({
      from: request.source,
      to: request.target,
      amount: request.amount,
    });
    if (kind === "route") {
      params.set("profile", request.profile);
      params.set("top_n", request.top_n);
      return params;
    }
    params.set("view", kind);
    if (kind === "compare") params.set("on", request.on_date);
    if (kind === "compare" || kind === "breakeven") params.set("profile", request.profile);
    if (RANGE_KINDS.includes(kind)) {
      params.set("min", request.min_amount);
      params.set("max", request.max_amount);
    }
    return params;
  }

  // Exactly the inputs a view's result depends on; changing anything else
  // must not flag the result as stale or split the recent-search history.
  function resultSignature(kind, request) {
    const fields = [kind, request.source, request.target];
    if (RANGE_KINDS.includes(kind)) {
      fields.push(canonicalAmount(request.min_amount), canonicalAmount(request.max_amount));
    } else {
      fields.push(canonicalAmount(request.amount));
    }
    if (kind === "route") fields.push(request.profile, String(request.top_n));
    if (kind === "compare") fields.push(request.on_date, request.profile);
    if (kind === "breakeven") fields.push(request.profile);
    return JSON.stringify(fields);
  }

  function setResultsStale(stale) {
    resultsContext.hidden = !stale;
    if (stale) {
      resultsBox.setAttribute("aria-describedby", "results-context-copy");
    } else {
      resultsBox.removeAttribute("aria-describedby");
    }
  }

  function markResultsStale() {
    if (!lastSuccessfulRun) {
      setResultsStale(false);
      return;
    }
    const stale =
      resultSignature(lastSuccessfulRun.kind, lastSuccessfulRun.request) !==
      resultSignature(lastSuccessfulRun.kind, currentRequest());
    setResultsStale(stale);
  }

  function requestFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const source = params.get("from");
    const target = params.get("to");
    if (!source || !target) return null;
    const view = params.get("view");
    const profile = params.get("profile");
    return {
      kind: ["decide", "sensitivity", "compare", "breakeven", "regime"].includes(view)
        ? view
        : "route",
      on_date: params.get("on") || "",
      source: source.toUpperCase(),
      target: target.toUpperCase(),
      amount: params.get("amount") || normalizeAmount(amountInput.value),
      profile: PROFILES.includes(profile) ? profile : "balanced",
      top_n: params.get("top_n") || "1",
      min_amount: params.get("min") || DEFAULT_SCAN.min,
      max_amount: params.get("max") || DEFAULT_SCAN.max,
    };
  }

  function applyRequestToForm(request) {
    amountInput.value = request.amount;
    if (request.on_date) onDateInput.value = request.on_date;
    rangeMinInput.value = request.min_amount || DEFAULT_SCAN.min;
    rangeMaxInput.value = request.max_amount || DEFAULT_SCAN.max;
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
    clearFieldErrors();
    updateScenarioSummary();
  }

  function syncUrl(kind, request) {
    const next = `${window.location.pathname}?${requestToParams(kind, request)}`;
    const current = `${window.location.pathname}${window.location.search}`;
    if (next !== current) history.pushState(null, "", next);
  }

  function updateDocumentTitle(kind, request) {
    document.title = kind
      ? `${VIEW_LABELS[kind]} · ${request.source} → ${request.target} — ${TITLE_BASE}`
      : TITLE_BASE;
  }

  /* ---------- recent searches ---------- */

  const RECENTS_KEY = "payment-router-recents";
  const MAX_RECENTS = 5;
  const recentsBox = $("#recents");

  function normalizeRecent(item) {
    return {
      kind: item.kind,
      source: item.source,
      target: item.target,
      amount: item.amount,
      profile: PROFILES.includes(item.profile) ? item.profile : "balanced",
      top_n: item.top_n || "1",
      on_date: item.on_date || "",
      min_amount: item.min_amount || DEFAULT_SCAN.min,
      max_amount: item.max_amount || DEFAULT_SCAN.max,
    };
  }

  function loadRecents() {
    try {
      const parsed = JSON.parse(localStorage.getItem(RECENTS_KEY) || "[]");
      return Array.isArray(parsed)
        ? parsed
            .filter((item) => item && VIEW_KINDS.includes(item.kind) && item.source && item.target)
            .map(normalizeRecent)
            .slice(0, MAX_RECENTS)
        : [];
    } catch {
      return [];
    }
  }

  function saveRecent(kind, request) {
    const entry = normalizeRecent({ kind, ...request });
    const key = resultSignature(kind, entry);
    const next = [
      entry,
      ...loadRecents().filter((item) => resultSignature(item.kind, item) !== key),
    ].slice(0, MAX_RECENTS);
    try {
      localStorage.setItem(RECENTS_KEY, JSON.stringify(next));
    } catch {
      /* storage unavailable */
    }
    renderRecents();
  }

  function recentDetail(item) {
    const profileNote = item.profile === "balanced" ? "" : ` · ${item.profile}`;
    const range = `${fmtCompact(item.min_amount)}–${fmtCompact(item.max_amount)}`;
    if (item.kind === "decide") return "profiles";
    if (item.kind === "sensitivity") return "sensitivity";
    if (item.kind === "compare") return `vs ${item.on_date || "a past date"}${profileNote}`;
    if (item.kind === "breakeven") return `break-even ${range}${profileNote}`;
    if (item.kind === "regime") return `regime map ${range}`;
    return `${item.profile}${String(item.top_n) === "1" ? "" : ` · top ${item.top_n}`}`;
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
      // The amount does not drive a scan across amounts, so it is not shown.
      const corridor = RANGE_KINDS.includes(item.kind)
        ? `${item.source}`
        : `${fmtAmountLabel(item.amount)} ${item.source}`;
      chip.append(
        document.createTextNode(corridor),
        el("span", "sep", "→"),
        document.createTextNode(item.target),
        el("span", "sep", "·"),
        document.createTextNode(recentDetail(item))
      );
      chip.addEventListener("click", () => {
        applyRequestToForm(item);
        runRequest(item.kind, buttonForKind(item.kind));
      });
      recentsBox.append(chip);
    });
    const clear = el("button", "recents-clear", "Clear");
    clear.type = "button";
    clear.setAttribute("aria-label", "Clear recent searches");
    clear.addEventListener("click", () => {
      try {
        localStorage.removeItem(RECENTS_KEY);
      } catch {
        /* storage unavailable */
      }
      renderRecents();
      routeButton.focus({ preventScroll: true });
    });
    recentsBox.append(clear);
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

  function statTile(label, valueNode, subs) {
    const tile = el("div", "stat-tile");
    tile.append(el("div", "stat-label", label));
    const value = el("div", "stat-value");
    value.append(valueNode);
    tile.append(value);
    (Array.isArray(subs) ? subs : [subs]).filter(Boolean).forEach((sub) => {
      tile.append(typeof sub === "string" ? el("div", "stat-sub", sub) : sub);
    });
    return tile;
  }

  function valueWithUnit(main, unit) {
    const fragment = document.createDocumentFragment();
    fragment.append(document.createTextNode(main));
    if (unit) fragment.append(el("span", "unit", unit));
    return fragment;
  }

  // Derived only from the amounts on screen: what one unit sent turned into
  // after every fee and spread on this route. It claims no market rate.
  function effectiveRateLine(route) {
    const sent = Number.parseFloat(route.source_amount);
    const received = Number.parseFloat(route.final_amount);
    if (!(sent > 0) || !Number.isFinite(received)) return null;
    const text =
      route.source_currency === route.target_currency
        ? `${((received / sent) * 100).toFixed(2)}% of the amount sent arrives`
        : `Effective 1 ${route.source_currency} = ${fmtRate(received / sent)} ${route.target_currency}`;
    const line = el("div", "stat-sub stat-effective", text);
    line.title = "Recipient amount divided by the amount sent, after every fee and FX spread on this route.";
    return line;
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

  function hopEvidence(hop) {
    const badges = el("div", "badges");
    const kinds = new Set(
      [hop.fee_data_source, hop.time_data_source, hop.fx_data_source].filter(Boolean)
    );
    ["VERIFIED", "INDUSTRY_AVERAGE", "ESTIMATED"].forEach((kind) => {
      if (kinds.has(kind)) badges.append(provenanceBadge(kind));
    });
    const label = (kind) => PROVENANCE_LABELS[kind] || kind || "—";
    badges.title =
      `Fee: ${label(hop.fee_data_source)} · Time: ${label(hop.time_data_source)} · ` +
      `FX: ${label(hop.fx_data_source)}`;
    return badges;
  }

  function hopTable(route) {
    const wrap = el("div", "hop-table-wrap");
    const table = el("table", "data-table hop-table");
    const head = el("thead");
    const headRow = el("tr");
    [
      ["Hop", "num"],
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
      const rateCell = el("td", "num", fmtRate(hop.fx_rate));
      rateCell.title = `1 ${hop.from} = ${fmtRate(hop.fx_rate)} ${hop.to}`;
      row.append(rateCell);
      const evidenceCell = el("td");
      evidenceCell.append(hopEvidence(hop));
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
    card.id = `route-card-${rank}`;

    const header = el("div", "panel-header");
    const title = el("div", "route-title");
    title.tabIndex = -1;
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
        [
          `from ${fmtMoney(route.source_amount, route.source_currency)} ${route.source_currency} sent`,
          effectiveRateLine(route),
        ]
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
        route.total_time_min_hours !== route.total_time_max_hours
          ? `range ${humanizeHours(route.total_time_min_hours)} – ` +
              `${humanizeHours(route.total_time_max_hours)}`
          : `${route.total_time_hours} hours`
      )
    );
    card.append(stats);

    card.append(flowDiagram(route));
    if (route.hops.length > 0) card.append(hopTable(route));
    card.append(mermaidDetails(route));
    return card;
  }

  function jumpToCard(rank) {
    const card = document.getElementById(`route-card-${rank}`);
    if (!card) return;
    card.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
    card.querySelector(".route-title")?.focus({ preventScroll: true });
    card.classList.remove("is-highlighted");
    // Restart the highlight even when the same card is chosen twice.
    void card.offsetWidth;
    card.classList.add("is-highlighted");
  }

  function candidateSummary(routes, request) {
    const best = routes[0];
    const bestAmount = Number.parseFloat(best.final_amount);
    const target = best.target_currency;
    const profile = PROFILE_LABELS[request.profile] || "Balanced";

    const panel = el("section", "panel candidate-summary");
    const header = el("div", "panel-header");
    header.append(el("h2", "", "Candidate comparison"));
    header.append(
      el("span", "hint", `Ranked by the ${profile.toLowerCase()} cost/time score · select a row for its breakdown`)
    );
    panel.append(header);

    const wrap = el("div", "hop-table-wrap");
    const table = el("table", "data-table candidate-table");
    const head = el("thead");
    const headRow = el("tr");
    [
      ["#", ""],
      ["Route", ""],
      [`Recipient gets · vs #1`, "num"],
      ["Fees (USD)", "num"],
      ["Time", "num"],
      ["Evidence", "col-evidence"],
    ].forEach(([label, className]) => headRow.append(el("th", className, label)));
    head.append(headRow);
    table.append(head);

    const body = el("tbody");
    routes.forEach((route, index) => {
      const rank = index + 1;
      const row = el("tr", "candidate-row");
      const rankCell = el("td");
      const jump = el("button", "rank-button", `#${rank}`);
      jump.type = "button";
      jump.setAttribute("aria-label", `Show the breakdown of route ${rank}`);
      jump.addEventListener("click", () => jumpToCard(rank));
      rankCell.append(jump);
      row.append(rankCell);

      const routeCell = el("td");
      const routeText = el("div", "candidate-route");
      routeText.append(pathFragment(route.path, "candidate-path"));
      routeText.append(el("span", "candidate-networks", routeNetworks(route)));
      routeCell.append(routeText);
      row.append(routeCell);

      // The difference to #1 sits under the amount so the comparison that
      // matters stays visible without scrolling a narrow table sideways.
      const amountCell = el("td", "num");
      const amountStack = el("div", "candidate-amount");
      amountStack.append(el("span", "", fmtMoney(route.final_amount, target)));
      if (index === 0) {
        amountStack.append(el("span", "candidate-muted", "top ranked"));
      } else {
        const delta = Number.parseFloat(route.final_amount) - bestAmount;
        const share = bestAmount > 0 ? (delta / bestAmount) * 100 : 0;
        const sign = delta >= 0 ? "+" : "-";
        amountStack.append(
          el(
            "span",
            `candidate-delta ${delta >= 0 ? "delta-positive" : "delta-negative"}`,
            `${fmtSigned(delta)} ${target} (${sign}${Math.abs(share).toFixed(1)}%)`
          )
        );
      }
      amountCell.append(amountStack);
      row.append(amountCell);

      row.append(el("td", "num", fmtNumber(route.total_fee_usd)));
      row.append(el("td", "num", humanizeHours(route.total_time_hours)));
      const evidenceCell = el("td", "col-evidence");
      const badges = el("div", "badges");
      route.provenance.forEach((kind) => badges.append(provenanceBadge(kind)));
      evidenceCell.append(badges);
      row.append(evidenceCell);

      // Mouse convenience; the rank button stays the keyboard path.
      row.addEventListener("click", (event) => {
        if (event.target.closest("button, a, summary")) return;
        jumpToCard(rank);
      });
      body.append(row);
    });
    table.append(body);
    wrap.append(table);
    panel.append(wrap);
    return panel;
  }

  function renderRoutes(data) {
    const nodes = [];
    const meta = quotesMetaNode(data.quotes);
    if (meta) nodes.push(meta);
    const requested = Number.parseInt(data.request?.top_n ?? 1, 10);
    if (requested > data.routes.length) {
      nodes.push(
        el(
          "p",
          "result-note",
          `Only ${data.routes.length} of the ${requested} requested candidates were found for this corridor.`
        )
      );
    }
    if (data.routes.length > 1) nodes.push(candidateSummary(data.routes, data.request || {}));
    data.routes.forEach((route, index) =>
      nodes.push(routeCard(route, index + 1, data.routes.length > 1))
    );
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

  /* ---------- sensitivity rendering ---------- */

  function parseHours(value) {
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function renderSensitivity(data) {
    // Stable slot per distinct route, in first-appearance order.
    const slots = new Map();
    data.regions.forEach((region) => {
      const key = routeKey(region.route);
      if (!slots.has(key)) {
        slots.set(key, { index: slots.size, route: region.route, key });
      }
    });
    const slotOf = (region) => slots.get(routeKey(region.route));

    const panel = el("section", "panel");
    const header = el("div", "panel-header");
    header.append(el("h2", "", "Preference sensitivity"));
    header.append(
      el("span", "hint", "Where the winning route flips as the cost/time weight moves")
    );
    panel.append(header);

    const wrap = el("div", "regime-wrap");
    const strip = el("div", "regime-strip");
    strip.setAttribute("role", "img");
    strip.setAttribute(
      "aria-label",
      "Winning route by cost weight: " +
        data.regions
          .map(
            (region) =>
              `${region.cost_weight_start.toFixed(2)} to ${region.cost_weight_end.toFixed(2)}, ` +
              `${region.route.path.join(" to ")} via ${routeNetworks(region.route)}`
          )
          .join("; ")
    );
    data.regions.forEach((region) => {
      const slot = slotOf(region);
      const segment = el("div", "regime-segment");
      const share = Math.max(
        (region.cost_weight_end - region.cost_weight_start) * 100,
        0.8
      );
      segment.style.width = `${share}%`;
      segment.style.background = slotColor(slot.index);
      segment.title =
        `${region.route.path.join(" → ")} · ${routeNetworks(region.route)} · cost weight ` +
        `${region.cost_weight_start.toFixed(2)}–${region.cost_weight_end.toFixed(2)}`;
      strip.append(segment);
    });
    strip.append(el("span", "regime-marker"));
    wrap.append(strip);

    const axis = el("div", "regime-axis");
    axis.append(el("span", "", "0 · fastest"));
    axis.append(el("span", "", "0.5 · balanced"));
    axis.append(el("span", "", "1 · cheapest"));
    wrap.append(axis);

    const legend = el("div", "regime-legend");
    slots.forEach((slot) => {
      const row = el("div", "legend-row");
      const dot = el("span", "dot");
      dot.style.background = slotColor(slot.index);
      row.append(dot);
      row.append(el("span", "legend-path", slot.route.path.join(" → ")));
      row.append(
        el(
          "span",
          "legend-meta",
          `${routeNetworks(slot.route)} · ` +
            `fee $${fmtNumber(slot.route.total_fee_usd)} · ` +
            `eta ${humanizeHours(slot.route.total_time_hours)}`
        )
      );
      legend.append(row);
    });
    wrap.append(legend);
    panel.append(wrap);

    // Timing ranges from the per-hop bounds model.
    const rangeHeader = el("div", "panel-header");
    rangeHeader.append(el("h2", "", "Timing ranges"));
    rangeHeader.append(
      el("span", "hint", "Registered per-hop bounds aggregated along each route")
    );
    panel.append(rangeHeader);
    const rows = el("div", "range-rows");
    const globalMax = Math.max(
      ...[...slots.values()].map((slot) => parseHours(slot.route.total_time_max_hours)),
      0.0001
    );
    slots.forEach((slot) => {
      const route = slot.route;
      const min = parseHours(route.total_time_min_hours);
      const max = parseHours(route.total_time_max_hours);
      const expected = parseHours(route.total_time_hours);
      const row = el("div", "range-row");
      const label = el("span", "range-label");
      label.append(document.createTextNode(route.path.join(" → ")));
      label.append(el("span", "range-networks", routeNetworks(route)));
      row.append(label);
      const track = el("div", "range-track");
      const bar = el("span", "range-bar");
      bar.style.left = `${(min / globalMax) * 100}%`;
      bar.style.width = `${Math.max(((max - min) / globalMax) * 100, 0.5)}%`;
      bar.style.background = slotColor(slot.index);
      track.append(bar);
      const tick = el("span", "range-tick");
      tick.style.left = `calc(${(expected / globalMax) * 100}% - 1px)`;
      tick.style.background = slotColor(slot.index);
      track.append(tick);
      row.append(track);
      row.append(
        el(
          "span",
          "range-value",
          min === max
            ? humanizeHours(route.total_time_hours)
            : `${humanizeHours(route.total_time_min_hours)} – ` +
              `${humanizeHours(route.total_time_max_hours)}` +
              ` · point ${humanizeHours(route.total_time_hours)}`
        )
      );
      rows.append(row);
    });
    panel.append(rows);

    if (data.caveats && data.caveats.length > 0) panel.append(caveatRows(data.caveats));

    const nodes = [panel];
    const meta = quotesMetaNode(data.quotes);
    if (meta) nodes.unshift(meta);
    if (data.balanced_region) {
      const note = el("div", "tradeoff-note");
      const body = el("div");
      body.append(el("strong", "", "Stability "));
      body.append(
        document.createTextNode(
          `The balanced (0.50) choice — ${data.balanced_region.route.path.join(" → ")} via ` +
            `${routeNetworks(data.balanced_region.route)} — holds for cost weights ` +
            `${data.balanced_region.cost_weight_start.toFixed(2)}` +
            `–${data.balanced_region.cost_weight_end.toFixed(2)}.`
        )
      );
      note.append(svg(ICONS.note), body);
      nodes.push(note);
    }
    resultsBox.replaceChildren(...nodes);
  }

  function caveatRows(caveats) {
    const rows = el("div", "caveat-rows");
    caveats.forEach((caveat) => rows.append(el("div", "", `⚠ ${caveat}`)));
    return rows;
  }

  /* ---------- comparison rendering ---------- */

  function compareSideCard(side, target, isCandidate) {
    const card = el("div", `compare-side${isCandidate ? " is-candidate" : ""}`);
    const heading = el("div", "compare-date");
    heading.append(document.createTextNode(side.rate_date || side.label));
    if (side.resolved_to_earlier_publication) {
      heading.append(el("span", "resolved", `asked ${side.requested_date}`));
    }
    card.append(heading);

    const rows = el("div", "compare-rows");
    const addRow = (label, valueNode) => {
      const row = el("div");
      row.append(el("span", "label", label));
      const value = el("span", "value");
      value.append(valueNode);
      row.append(value);
      rows.append(row);
    };

    const route = side.route;
    addRow("Mid-rate", document.createTextNode(side.mid_rate ? fmtRate(side.mid_rate) : "—"));
    addRow("Route", pathFragment(route.path, "compare-path"));
    addRow("Networks", document.createTextNode(routeNetworks(route)));
    addRow("Fee", document.createTextNode(`$${fmtNumber(route.total_fee_usd)}`));
    addRow("ETA", document.createTextNode(humanizeHours(route.total_time_hours)));
    addRow("Recipient gets", document.createTextNode(fmtMoney(route.final_amount, target)));
    card.append(rows);
    return card;
  }

  function renderComparison(data) {
    const target = data.request.target;
    const profile = PROFILE_LABELS[data.request.profile] || "Balanced";
    const panel = el("section", "panel");
    const header = el("div", "panel-header");
    header.append(el("h2", "", "Rate-date comparison"));
    header.append(
      el("span", "hint", `${profile} profile · same rails, only the ECB fixing differs`)
    );
    panel.append(header);

    const grid = el("div", "compare-grid");
    grid.append(compareSideCard(data.baseline, target, false));
    grid.append(compareSideCard(data.candidate, target, true));
    panel.append(grid);

    const deltas = el("div", "delta-rows");
    const addDelta = (label, text) => {
      const row = el("div");
      row.append(el("span", "label", label));
      row.append(el("span", "value", text));
      deltas.append(row);
    };
    addDelta(
      "Mid-rate change",
      data.deltas.mid_rate ? fmtSigned(data.deltas.mid_rate) : "—"
    );
    addDelta("Fee change", data.deltas.fee_usd ? `${fmtSigned(data.deltas.fee_usd)} USD` : "—");
    addDelta(
      "ETA change",
      data.deltas.time_hours
        ? Number.parseFloat(data.deltas.time_hours) === 0
          ? "no change"
          : `${Number.parseFloat(data.deltas.time_hours) > 0 ? "+" : "-"}` +
            humanizeHours(Math.abs(Number.parseFloat(data.deltas.time_hours)))
        : "—"
    );
    addDelta(
      "Recipient gets",
      data.deltas.receive ? `${fmtSigned(data.deltas.receive)} ${target}` : "—"
    );
    if (data.deltas.route_changed) {
      addDelta("Winning route", "differs between the two dates");
    }
    panel.append(deltas);

    if (data.caveats && data.caveats.length > 0) panel.append(caveatRows(data.caveats));

    resultsBox.replaceChildren(panel);
  }

  /* ---------- amount-axis helpers ---------- */

  // Fee structure is scale-driven, so amount axes are logarithmic.
  function logPosition(min, max) {
    const low = Math.log10(Math.max(min, 1e-9));
    const span = Math.log10(Math.max(max, min * 1.000001)) - low || 1;
    return (value) => {
      const ratio = (Math.log10(Math.max(value, 1e-9)) - low) / span;
      return Math.min(Math.max(ratio, 0), 1);
    };
  }

  function amountTicks(min, max) {
    const decades = [];
    for (let exponent = Math.ceil(Math.log10(min)); 10 ** exponent < max; exponent += 1) {
      const value = 10 ** exponent;
      // Leave room around the end labels instead of printing them twice.
      if (value / min > 1.6 && max / value > 1.6) decades.push(value);
    }
    // A very wide range keeps every n-th decade so labels never collide.
    const step = Math.ceil(decades.length / 5) || 1;
    return [min, ...decades.filter((_, index) => index % step === 0), max];
  }

  function axisTicks(ticks, toPercent) {
    const row = el("div", "axis-ticks");
    row.setAttribute("aria-hidden", "true");
    ticks.forEach((value) => {
      const percent = toPercent(value);
      const tick = el("span", "axis-tick", fmtCompact(value));
      tick.style.left = `${percent}%`;
      if (percent < 4) tick.classList.add("align-start");
      if (percent > 96) tick.classList.add("align-end");
      row.append(tick);
    });
    return row;
  }

  function placeLabel(label, percent) {
    label.classList.toggle("align-start", percent < 12);
    label.classList.toggle("align-end", percent > 88);
  }

  /* ---------- break-even rendering ---------- */

  function renderBreakeven(data) {
    const source = data.request.source;
    const min = Number.parseFloat(data.request.min_amount);
    const max = Number.parseFloat(data.request.max_amount);
    const toRatio = logPosition(min, max);
    const toPercent = (value) => toRatio(Number.parseFloat(value)) * 100;
    const profile = PROFILE_LABELS[data.request.profile] || "Balanced";

    const slots = new Map();
    data.regions.forEach((region) => {
      const key = routeKey(region.route);
      if (!slots.has(key)) slots.set(key, slots.size);
    });
    const routeText = (route) => `${route.path.join(" → ")} via ${routeNetworks(route)}`;

    const panel = el("section", "panel");
    const header = el("div", "panel-header");
    header.append(el("h2", "", "Break-even by amount"));
    header.append(
      el(
        "span",
        "hint",
        `${profile} profile · which route wins at which size · ${data.builds} quote rounds`
      )
    );
    panel.append(header);

    const wrap = el("div", "regime-wrap");
    const frame = el("div", "strip-frame");
    const strip = el("div", "regime-strip breakeven-strip");
    strip.setAttribute("role", "img");
    strip.setAttribute(
      "aria-label",
      "Winning route by amount sent: " +
        data.regions
          .map(
            (region) =>
              `${fmtMoney(region.amount_start, source)} to ${fmtMoney(region.amount_end, source)}, ` +
              routeText(region.route)
          )
          .join("; ")
    );
    data.regions.forEach((region) => {
      const start = toPercent(region.amount_start);
      const end = toPercent(region.amount_end);
      const width = Math.max(end - start, 0.8);
      const segment = el("div", "regime-segment");
      segment.style.left = `${Math.min(start, 100 - width)}%`;
      segment.style.width = `${width}%`;
      segment.style.background = slotColor(slots.get(routeKey(region.route)));
      segment.title =
        `${routeText(region.route)} · ${fmtMoney(region.amount_start, source)} – ` +
        `${fmtMoney(region.amount_end, source)}`;
      strip.append(segment);
    });
    frame.append(strip);

    const marker = el("div", "scenario-marker");
    marker.setAttribute("aria-hidden", "true");
    const markerLabel = el("span", "scenario-marker-label");
    marker.append(markerLabel);
    frame.append(marker);
    wrap.append(frame);

    wrap.append(axisTicks(amountTicks(min, max), (value) => toRatio(value) * 100));
    wrap.append(el("div", "axis-caption", `Amount sent (${source}, logarithmic scale)`));

    const legend = el("div", "regime-legend");
    const covered = data.regions.reduce(
      (total, region) => total + (toPercent(region.amount_end) - toPercent(region.amount_start)),
      0
    );
    data.regions.forEach((region) => {
      const row = el("div", "legend-row");
      const dot = el("span", "dot");
      dot.style.background = slotColor(slots.get(routeKey(region.route)));
      row.append(dot);
      row.append(el("span", "legend-path", routeNetworks(region.route)));
      row.append(
        el(
          "span",
          "legend-meta",
          `${region.route.path.join(" → ")} · ` +
            `${fmtMoney(region.amount_start, source)} – ${fmtMoney(region.amount_end, source)}`
        )
      );
      legend.append(row);
    });
    if (covered < 99.5) {
      const row = el("div", "legend-row");
      row.append(el("span", "dot no-route-swatch"));
      row.append(el("span", "legend-path", "No route observed"));
      row.append(el("span", "legend-meta", "never filled in from neighbouring samples"));
      legend.append(row);
    }
    wrap.append(legend);

    const note = el("p", "scenario-note");
    wrap.append(note);
    panel.append(wrap);

    if (data.crossovers && data.crossovers.length > 0) {
      const rows = el("div", "delta-rows");
      data.crossovers.forEach((crossover) => {
        const row = el("div");
        row.append(
          el(
            "span",
            "label",
            `${crossover.below.networks.join(", ")} → ${crossover.above.networks.join(", ")}`
          )
        );
        // Always a bracket: the exact crossing was never observed.
        row.append(
          el(
            "span",
            "value",
            `${fmtMoney(crossover.bracket_low, source)} – ` +
              `${fmtMoney(crossover.bracket_high, source)}`
          )
        );
        rows.append(row);
      });
      panel.append(rows);
    }

    if (data.caveats && data.caveats.length > 0) panel.append(caveatRows(data.caveats));

    resultsBox.replaceChildren(panel);

    scenarioMarkerUpdater = (current) => {
      const parsed = parsePositiveAmount(current.amount);
      const sameCurrency = current.source === source;
      const inRange = parsed !== null && parsed.value >= min && parsed.value <= max;
      marker.hidden = !(sameCurrency && inRange);
      if (!sameCurrency) {
        note.textContent = `This scan is in ${source}; switch the source currency back to place your amount on it.`;
        return;
      }
      if (!parsed) {
        note.textContent = "Enter an amount to see where it falls on this scan.";
        return;
      }
      const amountText = `${fmtAmountLabel(parsed.value)} ${source}`;
      if (!inRange) {
        note.textContent = `Your amount (${amountText}) is outside the scanned range; widen the scan range to include it.`;
        return;
      }
      const percent = toRatio(parsed.value) * 100;
      marker.style.left = `${percent}%`;
      markerLabel.textContent = `Your amount · ${fmtCompact(parsed.value)}`;
      placeLabel(markerLabel, percent);
      const bracket = (data.crossovers || []).find(
        (crossover) =>
          parsed.value >= Number.parseFloat(crossover.bracket_low) &&
          parsed.value <= Number.parseFloat(crossover.bracket_high)
      );
      if (bracket) {
        note.textContent =
          `Your amount (${amountText}) falls inside the ${bracket.below.networks.join(", ")} → ` +
          `${bracket.above.networks.join(", ")} crossover bracket, so either route may win there.`;
        return;
      }
      const region = data.regions.find(
        (candidate) =>
          parsed.value >= Number.parseFloat(candidate.amount_start) &&
          parsed.value <= Number.parseFloat(candidate.amount_end)
      );
      note.textContent = region
        ? `At your amount (${amountText}), ${routeText(region.route)} wins in this scan.`
        : `Your amount (${amountText}) falls in a gap this scan could not route, so it cannot say which route wins there.`;
    };
  }

  /* ---------- two-dimensional regime rendering ---------- */

  function renderRegime(data) {
    const source = data.request.source;
    const winnerById = new Map(data.winners.map((winner) => [winner.id, winner]));
    const amounts = data.amounts.map((amount) => Number.parseFloat(amount));
    const weights = data.cost_weights;
    const columnCount = amounts.length;
    const rowCount = weights.length;
    const min = amounts[0];
    const max = amounts[columnCount - 1];
    const toRatio = logPosition(min, max);
    // Columns are equal-width geometric samples; a value maps between the
    // centres of the first and last column.
    const columnPercent = (value) =>
      ((toRatio(value) * (columnCount - 1) + 0.5) / columnCount) * 100;
    const rowPercent = (weight) =>
      ((rowCount - 1 - weight * (rowCount - 1) + 0.5) / rowCount) * 100;

    const panel = el("section", "panel");
    const header = el("div", "panel-header");
    header.append(el("h2", "", "Regime map"));
    header.append(
      el(
        "span",
        "hint",
        `${data.builds} graph builds · ${data.amounts.length} amount columns · sampled cells only`
      )
    );
    panel.append(header);

    const wrap = el("div", "regime-map-wrap");
    const layout = el("div", "regime-map-layout");
    layout.append(el("div", "regime-map-y-title", "Cost weight α"));

    const yAxis = el("div", "regime-map-y-axis");
    yAxis.append(el("span", "", "1 · cost"));
    yAxis.append(el("span", "", "0.5"));
    yAxis.append(el("span", "", "0 · time"));
    layout.append(yAxis);

    const plot = el("div", "regime-map-plot");
    plot.style.gridTemplateColumns = `repeat(${columnCount}, minmax(12px, 1fr))`;
    plot.style.gridTemplateRows = `repeat(${rowCount}, minmax(3px, 1fr))`;
    plot.setAttribute("role", "img");
    plot.setAttribute(
      "aria-label",
      `Winning routes for ${data.request.source} to ${data.request.target} by amount and cost weight. ` +
        "The connected regions list below describes the same map."
    );

    for (let weightIndex = rowCount - 1; weightIndex >= 0; weightIndex -= 1) {
      amounts.forEach((amount, amountIndex) => {
        const winnerId = data.grid[weightIndex][amountIndex];
        const regionId = data.region_grid[weightIndex][amountIndex];
        const cell = el("span", `regime-map-cell${winnerId === null ? " no-route" : ""}`);
        if (winnerId !== null) {
          const winner = winnerById.get(winnerId);
          cell.style.background = slotColor(winnerId);
          cell.title =
            `${fmtMoney(amount, source)} · cost weight ` +
            `${weights[weightIndex].toFixed(2)} · ` +
            `${winner.signature.path.join(" → ")} via ` +
            `${winner.signature.networks.join(", ")} · region ${regionId + 1}`;
        } else {
          cell.title =
            `${fmtMoney(amount, source)} · cost weight ` +
            `${weights[weightIndex].toFixed(2)} · no route`;
        }
        plot.append(cell);
      });
    }

    const crossX = el("span", "regime-crosshair-x");
    const crossY = el("span", "regime-crosshair-y");
    const crossDot = el("span", "regime-crosshair-dot");
    [crossX, crossY, crossDot].forEach((node) => node.setAttribute("aria-hidden", "true"));
    plot.append(crossX, crossY, crossDot);
    layout.append(plot);

    const xAxis = el("div", "regime-map-x-axis");
    xAxis.append(axisTicks(amountTicks(min, max), columnPercent));
    xAxis.append(el("div", "axis-caption", `Amount sent (${source}, logarithmic scale)`));
    layout.append(xAxis);
    wrap.append(layout);

    const legend = el("div", "regime-legend regime-map-legend");
    data.winners.forEach((winner) => {
      const row = el("div", "legend-row");
      const swatch = el("span", "dot");
      swatch.style.background = slotColor(winner.id);
      row.append(swatch);
      row.append(el("span", "legend-path", winner.signature.path.join(" → ")));
      row.append(
        el(
          "span",
          "legend-meta",
          [...new Set(winner.signature.networks)].join(", ")
        )
      );
      legend.append(row);
    });
    wrap.append(legend);

    const note = el("p", "scenario-note");
    wrap.append(note);
    panel.append(wrap);

    const regionsHeader = el("div", "panel-header");
    regionsHeader.append(el("h2", "", "Connected regions"));
    regionsHeader.append(
      el("span", "hint", "Four-neighbour cells with the same route signature")
    );
    panel.append(regionsHeader);

    const regionRows = el("div", "regime-region-rows");
    data.regions.forEach((region) => {
      const winner = winnerById.get(region.winner_id);
      const row = el("div", "regime-region-row");
      const label = el("span", "regime-region-label");
      const swatch = el("span", "dot");
      swatch.style.background = slotColor(region.winner_id);
      label.append(
        swatch,
        document.createTextNode(
          `Region ${region.id + 1} · ${winner.signature.networks.join(", ")}`
        )
      );
      row.append(label);
      row.append(
        el(
          "span",
          "regime-region-span",
          `${fmtMoney(region.sampled_amount_start, source)}–` +
            `${fmtMoney(region.sampled_amount_end, source)} · α ` +
            `${region.sampled_cost_weight_start.toFixed(2)}–` +
            `${region.sampled_cost_weight_end.toFixed(2)} · ` +
            `${region.cell_count} cells`
        )
      );
      regionRows.append(row);
    });
    panel.append(regionRows);

    if (data.caveats && data.caveats.length > 0) panel.append(caveatRows(data.caveats));

    resultsBox.replaceChildren(panel);

    scenarioMarkerUpdater = (current) => {
      const parsed = parsePositiveAmount(current.amount);
      const weight = PROFILE_COST_WEIGHTS[current.profile] ?? 0.5;
      const sameCurrency = current.source === source;
      const inRange = parsed !== null && parsed.value >= min && parsed.value <= max;
      [crossX, crossY, crossDot].forEach((node) => {
        node.hidden = !(sameCurrency && inRange);
      });
      if (!sameCurrency) {
        note.textContent = `This map is in ${source}; switch the source currency back to place your scenario on it.`;
        return;
      }
      if (!parsed) {
        note.textContent = "Enter an amount to see where your scenario sits on this map.";
        return;
      }
      const amountText = `${fmtAmountLabel(parsed.value)} ${source}`;
      if (!inRange) {
        note.textContent = `Your amount (${amountText}) is outside the sampled range; widen the scan range to include it.`;
        return;
      }
      const x = columnPercent(parsed.value);
      const y = rowPercent(weight);
      crossX.style.left = `${x}%`;
      crossY.style.top = `${y}%`;
      crossDot.style.left = `${x}%`;
      crossDot.style.top = `${y}%`;
      // Describe the nearest observed cell rather than inventing a value
      // for the unsampled point between cells.
      let column = 0;
      amounts.forEach((amount, index) => {
        if (
          Math.abs(Math.log(amount / parsed.value)) <
          Math.abs(Math.log(amounts[column] / parsed.value))
        ) {
          column = index;
        }
      });
      const row = Math.round(weight * (rowCount - 1));
      const winnerId = data.grid[row][column];
      const regionId = data.region_grid[row][column];
      const profile = PROFILE_LABELS[current.profile] || "Balanced";
      const cellText = `${fmtMoney(amounts[column], source)}, α ${weights[row].toFixed(2)}`;
      if (winnerId === null) {
        note.textContent = `Your scenario (${amountText}, ${profile.toLowerCase()}) is nearest the sampled cell at ${cellText}, where no route was found.`;
        return;
      }
      const winner = winnerById.get(winnerId);
      note.textContent =
        `Your scenario (${amountText}, ${profile.toLowerCase()}) is nearest the sampled cell at ` +
        `${cellText}: ${winner.signature.path.join(" → ")} via ` +
        `${[...new Set(winner.signature.networks)].join(", ")} (region ${regionId + 1}).`;
    };
  }

  /* ---------- sources rendering ---------- */

  function renderSources(records) {
    const wrap = el("div", "hop-table-wrap");
    const table = el("table", "data-table registry-table");
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

  async function streamExplanation(kind, data, output, signal) {
    const response = await send("/api/explain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, data, lang: navigator.language || "en" }),
      signal,
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

  function appendAiPanel(kind, data, signal) {
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
    // Streamed narration remains opt-in so every token is not announced.
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
        const result = await streamExplanation(kind, data, output, signal);
        footer.textContent =
          `Generated by ${result.model || "Claude"} from the simulated data above — ` +
          "not live quotes, not financial advice.";
        footer.hidden = false;
        button.textContent = "Explain again";
      } catch (error) {
        // Superseded by a new result: that result already replaced this panel.
        if (isAbort(error)) return;
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
    const reducedMotion = prefersReducedMotion();
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

  // On a narrow screen the results start below the form, so a finished run
  // would otherwise change nothing the user can see.
  function revealIfOffscreen(target) {
    if (!target || target.hidden) return;
    const topbar = document.querySelector(".topbar");
    const headerBottom = topbar ? topbar.getBoundingClientRect().bottom : 0;
    const { top } = target.getBoundingClientRect();
    if (top >= headerBottom - 4 && top < window.innerHeight - 120) return;
    target.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
  }

  /* ---------- actions ---------- */

  const RENDERERS = {
    route: renderRoutes,
    decide: renderDecisions,
    sensitivity: renderSensitivity,
    compare: renderComparison,
    breakeven: renderBreakeven,
    regime: renderRegime,
  };

  function paramsFor(kind, request) {
    const corridor = { source: request.source, target: request.target };
    if (kind === "route") {
      return { ...corridor, amount: request.amount, profile: request.profile, top_n: request.top_n };
    }
    if (kind === "compare") {
      return { ...corridor, amount: request.amount, on: request.on_date, profile: request.profile };
    }
    if (kind === "breakeven") {
      return { ...corridor, min: request.min_amount, max: request.max_amount, profile: request.profile };
    }
    if (kind === "regime") {
      return { ...corridor, min: request.min_amount, max: request.max_amount };
    }
    return { ...corridor, amount: request.amount };
  }

  function snapshotView() {
    return {
      results: [...resultsBox.childNodes],
      alerts: [...alertsBox.childNodes],
      alertsHidden: alertsBox.hidden,
      warnings: [...warningsBox.childNodes],
      warningsHidden: warningsBox.hidden,
      markerUpdater: scenarioMarkerUpdater,
    };
  }

  function restoreView(snapshot) {
    resultsBox.replaceChildren(...snapshot.results);
    alertsBox.replaceChildren(...snapshot.alerts);
    alertsBox.hidden = snapshot.alertsHidden;
    warningsBox.replaceChildren(...snapshot.warnings);
    warningsBox.hidden = snapshot.warningsHidden;
    scenarioMarkerUpdater = snapshot.markerUpdater;
    if (scenarioMarkerUpdater) scenarioMarkerUpdater(currentRequest());
  }

  // Called whenever the results on screen are replaced for good.
  function retireView() {
    if (viewController) viewController.abort();
    viewController = null;
    scenarioMarkerUpdater = null;
  }

  async function runRequest(kind, activeButton, { reveal = true } = {}) {
    if (!validateRequest(kind)) return;
    const request = currentRequest();
    // A run that supersedes another inherits its snapshot: what is on screen
    // now is that run's loading state, not something to return to.
    const snapshot = activeRun && activeRun.snapshot ? activeRun.snapshot : snapshotView();
    const run = beginRun();
    run.snapshot = snapshot;
    const signal = run.signal;
    clearFeedback();
    setResultsStale(false);
    setBusy(true, activeButton);
    showSkeleton(kind);
    announceResults(
      `${VIEW_LABELS[kind]} in progress. Results will update when the calculation finishes; press Escape to cancel.`
    );
    try {
      const data = await apiGet(ENDPOINTS[kind], paramsFor(kind, request), signal);
      // Route a late abort through the same path as one during the fetch.
      if (signal.aborted) throw new DOMException("Request aborted.", "AbortError");
      retireView();
      viewController = new AbortController();
      showWarnings(data.warnings);
      RENDERERS[kind](data, request);
      if (scenarioMarkerUpdater) scenarioMarkerUpdater(currentRequest());
      appendAiPanel(kind, data, viewController.signal);
      decorateResults();
      lastSuccessfulRun = { kind, request: { ...request } };
      markResultsStale();
      saveRecent(kind, request);
      syncUrl(kind, request);
      updateDocumentTitle(kind, request);
      announceResults(completionMessage(kind, data));
      if (reveal) revealIfOffscreen(warningsBox.hidden ? resultsBox : warningsBox);
    } catch (error) {
      if (isAbort(error)) {
        // A superseded run is not a failure; the run that replaced it owns
        // the view. A cancelled one puts back what was there before it.
        if (run.cancelledByUser) {
          restoreView(snapshot);
          markResultsStale();
          announceResults("Request cancelled. The previous view is shown again.");
        }
        return;
      }
      retireView();
      lastSuccessfulRun = null;
      setResultsStale(false);
      resultsBox.replaceChildren();
      showError(error instanceof Error ? error.message : "Unexpected error.");
      if (reveal) revealIfOffscreen(alertsBox);
    } finally {
      // A superseded run must not re-enable the controls: the run that
      // replaced it is still working and owns the busy state.
      if (activeRun === run) {
        activeRun = null;
        setBusy(false, activeButton);
      }
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    runRequest("route", routeButton);
  });

  decideButton.addEventListener("click", () => runRequest("decide", decideButton));
  sensitivityButton.addEventListener("click", () =>
    runRequest("sensitivity", sensitivityButton)
  );
  regimeButton.addEventListener("click", () => runRequest("regime", regimeButton));
  breakevenButton.addEventListener("click", () => runRequest("breakeven", breakevenButton));
  compareButton.addEventListener("click", () => runRequest("compare", compareButton));
  rerunButton.addEventListener("click", () => {
    if (!lastSuccessfulRun) return;
    runRequest(lastSuccessfulRun.kind, buttonForKind(lastSuccessfulRun.kind));
  });

  // Enter in a field that only feeds one kind of analysis runs that
  // analysis, not the form's default route search.
  [rangeMinInput, rangeMaxInput].forEach((input) => {
    input.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || event.isComposing) return;
      event.preventDefault();
      const kind =
        lastSuccessfulRun && RANGE_KINDS.includes(lastSuccessfulRun.kind)
          ? lastSuccessfulRun.kind
          : "breakeven";
      runRequest(kind, buttonForKind(kind));
    });
  });
  onDateInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.isComposing) return;
    event.preventDefault();
    runRequest("compare", compareButton);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && activeRun && !event.defaultPrevented) cancelActiveRun();
  });

  const initialEmptyState = resultsBox.firstElementChild;

  window.addEventListener("popstate", () => {
    const request = requestFromUrl();
    if (request) {
      applyRequestToForm(request);
      runRequest(request.kind, buttonForKind(request.kind), { reveal: false });
    } else {
      if (activeRun) {
        activeRun.abort();
        activeRun = null;
        setBusy(false, routeButton);
      }
      clearFeedback();
      retireView();
      lastSuccessfulRun = null;
      setResultsStale(false);
      resultsBox.replaceChildren(initialEmptyState);
      updateDocumentTitle(null);
      announceResults("Results cleared. Choose a corridor to run another simulation.");
    }
  });

  swapButton.addEventListener("click", () => {
    const source = sourceSelect.value;
    sourceSelect.value = targetSelect.value;
    targetSelect.value = source;
    updateScenarioSummary();
    markResultsStale();
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
    updateScenarioSummary();
  }

  async function boot() {
    renderRecents();
    // The backend rejects future dates; do not offer them in the picker.
    onDateInput.max = new Date().toISOString().slice(0, 10);
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
      if (meta.fx) {
        const fxChip = $("#fx-chip");
        fxChip.textContent =
          meta.fx.mode === "live"
            ? `FX · ECB ${meta.fx.rate_date}${meta.fx.stale ? " (cached)" : ""}`
            : `FX · frozen table${meta.fx.fallback ? " (live unavailable)" : ""}`;
        fxChip.title = meta.fx.detail || "";
        if (meta.fx.fallback) fxChip.classList.add("chip-warning");
        fxChip.hidden = false;
      }
      if (meta.disclaimer) {
        $("#disclaimer-text").textContent = meta.disclaimer;
        $("#disclaimer").hidden = false;
      }
      const urlRequest = requestFromUrl();
      if (urlRequest) {
        applyRequestToForm(urlRequest);
        runRequest(urlRequest.kind, buttonForKind(urlRequest.kind), { reveal: false });
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
