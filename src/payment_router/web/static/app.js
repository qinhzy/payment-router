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
  const quickAmountsBox = $("#quick-amounts");
  const alertsBox = $("#alerts");
  const warningsBox = $("#warnings");
  const resultsBox = $("#results");
  const resultsStatus = $("#results-status");
  const resultsContext = $("#results-context");
  const rerunButton = $("#rerun-button");
  const sourcesBox = $("#sources");
  const themeToggle = $("#theme-toggle");
  const langToggle = $("#lang-toggle");
  const scenarioSummary = $("#scenario-summary");
  const actionButtons = [
    routeButton,
    decideButton,
    sensitivityButton,
    regimeButton,
    compareButton,
    breakevenButton,
  ];

  const DEFAULT_SCAN = { min: "10", max: "100000" };
  const DEFAULT_QUICK_AMOUNTS = ["250", "500", "1000", "2500", "5000"];
  const PROFILES = ["cheapest", "fastest", "balanced"];
  // Cost weight of each profile, matching service.preference_for_profile.
  const PROFILE_COST_WEIGHTS = { cheapest: 1, fastest: 0, balanced: 0.5 };
  const VIEW_KINDS = ["route", "decide", "sensitivity", "compare", "breakeven", "regime"];
  const RANGE_KINDS = ["breakeven", "regime"];
  const ENDPOINTS = {
    route: "/api/route",
    decide: "/api/decide",
    sensitivity: "/api/sensitivity",
    compare: "/api/compare",
    breakeven: "/api/breakeven",
    regime: "/api/regime",
  };
  // Literal catalog keys, so a test can check every key the console uses.
  const VIEW_KEYS = {
    route: "view.route",
    decide: "view.decide",
    sensitivity: "view.sensitivity",
    compare: "view.compare",
    breakeven: "view.breakeven",
    regime: "view.regime",
  };
  const PROFILE_KEYS = {
    cheapest: "profile.cheapest",
    fastest: "profile.fastest",
    balanced: "profile.balanced",
  };
  const PROFILE_INLINE_KEYS = {
    cheapest: "profileInline.cheapest",
    fastest: "profileInline.fastest",
    balanced: "profileInline.balanced",
  };
  const PROVENANCE_KEYS = {
    VERIFIED: "provenance.VERIFIED",
    INDUSTRY_AVERAGE: "provenance.INDUSTRY_AVERAGE",
    ESTIMATED: "provenance.ESTIMATED",
  };
  const ANNOUNCE_KEYS = {
    route: "announce.route",
    decide: "announce.decide",
    sensitivity: "announce.sensitivity",
    regime: "announce.regime",
    breakeven: "announce.breakeven",
  };

  const CURRENCY_SYMBOLS = {
    USD: "$",
    EUR: "€",
    GBP: "£",
    CNY: "¥",
    HKD: "HK$",
    SGD: "S$",
  };

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
  let metaInfo = null;
  let sourceRecords = null;
  let quickAmountsByCurrency = {};
  let resultsAnnouncementFrame = null;
  let lastSuccessfulRun = null;
  // What the results area shows, kept so a language switch can redraw it
  // from the same data instead of asking the server again.
  let currentView = { type: "empty" };
  // Aborts work owned by the results on screen (an AI stream) once they are
  // replaced. It is separate from the request run, which ends on render.
  let viewController = null;
  // Set by the amount-axis views so the "your scenario" marker can follow
  // the form without re-running the scan: the marker is purely client-side.
  let scenarioMarkerUpdater = null;
  // Messages are kept as functions so a language switch can re-render them.
  let alertMessage = null;
  let shownWarnings = null;

  const networkSlots = new Map();

  /* ---------- language ---------- */

  const LANG_KEY = "payment-router-lang";
  const LANGUAGES = ["en", "zh-CN"];
  const NUMBER_LOCALES = { en: "en-US", "zh-CN": "zh-CN" };
  const catalogs = {};
  const catalogRequests = {};
  let lang = preferredLanguage();

  function preferredLanguage() {
    try {
      const stored = localStorage.getItem(LANG_KEY);
      if (LANGUAGES.includes(stored)) return stored;
    } catch {
      /* storage can be unavailable in private or hardened browser contexts */
    }
    const tags =
      navigator.languages && navigator.languages.length
        ? navigator.languages
        : [navigator.language || "en"];
    const first = tags.find((tag) => /^(en|zh)\b/i.test(tag));
    return first && /^zh/i.test(first) ? "zh-CN" : "en";
  }

  function numberLocale() {
    return NUMBER_LOCALES[lang] || "en-US";
  }

  function lookup(key) {
    const active = catalogs[lang];
    if (active && Object.hasOwn(active, key)) return active[key];
    const english = catalogs.en;
    if (english && Object.hasOwn(english, key)) return english[key];
    return undefined;
  }

  function fill(template, params) {
    return template.replace(/\{(\w+)\}/g, (match, name) =>
      params && Object.hasOwn(params, name) ? String(params[name]) : match
    );
  }

  function t(key, params) {
    const template = lookup(key);
    return template === undefined ? key : fill(template, params);
  }

  function tn(key, count, params) {
    return t(`${key}.${count === 1 ? "one" : "other"}`, { count, ...params });
  }

  // For sentences that embed styled fragments: the template decides the
  // word order and the caller supplies the nodes.
  function tNodes(key, values) {
    const template = lookup(key) ?? key;
    return template
      .split(/(\{\w+\})/)
      .filter(Boolean)
      .map((part) => {
        const name = part.match(/^\{(\w+)\}$/)?.[1];
        if (name && Object.hasOwn(values, name)) {
          const value = values[name];
          return value instanceof Node ? value : document.createTextNode(String(value));
        }
        return document.createTextNode(part);
      });
  }

  // A backend statement in the active language when a translation exists
  // for its code; otherwise the English sentence the backend sent. The code
  // decides which statement applies, so a translation cannot drift from it.
  function localizedMessage(namespace, code, params, english) {
    if (lang !== "en" && code) {
      const template = lookup(`${namespace}.${code}`);
      const values = params || {};
      // A server of another version may not send every figure the template
      // quotes; its own English sentence is then the only complete one.
      const complete =
        template !== undefined &&
        [...template.matchAll(/\{(\w+)\}/g)].every(([, name]) => Object.hasOwn(values, name));
      if (complete) return fill(template, values);
    }
    return english;
  }

  function localizedCaveats(data) {
    const codes = data.caveat_codes || [];
    return (data.caveats || []).map((caveat, index) =>
      localizedMessage("caveat", codes[index]?.code, codes[index]?.params, caveat)
    );
  }

  function applyTranslations(root = document) {
    root.querySelectorAll("[data-i18n]").forEach((node) => {
      // A busy button shows its progress label until the request settles,
      // and without a catalog entry the markup's English text stands.
      if (node.dataset.busy === "true" || lookup(node.dataset.i18n) === undefined) return;
      let params;
      if (node.dataset.i18nParams) {
        try {
          params = JSON.parse(node.dataset.i18nParams);
        } catch {
          params = undefined;
        }
      }
      node.textContent = t(node.dataset.i18n, params);
    });
    root.querySelectorAll("[data-i18n-attr]").forEach((node) => {
      node.dataset.i18nAttr.split(";").forEach((entry) => {
        const [attribute, key] = entry.split("=").map((part) => part.trim());
        if (attribute && key && lookup(key) !== undefined) node.setAttribute(attribute, t(key));
      });
    });
  }

  function loadCatalog(code) {
    catalogRequests[code] ??= fetch(`./i18n/${code}.json`, {
      headers: { Accept: "application/json" },
    })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((catalog) => {
        catalogs[code] = catalog;
        return catalog;
      })
      .catch((error) => {
        delete catalogRequests[code]; // let a later switch try again
        throw error;
      });
    return catalogRequests[code];
  }

  function syncLanguageControl() {
    // The button names the other language in that language.
    langToggle.lang = lang === "en" ? "zh-CN" : "en";
  }

  async function setLanguage(next) {
    try {
      await Promise.all([loadCatalog("en"), loadCatalog(next)]);
    } catch {
      showError(() => t("request.catalogFailed"));
      return;
    }
    lang = next;
    try {
      localStorage.setItem(LANG_KEY, next);
    } catch {
      /* the selected language still applies for this page */
    }
    refreshLanguage();
  }

  function refreshLanguage() {
    document.documentElement.lang = lang;
    applyTranslations();
    syncThemeControl();
    syncLanguageControl();
    renderQuickAmounts();
    updateScenarioSummary();
    renderRecents();
    renderMeta();
    if (sourceRecords) renderSources(sourceRecords);
    rerenderView();
    updateDocumentTitle();
  }

  langToggle.addEventListener("click", () => setLanguage(lang === "en" ? "zh-CN" : "en"));

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
    return parsed.toLocaleString(numberLocale(), {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function fmtAmountLabel(value) {
    const parsed = Number.parseFloat(value);
    if (!Number.isFinite(parsed)) return String(value);
    return parsed.toLocaleString(numberLocale(), { maximumFractionDigits: 2 });
  }

  function fmtCompact(value) {
    const parsed = Number.parseFloat(value);
    if (!Number.isFinite(parsed)) return String(value);
    return parsed.toLocaleString(numberLocale(), {
      notation: "compact",
      maximumFractionDigits: 1,
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
    if (!Number.isFinite(hours)) return t("time.hours", { n: value });
    const seconds = hours * 3600;
    if (seconds < 90) return t("time.seconds", { n: Math.round(seconds) });
    if (hours < 1) return t("time.minutes", { n: Math.round(hours * 60) });
    if (hours < 10) return t("time.hours", { n: Math.round(hours * 10) / 10 });
    if (hours < 72) return t("time.hours", { n: Math.round(hours) });
    return t("time.days", { n: Math.round((hours / 24) * 10) / 10 });
  }

  function profileLabel(profile) {
    return t(PROFILE_KEYS[profile] || PROFILE_KEYS.balanced);
  }

  function profileInline(profile) {
    return t(PROFILE_INLINE_KEYS[profile] || PROFILE_INLINE_KEYS.balanced);
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

  function provenanceLabel(kind) {
    return PROVENANCE_KEYS[kind] ? t(PROVENANCE_KEYS[kind]) : String(kind || "—");
  }

  function provenanceBadge(kind) {
    return el("span", `badge badge-${String(kind).toLowerCase()}`, provenanceLabel(kind));
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
    themeToggle.setAttribute("aria-label", isDark ? t("theme.toLight") : t("theme.toDark"));
  }

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
    alertMessage = null;
    shownWarnings = null;
    alertsBox.hidden = true;
    alertsBox.replaceChildren();
    warningsBox.hidden = true;
    warningsBox.replaceChildren();
  }

  function renderAlert() {
    if (!alertMessage) return;
    const alert = el("div", "alert alert-error");
    alert.setAttribute("role", "alert");
    alert.append(svg(ICONS.error), el("span", "", alertMessage()));
    alertsBox.replaceChildren(alert);
    alertsBox.hidden = false;
  }

  function showError(message) {
    alertMessage = typeof message === "function" ? message : () => message;
    renderAlert();
  }

  function formatPair(pair) {
    return pair === "*->*" ? t("warnings.allCorridors") : String(pair).replace("->", " → ");
  }

  // A provider that is down fails every corridor with the same reason; one
  // line per network and reason keeps thirty identical rows from burying
  // the one failure that differs.
  function groupWarnings(warnings) {
    const groups = new Map();
    warnings.forEach((warning) => {
      const reason = localizedMessage("warning", warning.code, {}, warning.reason);
      const key = `${warning.network}\u0000${reason}`;
      if (!groups.has(key)) {
        groups.set(key, { network: warning.network, reason, pairs: [] });
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
      details.append(el("summary", "", t("warnings.corridors", { n: group.pairs.length })));
      details.append(el("p", "", group.pairs.join(", ")));
      item.append(details);
    }
    return item;
  }

  function showWarnings(warnings) {
    if (!warnings || warnings.length === 0) return;
    shownWarnings = warnings;
    const groups = groupWarnings(warnings);
    const alert = el("div", "alert alert-warning");
    alert.setAttribute("role", "status");
    const body = el("div");
    body.append(el("strong", "", t("warnings.title")));
    body.append(el("p", "alert-note", t("warnings.note")));
    const visibleCount = 4;
    const list = el("ul");
    groups.slice(0, visibleCount).forEach((group) => list.append(warningItem(group)));
    body.append(list);
    if (groups.length > visibleCount) {
      const rest = groups.slice(visibleCount);
      const details = el("details");
      details.append(el("summary", "", t("warnings.more", { n: rest.length })));
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
    label.append(
      svg('<span class="spinner"></span>'),
      document.createTextNode(t("busy.running", { view: t(VIEW_KEYS[kind]) }))
    );
    const cancel = el("button", "button button-ghost button-small", t("busy.cancel"));
    cancel.type = "button";
    cancel.title = t("busy.cancelTitle");
    cancel.addEventListener("click", cancelActiveRun);
    head.append(label, cancel);
    card.append(head);
    if (RANGE_KINDS.includes(kind)) card.append(el("p", "skeleton-note", t("busy.scanNote")));
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
    if (kind === "compare") return t("announce.compare");
    const counts = {
      route: data.routes?.length,
      decide: data.decisions?.length,
      sensitivity: data.regions?.length,
      regime: data.regions?.length,
      breakeven: data.regions?.length,
    };
    return tn(ANNOUNCE_KEYS[kind], counts[kind] ?? 0);
  }

  function buttonForKind(kind) {
    if (kind === "compare") return compareButton;
    if (kind === "breakeven") return breakevenButton;
    if (kind === "regime") return regimeButton;
    if (kind === "decide") return decideButton;
    if (kind === "sensitivity") return sensitivityButton;
    return routeButton;
  }

  function showBusyLabel(button) {
    button.dataset.busy = "true";
    button.replaceChildren(
      svg('<span class="spinner"></span>'),
      document.createTextNode(` ${t("form.working")}`)
    );
  }

  function restoreButtonLabels() {
    actionButtons.forEach((button) => {
      if (button.dataset.busy === "true") {
        delete button.dataset.busy;
        button.textContent = t(button.dataset.i18n);
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
    form.querySelectorAll("input, select, button").forEach((control) => {
      control.disabled = busy;
    });
    form.setAttribute("aria-busy", String(busy));
    resultsBox.setAttribute("aria-busy", String(busy));
    // A superseding run may use a different button; only one spinner shows.
    restoreButtonLabels();
    if (busy) {
      showBusyLabel(activeButton);
    } else {
      restoreFocus(activeButton);
    }
  }

  /* ---------- fetch ---------- */

  // An error message that can be re-rendered in another language: either a
  // console string (key) or a backend sentence with its code and params.
  class ApiRequestError extends Error {
    constructor({ detail = "", code = null, params = {}, key = null, keyParams = {} }) {
      super(detail || key || "request failed");
      this.detail = detail;
      this.code = code;
      this.params = params;
      this.key = key;
      this.keyParams = keyParams;
    }

    localized() {
      if (this.key) return t(this.key, this.keyParams);
      return localizedMessage("error", this.code, this.params, this.detail);
    }
  }

  function messageOf(error) {
    if (error instanceof ApiRequestError) return error.localized();
    return error instanceof Error && error.message ? error.message : t("request.unexpected");
  }

  async function responseError(response) {
    try {
      const payload = await response.json();
      const detail = payload ? payload.detail : undefined;
      if (typeof detail === "string") {
        return new ApiRequestError({ detail, code: payload.code || null, params: payload.params || {} });
      }
      // FastAPI validation errors arrive as a list of {loc, msg}.
      if (Array.isArray(detail) && detail.length > 0) {
        const details = detail
          .map((issue) => {
            const field = Array.isArray(issue.loc)
              ? issue.loc.filter((part) => part !== "query" && part !== "body").join(".")
              : "";
            return field ? `${field}: ${issue.msg}` : String(issue.msg);
          })
          .join("; ");
        return new ApiRequestError({ key: "request.invalid", keyParams: { details } });
      }
    } catch {
      /* non-JSON error body */
    }
    const status = response.status;
    return new ApiRequestError({
      key: status >= 500 ? "request.serverFailed" : "request.failed",
      keyParams: { status },
    });
  }

  async function send(path, init) {
    try {
      return await fetch(path, init);
    } catch (error) {
      if (isAbort(error)) throw error;
      throw new ApiRequestError({ key: "request.unreachable" });
    }
  }

  async function apiGet(path, params, signal) {
    const query = new URLSearchParams(params);
    const response = await send(`${path}?${query}`, {
      headers: { Accept: "application/json" },
      signal,
    });
    if (!response.ok) throw await responseError(response);
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
    const amount = parsed ? fmtAmountLabel(parsed.value) : amountInput.value.trim() || "—";
    const candidateCount = form.elements.top_n.value;
    scenarioSummary.textContent = t("scenario.summary", {
      amount,
      source: sourceSelect.value || "—",
      target: targetSelect.value || "—",
      profile: profileLabel(form.elements.profile.value),
      candidates:
        candidateCount === "1" ? t("scenario.best") : t("scenario.topN", { n: candidateCount }),
    });
    rangeCurrency.textContent = sourceSelect.value || "";

    quickAmountsBox.querySelectorAll("[data-quick-amount]").forEach((button) => {
      const active = parsed !== null && parsed.value === Number(button.dataset.quickAmount);
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });

    if (scenarioMarkerUpdater) scenarioMarkerUpdater(currentRequest());
  }

  /* ---------- quick amounts ---------- */

  // Round figures of a similar size in the source currency, computed by the
  // server from the active rate table: 250 USD, but 2,000 CNY.
  function renderQuickAmounts() {
    const ladder = quickAmountsByCurrency[sourceSelect.value] || DEFAULT_QUICK_AMOUNTS;
    const label = el("span", "", t("form.quick"));
    label.dataset.i18n = "form.quick";
    const buttons = ladder.map((value) => {
      const button = el("button", "", fmtAmountLabel(value));
      button.type = "button";
      button.dataset.quickAmount = value;
      button.setAttribute("aria-pressed", "false");
      button.disabled = form.getAttribute("aria-busy") === "true";
      return button;
    });
    quickAmountsBox.replaceChildren(label, ...buttons);
  }

  quickAmountsBox.addEventListener("click", (event) => {
    const button = event.target.closest("[data-quick-amount]");
    if (!button) return;
    amountInput.value = button.dataset.quickAmount;
    setFieldError(amountInput, amountError, null);
    updateScenarioSummary();
    markResultsStale();
  });

  /* ---------- validation ---------- */

  function setFieldError(input, errorNode, key, params) {
    if (key) {
      input.setAttribute("aria-invalid", "true");
      errorNode.dataset.i18n = key;
      if (params) errorNode.dataset.i18nParams = JSON.stringify(params);
      else delete errorNode.dataset.i18nParams;
      errorNode.textContent = t(key, params);
      errorNode.hidden = false;
    } else {
      input.removeAttribute("aria-invalid");
      delete errorNode.dataset.i18n;
      delete errorNode.dataset.i18nParams;
      errorNode.textContent = "";
      errorNode.hidden = true;
    }
  }

  function clearRangeError() {
    rangeMinInput.removeAttribute("aria-invalid");
    setFieldError(rangeMaxInput, rangeError, null);
  }

  function clearFieldErrors() {
    setFieldError(amountInput, amountError, null);
    setFieldError(onDateInput, dateError, null);
    clearRangeError();
  }

  function validateAmount() {
    if (parsePositiveAmount(amountInput.value)) return true;
    setFieldError(amountInput, amountError, "validate.amount");
    amountInput.focus();
    return false;
  }

  function validateRange() {
    const low = parsePositiveAmount(rangeMinInput.value);
    const high = parsePositiveAmount(rangeMaxInput.value);
    let culprit = null;
    let key = null;
    if (!low) {
      culprit = rangeMinInput;
      key = "validate.rangeMin";
    } else if (!high) {
      culprit = rangeMaxInput;
      key = "validate.rangeMax";
    } else if (low.value >= high.value) {
      culprit = rangeMaxInput;
      key = "validate.rangeOrder";
    }
    if (!culprit) return true;
    setFieldError(culprit, rangeError, key);
    culprit.focus();
    return false;
  }

  function validateDate() {
    const value = onDateInput.value;
    let key = null;
    let params;
    if (!value) {
      key = "validate.dateMissing";
    } else if (onDateInput.min && value < onDateInput.min) {
      key = "validate.dateTooEarly";
      params = { date: onDateInput.min };
    } else if (onDateInput.max && value > onDateInput.max) {
      key = "validate.dateFuture";
    }
    if (!key) return true;
    setFieldError(onDateInput, dateError, key, params);
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
    if (event.target === amountInput) setFieldError(amountInput, amountError, null);
    if (event.target === rangeMinInput || event.target === rangeMaxInput) clearRangeError();
    if (event.target === onDateInput) setFieldError(onDateInput, dateError, null);
    if (event.target === sourceSelect) renderQuickAmounts();
    updateScenarioSummary();
    markResultsStale();
  });
  form.addEventListener("change", (event) => {
    if (event.target === sourceSelect) renderQuickAmounts();
    updateScenarioSummary();
    markResultsStale();
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
    renderQuickAmounts();
    updateScenarioSummary();
  }

  function syncUrl(kind, request) {
    const next = `${window.location.pathname}?${requestToParams(kind, request)}`;
    const current = `${window.location.pathname}${window.location.search}`;
    if (next !== current) history.pushState(null, "", next);
  }

  function updateDocumentTitle() {
    const base = t("meta.title");
    document.title =
      currentView.type === "results"
        ? `${t(VIEW_KEYS[currentView.kind])} · ${currentView.request.source} → ` +
          `${currentView.request.target} — ${base}`
        : base;
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
    const profileNote = item.profile === "balanced" ? "" : ` · ${profileLabel(item.profile)}`;
    const range = `${fmtCompact(item.min_amount)}–${fmtCompact(item.max_amount)}`;
    if (item.kind === "decide") return t("recents.profiles");
    if (item.kind === "sensitivity") return t("recents.sensitivity");
    if (item.kind === "compare") {
      return t("recents.compare", { date: item.on_date || t("recents.comparePast") }) + profileNote;
    }
    if (item.kind === "breakeven") return t("recents.breakeven", { range }) + profileNote;
    if (item.kind === "regime") return t("recents.regime", { range });
    const topNote = String(item.top_n) === "1" ? "" : ` · ${t("recents.topN", { n: item.top_n })}`;
    return profileLabel(item.profile) + topNote;
  }

  function renderRecents() {
    const recents = loadRecents();
    if (recents.length === 0) {
      recentsBox.hidden = true;
      recentsBox.replaceChildren();
      return;
    }
    recentsBox.replaceChildren(el("span", "recents-label", t("recents.label")));
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
    const clear = el("button", "recents-clear", t("recents.clear"));
    clear.type = "button";
    clear.setAttribute("aria-label", t("recents.clearLabel"));
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
    const stamp = Number.isNaN(time.getTime())
      ? quotes.quoted_at
      : time.toLocaleTimeString(numberLocale());
    wrap.append(
      document.createTextNode(
        t(quotes.from_cache ? "quotes.cached" : "quotes.fetched", { time: stamp })
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
        ? t("route.arrivesShare", { share: ((received / sent) * 100).toFixed(2) })
        : t("route.effective", {
            source: route.source_currency,
            rate: fmtRate(received / sent),
            target: route.target_currency,
          });
    const line = el("div", "stat-sub stat-effective", text);
    line.title = t("route.effectiveTitle");
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
            t("route.feeTime", {
              fee: `$${fmtNumber(hop.fee_usd)}`,
              time: humanizeHours(hop.time_hours),
            })
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
    badges.title = t("hop.evidenceTitle", {
      fee: provenanceLabel(hop.fee_data_source),
      time: provenanceLabel(hop.time_data_source),
      fx: provenanceLabel(hop.fx_data_source),
    });
    return badges;
  }

  function hopTable(route) {
    const wrap = el("div", "hop-table-wrap");
    const table = el("table", "data-table hop-table");
    const head = el("thead");
    const headRow = el("tr");
    [
      ["hop.hop", "num"],
      ["hop.network", ""],
      ["hop.pair", ""],
      ["hop.fee", "num"],
      ["hop.time", "num"],
      ["hop.rate", "num"],
      ["hop.evidence", ""],
    ].forEach(([key, className]) => {
      headRow.append(el("th", className, t(key)));
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
    details.append(el("summary", "", t("mermaid.summary")));
    const body = el("div", "mermaid-body");
    const pre = el("pre");
    pre.append(el("code", "", route.mermaid));
    const copy = el("button", "copy-button", t("mermaid.copy"));
    copy.type = "button";
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(route.mermaid);
        copy.textContent = t("mermaid.copied");
        setTimeout(() => {
          copy.textContent = t("mermaid.copy");
        }, 1400);
      } catch {
        copy.textContent = t("mermaid.selectCopy");
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
        t("route.recipientGets"),
        valueWithUnit(fmtMoney(route.final_amount, route.target_currency), route.target_currency),
        [
          t("route.fromSent", {
            amount: fmtMoney(route.source_amount, route.source_currency),
            currency: route.source_currency,
          }),
          effectiveRateLine(route),
        ]
      )
    );
    stats.append(
      statTile(
        t("route.totalFees"),
        valueWithUnit(`$${fmtNumber(route.total_fee_usd)}`, "USD"),
        tn("route.hops", route.hops.length)
      )
    );
    stats.append(
      statTile(
        t("route.estimatedTime"),
        valueWithUnit(humanizeHours(route.total_time_hours)),
        route.total_time_min_hours !== route.total_time_max_hours
          ? t("route.timeRange", {
              min: humanizeHours(route.total_time_min_hours),
              max: humanizeHours(route.total_time_max_hours),
            })
          : t("route.timeHours", { hours: route.total_time_hours })
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

    const panel = el("section", "panel candidate-summary");
    const header = el("div", "panel-header");
    header.append(el("h2", "", t("candidates.title")));
    header.append(
      el("span", "hint", t("candidates.hint", { profile: profileInline(request.profile) }))
    );
    panel.append(header);

    const wrap = el("div", "hop-table-wrap");
    const table = el("table", "data-table candidate-table");
    const head = el("thead");
    const headRow = el("tr");
    headRow.append(el("th", "", "#"));
    [
      ["candidates.route", ""],
      ["candidates.recipient", "num"],
      ["candidates.fees", "num"],
      ["candidates.time", "num"],
      ["candidates.evidence", "col-evidence"],
    ].forEach(([key, className]) => headRow.append(el("th", className, t(key))));
    head.append(headRow);
    table.append(head);

    const body = el("tbody");
    routes.forEach((route, index) => {
      const rank = index + 1;
      const row = el("tr", "candidate-row");
      const rankCell = el("td");
      const jump = el("button", "rank-button", `#${rank}`);
      jump.type = "button";
      jump.setAttribute("aria-label", t("candidates.jump", { rank }));
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
        amountStack.append(el("span", "candidate-muted", t("candidates.topRanked")));
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
          t("candidates.onlyFound", { found: data.routes.length, requested })
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
    profile.append(document.createTextNode(profileLabel(decision.profile)));
    head.append(profile);
    if (recommended) head.append(el("span", "badge badge-recommended", t("decide.recommended")));
    card.append(head);

    const body = el("div", "decision-body");
    const receive = el("div", "decision-receive");
    receive.append(
      valueWithUnit(fmtMoney(route.final_amount, route.target_currency), route.target_currency)
    );
    body.append(receive);

    const metrics = el("div", "decision-metrics");
    metrics.append(el("span", "", t("decide.fee", { fee: `$${fmtNumber(route.total_fee_usd)}` })));
    metrics.append(el("span", "", t("decide.eta", { time: humanizeHours(route.total_time_hours) })));
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
        title: t("decide.totalFee"),
        value: (decision) => Number.parseFloat(decision.route.total_fee_usd),
        label: (decision) => `$${fmtNumber(decision.route.total_fee_usd)}`,
      },
      {
        title: t("decide.estimatedTime"),
        value: (decision) => Number.parseFloat(decision.route.total_time_hours),
        label: (decision) => humanizeHours(decision.route.total_time_hours),
      },
    ];
    const panel = el("section", "panel");
    const header = el("div", "panel-header");
    header.append(el("h2", "", t("decide.chartTitle")));
    header.append(el("span", "hint", t("decide.chartHint")));
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
        row.append(el("span", "bar-label", profileLabel(decision.profile)));
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
      body.append(el("strong", "", t("decide.noteTitle")));
      if (data.tradeoff.same_route_for_all_profiles) {
        body.append(document.createTextNode(t("decide.sameRoute")));
      } else {
        const target =
          data.decisions.length > 0 ? data.decisions[0].route.target_currency : "";
        const deltaSpan = (value, text, lowerIsBetter) => {
          const good = lowerIsBetter
            ? Number.parseFloat(value) <= 0
            : Number.parseFloat(value) >= 0;
          return el("span", good ? "delta-positive" : "delta-negative", text);
        };
        const { balanced_fee_delta_usd: fee, balanced_receive_delta: receive } = data.tradeoff;
        const saved = data.tradeoff.balanced_hours_saved_vs_cheapest;
        body.append(
          ...tNodes("decide.tradeoff", {
            fee: deltaSpan(fee, `${fmtSigned(fee)} USD`, true),
            time: deltaSpan(saved, t("time.hours", { n: fmtSigned(saved) }), false),
            receive: deltaSpan(receive, `${fmtSigned(receive)} ${target}`, false),
          })
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

  function caveatRows(data) {
    const rows = el("div", "caveat-rows");
    localizedCaveats(data).forEach((caveat) => rows.append(el("div", "", `⚠ ${caveat}`)));
    return rows;
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
    header.append(el("h2", "", t("sensitivity.title")));
    header.append(el("span", "hint", t("sensitivity.hint")));
    panel.append(header);

    const wrap = el("div", "regime-wrap");
    const strip = el("div", "regime-strip");
    strip.setAttribute("role", "img");
    strip.setAttribute(
      "aria-label",
      t("sensitivity.stripLabel", {
        regions: data.regions
          .map((region) =>
            t("sensitivity.regionLabel", {
              start: region.cost_weight_start.toFixed(2),
              end: region.cost_weight_end.toFixed(2),
              path: region.route.path.join(" → "),
              networks: routeNetworks(region.route),
            })
          )
          .join("; "),
      })
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
      segment.title = t("sensitivity.segmentTitle", {
        path: region.route.path.join(" → "),
        networks: routeNetworks(region.route),
        start: region.cost_weight_start.toFixed(2),
        end: region.cost_weight_end.toFixed(2),
      });
      strip.append(segment);
    });
    strip.append(el("span", "regime-marker"));
    wrap.append(strip);

    const axis = el("div", "regime-axis");
    axis.append(el("span", "", t("sensitivity.axisFastest")));
    axis.append(el("span", "", t("sensitivity.axisBalanced")));
    axis.append(el("span", "", t("sensitivity.axisCheapest")));
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
          t("sensitivity.legendMeta", {
            networks: routeNetworks(slot.route),
            fee: `$${fmtNumber(slot.route.total_fee_usd)}`,
            time: humanizeHours(slot.route.total_time_hours),
          })
        )
      );
      legend.append(row);
    });
    wrap.append(legend);
    panel.append(wrap);

    // Timing ranges from the per-hop bounds model.
    const rangeHeader = el("div", "panel-header");
    rangeHeader.append(el("h2", "", t("sensitivity.timingTitle")));
    rangeHeader.append(el("span", "hint", t("sensitivity.timingHint")));
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
            : t("sensitivity.rangeValue", {
                min: humanizeHours(route.total_time_min_hours),
                max: humanizeHours(route.total_time_max_hours),
                point: humanizeHours(route.total_time_hours),
              })
        )
      );
      rows.append(row);
    });
    panel.append(rows);

    if (data.caveats && data.caveats.length > 0) panel.append(caveatRows(data));

    const nodes = [panel];
    const meta = quotesMetaNode(data.quotes);
    if (meta) nodes.unshift(meta);
    if (data.balanced_region) {
      const note = el("div", "tradeoff-note");
      const body = el("div");
      body.append(el("strong", "", t("sensitivity.stabilityTitle")));
      body.append(
        document.createTextNode(
          t("sensitivity.stability", {
            path: data.balanced_region.route.path.join(" → "),
            networks: routeNetworks(data.balanced_region.route),
            start: data.balanced_region.cost_weight_start.toFixed(2),
            end: data.balanced_region.cost_weight_end.toFixed(2),
          })
        )
      );
      note.append(svg(ICONS.note), body);
      nodes.push(note);
    }
    resultsBox.replaceChildren(...nodes);
  }

  /* ---------- comparison rendering ---------- */

  function compareSideCard(side, target, isCandidate) {
    const card = el("div", `compare-side${isCandidate ? " is-candidate" : ""}`);
    const heading = el("div", "compare-date");
    heading.append(document.createTextNode(side.rate_date || side.label));
    if (side.resolved_to_earlier_publication) {
      heading.append(el("span", "resolved", t("compare.asked", { date: side.requested_date })));
    }
    card.append(heading);

    const rows = el("div", "compare-rows");
    const addRow = (key, valueNode) => {
      const row = el("div");
      row.append(el("span", "label", t(key)));
      const value = el("span", "value");
      value.append(valueNode);
      row.append(value);
      rows.append(row);
    };

    const route = side.route;
    addRow("compare.midRate", document.createTextNode(side.mid_rate ? fmtRate(side.mid_rate) : "—"));
    addRow("compare.route", pathFragment(route.path, "compare-path"));
    addRow("compare.networks", document.createTextNode(routeNetworks(route)));
    addRow("compare.fee", document.createTextNode(`$${fmtNumber(route.total_fee_usd)}`));
    addRow("compare.eta", document.createTextNode(humanizeHours(route.total_time_hours)));
    addRow("compare.recipient", document.createTextNode(fmtMoney(route.final_amount, target)));
    card.append(rows);
    return card;
  }

  function renderComparison(data) {
    const target = data.request.target;
    const panel = el("section", "panel");
    const header = el("div", "panel-header");
    header.append(el("h2", "", t("compare.title")));
    header.append(
      el("span", "hint", t("compare.hint", { profile: profileLabel(data.request.profile) }))
    );
    panel.append(header);

    const grid = el("div", "compare-grid");
    grid.append(compareSideCard(data.baseline, target, false));
    grid.append(compareSideCard(data.candidate, target, true));
    panel.append(grid);

    const deltas = el("div", "delta-rows");
    const addDelta = (key, text) => {
      const row = el("div");
      row.append(el("span", "label", t(key)));
      row.append(el("span", "value", text));
      deltas.append(row);
    };
    const hours = Number.parseFloat(data.deltas.time_hours);
    addDelta("compare.midRateChange", data.deltas.mid_rate ? fmtSigned(data.deltas.mid_rate) : "—");
    addDelta("compare.feeChange", data.deltas.fee_usd ? `${fmtSigned(data.deltas.fee_usd)} USD` : "—");
    addDelta(
      "compare.etaChange",
      !Number.isFinite(hours)
        ? "—"
        : hours === 0
          ? t("compare.noChange")
          : `${hours > 0 ? "+" : "-"}${humanizeHours(Math.abs(hours))}`
    );
    addDelta(
      "compare.recipient",
      data.deltas.receive ? `${fmtSigned(data.deltas.receive)} ${target}` : "—"
    );
    if (data.deltas.route_changed) {
      addDelta("compare.winningRoute", t("compare.routeDiffers"));
    }
    panel.append(deltas);

    if (data.caveats && data.caveats.length > 0) panel.append(caveatRows(data));

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

    const slots = new Map();
    data.regions.forEach((region) => {
      const key = routeKey(region.route);
      if (!slots.has(key)) slots.set(key, slots.size);
    });
    const routeText = (route) =>
      t("breakeven.routeVia", { path: route.path.join(" → "), networks: routeNetworks(route) });

    const panel = el("section", "panel");
    const header = el("div", "panel-header");
    header.append(el("h2", "", t("breakeven.title")));
    header.append(
      el(
        "span",
        "hint",
        t("breakeven.hint", { profile: profileLabel(data.request.profile), builds: data.builds })
      )
    );
    panel.append(header);

    const wrap = el("div", "regime-wrap");
    const frame = el("div", "strip-frame");
    const strip = el("div", "regime-strip breakeven-strip");
    strip.setAttribute("role", "img");
    strip.setAttribute(
      "aria-label",
      t("breakeven.stripLabel", {
        regions: data.regions
          .map((region) =>
            t("breakeven.regionLabel", {
              start: fmtMoney(region.amount_start, source),
              end: fmtMoney(region.amount_end, source),
              route: routeText(region.route),
            })
          )
          .join("; "),
      })
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
    wrap.append(el("div", "axis-caption", t("breakeven.axis", { currency: source })));

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
      row.append(el("span", "legend-path", t("breakeven.noRoute")));
      row.append(el("span", "legend-meta", t("breakeven.noRouteMeta")));
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

    if (data.caveats && data.caveats.length > 0) panel.append(caveatRows(data));

    resultsBox.replaceChildren(panel);

    scenarioMarkerUpdater = (current) => {
      const parsed = parsePositiveAmount(current.amount);
      const sameCurrency = current.source === source;
      const inRange = parsed !== null && parsed.value >= min && parsed.value <= max;
      marker.hidden = !(sameCurrency && inRange);
      if (!sameCurrency) {
        note.textContent = t("breakeven.noteCurrency", { currency: source });
        return;
      }
      if (!parsed) {
        note.textContent = t("breakeven.noteNoAmount");
        return;
      }
      const amount = `${fmtAmountLabel(parsed.value)} ${source}`;
      if (!inRange) {
        note.textContent = t("breakeven.noteOutside", { amount });
        return;
      }
      const percent = toRatio(parsed.value) * 100;
      marker.style.left = `${percent}%`;
      markerLabel.textContent = t("marker.yourAmount", { amount: fmtCompact(parsed.value) });
      placeLabel(markerLabel, percent);
      const bracket = (data.crossovers || []).find(
        (crossover) =>
          parsed.value >= Number.parseFloat(crossover.bracket_low) &&
          parsed.value <= Number.parseFloat(crossover.bracket_high)
      );
      if (bracket) {
        note.textContent = t("breakeven.noteBracket", {
          amount,
          below: bracket.below.networks.join(", "),
          above: bracket.above.networks.join(", "),
        });
        return;
      }
      const region = data.regions.find(
        (candidate) =>
          parsed.value >= Number.parseFloat(candidate.amount_start) &&
          parsed.value <= Number.parseFloat(candidate.amount_end)
      );
      note.textContent = region
        ? t("breakeven.noteWinner", { amount, route: routeText(region.route) })
        : t("breakeven.noteGap", { amount });
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
    const winnerText = (winner) =>
      t("breakeven.routeVia", {
        path: winner.signature.path.join(" → "),
        networks: [...new Set(winner.signature.networks)].join(", "),
      });

    const panel = el("section", "panel");
    const header = el("div", "panel-header");
    header.append(el("h2", "", t("regime.title")));
    header.append(
      el("span", "hint", t("regime.hint", { builds: data.builds, columns: columnCount }))
    );
    panel.append(header);

    const wrap = el("div", "regime-map-wrap");
    const layout = el("div", "regime-map-layout");
    layout.append(el("div", "regime-map-y-title", t("regime.yTitle")));

    const yAxis = el("div", "regime-map-y-axis");
    yAxis.append(el("span", "", t("regime.yCost")));
    yAxis.append(el("span", "", "0.5"));
    yAxis.append(el("span", "", t("regime.yTime")));
    layout.append(yAxis);

    const plot = el("div", "regime-map-plot");
    plot.style.gridTemplateColumns = `repeat(${columnCount}, minmax(12px, 1fr))`;
    plot.style.gridTemplateRows = `repeat(${rowCount}, minmax(3px, 1fr))`;
    plot.setAttribute("role", "img");
    plot.setAttribute(
      "aria-label",
      t("regime.plotLabel", { source: data.request.source, target: data.request.target })
    );

    for (let weightIndex = rowCount - 1; weightIndex >= 0; weightIndex -= 1) {
      amounts.forEach((amount, amountIndex) => {
        const winnerId = data.grid[weightIndex][amountIndex];
        const regionId = data.region_grid[weightIndex][amountIndex];
        const cell = el("span", `regime-map-cell${winnerId === null ? " no-route" : ""}`);
        if (winnerId !== null) {
          cell.style.background = slotColor(winnerId);
          cell.title = t("regime.cellTitle", {
            amount: fmtMoney(amount, source),
            weight: weights[weightIndex].toFixed(2),
            route: winnerText(winnerById.get(winnerId)),
            region: regionId + 1,
          });
        } else {
          cell.title = t("regime.cellNoRoute", {
            amount: fmtMoney(amount, source),
            weight: weights[weightIndex].toFixed(2),
          });
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
    xAxis.append(el("div", "axis-caption", t("breakeven.axis", { currency: source })));
    layout.append(xAxis);
    wrap.append(layout);

    const legend = el("div", "regime-legend regime-map-legend");
    data.winners.forEach((winner) => {
      const row = el("div", "legend-row");
      const swatch = el("span", "dot");
      swatch.style.background = slotColor(winner.id);
      row.append(swatch);
      row.append(el("span", "legend-path", winner.signature.path.join(" → ")));
      row.append(el("span", "legend-meta", [...new Set(winner.signature.networks)].join(", ")));
      legend.append(row);
    });
    wrap.append(legend);

    const note = el("p", "scenario-note");
    wrap.append(note);
    panel.append(wrap);

    const regionsHeader = el("div", "panel-header");
    regionsHeader.append(el("h2", "", t("regime.regionsTitle")));
    regionsHeader.append(el("span", "hint", t("regime.regionsHint")));
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
          t("regime.regionLabel", {
            id: region.id + 1,
            networks: winner.signature.networks.join(", "),
          })
        )
      );
      row.append(label);
      row.append(
        el(
          "span",
          "regime-region-span",
          t("regime.regionSpan", {
            start: fmtMoney(region.sampled_amount_start, source),
            end: fmtMoney(region.sampled_amount_end, source),
            wstart: region.sampled_cost_weight_start.toFixed(2),
            wend: region.sampled_cost_weight_end.toFixed(2),
            cells: region.cell_count,
          })
        )
      );
      regionRows.append(row);
    });
    panel.append(regionRows);

    if (data.caveats && data.caveats.length > 0) panel.append(caveatRows(data));

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
        note.textContent = t("regime.noteCurrency", { currency: source });
        return;
      }
      if (!parsed) {
        note.textContent = t("regime.noteNoAmount");
        return;
      }
      const amount = `${fmtAmountLabel(parsed.value)} ${source}`;
      if (!inRange) {
        note.textContent = t("regime.noteOutside", { amount });
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
      amounts.forEach((sample, index) => {
        if (
          Math.abs(Math.log(sample / parsed.value)) <
          Math.abs(Math.log(amounts[column] / parsed.value))
        ) {
          column = index;
        }
      });
      const row = Math.round(weight * (rowCount - 1));
      const winnerId = data.grid[row][column];
      const regionId = data.region_grid[row][column];
      const cell = `${fmtMoney(amounts[column], source)}, α ${weights[row].toFixed(2)}`;
      const profile = profileInline(current.profile);
      note.textContent =
        winnerId === null
          ? t("regime.noteNoRoute", { amount, profile, cell })
          : t("regime.noteWinner", {
              amount,
              profile,
              cell,
              route: winnerText(winnerById.get(winnerId)),
              region: regionId + 1,
            });
    };
  }

  /* ---------- sources rendering ---------- */

  function renderSources(records) {
    sourceRecords = records;
    const nodes = [];
    // Entries quote their evidence, so they stay in the language of the
    // cited sources; the surrounding interface is translated.
    const note = t("registry.originalNote");
    if (note) nodes.push(el("p", "registry-note", note));
    const wrap = el("div", "hop-table-wrap");
    const table = el("table", "data-table registry-table");
    const head = el("thead");
    const headRow = el("tr");
    [
      "registry.evidence",
      "registry.network",
      "registry.metric",
      "registry.class",
      "registry.checked",
      "registry.reference",
    ].forEach((key) => headRow.append(el("th", "", t(key))));
    head.append(headRow);
    table.append(head);

    const body = el("tbody");
    records.forEach((record) => {
      const row = el("tr");
      row.append(el("td", "", record.evidence_id));
      row.append(el("td", "", record.network));
      const metricCell = el("td");
      metricCell.lang = "en";
      metricCell.append(document.createTextNode(`${record.metric}: ${record.value}`));
      metricCell.append(el("span", "caveat", record.caveat));
      row.append(metricCell);
      const classCell = el("td");
      classCell.append(provenanceBadge(record.classification));
      row.append(classCell);
      row.append(el("td", "num", record.checked_on));
      const referenceCell = el("td");
      if (record.reference) {
        const link = el("a", "reference-link", t("registry.source"));
        link.href = record.reference;
        link.target = "_blank";
        link.rel = "noopener";
        referenceCell.append(link);
      } else {
        referenceCell.append(el("span", "caveat", t("registry.assumption")));
      }
      row.append(referenceCell);
      body.append(row);
    });
    table.append(body);
    wrap.append(table);
    nodes.push(wrap);
    sourcesBox.replaceChildren(...nodes);
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
      // The explanation follows the interface language, not the browser's.
      body: JSON.stringify({ kind, data, lang }),
      signal,
    });
    if (!response.ok || !response.body) {
      throw await responseError(response);
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
          throw new Error(event.message || t("ai.failed"));
        }
      }
    }
    renderAiText(output, fullText, false);
    return { model: null };
  }

  function setAiButton(button, key) {
    button.dataset.i18n = key;
    button.textContent = t(key);
  }

  function appendAiPanel(kind, data, signal) {
    if (!aiMeta || !aiMeta.enabled) return;
    const panel = el("section", "ai-panel");

    const head = el("div", "ai-head");
    const title = el("span", "ai-title");
    const titleText = el("span", "", t("ai.title"));
    titleText.dataset.i18n = "ai.title";
    title.append(svg(ICONS.sparkle), titleText);
    head.append(title);
    const button = el("button", "button button-ai");
    button.type = "button";
    setAiButton(button, "ai.explain");
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
      button.dataset.busy = "true";
      button.replaceChildren(
        svg('<span class="spinner"></span>'),
        document.createTextNode(` ${t("ai.thinking")}`)
      );
      body.hidden = false;
      footer.hidden = true;
      output.replaceChildren(el("p", "", ""));
      output.firstChild.append(el("span", "ai-caret"));
      try {
        const result = await streamExplanation(kind, data, output, signal);
        footer.dataset.i18n = "ai.footer";
        footer.dataset.i18nParams = JSON.stringify({ model: result.model || "Claude" });
        footer.textContent = t("ai.footer", { model: result.model || "Claude" });
        footer.hidden = false;
        delete button.dataset.busy;
        setAiButton(button, "ai.again");
      } catch (error) {
        delete button.dataset.busy;
        // Superseded by a new result: that result already replaced this panel.
        if (isAbort(error)) return;
        output.replaceChildren(el("p", "ai-error", messageOf(error)));
        setAiButton(button, "ai.retry");
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
        const progress = Math.min((now - start) / duration, 1);
        const eased = 1 - (1 - progress) ** 3;
        node.textContent =
          prefix +
          (target * eased).toLocaleString(numberLocale(), {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
          }) +
          suffix;
        if (progress < 1) {
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

  // Draws results from data already received. A language switch calls it
  // again with the same data, keeping any AI explanation already on screen.
  function drawResults(view, { preserveAi = false } = {}) {
    const aiPanel = preserveAi ? resultsBox.querySelector(".ai-panel") : null;
    scenarioMarkerUpdater = null;
    RENDERERS[view.kind](view.data, view.request);
    if (scenarioMarkerUpdater) scenarioMarkerUpdater(currentRequest());
    if (aiPanel) {
      applyTranslations(aiPanel);
      resultsBox.append(aiPanel);
    } else {
      appendAiPanel(view.kind, view.data, viewController.signal);
    }
  }

  function rerenderView() {
    renderAlert();
    if (shownWarnings) showWarnings(shownWarnings);
    // A cancelled run is still `activeRun` until it unwinds; it no longer
    // owns the view, so only a live run keeps the loading card.
    if (activeRun && !activeRun.signal.aborted) {
      showSkeleton(activeRun.kind);
      const busyButton = actionButtons.find((button) => button.dataset.busy === "true");
      if (busyButton) showBusyLabel(busyButton);
      return;
    }
    if (currentView.type === "results") drawResults(currentView, { preserveAi: true });
  }

  function snapshotView() {
    return {
      results: [...resultsBox.childNodes],
      alerts: [...alertsBox.childNodes],
      alertsHidden: alertsBox.hidden,
      alertMessage,
      warnings: [...warningsBox.childNodes],
      warningsHidden: warningsBox.hidden,
      shownWarnings,
      markerUpdater: scenarioMarkerUpdater,
      lang,
    };
  }

  function restoreView(snapshot) {
    resultsBox.replaceChildren(...snapshot.results);
    alertsBox.replaceChildren(...snapshot.alerts);
    alertsBox.hidden = snapshot.alertsHidden;
    alertMessage = snapshot.alertMessage;
    warningsBox.replaceChildren(...snapshot.warnings);
    warningsBox.hidden = snapshot.warningsHidden;
    shownWarnings = snapshot.shownWarnings;
    scenarioMarkerUpdater = snapshot.markerUpdater;
    // The language may have changed while the request was running.
    if (snapshot.lang !== lang) rerenderView();
    else if (scenarioMarkerUpdater) scenarioMarkerUpdater(currentRequest());
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
    run.kind = kind;
    const signal = run.signal;
    clearFeedback();
    setResultsStale(false);
    setBusy(true, activeButton);
    showSkeleton(kind);
    announceResults(t("announce.progress", { view: t(VIEW_KEYS[kind]) }));
    try {
      const data = await apiGet(ENDPOINTS[kind], paramsFor(kind, request), signal);
      // Route a late abort through the same path as one during the fetch.
      if (signal.aborted) throw new DOMException("Request aborted.", "AbortError");
      retireView();
      viewController = new AbortController();
      currentView = { type: "results", kind, data, request: { ...request } };
      showWarnings(data.warnings);
      drawResults(currentView);
      decorateResults();
      lastSuccessfulRun = { kind, request: { ...request } };
      markResultsStale();
      saveRecent(kind, request);
      syncUrl(kind, request);
      updateDocumentTitle();
      announceResults(completionMessage(kind, data));
      if (reveal) revealIfOffscreen(warningsBox.hidden ? resultsBox : warningsBox);
    } catch (error) {
      if (isAbort(error)) {
        // A superseded run is not a failure; the run that replaced it owns
        // the view. A cancelled one puts back what was there before it.
        if (run.cancelledByUser) {
          restoreView(snapshot);
          markResultsStale();
          announceResults(t("announce.cancelled"));
        }
        return;
      }
      retireView();
      currentView = { type: "error" };
      lastSuccessfulRun = null;
      setResultsStale(false);
      resultsBox.replaceChildren();
      showError(() => messageOf(error));
      updateDocumentTitle();
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
      currentView = { type: "empty" };
      lastSuccessfulRun = null;
      setResultsStale(false);
      resultsBox.replaceChildren(initialEmptyState);
      applyTranslations(initialEmptyState);
      updateDocumentTitle();
      announceResults(t("announce.cleared"));
    }
  });

  swapButton.addEventListener("click", () => {
    const source = sourceSelect.value;
    sourceSelect.value = targetSelect.value;
    targetSelect.value = source;
    renderQuickAmounts();
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
    renderQuickAmounts();
    updateScenarioSummary();
  }

  function renderMeta() {
    if (!metaInfo) return;
    const versionChip = $("#version-chip");
    versionChip.textContent = `v${metaInfo.version}`;
    versionChip.hidden = false;
    const fx = metaInfo.fx;
    if (fx) {
      const label =
        fx.mode === "live"
          ? t(fx.stale ? "fx.liveCached" : "fx.live", { date: fx.rate_date })
          : t(fx.fallback ? "fx.frozenFallback" : "fx.frozen");
      // The top bar and the phone layout's disclaimer carry the same status.
      [$("#fx-chip"), $("#disclaimer-fx")].forEach((chip) => {
        chip.textContent = label;
        // The detail is the server's own diagnostic, kept verbatim.
        chip.title = fx.detail || "";
        chip.classList.toggle("chip-warning", Boolean(fx.fallback));
        chip.hidden = false;
      });
    }
    if (metaInfo.disclaimer) $("#disclaimer").hidden = false;
  }

  async function boot() {
    // The backend rejects future dates; do not offer them in the picker.
    onDateInput.max = new Date().toISOString().slice(0, 10);
    const metaPromise = apiGet("/api/meta", {});
    const sourcesPromise = apiGet("/api/sources", {});
    try {
      await Promise.all([loadCatalog("en"), loadCatalog(lang)]);
    } catch {
      // Without a catalog the markup's English text still stands.
      lang = "en";
    }
    refreshLanguage();
    try {
      const meta = await metaPromise;
      metaInfo = meta;
      aiMeta = meta.ai || null;
      quickAmountsByCurrency = meta.quick_amounts || {};
      populateCurrencies(meta.currencies);
      meta.networks.forEach((network) => networkSlot(network.name));
      renderMeta();
      const urlRequest = requestFromUrl();
      if (urlRequest) {
        applyRequestToForm(urlRequest);
        runRequest(urlRequest.kind, buttonForKind(urlRequest.kind), { reveal: false });
      }
    } catch (error) {
      showError(() => t("request.metaFailed", { message: messageOf(error) }));
    }
    try {
      const sources = await sourcesPromise;
      renderSources(sources.records);
    } catch {
      sourcesBox.replaceChildren(el("div", "empty-state", t("request.registryFailed")));
    }
  }

  boot();
})();
