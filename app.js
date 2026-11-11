/**
 * Crystal Casino v5 — Demo / TEST MODE slot machine (Megaways + 25-line Classic).
 * Every outcome (reel heights, symbols, cascades, line/ways wins, free spins,
 * mini-game prizes, Tea Wheel stop, jackpot, gamble card) is
 * decided on the server. This file only animates the result it is sent.
 * Social casino: virtual coins only. Coin packs use Stripe Checkout in TEST
 * mode. Coins have no cash value and cannot be withdrawn or redeemed.
 */
(() => {
  "use strict";

  const REELS = 5;
  const ROWS = 3;
  const TEA_IMG = "/assets/green-tea-256.webp";
  const TEA_IMG_BIG = "/assets/green-tea-512.webp";
  const BIG_WIN_X = 15, MEGA_WIN_X = 50, EPIC_WIN_X = 150;
  let JACKPOT_MULT = 5000;
  const HISTORY_KEY = "crystal-reels-history-v2";
  const PREFS_KEY = "crystal-reels-prefs-v3";
  const Gems = window.CrystalGems;
  const HI_SYMBOLS = new Set(["ruby", "greentea", "wild", "sapphire", "emerald"]);
  const REDUCE = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const ENGAGE_KEY = "crystal-reels-engage-v5";
  const AGE_KEY = "crystal-casino-age-ok-v1";
  const LEGAL_DEFAULT = "Coins are for entertainment only, have no monetary value and cannot be redeemed for cash or prizes.";

  let SYMBOLS = [];
  let PAYLINES = [
    [1, 1, 1, 1, 1], [0, 0, 0, 0, 0], [2, 2, 2, 2, 2], [0, 1, 2, 1, 0], [2, 1, 0, 1, 2],
    [0, 0, 1, 2, 2], [2, 2, 1, 0, 0], [1, 0, 0, 0, 1], [1, 2, 2, 2, 1], [0, 1, 1, 1, 0],
    [2, 1, 1, 1, 2], [1, 0, 1, 2, 1], [1, 2, 1, 0, 1], [0, 1, 0, 1, 0], [2, 1, 2, 1, 2],
    [1, 1, 0, 1, 1], [1, 1, 2, 1, 1], [0, 0, 2, 0, 0], [2, 2, 0, 2, 2], [0, 2, 0, 2, 0],
    [2, 0, 2, 0, 2], [1, 0, 2, 0, 1], [1, 2, 0, 2, 1], [0, 2, 2, 2, 0], [2, 0, 0, 0, 2],
  ];
  let LINE_OPTIONS = [1, 5, 10, 20, 25];
  let BPL = [20, 50, 100, 200, 400, 1000, 2000, 4000];
  let FEATURES = { wild_mult: 2, free_spin_mult: 2, max_free_spins: 50, gamble_max_rounds: 5,
    scatter_pays: { 3: { pay: 2, free_spins: 8 }, 4: { pay: 5, free_spins: 12 }, 5: { pay: 20, free_spins: 20 } } };
  let MW = { bet_aud: [200, 400, 600, 1000, 2000, 4000, 10000, 20000, 50000, 100000], reels: 6, top_reels: [1, 2, 3, 4], min_rows: 2, max_rows: 7, max_ways: 117649,
    pays: {}, scatter_pays: { 4: { pay: 1, free_spins: 10 }, 5: { pay: 5, free_spins: 15 }, 6: { pay: 25, free_spins: 20 } }, retrigger: {} };
  let MINIS = { pick_tiles: 12, pick_prizes: [], wheel_wedges: [], wheel_min_scatters: { classic: 2, megaways: 3 } };
  let PACKS = [];
  let LEGAL = LEGAL_DEFAULT;
  let RESPONSIBLE = "Play for fun. This is a social casino, not real-money gambling. If you need a break, step away. 18+ only.";
  const lineColor = (n) => `hsl(${((n - 1) * 137.5) % 360}, 95%, 62%)`;
  const SYM_COLORS = { quartz: ["#ffc2e6", "#ff7fc8"], citrine: ["#fff1a6", "#f3c441"], topaz: ["#ffd0a0", "#ff9a3d"], amethyst: ["#e0c2ff", "#a855f7"],
    emerald: ["#b8ffcf", "#22c55e"], sapphire: ["#bfe0ff", "#3b82f6"], ruby: ["#ffb3c0", "#ef233c"], greentea: ["#eaffd0", "#8ff06b"], wild: ["#f5d0fe", "#c084fc", "#f3c441"], shard: ["#e0f2fe"] };

  // ---- State ----
  let prefs = loadPrefs();
  let coins = 0;
  let stats = { spins: 0, totalWonAud: 0, totalBetAud: 0 };
  let bonuses = { daily_available: false, hourly_available: false, hourly_seconds: 0, daily_coins: 8000, hourly_coins: 2000 };
  let profile = { nickname: "Hopper", level: 1, xp: 0, xp_needed: 80, current_streak: 0, best_streak: 0, theme: "crystal" };
  let trophies = { unlocked: [], new: [], items: [] };
  let missions = [];
  let themes = [];
  let prizeLegal = "All in-game prizes are for entertainment only. Trophies, themes, badges and bonus coins have no cash or real-world value and cannot be redeemed for money or prizes.";
  let prizeEvents = { newTrophies: [], levelUp: 0 };
  let lbPeriod = "daily";
  let lbBoard = "biggest";
  let stripeEnabled = false;
  let busy = false;
  let ready = false;
  let muted = !!prefs.muted;
  let volume = Number.isFinite(prefs.volume) ? prefs.volume : 70;
  let turbo = !!prefs.turbo;
  let mode = prefs.mode === "classic" ? "classic" : "megaways";
  let lineIdx = prefs.lineIdx;
  let bplIdx = prefs.bplIdx;
  let mwBetIdx = prefs.mwBetIdx;
  let pendingWinAud = 0;
  let gambleAud = 0;
  let history = loadHistory();
  let presentToken = 0;
  let autoCountChoice = prefs.autoCount || "25";
  const auto = { running: false, remaining: 0, total: 0, played: 0, stopBonus: true, stopBig: true, stopBelowAud: null };
  let engage = loadEngage();
  function loadEngage() {
    try { return { xp: 0, level: 1, streak: 0, bestStreak: 0, daily: "", ...JSON.parse(localStorage.getItem(ENGAGE_KEY) || "{}") }; }
    catch { return { xp: 0, level: 1, streak: 0, bestStreak: 0, daily: "" }; }
  }
  function saveEngage() { try { localStorage.setItem(ENGAGE_KEY, JSON.stringify(engage)); } catch { /* ignore */ } }
  const todayPerth = () => new Date().toLocaleDateString("en-CA", { timeZone: "Australia/Perth" });
  const xpNeeded = (lv) => 80 * Math.max(1, lv);
  const isMobile = () => innerWidth < 720;
  const pcount = (n) => (REDUCE ? 0 : Math.round(n * (isMobile() ? 0.42 : 1)));

  // ---- DOM ----
  const $ = (s) => document.querySelector(s);
  const reelsEl = $("#reels");
  const frameEl = $("#reels-frame");
  const overlay = $("#lines-overlay");
  const cabinetEl = $("#cabinet");
  const msgEl = $("#msg");
  const winStrip = msgEl.parentElement;
  const winMeter = $("#win-meter");
  const btnSpin = $("#btn-spin");
  const btnAuto = $("#btn-auto");
  const btnTurbo = $("#btn-turbo");
  const btnGamble = $("#btn-gamble");
  const btnMute = $("#btn-mute");
  const volEl = $("#vol");
  const toastEl = $("#toast");
  const celebrateEl = $("#celebrate");
  const autoStatus = $("#auto-status");
  const fsBanner = $("#fs-banner");
  const mwReelsEl = $("#mw-reels");
  const mwTopEl = $("#mw-top");
  const mwMultEl = $("#mw-mult");
  const waysVal = $("#ways-val");

  // ---- Prefs & history ----
  function defaultPrefs() { return { mode: "megaways", lineIdx: 4, bplIdx: 0, mwBetIdx: 1, muted: false, volume: 70, turbo: false, autoCount: "25" }; }
  function loadPrefs() {
    try {
      const old = JSON.parse(localStorage.getItem("crystal-reels-prefs-v2") || "{}");
      const loaded = { ...defaultPrefs(), ...old, mode: "megaways", ...JSON.parse(localStorage.getItem(PREFS_KEY) || "{}") };
      delete loaded.displayCurrency;
      return loaded;
    } catch { return defaultPrefs(); }
  }
  function savePrefs() {
    prefs = { mode, lineIdx, bplIdx, mwBetIdx, muted, volume, turbo, autoCount: autoCountChoice };
    try { localStorage.setItem(PREFS_KEY, JSON.stringify(prefs)); } catch { /* ignore */ }
  }
  function loadHistory() { try { const h = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"); return Array.isArray(h) ? h.slice(0, 40) : []; } catch { return []; } }
  function saveHistory() { try { localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, 40))); } catch { /* ignore */ } }

  // ---- Money ----
  const totalCoins = () => Math.max(0, Math.round(coins || 0));
  const field = (obj, ...keys) => {
    if (!obj) return 0;
    for (const k of keys) if (obj[k] != null) return obj[k];
    return 0;
  };
  const winOf = (s) => field(s, "win", "win_aud");
  const rawWinOf = (s) => field(s, "raw_win", "raw_win_aud");
  const jackpotOf = (s) => field(s, "jackpot", "jackpot_aud", "jackpot_paid", "jackpot_paid_aud");
  const scatterWinOf = (s) => field(s, "scatter_win", "scatter_win_aud");
  function money(n) {
    const v = Math.round(Number(n) || 0);
    return `${v.toLocaleString("en-US")} coins`;
  }
  function moneyShort(n) {
    return Math.round(Number(n) || 0).toLocaleString("en-US");
  }
  const lines = () => LINE_OPTIONS[Math.min(lineIdx, LINE_OPTIONS.length - 1)];
  const bpl = () => BPL[Math.min(bplIdx, BPL.length - 1)];
  const mwBet = () => MW.bet_aud[Math.min(mwBetIdx, MW.bet_aud.length - 1)];
  const totalBet = () => (mode === "megaways" ? mwBet() : Math.round(lines() * bpl() * 100) / 100);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const speed = (ms) => (turbo ? Math.round(ms * 0.35) : ms);
  const symH = () => { const el = reelsEl.querySelector(".symbol"); return el ? el.getBoundingClientRect().height : 100; };
  const symbolName = (id) => (SYMBOLS.find((s) => s.id === id) || {}).name || id;

  // ---- API ----
  async function api(path, options = {}) {
    const res = await fetch(path, { credentials: "same-origin", headers: options.body ? { "Content-Type": "application/json" } : {}, ...options });
    let data = null;
    try { data = await res.json(); } catch { data = null; }
    if (!res.ok) { const e = new Error((data && data.error) || `Request failed (${res.status})`); e.status = res.status; e.data = data; throw e; }
    return data;
  }
  function applySnapshot(s) {
    if (!s) return;
    if (typeof s.coins === "number") coins = Math.round(s.coins);
    if (s.stats) stats = { spins: s.stats.spins || 0, totalWonAud: field(s.stats, "total_won", "total_won_aud"), totalBetAud: field(s.stats, "total_bet", "total_bet_aud") };
    if (typeof s.gamble === "number") gambleAud = s.gamble;
    else if (typeof s.gamble_aud === "number") gambleAud = s.gamble_aud;
    if (s.bonuses) bonuses = { ...bonuses, ...s.bonuses };
    if (s.profile) {
      profile = { ...profile, ...s.profile };
      engage.level = profile.level;
      engage.xp = profile.xp;
      engage.streak = profile.current_streak;
      engage.bestStreak = profile.best_streak;
    }
    if (s.trophies) {
      trophies = { unlocked: [], new: [], items: [], ...s.trophies };
      if (Array.isArray(s.trophies.new) && s.trophies.new.length) prizeEvents.newTrophies = s.trophies.new.slice();
    }
    if (Array.isArray(s.missions)) missions = s.missions;
    if (Array.isArray(s.themes)) themes = s.themes;
    if (s.prize_legal) prizeLegal = s.prize_legal;
    if (s.level_up) prizeEvents.levelUp = s.level_up;
    applyTheme(profile.theme);
    if (s.config) applyConfig(s.config);
  }
  function applyConfig(cfg) {
    stripeEnabled = !!cfg.stripe_enabled;
    $("#stripe-key-banner").hidden = stripeEnabled;
    if (Array.isArray(cfg.line_options)) LINE_OPTIONS = cfg.line_options;
    if (Array.isArray(cfg.bet_per_line) || Array.isArray(cfg.bet_per_line_aud)) BPL = cfg.bet_per_line || cfg.bet_per_line_aud;
    if (Array.isArray(cfg.packs)) PACKS = cfg.packs;
    if (cfg.legal) LEGAL = cfg.legal;
    if (cfg.responsible_play) RESPONSIBLE = cfg.responsible_play;
    if (cfg.jackpot_mult) JACKPOT_MULT = cfg.jackpot_mult;
    if (cfg.prize_legal) prizeLegal = cfg.prize_legal;
    if (cfg.prizes && cfg.prizes.legal) prizeLegal = cfg.prizes.legal;
    renderShop();
    if (Array.isArray(cfg.paylines)) PAYLINES = cfg.paylines;
    if (cfg.features) FEATURES = { ...FEATURES, ...cfg.features };
    if (cfg.megaways) {
      MW = { ...MW, ...cfg.megaways };
      if (Array.isArray(cfg.megaways.bet)) MW.bet_aud = cfg.megaways.bet;
    }
    if (cfg.minigames) MINIS = { ...MINIS, ...cfg.minigames };
    if (Array.isArray(cfg.symbols)) SYMBOLS = cfg.symbols.map((s) => ({ ...s, pays: Object.fromEntries(Object.entries(s.pays || {}).map(([k, v]) => [Number(k), v])) }));
    lineIdx = Math.min(lineIdx, LINE_OPTIONS.length - 1);
    bplIdx = Math.min(bplIdx, BPL.length - 1);
    mwBetIdx = Math.min(mwBetIdx, MW.bet_aud.length - 1);
    renderBadges();
  }

  // ---- Rendering ----
  function render() {
    const credit = Math.max(0, totalCoins() - pendingWinAud);
    $("#credit").textContent = moneyShort(credit);
    $("#primary-balance").textContent = moneyShort(credit);
    const legalEl = $("#shop-legal"); if (legalEl) legalEl.textContent = LEGAL;
    const foot = $("#footer-legal"); if (foot) foot.textContent = LEGAL;
    const resp = $("#footer-responsible"); if (resp) resp.textContent = RESPONSIBLE + " DEMO · TEST MODE.";
    cabinetEl.classList.toggle("mw", mode === "megaways");
    cabinetEl.classList.toggle("classic", mode === "classic");
    document.querySelectorAll("#mode-toggle button").forEach((b) => { b.classList.toggle("active", b.dataset.mode === mode); b.setAttribute("aria-pressed", String(b.dataset.mode === mode)); });
    $("#lines-val").textContent = String(lines());
    $("#lines-active").textContent = String(lines());
    $("#bpl-val").textContent = moneyShort(bpl());
    $("#mwbet-val").textContent = moneyShort(mwBet());
    $("#total-bet").textContent = moneyShort(totalBet());
    $("#stat-spins").textContent = String(stats.spins);
    $("#stat-won").textContent = moneyShort(stats.totalWonAud);
    $("#stat-bet").textContent = moneyShort(stats.totalBetAud);
    btnMute.textContent = muted || volume === 0 ? "🔇" : volume < 40 ? "🔉" : "🔊";
    volEl.value = String(volume);
    btnTurbo.setAttribute("aria-pressed", String(turbo));
    const lock = busy || auto.running;
    document.querySelectorAll("#mode-toggle button").forEach((b) => { b.disabled = lock; });
    ["#lines-down", "#lines-up", "#bpl-down", "#bpl-up", "#btn-max", "#mwbet-down", "#mwbet-up"].forEach((s) => { $(s).disabled = lock; });
    $("#lines-down").disabled = lock || lineIdx === 0;
    $("#lines-up").disabled = lock || lineIdx === LINE_OPTIONS.length - 1;
    $("#bpl-down").disabled = lock || bplIdx === 0;
    $("#bpl-up").disabled = lock || bplIdx === BPL.length - 1;
    $("#mwbet-down").disabled = lock || mwBetIdx === 0;
    $("#mwbet-up").disabled = lock || mwBetIdx === MW.bet_aud.length - 1;
    btnGamble.disabled = !(gambleAud > 0) || lock;
    document.querySelectorAll(".line-badge").forEach((b) => b.classList.toggle("active", Number(b.dataset.line) <= lines()));
    renderEngage();
  }
  function setMsg(text, lose = false) { msgEl.textContent = text; winStrip.classList.toggle("lose", lose); winStrip.classList.remove("pop"); void winStrip.offsetWidth; if (!lose) winStrip.classList.add("pop"); }
  function toast(msg, isError = false) {
    toastEl.hidden = false; toastEl.textContent = msg; toastEl.classList.toggle("error", isError);
    clearTimeout(toast._t); toast._t = setTimeout(() => { toastEl.hidden = true; }, 3200);
  }

  // ---- Badges & lines ----
  function renderBadges() {
    const L = $("#badges-left"), R = $("#badges-right");
    L.innerHTML = ""; R.innerHTML = "";
    PAYLINES.forEach((p, i) => {
      [[L, p[0]], [R, p[4]]].forEach(([el]) => {
        const b = document.createElement("button");
        b.type = "button"; b.className = "line-badge"; b.dataset.line = String(i + 1); b.textContent = String(i + 1);
        b.style.background = lineColor(i + 1); b.style.color = "#1a0633";
        b.title = `Line ${i + 1}`;
        el.appendChild(b);
      });
    });
    layoutBadges();
  }
  function layoutBadges() {
    const h = symH();
    const reels = reelsEl.getBoundingClientRect();
    [["#badges-left", 0], ["#badges-right", 4]].forEach(([sel, reel]) => {
      const box = $(sel);
      const top0 = reels.top - box.getBoundingClientRect().top;
      const bw = box.clientWidth;
      const groups = [[], [], []];
      [...box.children].forEach((b) => { const n = Number(b.dataset.line); groups[PAYLINES[n - 1][reel]].push(b); });
      groups.forEach((g, row) => {
        const size = g[0] ? g[0].getBoundingClientRect().width || 14 : 14;
        const cols = bw >= size * 2 + 2 ? 2 : 1;
        const rowsNeeded = Math.ceil(g.length / cols);
        const step = Math.min(size + 2, h / rowsNeeded);
        const startY = top0 + row * h + (h - rowsNeeded * step) / 2;
        g.forEach((b, k) => {
          const c = k % cols, r = Math.floor(k / cols);
          b.style.top = `${startY + r * step}px`;
          b.style.left = `${cols === 2 ? (c === 0 ? 0 : bw - size) : (bw - size) / 2}px`;
        });
      });
    });
  }
  function cellCenter(col, row) {
    const fr = frameEl.getBoundingClientRect();
    const reel = reelsEl.children[col].getBoundingClientRect();
    const h = symH();
    return [reel.left - fr.left + reel.width / 2, reel.top - fr.top + (row + 0.5) * h];
  }
  function clearLines() { overlay.innerHTML = ""; document.querySelectorAll(".line-badge.win").forEach((b) => b.classList.remove("win")); }
  function drawLine(n) {
    const rows = PAYLINES[n - 1];
    const fr = frameEl.getBoundingClientRect();
    overlay.setAttribute("viewBox", `0 0 ${fr.width} ${fr.height}`);
    const pts = rows.map((r, c) => cellCenter(c, r));
    const all = [[0, pts[0][1]], ...pts, [fr.width, pts[4][1]]].map((p) => p.map((v) => v.toFixed(1)).join(",")).join(" ");
    const col = lineColor(n);
    overlay.insertAdjacentHTML("beforeend", `<polyline class="ln-glow" points="${all}" stroke="${col}"/><polyline class="ln" points="${all}" stroke="${col}"/><polyline class="ln-run" points="${all}" stroke="${col}"/>`);
    document.querySelectorAll(`.line-badge[data-line="${n}"]`).forEach((b) => b.classList.add("win"));
  }
  function cellEl(col, row) { const cells = reelsEl.children[col].querySelectorAll(".symbol"); return cells[cells.length - ROWS + row]; }
  function highlightWin(w) {
    w.cells.forEach(([c, r]) => { const el = cellEl(c, r); if (el) { el.classList.add("win"); el.style.setProperty("--lc", lineColor(w.line)); } });
  }

  function makeCell(id) {
    const d = document.createElement("div");
    d.className = "symbol" + (HI_SYMBOLS.has(id) ? " hi" : "") + (id === "wild" ? " wild" : "");
    d.dataset.id = id;
    const img = document.createElement("img");
    img.src = Gems.url(id); img.alt = ""; img.draggable = false; img.decoding = "async";
    d.appendChild(img);
    return d;
  }
  const fillerIds = () => (SYMBOLS.length ? SYMBOLS.map((s) => s.id) : Gems.ids.concat("greentea"));
  const randomId = () => { const ids = fillerIds(); return ids[(Math.random() * ids.length) | 0]; };
  function initReels() {
    reelsEl.innerHTML = "";
    for (let c = 0; c < REELS; c++) {
      const reel = document.createElement("div"); reel.className = "reel";
      const strip = document.createElement("div"); strip.className = "reel-strip";
      for (let r = 0; r < ROWS; r++) strip.appendChild(makeCell(randomId()));
      reel.appendChild(strip); reelsEl.appendChild(reel);
    }
  }
  async function animateGrid(grid) {
    clearLines(); clearHighlights();
    const reels = [...reelsEl.children];
    const h = symH();
    cabinetEl.classList.remove("anticipate-any");
    reels.forEach((reel) => reel.querySelector(".reel-strip")?.classList.remove("land"));
    sfx.spin();
    let scatters = 0, extra = 0, landedScat = 0;
    const base = speed(800), gap = speed(220);
    await Promise.all(reels.map((reel, col) => {
      const strip = reel.querySelector(".reel-strip");
      const pad = turbo ? 8 : 18 + col * 4;
      strip.style.transition = "none";
      strip.style.transform = "translateY(0)";
      const keep = [...strip.children].slice(-ROWS);
      strip.innerHTML = "";
      for (let i = 0; i < pad; i++) strip.appendChild(makeCell(randomId()));
      keep.forEach((k) => strip.appendChild(k));
      // final symbols go on top so the strip scrolls downward into them
      const finals = grid[col].map(makeCell);
      finals.reverse().forEach((f) => strip.insertBefore(f, strip.firstChild));
      strip.style.transform = `translateY(${-(strip.children.length - ROWS) * h}px)`;
      if (scatters >= 2 && !turbo && !REDUCE) { extra += 950; reel.classList.add("anticipate"); cabinetEl.classList.add("anticipate-any"); sfx.anticipate(scatters); }
      const dur = base + col * gap + extra;
      const colScat = grid[col].filter((id) => id === "scatter").length;
      scatters += colScat;
      void strip.offsetHeight;
      reel.classList.add("spinning");
      const ease = reel.classList.contains("anticipate") && !REDUCE ? "cubic-bezier(0.05, 0.82, 0.12, 1.05)" : "cubic-bezier(0.22, 0.9, 0.3, 1.08)";
      strip.style.transition = `transform ${dur}ms ${ease}`;
      strip.style.transform = "translateY(0)";
      if (reel.classList.contains("anticipate")) setTimeout(() => sfx.tease(), Math.max(0, dur - 800));
      return sleep(dur + 20).then(() => {
        reel.classList.remove("spinning", "anticipate");
        if (!reelsEl.querySelector(".reel.anticipate")) cabinetEl.classList.remove("anticipate-any");
        sfx.stop(col);
        while (strip.children.length > ROWS) strip.removeChild(strip.lastChild);
        strip.style.transition = "none"; strip.style.transform = "translateY(0)";
        if (!REDUCE) {
          strip.classList.remove("land"); void strip.offsetWidth; strip.classList.add("land");
          [...strip.children].forEach((el) => { el.classList.remove("landed"); void el.offsetWidth; el.classList.add("landed"); });
          setTimeout(() => strip.classList.remove("land"), 400);
        }
        if (colScat) { landedScat += colScat; sfx.scatter(landedScat); grid[col].forEach((id, row) => { if (id === "scatter") burstAt(cellEl(col, row), 14); }); }
      });
    }));
    sfx.spinEnd();
  }

  // ---- Megaways reels ----
  const hasTop = (c) => MW.top_reels.includes(c);
  const fmtWays = (n) => Math.round(n).toLocaleString("en-US");
  let mwCols = null; // current combined columns (top cell first on reels 2-5)
  function mwColH() { const r = mwReelsEl.querySelector(".mw-reel"); return r ? r.getBoundingClientRect().height : 300; }
  function mwCell(id) {
    const d = makeCell(id);
    d.classList.add("mw-cell");
    return d;
  }
  function initMw() {
    mwReelsEl.innerHTML = ""; mwTopEl.innerHTML = "";
    const cols = [];
    for (let c = 0; c < MW.reels; c++) {
      const n = 2 + ((Math.random() * 5) | 0);
      const col = [];
      if (hasTop(c)) col.push(randomMwId(true, c));
      for (let i = 0; i < (hasTop(c) ? Math.min(n, 6) : n); i++) col.push(randomMwId(false, c));
      cols.push(col);
      const reel = document.createElement("div"); reel.className = "mw-reel";
      const strip = document.createElement("div"); strip.className = "mw-strip";
      reel.appendChild(strip); mwReelsEl.appendChild(reel);
      const top = document.createElement("div"); top.className = "mw-topslot" + (hasTop(c) ? "" : " cap");
      if (!hasTop(c)) top.innerHTML = c === 0 ? '<span class="cap-l">◀</span>' : '<span class="cap-r">▶</span>';
      mwTopEl.appendChild(top);
    }
    setMwBoard(cols);
    setWays(cols.reduce((p, col) => p * col.length, 1), false);
  }
  const randomMwId = (top = false, c = 1) => {
    // decorative filler only (real symbols come from the server): no wilds on reels 1 & 6, no BONUS on the top reel
    const ids = ["quartz", "citrine", "topaz", "amethyst", "emerald", "sapphire", "ruby", "greentea", "shard"].concat(hasTop(c) ? ["wild"] : [], top ? [] : ["scatter"]);
    return ids[(Math.random() * ids.length) | 0];
  };
  function mainOf(col, c) { return hasTop(c) ? col.slice(1) : col; }
  function setMwBoard(cols, anim = null) {
    // anim: { removed: Set("c,r"), prev: cols } → survivors fall, new cells drop in
    const h = mwColH();
    cols.forEach((col, c) => {
      const strip = mwReelsEl.children[c].querySelector(".mw-strip");
      const main = mainOf(col, c);
      const ch = h / main.length;
      strip.style.transition = "none"; strip.style.transform = "none";
      strip.innerHTML = "";
      main.forEach((id) => { const el = mwCell(id); el.style.height = `${ch}px`; strip.appendChild(el); });
      mwReelsEl.children[c].dataset.rows = String(main.length);
      const slot = mwTopEl.children[c];
      if (hasTop(c)) {
        slot.innerHTML = ""; const t = mwCell(col[0]); t.classList.add("top"); slot.appendChild(t);
      }
      if (anim) {
        const off = hasTop(c) ? 1 : 0;
        const prevMain = mainOf(anim.prev[c], c);
        const removedIdx = prevMain.map((_, r) => anim.removed.has(`${c},${r + off}`));
        const nNew = removedIdx.filter(Boolean).length;
        const els = [...strip.children];
        // survivors: old index r -> new index r + removedAfter(r)
        let k = nNew;
        prevMain.forEach((_, r) => {
          if (removedIdx[r]) return;
          const after = removedIdx.slice(r + 1).filter(Boolean).length;
          const el = els[k++];
          if (after && el) el.animate([{ transform: `translateY(${-after * ch}px)` }, { transform: "none" }], { duration: speed(380), easing: "cubic-bezier(.45,1.6,.6,1)" });
        });
        for (let i = 0; i < nNew; i++) {
          els[i].animate([{ transform: `translateY(${-(nNew + 0.6) * ch}px)`, opacity: 0.2 }, { transform: "none", opacity: 1 }],
            { duration: speed(420 + 40 * (nNew - i)), easing: "cubic-bezier(.35,1.45,.6,1)" });
        }
        if (hasTop(c) && anim.removed.has(`${c},0`)) {
          const t = mwTopEl.children[c].firstChild;
          t.animate([{ transform: "translateX(110%)", opacity: 0 }, { transform: "none", opacity: 1 }], { duration: speed(380), easing: "cubic-bezier(.3,1.4,.6,1)" });
        }
      }
    });
    mwCols = cols.map((c) => c.slice());
  }
  function mwCellEl(c, r) {
    if (hasTop(c) && r === 0) return mwTopEl.children[c].firstChild;
    const strip = mwReelsEl.children[c].querySelector(".mw-strip");
    return strip.children[r - (hasTop(c) ? 1 : 0)];
  }
  let waysRaf = null, waysShown = 117649;
  function setWays(n, animate = true) {
    cancelAnimationFrame(waysRaf);
    const meter = $("#ways-meter");
    const counter = $("#ways-counter");
    if (!animate) { waysShown = n; waysVal.textContent = fmtWays(n); meter.textContent = fmtWays(n); return Promise.resolve(); }
    const from = waysShown, t0 = performance.now(), dur = speed(650);
    counter.classList.remove("pop"); void counter.offsetWidth; counter.classList.add("pop");
    counter.classList.toggle("max", n >= MW.max_ways);
    return new Promise((res) => {
      let last = 0;
      const step = (t) => {
        const k = Math.min(1, (t - t0) / dur), v = from + (n - from) * (1 - Math.pow(1 - k, 3));
        waysVal.textContent = fmtWays(v); meter.textContent = fmtWays(v);
        if (t - last > 60 && k < 1) { sfx.waysTick(k); last = t; }
        if (k < 1) waysRaf = requestAnimationFrame(step); else { waysShown = n; res(); }
      };
      waysRaf = requestAnimationFrame(step);
    });
  }
  function scrambleWays() {
    cancelAnimationFrame(waysRaf);
    const counter = $("#ways-counter"); counter.classList.add("scramble"); counter.classList.remove("max");
    const step = () => { const v = 324 + Math.random() * (MW.max_ways - 324); waysVal.textContent = fmtWays(v); waysRaf = requestAnimationFrame(step); };
    waysRaf = requestAnimationFrame(step);
  }
  async function animateMw(stage) {
    clearHighlights();
    const cols = stage.cols;
    const h = mwColH();
    cabinetEl.classList.remove("anticipate-any");
    [...mwReelsEl.children].forEach((reel) => reel.querySelector(".mw-strip")?.classList.remove("land"));
    sfx.spin();
    scrambleWays();
    let scat = 0, extra = 0, landed = 0;
    const base = speed(700), gap = speed(190);
    // top reel: whole strip slides right-to-left during the spin
    mwTopEl.classList.add("spinning");
    await Promise.all(cols.map((col, c) => {
      const reel = mwReelsEl.children[c];
      const strip = reel.querySelector(".mw-strip");
      const main = mainOf(col, c);
      const ch = h / main.length;
      const pad = turbo ? 6 : 12 + c * 3;
      strip.style.transition = "none";
      strip.innerHTML = "";
      main.forEach((id) => { const el = mwCell(id); el.style.height = `${ch}px`; strip.appendChild(el); });
      for (let i = 0; i < pad; i++) { const el = mwCell(randomMwId(false, c)); el.style.height = `${ch}px`; strip.appendChild(el); }
      strip.style.transform = `translateY(${-pad * ch}px)`;
      reel.dataset.rows = String(main.length);
      if (scat >= 3 && !turbo && !REDUCE) { extra += 1000; reel.classList.add("anticipate"); cabinetEl.classList.add("anticipate-any"); sfx.anticipate(scat); }
      scat += col.filter((x) => x === "scatter").length;
      const dur = base + c * gap + extra;
      void strip.offsetHeight;
      reel.classList.add("spinning");
      const ease = reel.classList.contains("anticipate") && !REDUCE ? "cubic-bezier(0.05, 0.82, 0.12, 1.05)" : "cubic-bezier(0.22, 0.9, 0.3, 1.06)";
      strip.style.transition = `transform ${dur}ms ${ease}`;
      strip.style.transform = "translateY(0)";
      return sleep(dur + 20).then(() => {
        reel.classList.remove("spinning", "anticipate");
        if (!mwReelsEl.querySelector(".mw-reel.anticipate")) cabinetEl.classList.remove("anticipate-any");
        sfx.stop(c);
        while (strip.children.length > main.length) strip.removeChild(strip.lastChild);
        strip.style.transition = "none"; strip.style.transform = "none";
        if (!REDUCE) {
          strip.classList.remove("land"); void strip.offsetWidth; strip.classList.add("land");
          [...strip.children].forEach((el) => { el.classList.remove("landed"); void el.offsetWidth; el.classList.add("landed"); });
          setTimeout(() => strip.classList.remove("land"), 400);
        }
        if (hasTop(c)) {
          const slot = mwTopEl.children[c]; slot.innerHTML = "";
          const t = mwCell(col[0]); t.classList.add("top"); slot.appendChild(t);
          t.animate([{ transform: "translateX(120%)" }, { transform: "none" }], { duration: speed(260), easing: "cubic-bezier(.3,1.5,.6,1)" });
        }
        const colScat = col.filter((x) => x === "scatter").length;
        if (colScat) { landed += colScat; sfx.scatter(landed); col.forEach((x, r) => { if (x === "scatter") burstAt(mwCellEl(c, r), 14); }); }
      });
    }));
    mwTopEl.classList.remove("spinning");
    sfx.spinEnd();
    mwCols = cols.map((c) => c.slice());
    $("#ways-counter").classList.remove("scramble");
    await setWays(stage.ways);
    if (stage.ways >= MW.max_ways) { toast("MAXIMUM 117,649 WAYS!"); sfx.bonusSting(); }
  }
  function mwHighlight(wins) {
    clearHighlights();
    if (!wins.length) return;
    mwReelsEl.parentElement.classList.add("symbols-dim");
    wins.forEach((w) => w.cells.forEach(([c, r]) => { const el = mwCellEl(c, r); if (el) { el.classList.add("win"); el.style.setProperty("--lc", (SYM_COLORS[w.symbol] || ["#ffe07a"])[1]); } }));
  }
  function shatter(wins) {
    const seen = new Set();
    wins.forEach((w) => w.cells.forEach(([c, r]) => {
      const key = `${c},${r}`; if (seen.has(key)) return; seen.add(key);
      const el = mwCellEl(c, r); if (!el) return;
      el.classList.add("shatter");
      const id = el.dataset.id;
      const rr = el.getBoundingClientRect();
      shards(rr.left + rr.width / 2, rr.top + rr.height / 2, SYM_COLORS[id] || COLORS);
    }));
    sfx.shatter(seen.size);
    return seen;
  }
  const symName = (id) => ({ greentea: "GREEN TEA", wild: "WILD" }[id] || symbolName(id).toUpperCase());
  function mwDescribe(w, k) {
    return `${w.count} × ${symName(w.symbol)} · ${fmtWays(w.ways)} WAY${w.ways > 1 ? "S" : ""}${w.multiplier > 1 ? ` · ×${w.multiplier}` : ""} · ${money(winOf(w) * k)}`;
  }

  /** Present one Megaways spin (paid or free). Returns the amount shown. */
  async function presentMw(step, ctx) {
    const stages = step.stages || [];
    const k = rawWinOf(step) > 0 ? Math.min(1, winOf(step) / rawWinOf(step)) : 1; // table-limit scale
    await animateMw(stages[0]);
    let shown = ctx.shown;
    if (ctx.free) setMult(stages[0].multiplier, false);
    for (let i = 0; i < stages.length; i++) {
      const st = stages[i];
      if (!st.wins.length) break;
      if (ctx.token !== presentToken) return shown;
      mwHighlight(st.wins);
      const amt = winOf(st) * k;
      if (st.wins[0] && st.wins[0].cells[0]) flyWin(mwCellEl(...st.wins[0].cells[0]), amt);
      const x = amt / ctx.bet;
      sfx.winScaled(x, i);
      const tumble = i > 0 ? `TUMBLE ${i} · ` : "";
      setMsg(st.wins.length === 1 ? `${tumble}${mwDescribe(st.wins[0], k)}` : `${tumble}${st.wins.length} WINS · ${money(amt)}${st.multiplier > 1 ? ` · ×${st.multiplier}` : ""}`);
      document.querySelectorAll("#mw-reels .symbol.win").forEach((el, j) => { if (j % 3 === 0) burstAt(el, 6); });
      await rollUp(shown, shown + amt, speed(Math.min(1500, rollMs(amt, ctx.bet))));
      shown += amt;
      ctx.onShown(shown);
      if (st.wins.length > 1 && !turbo) {
        for (const w of st.wins.slice(0, 4)) { if (ctx.token !== presentToken) break; setMsg(`${tumble}${mwDescribe(w, k)}`); await sleep(520); }
      }
      await sleep(speed(350));
      const removed = shatter(st.wins);
      await sleep(speed(330));
      clearHighlights();
      const next = stages[i + 1];
      if (!next) break;
      setMwBoard(next.cols, { removed, prev: stages[i].cols });
      sfx.drop();
      if (ctx.free && next.multiplier > st.multiplier) { setMult(next.multiplier, true); }
      await sleep(speed(480));
    }
    if (scatterWinOf(step) > 0 || step.free_spins_awarded > 0) {
      clearHighlights(); mwReelsEl.parentElement.classList.add("symbols-dim");
      (step.scatter_pos || []).forEach(([c, r]) => { const el = mwCellEl(c, r); if (el) el.classList.add("scatter-hit"); });
      if (scatterWinOf(step) > 0) {
        const amt = scatterWinOf(step) * k;
        setMsg(`${step.scatters} × BONUS · ${money(amt)}`);
        await rollUp(shown, shown + amt, speed(700)); shown += amt; ctx.onShown(shown);
      }
      await sleep(speed(700));
    }
    if (step.cascades >= 3) toast(`${step.cascades} TUMBLES IN A ROW!`);
    return shown;
  }
  function setMult(n, bump) {
    mwMultEl.hidden = false;
    mwMultEl.textContent = `×${n}`;
    $("#fs-mult").textContent = mode === "megaways" ? `MULTIPLIER ×${n}` : `ALL WINS ×${FEATURES.free_spin_mult}`;
    if (bump) { mwMultEl.classList.remove("bump"); void mwMultEl.offsetWidth; mwMultEl.classList.add("bump"); sfx.multUp(n); burstAt(mwMultEl, 22); }
  }
  function clearHighlights() {
    reelsEl.classList.remove("symbols-dim");
    mwReelsEl.parentElement.classList.remove("symbols-dim");
    document.querySelectorAll(".symbol.win, .symbol.scatter-hit").forEach((el) => { el.classList.remove("win", "scatter-hit"); el.style.removeProperty("--lc"); });
  }

  // ---- Presentation ----
  function describe(w, mult = 1) {
    return `LINE ${w.line} · ${w.count} × ${symbolName(w.symbol)}${w.wild ? " (WILD ×2)" : ""}${mult > 1 ? ` · ×${mult}` : ""} · ${money(winOf(w))}`;
  }
  function showAllWins(step) {
    clearLines(); clearHighlights();
    const wins = step.line_wins || [];
    if (!wins.length && step.scatters < 3) return false;
    reelsEl.classList.add("symbols-dim");
    wins.forEach((w) => { drawLine(w.line); highlightWin(w); });
    if (step.scatters >= 3) (step.scatter_pos || []).forEach(([c, r]) => { const el = cellEl(c, r); if (el) el.classList.add("scatter-hit"); });
    reelsEl.querySelectorAll(".symbol.win").forEach((el, i) => { if (i % 3 === 0) burstAt(el, 8); });
    return true;
  }
  async function cycleWins(step, token, loop) {
    const wins = step.line_wins || [];
    if (wins.length < 2 && !loop) return;
    do {
      for (const w of wins) {
        if (token !== presentToken) return;
        clearLines(); clearHighlights(); reelsEl.classList.add("symbols-dim");
        drawLine(w.line); highlightWin(w); setMsg(describe(w, step.multiplier));
        await sleep(turbo ? 500 : 1100);
      }
      if (step.scatters >= 3 && token === presentToken) {
        clearLines(); clearHighlights(); reelsEl.classList.add("symbols-dim");
        (step.scatter_pos || []).forEach(([c, r]) => { const el = cellEl(c, r); if (el) el.classList.add("scatter-hit"); });
        setMsg(`${step.scatters} × PRISM SCATTER · ${money(scatterWinOf(step))}`);
        await sleep(turbo ? 500 : 1100);
      }
    } while (loop && token === presentToken && wins.length + (step.scatters >= 3 ? 1 : 0) > 1);
    if (token === presentToken && loop) { showAllWins(step); }
  }
  let rollRaf = null;
  function rollUp(fromAud, toAudAmt, ms) {
    cancelAnimationFrame(rollRaf);
    return new Promise((resolve) => {
      const meter = winMeter.parentElement;
      if (toAudAmt <= fromAud || ms <= 0) { winMeter.textContent = moneyShort(toAudAmt); resolve(); return; }
      meter.classList.add("rolling");
      const t0 = performance.now(); let lastTick = 0;
      const step = (t) => {
        const k = Math.min(1, (t - t0) / ms);
        winMeter.textContent = moneyShort(fromAud + (toAudAmt - fromAud) * (1 - Math.pow(1 - k, 2)));
        if (t - lastTick > 70 && k < 1) { sfx.tick(); lastTick = t; }
        if (k < 1) rollRaf = requestAnimationFrame(step); else { meter.classList.remove("rolling"); punchWin(); resolve(); }
      };
      rollRaf = requestAnimationFrame(step);
    });
  }
  const rollMs = (win, bet) => Math.min(3200, 500 + 120 * Math.sqrt(Math.max(0, win / Math.max(bet, 0.01))) * 60 / 10);
  function punchWin() {
    const meter = winMeter.parentElement;
    meter.classList.remove("punch"); void meter.offsetWidth; meter.classList.add("punch");
  }
  function flyWin(el, amount) {
    if (REDUCE || !el || !(amount > 0)) return;
    const r = el.getBoundingClientRect();
    const chip = document.createElement("div");
    chip.className = "fly-win";
    chip.textContent = "+" + money(amount);
    chip.style.left = `${r.left + r.width / 2}px`;
    chip.style.top = `${r.top}px`;
    document.body.appendChild(chip);
    setTimeout(() => chip.remove(), 950);
  }
  function shakeCabinet(heavy = false) {
    if (REDUCE) return;
    cabinetEl.classList.remove("shake", "shake-heavy");
    void cabinetEl.offsetWidth;
    cabinetEl.classList.add(heavy ? "shake-heavy" : "shake");
    setTimeout(() => cabinetEl.classList.remove("shake", "shake-heavy"), 750);
  }

  // ---- Sound (Web Audio, synthesised — no recorded assets) ----
  let audioCtx = null, master = null, sfxBus = null, musicBus = null;
  function ensureAudio() {
    if (!audioCtx) {
      const AC = window.AudioContext || window.webkitAudioContext; if (!AC) return;
      audioCtx = new AC();
      master = audioCtx.createGain();
      const comp = audioCtx.createDynamicsCompressor(); comp.threshold.value = -14; comp.ratio.value = 4;
      master.connect(comp); comp.connect(audioCtx.destination);
      sfxBus = audioCtx.createGain(); sfxBus.connect(master);
      musicBus = audioCtx.createGain(); musicBus.gain.value = 0.55; musicBus.connect(master);
      applyVolume();
    }
    if (audioCtx.state === "suspended") audioCtx.resume();
  }
  function applyVolume() {
    if (!master) return;
    const v = muted ? 0 : Math.pow(volume / 100, 1.6) * 1.1;
    master.gain.setTargetAtTime(v, audioCtx.currentTime, 0.03);
  }
  const silent = () => muted || volume === 0 || !audioCtx;
  function tone(freq, dur, { type = "sine", gain = 0.05, delay = 0, slideTo = null, bus = null, attack = 0.01 } = {}) {
    if (silent()) return;
    const t0 = audioCtx.currentTime + delay, o = audioCtx.createOscillator(), g = audioCtx.createGain();
    o.type = type; o.frequency.setValueAtTime(freq, t0);
    if (slideTo) o.frequency.exponentialRampToValueAtTime(slideTo, t0 + dur);
    g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(gain, t0 + attack); g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    o.connect(g); g.connect(bus || sfxBus); o.start(t0); o.stop(t0 + dur + 0.02);
  }
  let noiseBuf = null;
  function getNoise() {
    if (noiseBuf) return noiseBuf;
    const n = audioCtx.sampleRate * 1.5; noiseBuf = audioCtx.createBuffer(1, n, audioCtx.sampleRate);
    const d = noiseBuf.getChannelData(0); for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
    return noiseBuf;
  }
  function noise(dur, gain = 0.05, freq = 900, { type = "lowpass", delay = 0, q = 0.7 } = {}) {
    if (silent()) return;
    const t0 = audioCtx.currentTime + delay;
    const src = audioCtx.createBufferSource(), f = audioCtx.createBiquadFilter(), g = audioCtx.createGain();
    src.buffer = getNoise(); f.type = type; f.frequency.value = freq; f.Q.value = q;
    g.gain.setValueAtTime(gain, t0); g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    src.connect(f); f.connect(g); g.connect(sfxBus); src.start(t0, Math.random()); src.stop(t0 + dur + 0.02);
  }
  function chime(freq, dur = 0.5, gain = 0.05, delay = 0, bus = null) {
    tone(freq, dur, { gain, delay, bus }); tone(freq * 2.76, dur * 0.6, { gain: gain * 0.35, delay, bus }); tone(freq * 5.4, dur * 0.3, { gain: gain * 0.12, delay, bus });
  }
  const NOTE = (n) => 440 * Math.pow(2, (n - 69) / 12);
  let spinLoop = null;
  function startSpinLoop() {
    if (silent() || spinLoop) return;
    const t = audioCtx.currentTime;
    const src = audioCtx.createBufferSource(); src.buffer = getNoise(); src.loop = true;
    const bp = audioCtx.createBiquadFilter(); bp.type = "bandpass"; bp.frequency.value = 1500; bp.Q.value = 1.4;
    const g = audioCtx.createGain(); g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.05, t + 0.12);
    // "clack-clack" of symbols passing: amplitude LFO
    const lfo = audioCtx.createOscillator(); lfo.type = "square"; lfo.frequency.value = turbo ? 26 : 17;
    const lfoG = audioCtx.createGain(); lfoG.gain.value = 0.025; lfo.connect(lfoG); lfoG.connect(g.gain);
    const hum = audioCtx.createOscillator(); hum.type = "triangle"; hum.frequency.value = 110;
    const humG = audioCtx.createGain(); humG.gain.value = 0.012; hum.connect(humG); humG.connect(sfxBus);
    src.connect(bp); bp.connect(g); g.connect(sfxBus);
    src.start(); lfo.start(); hum.start();
    spinLoop = { src, g, lfo, hum, humG };
  }
  function stopSpinLoop() {
    if (!spinLoop || !audioCtx) { spinLoop = null; return; }
    const { src, g, lfo, hum, humG } = spinLoop, t = audioCtx.currentTime;
    g.gain.cancelScheduledValues(t); g.gain.setTargetAtTime(0.0001, t, 0.05); humG.gain.setTargetAtTime(0.0001, t, 0.05);
    [src, lfo, hum].forEach((n) => n.stop(t + 0.3));
    spinLoop = null;
  }
  // Bonus / wheel music loop: a simple synth sequencer (C minor pentatonic, 128 bpm)
  let music = null;
  function startMusic(kind = "bonus") {
    ensureAudio();
    if (!audioCtx || music) return;
    const bass = kind === "wheel" ? [48, 48, 55, 55, 51, 51, 53, 55] : [48, 48, 51, 51, 53, 53, 46, 50];
    const arp = kind === "wheel" ? [72, 75, 79, 82, 84, 82, 79, 75] : [67, 70, 72, 75, 77, 75, 72, 70];
    let step = 0;
    const tick = () => {
      if (silent()) { step++; return; }
      const s = step % 16;
      if (s % 2 === 0) tone(NOTE(bass[(step >> 1) % 8] - 12), 0.22, { type: "triangle", gain: 0.07, bus: musicBus });
      tone(NOTE(arp[(s + (step >> 4)) % 8]), 0.12, { type: "square", gain: 0.012, bus: musicBus });
      if (s % 4 === 0) noise(0.05, 0.03, 7000, { type: "highpass" });
      if (s % 8 === 4) noise(0.12, 0.04, 1800, { type: "bandpass" });
      step++;
    };
    music = setInterval(tick, 117);
  }
  function stopMusic() { if (music) clearInterval(music); music = null; }
  const sfx = {
    spin() { ensureAudio(); noise(0.2, 0.04, 2400, { type: "highpass" }); tone(180, 0.25, { type: "triangle", gain: 0.03, slideTo: 520 }); startSpinLoop(); },
    spinEnd() { stopSpinLoop(); },
    stop(col) { ensureAudio(); tone(85, 0.14, { type: "sine", gain: 0.14, slideTo: 55 }); noise(0.07, 0.07, 500); chime(980 + col * 110, 0.2, 0.02); },
    anticipate(n) { ensureAudio(); tone(NOTE(60 + n * 4), 0.9, { type: "sawtooth", gain: 0.018, slideTo: NOTE(72 + n * 4), attack: 0.3 }); tone(NOTE(48 + n * 4), 0.9, { type: "sine", gain: 0.04, attack: 0.3 }); },
    scatter(n) { ensureAudio(); const f = NOTE(76 + n * 3); chime(f, 0.7, 0.07); chime(f * 1.5, 0.5, 0.03, 0.08); },
    tease() { ensureAudio(); tone(330, 0.8, { type: "sawtooth", gain: 0.015, slideTo: 1320 }); },
    nearMiss() { ensureAudio(); tone(NOTE(76), 0.25, { type: "triangle", gain: 0.04 }); tone(NOTE(73), 0.4, { type: "triangle", gain: 0.04, delay: 0.18, slideTo: NOTE(68) }); },
    shatter(n = 6) {
      ensureAudio(); noise(0.35, 0.09, 4200, { type: "highpass" }); noise(0.12, 0.08, 1200, { type: "bandpass", q: 2 });
      for (let i = 0; i < Math.min(10, 3 + n); i++) tone(2000 + Math.random() * 4200, 0.12 + Math.random() * 0.25, { type: "sine", gain: 0.015 + Math.random() * 0.015, delay: Math.random() * 0.18 });
    },
    drop() { ensureAudio(); tone(140, 0.12, { type: "sine", gain: 0.08, slideTo: 70, delay: 0.1 }); noise(0.05, 0.04, 700, { delay: 0.1 }); },
    winScaled(x, cascade = 0) {
      ensureAudio(); const up = cascade * 2;
      if (x < 1) [72, 79].forEach((n, i) => chime(NOTE(n + up), 0.35, 0.045, i * 0.07));
      else if (x < 5) [72, 76, 79].forEach((n, i) => chime(NOTE(n + up), 0.45, 0.05, i * 0.08));
      else if (x < BIG_WIN_X) [72, 76, 79, 84, 88].forEach((n, i) => chime(NOTE(n + up), 0.55, 0.055, i * 0.08));
      else this.big();
    },
    win() { this.winScaled(2); },
    big() { ensureAudio(); [60, 64, 67, 72, 76, 79, 84].forEach((n, i) => { chime(NOTE(n), 0.8, 0.06, i * 0.1); tone(NOTE(n - 24), 0.3, { type: "triangle", gain: 0.05, delay: i * 0.1 }); }); },
    bonus() { ensureAudio(); for (let i = 0; i < 12; i++) chime(600 * Math.pow(2, i / 6), 0.5, 0.04, i * 0.06); },
    bonusSting() { ensureAudio(); [67, 71, 74, 79].forEach((n, i) => chime(NOTE(n), 0.6, 0.05, i * 0.07)); },
    jackpot() { ensureAudio(); for (let r = 0; r < 3; r++) [60, 67, 72, 79].forEach((n, i) => chime(NOTE(n), 0.9, 0.06, r * 0.5 + i * 0.09)); },
    multUp(n) { ensureAudio(); tone(NOTE(67 + Math.min(n, 24)), 0.3, { type: "square", gain: 0.03, slideTo: NOTE(79 + Math.min(n, 24)) }); },
    lose() { ensureAudio(); tone(196, 0.16, { type: "triangle", gain: 0.02 }); },
    tick() { ensureAudio(); chime(1760, 0.05, 0.016); },
    waysTick(k) { ensureAudio(); tone(600 + k * 900, 0.04, { type: "square", gain: 0.012 }); },
    wheelTick() { ensureAudio(); noise(0.03, 0.08, 3000, { type: "bandpass", q: 3 }); tone(1400, 0.03, { type: "square", gain: 0.015 }); },
    reveal(i) { ensureAudio(); chime(NOTE(72 + i * 2), 0.5, 0.06); noise(0.15, 0.05, 5000, { type: "highpass" }); },
    collect() { ensureAudio(); [79, 76, 72, 79, 84].forEach((n, i) => chime(NOTE(n), 0.4, 0.05, i * 0.09)); },
    click() { ensureAudio(); tone(880, 0.04, { type: "square", gain: 0.018 }); tone(1320, 0.03, { type: "sine", gain: 0.02, delay: 0.02 }); },
    card() { ensureAudio(); noise(0.12, 0.06, 3000); },
    levelUp() { ensureAudio(); [60, 64, 67, 72, 76, 79, 84, 88].forEach((n, i) => chime(NOTE(n), 0.5, 0.05, i * 0.06)); },
    chest() { ensureAudio(); noise(0.2, 0.06, 600, { type: "bandpass" }); [67, 74, 79, 86].forEach((n, i) => chime(NOTE(n), 0.45, 0.05, 0.08 + i * 0.07)); },
    streak() { ensureAudio(); [72, 76, 79, 84].forEach((n, i) => chime(NOTE(n), 0.35, 0.05, i * 0.06)); },
    trophy() { ensureAudio(); [67, 71, 74, 79, 86, 91].forEach((n, i) => chime(NOTE(n), 0.7, 0.06, i * 0.08)); tone(NOTE(43), 0.8, { type: "triangle", gain: 0.05 }); },
    coins() { ensureAudio(); for (let i = 0; i < 8; i++) tone(900 + Math.random() * 800, 0.08, { type: "square", gain: 0.02, delay: i * 0.05 }); },
  };

  // ---- Sparkles ----
  const canvas = $("#sparkle-canvas"), ctx = canvas.getContext("2d");
  let particles = [], raf = null;
  function resizeCanvas() { const dpr = window.devicePixelRatio || 1; canvas.width = innerWidth * dpr; canvas.height = innerHeight * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); }
  const COLORS = ["#ffffff", "#fff3b0", "#f3c441", "#c792ff", "#ff9fe0", "#8ff06b"];
  function addP(p) { particles.push(p); if (!raf) raf = requestAnimationFrame(tickP); }
  function burst(x, y, n = 24, colors = COLORS, power = 5) {
    n = pcount(n);
    for (let i = 0; i < n; i++) { const a = Math.random() * Math.PI * 2, v = (0.4 + Math.random()) * power; addP({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v - 2, life: 1, decay: 0.015 + Math.random() * 0.02, size: 2 + Math.random() * 4, color: colors[(Math.random() * colors.length) | 0], rot: Math.random() * 6 }); }
  }
  function shards(x, y, colors) {
    if (REDUCE) return;
    const n = pcount(14) || 0;
    for (let i = 0; i < n; i++) { const a = Math.random() * Math.PI * 2, v = 2 + Math.random() * 6; addP({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v - 3, life: 1, decay: 0.02 + Math.random() * 0.02, size: 3 + Math.random() * 6, color: colors[(Math.random() * colors.length) | 0], rot: Math.random() * 6, shard: true }); }
  }
  function burstAt(el, n) { if (!el || REDUCE) return; const r = el.getBoundingClientRect(); burst(r.left + r.width / 2, r.top + r.height / 2, n); }
  function rain(n = 120, colors = COLORS) {
    n = pcount(n);
    for (let i = 0; i < n; i++) addP({ x: Math.random() * innerWidth, y: -20 - Math.random() * innerHeight * 0.6, vx: (Math.random() - 0.5) * 1.5, vy: 2 + Math.random() * 3, life: 1, decay: 0.004 + Math.random() * 0.004, size: 3 + Math.random() * 5, color: colors[(Math.random() * colors.length) | 0], rot: Math.random() * 6 });
  }
  function coinBurst(n = 80, origin = null) {
    n = pcount(n);
    let ox = 0, oy = 0;
    if (origin) { const r = origin.getBoundingClientRect(); ox = r.left + r.width / 2; oy = r.top + r.height / 2; }
    for (let i = 0; i < n; i++) {
      addP({
        x: origin ? ox : Math.random() * innerWidth,
        y: origin ? oy : -20 - Math.random() * innerHeight * 0.35,
        vx: (Math.random() - 0.5) * (origin ? 8 : 1.6),
        vy: origin ? -3 - Math.random() * 6 : 2.2 + Math.random() * 3.5,
        life: 1, decay: 0.006 + Math.random() * 0.006,
        size: 5 + Math.random() * 5,
        color: ["#fff3b0", "#f3c441", "#fbe08a", "#ffd37a"][(Math.random() * 4) | 0],
        rot: Math.random() * 6, coin: true,
      });
    }
    if (n) sfx.coins();
  }
  function ambient() {
    // gentle twinkles around the cabinet to keep the machine "alive"
    if (REDUCE || document.hidden || particles.length > 160) return;
    const r = cabinetEl.getBoundingClientRect();
    for (let i = 0; i < 2; i++) {
      const edge = Math.random();
      const x = edge < 0.5 ? r.left + Math.random() * r.width : (Math.random() < 0.5 ? r.left - 10 + Math.random() * 30 : r.right - 20 + Math.random() * 30);
      const y = edge < 0.5 ? r.top + Math.random() * r.height * 0.35 : r.top + Math.random() * r.height;
      addP({ x, y, vx: (Math.random() - 0.5) * 0.3, vy: -0.2 - Math.random() * 0.4, g: -0.002, life: 1, decay: 0.006 + Math.random() * 0.008, size: 1.5 + Math.random() * 2.5, color: COLORS[(Math.random() * COLORS.length) | 0], rot: Math.random() * 6, twinkle: true });
    }
  }
  function tickP() {
    ctx.clearRect(0, 0, innerWidth, innerHeight);
    particles = particles.filter((p) => p.life > 0 && p.y < innerHeight + 40);
    for (const p of particles) {
      p.x += p.vx; p.y += p.vy; p.vy += p.g ?? 0.12; p.vx *= 0.99; p.life -= p.decay; p.rot += p.shard ? 0.25 : 0.1;
      ctx.save(); ctx.globalAlpha = Math.max(0, p.twinkle ? Math.sin(p.life * Math.PI) : p.life); ctx.translate(p.x, p.y); ctx.rotate(p.rot);
      ctx.fillStyle = p.color; ctx.shadowColor = p.color; ctx.shadowBlur = 8; const s = p.size;
      ctx.beginPath();
      if (p.coin) {
        ctx.ellipse(0, 0, s, s * 0.72, 0, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = "rgba(90,58,0,.55)"; ctx.lineWidth = 1; ctx.stroke();
        ctx.fillStyle = "rgba(90,58,0,.6)"; ctx.font = `bold ${Math.max(7, s)}px serif`;
        ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText("$", 0, 1);
      } else if (p.shard) { ctx.moveTo(0, -s); ctx.lineTo(s * 0.55, s * 0.2); ctx.lineTo(-s * 0.15, s * 0.8); ctx.lineTo(-s * 0.5, -s * 0.1); ctx.closePath(); ctx.fill(); }
      else { ctx.moveTo(0, -s); ctx.lineTo(s * 0.3, -s * 0.3); ctx.lineTo(s, 0); ctx.lineTo(s * 0.3, s * 0.3); ctx.lineTo(0, s); ctx.lineTo(-s * 0.3, s * 0.3); ctx.lineTo(-s, 0); ctx.lineTo(-s * 0.3, -s * 0.3); ctx.closePath(); ctx.fill(); }
      ctx.restore();
    }
    raf = particles.length ? requestAnimationFrame(tickP) : null;
    if (!raf) ctx.clearRect(0, 0, innerWidth, innerHeight);
  }

  // ---- Celebrations ----
  let celebrateResolve = null;
  function celebrate({ kind = "big", title, amountAud = null, sub = "", hold = 3400, tier = null }) {
    return new Promise((resolve) => {
      const inner = celebrateEl.querySelector(".celebrate-inner");
      inner.querySelector(".celebrate-art")?.remove();
      const art = document.createElement("div");
      art.className = "celebrate-art";
      art.innerHTML = kind === "bonus" ? `<img class="prism" src="${Gems.url("scatter")}" alt="" />` : kind === "pick" ? `<img class="prism" src="${Gems.url("amethyst")}" alt="" />` : `<div class="celebrate-tea"><img src="${TEA_IMG_BIG}" alt="Green Tea 1kg packet" /></div>`;
      inner.prepend(art);
      const cls = ["celebrate"];
      if (kind === "bonus" || kind === "pick") cls.push("bonus");
      if (kind === "jackpot") cls.push("jackpot", "cinematic");
      if (tier) cls.push(`tier-${tier}`);
      celebrateEl.className = cls.join(" ");
      $("#celebrate-title").textContent = title;
      $("#celebrate-sub").textContent = sub;
      const amtEl = $("#celebrate-amount");
      amtEl.textContent = amountAud == null ? "" : money(0);
      celebrateEl.hidden = false;
      const tea = ["#8ff06b", "#eaffd0", "#fff3b0", "#f3c441", "#ffffff"];
      const heavy = kind === "jackpot" || tier === "mega" || tier === "epic";
      shakeCabinet(heavy);
      if (kind === "bonus" || kind === "pick") { sfx.bonus(); rain(90); }
      else if (kind === "jackpot") { sfx.jackpot(); rain(240, tea); coinBurst(140); burst(innerWidth / 2, innerHeight * 0.42, 50, tea, 8); }
      else if (tier === "epic") { sfx.big(); rain(200, tea); coinBurst(150); }
      else if (tier === "mega") { sfx.big(); rain(160, tea); coinBurst(100); }
      else { sfx.big(); rain(140, tea); coinBurst(70); }
      let r = null;
      if (amountAud != null) {
        const t0 = performance.now(), dur = Math.min(hold * 0.7, 2400); let last = 0;
        const step = (t) => { const k = Math.min(1, (t - t0) / dur); amtEl.textContent = money(amountAud * (1 - Math.pow(1 - k, 3))); if (t - last > 90 && k < 1) { sfx.tick(); last = t; } if (k < 1) r = requestAnimationFrame(step); };
        r = requestAnimationFrame(step);
      }
      const done = () => { if (r) cancelAnimationFrame(r); if (amountAud != null) amtEl.textContent = money(amountAud); celebrateEl.hidden = true; clearTimeout(timer); celebrateResolve = null; resolve(); };
      const timer = setTimeout(done, auto.running || turbo || REDUCE ? Math.min(hold, 1800) : hold);
      celebrateResolve = done;
    });
  }
  const bigTitle = (x) => (x >= EPIC_WIN_X ? "GREEN TEA EPIC WIN!" : x >= MEGA_WIN_X ? "GREEN TEA MEGA WIN!" : "GREEN TEA BIG WIN!");
  const winTier = (x) => (x >= EPIC_WIN_X ? "epic" : x >= MEGA_WIN_X ? "mega" : "big");

  let stingResolve = null;
  function showSting({ kicker = "FEATURE", title, sub = "", mult = "", kind = "", hold = 2200 }) {
    return new Promise((resolve) => {
      const el = $("#sting");
      el.className = "sting" + (kind ? " " + kind : "");
      $("#sting-kicker").textContent = kicker;
      $("#sting-title").textContent = title;
      $("#sting-sub").textContent = sub;
      const m = $("#sting-mult");
      if (mult) { m.hidden = false; m.textContent = mult; } else m.hidden = true;
      el.hidden = false;
      sfx.bonusSting();
      if (!REDUCE) rain(kind === "outro" ? 70 : 50);
      const done = () => { el.hidden = true; clearTimeout(timer); stingResolve = null; resolve(); };
      const timer = setTimeout(done, auto.running || turbo || REDUCE ? Math.min(hold, 1200) : hold);
      stingResolve = done;
    });
  }
  function showLevelUp(lv) {
    const el = $("#level-up");
    $("#level-up-val").textContent = String(lv);
    el.hidden = false;
    sfx.levelUp();
    if (!REDUCE) { rain(80, ["#c792ff", "#fff3b0", "#ffffff", "#f3c441"]); burst(innerWidth / 2, innerHeight * 0.45, 40); }
    setTimeout(() => { el.hidden = true; }, REDUCE || turbo ? 900 : 1800);
  }

  function renderEngage() {
    const level = profile.level || engage.level || 1;
    const need = profile.xp_needed || xpNeeded(level);
    const have = profile.xp ?? engage.xp;
    const streak = profile.current_streak ?? engage.streak;
    const lvl = $("#xp-level"), lab = $("#xp-label"), fill = $("#xp-fill");
    if (!lvl) return;
    lvl.textContent = `LV ${level}`;
    lab.textContent = `${Math.floor(have)} / ${need}`;
    fill.style.width = `${Math.min(100, (have / Math.max(need, 1)) * 100)}%`;
    const st = $("#streak");
    if (streak >= 2) { st.hidden = false; $("#streak-val").textContent = String(streak); }
    else st.hidden = true;
    const nickEl = $("#profile-nick"); if (nickEl) nickEl.textContent = profile.nickname || "Hopper";
    const plvl = $("#profile-level"); if (plvl) plvl.textContent = `LV ${level}`;
    const dailyReady = !!bonuses.daily_available;
    const hourlyReady = !!bonuses.hourly_available;
    const dbtns = [$("#btn-daily"), $("#btn-daily-panel")].filter(Boolean);
    dbtns.forEach((btn) => {
      btn.classList.toggle("ready", dailyReady);
      btn.classList.toggle("claimed", !dailyReady);
      btn.disabled = !dailyReady || busy;
    });
    $("#daily-label").textContent = dailyReady ? "BONUS" : "CLAIMED";
    const hbtns = [$("#btn-hourly"), $("#btn-hourly-panel")].filter(Boolean);
    hbtns.forEach((btn) => {
      btn.classList.toggle("ready", hourlyReady);
      btn.classList.toggle("claimed", !hourlyReady);
      btn.disabled = !hourlyReady || busy;
    });
    const hlab = $("#hourly-label");
    if (hlab) hlab.textContent = hourlyReady ? "BONUS" : formatRemain(bonuses.hourly_seconds || 0);
  }
  function addXp(n) {
    if (!(n > 0)) return;
    engage.xp += n;
    let lastUp = 0;
    while (engage.xp >= xpNeeded(engage.level) && engage.level < 99) {
      engage.xp -= xpNeeded(engage.level);
      engage.level += 1;
      lastUp = engage.level;
    }
    saveEngage();
    const bar = $("#xp-bar");
    if (bar) { bar.classList.remove("level-flash"); void bar.offsetWidth; bar.classList.add("level-flash"); }
    renderEngage();
    if (lastUp) showLevelUp(lastUp);
  }
  function noteRound(totalWin, bet, bonus, big) {
    const streak = profile.current_streak || 0;
    if (streak >= 2) {
      if ([3, 5, 8, 10, 15, 20].includes(streak)) {
        toast(`${streak} WIN STREAK!`);
        sfx.streak();
        const st = $("#streak"); if (st) { st.classList.remove("pop"); void st.offsetWidth; st.classList.add("pop"); }
      }
    }
    renderEngage();
    const bar = $("#xp-bar");
    if (bar) { bar.classList.remove("level-flash"); void bar.offsetWidth; bar.classList.add("level-flash"); }
    if (prizeEvents.levelUp) showLevelUp(prizeEvents.levelUp);
    const unlocked = prizeEvents.newTrophies.splice(0);
    prizeEvents.levelUp = 0;
    if (unlocked.length) queueTrophyToasts(unlocked);
    renderPrizes();
  }
  function formatRemain(sec) {
    sec = Math.max(0, Math.round(sec || 0));
    const m = Math.floor(sec / 60), s = sec % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  }
  async function claimDaily() {
    if (!ready || busy || !bonuses.daily_available) return;
    ensureAudio();
    const btn = $("#btn-daily");
    if (btn) { btn.classList.add("opening"); btn.disabled = true; }
    sfx.chest();
    try {
      applySnapshot(await api("/api/bonus/daily", { method: "POST", body: "{}" }));
      render();
      if (!REDUCE && btn) { burstAt(btn, 36); coinBurst(40, btn); }
      toast(`Daily bonus: ${money(bonuses.daily_coins || 0)} credited`);
      addXp(20);
    } catch (e) {
      toast((e && e.message) || "Daily bonus unavailable", true);
    } finally {
      if (btn) setTimeout(() => btn.classList.remove("opening"), 600);
      renderEngage();
    }
  }
  async function claimHourly() {
    if (!ready || busy || !bonuses.hourly_available) return;
    ensureAudio();
    const btn = $("#btn-hourly");
    if (btn) { btn.classList.add("opening"); btn.disabled = true; }
    sfx.chest();
    try {
      applySnapshot(await api("/api/bonus/hourly", { method: "POST", body: "{}" }));
      render();
      if (!REDUCE && btn) { burstAt(btn, 28); coinBurst(24, btn); }
      toast(`Hourly bonus: ${money(bonuses.hourly_coins || 0)} credited`);
      addXp(8);
    } catch (e) {
      toast((e && e.message) || "Hourly bonus not ready yet", true);
    } finally {
      if (btn) setTimeout(() => btn.classList.remove("opening"), 600);
      renderEngage();
    }
  }
  let hourlyTick = null;
  function startHourlyTick() {
    if (hourlyTick) return;
    hourlyTick = setInterval(() => {
      if (bonuses.hourly_available) return;
      if (bonuses.hourly_seconds > 0) {
        bonuses.hourly_seconds = Math.max(0, bonuses.hourly_seconds - 1);
        if (bonuses.hourly_seconds === 0) bonuses.hourly_available = true;
        const hlab = $("#hourly-label");
        if (hlab) hlab.textContent = bonuses.hourly_available ? "BONUS" : formatRemain(bonuses.hourly_seconds);
        if (bonuses.hourly_available) renderEngage();
      }
    }, 1000);
  }

  // ---- Mini games (outcomes arrive with the spin; the server drew them) ----
  const miniModal = $("#modal-mini"), miniStage = $("#mini-stage"), miniBtn = $("#mini-btn"), miniTotal = $("#mini-total");
  const autoAdvance = () => auto.running;
  function miniWait(label, autoMs) {
    return new Promise((resolve) => {
      miniBtn.hidden = false; miniBtn.textContent = label; miniBtn.disabled = false;
      let t = null;
      const go = () => { clearTimeout(t); miniBtn.removeEventListener("click", go); miniBtn.hidden = true; resolve(); };
      miniBtn.addEventListener("click", go);
      if (autoAdvance()) t = setTimeout(go, turbo ? Math.min(autoMs, 700) : autoMs);
    });
  }
  function miniOpen(kind, badge, title, sub) {
    miniModal.className = `modal mini ${kind}`; miniModal.hidden = false;
    $("#mini-badge").textContent = badge; $("#mini-title").textContent = title; $("#mini-sub").textContent = sub;
    miniTotal.textContent = money(0); miniStage.innerHTML = ""; miniBtn.hidden = true;
    const card = $("#mini-card"); card.classList.remove("enter"); void card.offsetWidth; card.classList.add("enter");
  }
  function miniRoll(from, to, ms = 700) {
    return new Promise((res) => {
      const t0 = performance.now(); let last = 0;
      const step = (t) => { const k = Math.min(1, (t - t0) / ms); miniTotal.textContent = money(from + (to - from) * (1 - Math.pow(1 - k, 3))); if (t - last > 80 && k < 1) { sfx.tick(); last = t; } if (k < 1) requestAnimationFrame(step); else res(); };
      requestAnimationFrame(step);
    });
  }
  const PICK_GEMS = ["amethyst", "sapphire", "emerald", "ruby", "topaz", "citrine", "quartz"];
  async function playPick(g, bet) {
    miniOpen("pick", "MYSTERY BONUS", "CRYSTAL PICK", "A mystery crystal bonus! Pick crystals to reveal cash prizes — keep picking until you find COLLECT.");
    miniStage.innerHTML = `<div class="mini-intro">${["amethyst", "greentea", "sapphire"].map((id, i) => `<img style="animation-delay:${i * 0.2}s" class="${id === "greentea" ? "tea" : ""}" src="${Gems.url(id)}" alt="" />`).join("")}</div>`;
    sfx.bonusSting(); startMusic("bonus"); rain(60);
    await miniWait("START PICKING", 1300);
    $("#mini-sub").textContent = "Pick a crystal!";
    const grid = document.createElement("div"); grid.className = "pick-grid";
    const tiles = [];
    for (let i = 0; i < g.tiles; i++) {
      const b = document.createElement("button"); b.type = "button"; b.className = "pick-tile";
      b.style.animationDelay = `${(i % 4) * 0.15 + Math.floor(i / 4) * 0.1}s`;
      b.innerHTML = `<img src="${Gems.url(PICK_GEMS[i % PICK_GEMS.length])}" alt="" /><span class="face"></span>`;
      b.setAttribute("aria-label", `Crystal ${i + 1}`);
      grid.appendChild(b); tiles.push(b);
    }
    miniStage.innerHTML = ""; miniStage.appendChild(grid);
    let idx = 0, total = 0, locked = false;
    await new Promise((done) => {
      const pick = async (tile) => {
        if (locked || tile.classList.contains("revealed")) return;
        locked = true;
        const p = g.picks[idx++];
        tile.classList.add("revealed");
        const face = tile.querySelector(".face");
        if (p.collect) {
          face.innerHTML = "<b>COLLECT</b>"; tile.classList.add("collect");
          sfx.collect(); burstAt(tile, 30);
          $("#mini-sub").textContent = "COLLECT!";
          clearInterval(autoT); setTimeout(done, 700);
          return;
        }
        const amt = bet * p.prize_mult;
        face.innerHTML = `<b>${money(amt)}</b><small>${p.prize_mult}×</small>`;
        if (p.prize_mult >= 5) tile.classList.add("big");
        sfx.reveal(idx); burstAt(tile, p.prize_mult >= 5 ? 40 : 18);
        $("#mini-sub").textContent = idx === 1 ? "Nice! Pick another crystal" : `${idx} prizes found — keep going!`;
        await miniRoll(total, total + amt, 450); total += amt;
        locked = false;
      };
      tiles.forEach((t) => t.addEventListener("click", () => pick(t)));
      const autoT = autoAdvance() ? setInterval(() => { const left = tiles.filter((t) => !t.classList.contains("revealed")); if (left.length && !locked) pick(left[(Math.random() * left.length) | 0]); }, turbo ? 350 : 750) : null;
    });
    // show what was left behind
    const rest = tiles.filter((t) => !t.classList.contains("revealed"));
    rest.forEach((t, i) => {
      const d = g.decoys[i]; if (!d) return;
      setTimeout(() => { t.classList.add("revealed", "decoy"); t.querySelector(".face").innerHTML = d.collect ? "<b>COLLECT</b>" : `<b>${money(bet * d.prize_mult)}</b>`; }, i * 70);
    });
    await sleep(speed(700) + rest.length * 70);
    const paid = winOf(g) + jackpotOf(g);
    $("#mini-title").textContent = "CRYSTAL PICK COMPLETE";
    $("#mini-sub").textContent = `${g.picks.length - 1} prize${g.picks.length - 1 === 1 ? "" : "s"} found${g.limited ? " · TABLE LIMIT APPLIED" : ""}`;
    miniTotal.textContent = money(paid);
    miniModal.classList.add("summary"); sfx.winScaled(paid / bet); rain(50);
    await miniWait("COLLECT", 2200);
    stopMusic(); miniModal.hidden = true; miniModal.classList.remove("summary");
    return paid;
  }

  // Tea Wheel
  const WEDGE_COLORS = ["#5b21b6", "#7c2d92", "#4c1d95", "#9d174d", "#5b21b6", "#0e7490", "#6d28d9", "#b45309", "#4c1d95", "#7c2d92", "#5b21b6", "#15803d"];
  function wedgeLabel(w) { return w.type === "mult" ? `${w.value}×` : w.type === "free_spins" ? `${w.value} FS` : "JACKPOT"; }
  function wheelSvg(wedges) {
    const R = 140, n = wedges.length, seg = 360 / n;
    const pt = (a, r = R) => [Math.sin((a * Math.PI) / 180) * r, -Math.cos((a * Math.PI) / 180) * r].map((v) => v.toFixed(2)).join(",");
    const slices = wedges.map((w, i) => {
      const a0 = i * seg, a1 = a0 + seg, ac = a0 + seg / 2;
      const fill = WEDGE_COLORS[i % WEDGE_COLORS.length];
      const label = w.type === "jackpot"
        ? `<image href="${TEA_IMG}" x="-17" y="${-R * 0.9}" width="34" height="34" /><text y="${-R * 0.55}" class="wl jp">JACKPOT</text>`
        : `<text y="${-R * 0.7}" class="wl${w.value >= 10 || w.type === "free_spins" ? " hi" : ""}">${wedgeLabel(w)}</text>`;
      return `<path d="M0,0 L${pt(a0)} A${R},${R} 0 0 1 ${pt(a1)} Z" fill="${fill}" stroke="#f3c441" stroke-width="2"/><g transform="rotate(${ac})">${label}</g>`;
    }).join("");
    const bulbs = wedges.map((_, i) => `<circle cx="${pt(i * seg, R + 9).split(",")[0]}" cy="${pt(i * seg, R + 9).split(",")[1]}" r="4" class="bulb" style="animation-delay:${(i % 2) * 0.4}s"/>`).join("");
    return `<svg class="wheel-svg" viewBox="-160 -160 320 320" aria-label="Tea Wheel">
      <defs><radialGradient id="whub"><stop offset="0" stop-color="#fff3b0"/><stop offset="1" stop-color="#b8860b"/></radialGradient></defs>
      <circle r="${R + 16}" fill="#2a0a5c" stroke="#f3c441" stroke-width="5"/>${bulbs}
      <g id="wheel-rot">${slices}<circle r="${R}" fill="none" stroke="#fff3b0" stroke-width="3"/></g>
      <circle r="26" fill="url(#whub)" stroke="#7a4b00" stroke-width="3"/><clipPath id="hubclip"><circle r="19"/></clipPath><image href="${TEA_IMG}" x="-19" y="-19" width="38" height="38" clip-path="url(#hubclip)" preserveAspectRatio="xMidYMid slice"/>
      <path class="wheel-pointer" d="M0,${-R + 18} L-15,${-R - 22} L15,${-R - 22} Z" fill="#fff3b0" stroke="#7a4b00" stroke-width="3"/>
    </svg>`;
  }
  let wheelRot = 0;
  function spinWheelTo(target, ms, ease = (k) => 1 - Math.pow(1 - k, 4)) {
    const g = document.getElementById("wheel-rot"), pointer = miniStage.querySelector(".wheel-pointer");
    const from = wheelRot, seg = 360 / (MINIS.wheel_wedges.length || 12);
    return new Promise((res) => {
      const t0 = performance.now(); let lastSeg = Math.floor(from / seg);
      const step = (t) => {
        const k = Math.min(1, (t - t0) / ms), r = from + (target - from) * ease(k);
        g.setAttribute("transform", `rotate(${r.toFixed(2)})`);
        const sg = Math.floor(r / seg);
        if (sg !== lastSeg) { lastSeg = sg; sfx.wheelTick(); if (pointer) { pointer.classList.remove("flick"); void pointer.getBBox(); pointer.classList.add("flick"); } }
        if (k < 1) requestAnimationFrame(step); else { wheelRot = target; res(); }
      };
      requestAnimationFrame(step);
    });
  }
  const rotFor = (i, n, jitter = 0) => -((i + 0.5) * (360 / n) + jitter);
  async function playWheel(g, bet) {
    const wedges = g.wedges || MINIS.wheel_wedges, n = wedges.length, seg = 360 / n;
    miniOpen("wheel", "BONUS + WILD", "TEA WHEEL", "Spin the Tea Wheel for multipliers, free spins or the GREEN TEA JACKPOT!");
    wheelRot = 0;
    miniStage.innerHTML = `<div class="wheel-wrap">${wheelSvg(wedges)}</div>`;
    sfx.bonusSting(); startMusic("wheel"); rain(50);
    await miniWait("SPIN THE WHEEL", 1200);
    $("#mini-sub").textContent = "Round and round…";
    const first = g.near_miss ? wedges.findIndex((w) => w.type === "jackpot") : g.index;
    const jitter = g.near_miss ? (g.index === (first + 1) % n ? -seg * 0.32 : seg * 0.32) : (Math.random() - 0.5) * seg * 0.6;
    const base = rotFor(first, n, jitter);
    const turns = (turbo ? 3 : 6) * 360;
    let target = base; while (target < wheelRot + turns) target += 360;
    await spinWheelTo(target, turbo ? 2200 : 5200);
    if (g.near_miss) {
      $("#mini-sub").textContent = "JACKPOT…?"; sfx.anticipate(3);
      await sleep(speed(900));
      // ticks over to the neighbouring wedge
      let t2 = rotFor(g.index, n, 0); while (t2 - wheelRot > 180) t2 -= 360; while (wheelRot - t2 > 180) t2 += 360;
      await spinWheelTo(t2, 1100, (k) => (k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2));
      sfx.nearMiss();
    }
    const w = wedges[g.index];
    const paid = winOf(g) + jackpotOf(g);
    miniModal.classList.add("summary");
    if (g.jackpot) {
      $("#mini-title").textContent = "GREEN TEA JACKPOT!"; $("#mini-sub").textContent = `The wheel stopped on the jackpot — ${Number(JACKPOT_MULT).toLocaleString("en-US")}× your total bet!`;
      sfx.jackpot(); rain(200, ["#8ff06b", "#eaffd0", "#fff3b0", "#f3c441"]);
    } else if (w.type === "free_spins") {
      $("#mini-title").textContent = `${g.free_spins} FREE SPINS!`; $("#mini-sub").textContent = mode === "megaways" ? "Free spins with a multiplier that grows on every tumble" : `Free spins with every win ×${FEATURES.free_spin_mult}`;
      sfx.bonus(); rain(80);
    } else {
      $("#mini-title").textContent = `${g.prize_mult}× TOTAL BET`; $("#mini-sub").textContent = g.near_miss ? "So close to the jackpot!" : g.limited ? "TABLE LIMIT APPLIED" : "Tea Wheel prize";
      sfx.winScaled(g.prize_mult); burstAt(miniStage, 40);
    }
    await miniRoll(0, paid, paid > 0 ? 900 : 1);
    await miniWait(w.type === "free_spins" && !g.jackpot ? "PLAY FREE SPINS" : "COLLECT", 2200);
    stopMusic(); miniModal.hidden = true; miniModal.classList.remove("summary");
    if (g.jackpot) await celebrate({ kind: "jackpot", title: "GREEN TEA JACKPOT!", amountAud: jackpotOf(g), sub: `Tea Wheel jackpot — ${Number(JACKPOT_MULT).toLocaleString("en-US")}× your total bet!`, hold: 4500 });
    return paid;
  }

  // ---- Round ----
  function setBusy(on) {
    busy = on;
    btnSpin.classList.toggle("spinning", on && !auto.running);
    btnSpin.disabled = on && !auto.running;
    render();
  }
  async function presentClassic(step, ctx, label) {
    await animateGrid(step.grid);
    const w = winOf(step);
    let shown = ctx.shown;
    if (showAllWins(step) || w > 0) {
      flyWin(frameEl, w);
      sfx.winScaled(w / ctx.bet);
      const n = (step.line_wins || []).length;
      setMsg(`${label}${n ? `${n} WINNING LINE${n > 1 ? "S" : ""}` : "PRISM SCATTER"} · ${money(w)}${step.limited ? " · TABLE LIMIT" : ""}`);
      await rollUp(shown, shown + w, speed(Math.min(ctx.free ? 1400 : 3200, rollMs(w, ctx.bet))));
      shown += w; ctx.onShown(shown);
    }
    return shown;
  }
  async function playRound() {
    const bet = totalBet();
    if (totalCoins() < bet - 1e-9) { toast("Not enough coins — claim a free bonus or buy coins in the shop", true); if (!auto.running) openModal("shop"); return null; }
    ensureAudio();
    presentToken++;
    const token = presentToken;
    closeModal("gamble");
    gambleAud = 0;
    setBusy(true);
    clearLines(); clearHighlights(); mwMultEl.hidden = true;
    winMeter.textContent = money(0);
    setMsg("GOOD LUCK!");
    const body = mode === "megaways"
      ? { mode, bet_index: mwBetIdx }
      : { mode, lines: lines(), bet_per_line_index: bplIdx };
    let res;
    try {
      res = await api("/api/spin", { method: "POST", body: JSON.stringify(body) });
    } catch (err) {
      setBusy(false); toast(err.message || "Spin failed", true);
      if (/coins|shop|bonus/i.test(err.message || "") && !auto.running) openModal("shop");
      return null;
    }
    const totalWin = winOf(res);
    pendingWinAud = totalWin;
    applySnapshot(res);
    gambleAud = 0;
    render();
    const ctx = { bet, token, shown: 0, free: false, onShown: (v) => { pendingWinAud = Math.max(0, totalWin - v); render(); } };
    const base = res.base;
    const games = res.minigames || [];
    const isMw = res.mode === "megaways";
    const baseWin = winOf(base);
    if (isMw) await presentMw(base, ctx); else await presentClassic(base, ctx, "");
    let shown = baseWin;
    ctx.onShown(shown);
    winMeter.textContent = money(shown);
    if (baseWin > 0) {
      if (isMw) setMsg(`WIN ${money(baseWin)}${base.cascades ? ` · ${base.cascades} TUMBLE${base.cascades > 1 ? "S" : ""}` : ""}${base.limited ? " · TABLE LIMIT" : ""}`);
      else if ((base.line_wins || []).length > 1 && !auto.running && !(res.free_spins || []).length && !games.length) await cycleWins(base, token, false);
    } else {
      const trig = isMw ? 4 : 3;
      if (base.scatters === trig - 1 && !games.some((g) => g.kind === "wheel")) { setMsg(`SO CLOSE! ${base.scatters} BONUS — ${trig} TRIGGER FREE SPINS`, true); sfx.nearMiss(); }
      else { setMsg(isMw ? `${fmtWays(base.ways)} WAYS · NO WIN — SPIN AGAIN` : `${lines()} LINE${lines() > 1 ? "S" : ""} · NO WIN — SPIN AGAIN`, true); sfx.lose(); }
    }

    if (jackpotOf(base) > 0) {
      const sign = $("#jackpot-sign"); sign.classList.remove("hit"); void sign.offsetWidth; sign.classList.add("hit");
      await celebrate({ kind: "jackpot", title: "GREEN TEA JACKPOT!", amountAud: jackpotOf(base), sub: `You hit the Green Tea Jackpot — ${Number(JACKPOT_MULT).toLocaleString("en-US")}× your total bet!`, hold: 4800 });
      await rollUp(shown, shown + jackpotOf(base), 600);
      shown += jackpotOf(base); ctx.onShown(shown);
    }

    // mini games
    let wheelFs = 0;
    for (const g of games) {
      await sleep(speed(400));
      clearHighlights();
      await showSting({
        kicker: "MYSTERY BONUS",
        title: g.kind === "pick" ? "CRYSTAL PICK" : "TEA WHEEL",
        sub: g.kind === "pick" ? "Pick crystals for cash prizes — until COLLECT" : "Spin for multipliers, free spins or the jackpot",
        kind: "mini",
        hold: 1600,
      });
      const paid = g.kind === "pick" ? await playPick(g, bet) : await playWheel(g, bet);
      if (g.kind === "wheel") wheelFs += g.free_spins || 0;
      if (paid > 0) { await rollUp(shown, shown + paid, speed(700)); shown += paid; ctx.onShown(shown); setMsg(`${g.kind === "pick" ? "CRYSTAL PICK" : "TEA WHEEL"} · ${money(paid)}`); }
    }

    const fs = res.free_spins || [];
    if (fs.length) {
      await sleep(speed(400));
      const awarded = (base.free_spins_awarded || 0) + wheelFs;
      await showSting({
        kicker: "FREE SPINS",
        title: `${awarded} FREE SPINS`,
        sub: isMw ? "Unlimited win multiplier · +1 on every tumble" : `Same ${res.lines} lines · all wins ×${FEATURES.free_spin_mult}`,
        mult: isMw ? "×1" : `×${FEATURES.free_spin_mult}`,
        kind: "intro",
        hold: 2400,
      });
      cabinetEl.classList.add("in-bonus"); fsBanner.hidden = false;
      startMusic("bonus");
      let total = awarded, bonus = 0;
      if (isMw) setMult(fs[0].multiplier || 1, false); else $("#fs-mult").textContent = `ALL WINS ×${FEATURES.free_spin_mult}`;
      for (let i = 0; i < fs.length; i++) {
        $("#fs-count").textContent = `${i + 1} / ${total}`; $("#fs-total").textContent = money(bonus);
        setMsg(`FREE SPIN ${i + 1} OF ${total}`);
        const fctx = { ...ctx, free: true, shown };
        if (isMw) await presentMw(fs[i], fctx); else await presentClassic(fs[i], fctx, `FREE SPIN ${i + 1} · `);
        const w = winOf(fs[i]);
        if (w <= 0) setMsg(`FREE SPIN ${i + 1} · NO WIN`, true);
        else if (isMw) setMsg(`FREE SPIN ${i + 1} · ${money(w)}${fs[i].cascades ? ` · ${fs[i].cascades} TUMBLES` : ""} · ×${fs[i].multiplier_end}`);
        bonus += w; shown += w; ctx.onShown(shown); winMeter.textContent = money(shown);
        $("#fs-total").textContent = money(bonus);
        if (fs[i].free_spins_awarded > 0) { total += fs[i].free_spins_awarded; toast(`+${fs[i].free_spins_awarded} FREE SPINS!`); sfx.bonus(); }
        await sleep(speed(w > 0 ? 700 : 280));
      }
      stopMusic();
      cabinetEl.classList.remove("in-bonus"); fsBanner.hidden = true; mwMultEl.hidden = true;
      await showSting({
        kicker: "BONUS COMPLETE",
        title: money(bonus),
        sub: `${fs.length} free spins${isMw ? ` · multiplier reached ×${fs[fs.length - 1].multiplier_end}` : ""}`,
        mult: isMw ? `×${fs[fs.length - 1].multiplier_end}` : "",
        kind: "outro",
        hold: 2600,
      });
    }

    pendingWinAud = 0;
    winMeter.textContent = money(totalWin);
    const x = bet ? totalWin / bet : 0;
    if (x >= BIG_WIN_X && !field(res, "jackpot_paid", "jackpot_paid_aud")) {
      const tier = winTier(x);
      await celebrate({ kind: "big", tier, title: bigTitle(x), amountAud: totalWin, sub: `${Math.round(x)}× your total bet`, hold: tier === "epic" ? 4400 : tier === "mega" ? 4000 : 3400 });
    }
    if (totalWin > 0) setMsg(`TOTAL WIN ${money(totalWin)}${fs.length ? ` · ${fs.length} FREE SPINS` : ""}${games.length ? ` · ${games.map((g) => (g.kind === "pick" ? "PICK" : "WHEEL")).join(" + ")}` : ""}${field(res, "jackpot_paid", "jackpot_paid_aud") ? " · JACKPOT" : ""}${res.limited ? " · TABLE LIMIT APPLIED" : ""}${!auto.running ? " · GAMBLE OR SPIN" : ""}`);

    history.unshift({ t: Date.now(), bet, mode: isMw ? "MW" : "L", lines: res.lines, win: totalWin, fs: fs.length, jp: !!field(res, "jackpot_paid", "jackpot_paid_aud"), mini: games.map((g) => g.kind) });
    history = history.slice(0, 40); saveHistory(); renderHistory();
    gambleAud = auto.running ? 0 : field(res, "gamble", "gamble_aud");
    setBusy(false);
    const bonusHit = fs.length > 0 || games.length > 0;
    const bigHit = x >= BIG_WIN_X || !!field(res, "jackpot_paid", "jackpot_paid_aud");
    noteRound(totalWin, bet, bonusHit, bigHit);
    if (!isMw && totalWin > 0 && !auto.running && !fs.length && !games.length) cycleWins(base, presentToken, true);
    return { x, bonus: bonusHit, bigWin: bigHit };
  }
  async function spin() {
    if (!ready) return;
    if (celebrateResolve) { celebrateResolve(); return; }
    if (stingResolve) { stingResolve(); return; }
    if (auto.running) { stopAuto("Auto spin stopped"); return; }
    if (busy) return;
    await playRound();
  }

  function renderHistory() {
    const ul = $("#history");
    if (!history.length) { ul.innerHTML = '<li class="empty">No spins yet</li>'; return; }
    ul.innerHTML = history.map((h) => {
      const x = h.bet ? h.win / h.bet : 0;
      const cls = h.win <= 0 ? "lose" : x >= BIG_WIN_X ? "big" : "win";
      const tags = [h.mode === "MW" ? '<span class="tag mw">MW</span>' : h.lines ? `<span class="tag">${h.lines}L</span>` : "",
        h.fs ? `<span class="tag fs">${h.fs} FS</span>` : "", ...(h.mini || []).map((k) => `<span class="tag fs">${k === "pick" ? "PICK" : "WHEEL"}</span>`),
        h.jp ? '<span class="tag jp">JACKPOT</span>' : "", h.g ? `<span class="tag">GAMBLE ${h.g}</span>` : ""].join("");
      const t = new Date(h.t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      return `<li class="${cls}"><span class="t">${t}</span><span class="tags">${money(h.bet)} ${tags}</span><span class="amt">${h.win > 0 ? "+" + money(h.win) : "—"}</span></li>`;
    }).join("");
  }

  // ---- Gamble ----
  const SUIT = { hearts: "♥", diamonds: "♦", clubs: "♣", spades: "♠" };
  let gHistory = [];
  function openGamble() {
    if (!(gambleAud > 0) || busy || auto.running) return;
    presentToken++;
    gHistory = [];
    renderGamble("Pick a colour. Red or black — 50/50.");
    $("#g-card").classList.remove("flipped");
    openModal("gamble");
  }
  function renderGamble(msg) {
    if (gambleAud > 0) { $("#g-stake").textContent = money(gambleAud); $("#g-to").textContent = money(gambleAud * 2); }
    $("#g-msg").textContent = msg;
    $("#g-history").innerHTML = gHistory.map((c) => `<span class="${c.colour}">${SUIT[c.suit]}</span>`).join("");
    const can = gambleAud > 0;
    $("#g-red").disabled = !can; $("#g-black").disabled = !can;
    $("#g-collect").textContent = can ? `COLLECT ${money(gambleAud)}` : "CLOSE";
  }
  async function gambleChoose(choice) {
    $("#g-red").disabled = true; $("#g-black").disabled = true;
    const card = $("#g-card");
    card.classList.remove("flipped"); card.classList.add("shuffling");
    sfx.card();
    const [res] = await Promise.all([
      api("/api/gamble", { method: "POST", body: JSON.stringify({ choice }) }).catch((e) => ({ __err: e })),
      sleep(700),
    ]);
    card.classList.remove("shuffling");
    if (res.__err) {
      const e = res.__err;
      if (e.data && e.data.balances) applySnapshot(e.data);
      gambleAud = 0; render(); renderGamble(e.message || "Gamble unavailable");
      toast(e.message || "Gamble unavailable", true);
      return;
    }
    const c = res.card;
    const face = $("#g-face");
    face.className = `card-face ${c.colour}`;
    face.innerHTML = `<span class="r">${c.rank}<br>${SUIT[c.suit]}</span><span class="s">${SUIT[c.suit]}</span>`;
    card.classList.add("flipped");
    sfx.card();
    gHistory.push(c);
    await sleep(500);
    const stakeWas = field(res, "gamble_stake", "gamble_stake_aud");
    applySnapshot(res);
    gambleAud = res.gamble_aud || 0;
    render();
    if (res.won) {
      sfx.win(); burstAt(card, 40);
      const payout = field(res, "gamble_payout", "gamble_payout_aud");
      winMeter.textContent = moneyShort(payout);
      history.unshift({ t: Date.now(), bet: stakeWas, win: payout, g: "WIN" });
      renderGamble(gambleAud > 0 ? `${c.colour.toUpperCase()}! You won ${money(payout)}. Gamble again or collect.` : `${c.colour.toUpperCase()}! You won ${money(payout)} — max gambles reached, collected.`);
      setMsg(`GAMBLE WIN ${money(payout)}`);
    } else {
      sfx.lose();
      winMeter.textContent = money(0);
      history.unshift({ t: Date.now(), bet: stakeWas, win: 0, g: "LOSE" });
      renderGamble(`${c.colour.toUpperCase()} — gamble lost.`);
      setMsg("GAMBLE LOST", true);
      setTimeout(() => closeModal("gamble"), 1500);
    }
    saveHistory(); renderHistory();
  }
  async function gambleCollect() {
    if (gambleAud > 0) { try { applySnapshot(await api("/api/gamble/collect", { method: "POST", body: "{}" })); } catch { /* ignore */ } }
    gambleAud = 0; render(); closeModal("gamble");
  }

  // ---- Auto ----
  function updateAutoUI() {
    if (auto.running) {
      btnAuto.textContent = `STOP ${auto.remaining === Infinity ? "∞" : auto.remaining}`;
      btnAuto.classList.add("auto-on");
      btnSpin.querySelector("span").textContent = "STOP"; btnSpin.classList.add("stop-mode"); btnSpin.disabled = false;
      autoStatus.hidden = false;
      autoStatus.textContent = `AUTO SPIN ${auto.total === Infinity ? auto.played : `${auto.played} / ${auto.total}`}${turbo ? " · TURBO" : ""}`;
    } else {
      btnAuto.textContent = "AUTO"; btnAuto.classList.remove("auto-on");
      btnSpin.querySelector("span").textContent = "SPIN"; btnSpin.classList.remove("stop-mode");
      autoStatus.hidden = true;
    }
  }
  function stopAuto(reason) { if (!auto.running) return; auto.running = false; updateAutoUI(); render(); if (reason) toast(reason); }
  async function startAuto() {
    const n = autoCountChoice === "Infinity" ? Infinity : parseInt(autoCountChoice, 10) || 25;
    Object.assign(auto, { total: n, remaining: n, played: 0, stopBonus: $("#auto-stop-bonus").checked, stopBig: $("#auto-stop-bigwin").checked });
    const below = parseFloat($("#auto-stop-balance").value);
    auto.stopBelowAud = $("#auto-stop-balance-on").checked && below >= 0 ? Math.round(below) : null;
    turbo = $("#auto-turbo").checked; savePrefs();
    closeModal("auto");
    if (busy) return;
    if (gambleAud > 0) await gambleCollect();
    auto.running = true; updateAutoUI(); render();
    while (auto.running && auto.remaining > 0) {
      if (auto.stopBelowAud != null && totalCoins() < auto.stopBelowAud) { stopAuto(`Auto spin stopped: balance below ${money(auto.stopBelowAud)}`); break; }
      const r = await playRound();
      if (!r) { stopAuto("Auto spin stopped"); break; }
      auto.played++; if (auto.remaining !== Infinity) auto.remaining--;
      updateAutoUI();
      if (auto.stopBonus && r.bonus) { stopAuto("Auto spin stopped: bonus triggered"); break; }
      if (auto.stopBig && r.bigWin) { stopAuto("Auto spin stopped: big win"); break; }
      await sleep(turbo ? 150 : 600);
    }
    if (auto.running) stopAuto("Auto spin finished");
  }

  // ---- Info modal ----
  function renderInfo() {
    const isMw = mode === "megaways";
    const sp = FEATURES.scatter_pays || {}, msp = MW.scatter_pays || {};
    $("#tab-lines-btn").textContent = isMw ? "Megaways" : "Paylines";
    if (isMw) {
      const b = mwBet();
      $("#pays-hint").textContent = `MEGAWAYS pays for a ${money(b)} bet, per way. Win = pay × number of ways (matching symbols multiplied reel by reel).`;
      const order = Object.keys(MW.pays || {}).sort((a, c) => (MW.pays[c][6] || 0) - (MW.pays[a][6] || 0));
      $("#pay-grid").innerHTML = order.map((id) => `<div class="pay-item${id === "greentea" ? " top" : ""}"><img class="${id === "greentea" ? "tea" : ""}" src="${Gems.url(id)}" alt="" /><span><span class="nm">${symbolName(id)}</span>
        ${[6, 5, 4, 3].map((k) => `<span class="row">${k} × <b>${money(b * (MW.pays[id][k] || 0))}</b> <small>/way</small></span>`).join("")}</span></div>`).join("");
      $("#lines-hint").textContent = `6 reels land ${MW.min_rows}–${MW.max_rows} symbols every spin, plus a horizontal top reel above reels 2–5. Ways = symbols on reel 1 × reel 2 × … × reel 6 — up to ${fmtWays(MW.max_ways)} WAYS. Wins pay left to right on adjacent reels from reel 1.`;
      $("#lines-grid").classList.add("block");
      $("#lines-grid").innerHTML = `<div class="ways-demo">${[2, 7, 4, 7, 3, 6].map((n, c) => `<div class="wd-col">${hasTop(c) ? '<span class="t"></span>' : '<span class="t cap"></span>'}${Array.from({ length: n - (hasTop(c) ? 1 : 0) }, () => "<span></span>").join("")}<small>${n}</small></div>`).join("")}</div>
        <p class="hint center">Example: 2 × 7 × 4 × 7 × 3 × 6 = <b>${fmtWays(2 * 7 * 4 * 7 * 3 * 6)} WAYS</b></p>
        <p class="hint"><b>Tumbling reels:</b> winning symbols shatter like crystal and new ones drop in from above. Tumbles repeat until there is no new win — one paid spin can win again and again.</p>`;
    } else {
      const b = bpl();
      $("#pays-hint").textContent = `Pays shown for ${money(b)} per line (multiplier × bet per line). Scatter pays × total bet (${money(totalBet())}).`;
      const order = SYMBOLS.filter((s) => !s.scatter && !s.blank).sort((a, c) => (c.pays[5] || 0) - (a.pays[5] || 0));
      $("#pay-grid").innerHTML = order.map((s) => `<div class="pay-item${s.id === "greentea" ? " top" : ""}"><img class="${s.id === "greentea" ? "tea" : ""}" src="${Gems.url(s.id)}" alt="" /><span><span class="nm">${s.name}</span>
        ${[5, 4, 3].map((k) => `<span class="row">${k} × <b>${money(b * (s.pays[k] || 0))}</b> <small>(${s.pays[k]}×)</small></span>`).join("")}</span></div>`).join("");
      $("#lines-grid").classList.remove("block");
      $("#lines-hint").textContent = "Wins pay left to right on active lines, starting from reel 1. Only the highest win per line is paid.";
      $("#lines-grid").innerHTML = PAYLINES.map((p, i) => {
        const cells = [];
        for (let r = 0; r < 3; r++) for (let c = 0; c < 5; c++) cells.push(`<span class="${p[c] === r ? "on" : ""}"></span>`);
        return `<div class="mini-line" style="--lc:${lineColor(i + 1)}"><span style="color:${lineColor(i + 1)}">LINE ${i + 1}</span><div class="g">${cells.join("")}</div></div>`;
      }).join("");
    }
    $("#features").innerHTML = `
      <div class="feat"><img class="tea" src="${TEA_IMG}" alt="" /><div><b>Green Tea Jackpot.</b> Can drop on any paid spin in either mode, and can also land on the Tea Wheel. When it hits, it pays <b>${Number(JACKPOT_MULT).toLocaleString("en-US")}× your total bet</b>.</div></div>
      ${isMw ? `<div class="feat"><img src="${Gems.url("wild")}" alt="" /><div><b>Crystal Wild</b> lands on reels 2–5 (including the top reel) and substitutes for every gem except the BONUS scatter.</div></div>
      <div class="feat"><img src="${Gems.url("scatter")}" alt="" /><div><b>BONUS scatter</b> on the main reels: ${Object.keys(msp).map((k) => `${k}${k === "6" ? "+" : ""} pay ${msp[k].pay}× + ${msp[k].free_spins} free spins`).join(" · ")}. In free spins the <b>win multiplier starts at ×1 and rises by +1 on every tumble — with no upper limit</b> — and it never resets during the bonus. 3+ BONUS retrigger extra spins (max ${FEATURES.max_free_spins}).</div></div>`
        : `<div class="feat"><img src="${Gems.url("wild")}" alt="" /><div><b>Crystal Wild</b> lands on reels 2–4, substitutes for every gem except the Prism Scatter, and <b>doubles</b> any line win it completes.</div></div>
      <div class="feat"><img src="${Gems.url("scatter")}" alt="" /><div><b>Prism Scatter</b> pays anywhere: 3/4/5 pay ${Object.keys(sp).map((k) => sp[k].pay + "×").join(" / ")} total bet and award <b>${Object.keys(sp).map((k) => sp[k].free_spins).join(" / ")} free spins</b> with every win ×${FEATURES.free_spin_mult}. Free spins can retrigger (max ${FEATURES.max_free_spins}).</div></div>`}
      <div class="feat"><img src="${Gems.url("ruby")}" alt="" /><div><b>Gamble / Double up.</b> After any win, pick red or black. Guess right to double, wrong and the win is lost. Up to ${FEATURES.gamble_max_rounds} times in a row. The card is drawn on the server.</div></div>
      <div class="feat"><img src="${Gems.url("shard")}" alt="" /><div><b>Social casino · TEST MODE.</b> Malfunction voids all pays and plays. Coins have no cash value and cannot be redeemed for money or prizes.</div></div>`;
    const wedges = MINIS.wheel_wedges || [];
    $("#minis-info").innerHTML = `
      <div class="feat"><img src="${Gems.url("amethyst")}" alt="" /><div><b>Crystal Pick</b> — a <b>mystery bonus</b> that can start after any paid spin. Pick crystals from a grid of ${MINIS.pick_tiles}: each one reveals a coin prize (${(MINIS.pick_prizes || []).map((p) => p + "×").join(", ")} total bet) until you find a COLLECT crystal.</div></div>
      <div class="feat"><img class="tea" src="${TEA_IMG}" alt="" /><div><b>Tea Wheel</b> — land <b>${(MINIS.wheel_min_scatters || {})[mode] || 2}+ BONUS together with a WILD</b> (without triggering free spins) to spin the wheel: ${wedges.map(wedgeLabel).join(" · ")}. The Free Spins wedge starts a bonus; the JACKPOT wedge can award the Green Tea Jackpot.</div></div>
      <div class="feat"><img src="${Gems.url("ruby")}" alt="" /><div><b>Red / Black Gamble</b> — after any win, double up on a card colour (50/50), up to ${FEATURES.gamble_max_rounds} times.</div></div>
      <p class="hint">Every mini-game result is decided on the server the moment it triggers — your picks reveal it.</p>`;
  }

  // ---- Modals / shop / age gate ----
  function formatAudPrice(n) {
    return `A$${(Number(n) || 0).toFixed(2)}`;
  }

  function applyTheme(id) {
    const theme = id || "crystal";
    document.body.dataset.theme = theme === "crystal" ? "" : theme;
    if (!theme || theme === "crystal") document.body.removeAttribute("data-theme");
    else document.body.dataset.theme = theme;
  }
  let trophyQueue = Promise.resolve();
  function queueTrophyToasts(list) {
    list.forEach((t) => {
      trophyQueue = trophyQueue.then(() => showTrophyToast(t));
    });
  }
  function showTrophyToast(trophy) {
    return new Promise((resolve) => {
      const el = $("#trophy-toast");
      if (!el) { resolve(); return; }
      $("#trophy-toast-icon").textContent = trophy.icon || "🏆";
      $("#trophy-toast-title").textContent = trophy.name || "Trophy";
      $("#trophy-toast-sub").textContent = trophy.desc || "Cosmetic prize — no cash value";
      el.hidden = false;
      sfx.trophy();
      if (!REDUCE) { rain(70, ["#fff3b0", "#f3c441", "#c792ff", "#ffffff"]); burst(innerWidth / 2, innerHeight * 0.42, 36); }
      toast(`Trophy unlocked: ${trophy.name}`);
      setTimeout(() => { el.hidden = true; resolve(); }, REDUCE || turbo ? 1100 : 2200);
    });
  }
  function renderPrizes() {
    const legal = $("#prize-legal");
    if (legal) legal.textContent = prizeLegal;
    const nick = $("#nickname");
    if (nick && document.activeElement !== nick) nick.value = profile.nickname || "";
    const grid = $("#trophy-grid");
    if (grid) {
      const items = trophies.items && trophies.items.length
        ? trophies.items
        : [];
      grid.innerHTML = items.map((t) => `
        <article class="trophy-card ${t.unlocked ? "owned" : "locked"}">
          <div class="tico">${t.icon || "🏆"}</div>
          <h3>${t.name}</h3>
          <p>${t.desc}</p>
        </article>`).join("") || '<p class="hint">No trophies in the catalogue.</p>';
    }
    const list = $("#mission-list");
    if (list) {
      list.innerHTML = (missions || []).map((m) => {
        const pct = Math.min(100, Math.round((m.progress / Math.max(m.target, 1)) * 100));
        const reward = `${Number(m.reward_coins || 0).toLocaleString("en-US")} coins${m.reward_trophy ? " + badge" : ""}`;
        const btn = m.claimable
          ? `<button type="button" class="btn btn-gold" data-claim="${m.id}">Claim</button>`
          : m.claimed
            ? `<button type="button" class="btn" disabled>Claimed</button>`
            : `<button type="button" class="btn" disabled>In progress</button>`;
        return `<article class="mission-card">
          <header><h3>${m.title}</h3><span class="rew">${reward}</span></header>
          <div class="mission-track"><div class="mission-fill" style="width:${pct}%"></div></div>
          <div class="mission-meta"><span>${m.progress} / ${m.target}</span>${btn}</div>
        </article>`;
      }).join("") || '<p class="hint">Daily missions will appear here.</p>';
    }
    const tgrid = $("#theme-grid");
    if (tgrid) {
      tgrid.innerHTML = (themes || []).map((th) => {
        const lock = th.unlocked ? "Unlocked" : `Unlocks at level ${th.unlock_level}`;
        const sel = th.selected ? "selected" : "";
        return `<button type="button" class="theme-card ${sel}" data-theme="${th.id}" ${th.unlocked ? "" : "disabled"}>
          <div class="swatch"></div>
          <h3>${th.name}</h3>
          <p>${lock}${th.selected ? " · Selected" : ""}</p>
        </button>`;
      }).join("");
    }
  }
  async function loadLeaderboard() {
    const list = $("#leader-list");
    const me = $("#lb-me");
    if (!list) return;
    try {
      const data = await api(`/api/leaderboard?period=${encodeURIComponent(lbPeriod)}&board=${encodeURIComponent(lbBoard)}`);
      const rows = data.entries || [];
      list.innerHTML = rows.length
        ? rows.map((e) => `<li class="${e.me ? "me" : ""}"><span class="place">${e.place}</span><span class="name">${e.nickname}</span><span class="score">${money(e.score)}</span></li>`).join("")
        : '<li class="empty">No scores yet — spin to join the board.</li>';
      if (me) {
        const rewards = (data.rewards || []).map((r) => `#${r.place} ${Number(r.coins).toLocaleString("en-US")} coins`).join(" · ");
        const place = data.me && data.me.place ? `You are #${data.me.place} with ${money(data.me.score)}.` : "You are not on this board yet.";
        me.textContent = `${place} End-of-period rewards: ${rewards}. Coins only.`;
      }
    } catch (e) {
      list.innerHTML = `<li class="empty">${(e && e.message) || "Could not load leaderboard"}</li>`;
    }
  }
  async function saveNickname(ev) {
    if (ev) ev.preventDefault();
    const input = $("#nickname");
    try {
      applySnapshot(await api("/api/profile", { method: "POST", body: JSON.stringify({ nickname: (input && input.value) || "" }) }));
      render(); renderPrizes();
      toast("Nickname saved");
    } catch (e) {
      toast((e && e.message) || "Could not save nickname", true);
    }
  }
  async function chooseTheme(id) {
    try {
      applySnapshot(await api("/api/theme", { method: "POST", body: JSON.stringify({ theme: id }) }));
      render(); renderPrizes();
      toast(`Theme: ${(themes.find((t) => t.id === id) || {}).name || id}`);
    } catch (e) {
      toast((e && e.message) || "Theme is still locked", true);
    }
  }
  async function claimMission(id) {
    try {
      applySnapshot(await api("/api/missions/claim", { method: "POST", body: JSON.stringify({ mission_id: id }) }));
      render(); renderPrizes();
      toast(`Mission claimed: ${money(missions.find((m) => m.id === id)?.reward_coins || 0)}`);
      sfx.chest();
    } catch (e) {
      toast((e && e.message) || "Could not claim mission", true);
    }
  }

  function renderShop() {
    const grid = $("#pack-grid");
    if (!grid) return;
    const legalEl = $("#shop-legal"); if (legalEl) legalEl.textContent = LEGAL;
    const note = $("#shop-note");
    if (note) {
      note.textContent = stripeEnabled
        ? "Stripe Checkout in TEST MODE. Use test card 4242 4242 4242 4242 (any future expiry, any CVC). Coins have no cash value."
        : "Add a Stripe test key to enable the coin shop. You can still claim free daily and hourly coins.";
    }
    grid.innerHTML = PACKS.map((p) => {
      const tag = p.tag ? `<span class="pack-tag">${p.tag}</span>` : "";
      return `<button type="button" class="pack-card${p.tag ? " featured" : ""}" data-pack="${p.id}" ${stripeEnabled ? "" : "disabled"}>
        ${tag}
        <h3 class="pack-label">${p.label || "Coin pack"}</h3>
        <div class="pack-coins">${Number(p.coins || 0).toLocaleString("en-US")}</div>
        <div class="pack-unit">coins</div>
        <div class="pack-price">${formatAudPrice(p.price)}</div>
        <span class="pack-buy">Buy with Stripe</span>
      </button>`;
    }).join("");
  }
  async function buyPack(packId) {
    if (!stripeEnabled) return toast("Add a Stripe test key to enable the coin shop", true);
    try {
      const d = await api("/api/shop/checkout", { method: "POST", body: JSON.stringify({ pack_id: packId }) });
      if (!d || !d.url) throw new Error("Checkout did not return a URL");
      window.location.href = d.url;
    } catch (e) { toast((e && e.message) || "Shop checkout failed", true); }
  }
  function openModal(name) {
    const m = $(`#modal-${name}`); if (!m) return;
    m.hidden = false;
    if (name === "shop") renderShop();
    if (name === "prizes") { renderPrizes(); loadLeaderboard(); }
    if (name === "auto") { $("#auto-count").querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.count === autoCountChoice)); $("#auto-turbo").checked = turbo; }
    if (name === "info") renderInfo();
  }
  function closeModal(name) { const m = $(`#modal-${name}`); if (m) m.hidden = true; }
  function ageAccepted() {
    try { return localStorage.getItem(AGE_KEY) === "1"; } catch { return false; }
  }
  function acceptAge() {
    try { localStorage.setItem(AGE_KEY, "1"); } catch { /* ignore */ }
    closeModal("age");
    const blocked = $("#age-blocked"); if (blocked) blocked.hidden = true;
    document.body.classList.remove("age-blocked-on");
    startGame();
  }
  function declineAge() {
    closeModal("age");
    const blocked = $("#age-blocked"); if (blocked) blocked.hidden = false;
    document.body.classList.add("age-blocked-on");
    ready = false;
  }

  // ---- Events ----
  function setMode(m) {
    if (busy || auto.running || m === mode || !["megaways", "classic"].includes(m)) return;
    mode = m; gambleAud = 0; presentToken++; clearLines(); clearHighlights(); savePrefs(); render();
    requestAnimationFrame(() => { if (mode === "classic") layoutBadges(); else if (mwCols) { setMwBoard(mwCols); setWays(mwCols.reduce((p, c) => p * c.length, 1), true); } });
    sfx.bonusSting();
    setMsg(mode === "megaways" ? `MEGAWAYS · UP TO ${fmtWays(MW.max_ways)} WAYS · ${money(mwBet())}` : `${lines()} LINES × ${money(bpl())} = ${money(totalBet())}`);
  }
  function wire() {
    btnSpin.addEventListener("click", spin);
    btnAuto.addEventListener("click", () => { if (auto.running) return stopAuto("Auto spin stopped"); if (!busy) openModal("auto"); });
    btnTurbo.addEventListener("click", () => { turbo = !turbo; savePrefs(); render(); updateAutoUI(); });
    btnGamble.addEventListener("click", openGamble);
    $("#btn-info").addEventListener("click", () => openModal("info"));
    $("#mode-toggle").addEventListener("click", (e) => { const b = e.target.closest("button[data-mode]"); if (b) setMode(b.dataset.mode); });
    $("#btn-max").addEventListener("click", () => {
      if (busy || auto.running) return;
      if (mode === "megaways") mwBetIdx = MW.bet_aud.length - 1; else { lineIdx = LINE_OPTIONS.length - 1; bplIdx = BPL.length - 1; }
      savePrefs(); render(); sfx.big(); toast(`MAX BET ${money(totalBet())}`);
    });
    const step = (fn) => () => { if (busy || auto.running) return; fn(); savePrefs(); render(); presentToken++; clearLines(); clearHighlights(); if (mode === "classic") previewLines(); else setMsg(`BET ${money(mwBet())} · UP TO ${fmtWays(MW.max_ways)} WAYS`); };
    $("#lines-down").addEventListener("click", step(() => { lineIdx = Math.max(0, lineIdx - 1); }));
    $("#lines-up").addEventListener("click", step(() => { lineIdx = Math.min(LINE_OPTIONS.length - 1, lineIdx + 1); }));
    $("#bpl-down").addEventListener("click", step(() => { bplIdx = Math.max(0, bplIdx - 1); }));
    $("#bpl-up").addEventListener("click", step(() => { bplIdx = Math.min(BPL.length - 1, bplIdx + 1); }));
    $("#mwbet-down").addEventListener("click", step(() => { mwBetIdx = Math.max(0, mwBetIdx - 1); }));
    $("#mwbet-up").addEventListener("click", step(() => { mwBetIdx = Math.min(MW.bet_aud.length - 1, mwBetIdx + 1); }));
    document.querySelectorAll(".line-badges").forEach((el) => {
      el.addEventListener("mouseover", (e) => { const b = e.target.closest(".line-badge"); if (b && !busy) { clearLines(); drawLine(Number(b.dataset.line)); } });
      el.addEventListener("mouseout", () => { if (!busy) clearLines(); });
      el.addEventListener("click", (e) => { const b = e.target.closest(".line-badge"); if (b && !busy) { presentToken++; clearLines(); drawLine(Number(b.dataset.line)); setTimeout(clearLines, 1200); } });
    });
    // every button gets a soft click (spin has its own sound) plus a press flash
    document.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b || b.disabled) return;
      b.classList.remove("press"); void b.offsetWidth; b.classList.add("press");
      setTimeout(() => b.classList.remove("press"), 200);
      if (b !== btnSpin && !b.closest(".pick-grid")) sfx.click();
    }, true);
    $("#btn-daily").addEventListener("click", claimDaily);
    $("#sting").addEventListener("click", () => stingResolve && stingResolve());
    $("#g-red").addEventListener("click", () => gambleChoose("red"));
    $("#g-black").addEventListener("click", () => gambleChoose("black"));
    $("#g-collect").addEventListener("click", gambleCollect);
    $("#info-tabs").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-tab]"); if (!b) return;
      $("#info-tabs").querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
      document.querySelectorAll("#modal-info .tab").forEach((t) => { t.hidden = t.dataset.tab !== b.dataset.tab; });
    });
    $("#auto-count").addEventListener("click", (e) => { const b = e.target.closest("button[data-count]"); if (!b) return; autoCountChoice = b.dataset.count; $("#auto-count").querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b)); savePrefs(); });
    $("#auto-stop-balance").addEventListener("input", () => { $("#auto-stop-balance-on").checked = $("#auto-stop-balance").value !== ""; });
    $("#auto-start").addEventListener("click", startAuto);
    celebrateEl.addEventListener("click", () => celebrateResolve && celebrateResolve());
    btnMute.addEventListener("click", () => { muted = !muted; if (!muted && volume === 0) volume = 50; ensureAudio(); applyVolume(); savePrefs(); render(); if (!muted) chime(1046, 0.3, 0.05); });
    volEl.addEventListener("input", () => { volume = Number(volEl.value) || 0; muted = volume === 0; ensureAudio(); applyVolume(); savePrefs(); render(); });
    volEl.addEventListener("change", () => { if (!muted) chime(880, 0.25, 0.05); });
    const openShop = () => openModal("shop");
    const openPrizes = (tab) => {
      if (tab) {
        document.querySelectorAll("#prizes-tabs button").forEach((b) => b.classList.toggle("active", b.dataset.ptab === tab));
        document.querySelectorAll("#modal-prizes .ptab").forEach((s) => { s.hidden = s.dataset.ptab !== tab; });
      }
      openModal("prizes");
    };
    $("#btn-deposit").addEventListener("click", openShop);
    $("#btn-wallet").addEventListener("click", openShop);
    const bp = $("#btn-prizes"); if (bp) bp.addEventListener("click", () => openPrizes("trophies"));
    const bpp = $("#btn-prizes-panel"); if (bpp) bpp.addEventListener("click", () => openPrizes("trophies"));
    const ptabs = $("#prizes-tabs");
    if (ptabs) ptabs.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-ptab]"); if (!b) return;
      ptabs.querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
      document.querySelectorAll("#modal-prizes .ptab").forEach((s) => { s.hidden = s.dataset.ptab !== b.dataset.ptab; });
      if (b.dataset.ptab === "leaders") loadLeaderboard();
    });
    const nickForm = $("#nick-form"); if (nickForm) nickForm.addEventListener("submit", saveNickname);
    const mlist = $("#mission-list");
    if (mlist) mlist.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-claim]"); if (b) claimMission(b.dataset.claim);
    });
    const tgrid = $("#theme-grid");
    if (tgrid) tgrid.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-theme]"); if (b && !b.disabled) chooseTheme(b.dataset.theme);
    });
    const lp = $("#lb-period");
    if (lp) lp.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-period]"); if (!b) return;
      lbPeriod = b.dataset.period;
      lp.querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
      loadLeaderboard();
    });
    const lb = $("#lb-board");
    if (lb) lb.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-board]"); if (!b) return;
      lbBoard = b.dataset.board;
      lb.querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
      loadLeaderboard();
    });
    const packGrid = $("#pack-grid");
    if (packGrid) packGrid.addEventListener("click", (e) => {
      const card = e.target.closest("button[data-pack]");
      if (card && !card.disabled) buyPack(card.dataset.pack);
    });
    const hbtn = $("#btn-hourly"); if (hbtn) hbtn.addEventListener("click", claimHourly);
    const dp = $("#btn-daily-panel"); if (dp) dp.addEventListener("click", claimDaily);
    const hp = $("#btn-hourly-panel"); if (hp) hp.addEventListener("click", claimHourly);
    const ageYes = $("#age-yes"); if (ageYes) ageYes.addEventListener("click", acceptAge);
    const ageNo = $("#age-no"); if (ageNo) ageNo.addEventListener("click", declineAge);
    document.querySelectorAll("[data-close]").forEach((el) => el.addEventListener("click", () => closeModal(el.dataset.close)));
    document.addEventListener("keydown", (e) => {
      const tag = (e.target && e.target.tagName) || "";
      if (e.code === "Space" && !e.repeat) {
        if (["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(tag) || document.querySelector(".modal:not([hidden])") || !ageAccepted()) return;
        e.preventDefault(); spin();
      }
      if (e.key === "Escape") { ["shop", "auto", "info", "prizes"].forEach(closeModal); if (celebrateResolve) celebrateResolve(); if (stingResolve) stingResolve(); }
    });
    let rt = null;
    window.addEventListener("resize", () => { resizeCanvas(); clearTimeout(rt); rt = setTimeout(() => { layoutBadges(); clearLines(); if (!busy && mwCols) setMwBoard(mwCols); }, 120); });
    // unlock audio on first interaction (browsers block autoplay)
    const unlock = () => { ensureAudio(); window.removeEventListener("pointerdown", unlock); };
    window.addEventListener("pointerdown", unlock);
  }
  async function previewLines() {
    const tok = presentToken, n = lines();
    for (let i = 1; i <= n; i++) drawLine(i);
    setMsg(`${n} LINE${n > 1 ? "S" : ""} × ${money(bpl())} = ${money(totalBet())}`);
    await sleep(900);
    if (tok === presentToken && !busy) clearLines();
  }

  function decorate() {
    $("#brand-gem").src = Gems.url("ruby");
    const purple = Gems.decorCluster(282), blue = Gems.decorCluster(212);
    $("#marquee-crystals").innerHTML = `<img class="side" src="${blue}" alt="" /><img src="${purple}" alt="" /><img class="side" src="${blue}" alt="" />`;
    document.querySelectorAll(".side-crystals").forEach((el, i) => { el.style.backgroundImage = `url("${i ? blue : purple}"), url("${i ? purple : blue}")`; el.style.backgroundSize = "70%, 45%"; el.style.backgroundPosition = "left bottom, right bottom"; });
    spawnMotes();
  }
  function spawnMotes() {
    const box = $("#bg-float");
    if (!box) return;
    box.innerHTML = "";
    if (REDUCE) return;
    const n = isMobile() ? 8 : 16;
    for (let i = 0; i < n; i++) {
      const el = document.createElement("span");
      el.className = "mote" + (i % 3 === 0 ? " gold" : i % 5 === 0 ? " tea" : "");
      el.style.left = `${Math.random() * 100}%`;
      el.style.setProperty("--dur", `${12 + Math.random() * 14}s`);
      el.style.setProperty("--delay", `${(-Math.random() * 16).toFixed(2)}s`);
      el.style.setProperty("--dx", `${-60 + Math.random() * 120}px`);
      el.style.width = el.style.height = `${5 + Math.random() * 7}px`;
      box.appendChild(el);
    }
  }

  let started = false;
  async function startGame() {
    if (started) return;
    started = true;
    try {
      applySnapshot(await api("/api/balance"));
      initReels(); render(); initMw(); renderShop();
      requestAnimationFrame(() => { layoutBadges(); if (mwCols) setMwBoard(mwCols); });
    } catch { toast("Could not load the server ledger — is the Flask app running?", true); }
    startHourlyTick();
    renderEngage();
    setMsg(mode === "megaways" ? `MEGAWAYS · UP TO ${fmtWays(MW.max_ways)} WAYS` : "PLACE YOUR BET");
    ready = true;
  }
  async function boot() {
    resizeCanvas(); decorate(); initReels(); renderBadges(); render(); initMw(); renderHistory(); wire(); updateAutoUI();
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { layoutBadges(); if (mwCols && !busy) setMwBoard(mwCols); });
    if (REDUCE) document.documentElement.classList.add("reduce-motion");
    if (!REDUCE) setInterval(ambient, 420);
    if (!ageAccepted()) {
      ready = false;
      openModal("age");
      return;
    }
    await startGame();
  }
  boot();
})();
