/**
 * Crystal Casino v7 shell: home, game floor, hash routing, and full-screen tables.
 * Outcomes come from the server; this file only animates them. Coins have no cash value.
 */
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const CC = () => window.CrystalCasino;

  const REDS = new Set([1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]);
  const WHEEL = [0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26];
  const CHIPS = [100, 500, 1000, 5000, 10000, 25000, 50000];
  const SUIT = { hearts: "♥", diamonds: "♦", clubs: "♣", spades: "♠" };

  const TILES = [
    { id: "slots", name: "Crystal Slots", cat: "Slots", tag: "Megaways & 25-line classic · ~95% RTP", glyph: "💎" },
    { id: "roulette", name: "European Roulette", cat: "Table Games", tag: "Single zero · 2.70% house edge", glyph: "🎡" },
    { id: "blackjack", name: "Blackjack", cat: "Card Games", tag: "3:2 · stand soft 17 · 6-deck", glyph: "🂡" },
    { id: "poker", name: "Poker", cat: "Card Games", tag: "Video Poker & Three Card Poker", glyph: "♠" },
    { id: "war", name: "Casino War", cat: "Card Games", tag: "Higher card wins · war on a tie · 6-deck", glyph: "⚔" },
    { id: "highcard", name: "High Card", cat: "Card Games", tag: "Higher card 1:1 · tie push or war", glyph: "🃏" },
    { id: "mines", name: "Crystal Mines", cat: "Instant/Mini", tag: "Cash out anytime · ~4% house edge", glyph: "◆" },
    { id: "scratch", name: "Dragon Scratch", cat: "Instant/Mini", tag: "Scratch card · ~95% RTP", glyph: "🐉" },
    { id: "dice", name: "Lucky Dice", cat: "Instant/Mini", tag: "2d6 duel · tie is a push", glyph: "🎲" },
  ];
  const CATS = ["Slots", "Table Games", "Card Games", "Instant/Mini"];
  const FEATURED = ["roulette", "blackjack", "poker", "war"];

  const JOB_PAYS = [
    ["Royal Flush", "800×"], ["Straight Flush", "50×"], ["Four of a Kind", "25×"],
    ["Full House", "9×"], ["Flush", "6×"], ["Straight", "4×"],
    ["Three of a Kind", "3×"], ["Two Pair", "2×"], ["Jacks or Better", "1×"],
  ];

  let chip = 1000;
  let busy = false;
  let currentPath = "/home";
  let rouletteBets = [];
  let lastRoulette = [];
  let rouletteHistory = [];
  let lastBJ = 1000;
  let minesCount = 3;
  let vpHolds = [false, false, false, false, false];
  let tcpAnte = 1000;
  let tcpPP = 0;

  function money(n) { return CC() ? CC().money(n) : String(n); }
  function sfx(name, ...a) { const s = CC() && CC().sfx; if (s && s[name]) s[name](...a); }
  function toast(msg, err) { if (CC() && CC().toast) CC().toast(msg, err); }
  async function api(path, body) {
    return CC().api(path, { method: "POST", body: JSON.stringify(body || {}) });
  }
  function applyCoins(res) { if (res && CC() && CC().applySnapshot) CC().applySnapshot(res); }

  function parsePath() {
    const raw = (location.hash || "").replace(/^#/, "");
    const path = raw.startsWith("/") ? raw : "/" + raw;
    if (!path || path === "/") return "/home";
    return path.replace(/\/+$/, "") || "/home";
  }

  function go(path) {
    if (!path.startsWith("/")) path = "/" + path;
    const hash = "#" + path;
    if (location.hash !== hash) location.hash = hash;
    else apply();
  }

  async function leaveTable() {
    if (CC()) {
      try { await CC().api("/api/side/cancel", { method: "POST", body: "{}" }); } catch (e) { /* none */ }
    }
    rouletteBets = [];
    vpHolds = [false, false, false, false, false];
  }

  async function apply() {
    const path = parsePath();
    const prev = currentPath;
    const tablePaths = new Set(["/roulette","/blackjack","/war","/highcard","/mines","/scratch","/dice","/videopoker","/threecard","/poker/video","/poker/three"]);
    if (tablePaths.has(prev) && prev !== path) await leaveTable();
    currentPath = path;

    let view = "home";
    if (path === "/slots") view = "slots";
    else if (path === "/lobby" || path === "/games") view = "lobby";
    else if (path === "/home" || path === "/") view = "home";
    else view = "table";

    document.body.classList.toggle("view-home", view === "home");
    document.body.classList.toggle("view-lobby", view === "lobby");
    document.body.classList.toggle("view-slots", view === "slots");
    document.body.classList.toggle("view-table", view === "table");

    const home = $("#home"), lobby = $("#lobby"), stage = $("#game-stage");
    if (home) home.hidden = view !== "home";
    if (lobby) lobby.hidden = view !== "lobby";
    if (stage) stage.hidden = view !== "table";

    $$(".view-nav button").forEach((b) => {
      const r = b.dataset.route || b.dataset.view;
      b.classList.toggle("active", (r === "home" && view === "home") || (r === "lobby" && (view === "lobby" || view === "table")));
    });

    if (view === "lobby") renderLobby();
    if (view === "home") renderHomeFeatures();
    if (view === "table") openRoute(path);
  }

  function openRoute(path) {
    if (path === "/roulette") paintRoulette({});
    else if (path === "/blackjack") paintBJ({});
    else if (path === "/poker") paintPokerMenu();
    else if (path === "/videopoker" || path === "/poker/video") paintVP(null);
    else if (path === "/threecard" || path === "/poker/three") paintTCP(null);
    else if (path === "/war") paintWar(null);
    else if (path === "/highcard") paintHigh(null);
    else if (path === "/mines") paintMines(null);
    else if (path === "/scratch") paintScratch(null);
    else if (path === "/dice") paintDice(null);
    else go("/lobby");
  }

  function start() {
    if (!location.hash) location.hash = "#/home";
    else apply();
  }

  function refreshHud(s) {
    if (!s) return;
    if (s.profile) {
      const nick = s.profile.nickname || "Hopper";
      const lvl = s.profile.level || 1;
      const vip = (s.profile.vip && s.profile.vip.name) || "Bronze";
      const vipId = (s.profile.vip && s.profile.vip.id) || "bronze";
      const hn = $("#home-nick"); if (hn) hn.textContent = nick;
      const hl = $("#home-level"); if (hl) hl.textContent = "LV " + lvl;
      const hv = $("#home-vip");
      if (hv) { hv.textContent = String(vip).toUpperCase(); hv.className = "vip-badge " + vipId; }
    }
    if (s.bonuses) {
      const dailyReady = !!s.bonuses.daily_available;
      const hourlyReady = !!s.bonuses.hourly_available;
      $$(".js-daily").forEach((b) => { b.classList.toggle("ready", dailyReady); b.classList.toggle("claimed", !dailyReady); b.disabled = !dailyReady; });
      $$(".js-hourly").forEach((b) => { b.classList.toggle("ready", hourlyReady); b.classList.toggle("claimed", !hourlyReady); b.disabled = !hourlyReady; });
      $$(".daily-home-label").forEach((el) => { el.textContent = dailyReady ? "BONUS" : "CLAIMED"; });
      $$(".hourly-home-label").forEach((el) => { el.textContent = hourlyReady ? "BONUS" : "WAIT"; });
    }
  }

  function renderHomeFeatures() {
    const row = $("#home-features");
    if (!row) return;
    row.innerHTML = FEATURED.map((id) => {
      const g = TILES.find((t) => t.id === id);
      return `<a class="feature-tile" href="#/${g.id}" data-game="${g.id}">
        <span class="glyph">${g.glyph}</span><h3>${g.name}</h3><p>${g.tag}</p>
      </a>`;
    }).join("");
  }

  function renderLobby() {
    const grid = $("#lobby-grid");
    if (!grid) return;
    grid.innerHTML = CATS.map((cat) => {
      const tiles = TILES.filter((t) => t.cat === cat).map((g) =>
        `<a class="lobby-card lobby-tile" href="#/${g.id}" data-game="${g.id}">
          <span class="glyph">${g.glyph}</span><h3>${g.name}</h3><p>${g.tag}</p>
        </a>`
      ).join("");
      return `<div class="lobby-cat"><h3 class="cat-label">${cat}</h3><div class="lobby-grid">${tiles}</div></div>`;
    }).join("");
  }

  function stage(title, html, backHref) {
    const t = $("#stage-title"); if (t) t.textContent = title;
    const back = $("#btn-stage-back");
    if (back) back.setAttribute("href", backHref || "#/lobby");
    const body = $("#stage-body");
    if (body) body.innerHTML = html;
    return body;
  }

  function cardHTML(c, i) {
    if (!c || c.hidden || c.suit === "back") {
      return `<div class="pcard back" style="animation-delay:${(i||0)*70}ms"><span class="r">✦</span><span class="s">✦</span></div>`;
    }
    const red = c.colour === "red" || c.suit === "hearts" || c.suit === "diamonds";
    const suit = SUIT[c.suit] || c.suit;
    return `<div class="pcard ${red ? "red" : ""}" style="animation-delay:${(i||0)*70}ms"><span class="r">${c.rank}</span><span class="s">${suit}</span></div>`;
  }

  function chipRack(extra) {
    return `<div class="chip-rack" role="group" aria-label="Chip denominations">
      ${CHIPS.map((n) => `<button type="button" class="chip c${n} ${n === chip ? "on" : ""}" data-chip="${n}">${money(n)}</button>`).join("")}
    </div>${extra || ""}`;
  }

  function bindChips(root) {
    root.querySelectorAll("[data-chip]").forEach((b) => b.addEventListener("click", () => {
      chip = Number(b.dataset.chip);
      sfx("chip");
      root.querySelectorAll("[data-chip]").forEach((x) => x.classList.toggle("on", Number(x.dataset.chip) === chip));
    }));
  }

  // ---- Poker submenu ----
  function paintPokerMenu() {
    stage("Poker", `
      <div class="poker-menu">
        <a class="lobby-tile poker-pick" href="#/videopoker">
          <span class="glyph">♚</span>
          <h3>Video Poker</h3>
          <p>Jacks or Better · 9/6 full-pay paytable. Hold and draw five cards.</p>
        </a>
        <a class="lobby-tile poker-pick" href="#/threecard">
          <span class="glyph">♛</span>
          <h3>Three Card Poker</h3>
          <p>Ante/Play + Pair Plus. Dealer qualifies Queen-high.</p>
        </a>
      </div>`, "#/lobby");
  }

  // ---- Blackjack ----
  function paintBJ(state) {
    const hands = (state.hands || []).map((h, i) => {
      const act = state.active === i && !state.done ? " active" : "";
      return `<div class="bj-hand${act}">
        <div class="hand-meta">You${act ? " · playing" : ""} · ${h.total || ""}${h.result ? " · " + h.result : ""} · bet ${money(h.bet)}</div>
        <div class="hand">${(h.cards || []).map((c, n) => cardHTML(c, n)).join("")}</div>
      </div>`;
    }).join("");
    const can = new Set(state.can || []);
    const acts = ["hit","stand","double","split","insurance","no_insurance"]
      .filter((a) => can.has(a))
      .map((a) => `<button type="button" class="btn ${a==="hit"||a==="stand"?"btn-gold":"btn-outline"}" data-act="${a}">${a.replace("_", " ")}</button>`)
      .join("");
    const idle = state.done || !state.hands;
    const root = stage("Blackjack", `
      <div class="felt-table bj-table">
        <div class="dealer-spot">
          <div class="hand-meta">Dealer${state.dealer_total != null ? " · " + state.dealer_total : ""}</div>
          <div class="hand" id="dealer-hand">${(state.dealer || []).map((c, n) => cardHTML(c, n)).join("")}</div>
        </div>
        <div class="player-spot">${hands || `<div class="bj-hand"><div class="hand-meta">You</div><div class="hand"></div></div>`}</div>
        <div class="bet-circle" id="bj-circle"><span>${money(idle ? chip : (state.bet || lastBJ))}</span><small>ANTE</small></div>
        <div class="table-msg" id="side-msg">${state.done ? "Payout " + money(state.payout || 0) : (state.hands ? "Your play." : "Place chips, then deal.")}</div>
        ${chipRack(`<div class="actions-row">
          ${idle ? `<button type="button" class="btn btn-gold" id="bj-deal">Deal</button>
                    <button type="button" class="btn btn-outline" id="bj-rebet">Rebet</button>` : acts}
        </div>`)}
      </div>`);
    bindChips(root);
    const deal = $("#bj-deal");
    if (deal) deal.addEventListener("click", () => bjAct("deal", chip));
    const rebet = $("#bj-rebet");
    if (rebet) rebet.addEventListener("click", () => bjAct("deal", lastBJ));
    root.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => bjAct(b.dataset.act)));
    const circle = $("#bj-circle");
    if (circle && idle) circle.addEventListener("click", () => { sfx("chip"); /* denomination already selected */ });
  }

  async function bjAct(action, betAmt) {
    if (busy) return;
    busy = true;
    try {
      sfx(action === "deal" ? "chip" : "card");
      const body = action === "deal" ? { action: "deal", bet: betAmt || chip } : { action };
      const res = await api("/api/side/blackjack", body);
      applyCoins(res);
      if (action === "deal") lastBJ = betAmt || chip;
      paintBJ(res.result || res.session || res);
    } catch (err) { toast(err.message || "Failed", true); }
    finally { busy = false; }
  }

  // ---- Roulette ----
  function wheelSVG() {
    const n = WHEEL.length, cx = 160, cy = 160, R = 150, r = 48;
    let wedges = "";
    WHEEL.forEach((num, i) => {
      const a0 = (i / n) * Math.PI * 2 - Math.PI / 2;
      const a1 = ((i + 1) / n) * Math.PI * 2 - Math.PI / 2;
      const fill = num === 0 ? "#15803d" : REDS.has(num) ? "#b91c1c" : "#111";
      const p = (a, rad) => [cx + Math.cos(a) * rad, cy + Math.sin(a) * rad];
      const p0 = p(a0, R), p1 = p(a1, R), i0 = p(a0, r), i1 = p(a1, r);
      const mid = p((a0 + a1) / 2, 102);
      wedges += `<path d="M${i0[0]},${i0[1]} L${p0[0]},${p0[1]} A${R},${R} 0 0 1 ${p1[0]},${p1[1]} L${i1[0]},${i1[1]} A${r},${r} 0 0 0 ${i0[0]},${i0[1]}" fill="${fill}" stroke="#fbe08a" stroke-width=".5"/>
        <text x="${mid[0]}" y="${mid[1]}" text-anchor="middle" dominant-baseline="middle" font-size="10" fill="#fff" font-weight="700">${num}</text>`;
    });
    return `<svg viewBox="0 0 320 320" class="wheel-svg">
      <g class="wheel-rotor" id="wheel-rotor">${wedges}<circle cx="160" cy="160" r="44" fill="#1a0d00" stroke="#f3c441" stroke-width="4"/></g>
      <polygon points="160,8 170,28 150,28" fill="#f3c441"/>
    </svg><div class="ball-orbit" id="ball-orbit"><span class="ball-dot" id="ball-dot"></span></div>`;
  }

  function feltHTML() {
    const nums = [];
    for (let col = 1; col <= 12; col++) {
      for (let row = 3; row >= 1; row--) {
        const n = (col - 1) * 3 + row;
        const cls = REDS.has(n) ? "nr" : "nb";
        nums.push(`<button type="button" class="${cls}" style="grid-column:${col+1};grid-row:${4-row}" data-kind="straight" data-n="${n}">${n}</button>`);
      }
    }
    return `<div class="felt-eu" id="felt">
      <button type="button" class="n0" data-kind="straight" data-n="0">0</button>
      ${nums.join("")}
      <button type="button" class="ncol" style="grid-column:14;grid-row:1" data-kind="column" data-n="3">2:1</button>
      <button type="button" class="ncol" style="grid-column:14;grid-row:2" data-kind="column" data-n="2">2:1</button>
      <button type="button" class="ncol" style="grid-column:14;grid-row:3" data-kind="column" data-n="1">2:1</button>
      <button type="button" class="nout" style="grid-column:2/6;grid-row:4" data-kind="dozen" data-n="1">1st 12</button>
      <button type="button" class="nout" style="grid-column:6/10;grid-row:4" data-kind="dozen" data-n="2">2nd 12</button>
      <button type="button" class="nout" style="grid-column:10/14;grid-row:4" data-kind="dozen" data-n="3">3rd 12</button>
      <button type="button" class="nout" style="grid-column:2/4;grid-row:5" data-kind="low">1–18</button>
      <button type="button" class="nout" style="grid-column:4/6;grid-row:5" data-kind="even">Even</button>
      <button type="button" class="nout nr" style="grid-column:6/8;grid-row:5" data-kind="red">Red</button>
      <button type="button" class="nout nb" style="grid-column:8/10;grid-row:5" data-kind="black">Black</button>
      <button type="button" class="nout" style="grid-column:10/12;grid-row:5" data-kind="odd">Odd</button>
      <button type="button" class="nout" style="grid-column:12/14;grid-row:5" data-kind="high">19–36</button>
    </div>`;
  }

  function historyHTML() {
    if (!rouletteHistory.length) return `<div class="rl-history empty">No spins yet</div>`;
    return `<div class="rl-history">${rouletteHistory.map((h) =>
      `<span class="${h.colour === "red" ? "nr" : h.colour === "black" ? "nb" : "ng"}">${h.number}</span>`
    ).join("")}</div>`;
  }

  function betKey(b) {
    return [b.kind, b.number, b.dozen, b.column, b.n].join(":");
  }

  function markFelt(root) {
    root.querySelectorAll("#felt button").forEach((btn) => {
      const kind = btn.dataset.kind;
      const n = btn.dataset.n != null ? Number(btn.dataset.n) : null;
      const total = rouletteBets.filter((b) => {
        if (b.kind !== kind) return false;
        if (kind === "straight") return b.number === n;
        if (kind === "dozen") return b.dozen === n;
        if (kind === "column") return b.column === n;
        return true;
      }).reduce((s, b) => s + b.amount, 0);
      btn.classList.toggle("on", total > 0);
      let badge = btn.querySelector(".chip-badge");
      if (total > 0) {
        if (!badge) { badge = document.createElement("span"); badge.className = "chip-badge"; btn.appendChild(badge); }
        badge.textContent = money(total);
      } else if (badge) badge.remove();
    });
  }

  function paintRoulette(result) {
    const stake = rouletteBets.reduce((s, b) => s + b.amount, 0);
    const root = stage("European Roulette", `
      <div class="felt-table rl-table">
        ${historyHTML()}
        <div class="roulette-wrap">
          <div class="wheel-box">${wheelSVG()}</div>
          <div class="felt-col">
            ${feltHTML()}
            <div class="table-msg" id="side-msg">${
              result && result.number != null
                ? "Winning number " + result.number + " · payout " + money(result.payout || 0)
                : (stake ? money(stake) + " on the table" : "Place chips, then spin.")
            }</div>
          </div>
        </div>
        ${chipRack(`<div class="actions-row">
          <button type="button" class="btn btn-gold" id="rl-spin">Spin</button>
          <button type="button" class="btn btn-outline" id="rl-undo">Undo</button>
          <button type="button" class="btn btn-outline" id="rl-clear">Clear</button>
          <button type="button" class="btn btn-outline" id="rl-rebet">Rebet</button>
        </div>`)}
      </div>`);
    bindChips(root);
    markFelt(root);
    root.querySelectorAll("#felt button").forEach((btn) => btn.addEventListener("click", () => {
      const kind = btn.dataset.kind;
      const n = btn.dataset.n != null ? Number(btn.dataset.n) : undefined;
      const bet = { kind, amount: chip };
      if (kind === "straight") bet.number = n;
      if (kind === "dozen") bet.dozen = n;
      if (kind === "column") bet.column = n;
      rouletteBets.push(bet);
      sfx("chip");
      markFelt(root);
      $("#side-msg").textContent = money(rouletteBets.reduce((s, b) => s + b.amount, 0)) + " on the table";
    }));
    $("#rl-undo").addEventListener("click", () => { rouletteBets.pop(); markFelt(root); });
    $("#rl-clear").addEventListener("click", () => { rouletteBets = []; markFelt(root); $("#side-msg").textContent = "Bets cleared."; });
    $("#rl-rebet").addEventListener("click", () => {
      if (!lastRoulette.length) { toast("No previous bets", true); return; }
      rouletteBets = lastRoulette.map((b) => ({ ...b }));
      sfx("chip");
      markFelt(root);
    });
    $("#rl-spin").addEventListener("click", spinRoulette);
    if (result && result.number != null) landRoulette(result);
  }

  function landRoulette(result) {
    const idx = result.pocket != null ? result.pocket : WHEEL.indexOf(result.number);
    const rotor = $("#wheel-rotor");
    const orbit = $("#ball-orbit");
    if (!rotor) return;
    const n = WHEEL.length;
    const deg = 360 * 6 + (360 - (idx + 0.5) * (360 / n));
    rotor.style.transition = "transform 4.2s cubic-bezier(.15,.7,.05,1)";
    rotor.style.transform = `rotate(${deg}deg)`;
    if (orbit) {
      orbit.style.transition = "transform 4.2s cubic-bezier(.05,.6,.05,1)";
      orbit.style.transform = `rotate(${-(deg + 18)}deg)`;
    }
    sfx("roulette");
  }

  async function spinRoulette() {
    if (busy) return;
    if (!rouletteBets.length) { toast("Place a bet first", true); return; }
    busy = true;
    try {
      lastRoulette = rouletteBets.map((b) => ({ ...b }));
      const res = await api("/api/side/roulette", { bets: rouletteBets });
      applyCoins(res);
      const st = res.result;
      rouletteHistory.unshift({ number: st.number, colour: st.colour || (st.number === 0 ? "green" : REDS.has(st.number) ? "red" : "black") });
      rouletteHistory = rouletteHistory.slice(0, 16);
      rouletteBets = [];
      paintRoulette(st);
    } catch (err) { toast(err.message || "Failed", true); }
    finally { busy = false; }
  }

  // ---- Video poker ----
  function paintVP(st) {
    const cards = (st && (st.cards || st.dealt)) || [null, null, null, null, null];
    const canDraw = st && !st.done && st.cards;
    const root = stage("Video Poker — Jacks or Better", `
      <div class="felt-table vp-table">
        <div class="vp-layout">
          <ol class="vp-pays">${JOB_PAYS.map(([n, p]) =>
            `<li class="${st && st.hand === n.toLowerCase().replace(/ /g, "_") ? "hit" : ""}"><span>${n}</span><b>${p}</b></li>`
          ).join("")}</ol>
          <div>
            <div class="hand vp-hand" id="vp-hand">${cards.map((c, i) => `
              <button type="button" class="vp-card ${vpHolds[i] ? "held" : ""}" data-i="${i}" ${canDraw ? "" : "disabled"}>
                ${cardHTML(c, i)}
                <span class="hold-tag">${vpHolds[i] ? "HOLD" : "HOLD?"}</span>
              </button>`).join("")}
            </div>
            <div class="table-msg" id="side-msg">${
              st && st.done ? ((st.hand || "nothing").replace(/_/g, " ") + " · " + money(st.payout || 0))
              : (canDraw ? "Tap cards to hold, then draw." : "Choose a bet and deal.")
            }</div>
            ${chipRack(`<div class="actions-row">
              ${canDraw
                ? `<button type="button" class="btn btn-gold" id="vp-draw">Draw</button>`
                : `<button type="button" class="btn btn-gold" id="vp-deal">Deal</button>`}
            </div>`)}
          </div>
        </div>
      </div>`, "#/poker");
    bindChips(root);
    root.querySelectorAll(".vp-card").forEach((b) => b.addEventListener("click", () => {
      if (!canDraw) return;
      const i = Number(b.dataset.i);
      vpHolds[i] = !vpHolds[i];
      sfx("chip");
      paintVP(st);
    }));
    const deal = $("#vp-deal");
    if (deal) deal.addEventListener("click", vpDeal);
    const draw = $("#vp-draw");
    if (draw) draw.addEventListener("click", vpDraw);
  }

  async function vpDeal() {
    if (busy) return; busy = true;
    try {
      sfx("chip");
      vpHolds = [false, false, false, false, false];
      const res = await api("/api/side/videopoker", { action: "deal", bet: chip });
      applyCoins(res);
      sfx("card");
      paintVP(res.result || res);
    } catch (err) { toast(err.message || "Failed", true); }
    finally { busy = false; }
  }

  async function vpDraw() {
    if (busy) return; busy = true;
    try {
      const res = await api("/api/side/videopoker", { action: "draw", holds: vpHolds });
      applyCoins(res);
      sfx("card");
      paintVP(res.result || res);
    } catch (err) { toast(err.message || "Failed", true); }
    finally { busy = false; }
  }

  // ---- Three Card Poker ----
  function paintTCP(st) {
    const waiting = st && !st.done && st.player;
    const root = stage("Three Card Poker", `
      <div class="felt-table tcp-table">
        <div class="dealer-spot">
          <div class="hand-meta">Dealer${st && st.done && st.dealer_hand ? " · " + st.dealer_hand.replace(/_/g, " ") : ""}${st && st.done && !st.dealer_qualifies ? " · does not qualify" : ""}</div>
          <div class="hand">${((st && st.dealer) || []).map((c, i) => cardHTML(c, i)).join("")}</div>
        </div>
        <div class="player-spot">
          <div class="hand-meta">You${st && st.player_hand ? " · " + String(st.player_hand).replace(/_/g, " ") : ""}</div>
          <div class="hand">${((st && st.player) || []).map((c, i) => cardHTML(c, i)).join("")}</div>
        </div>
        <div class="tcp-spots">
          <div class="bet-circle ${tcpPP ? "on" : ""}" id="tcp-pp"><span>${money(tcpPP)}</span><small>PAIR PLUS</small></div>
          <div class="bet-circle on" id="tcp-ante"><span>${money(tcpAnte)}</span><small>ANTE</small></div>
          <div class="bet-circle" id="tcp-play"><span>${st && st.play ? money(st.play) : "—"}</span><small>PLAY</small></div>
        </div>
        <div class="table-msg" id="side-msg">${
          st && st.done ? (String(st.result || "").replace(/_/g, " ") + " · payout " + money(st.payout || 0))
          : (waiting ? "Play (match the ante) or fold." : "Set Ante and optional Pair Plus, then deal. Dealer qualifies Queen-high.")
        }</div>
        ${chipRack(`<div class="actions-row">
          ${waiting
            ? `<button type="button" class="btn btn-gold" id="tcp-play-btn">Play</button>
               <button type="button" class="btn btn-outline" id="tcp-fold">Fold</button>`
            : `<button type="button" class="btn btn-gold" id="tcp-deal">Deal</button>
               <button type="button" class="btn btn-outline" id="tcp-pp-toggle">${tcpPP ? "Clear Pair Plus" : "Add Pair Plus"}</button>`}
        </div>`)}
      </div>`, "#/poker");
    bindChips(root);
    const ante = $("#tcp-ante");
    if (ante && !waiting) ante.addEventListener("click", () => { tcpAnte = chip; sfx("chip"); paintTCP(st); });
    const pp = $("#tcp-pp");
    if (pp && !waiting) pp.addEventListener("click", () => { tcpPP = tcpPP ? 0 : chip; sfx("chip"); paintTCP(st); });
    const tog = $("#tcp-pp-toggle");
    if (tog) tog.addEventListener("click", () => { tcpPP = tcpPP ? 0 : chip; sfx("chip"); paintTCP(st); });
    const deal = $("#tcp-deal");
    if (deal) deal.addEventListener("click", () => tcpAct("deal"));
    const play = $("#tcp-play-btn");
    if (play) play.addEventListener("click", () => tcpAct("play"));
    const fold = $("#tcp-fold");
    if (fold) fold.addEventListener("click", () => tcpAct("fold"));
  }

  async function tcpAct(action) {
    if (busy) return; busy = true;
    try {
      sfx(action === "deal" ? "chip" : "card");
      const body = action === "deal" ? { action: "deal", ante: tcpAnte, pair_plus: tcpPP } : { action };
      const res = await api("/api/side/threecard", body);
      applyCoins(res);
      paintTCP(res.result || res);
    } catch (err) { toast(err.message || "Failed", true); }
    finally { busy = false; }
  }

  // ---- Casino War ----
  function paintWar(st) {
    const root = stage("Casino War", `
      <div class="felt-table war-table">
        <div class="war-row">
          <div class="war-spot"><div class="hand-meta">You</div><div class="hand">${st && st.player ? cardHTML(st.player, 0) : ""}</div>
            ${st && st.player_war ? `<div class="hand-meta">War</div><div class="hand">${cardHTML(st.player_war, 1)}</div>` : ""}</div>
          <div class="war-spot"><div class="hand-meta">Dealer</div><div class="hand">${st && st.dealer ? cardHTML(st.dealer, 0) : ""}</div>
            ${st && st.dealer_war ? `<div class="hand-meta">War</div><div class="hand">${cardHTML(st.dealer_war, 1)}</div>` : ""}</div>
        </div>
        <div class="bet-circle on"><span>${money(st && st.bet ? st.bet : chip)}</span><small>ANTE</small></div>
        <div class="table-msg" id="side-msg">${
          st && st.awaiting_war ? "Tie — surrender half, or go to war (match the bet). A war win pays 1:1 on the raise; the original ante pushes."
          : (st ? (String(st.result || "").replace(/_/g, " ") + " · " + money(st.payout || 0))
                : "Higher card wins even money. Ties: surrender half or go to war.")
        }</div>
        ${chipRack(`<div class="actions-row">
          ${st && st.awaiting_war
            ? `<button type="button" class="btn btn-gold" id="war-go">Go to war</button>
               <button type="button" class="btn btn-outline" id="war-surrender">Surrender</button>`
            : `<button type="button" class="btn btn-gold" id="war-deal">Deal</button>`}
        </div>`)}
      </div>`);
    bindChips(root);
    const deal = $("#war-deal");
    if (deal) deal.addEventListener("click", () => warAct("deal"));
    const goBtn = $("#war-go");
    if (goBtn) goBtn.addEventListener("click", () => warAct("war"));
    const sur = $("#war-surrender");
    if (sur) sur.addEventListener("click", () => warAct("surrender"));
  }

  async function warAct(action) {
    if (busy) return; busy = true;
    try {
      sfx(action === "deal" ? "chip" : "card");
      const body = action === "deal" ? { action: "deal", bet: chip } : { action };
      const res = await api("/api/side/war", body);
      applyCoins(res);
      paintWar(res.result || res);
    } catch (err) { toast(err.message || "Failed", true); }
    finally { busy = false; }
  }

  // ---- High card / mines / scratch / dice (full-stage versions) ----
  function paintHigh(st) {
    const root = stage("High Card", `
      <div class="felt-table">
        <div class="war-row">
          <div class="war-spot"><div class="hand-meta">You</div><div class="hand">${st && st.player ? cardHTML(st.player, 0) : ""}</div></div>
          <div class="war-spot"><div class="hand-meta">Dealer</div><div class="hand">${st && st.dealer ? cardHTML(st.dealer, 0) : ""}</div></div>
        </div>
        <div class="table-msg">${st ? (st.result + " · " + money(st.payout || 0)) : "Higher card wins even money. Ties can be pushed or taken to war."}</div>
        ${chipRack(`<div class="actions-row">
          ${st && st.awaiting_war
            ? `<button type="button" class="btn btn-gold" id="hc-war">War</button><button type="button" class="btn btn-outline" id="hc-push">Push</button>`
            : `<button type="button" class="btn btn-gold" id="hc-play">Play</button>`}
        </div>`)}
      </div>`);
    bindChips(root);
    const play = $("#hc-play"); if (play) play.addEventListener("click", () => hcPlay("deal"));
    const war = $("#hc-war"); if (war) war.addEventListener("click", () => hcPlay("war"));
    const push = $("#hc-push"); if (push) push.addEventListener("click", () => hcPlay("push"));
  }

  async function hcPlay(action) {
    if (busy) return; busy = true;
    try {
      sfx("card");
      const body = action === "deal" ? { bet: chip, war_option: true } : { action };
      const res = await api("/api/side/highcard", body);
      applyCoins(res);
      paintHigh(res.result);
    } catch (err) { toast(err.message || "Failed", true); }
    finally { busy = false; }
  }

  function paintDice(st) {
    const die = (n) => `<div class="die">${n || "?"}</div>`;
    const root = stage("Lucky Dice", `
      <div class="felt-table">
        <div class="dice-pair">
          <div>${(st && st.player ? st.player : [0, 0]).map(die).join("")}<div class="hint">You ${st && st.player_total != null ? st.player_total : ""}</div></div>
          <div>${(st && st.dealer ? st.dealer : [0, 0]).map(die).join("")}<div class="hint">Dealer ${st && st.dealer_total != null ? st.dealer_total : ""}</div></div>
        </div>
        <div class="table-msg">${st ? st.result + " · " + money(st.payout || 0) : "Roll 2d6 against the dealer. Higher total wins even money; ties push."}</div>
        ${chipRack(`<div class="actions-row"><button type="button" class="btn btn-gold" id="dc-play">Roll</button></div>`)}
      </div>`);
    bindChips(root);
    $("#dc-play").addEventListener("click", async () => {
      if (busy) return; busy = true;
      try {
        sfx("dice");
        const res = await api("/api/side/dice", { bet: chip });
        applyCoins(res);
        paintDice(res.result);
      } catch (err) { toast(err.message || "Failed", true); }
      finally { busy = false; }
    });
  }

  function paintMines(st) {
    const picks = new Set((st && st.picks) || []);
    const bombs = new Set((st && st.done && st.bombs) || []);
    const cells = Array.from({ length: 25 }, (_, i) => {
      const last = st && st.picks && st.picks[st.picks.length - 1];
      const cls = picks.has(i) ? (bombs.has(i) || (st && st.boom && i === last) ? "bomb" : "safe") : "";
      const label = picks.has(i) ? (cls === "bomb" ? "💥" : "✦") : "";
      return `<button type="button" class="${cls}" data-tile="${i}" ${st && !st.done ? "" : "disabled"}>${label}</button>`;
    }).join("");
    const minePick = [1,2,3,4,5].map((n) => `<button type="button" data-mines="${n}" class="${n === minesCount ? "on" : ""}">${n} mines</button>`).join("");
    const root = stage("Crystal Mines", `
      <div class="felt-table">
        <div class="mines-grid">${cells}</div>
        <div class="table-msg">${st ? (st.boom ? "Mine! " : (st.done ? "Cashed out " : "Multiplier ")) + (st.done ? money(st.payout || 0) : ((st.multiplier || 1).toFixed(2) + "× · next " + (st.next_multiplier != null ? Number(st.next_multiplier).toFixed(2) : "—") + "×")) : "Pick safe crystals, then cash out. Hitting a mine loses the bet."}</div>
        ${chipRack(`<div class="bet-row" style="margin:.6rem 0">${minePick}</div>
          <div class="actions-row">${!st || st.done ? `<button type="button" class="btn btn-gold" id="mn-start">Start</button>` : `<button type="button" class="btn btn-gold" id="mn-cash">Cash out</button>`}</div>`)}
      </div>`);
    bindChips(root);
    root.querySelectorAll("[data-mines]").forEach((b) => b.addEventListener("click", () => {
      minesCount = Number(b.dataset.mines);
      root.querySelectorAll("[data-mines]").forEach((x) => x.classList.toggle("on", Number(x.dataset.mines) === minesCount));
    }));
    const startBtn = $("#mn-start"); if (startBtn) startBtn.addEventListener("click", () => minesAct("start"));
    const cash = $("#mn-cash"); if (cash) cash.addEventListener("click", () => minesAct("cashout"));
    root.querySelectorAll("[data-tile]").forEach((b) => b.addEventListener("click", () => minesAct("pick", Number(b.dataset.tile))));
  }

  async function minesAct(action, tile) {
    if (busy) return; busy = true;
    try {
      sfx("chip");
      const body = action === "start" ? { action: "start", bet: chip, mines: minesCount } : { action, tile };
      const res = await api("/api/side/mines", body);
      applyCoins(res);
      paintMines(res.result);
    } catch (err) { toast(err.message || "Failed", true); }
    finally { busy = false; }
  }

  function paintScratch(st) {
    const cells = Array.from({ length: 9 }, (_, i) => {
      const sym = st && st.grid ? st.grid[i] : "";
      return `<button type="button" data-i="${i}" class="${st ? "revealed" : ""}">${st ? (sym || "").slice(0, 8) : "✦"}</button>`;
    }).join("");
    const root = stage("Dragon Scratch", `
      <div class="felt-table">
        <div class="scratch-grid" id="scratch-grid">${cells}</div>
        <div class="table-msg" id="side-msg">${st ? ("Prize " + money(st.payout || 0) + (st.mult ? " · " + st.mult + "×" : "")) : "Buy a card and scratch. Prize is decided on the server first — the card is honest."}</div>
        ${chipRack(`<div class="actions-row"><button type="button" class="btn btn-gold" id="sc-play">Buy card</button></div>`)}
      </div>`);
    bindChips(root);
    $("#sc-play").addEventListener("click", async () => {
      if (busy) return; busy = true;
      try {
        const res = await api("/api/side/scratch", { bet: chip });
        applyCoins(res);
        const r = res.result;
        const grid = $("#scratch-grid");
        grid.querySelectorAll("button").forEach((b) => { b.className = ""; b.textContent = "✦"; });
        for (const i of r.reveal_order || []) {
          sfx("scratch");
          const b = grid.querySelector(`[data-i="${i}"]`);
          if (b) { b.classList.add("revealed"); b.textContent = (r.grid[i] || "").slice(0, 8); }
          await sleep(160);
        }
        $("#side-msg").textContent = "Prize " + money(r.payout || 0) + (r.mult ? " · " + r.mult + "×" : "");
      } catch (err) { toast(err.message || "Failed", true); }
      finally { busy = false; }
    });
  }

  function wireShell() {
    window.addEventListener("hashchange", () => apply());
    $$(".view-nav button").forEach((b) => {
      // app.js also binds setView; that's fine — it calls go().
    });
    document.body.addEventListener("click", (e) => {
      const daily = e.target.closest(".js-daily");
      if (daily && CC() && CC().claimDaily) { e.preventDefault(); CC().claimDaily(); }
      const hourly = e.target.closest(".js-hourly");
      if (hourly && CC() && CC().claimHourly) { e.preventDefault(); CC().claimHourly(); }
      const shop = e.target.closest(".js-shop");
      if (shop && CC() && CC().openShop) { e.preventDefault(); CC().openShop(); }
      const prizes = e.target.closest(".js-prizes");
      if (prizes && CC() && CC().openPrizes) { e.preventDefault(); CC().openPrizes(); }
    });
  }

  window.CrystalShell = { go, apply, start, refreshHud, renderLobby };
  wireShell();
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => { /* start() is called from app.js after ledger load */ });
})();
