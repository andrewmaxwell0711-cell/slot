/**
 * Crystal Casino · Crystal Reels — Demo / TEST MODE slot machine.
 * Every outcome (reels, line wins, free spins, jackpot, gamble card, payout
 * limits) is decided on the server. This file only animates the result.
 * Fiat deposits use Stripe test Checkout. Crypto is play money. Withdrawals are simulated.
 */
(() => {
  "use strict";

  const REELS = 5;
  const ROWS = 3;
  const TEA_IMG = "/assets/green-tea-256.webp";
  const TEA_IMG_BIG = "/assets/green-tea-512.webp";
  const BIG_WIN_X = 15, MEGA_WIN_X = 50, EPIC_WIN_X = 150;
  const HISTORY_KEY = "crystal-reels-history-v2";
  const PREFS_KEY = "crystal-reels-prefs-v2";
  const Gems = window.CrystalGems;
  const HI_SYMBOLS = new Set(["ruby", "greentea", "wild", "sapphire", "emerald"]);

  let SYMBOLS = [];
  let PAYLINES = [
    [1, 1, 1, 1, 1], [0, 0, 0, 0, 0], [2, 2, 2, 2, 2], [0, 1, 2, 1, 0], [2, 1, 0, 1, 2],
    [0, 0, 1, 2, 2], [2, 2, 1, 0, 0], [1, 0, 0, 0, 1], [1, 2, 2, 2, 1], [0, 1, 1, 1, 0],
    [2, 1, 1, 1, 2], [1, 0, 1, 2, 1], [1, 2, 1, 0, 1], [0, 1, 0, 1, 0], [2, 1, 2, 1, 2],
    [1, 1, 0, 1, 1], [1, 1, 2, 1, 1], [0, 0, 2, 0, 0], [2, 2, 0, 2, 2], [0, 2, 0, 2, 0],
    [2, 0, 2, 0, 2], [1, 0, 2, 0, 1], [1, 2, 0, 2, 1], [0, 2, 2, 2, 0], [2, 0, 0, 0, 2],
  ];
  let LINE_OPTIONS = [1, 5, 10, 20, 25];
  let BPL = [0.02, 0.05, 0.1, 0.2, 0.4, 1, 2, 4];
  let FEATURES = { wild_mult: 2, free_spin_mult: 2, max_free_spins: 50, gamble_max_rounds: 5,
    scatter_pays: { 3: { pay: 2, free_spins: 8 }, 4: { pay: 5, free_spins: 12 }, 5: { pay: 20, free_spins: 20 } } };
  let RATES_TO_AUD = { AUD: 1, USD: 1.52, EUR: 1.65, BTC: 145000, ETH: 5200, USDT: 1.52, SOL: 280 };
  const FIAT = ["AUD", "USD", "EUR"];
  const CRYPTO = ["BTC", "ETH", "USDT", "SOL"];
  const ALL_ASSETS = [...FIAT, ...CRYPTO];
  const lineColor = (n) => `hsl(${((n - 1) * 137.5) % 360}, 95%, 62%)`;

  // ---- State ----
  let prefs = loadPrefs();
  let balances = Object.fromEntries(ALL_ASSETS.map((a) => [a, 0]));
  let stats = { spins: 0, totalWonAud: 0, totalBetAud: 0 };
  let displayCurrency = prefs.displayCurrency || "AUD";
  let stripeEnabled = false;
  let busy = false;
  let ready = false;
  let muted = !!prefs.muted;
  let turbo = !!prefs.turbo;
  let lineIdx = prefs.lineIdx;
  let bplIdx = prefs.bplIdx;
  let pendingWinAud = 0;
  let gambleAud = 0;
  let history = loadHistory();
  let presentToken = 0;
  let autoCountChoice = prefs.autoCount || "25";
  const auto = { running: false, remaining: 0, total: 0, played: 0, stopBonus: true, stopBig: true, stopBelowAud: null };

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
  const toastEl = $("#toast");
  const celebrateEl = $("#celebrate");
  const autoStatus = $("#auto-status");
  const fsBanner = $("#fs-banner");

  // ---- Prefs & history ----
  function defaultPrefs() { return { displayCurrency: "AUD", lineIdx: 4, bplIdx: 0, muted: false, turbo: false, autoCount: "25" }; }
  function loadPrefs() { try { return { ...defaultPrefs(), ...JSON.parse(localStorage.getItem(PREFS_KEY) || "{}") }; } catch { return defaultPrefs(); } }
  function savePrefs() {
    prefs = { displayCurrency, lineIdx, bplIdx, muted, turbo, autoCount: autoCountChoice };
    try { localStorage.setItem(PREFS_KEY, JSON.stringify(prefs)); } catch { /* ignore */ }
  }
  function loadHistory() { try { const h = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"); return Array.isArray(h) ? h.slice(0, 40) : []; } catch { return []; } }
  function saveHistory() { try { localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, 40))); } catch { /* ignore */ } }

  // ---- Money ----
  const toAud = (a, x) => x * (RATES_TO_AUD[a] || 1);
  const fromAud = (a, x) => x / (RATES_TO_AUD[a] || 1);
  const totalAud = () => ALL_ASSETS.reduce((s, a) => s + toAud(a, balances[a] || 0), 0);
  function money(aud) {
    const cur = displayCurrency || "AUD";
    return new Intl.NumberFormat(undefined, { style: "currency", currency: cur, minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(fromAud(cur, aud || 0));
  }
  function formatAsset(asset, amount) {
    if (FIAT.includes(asset)) return new Intl.NumberFormat(undefined, { style: "currency", currency: asset, minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount);
    return `${Number(amount).toFixed(asset === "USDT" ? 2 : amount >= 1 ? 4 : 6)} ${asset}`;
  }
  const lines = () => LINE_OPTIONS[Math.min(lineIdx, LINE_OPTIONS.length - 1)];
  const bpl = () => BPL[Math.min(bplIdx, BPL.length - 1)];
  const totalBet = () => Math.round(lines() * bpl() * 100) / 100;
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
    if (s.balances) balances = { ...Object.fromEntries(ALL_ASSETS.map((a) => [a, 0])), ...s.balances };
    if (s.stats) stats = { spins: s.stats.spins || 0, totalWonAud: s.stats.total_won_aud || 0, totalBetAud: s.stats.total_bet_aud || 0 };
    if (s.display_currency) displayCurrency = s.display_currency;
    if (typeof s.gamble_aud === "number") gambleAud = s.gamble_aud;
    if (s.config) applyConfig(s.config);
  }
  function applyConfig(cfg) {
    stripeEnabled = !!cfg.stripe_enabled;
    $("#stripe-key-banner").hidden = stripeEnabled;
    if (cfg.rates_to_aud) RATES_TO_AUD = cfg.rates_to_aud;
    if (Array.isArray(cfg.line_options)) LINE_OPTIONS = cfg.line_options;
    if (Array.isArray(cfg.bet_per_line_aud)) BPL = cfg.bet_per_line_aud;
    if (Array.isArray(cfg.paylines)) PAYLINES = cfg.paylines;
    if (cfg.features) FEATURES = { ...FEATURES, ...cfg.features };
    if (Array.isArray(cfg.symbols)) SYMBOLS = cfg.symbols.map((s) => ({ ...s, pays: Object.fromEntries(Object.entries(s.pays || {}).map(([k, v]) => [Number(k), v])) }));
    lineIdx = Math.min(lineIdx, LINE_OPTIONS.length - 1);
    bplIdx = Math.min(bplIdx, BPL.length - 1);
    renderBadges();
  }

  // ---- Rendering ----
  function render() {
    const credit = Math.max(0, totalAud() - pendingWinAud);
    $("#credit").textContent = money(credit);
    $("#primary-balance").textContent = money(credit);
    $("#primary-currency-label").textContent = `Displayed in ${displayCurrency}`;
    $("#display-currency").value = displayCurrency;
    const list = $("#balance-list");
    list.innerHTML = "";
    ALL_ASSETS.forEach((a) => {
      const amt = balances[a] || 0;
      const row = document.createElement("div");
      row.className = "balance-row" + (amt === 0 ? " zero" : "");
      row.innerHTML = `<span class="code">${a}${CRYPTO.includes(a) ? '<span class="tag">play money</span>' : ""}</span><span class="amt">${formatAsset(a, amt)}</span>`;
      list.appendChild(row);
    });
    $("#lines-val").textContent = String(lines());
    $("#bpl-val").textContent = money(bpl());
    $("#total-bet").textContent = money(totalBet());
    $("#stat-spins").textContent = String(stats.spins);
    $("#stat-won").textContent = money(stats.totalWonAud);
    $("#stat-bet").textContent = money(stats.totalBetAud);
    btnMute.textContent = muted ? "🔇" : "🔊";
    btnTurbo.setAttribute("aria-pressed", String(turbo));
    const lock = busy || auto.running;
    ["#lines-down", "#lines-up", "#bpl-down", "#bpl-up", "#btn-max"].forEach((s) => { $(s).disabled = lock; });
    $("#lines-down").disabled = lock || lineIdx === 0;
    $("#lines-up").disabled = lock || lineIdx === LINE_OPTIONS.length - 1;
    $("#bpl-down").disabled = lock || bplIdx === 0;
    $("#bpl-up").disabled = lock || bplIdx === BPL.length - 1;
    btnGamble.disabled = !(gambleAud > 0) || lock;
    document.querySelectorAll(".line-badge").forEach((b) => b.classList.toggle("active", Number(b.dataset.line) <= lines()));
  }
  function setMsg(text, lose = false) { msgEl.textContent = text; winStrip.classList.toggle("lose", lose); }
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
    overlay.insertAdjacentHTML("beforeend", `<polyline class="ln-glow" points="${all}" stroke="${col}"/><polyline class="ln" points="${all}" stroke="${col}"/>`);
    document.querySelectorAll(`.line-badge[data-line="${n}"]`).forEach((b) => b.classList.add("win"));
  }
  function clearHighlights() {
    reelsEl.classList.remove("symbols-dim");
    reelsEl.querySelectorAll(".symbol.win, .symbol.scatter-hit").forEach((el) => { el.classList.remove("win", "scatter-hit"); el.style.removeProperty("--lc"); });
  }
  function cellEl(col, row) { const cells = reelsEl.children[col].querySelectorAll(".symbol"); return cells[cells.length - ROWS + row]; }
  function highlightWin(w) {
    w.cells.forEach(([c, r]) => { const el = cellEl(c, r); if (el) { el.classList.add("win"); el.style.setProperty("--lc", lineColor(w.line)); } });
  }

  // ---- Symbols / reels ----
  function makeCell(id) {
    const d = document.createElement("div");
    d.className = "symbol" + (HI_SYMBOLS.has(id) ? " hi" : "");
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
    sfx.spin();
    let scatters = 0, extra = 0;
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
      if (scatters >= 2 && !turbo) { extra += 700; reel.classList.add("anticipate"); }
      const dur = base + col * gap + extra;
      const colScat = grid[col].filter((id) => id === "scatter").length;
      scatters += colScat;
      void strip.offsetHeight;
      reel.classList.add("spinning");
      strip.style.transition = `transform ${dur}ms cubic-bezier(0.22, 0.9, 0.3, 1.08)`;
      strip.style.transform = "translateY(0)";
      if (reel.classList.contains("anticipate")) setTimeout(() => sfx.tease(), Math.max(0, dur - 800));
      return sleep(dur + 20).then(() => {
        reel.classList.remove("spinning", "anticipate");
        sfx.stop(col);
        while (strip.children.length > ROWS) strip.removeChild(strip.lastChild);
        strip.style.transition = "none"; strip.style.transform = "translateY(0)";
        if (colScat) { sfx.scatter(col); grid[col].forEach((id, row) => { if (id === "scatter") burstAt(cellEl(col, row), 14); }); }
      });
    }));
  }

  // ---- Presentation ----
  function describe(w, mult = 1) {
    return `LINE ${w.line} · ${w.count} × ${symbolName(w.symbol)}${w.wild ? " (WILD ×2)" : ""}${mult > 1 ? ` · ×${mult}` : ""} · ${money(w.win_aud)}`;
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
        setMsg(`${step.scatters} × PRISM SCATTER · ${money(step.scatter_win_aud)}`);
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
      if (toAudAmt <= fromAud || ms <= 0) { winMeter.textContent = money(toAudAmt); resolve(); return; }
      meter.classList.add("rolling");
      const t0 = performance.now(); let lastTick = 0;
      const step = (t) => {
        const k = Math.min(1, (t - t0) / ms);
        winMeter.textContent = money(fromAud + (toAudAmt - fromAud) * (1 - Math.pow(1 - k, 2)));
        if (t - lastTick > 70 && k < 1) { sfx.tick(); lastTick = t; }
        if (k < 1) rollRaf = requestAnimationFrame(step); else { meter.classList.remove("rolling"); resolve(); }
      };
      rollRaf = requestAnimationFrame(step);
    });
  }
  const rollMs = (win, bet) => Math.min(3200, 500 + 120 * Math.sqrt(Math.max(0, win / Math.max(bet, 0.01))) * 60 / 10);

  // ---- Sound (Web Audio) ----
  let audioCtx = null, master = null;
  function ensureAudio() {
    if (!audioCtx) { const AC = window.AudioContext || window.webkitAudioContext; if (!AC) return; audioCtx = new AC(); master = audioCtx.createGain(); master.gain.value = 0.5; master.connect(audioCtx.destination); }
    if (audioCtx.state === "suspended") audioCtx.resume();
  }
  function tone(freq, dur, { type = "sine", gain = 0.05, delay = 0, slideTo = null } = {}) {
    if (muted || !audioCtx) return;
    const t0 = audioCtx.currentTime + delay, o = audioCtx.createOscillator(), g = audioCtx.createGain();
    o.type = type; o.frequency.setValueAtTime(freq, t0);
    if (slideTo) o.frequency.exponentialRampToValueAtTime(slideTo, t0 + dur);
    g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(gain, t0 + 0.01); g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    o.connect(g); g.connect(master); o.start(t0); o.stop(t0 + dur + 0.02);
  }
  function noise(dur, gain = 0.05, freq = 900) {
    if (muted || !audioCtx) return;
    const n = audioCtx.sampleRate * dur, buf = audioCtx.createBuffer(1, n, audioCtx.sampleRate), d = buf.getChannelData(0);
    for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
    const src = audioCtx.createBufferSource(), f = audioCtx.createBiquadFilter(), g = audioCtx.createGain();
    src.buffer = buf; f.type = "lowpass"; f.frequency.value = freq; g.gain.value = gain;
    src.connect(f); f.connect(g); g.connect(master); src.start();
  }
  function chime(freq, dur = 0.5, gain = 0.05, delay = 0) { tone(freq, dur, { gain, delay }); tone(freq * 2.76, dur * 0.6, { gain: gain * 0.35, delay }); tone(freq * 5.4, dur * 0.3, { gain: gain * 0.12, delay }); }
  const sfx = {
    spin() { ensureAudio(); noise(0.35, 0.03, 1400); tone(180, 0.3, { type: "triangle", gain: 0.025, slideTo: 520 }); },
    stop(col) { ensureAudio(); tone(95, 0.12, { type: "triangle", gain: 0.09 }); noise(0.06, 0.05, 600); chime(980 + col * 120, 0.22, 0.025); },
    scatter(n) { ensureAudio(); chime(1320 + n * 160, 0.7, 0.06); },
    tease() { ensureAudio(); tone(330, 0.8, { type: "sawtooth", gain: 0.015, slideTo: 1320 }); },
    win() { ensureAudio(); [784, 988, 1175].forEach((f, i) => chime(f, 0.5, 0.05, i * 0.08)); },
    big() { ensureAudio(); [523, 659, 784, 1046, 1318, 1568].forEach((f, i) => chime(f, 0.8, 0.06, i * 0.11)); },
    bonus() { ensureAudio(); for (let i = 0; i < 12; i++) chime(600 * Math.pow(2, i / 6), 0.5, 0.04, i * 0.06); },
    jackpot() { ensureAudio(); for (let r = 0; r < 3; r++) [523, 784, 1046, 1568].forEach((f, i) => chime(f, 0.9, 0.06, r * 0.5 + i * 0.09)); },
    lose() { ensureAudio(); tone(196, 0.16, { type: "triangle", gain: 0.02 }); },
    tick() { ensureAudio(); chime(1760, 0.06, 0.018); },
    click() { ensureAudio(); tone(660, 0.05, { type: "square", gain: 0.02 }); },
    card() { ensureAudio(); noise(0.12, 0.06, 3000); },
  };

  // ---- Sparkles ----
  const canvas = $("#sparkle-canvas"), ctx = canvas.getContext("2d");
  let particles = [], raf = null;
  function resizeCanvas() { const dpr = window.devicePixelRatio || 1; canvas.width = innerWidth * dpr; canvas.height = innerHeight * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); }
  const COLORS = ["#ffffff", "#fff3b0", "#f3c441", "#c792ff", "#ff9fe0", "#8ff06b"];
  function addP(p) { particles.push(p); if (!raf) raf = requestAnimationFrame(tickP); }
  function burst(x, y, n = 24, colors = COLORS, power = 5) {
    for (let i = 0; i < n; i++) { const a = Math.random() * Math.PI * 2, v = (0.4 + Math.random()) * power; addP({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v - 2, life: 1, decay: 0.015 + Math.random() * 0.02, size: 2 + Math.random() * 4, color: colors[(Math.random() * colors.length) | 0], rot: Math.random() * 6 }); }
  }
  function burstAt(el, n) { if (!el) return; const r = el.getBoundingClientRect(); burst(r.left + r.width / 2, r.top + r.height / 2, n); }
  function rain(n = 120, colors = COLORS) {
    for (let i = 0; i < n; i++) addP({ x: Math.random() * innerWidth, y: -20 - Math.random() * innerHeight * 0.6, vx: (Math.random() - 0.5) * 1.5, vy: 2 + Math.random() * 3, life: 1, decay: 0.004 + Math.random() * 0.004, size: 3 + Math.random() * 5, color: colors[(Math.random() * colors.length) | 0], rot: Math.random() * 6 });
  }
  function tickP() {
    ctx.clearRect(0, 0, innerWidth, innerHeight);
    particles = particles.filter((p) => p.life > 0 && p.y < innerHeight + 40);
    for (const p of particles) {
      p.x += p.vx; p.y += p.vy; p.vy += 0.12; p.vx *= 0.99; p.life -= p.decay; p.rot += 0.1;
      ctx.save(); ctx.globalAlpha = Math.max(0, p.life); ctx.translate(p.x, p.y); ctx.rotate(p.rot);
      ctx.fillStyle = p.color; ctx.shadowColor = p.color; ctx.shadowBlur = 8; const s = p.size;
      ctx.beginPath(); ctx.moveTo(0, -s); ctx.lineTo(s * 0.3, -s * 0.3); ctx.lineTo(s, 0); ctx.lineTo(s * 0.3, s * 0.3); ctx.lineTo(0, s); ctx.lineTo(-s * 0.3, s * 0.3); ctx.lineTo(-s, 0); ctx.lineTo(-s * 0.3, -s * 0.3); ctx.closePath(); ctx.fill(); ctx.restore();
    }
    raf = particles.length ? requestAnimationFrame(tickP) : null;
    if (!raf) ctx.clearRect(0, 0, innerWidth, innerHeight);
  }

  // ---- Celebrations ----
  let celebrateResolve = null;
  function celebrate({ kind = "big", title, amountAud = null, sub = "", hold = 3400 }) {
    return new Promise((resolve) => {
      const inner = celebrateEl.querySelector(".celebrate-inner");
      inner.querySelector(".celebrate-art")?.remove();
      const art = document.createElement("div");
      art.className = "celebrate-art";
      art.innerHTML = kind === "bonus" ? `<img class="prism" src="${Gems.url("scatter")}" alt="" />` : `<div class="celebrate-tea"><img src="${TEA_IMG_BIG}" alt="Green Tea 1kg packet" /></div>`;
      inner.prepend(art);
      celebrateEl.className = "celebrate" + (kind === "bonus" ? " bonus" : "");
      $("#celebrate-title").textContent = title;
      $("#celebrate-sub").textContent = sub;
      const amtEl = $("#celebrate-amount");
      amtEl.textContent = amountAud == null ? "" : money(0);
      celebrateEl.hidden = false;
      const tea = ["#8ff06b", "#eaffd0", "#fff3b0", "#f3c441", "#ffffff"];
      if (kind === "bonus") { sfx.bonus(); rain(90); } else if (kind === "jackpot") { sfx.jackpot(); rain(240, tea); } else { sfx.big(); rain(160, tea); }
      let r = null;
      if (amountAud != null) {
        const t0 = performance.now(), dur = Math.min(hold * 0.7, 2400); let last = 0;
        const step = (t) => { const k = Math.min(1, (t - t0) / dur); amtEl.textContent = money(amountAud * (1 - Math.pow(1 - k, 3))); if (t - last > 90 && k < 1) { sfx.tick(); last = t; } if (k < 1) r = requestAnimationFrame(step); };
        r = requestAnimationFrame(step);
      }
      const done = () => { if (r) cancelAnimationFrame(r); if (amountAud != null) amtEl.textContent = money(amountAud); celebrateEl.hidden = true; clearTimeout(timer); celebrateResolve = null; resolve(); };
      const timer = setTimeout(done, auto.running || turbo ? Math.min(hold, 2200) : hold);
      celebrateResolve = done;
    });
  }
  const bigTitle = (x) => (x >= EPIC_WIN_X ? "GREEN TEA EPIC WIN!" : x >= MEGA_WIN_X ? "GREEN TEA MEGA WIN!" : "GREEN TEA BIG WIN!");

  // ---- Round ----
  function setBusy(on) {
    busy = on;
    btnSpin.classList.toggle("spinning", on && !auto.running);
    btnSpin.disabled = on && !auto.running;
    render();
  }
  async function playRound() {
    const bet = totalBet();
    if (totalAud() < bet - 1e-9) { toast("Insufficient test balance — deposit first", true); if (!auto.running) openModal("deposit"); return null; }
    ensureAudio();
    presentToken++;
    closeModal("gamble");
    gambleAud = 0;
    setBusy(true);
    winMeter.textContent = money(0);
    setMsg("GOOD LUCK!");
    let res;
    try {
      res = await api("/api/spin", { method: "POST", body: JSON.stringify({ lines: lines(), bet_per_line_index: bplIdx, display_currency: displayCurrency }) });
    } catch (err) {
      setBusy(false); toast(err.message || "Spin failed", true);
      if (/deposit/i.test(err.message || "") && !auto.running) openModal("deposit");
      return null;
    }
    const totalWin = res.win_aud || 0;
    pendingWinAud = totalWin;
    applySnapshot(res);
    gambleAud = 0;
    render();

    let shown = 0;
    const base = res.base;
    await animateGrid(base.grid);
    const baseWin = base.win_aud || 0;
    if (showAllWins(base) || baseWin > 0) {
      sfx.win();
      const n = (base.line_wins || []).length;
      setMsg(`${n ? `${n} WINNING LINE${n > 1 ? "S" : ""}` : "PRISM SCATTER"} · ${money(baseWin)}${base.limited ? " · TABLE LIMIT" : ""}`);
      await rollUp(0, baseWin, speed(rollMs(baseWin, bet)));
      shown = baseWin;
      pendingWinAud = Math.max(0, totalWin - shown); render();
      if (n > 1 && !auto.running && !(res.free_spins || []).length) await cycleWins(base, presentToken, false);
    } else {
      setMsg(`${lines()} LINE${lines() > 1 ? "S" : ""} · NO WIN — SPIN AGAIN`, true); sfx.lose();
    }

    if (res.jackpot_hit && res.jackpot_paid_aud > 0) {
      cabinetEl.classList.add("shake"); setTimeout(() => cabinetEl.classList.remove("shake"), 600);
      const sign = $("#jackpot-sign"); sign.classList.remove("hit"); void sign.offsetWidth; sign.classList.add("hit");
      await celebrate({ kind: "jackpot", title: "GREEN TEA JACKPOT!", amountAud: res.jackpot_paid_aud, sub: "You hit the Green Tea Jackpot — the table maximum!", hold: 4500 });
      await rollUp(shown, shown + res.jackpot_paid_aud, 600);
      shown += res.jackpot_paid_aud;
      pendingWinAud = Math.max(0, totalWin - shown); render();
    }

    const fs = res.free_spins || [];
    if (fs.length) {
      await sleep(speed(400));
      await celebrate({ kind: "bonus", title: `${base.free_spins_awarded} FREE SPINS`, sub: `Same ${res.lines} lines · all wins ×${FEATURES.free_spin_mult}`, hold: 2400 });
      cabinetEl.classList.add("in-bonus"); fsBanner.hidden = false;
      let total = base.free_spins_awarded, bonus = 0;
      for (let i = 0; i < fs.length; i++) {
        $("#fs-count").textContent = `${i + 1} / ${total}`; $("#fs-total").textContent = money(bonus);
        setMsg(`FREE SPIN ${i + 1} OF ${total}`);
        await animateGrid(fs[i].grid);
        const w = fs[i].win_aud || 0;
        if (showAllWins(fs[i]) || w > 0) {
          sfx.win();
          setMsg(`FREE SPIN ${i + 1} · ${(fs[i].line_wins || []).length} LINES · ${money(w)}`);
          await rollUp(shown, shown + w, speed(Math.min(1400, rollMs(w, bet))));
        } else { setMsg(`FREE SPIN ${i + 1} · NO WIN`, true); }
        bonus += w; shown += w;
        pendingWinAud = Math.max(0, totalWin - shown); render();
        $("#fs-total").textContent = money(bonus);
        if (fs[i].free_spins_awarded > 0) { total += fs[i].free_spins_awarded; toast(`+${fs[i].free_spins_awarded} FREE SPINS!`); sfx.bonus(); }
        await sleep(speed(w > 0 ? 800 : 300));
      }
      cabinetEl.classList.remove("in-bonus"); fsBanner.hidden = true;
      await celebrate({ kind: "bonus", title: "BONUS COMPLETE", amountAud: bonus, sub: `${fs.length} free spins`, hold: 2600 });
    }

    pendingWinAud = 0;
    winMeter.textContent = money(totalWin);
    const x = bet ? totalWin / bet : 0;
    if (x >= BIG_WIN_X && !res.jackpot_paid_aud) {
      await celebrate({ kind: "big", title: bigTitle(x), amountAud: totalWin, sub: `${Math.round(x)}× your total bet`, hold: 3600 });
    }
    if (totalWin > 0) setMsg(`TOTAL WIN ${money(totalWin)}${fs.length ? ` · ${fs.length} FREE SPINS` : ""}${res.jackpot_paid_aud ? " · JACKPOT" : ""}${res.limited ? " · TABLE LIMIT APPLIED" : ""}${!auto.running ? " · GAMBLE OR SPIN" : ""}`);

    history.unshift({ t: Date.now(), bet, lines: res.lines, win: totalWin, fs: fs.length, jp: !!res.jackpot_paid_aud });
    history = history.slice(0, 40); saveHistory(); renderHistory();
    gambleAud = auto.running ? 0 : res.gamble_aud || 0;
    setBusy(false);
    if (totalWin > 0 && !auto.running && !fs.length) cycleWins(base, presentToken, true);
    return { x, bonus: fs.length > 0, bigWin: x >= BIG_WIN_X || !!res.jackpot_paid_aud };
  }
  async function spin() {
    if (!ready) return;
    if (celebrateResolve) { celebrateResolve(); return; }
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
      const tags = [h.lines ? `<span class="tag">${h.lines}L</span>` : "", h.fs ? `<span class="tag fs">${h.fs} FS</span>` : "", h.jp ? '<span class="tag jp">JACKPOT</span>' : "", h.g ? `<span class="tag">GAMBLE ${h.g}</span>` : ""].join("");
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
    const stakeWas = res.gamble_stake_aud;
    applySnapshot(res);
    gambleAud = res.gamble_aud || 0;
    render();
    if (res.won) {
      sfx.win(); burstAt(card, 40);
      winMeter.textContent = money(res.gamble_payout_aud);
      history.unshift({ t: Date.now(), bet: stakeWas, win: res.gamble_payout_aud, g: "WIN" });
      renderGamble(gambleAud > 0 ? `${c.colour.toUpperCase()}! You won ${money(res.gamble_payout_aud)}. Gamble again or collect.` : `${c.colour.toUpperCase()}! You won ${money(res.gamble_payout_aud)} — max gambles reached, collected.`);
      setMsg(`GAMBLE WIN ${money(res.gamble_payout_aud)}`);
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
    auto.stopBelowAud = $("#auto-stop-balance-on").checked && below >= 0 ? toAud(displayCurrency, below) : null;
    turbo = $("#auto-turbo").checked; savePrefs();
    closeModal("auto");
    if (busy) return;
    if (gambleAud > 0) await gambleCollect();
    auto.running = true; updateAutoUI(); render();
    while (auto.running && auto.remaining > 0) {
      if (auto.stopBelowAud != null && totalAud() < auto.stopBelowAud) { stopAuto(`Auto spin stopped: balance below ${money(auto.stopBelowAud)}`); break; }
      const r = await playRound();
      if (!r) { stopAuto("Auto spin stopped"); break; }
      auto.played++; if (auto.remaining !== Infinity) auto.remaining--;
      updateAutoUI();
      if (auto.stopBonus && r.bonus) { stopAuto("Auto spin stopped: free spins won"); break; }
      if (auto.stopBig && r.bigWin) { stopAuto("Auto spin stopped: big win"); break; }
      await sleep(turbo ? 150 : 600);
    }
    if (auto.running) stopAuto("Auto spin finished");
  }

  // ---- Info modal ----
  function renderInfo() {
    const b = bpl();
    $("#pays-hint").textContent = `Pays shown for ${money(b)} per line (multiplier × bet per line). Scatter pays × total bet (${money(totalBet())}).`;
    const order = SYMBOLS.filter((s) => !s.scatter && !s.blank).sort((a, c) => (c.pays[5] || 0) - (a.pays[5] || 0));
    $("#pay-grid").innerHTML = order.map((s) => `<div class="pay-item${s.id === "greentea" ? " top" : ""}"><img class="${s.id === "greentea" ? "tea" : ""}" src="${Gems.url(s.id)}" alt="" /><span><span class="nm">${s.name}</span>
      ${[5, 4, 3].map((k) => `<span class="row">${k} × <b>${money(b * (s.pays[k] || 0))}</b> <small>(${s.pays[k]}×)</small></span>`).join("")}</span></div>`).join("");
    $("#lines-grid").innerHTML = PAYLINES.map((p, i) => {
      const cells = [];
      for (let r = 0; r < 3; r++) for (let c = 0; c < 5; c++) cells.push(`<span class="${p[c] === r ? "on" : ""}"></span>`);
      return `<div class="mini-line" style="--lc:${lineColor(i + 1)}"><span style="color:${lineColor(i + 1)}">LINE ${i + 1}</span><div class="g">${cells.join("")}</div></div>`;
    }).join("");
    const sp = FEATURES.scatter_pays || {};
    $("#features").innerHTML = `
      <div class="feat"><img class="tea" src="${TEA_IMG}" alt="" /><div><b>Green Tea Jackpot.</b> Can drop on any paid spin — bigger total bets have better odds. When it hits, the spin pays the table maximum.</div></div>
      <div class="feat"><img src="${Gems.url("wild")}" alt="" /><div><b>Crystal Wild</b> lands on reels 2–4, substitutes for every gem except the Prism Scatter, and <b>doubles</b> any line win it completes. 5 Wilds on a line pay 1000× line bet.</div></div>
      <div class="feat"><img src="${Gems.url("scatter")}" alt="" /><div><b>Prism Scatter</b> pays anywhere: 3/4/5 pay ${Object.keys(sp).map((k) => sp[k].pay + "×").join(" / ")} total bet and award <b>${Object.keys(sp).map((k) => sp[k].free_spins).join(" / ")} free spins</b>, played on the same lines with every win ×${FEATURES.free_spin_mult}. Free spins can retrigger (max ${FEATURES.max_free_spins}).</div></div>
      <div class="feat"><img src="${Gems.url("ruby")}" alt="" /><div><b>Gamble / Double up.</b> After any win, pick red or black. Guess right to double, wrong and the win is lost. Up to ${FEATURES.gamble_max_rounds} times in a row. The card is drawn on the server.</div></div>
      <div class="feat"><img src="${Gems.url("shard")}" alt="" /><div><b>Table limit.</b> Each spin's total win is limited to the table maximum. Lines pay left to right from reel 1, highest win per line. Malfunction voids all pays and plays. Demo / test mode only.</div></div>`;
  }

  // ---- Modals / wallet ----
  const depositType = () => ($("#deposit-type button.active") || {}).dataset?.type || "fiat";
  function fillAssetSelect(sel, type) { sel.innerHTML = (type === "crypto" ? CRYPTO : FIAT).map((a) => `<option value="${a}">${a}</option>`).join(""); }
  function updateDepositButton() {
    const btn = $("#confirm-deposit"), note = $("#deposit-note");
    if (depositType() === "crypto") { btn.disabled = false; btn.textContent = "Add play-money credit"; note.textContent = "Play money only — no real crypto is transferred or withdrawn."; }
    else if (stripeEnabled) { btn.disabled = false; btn.textContent = "Pay with Stripe (test mode)"; note.textContent = "Stripe Checkout in TEST MODE. Use test card 4242 4242 4242 4242 (any future expiry, any CVC). Real-money play needs a gambling licence plus Stripe approval."; }
    else { btn.disabled = true; btn.textContent = "Checkout unavailable"; note.textContent = "Add a Stripe test key to enable checkout"; }
  }
  function openModal(name) {
    const m = $(`#modal-${name}`); if (!m) return;
    m.hidden = false;
    if (name === "deposit") { fillAssetSelect($("#deposit-asset"), "fiat"); $("#deposit-type").querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.type === "fiat")); $("#deposit-amount").value = ""; updateDepositHint(); }
    if (name === "withdraw") { fillAssetSelect($("#withdraw-asset"), "fiat"); $("#withdraw-type").querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.type === "fiat")); $("#withdraw-amount").value = ""; $("#withdraw-processing").hidden = true; $("#withdraw-success").hidden = true; $("#confirm-withdraw").hidden = false; updateWithdrawHint(); }
    if (name === "auto") { $("#auto-count").querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.count === autoCountChoice)); $("#auto-turbo").checked = turbo; }
    if (name === "info") renderInfo();
  }
  function closeModal(name) { const m = $(`#modal-${name}`); if (m) m.hidden = true; }
  function updateDepositHint() {
    const a = $("#deposit-asset").value, amt = parseFloat($("#deposit-amount").value) || 0, rate = RATES_TO_AUD[a];
    $("#deposit-hint").textContent = amt > 0 ? `≈ ${money(toAud(a, amt))} play value · demo rate 1 ${a} ≈ ${rate} AUD` : `Demo rate: 1 ${a} ≈ ${rate} AUD`;
    updateDepositButton();
  }
  function updateWithdrawHint() {
    const a = $("#withdraw-asset").value, bal = balances[a] || 0, amt = parseFloat($("#withdraw-amount").value) || 0;
    $("#withdraw-available").textContent = `Available: ${formatAsset(a, bal)}${CRYPTO.includes(a) ? " (play money)" : ""}`;
    $("#withdraw-hint").textContent = amt > 0 ? `≈ ${money(toAud(a, amt))} will be debited from the test ledger (simulated, no real payout)` : "Withdrawals are simulated only — the ledger is debited and marked “test withdrawal recorded”.";
  }
  async function confirmDeposit() {
    const type = depositType(), asset = $("#deposit-asset").value, amount = parseFloat($("#deposit-amount").value);
    if (!amount || amount <= 0) return toast("Enter a valid amount", true);
    const btn = $("#confirm-deposit"); btn.disabled = true;
    try {
      if (type === "crypto") {
        applySnapshot(await api("/api/deposit/play", { method: "POST", body: JSON.stringify({ asset, amount }) }));
        render(); closeModal("deposit"); toast(`Added ${formatAsset(asset, amount)} play money`); sfx.win();
      } else {
        if (!stripeEnabled) return toast("Add a Stripe test key to enable checkout", true);
        const d = await api("/api/deposit/checkout", { method: "POST", body: JSON.stringify({ currency: asset, amount }) });
        if (!d || !d.url) throw new Error("Checkout did not return a URL");
        window.location.href = d.url; return;
      }
    } catch (e) { toast(e.message || "Deposit failed", true); } finally { updateDepositButton(); }
  }
  async function confirmWithdraw() {
    const asset = $("#withdraw-asset").value, amount = parseFloat($("#withdraw-amount").value), bal = balances[asset] || 0;
    if (!amount || amount <= 0) return toast("Enter a valid amount", true);
    if (amount > bal + 1e-12) return toast("Amount exceeds available balance", true);
    const btn = $("#confirm-withdraw"); btn.hidden = true; $("#withdraw-processing").hidden = false;
    try {
      const s = await api("/api/withdraw", { method: "POST", body: JSON.stringify({ asset, amount }) });
      applySnapshot(s); render();
      $("#withdraw-processing").hidden = true; $("#withdraw-success").hidden = false;
      toast(`${formatAsset(asset, amount)} — ${(s.withdrawal && s.withdrawal.status) || "test withdrawal recorded"}`);
      setTimeout(() => closeModal("withdraw"), 1400);
    } catch (e) { $("#withdraw-processing").hidden = true; btn.hidden = false; toast(e.message || "Withdrawal failed", true); }
  }

  // ---- Events ----
  function wire() {
    btnSpin.addEventListener("click", spin);
    btnAuto.addEventListener("click", () => { if (auto.running) return stopAuto("Auto spin stopped"); if (!busy) openModal("auto"); });
    btnTurbo.addEventListener("click", () => { turbo = !turbo; savePrefs(); render(); updateAutoUI(); sfx.click(); });
    btnGamble.addEventListener("click", openGamble);
    $("#btn-info").addEventListener("click", () => openModal("info"));
    $("#btn-max").addEventListener("click", () => { if (busy || auto.running) return; lineIdx = LINE_OPTIONS.length - 1; bplIdx = BPL.length - 1; savePrefs(); render(); sfx.big(); toast(`MAX BET ${money(totalBet())}`); });
    const step = (fn) => () => { if (busy || auto.running) return; fn(); savePrefs(); render(); sfx.click(); presentToken++; clearLines(); clearHighlights(); previewLines(); };
    $("#lines-down").addEventListener("click", step(() => { lineIdx = Math.max(0, lineIdx - 1); }));
    $("#lines-up").addEventListener("click", step(() => { lineIdx = Math.min(LINE_OPTIONS.length - 1, lineIdx + 1); }));
    $("#bpl-down").addEventListener("click", step(() => { bplIdx = Math.max(0, bplIdx - 1); }));
    $("#bpl-up").addEventListener("click", step(() => { bplIdx = Math.min(BPL.length - 1, bplIdx + 1); }));
    document.querySelectorAll(".line-badges").forEach((el) => {
      el.addEventListener("mouseover", (e) => { const b = e.target.closest(".line-badge"); if (b && !busy) { clearLines(); drawLine(Number(b.dataset.line)); } });
      el.addEventListener("mouseout", () => { if (!busy) clearLines(); });
      el.addEventListener("click", (e) => { const b = e.target.closest(".line-badge"); if (b && !busy) { presentToken++; clearLines(); drawLine(Number(b.dataset.line)); setTimeout(clearLines, 1200); } });
    });
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
    btnMute.addEventListener("click", () => { muted = !muted; savePrefs(); render(); if (!muted) { ensureAudio(); chime(1046, 0.3, 0.05); } });
    $("#btn-deposit").addEventListener("click", () => openModal("deposit"));
    $("#btn-withdraw").addEventListener("click", () => openModal("withdraw"));
    $("#btn-wallet").addEventListener("click", () => openModal("deposit"));
    $("#display-currency").addEventListener("change", async (e) => {
      const prev = displayCurrency; displayCurrency = e.target.value; savePrefs(); render(); renderHistory();
      try { applySnapshot(await api("/api/prefs", { method: "POST", body: JSON.stringify({ display_currency: displayCurrency }) })); render(); }
      catch (err) { displayCurrency = prev; savePrefs(); render(); renderHistory(); toast(err.message || "Could not update display currency", true); }
    });
    document.querySelectorAll("[data-close]").forEach((el) => el.addEventListener("click", () => closeModal(el.dataset.close)));
    ["deposit", "withdraw"].forEach((k) => {
      $(`#${k}-type`).addEventListener("click", (e) => {
        const b = e.target.closest("button[data-type]"); if (!b) return;
        $(`#${k}-type`).querySelectorAll("button").forEach((x) => x.classList.remove("active")); b.classList.add("active");
        fillAssetSelect($(`#${k}-asset`), b.dataset.type); (k === "deposit" ? updateDepositHint : updateWithdrawHint)();
      });
    });
    $("#deposit-asset").addEventListener("change", updateDepositHint);
    $("#deposit-amount").addEventListener("input", updateDepositHint);
    $("#withdraw-asset").addEventListener("change", updateWithdrawHint);
    $("#withdraw-amount").addEventListener("input", updateWithdrawHint);
    $("#confirm-deposit").addEventListener("click", confirmDeposit);
    $("#confirm-withdraw").addEventListener("click", confirmWithdraw);
    document.addEventListener("keydown", (e) => {
      const tag = (e.target && e.target.tagName) || "";
      if (e.code === "Space" && !e.repeat) {
        if (["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(tag) || document.querySelector(".modal:not([hidden])")) return;
        e.preventDefault(); spin();
      }
      if (e.key === "Escape") { ["deposit", "withdraw", "auto", "info"].forEach(closeModal); if (celebrateResolve) celebrateResolve(); }
    });
    let rt = null;
    window.addEventListener("resize", () => { resizeCanvas(); clearTimeout(rt); rt = setTimeout(() => { layoutBadges(); clearLines(); }, 120); });
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
  }

  async function boot() {
    resizeCanvas(); decorate(); initReels(); renderBadges(); render(); renderHistory(); wire(); updateAutoUI();
    try {
      applySnapshot(await api("/api/balance"));
      initReels(); render();
      requestAnimationFrame(layoutBadges);
    } catch { toast("Could not load the server ledger — is the Flask app running?", true); }
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(layoutBadges);
    ready = true;
  }
  boot();
})();
