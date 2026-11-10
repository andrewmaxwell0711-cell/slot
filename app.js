/**
 * Fortune Reels — Demo / TEST MODE slot machine.
 * Balances and spin outcomes are authoritative on the server.
 * Fiat deposits use Stripe test Checkout when a test key is configured.
 * Crypto deposits are play money only. Withdrawals are simulated.
 */

(() => {
  "use strict";

  // ---- Config ----
  const REEL_COUNT = 5;
  const VISIBLE_ROWS = 3;
  const SYMBOL_H = () => {
    return window.matchMedia("(max-width: 520px)").matches ? 70 : 88;
  };

  // Fallback copy of server rules (overwritten by /api/config when available).
  let SYMBOLS = [
    { id: "cherry", emoji: "🍒", weight: 22, pays: { 3: 4, 4: 10, 5: 20 } },
    { id: "lemon", emoji: "🍋", weight: 20, pays: { 3: 4, 4: 10, 5: 20 } },
    { id: "orange", emoji: "🍊", weight: 18, pays: { 3: 6, 4: 16, 5: 40 } },
    { id: "plum", emoji: "🍇", weight: 16, pays: { 3: 6, 4: 16, 5: 50 } },
    { id: "bell", emoji: "🔔", weight: 12, pays: { 3: 10, 4: 30, 5: 80 } },
    { id: "bar", emoji: "⬛", weight: 8, pays: { 3: 15, 4: 50, 5: 100 } },
    { id: "seven", emoji: "7️⃣", weight: 5, pays: { 3: 25, 4: 80, 5: 200 } },
    { id: "diamond", emoji: "💎", weight: 3, pays: { 3: 50, 4: 150, 5: 500 } },
  ];

  let RATES_TO_AUD = {
    AUD: 1,
    USD: 1.52,
    EUR: 1.65,
    BTC: 145000,
    ETH: 5200,
    USDT: 1.52,
    SOL: 280,
  };

  const FIAT = ["AUD", "USD", "EUR"];
  const CRYPTO = ["BTC", "ETH", "USDT", "SOL"];
  const ALL_ASSETS = [...FIAT, ...CRYPTO];

  let BET_STEPS_AUD = [0.5, 1, 2, 5, 10, 20, 50, 100];
  const PREFS_KEY = "fortune-reels-prefs-v2";

  // ---- State ----
  let prefs = loadPrefs();
  let balances = Object.fromEntries(ALL_ASSETS.map((a) => [a, 0]));
  let stats = { spins: 0, totalWonAud: 0, totalBetAud: 0 };
  let lastWinAud = 0;
  let displayCurrency = prefs.displayCurrency || "AUD";
  let stripeEnabled = false;
  let spinning = false;
  let muted = prefs.muted;
  let betIndex = prefs.betIndex;
  let currentGrid = null;
  let ready = false;

  // ---- DOM ----
  const $ = (sel) => document.querySelector(sel);
  const reelsEl = $("#reels");
  const balanceListEl = $("#balance-list");
  const primaryBalanceEl = $("#primary-balance");
  const primaryCurrencyLabel = $("#primary-currency-label");
  const betAmountEl = $("#bet-amount");
  const lastWinEl = $("#last-win");
  const resultBanner = $("#result-banner");
  const resultText = $("#result-text");
  const btnSpin = $("#btn-spin");
  const btnMute = $("#btn-mute");
  const toastEl = $("#toast");
  const payGrid = $("#pay-grid");
  const displayCurrencySel = $("#display-currency");
  const stripeKeyBanner = $("#stripe-key-banner");

  // ---- Prefs (UI only — not the ledger) ----
  function defaultPrefs() {
    return { displayCurrency: "AUD", betIndex: 1, muted: false };
  }

  function loadPrefs() {
    try {
      const raw = localStorage.getItem(PREFS_KEY);
      if (!raw) return defaultPrefs();
      return { ...defaultPrefs(), ...JSON.parse(raw) };
    } catch {
      return defaultPrefs();
    }
  }

  function savePrefs() {
    prefs = { displayCurrency, betIndex, muted };
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  }

  function applySnapshot(snap) {
    if (!snap) return;
    if (snap.balances) {
      balances = { ...Object.fromEntries(ALL_ASSETS.map((a) => [a, 0])), ...snap.balances };
    }
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
  }

  function applyConfig(cfg) {
    if (!cfg) return;
    stripeEnabled = !!cfg.stripe_enabled;
    if (stripeKeyBanner) stripeKeyBanner.hidden = stripeEnabled;
    if (cfg.rates_to_aud) RATES_TO_AUD = cfg.rates_to_aud;
    if (Array.isArray(cfg.bet_steps_aud) && cfg.bet_steps_aud.length) {
      BET_STEPS_AUD = cfg.bet_steps_aud;
      if (betIndex >= BET_STEPS_AUD.length) betIndex = BET_STEPS_AUD.length - 1;
    }
    if (Array.isArray(cfg.symbols) && cfg.symbols.length) {
      SYMBOLS = cfg.symbols.map((s) => ({
        id: s.id,
        emoji: s.emoji,
        pays: Object.fromEntries(
          Object.entries(s.pays || {}).map(([k, v]) => [Number(k), v])
        ),
      }));
      renderPaytable();
    }
  }

  async function api(path, options = {}) {
    const opts = {
      credentials: "same-origin",
      headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) },
      ...options,
    };
    const res = await fetch(path, opts);
    let data = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }
    if (!res.ok) {
      const message = (data && data.error) || `Request failed (${res.status})`;
      const err = new Error(message);
      err.status = res.status;
      err.data = data;
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

  // ---- Formatting & conversion ----
  function toAud(asset, amount) {
    return amount * (RATES_TO_AUD[asset] || 1);
  }

  function fromAud(asset, audAmount) {
    return audAmount / (RATES_TO_AUD[asset] || 1);
  }

  function totalAud() {
    return ALL_ASSETS.reduce((sum, a) => sum + toAud(a, balances[a] || 0), 0);
  }

  function formatAsset(asset, amount) {
    if (FIAT.includes(asset)) {
      return new Intl.NumberFormat(undefined, {
        style: "currency",
        currency: asset,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(amount);
    }
    const digits = asset === "USDT" ? 2 : amount >= 1 ? 4 : 6;
    return `${Number(amount).toFixed(digits)} ${asset}`;
  }

  function formatAudAsDisplay(audAmount) {
    const cur = displayCurrency || "AUD";
    const converted = fromAud(cur, audAmount);
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: cur,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(converted);
  }

  function currentBetAud() {
    return BET_STEPS_AUD[Math.min(betIndex, BET_STEPS_AUD.length - 1)];
  }

  // ---- UI updates ----
  function renderBalances() {
    primaryBalanceEl.textContent = formatAudAsDisplay(totalAud());
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

    betAmountEl.textContent = formatAudAsDisplay(currentBetAud());
    lastWinEl.textContent = formatAudAsDisplay(lastWinAud || 0);
    $("#stat-spins").textContent = String(stats.spins || 0);
    $("#stat-won").textContent = formatAudAsDisplay(stats.totalWonAud || 0);
    $("#stat-bet").textContent = formatAudAsDisplay(stats.totalBetAud || 0);
    btnMute.textContent = muted ? "🔇" : "🔊";
  }

  function renderPaytable() {
    payGrid.innerHTML = "";
    SYMBOLS.forEach((s) => {
      const item = document.createElement("div");
      item.className = "pay-item";
      item.innerHTML = `<span class="sym">${s.emoji}</span><span>×3–5</span><span class="mult">${s.pays[3]}–${s.pays[5]}×</span>`;
      payGrid.appendChild(item);
    });
  }

  function toast(msg, isError = false) {
    toastEl.hidden = false;
    toastEl.textContent = msg;
    toastEl.classList.toggle("error", isError);
    clearTimeout(toast._t);
    toast._t = setTimeout(() => {
      toastEl.hidden = true;
    }, 3200);
  }

  // ---- Sound (Web Audio, optional) ----
  let audioCtx = null;
  function ensureAudio() {
    if (!audioCtx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (AC) audioCtx = new AC();
    }
    if (audioCtx && audioCtx.state === "suspended") audioCtx.resume();
  }

  function beep(freq, dur, type = "square", gain = 0.04) {
    if (muted || !audioCtx) return;
    const o = audioCtx.createOscillator();
    const g = audioCtx.createGain();
    o.type = type;
    o.frequency.value = freq;
    g.gain.value = gain;
    o.connect(g);
    g.connect(audioCtx.destination);
    o.start();
    g.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + dur);
    o.stop(audioCtx.currentTime + dur);
  }

  function sfxSpin() {
    ensureAudio();
    beep(180, 0.08, "sawtooth", 0.03);
  }
  function sfxStop() {
    ensureAudio();
    beep(320, 0.06, "triangle", 0.04);
  }
  function sfxWin(big) {
    ensureAudio();
    const notes = big ? [523, 659, 784, 1046] : [440, 554, 659];
    notes.forEach((n, i) => setTimeout(() => beep(n, 0.15, "sine", 0.05), i * 90));
  }
  function sfxLose() {
    ensureAudio();
    beep(160, 0.12, "triangle", 0.03);
  }

  // ---- Reels (animation only; outcomes come from the server) ----
  function weightedPick() {
    // Decorative filler symbols only — not used for payouts.
    const pool = SYMBOLS;
    return pool[Math.floor(Math.random() * pool.length)] || pool[0];
  }

  function symbolById(id) {
    return SYMBOLS.find((s) => s.id === id) || SYMBOLS[0];
  }

  function buildReelStrip(finalSymbols) {
    const pad = 28;
    const strip = [];
    for (let i = 0; i < pad; i++) strip.push(weightedPick());
    strip.push(...finalSymbols);
    return strip;
  }

  function initReels() {
    reelsEl.innerHTML = "";
    currentGrid = [];
    for (let c = 0; c < REEL_COUNT; c++) {
      const col = [weightedPick(), weightedPick(), weightedPick()];
      currentGrid.push(col.map((s) => s.id));
      const reel = document.createElement("div");
      reel.className = "reel";
      reel.dataset.col = String(c);
      const strip = document.createElement("div");
      strip.className = "reel-strip";
      col.forEach((s) => {
        const cell = document.createElement("div");
        cell.className = "symbol";
        cell.textContent = s.emoji;
        strip.appendChild(cell);
      });
      strip.style.transform = `translateY(0px)`;
      reel.appendChild(strip);
      reelsEl.appendChild(reel);
    }
  }

  function clearWinHighlights() {
    reelsEl.querySelectorAll(".symbol.win").forEach((el) => el.classList.remove("win"));
  }

  function highlightWins(count) {
    const reels = [...reelsEl.querySelectorAll(".reel")];
    reels.forEach((reel, i) => {
      if (i >= count) return;
      const symbols = reel.querySelectorAll(".symbol");
      const mid = symbols[symbols.length - 2];
      if (mid) mid.classList.add("win");
    });
  }

  function depositType() {
    const active = $("#deposit-type").querySelector("button.active");
    return (active && active.dataset.type) || "fiat";
  }

  async function spin() {
    if (spinning || !ready) return;
    ensureAudio();

    const bet = currentBetAud();
    if (totalAud() < bet - 1e-9) {
      toast("Insufficient test balance — deposit first", true);
      openModal("deposit");
      return;
    }

    spinning = true;
    btnSpin.disabled = true;
    btnSpin.classList.add("spinning");
    clearWinHighlights();
    resultBanner.hidden = true;

    let result;
    try {
      result = await api("/api/spin", {
        method: "POST",
        body: JSON.stringify({ bet_index: betIndex, display_currency: displayCurrency }),
      });
    } catch (err) {
      spinning = false;
      btnSpin.disabled = false;
      btnSpin.classList.remove("spinning");
      toast(err.message || "Spin failed", true);
      if (/deposit/i.test(err.message || "")) openModal("deposit");
      return;
    }

    applySnapshot(result);
    renderBalances();
    sfxSpin();

    const finalGrid = result.grid.map((col) => col.map((id) => symbolById(id)));
    currentGrid = result.grid;

    const reels = [...reelsEl.querySelectorAll(".reel")];
    const h = SYMBOL_H();

    const animations = reels.map((reel, colIdx) => {
      return new Promise((resolve) => {
        const strip = reel.querySelector(".reel-strip");
        reel.classList.add("spinning");
        const finalSyms = finalGrid[colIdx];
        const full = buildReelStrip(finalSyms);
        strip.innerHTML = "";
        full.forEach((s) => {
          const cell = document.createElement("div");
          cell.className = "symbol";
          cell.textContent = s.emoji;
          strip.appendChild(cell);
        });

        const startY = 0;
        const endY = -((full.length - VISIBLE_ROWS) * h);
        strip.style.transition = "none";
        strip.style.transform = `translateY(${startY}px)`;
        void strip.offsetHeight;

        const duration = 1200 + colIdx * 350 + Math.random() * 200;
        strip.style.transition = `transform ${duration}ms cubic-bezier(0.12, 0.75, 0.15, 1)`;
        strip.style.transform = `translateY(${endY}px)`;

        setTimeout(() => {
          reel.classList.remove("spinning");
          sfxStop();
          resolve();
        }, duration + 30);
      });
    });

    await Promise.all(animations);

    if (result.win_aud > 0) {
      highlightWins(result.count);
      resultBanner.hidden = false;
      resultBanner.className = "result-banner" + (result.mult >= 50 ? " jackpot" : "");
      const emoji = (result.symbol && result.symbol.emoji) || "";
      resultText.textContent = `WIN! ${result.count}× ${emoji}  ·  ${formatAudAsDisplay(result.win_aud)} (${result.mult}×)`;
      sfxWin(result.mult >= 50);
    } else {
      resultBanner.hidden = false;
      resultBanner.className = "result-banner lose";
      resultText.textContent = "No win — try again!";
      sfxLose();
    }

    spinning = false;
    btnSpin.disabled = false;
    btnSpin.classList.remove("spinning");
  }

  // ---- Modals ----
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
      if (note) {
        note.textContent = "Play money only — no real crypto is transferred or withdrawn.";
      }
    } else if (stripeEnabled) {
      btn.disabled = false;
      btn.textContent = "Pay with Stripe (test mode)";
      if (note) {
        note.textContent =
          "Stripe Checkout in TEST MODE. Use test card 4242 4242 4242 4242 (any future expiry, any CVC). Real-money play needs a gambling licence plus Stripe approval.";
      }
    } else {
      btn.disabled = true;
      btn.textContent = "Checkout unavailable";
      if (note) {
        note.textContent = "Add a Stripe test key to enable checkout";
      }
    }
  }

  function openModal(name) {
    const modal = $(`#modal-${name}`);
    if (!modal) return;
    modal.hidden = false;
    if (name === "deposit") {
      fillAssetSelect($("#deposit-asset"), "fiat");
      $("#deposit-type").querySelectorAll("button").forEach((b) => {
        b.classList.toggle("active", b.dataset.type === "fiat");
      });
      $("#deposit-amount").value = "";
      updateDepositHint();
      updateDepositButton();
    }
    if (name === "withdraw") {
      fillAssetSelect($("#withdraw-asset"), "fiat");
      $("#withdraw-type").querySelectorAll("button").forEach((b) => {
        b.classList.toggle("active", b.dataset.type === "fiat");
      });
      $("#withdraw-amount").value = "";
      $("#withdraw-processing").hidden = true;
      $("#withdraw-success").hidden = true;
      $("#confirm-withdraw").hidden = false;
      updateWithdrawHint();
    }
  }

  function closeModal(name) {
    const modal = $(`#modal-${name}`);
    if (modal) modal.hidden = true;
  }

  function updateDepositHint() {
    const asset = $("#deposit-asset").value;
    const amount = parseFloat($("#deposit-amount").value) || 0;
    const aud = toAud(asset, amount);
    const rate = RATES_TO_AUD[asset];
    $("#deposit-hint").textContent =
      amount > 0
        ? `≈ ${formatAudAsDisplay(aud)} play value · demo rate 1 ${asset} ≈ ${rate} AUD`
        : `Demo rate: 1 ${asset} ≈ ${rate} AUD`;
    updateDepositButton();
  }

  function updateWithdrawHint() {
    const asset = $("#withdraw-asset").value;
    const bal = balances[asset] || 0;
    const amount = parseFloat($("#withdraw-amount").value) || 0;
    const aud = toAud(asset, amount);
    const play = CRYPTO.includes(asset) ? " (play money)" : "";
    $("#withdraw-available").textContent = `Available: ${formatAsset(asset, bal)}${play}`;
    $("#withdraw-hint").textContent =
      amount > 0
        ? `≈ ${formatAudAsDisplay(aud)} will be debited from the test ledger (simulated, no real payout)`
        : "Withdrawals are simulated only — the ledger is debited and marked “test withdrawal recorded”.";
  }

  async function confirmDeposit() {
    const type = depositType();
    const asset = $("#deposit-asset").value;
    const amount = parseFloat($("#deposit-amount").value);
    if (!amount || amount <= 0) {
      toast("Enter a valid amount", true);
      return;
    }
    if (amount > 1e9) {
      toast("Amount too large for demo", true);
      return;
    }

    const btn = $("#confirm-deposit");
    btn.disabled = true;

    try {
      if (type === "crypto") {
        const snap = await api("/api/deposit/play", {
          method: "POST",
          body: JSON.stringify({ asset, amount }),
        });
        applySnapshot(snap);
        renderBalances();
        closeModal("deposit");
        toast(`Added ${formatAsset(asset, amount)} play money`);
        beep(660, 0.1, "sine", 0.05);
      } else {
        if (!stripeEnabled) {
          toast("Add a Stripe test key to enable checkout", true);
          return;
        }
        const data = await api("/api/deposit/checkout", {
          method: "POST",
          body: JSON.stringify({ currency: asset, amount }),
        });
        if (!data || !data.url) {
          throw new Error("Checkout did not return a URL");
        }
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
    if (!amount || amount <= 0) {
      toast("Enter a valid amount", true);
      return;
    }
    if (amount > bal + 1e-12) {
      toast("Amount exceeds available balance", true);
      return;
    }

    const btn = $("#confirm-withdraw");
    btn.hidden = true;
    $("#withdraw-processing").hidden = false;
    $("#withdraw-success").hidden = true;

    try {
      const snap = await api("/api/withdraw", {
        method: "POST",
        body: JSON.stringify({ asset, amount }),
      });
      applySnapshot(snap);
      renderBalances();
      $("#withdraw-processing").hidden = true;
      $("#withdraw-success").hidden = false;
      const status = (snap.withdrawal && snap.withdrawal.status) || "test withdrawal recorded";
      toast(`${formatAsset(asset, amount)} — ${status}`);
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
    $("#bet-up").addEventListener("click", () => {
      if (spinning) return;
      betIndex = Math.min(BET_STEPS_AUD.length - 1, betIndex + 1);
      savePrefs();
      renderBalances();
    });
    $("#bet-down").addEventListener("click", () => {
      if (spinning) return;
      betIndex = Math.max(0, betIndex - 1);
      savePrefs();
      renderBalances();
    });
    btnMute.addEventListener("click", () => {
      muted = !muted;
      savePrefs();
      renderBalances();
      if (!muted) {
        ensureAudio();
        beep(520, 0.08, "sine", 0.04);
      }
    });
    $("#btn-deposit").addEventListener("click", () => openModal("deposit"));
    $("#btn-withdraw").addEventListener("click", () => openModal("withdraw"));
    $("#btn-wallet").addEventListener("click", () => openModal("deposit"));

    displayCurrencySel.addEventListener("change", async () => {
      const previous = displayCurrency;
      displayCurrency = displayCurrencySel.value;
      savePrefs();
      renderBalances();
      try {
        const snap = await api("/api/prefs", {
          method: "POST",
          body: JSON.stringify({ display_currency: displayCurrency }),
        });
        applySnapshot(snap);
        renderBalances();
      } catch (err) {
        displayCurrency = previous;
        savePrefs();
        renderBalances();
        toast(err.message || "Could not update display currency", true);
      }
    });

    document.querySelectorAll("[data-close]").forEach((el) => {
      el.addEventListener("click", () => closeModal(el.dataset.close));
    });

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
      if (e.code === "Space" && !e.repeat) {
        const tag = (e.target && e.target.tagName) || "";
        if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
        e.preventDefault();
        spin();
      }
      if (e.key === "Escape") {
        closeModal("deposit");
        closeModal("withdraw");
      }
    });

    window.addEventListener("resize", () => {
      if (spinning) return;
      const h = SYMBOL_H();
      reelsEl.querySelectorAll(".reel").forEach((reel) => {
        const strip = reel.querySelector(".reel-strip");
        const count = strip.children.length;
        if (count >= VISIBLE_ROWS) {
          strip.style.transition = "none";
          strip.style.transform = `translateY(${-((count - VISIBLE_ROWS) * h)}px)`;
        }
      });
    });
  }

  // ---- Boot ----
  async function boot() {
    renderPaytable();
    initReels();
    renderBalances();
    wireEvents();
    try {
      await refreshBalance();
    } catch (err) {
      toast("Could not load the server ledger — is the Flask app running?", true);
    }
    ready = true;
  }

  boot();
})();
