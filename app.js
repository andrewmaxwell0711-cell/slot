/**
 * Crystal Reels — Demo / TEST MODE slot machine.
 * Every outcome (reels, wins, free spins, jackpot, the 20%-of-pool cap) is
 * decided on the server. This file only animates what the server returns.
 * Fiat deposits use Stripe test Checkout. Crypto is play money. Withdrawals are simulated.
 */

(() => {
  "use strict";

  const REEL_COUNT = 5;
  const VISIBLE_ROWS = 3;
  const TEA_IMG = "/assets/green-tea-256.webp";
  const TEA_IMG_BIG = "/assets/green-tea-512.webp";
  const BIG_WIN_X = 15;
  const MEGA_WIN_X = 50;
  const EPIC_WIN_X = 150;
  const HISTORY_KEY = "crystal-reels-history-v1";
  const PREFS_KEY = "crystal-reels-prefs-v1";

  const symH = () => {
    const v = getComputedStyle(document.documentElement).getPropertyValue("--sym-h");
    return parseFloat(v) || 92;
  };

  // Visual mapping for each server symbol id.
  const GEMS = {
    quartz: { cut: "heart", grad: "quartz" },
    citrine: { cut: "trillion", grad: "citrine" },
    topaz: { cut: "oval", grad: "topaz" },
    amethyst: { cut: "hex", grad: "amethyst" },
    emerald: { cut: "octagon", grad: "emerald" },
    sapphire: { cut: "oval", grad: "sapphire" },
    ruby: { cut: "brilliant", grad: "ruby" },
    greentea: { img: true },
    wild: { cut: "wild" },
    scatter: { cut: "prism" },
    shard: { cut: "shard" },
  };

  let SYMBOLS = [
    { id: "quartz", name: "Rose Quartz", pays: { 3: 4, 4: 10, 5: 20 } },
    { id: "citrine", name: "Citrine", pays: { 3: 4, 4: 10, 5: 20 } },
    { id: "topaz", name: "Topaz", pays: { 3: 6, 4: 16, 5: 40 } },
    { id: "amethyst", name: "Amethyst", pays: { 3: 6, 4: 16, 5: 50 } },
    { id: "emerald", name: "Emerald", pays: { 3: 10, 4: 30, 5: 80 } },
    { id: "sapphire", name: "Sapphire", pays: { 3: 15, 4: 50, 5: 100 } },
    { id: "ruby", name: "Ruby", pays: { 3: 25, 4: 80, 5: 200 } },
    { id: "greentea", name: "Green Tea", pays: { 3: 50, 4: 150, 5: 500 } },
    { id: "wild", name: "Crystal Wild", pays: { 3: 50, 4: 150, 5: 1000 }, wild: true },
    { id: "scatter", name: "Prism Scatter", pays: {}, scatter: true },
    { id: "shard", name: "Ice Shard", pays: {}, blank: true },
  ];
  let FEATURES = {
    wild_mult: 2,
    free_spin_mult: 2,
    scatter_pays: { 3: { pay: 2, free_spins: 8 }, 4: { pay: 5, free_spins: 12 }, 5: { pay: 20, free_spins: 20 } },
    pool_cap_fraction: 0.2,
  };
  let RATES_TO_AUD = { AUD: 1, USD: 1.52, EUR: 1.65, BTC: 145000, ETH: 5200, USDT: 1.52, SOL: 280 };
  const FIAT = ["AUD", "USD", "EUR"];
  const CRYPTO = ["BTC", "ETH", "USDT", "SOL"];
  const ALL_ASSETS = [...FIAT, ...CRYPTO];
  let BET_STEPS_AUD = [0.5, 1, 2, 5, 10, 20, 50, 100];

  // ---- State ----
  let prefs = loadPrefs();
  let balances = Object.fromEntries(ALL_ASSETS.map((a) => [a, 0]));
  let stats = { spins: 0, totalWonAud: 0, totalBetAud: 0 };
  let lastWinAud = 0;
  let pendingWinAud = 0; // credited server-side but not yet "revealed" by the animation
  let displayCurrency = prefs.displayCurrency || "AUD";
  let stripeEnabled = false;
  let busy = false;
  let ready = false;
  let muted = !!prefs.muted;
  let turbo = !!prefs.turbo;
  let betIndex = prefs.betIndex;
  let pool = { pool_aud: 0, max_win_aud: 0, jackpot_aud: 0 };
  let history = loadHistory();
  const auto = { running: false, remaining: 0, total: 0, stopBonus: true, stopBig: true, stopBelowAud: null };
  let autoCountChoice = prefs.autoCount || "25";

  // ---- DOM ----
  const $ = (sel) => document.querySelector(sel);
  const reelsEl = $("#reels");
  const machineEl = $("#machine");
  const balanceListEl = $("#balance-list");
  const primaryBalanceEl = $("#primary-balance");
  const primaryCurrencyLabel = $("#primary-currency-label");
  const betAmountEl = $("#bet-amount");
  const lastWinEl = $("#last-win");
  const resultBanner = $("#result-banner");
  const resultText = $("#result-text");
  const btnSpin = $("#btn-spin");
  const btnAuto = $("#btn-auto");
  const btnTurbo = $("#btn-turbo");
  const btnMute = $("#btn-mute");
  const toastEl = $("#toast");
  const payGrid = $("#pay-grid");
  const featureGrid = $("#feature-grid");
  const displayCurrencySel = $("#display-currency");
  const stripeKeyBanner = $("#stripe-key-banner");
  const fsBanner = $("#fs-banner");
  const autoStatus = $("#auto-status");
  const celebrateEl = $("#celebrate");

  // ---- Prefs / history ----
  function defaultPrefs() {
    return { displayCurrency: "AUD", betIndex: 1, muted: false, turbo: false, autoCount: "25" };
  }
  function loadPrefs() {
    try {
      return { ...defaultPrefs(), ...JSON.parse(localStorage.getItem(PREFS_KEY) || "{}") };
    } catch {
      return defaultPrefs();
    }
  }
  function savePrefs() {
    prefs = { displayCurrency, betIndex, muted, turbo, autoCount: autoCountChoice };
    try { localStorage.setItem(PREFS_KEY, JSON.stringify(prefs)); } catch { /* ignore */ }
  }
  function loadHistory() {
    try {
      const h = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
      return Array.isArray(h) ? h.slice(0, 30) : [];
    } catch {
      return [];
    }
  }
  function saveHistory() {
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, 30))); } catch { /* ignore */ }
  }

  // ---- Server sync ----
  function applySnapshot(snap) {
    if (!snap) return;
    if (snap.balances) balances = { ...Object.fromEntries(ALL_ASSETS.map((a) => [a, 0])), ...snap.balances };
    if (snap.stats) {
      stats = {
        spins: snap.stats.spins || 0,
        totalWonAud: snap.stats.total_won_aud || 0,
        totalBetAud: snap.stats.total_bet_aud || 0,
      };
    }
    if (typeof snap.last_win_aud === "number") lastWinAud = snap.last_win_aud;
    if (snap.display_currency) displayCurrency = snap.display_currency;
    if (snap.config) applyConfig(snap.config);
    if (snap.pool) applyPool(snap.pool);
  }

  function applyConfig(cfg) {
    stripeEnabled = !!cfg.stripe_enabled;
    if (stripeKeyBanner) stripeKeyBanner.hidden = stripeEnabled;
    if (cfg.rates_to_aud) RATES_TO_AUD = cfg.rates_to_aud;
    if (Array.isArray(cfg.bet_steps_aud) && cfg.bet_steps_aud.length) {
      BET_STEPS_AUD = cfg.bet_steps_aud;
      if (betIndex >= BET_STEPS_AUD.length) betIndex = BET_STEPS_AUD.length - 1;
    }
    if (cfg.features) FEATURES = { ...FEATURES, ...cfg.features };
    if (Array.isArray(cfg.symbols) && cfg.symbols.length) {
      SYMBOLS = cfg.symbols.map((s) => ({
        ...s,
        pays: Object.fromEntries(Object.entries(s.pays || {}).map(([k, v]) => [Number(k), v])),
      }));
    }
    renderPaytable();
  }

  function applyPool(p) {
    if (!p) return;
    const jpChanged = Math.abs((p.jackpot_aud || 0) - (pool.jackpot_aud || 0)) > 0.004;
    const maxChanged = Math.abs((p.max_win_aud || 0) - (pool.max_win_aud || 0)) > 0.004;
    pool = { ...pool, ...p };
    renderPool(jpChanged, maxChanged);
  }

  async function api(path, options = {}) {
    const opts = {
      credentials: "same-origin",
      headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) },
      ...options,
    };
    const res = await fetch(path, opts);
    let data = null;
    try { data = await res.json(); } catch { data = null; }
    if (!res.ok) {
      const err = new Error((data && data.error) || `Request failed (${res.status})`);
      err.status = res.status;
      throw err;
    }
    return data;
  }

  async function refreshBalance() {
    const snap = await api("/api/balance");
    applySnapshot(snap);
    renderBalances();
    return snap;
  }

  async function refreshPool() {
    if (busy || document.hidden) return;
    try { applyPool(await api("/api/pool")); } catch { /* offline: ignore */ }
  }

  // ---- Formatting ----
  const toAud = (asset, amount) => amount * (RATES_TO_AUD[asset] || 1);
  const fromAud = (asset, aud) => aud / (RATES_TO_AUD[asset] || 1);
  const totalAud = () => ALL_ASSETS.reduce((sum, a) => sum + toAud(a, balances[a] || 0), 0);

  function formatAsset(asset, amount) {
    if (FIAT.includes(asset)) {
      return new Intl.NumberFormat(undefined, { style: "currency", currency: asset, minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount);
    }
    const digits = asset === "USDT" ? 2 : amount >= 1 ? 4 : 6;
    return `${Number(amount).toFixed(digits)} ${asset}`;
  }
  function money(aud) {
    const cur = displayCurrency || "AUD";
    return new Intl.NumberFormat(undefined, { style: "currency", currency: cur, minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(fromAud(cur, aud || 0));
  }
  const currentBetAud = () => BET_STEPS_AUD[Math.min(betIndex, BET_STEPS_AUD.length - 1)];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const speed = (ms) => (turbo ? Math.round(ms * 0.35) : ms);

  // ---- Rendering ----
  function symbolHTML(id) {
    const g = GEMS[id] || GEMS.shard;
    if (g.img) return `<span class="tea-coin"><img src="${TEA_IMG}" alt="Green Tea" draggable="false" /></span>`;
    const fill = g.grad ? ` fill="url(#g-${g.grad})"` : "";
    return `<svg viewBox="0 0 100 100" aria-hidden="true"><use href="#cut-${g.cut}"${fill}/></svg>`;
  }
  function makeCell(id) {
    const cell = document.createElement("div");
    cell.className = "symbol";
    cell.dataset.id = id;
    cell.innerHTML = symbolHTML(id);
    return cell;
  }
  const symbolName = (id) => (SYMBOLS.find((s) => s.id === id) || {}).name || id;

  function renderBalances() {
    primaryBalanceEl.textContent = money(Math.max(0, totalAud() - pendingWinAud));
    primaryCurrencyLabel.textContent = `Displayed in ${displayCurrency}`;
    displayCurrencySel.value = displayCurrency;
    balanceListEl.innerHTML = "";
    ALL_ASSETS.forEach((asset) => {
      const amt = balances[asset] || 0;
      const row = document.createElement("div");
      row.className = "balance-row" + (amt === 0 ? " zero" : "");
      const tag = CRYPTO.includes(asset) ? '<span class="tag">play money</span>' : "";
      row.innerHTML = `<span class="code">${asset}${tag}</span><span class="amt">${formatAsset(asset, amt)}</span>`;
      balanceListEl.appendChild(row);
    });
    betAmountEl.textContent = money(currentBetAud());
    lastWinEl.textContent = money(lastWinAud || 0);
    $("#stat-spins").textContent = String(stats.spins || 0);
    $("#stat-won").textContent = money(stats.totalWonAud || 0);
    $("#stat-bet").textContent = money(stats.totalBetAud || 0);
    btnMute.textContent = muted ? "🔇" : "🔊";
    btnTurbo.setAttribute("aria-pressed", String(turbo));
  }

  function renderPool(bumpJackpot, bumpMax) {
    const jp = $("#jackpot-amount");
    const mx = $("#maxwin-amount");
    jp.textContent = money(pool.jackpot_aud || 0);
    mx.textContent = money(pool.max_win_aud || 0);
    $("#pool-amount").textContent = money(pool.pool_aud || 0);
    if (bumpJackpot) bump(jp);
    if (bumpMax) bump(mx);
  }
  function bump(el) {
    el.classList.remove("bump");
    void el.offsetWidth;
    el.classList.add("bump");
  }

  function renderPaytable() {
    payGrid.innerHTML = "";
    SYMBOLS.filter((s) => !s.scatter && !s.blank && !s.wild).sort((a, b) => (a.pays[5] || 0) - (b.pays[5] || 0)).forEach((s) => {
      const item = document.createElement("div");
      item.className = "pay-item" + (s.id === "greentea" ? " top" : "");
      item.innerHTML = `<span class="sym">${symbolHTML(s.id)}</span><span><span class="nm">${s.name}</span><span class="mult">${s.pays[3]} · ${s.pays[4]} · ${s.pays[5]}×</span></span>`;
      payGrid.appendChild(item);
    });
    const sp = FEATURES.scatter_pays || {};
    const fsText = Object.keys(sp).map((k) => `${k}: ${sp[k].free_spins}`).join(" · ");
    const payText = Object.keys(sp).map((k) => `${sp[k].pay}×`).join(" · ");
    const wild = SYMBOLS.find((s) => s.wild) || { pays: {} };
    featureGrid.innerHTML = `
      <div class="pay-item"><span class="sym">${symbolHTML("wild")}</span><span><span class="nm">Crystal Wild</span><span class="mult">Reels 2–4 · substitutes · win ×${FEATURES.wild_mult} · 5 on line ${wild.pays[5] || 1000}×</span></span></div>
      <div class="pay-item"><span class="sym">${symbolHTML("scatter")}</span><span><span class="nm">Prism Scatter</span><span class="mult">3/4/5 anywhere pay ${payText} · free spins ${fsText} · all wins ×${FEATURES.free_spin_mult}</span></span></div>
      <div class="pay-item top"><span class="sym">${symbolHTML("greentea")}</span><span><span class="nm">Green Tea Jackpot</span><span class="mult">Can drop on any spin · capped at max win</span></span></div>`;
  }

  function renderHistory() {
    const ul = $("#history");
    if (!history.length) {
      ul.innerHTML = '<li class="empty">No spins yet</li>';
      return;
    }
    ul.innerHTML = history.map((h) => {
      const x = h.bet ? h.win / h.bet : 0;
      const cls = h.win <= 0 ? "lose" : x >= BIG_WIN_X ? "big" : "win";
      const tags = [
        h.fs ? `<span class="tag fs">${h.fs} FS</span>` : "",
        h.jp ? '<span class="tag jp">JACKPOT</span>' : "",
        h.capped ? '<span class="tag cap">capped</span>' : "",
        x >= BIG_WIN_X ? `<span class="tag jp">${Math.round(x)}×</span>` : "",
      ].join("");
      const t = new Date(h.t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      return `<li class="${cls}"><span class="t">${t}</span><span class="tags">${money(h.bet)} bet ${tags}</span><span class="amt">${h.win > 0 ? "+" + money(h.win) : "—"}</span></li>`;
    }).join("");
  }

  function toast(msg, isError = false) {
    toastEl.hidden = false;
    toastEl.textContent = msg;
    toastEl.classList.toggle("error", isError);
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { toastEl.hidden = true; }, 3200);
  }

  // ---- Sound (Web Audio, crystal chimes) ----
  let audioCtx = null;
  let master = null;
  function ensureAudio() {
    if (!audioCtx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      audioCtx = new AC();
      master = audioCtx.createGain();
      master.gain.value = 0.5;
      master.connect(audioCtx.destination);
    }
    if (audioCtx.state === "suspended") audioCtx.resume();
  }
  function tone(freq, dur, { type = "sine", gain = 0.05, delay = 0, slideTo = null } = {}) {
    if (muted || !audioCtx) return;
    const t0 = audioCtx.currentTime + delay;
    const o = audioCtx.createOscillator();
    const g = audioCtx.createGain();
    o.type = type;
    o.frequency.setValueAtTime(freq, t0);
    if (slideTo) o.frequency.exponentialRampToValueAtTime(slideTo, t0 + dur);
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(gain, t0 + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    o.connect(g);
    g.connect(master);
    o.start(t0);
    o.stop(t0 + dur + 0.02);
  }
  function chime(freq, dur = 0.5, gain = 0.05, delay = 0) {
    tone(freq, dur, { gain, delay });
    tone(freq * 2.76, dur * 0.6, { gain: gain * 0.35, delay }); // glassy inharmonic partial
    tone(freq * 5.4, dur * 0.3, { gain: gain * 0.15, delay });
  }
  const sfx = {
    spin() { ensureAudio(); tone(220, 0.35, { type: "triangle", gain: 0.03, slideTo: 880 }); },
    stop(col) { ensureAudio(); chime(880 + col * 110, 0.25, 0.035); },
    scatter(n) { ensureAudio(); chime(1320 + n * 160, 0.6, 0.06); },
    tease() { ensureAudio(); tone(440, 0.6, { type: "sawtooth", gain: 0.015, slideTo: 1200 }); },
    win() { ensureAudio(); [784, 988, 1175].forEach((f, i) => chime(f, 0.5, 0.05, i * 0.08)); },
    big() { ensureAudio(); [523, 659, 784, 1046, 1318, 1568].forEach((f, i) => chime(f, 0.8, 0.06, i * 0.11)); },
    bonus() { ensureAudio(); for (let i = 0; i < 12; i++) chime(600 * Math.pow(2, i / 6), 0.5, 0.04, i * 0.06); },
    jackpot() { ensureAudio(); for (let r = 0; r < 3; r++) [523, 784, 1046, 1568].forEach((f, i) => chime(f, 0.9, 0.06, r * 0.5 + i * 0.09)); },
    lose() { ensureAudio(); tone(196, 0.18, { type: "triangle", gain: 0.02 }); },
    tick() { ensureAudio(); chime(1760, 0.08, 0.02); },
  };

  // ---- Sparkles (canvas particles) ----
  const canvas = $("#sparkle-canvas");
  const ctx = canvas.getContext("2d");
  let particles = [];
  let rafId = null;
  function resizeCanvas() {
    const dpr = window.devicePixelRatio || 1;
    canvas.width = innerWidth * dpr;
    canvas.height = innerHeight * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  const SPARK_COLORS = ["#ffffff", "#9fe6ff", "#c9b6ff", "#ff9fe0", "#8ff06b", "#fff36b"];
  function burst(x, y, n = 30, colors = SPARK_COLORS, power = 6) {
    for (let i = 0; i < n; i++) {
      const a = Math.random() * Math.PI * 2;
      const v = (0.4 + Math.random()) * power;
      particles.push({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v - 2, life: 1, decay: 0.012 + Math.random() * 0.02, size: 2 + Math.random() * 4, color: colors[(Math.random() * colors.length) | 0], rot: Math.random() * 6 });
    }
    if (!rafId) rafId = requestAnimationFrame(tickParticles);
  }
  function rain(n = 120, colors = SPARK_COLORS) {
    for (let i = 0; i < n; i++) {
      particles.push({ x: Math.random() * innerWidth, y: -20 - Math.random() * innerHeight * 0.6, vx: (Math.random() - 0.5) * 1.5, vy: 2 + Math.random() * 3, life: 1, decay: 0.004 + Math.random() * 0.004, size: 3 + Math.random() * 5, color: colors[(Math.random() * colors.length) | 0], rot: Math.random() * 6 });
    }
    if (!rafId) rafId = requestAnimationFrame(tickParticles);
  }
  function tickParticles() {
    ctx.clearRect(0, 0, innerWidth, innerHeight);
    particles = particles.filter((p) => p.life > 0 && p.y < innerHeight + 40);
    for (const p of particles) {
      p.x += p.vx; p.y += p.vy; p.vy += 0.12; p.vx *= 0.99; p.life -= p.decay; p.rot += 0.1;
      ctx.save();
      ctx.globalAlpha = Math.max(0, p.life);
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rot);
      ctx.fillStyle = p.color;
      ctx.shadowColor = p.color;
      ctx.shadowBlur = 8;
      const s = p.size;
      ctx.beginPath(); // 4-point sparkle
      ctx.moveTo(0, -s); ctx.lineTo(s * 0.3, -s * 0.3); ctx.lineTo(s, 0); ctx.lineTo(s * 0.3, s * 0.3);
      ctx.lineTo(0, s); ctx.lineTo(-s * 0.3, s * 0.3); ctx.lineTo(-s, 0); ctx.lineTo(-s * 0.3, -s * 0.3);
      ctx.closePath(); ctx.fill();
      ctx.restore();
    }
    rafId = particles.length ? requestAnimationFrame(tickParticles) : null;
    if (!rafId) ctx.clearRect(0, 0, innerWidth, innerHeight);
  }
  function burstAtEl(el, n, colors) {
    const r = el.getBoundingClientRect();
    burst(r.left + r.width / 2, r.top + r.height / 2, n, colors);
  }

  // ---- Reels ----
  const fillerIds = () => SYMBOLS.map((s) => s.id);
  const randomId = () => { const ids = fillerIds(); return ids[(Math.random() * ids.length) | 0]; };

  function initReels() {
    reelsEl.innerHTML = "";
    for (let c = 0; c < REEL_COUNT; c++) {
      const reel = document.createElement("div");
      reel.className = "reel";
      const strip = document.createElement("div");
      strip.className = "reel-strip";
      for (let r = 0; r < VISIBLE_ROWS; r++) strip.appendChild(makeCell(randomId()));
      reel.appendChild(strip);
      reelsEl.appendChild(reel);
    }
  }
  function clearHighlights() {
    reelsEl.querySelectorAll(".symbol.win, .symbol.scatter-hit").forEach((el) => el.classList.remove("win", "scatter-hit"));
  }
  function visibleCell(col, row) {
    const reel = reelsEl.querySelectorAll(".reel")[col];
    if (!reel) return null;
    const cells = reel.querySelectorAll(".symbol");
    return cells[cells.length - VISIBLE_ROWS + row];
  }

  async function animateGrid(grid) {
    const reels = [...reelsEl.querySelectorAll(".reel")];
    const h = symH();
    sfx.spin();
    let scattersSoFar = 0;
    let extra = 0;
    const base = speed(900);
    const gap = speed(260);
    const promises = reels.map((reel, col) => {
      const strip = reel.querySelector(".reel-strip");
      const pad = turbo ? 10 : 22 + col * 4;
      strip.style.transition = "none";
      strip.style.transform = "translateY(0px)";
      strip.innerHTML = "";
      for (let i = 0; i < pad; i++) strip.appendChild(makeCell(randomId()));
      grid[col].forEach((id) => strip.appendChild(makeCell(id)));
      // Anticipation: if 2+ scatters already landed, slow the next reels down.
      if (scattersSoFar >= 2 && !turbo) extra += 650;
      const duration = base + col * gap + extra;
      const colScatters = grid[col].filter((id) => id === "scatter").length;
      scattersSoFar += colScatters;
      void strip.offsetHeight;
      reel.classList.add("spinning");
      strip.style.transition = `transform ${duration}ms cubic-bezier(0.15, 0.8, 0.2, 1.02)`;
      strip.style.transform = `translateY(${-((pad) * h)}px)`;
      if (extra && !turbo) setTimeout(() => sfx.tease(), duration - 700);
      return sleep(duration + 20).then(() => {
        reel.classList.remove("spinning");
        sfx.stop(col);
        if (colScatters) {
          sfx.scatter(col);
          grid[col].forEach((id, row) => { if (id === "scatter") { const c = visibleCell(col, row); if (c) burstAtEl(c, 14); } });
        }
      });
    });
    await Promise.all(promises);
    // Trim strips so the DOM stays small.
    reels.forEach((reel) => {
      const strip = reel.querySelector(".reel-strip");
      while (strip.children.length > VISIBLE_ROWS) strip.removeChild(strip.firstChild);
      strip.style.transition = "none";
      strip.style.transform = "translateY(0px)";
    });
  }

  function showStep(step, label = "") {
    clearHighlights();
    const parts = [];
    if (step.count >= 3) {
      for (let c = 0; c < step.count; c++) { const el = visibleCell(c, 1); if (el) el.classList.add("win"); }
      const nm = step.symbol ? step.symbol.name || symbolName(step.symbol.id) : "";
      parts.push(`${step.count}× ${nm}${step.wild ? ` (wild ×${FEATURES.wild_mult})` : ""}`);
    }
    if (step.scatters >= 3) {
      (step.scatter_pos || []).forEach(([c, r]) => { const el = visibleCell(c, r); if (el) el.classList.add("scatter-hit"); });
      parts.push(`${step.scatters} Prisms`);
    }
    const win = step.win_aud + (step.jackpot_aud || 0);
    if (win > 0 || step.raw_win_aud > 0) {
      resultBanner.hidden = false;
      resultBanner.className = "result-banner" + (step.capped ? " capped" : "");
      let text = `${label}WIN ${money(step.win_aud)}`;
      if (parts.length) text += ` · ${parts.join(" + ")}`;
      if (step.multiplier > 1) text += ` · ×${step.multiplier}`;
      if (step.capped) text += ` · capped at 20% of pool (${money(step.cap_aud)})`;
      resultText.textContent = text;
      reelsEl.querySelectorAll(".symbol.win").forEach((el, i) => { if (i % 2 === 0) burstAtEl(el, 10); });
      sfx.win();
    } else {
      resultBanner.hidden = false;
      resultBanner.className = "result-banner lose";
      resultText.textContent = label ? `${label}no win` : "No win — spin again!";
      sfx.lose();
    }
    return win;
  }

  // ---- Celebrations ----
  let celebrateResolve = null;
  function celebrate({ kind = "big", title, amountAud = null, sub = "", hold = 3200, count = true }) {
    return new Promise((resolve) => {
      const inner = celebrateEl.querySelector(".celebrate-inner");
      inner.querySelector(".celebrate-art")?.remove();
      const art = document.createElement("div");
      art.className = "celebrate-art";
      art.innerHTML = kind === "bonus"
        ? `<svg class="celebrate-prism" viewBox="0 0 100 100"><use href="#cut-prism"/></svg>`
        : `<div class="celebrate-tea"><img src="${TEA_IMG_BIG}" alt="Green Tea 1kg packet" /></div>`;
      inner.prepend(art);
      celebrateEl.className = "celebrate" + (kind === "bonus" ? " bonus" : "");
      $("#celebrate-title").textContent = title;
      $("#celebrate-sub").textContent = sub;
      const amtEl = $("#celebrate-amount");
      amtEl.textContent = amountAud == null ? "" : money(count ? 0 : amountAud);
      celebrateEl.hidden = false;
      const teaColors = ["#8ff06b", "#eaffd0", "#fff36b", "#ffffff", "#3ff0a8"];
      if (kind === "bonus") { sfx.bonus(); rain(90); } else if (kind === "jackpot") { sfx.jackpot(); rain(220, teaColors); } else { sfx.big(); rain(150, teaColors); }
      // Count-up
      let raf = null;
      if (amountAud != null && count) {
        const t0 = performance.now();
        const dur = Math.min(hold * 0.7, 2400);
        let lastTick = 0;
        const step = (t) => {
          const k = Math.min(1, (t - t0) / dur);
          const eased = 1 - Math.pow(1 - k, 3);
          amtEl.textContent = money(amountAud * eased);
          if (t - lastTick > 90 && k < 1) { sfx.tick(); lastTick = t; }
          if (k < 1) raf = requestAnimationFrame(step);
        };
        raf = requestAnimationFrame(step);
      }
      const done = () => {
        if (raf) cancelAnimationFrame(raf);
        if (amountAud != null) amtEl.textContent = money(amountAud);
        celebrateEl.hidden = true;
        clearTimeout(timer);
        celebrateResolve = null;
        resolve();
      };
      const timer = setTimeout(done, auto.running || turbo ? Math.min(hold, 2200) : hold);
      celebrateResolve = done;
    });
  }

  function bigWinTitle(x) {
    if (x >= EPIC_WIN_X) return "GREEN TEA EPIC WIN!";
    if (x >= MEGA_WIN_X) return "GREEN TEA MEGA WIN!";
    return "GREEN TEA BIG WIN!";
  }

  // ---- Round ----
  function setBusy(on) {
    busy = on;
    btnSpin.classList.toggle("spinning", on && !auto.running);
    btnSpin.disabled = on && !auto.running;
    document.querySelectorAll("#bet-up, #bet-down").forEach((b) => { b.disabled = on || auto.running; });
  }

  async function playRound() {
    const bet = currentBetAud();
    if (totalAud() < bet - 1e-9) {
      toast("Insufficient test balance — deposit first", true);
      if (!auto.running) openModal("deposit");
      return null;
    }
    ensureAudio();
    setBusy(true);
    clearHighlights();
    resultBanner.hidden = true;

    let result;
    try {
      result = await api("/api/spin", { method: "POST", body: JSON.stringify({ bet_index: betIndex, display_currency: displayCurrency }) });
    } catch (err) {
      setBusy(false);
      toast(err.message || "Spin failed", true);
      if (/deposit/i.test(err.message || "") && !auto.running) openModal("deposit");
      return null;
    }

    pendingWinAud = result.win_aud || 0;
    const prevLast = lastWinAud;
    applySnapshot(result);
    lastWinAud = prevLast;
    renderBalances();

    let revealed = 0;
    const base = result.base;
    await animateGrid(base.grid);
    revealed += showStep(base);
    pendingWinAud = Math.max(0, (result.win_aud || 0) - revealed);
    lastWinAud = revealed;
    renderBalances();

    if (result.jackpot_hit) {
      if (result.jackpot_paid_aud > 0) {
        machineEl.classList.add("shake");
        setTimeout(() => machineEl.classList.remove("shake"), 600);
        await celebrate({ kind: "jackpot", title: "GREEN TEA JACKPOT!", amountAud: result.jackpot_paid_aud, sub: "The Green Tea Jackpot dropped!", hold: 4200 });
      } else {
        toast("Green Tea Jackpot triggered, but the meter is empty — it pays out of the pool cap.");
      }
    }

    const fs = result.free_spins || [];
    if (fs.length) {
      await sleep(speed(500));
      await celebrate({ kind: "bonus", title: `${base.free_spins_awarded} FREE SPINS`, sub: `All wins ×${FEATURES.free_spin_mult}`, hold: 2400 });
      machineEl.classList.add("in-bonus");
      fsBanner.hidden = false;
      let totalAwarded = base.free_spins_awarded;
      let bonusWin = 0;
      for (let i = 0; i < fs.length; i++) {
        $("#fs-count").textContent = `${i + 1} / ${totalAwarded}`;
        $("#fs-total").textContent = money(bonusWin);
        resultBanner.hidden = true;
        await animateGrid(fs[i].grid);
        const w = showStep(fs[i], `Free spin ${i + 1}: `);
        bonusWin += w;
        revealed += w;
        pendingWinAud = Math.max(0, (result.win_aud || 0) - revealed);
        lastWinAud = revealed;
        renderBalances();
        $("#fs-total").textContent = money(bonusWin);
        if (fs[i].free_spins_awarded > 0) {
          totalAwarded += fs[i].free_spins_awarded;
          $("#fs-count").textContent = `${i + 1} / ${totalAwarded}`;
          toast(`+${fs[i].free_spins_awarded} free spins!`);
          sfx.bonus();
        }
        await sleep(speed(w > 0 ? 900 : 350));
      }
      machineEl.classList.remove("in-bonus");
      fsBanner.hidden = true;
      await celebrate({ kind: "bonus", title: "BONUS COMPLETE", amountAud: bonusWin, sub: `${fs.length} free spins`, hold: 2600 });
    }

    pendingWinAud = 0;
    lastWinAud = result.win_aud || 0;
    renderBalances();

    const x = result.bet_aud ? (result.win_aud || 0) / result.bet_aud : 0;
    const bigWin = x >= BIG_WIN_X && !result.jackpot_paid_aud;
    if (bigWin) {
      await celebrate({ kind: "big", title: bigWinTitle(x), amountAud: result.win_aud, sub: `${Math.round(x)}× your bet${result.any_capped ? " · capped at 20% of pool" : ""}`, hold: 3600 });
    }
    if (fs.length || x >= 2) {
      resultBanner.hidden = false;
      resultBanner.className = "result-banner" + (x >= BIG_WIN_X ? " big" : "") + (result.any_capped ? " capped" : "");
      resultText.textContent = `Total win ${money(result.win_aud)}${fs.length ? ` · incl. ${fs.length} free spins` : ""}${result.jackpot_paid_aud ? " · incl. jackpot" : ""}${result.any_capped ? " · capped at 20% of pool" : ""}`;
    }

    history.unshift({ t: Date.now(), bet: result.bet_aud, win: result.win_aud || 0, fs: fs.length, jp: !!result.jackpot_paid_aud, capped: !!result.any_capped });
    history = history.slice(0, 30);
    saveHistory();
    renderHistory();
    setBusy(false);
    return { result, x, bonus: fs.length > 0, bigWin: x >= BIG_WIN_X || !!result.jackpot_paid_aud };
  }

  async function spin() {
    if (!ready) return;
    if (celebrateResolve) { celebrateResolve(); return; }
    if (auto.running) { stopAuto("Auto spin stopped"); return; }
    if (busy) return;
    await playRound();
  }

  // ---- Auto spin ----
  function updateAutoUI() {
    if (auto.running) {
      const left = auto.remaining === Infinity ? "∞" : String(auto.remaining);
      btnAuto.textContent = `STOP (${left})`;
      btnAuto.classList.add("active-auto");
      btnSpin.textContent = "STOP";
      btnSpin.classList.add("stop-mode");
      btnSpin.disabled = false;
      autoStatus.hidden = false;
      const done = auto.total === Infinity ? auto.played : `${auto.played} / ${auto.total}`;
      autoStatus.textContent = `Auto spin ${done}${turbo ? " · turbo" : ""}`;
    } else {
      btnAuto.textContent = "AUTO";
      btnAuto.classList.remove("active-auto");
      btnSpin.textContent = "SPIN";
      btnSpin.classList.remove("stop-mode");
      autoStatus.hidden = true;
    }
  }
  function stopAuto(reason) {
    if (!auto.running) return;
    auto.running = false;
    updateAutoUI();
    if (reason) toast(reason);
  }
  async function startAuto() {
    const count = autoCountChoice === "Infinity" ? Infinity : parseInt(autoCountChoice, 10) || 25;
    auto.total = count;
    auto.remaining = count;
    auto.played = 0;
    auto.stopBonus = $("#auto-stop-bonus").checked;
    auto.stopBig = $("#auto-stop-bigwin").checked;
    const below = parseFloat($("#auto-stop-balance").value);
    auto.stopBelowAud = $("#auto-stop-balance-on").checked && below >= 0 ? toAud(displayCurrency, below) : null;
    turbo = $("#auto-turbo").checked;
    savePrefs();
    renderBalances();
    closeModal("auto");
    if (busy) return;
    auto.running = true;
    updateAutoUI();
    while (auto.running && auto.remaining > 0) {
      if (auto.stopBelowAud != null && totalAud() < auto.stopBelowAud) { stopAuto(`Auto spin stopped: balance below ${money(auto.stopBelowAud)}`); break; }
      const r = await playRound();
      if (!r) { stopAuto("Auto spin stopped"); break; }
      auto.played += 1;
      if (auto.remaining !== Infinity) auto.remaining -= 1;
      updateAutoUI();
      if (auto.stopBonus && r.bonus) { stopAuto("Auto spin stopped: free spins won"); break; }
      if (auto.stopBig && r.bigWin) { stopAuto("Auto spin stopped: big win"); break; }
      if (auto.stopBelowAud != null && totalAud() < auto.stopBelowAud) { stopAuto(`Auto spin stopped: balance below ${money(auto.stopBelowAud)}`); break; }
      await sleep(turbo ? 120 : 450);
    }
    if (auto.running) stopAuto("Auto spin finished");
  }

  // ---- Modals / wallet ----
  function depositType() {
    const active = $("#deposit-type").querySelector("button.active");
    return (active && active.dataset.type) || "fiat";
  }
  function fillAssetSelect(selectEl, type) {
    const list = type === "crypto" ? CRYPTO : FIAT;
    selectEl.innerHTML = list.map((a) => `<option value="${a}">${a}</option>`).join("");
  }
  function updateDepositButton() {
    const type = depositType();
    const btn = $("#confirm-deposit");
    const note = $("#deposit-note");
    if (type === "crypto") {
      btn.disabled = false;
      btn.textContent = "Add play-money credit";
      note.textContent = "Play money only — no real crypto is transferred or withdrawn.";
    } else if (stripeEnabled) {
      btn.disabled = false;
      btn.textContent = "Pay with Stripe (test mode)";
      note.textContent = "Stripe Checkout in TEST MODE. Use test card 4242 4242 4242 4242 (any future expiry, any CVC). Real-money play needs a gambling licence plus Stripe approval.";
    } else {
      btn.disabled = true;
      btn.textContent = "Checkout unavailable";
      note.textContent = "Add a Stripe test key to enable checkout";
    }
  }
  function openModal(name) {
    const modal = $(`#modal-${name}`);
    if (!modal) return;
    modal.hidden = false;
    if (name === "deposit") {
      fillAssetSelect($("#deposit-asset"), "fiat");
      $("#deposit-type").querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.type === "fiat"));
      $("#deposit-amount").value = "";
      updateDepositHint();
    }
    if (name === "withdraw") {
      fillAssetSelect($("#withdraw-asset"), "fiat");
      $("#withdraw-type").querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.type === "fiat"));
      $("#withdraw-amount").value = "";
      $("#withdraw-processing").hidden = true;
      $("#withdraw-success").hidden = true;
      $("#confirm-withdraw").hidden = false;
      updateWithdrawHint();
    }
    if (name === "auto") {
      $("#auto-count").querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.count === autoCountChoice));
      $("#auto-turbo").checked = turbo;
    }
  }
  function closeModal(name) {
    const modal = $(`#modal-${name}`);
    if (modal) modal.hidden = true;
  }
  function updateDepositHint() {
    const asset = $("#deposit-asset").value;
    const amount = parseFloat($("#deposit-amount").value) || 0;
    const rate = RATES_TO_AUD[asset];
    $("#deposit-hint").textContent = amount > 0 ? `≈ ${money(toAud(asset, amount))} play value · demo rate 1 ${asset} ≈ ${rate} AUD` : `Demo rate: 1 ${asset} ≈ ${rate} AUD`;
    updateDepositButton();
  }
  function updateWithdrawHint() {
    const asset = $("#withdraw-asset").value;
    const bal = balances[asset] || 0;
    const amount = parseFloat($("#withdraw-amount").value) || 0;
    const play = CRYPTO.includes(asset) ? " (play money)" : "";
    $("#withdraw-available").textContent = `Available: ${formatAsset(asset, bal)}${play}`;
    $("#withdraw-hint").textContent = amount > 0
      ? `≈ ${money(toAud(asset, amount))} will be debited from the test ledger (simulated, no real payout)`
      : "Withdrawals are simulated only — the ledger is debited and marked “test withdrawal recorded”.";
  }
  async function confirmDeposit() {
    const type = depositType();
    const asset = $("#deposit-asset").value;
    const amount = parseFloat($("#deposit-amount").value);
    if (!amount || amount <= 0) return toast("Enter a valid amount", true);
    if (amount > 1e9) return toast("Amount too large for demo", true);
    const btn = $("#confirm-deposit");
    btn.disabled = true;
    try {
      if (type === "crypto") {
        const snap = await api("/api/deposit/play", { method: "POST", body: JSON.stringify({ asset, amount }) });
        applySnapshot(snap);
        renderBalances();
        closeModal("deposit");
        toast(`Added ${formatAsset(asset, amount)} play money`);
        ensureAudio();
        sfx.win();
      } else {
        if (!stripeEnabled) return toast("Add a Stripe test key to enable checkout", true);
        const data = await api("/api/deposit/checkout", { method: "POST", body: JSON.stringify({ currency: asset, amount }) });
        if (!data || !data.url) throw new Error("Checkout did not return a URL");
        window.location.href = data.url;
        return;
      }
    } catch (err) {
      toast(err.message || "Deposit failed", true);
    } finally {
      updateDepositButton();
    }
  }
  async function confirmWithdraw() {
    const asset = $("#withdraw-asset").value;
    const amount = parseFloat($("#withdraw-amount").value);
    const bal = balances[asset] || 0;
    if (!amount || amount <= 0) return toast("Enter a valid amount", true);
    if (amount > bal + 1e-12) return toast("Amount exceeds available balance", true);
    const btn = $("#confirm-withdraw");
    btn.hidden = true;
    $("#withdraw-processing").hidden = false;
    $("#withdraw-success").hidden = true;
    try {
      const snap = await api("/api/withdraw", { method: "POST", body: JSON.stringify({ asset, amount }) });
      applySnapshot(snap);
      renderBalances();
      $("#withdraw-processing").hidden = true;
      $("#withdraw-success").hidden = false;
      toast(`${formatAsset(asset, amount)} — ${(snap.withdrawal && snap.withdrawal.status) || "test withdrawal recorded"}`);
      setTimeout(() => closeModal("withdraw"), 1400);
    } catch (err) {
      $("#withdraw-processing").hidden = true;
      btn.hidden = false;
      toast(err.message || "Withdrawal failed", true);
    }
  }

  // ---- Events ----
  function wireEvents() {
    btnSpin.addEventListener("click", spin);
    btnAuto.addEventListener("click", () => {
      if (auto.running) return stopAuto("Auto spin stopped");
      if (busy) return;
      openModal("auto");
    });
    btnTurbo.addEventListener("click", () => {
      turbo = !turbo;
      savePrefs();
      renderBalances();
      updateAutoUI();
      toast(turbo ? "Turbo on" : "Turbo off");
    });
    $("#auto-count").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-count]");
      if (!b) return;
      autoCountChoice = b.dataset.count;
      $("#auto-count").querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
      savePrefs();
    });
    $("#auto-stop-balance").addEventListener("input", () => { $("#auto-stop-balance-on").checked = $("#auto-stop-balance").value !== ""; });
    $("#auto-start").addEventListener("click", startAuto);
    celebrateEl.addEventListener("click", () => { if (celebrateResolve) celebrateResolve(); });

    $("#bet-up").addEventListener("click", () => {
      if (busy || auto.running) return;
      betIndex = Math.min(BET_STEPS_AUD.length - 1, betIndex + 1);
      savePrefs(); renderBalances(); sfx.tick();
    });
    $("#bet-down").addEventListener("click", () => {
      if (busy || auto.running) return;
      betIndex = Math.max(0, betIndex - 1);
      savePrefs(); renderBalances(); sfx.tick();
    });
    btnMute.addEventListener("click", () => {
      muted = !muted;
      savePrefs();
      renderBalances();
      if (!muted) { ensureAudio(); chime(1046, 0.3, 0.05); }
    });
    $("#btn-deposit").addEventListener("click", () => openModal("deposit"));
    $("#btn-withdraw").addEventListener("click", () => openModal("withdraw"));
    $("#btn-wallet").addEventListener("click", () => openModal("deposit"));

    displayCurrencySel.addEventListener("change", async () => {
      const previous = displayCurrency;
      displayCurrency = displayCurrencySel.value;
      savePrefs(); renderBalances(); renderPool(); renderHistory();
      try {
        applySnapshot(await api("/api/prefs", { method: "POST", body: JSON.stringify({ display_currency: displayCurrency }) }));
        renderBalances();
      } catch (err) {
        displayCurrency = previous;
        savePrefs(); renderBalances(); renderPool(); renderHistory();
        toast(err.message || "Could not update display currency", true);
      }
    });

    document.querySelectorAll("[data-close]").forEach((el) => el.addEventListener("click", () => closeModal(el.dataset.close)));
    $("#deposit-type").addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-type]");
      if (!btn) return;
      $("#deposit-type").querySelectorAll("button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      fillAssetSelect($("#deposit-asset"), btn.dataset.type);
      updateDepositHint();
    });
    $("#withdraw-type").addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-type]");
      if (!btn) return;
      $("#withdraw-type").querySelectorAll("button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      fillAssetSelect($("#withdraw-asset"), btn.dataset.type);
      updateWithdrawHint();
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
        if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || tag === "BUTTON") return;
        if (document.querySelector(".modal:not([hidden])")) return;
        e.preventDefault();
        spin();
      }
      if (e.key === "Escape") {
        ["deposit", "withdraw", "auto"].forEach(closeModal);
        if (celebrateResolve) celebrateResolve();
      }
    });
    window.addEventListener("resize", resizeCanvas);
    document.addEventListener("visibilitychange", refreshPool);
  }

  // ---- Boot ----
  async function boot() {
    resizeCanvas();
    renderPaytable();
    initReels();
    renderBalances();
    renderPool();
    renderHistory();
    wireEvents();
    updateAutoUI();
    try {
      await refreshBalance();
    } catch {
      toast("Could not load the server ledger — is the Flask app running?", true);
    }
    ready = true;
    setInterval(refreshPool, 8000);
  }

  boot();
})();
