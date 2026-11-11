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

  function chipLabel(n) {
    if (n >= 1000) return (n / 1000) + "K";
    return String(n);
  }

  function chipRack(extra) {
    return `<div class="chip-rack" role="group" aria-label="Chip denominations">
      ${CHIPS.map((n) => `<button type="button" class="chip c${n} ${n === chip ? "on" : ""}" data-chip="${n}" aria-label="${n.toLocaleString("en-US")} coins">
        <span class="chip-edge" aria-hidden="true"></span>
        <span class="chip-inlay">${chipLabel(n)}</span>
      </button>`).join("")}
    </div>${extra || ""}`;
  }

  function bindChips(root) {
    root.querySelectorAll("[data-chip]").forEach((b) => b.addEventListener("click", () => {
      chip = Number(b.dataset.chip);
      sfx("chip");
      root.querySelectorAll("[data-chip]").forEach((x) => x.classList.toggle("on", Number(x.dataset.chip) === chip));
    }));
  }

  function infoPanel(id, title, body) {
    return `<button type="button" class="info-btn" data-open-info="${id}" aria-label="Rules">?</button>
      <div class="game-info" id="${id}" hidden>
        <div class="game-info-card">
          <header><h3>${title}</h3><button type="button" class="icon-btn" data-close-info="${id}" aria-label="Close">✕</button></header>
          <div class="game-info-body">${body}</div>
        </div>
      </div>`;
  }

  function bindInfo(root) {
    root.querySelectorAll("[data-open-info]").forEach((b) => b.addEventListener("click", () => {
      const el = document.getElementById(b.dataset.openInfo);
      if (el) el.hidden = false;
    }));
    root.querySelectorAll("[data-close-info]").forEach((b) => b.addEventListener("click", () => {
      const el = document.getElementById(b.dataset.closeInfo);
      if (el) el.hidden = true;
    }));
    root.querySelectorAll(".game-info").forEach((el) => el.addEventListener("click", (e) => {
      if (e.target === el) el.hidden = true;
    }));
  }

  function resultBanner(text, kind, sub) {
    if (!text) return "";
    return `<div class="result-banner ${kind || ""}" id="result-banner">${text}${sub ? `<small>${sub}</small>` : ""}</div>`;
  }

  function breakdownTable(rows, net) {
    const body = rows.map((r) =>
      `<tr class="${r.status || ""}"><th>${r.name}</th><td class="st">${r.statusLabel}</td><td class="amt">${r.amount}</td></tr>`
    ).join("");
    const netCls = net > 0 ? "win" : net < 0 ? "lose" : "push";
    const netLab = net > 0 ? "+" + money(net) : net < 0 ? "−" + money(-net) : money(0);
    return `<table class="bet-break"><tbody>${body}</tbody>
      <tfoot><tr class="${netCls}"><th>Net</th><td></td><td class="amt">${netLab}</td></tr></tfoot></table>`;
  }

  function statusWord(s) {
    return ({ win: "Win", lose: "Lose", push: "Push", folded: "Folded", "—": "—" }[s] || s || "—");
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
    const banner = state.done ? resultBanner(
      (state.payout || 0) > (state.bet || 0) ? "YOU WIN" : (state.payout === (state.bet || 0) ? "PUSH" : "DEALER WINS"),
      (state.payout || 0) > (state.bet || 0) ? "win" : (state.payout === (state.bet || 0) ? "push" : "lose"),
      "Payout " + money(state.payout || 0)
    ) : "";
    const root = stage("Blackjack", `
      <div class="felt-table bj-table">
        <div class="dealer-spot">
          <div class="seat-label">Dealer</div>
          <div class="hand-meta">${state.dealer_total != null ? "Total " + state.dealer_total : " "}</div>
          <div class="hand" id="dealer-hand">${(state.dealer || []).map((c, n) => cardHTML(c, n)).join("")}</div>
        </div>
        <div class="player-spot"><div class="seat-label">You</div>${hands || `<div class="bj-hand"><div class="hand-meta"> </div><div class="hand"></div></div>`}</div>
        <div class="bet-circle" id="bj-circle"><span>${money(idle ? chip : (state.bet || lastBJ))}</span><small>ANTE</small></div>
        ${banner}
        <div class="table-msg" id="side-msg">${state.done ? "Payout " + money(state.payout || 0) : (state.hands ? "Hit, stand, or double." : "Place chips, then deal.")}</div>
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

  // ---- Roulette: 3D wheel + responsive felt ----
  let wheelAngle = 0;
  let ballAngle = 0;
  let wheelAnim = 0;

  const WHEEL_CX = 220, WHEEL_CY = 220;
  // Land the winning pocket at the near (bottom) edge, facing the player.
  const LAND_DEG = 180;
  const TRACK_Y = 40;   // SVG y: distance from top of viewBox = 180 from centre
  const POCKET_Y = 72;  // 148 from centre

  function bowlRingsHTML() {
    const layers = 16;
    const parts = [];
    for (let i = 0; i < layers; i++) {
      const t = i / (layers - 1);
      const z = (2 + t * 48).toFixed(1);
      const size = (92 + t * 8.5).toFixed(2);
      const isLip = t > 0.82;
      const cls = isLip ? "bowl-ring lip" : "bowl-ring";
      parts.push(`<div class="${cls}" style="width:${size}%;height:${size}%;transform:translate(-50%,-50%) translateZ(${z}px)"></div>`);
    }
    return `<div class="bowl-3d" aria-hidden="true">${parts.join("")}</div>`;
  }

  function turretHTML() {
    const discs = [
      { s: 49, z: 6, c: "base" },
      { s: 44, z: 14, c: "dark" },
      { s: 38, z: 22, c: "mid" },
      { s: 30, z: 30, c: "dark" },
      { s: 24, z: 38, c: "mid" },
      { s: 16, z: 46, c: "dark" },
      { s: 13, z: 54, c: "top" },
      { s: 6, z: 62, c: "cap" },
      { s: 3.2, z: 72, c: "spindle" },
    ];
    const discsH = discs.map((d) =>
      `<div class="t-disc ${d.c}" style="width:${d.s}%;height:${d.s}%;transform:translate(-50%,-50%) translateZ(${d.z}px)"></div>`
    ).join("");
    return `<div class="rl-turret" id="rl-turret" aria-hidden="true">
      ${discsH}
      <div class="t-handle a"></div>
      <div class="t-handle b"></div>
    </div>`;
  }

  function wheelHTML() {
    const cx = WHEEL_CX, cy = WHEEL_CY, n = WHEEL.length;
    const pockets = [];
    const frets = [];
    const numbers = [];
    for (let i = 0; i < n; i++) {
      const a0 = (i / n) * Math.PI * 2 - Math.PI / 2;
      const a1 = ((i + 1) / n) * Math.PI * 2 - Math.PI / 2;
      const num = WHEEL[i];
      const fill = num === 0 ? "url(#rlGreen)" : (REDS.has(num) ? "url(#rlRed)" : "url(#rlBlack)");
      const p = (a, rad) => [cx + Math.cos(a) * rad, cy + Math.sin(a) * rad];
      const R = 168, r = 114;
      const p0 = p(a0, R), p1 = p(a1, R), i0 = p(a0, r), i1 = p(a1, r);
      pockets.push(`<path d="M${i0[0].toFixed(2)},${i0[1].toFixed(2)} L${p0[0].toFixed(2)},${p0[1].toFixed(2)} A${R},${R} 0 0 1 ${p1[0].toFixed(2)},${p1[1].toFixed(2)} L${i1[0].toFixed(2)},${i1[1].toFixed(2)} A${r},${r} 0 0 0 ${i0[0].toFixed(2)},${i0[1].toFixed(2)}" fill="${fill}"/>`);
      frets.push(`<line x1="${i0[0].toFixed(2)}" y1="${i0[1].toFixed(2)}" x2="${p0[0].toFixed(2)}" y2="${p0[1].toFixed(2)}" stroke="url(#rlBrass)" stroke-width="1.6" stroke-linecap="round"/>`);
      const mid = (a0 + a1) / 2;
      const tx = cx + Math.cos(mid) * 147;
      const ty = cy + Math.sin(mid) * 147;
      const deg = mid * 180 / Math.PI + 90;
      numbers.push(`<text transform="rotate(${deg.toFixed(2)} ${tx.toFixed(2)} ${ty.toFixed(2)})" x="${tx.toFixed(2)}" y="${ty.toFixed(2)}" text-anchor="middle" dominant-baseline="middle" font-size="13" font-weight="800" fill="#fff" font-family="Inter, sans-serif">${num}</text>`);
    }
    const diamonds = [];
    for (let i = 0; i < 8; i++) {
      const a = (i / 8) * Math.PI * 2 - Math.PI / 2;
      const x = cx + Math.cos(a) * 180;
      const y = cy + Math.sin(a) * 180;
      const rot = a * 180 / Math.PI;
      diamonds.push(`<path transform="rotate(${rot.toFixed(1)} ${x.toFixed(1)} ${y.toFixed(1)})" d="M${x.toFixed(1)},${(y-6).toFixed(1)} L${(x+4.2).toFixed(1)},${y.toFixed(1)} L${x.toFixed(1)},${(y+6).toFixed(1)} L${(x-4.2).toFixed(1)},${y.toFixed(1)} Z" fill="url(#rlBrass)" stroke="#6b4a14" stroke-width=".4"/>`);
    }
    return `<div class="wheel-scene" id="wheel-scene">
      <div class="wheel-stage" id="wheel-stage">
        <div class="wheel-table-shadow"></div>
        ${bowlRingsHTML()}
        <div class="wheel-face">
          <svg viewBox="0 0 440 440" class="rl-wheel-svg" aria-hidden="true">
            <defs>
              <radialGradient id="rlWood" cx="50%" cy="40%" r="60%">
                <stop offset="0%" stop-color="#8a4e1a"/><stop offset="55%" stop-color="#5a2e0c"/><stop offset="100%" stop-color="#2a1406"/>
              </radialGradient>
              <linearGradient id="rlBrass" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#ffe9a8"/><stop offset="45%" stop-color="#d4a017"/><stop offset="100%" stop-color="#7a4e00"/>
              </linearGradient>
              <radialGradient id="rlTrack" cx="50%" cy="50%" r="50%">
                <stop offset="70%" stop-color="#1a1208"/><stop offset="85%" stop-color="#3a2a14"/><stop offset="100%" stop-color="#0c0804"/>
              </radialGradient>
              <radialGradient id="rlRed" cx="35%" cy="30%" r="75%">
                <stop offset="0%" stop-color="#ef4444"/><stop offset="100%" stop-color="#7f1d1d"/>
              </radialGradient>
              <radialGradient id="rlBlack" cx="35%" cy="30%" r="75%">
                <stop offset="0%" stop-color="#3f3f46"/><stop offset="100%" stop-color="#09090b"/>
              </radialGradient>
              <radialGradient id="rlGreen" cx="35%" cy="30%" r="75%">
                <stop offset="0%" stop-color="#22c55e"/><stop offset="100%" stop-color="#14532d"/>
              </radialGradient>
              <radialGradient id="rlTurret" cx="40%" cy="30%" r="70%">
                <stop offset="0%" stop-color="#f6cf55"/><stop offset="40%" stop-color="#b9800f"/><stop offset="100%" stop-color="#3a2400"/>
              </radialGradient>
              <radialGradient id="rlBall" cx="32%" cy="28%" r="70%">
                <stop offset="0%" stop-color="#fff"/><stop offset="55%" stop-color="#d4d4d8"/><stop offset="100%" stop-color="#52525b"/>
              </radialGradient>
            </defs>
            <circle cx="220" cy="220" r="214" fill="url(#rlWood)"/>
            <circle cx="220" cy="220" r="202" fill="none" stroke="url(#rlBrass)" stroke-width="10"/>
            <circle cx="220" cy="220" r="194" fill="none" stroke="#3a2400" stroke-width="2" opacity=".6"/>
            <circle cx="220" cy="220" r="186" fill="url(#rlTrack)"/>
            <circle cx="220" cy="220" r="170" fill="none" stroke="#d4a017" stroke-width="3"/>
            <g class="deflectors">${diamonds.join("")}</g>
            <g class="rl-rotor" id="rl-rotor">
              <circle cx="220" cy="220" r="168" fill="#1a1008"/>
              ${pockets.join("")}
              ${frets.join("")}
              ${numbers.join("")}
              <circle cx="220" cy="220" r="114" fill="none" stroke="url(#rlBrass)" stroke-width="3"/>
              <circle cx="220" cy="220" r="108" fill="#2a1800"/>
            </g>
            <g id="ball-arm" transform="rotate(0 220 220)">
              <g id="ball-rad" transform="translate(220, 40)">
                <circle r="8" fill="url(#rlBall)" stroke="#888" stroke-width=".4"/>
                <circle r="2.3" cx="-2" cy="-2.2" fill="#fff" opacity=".85"/>
              </g>
            </g>
          </svg>
        </div>
        ${turretHTML()}
        <div class="rl-pointer" aria-hidden="true"><span class="rl-pointer-fin"></span></div>
        <div class="wheel-light" aria-hidden="true"></div>
      </div>
    </div>`;
  }

  function normDeg(d) {
    const x = d % 360;
    return x < 0 ? x + 360 : x;
  }

  function setWheelPose(wDeg, bDeg, radius) {
    const rotor = $("#rl-rotor");
    const arm = $("#ball-arm");
    const rad = $("#ball-rad");
    const turret = $("#rl-turret");
    // Keep the SVG attribute in [0, 360) so CSS/SVG compositing stays stable.
    if (rotor) rotor.setAttribute("transform", `rotate(${normDeg(wDeg)} 220 220)`);
    if (arm) arm.setAttribute("transform", `rotate(${normDeg(bDeg)} 220 220)`);
    if (rad) rad.setAttribute("transform", `translate(220, ${radius})`);
    if (turret) turret.style.transform = `rotateZ(${normDeg(wDeg)}deg)`;
    wheelAngle = wDeg;
    ballAngle = bDeg;
  }

  function pocketWorldAngle(idx, wheelDeg) {
    const step = 360 / WHEEL.length;
    const local = (idx + 0.5) * step;
    return local + wheelDeg;
  }

  function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }
  function easeInOut(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; }

  function reduceMotion() {
    return document.documentElement.classList.contains("reduce-motion")
      || (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  function winningWheelAngle(result) {
    const idx = result.pocket != null ? result.pocket : WHEEL.indexOf(result.number);
    const step = 360 / WHEEL.length;
    return LAND_DEG - ((idx + 0.5) * step);
  }

  function showResultBadge(result) {
    const el = $("#rl-result");
    if (!el || !result || result.number == null) return;
    const col = result.colour || (result.number === 0 ? "green" : REDS.has(result.number) ? "red" : "black");
    el.className = "rl-result " + col + " show";
    el.hidden = false;
    el.innerHTML = `<span class="rl-num">${result.number}</span><small>${col.toUpperCase()}</small>`;
    const stage = $("#wheel-stage");
    if (stage && !reduceMotion()) stage.classList.add("settled");
  }

  function landRouletteImmediate(result) {
    setWheelPose(winningWheelAngle(result), LAND_DEG, POCKET_Y);
    showResultBadge(result);
  }

  function animateRoulette(result) {
    return new Promise((resolve) => {
      const finalLocal = winningWheelAngle(result);
      const stage = $("#wheel-stage");
      if (stage) stage.classList.remove("settled");
      if (reduceMotion()) {
        setWheelPose(finalLocal, LAND_DEG, POCKET_Y);
        showResultBadge(result);
        resolve();
        return;
      }
      const startW = wheelAngle;
      let travel = finalLocal - startW;
      while (travel > -360 * 5) travel -= 360;
      const endW = startW + travel;
      const startB = ballAngle;
      let bTravel = LAND_DEG - startB;
      while (bTravel < 360 * 7) bTravel += 360;
      const endB = startB + bTravel;
      const dur = 5200;
      const t0 = performance.now();
      if (wheelAnim) cancelAnimationFrame(wheelAnim);
      sfx("roulette");
      const tick = (now) => {
        const t = Math.min(1, (now - t0) / dur);
        const we = easeOutCubic(t);
        const be = easeOutCubic(Math.min(1, t * 1.02));
        const w = startW + (endW - startW) * we;
        const b = startB + (endB - startB) * be;
        let y = TRACK_Y;
        if (t > 0.62) {
          const u = (t - 0.62) / 0.38;
          const bounce = t < 0.86 ? Math.sin(u * Math.PI * 5) * (1 - u) * 10 : 0;
          y = TRACK_Y + (POCKET_Y - TRACK_Y) * easeInOut(u) + bounce;
        }
        setWheelPose(w, b, y);
        if (t < 1) wheelAnim = requestAnimationFrame(tick);
        else {
          setWheelPose(endW, endB, POCKET_Y);
          showResultBadge(result);
          resolve();
        }
      };
      wheelAnim = requestAnimationFrame(tick);
    });
  }

  function feltHTML() {
    // --dc/--dr = desktop column/row; --mc/--mr = mobile (portrait) column/row
    const nums = [];
    for (let n = 1; n <= 36; n++) {
      const colD = 1 + Math.ceil(n / 3);
      const rowD = 3 - ((n - 1) % 3);
      const colM = ((n - 1) % 3) + 1;
      const rowM = 1 + Math.ceil(n / 3);
      const cls = REDS.has(n) ? "nr" : "nb";
      nums.push(`<button type="button" class="${cls} felt-num" style="--dc:${colD};--dr:${rowD};--mc:${colM};--mr:${rowM}" data-kind="straight" data-n="${n}">${n}</button>`);
    }
    return `<div class="felt-eu" id="felt">
      <button type="button" class="n0" style="--dc:1;--dr:1;--mc:1;--mr:1" data-kind="straight" data-n="0">0</button>
      ${nums.join("")}
      <button type="button" class="ncol c3" style="--dc:14;--dr:1;--mc:1;--mr:14" data-kind="column" data-n="3" data-label="col3">2:1<span class="col-hint">3–36</span></button>
      <button type="button" class="ncol c2" style="--dc:14;--dr:2;--mc:2;--mr:14" data-kind="column" data-n="2">2:1<span class="col-hint">2–35</span></button>
      <button type="button" class="ncol c1" style="--dc:14;--dr:3;--mc:3;--mr:14" data-kind="column" data-n="1">2:1<span class="col-hint">1–34</span></button>
      <button type="button" class="nout d1" style="--dc:2;--dr:4;--mc:1;--mr:15" data-kind="dozen" data-n="1">1st 12<span class="col-hint">1–12</span></button>
      <button type="button" class="nout d2" style="--dc:6;--dr:4;--mc:2;--mr:15" data-kind="dozen" data-n="2">2nd 12<span class="col-hint">13–24</span></button>
      <button type="button" class="nout d3" style="--dc:10;--dr:4;--mc:3;--mr:15" data-kind="dozen" data-n="3">3rd 12<span class="col-hint">25–36</span></button>
      <button type="button" class="nout ev" style="--dc:2;--dr:5;--mc:1;--mr:16" data-kind="low">1–18</button>
      <button type="button" class="nout ev" style="--dc:4;--dr:5;--mc:2;--mr:16" data-kind="even">Even</button>
      <button type="button" class="nout ev nr" style="--dc:6;--dr:5;--mc:3;--mr:16" data-kind="red">Red</button>
      <button type="button" class="nout ev nb" style="--dc:8;--dr:5;--mc:1;--mr:17" data-kind="black">Black</button>
      <button type="button" class="nout ev" style="--dc:10;--dr:5;--mc:2;--mr:17" data-kind="odd">Odd</button>
      <button type="button" class="nout ev" style="--dc:12;--dr:5;--mc:3;--mr:17" data-kind="high">19–36</button>
    </div>`;
  }

  function historyHTML() {
    if (!rouletteHistory.length) return `<div class="rl-history empty">No spins yet</div>`;
    return `<div class="rl-history">${rouletteHistory.map((h) =>
      `<span class="${h.colour === "red" ? "nr" : h.colour === "black" ? "nb" : "ng"}">${h.number}</span>`
    ).join("")}</div>`;
  }

  function dozenNumbers(d) {
    const lo = (d - 1) * 12 + 1;
    return Array.from({ length: 12 }, (_, i) => lo + i);
  }

  function markFelt(root) {
    const scope = root || document;
    scope.querySelectorAll("#felt button").forEach((btn) => {
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
        badge.textContent = chipLabel(total) === String(total) ? String(total) : chipLabel(total);
      } else if (badge) badge.remove();
    });
  }

  function buildRouletteBet(btn) {
    const kind = btn.dataset.kind;
    const n = btn.dataset.n != null ? Number(btn.dataset.n) : undefined;
    const bet = { kind, amount: chip };
    if (kind === "straight") bet.number = n;
    if (kind === "dozen") { bet.dozen = n; bet.numbers = dozenNumbers(n); }
    if (kind === "column") bet.column = n;
    return bet;
  }

  function paintRoulette(result, opts) {
    const keepWheel = opts && opts.keepWheel;
    const stake = rouletteBets.reduce((s, b) => s + b.amount, 0);
    const msg = result && result.number != null
      ? "Winning number " + result.number + " · payout " + money(result.payout || 0)
      : (stake ? money(stake) + " on the table" : "Place chips, then spin.");
    if (keepWheel && $("#rl-rotor")) {
      const m = $("#side-msg"); if (m) m.textContent = msg;
      markFelt(document);
      historyMount();
      if (result && result.number != null && !opts.animating) showResultBadge(result);
      return $("#stage-body");
    }
    const root = stage("European Roulette", `
      <div class="felt-table rl-table">
        ${historyHTML()}
        <div class="roulette-wrap">
          <div class="wheel-box">${wheelHTML()}
            <div class="rl-result" id="rl-result" hidden></div>
          </div>
          <div class="felt-col">
            ${feltHTML()}
            <div class="table-msg" id="side-msg">${msg}</div>
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
    bindFelt(root);
    markFelt(root);
    if (result && result.number != null) landRouletteImmediate(result);
    else setWheelPose(wheelAngle, ballAngle, 40);
    return root;
  }

  function historyMount() {
    const old = document.querySelector(".rl-history");
    if (!old) return;
    const wrap = document.createElement("div");
    wrap.innerHTML = historyHTML();
    old.replaceWith(wrap.firstElementChild);
  }

  function bindFelt(root) {
    root.querySelectorAll("#felt button").forEach((btn) => btn.addEventListener("click", () => {
      rouletteBets.push(buildRouletteBet(btn));
      sfx("chip");
      markFelt(root);
      const msg = $("#side-msg");
      if (msg) msg.textContent = money(rouletteBets.reduce((s, b) => s + b.amount, 0)) + " on the table";
    }));
    $("#rl-undo").addEventListener("click", () => {
      rouletteBets.pop();
      markFelt(root);
      const msg = $("#side-msg");
      if (msg) msg.textContent = rouletteBets.length ? money(rouletteBets.reduce((s, b) => s + b.amount, 0)) + " on the table" : "Bets cleared.";
    });
    $("#rl-clear").addEventListener("click", () => {
      rouletteBets = [];
      markFelt(root);
      $("#side-msg").textContent = "Bets cleared.";
    });
    $("#rl-rebet").addEventListener("click", () => {
      if (!lastRoulette.length) { toast("No previous bets", true); return; }
      rouletteBets = lastRoulette.map((b) => ({ ...b }));
      sfx("chip");
      markFelt(root);
    });
    $("#rl-spin").addEventListener("click", spinRoulette);
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
      const badge = $("#rl-result"); if (badge) { badge.hidden = true; badge.classList.remove("show"); }
      const stg = $("#wheel-stage"); if (stg) stg.classList.remove("settled");
      historyMount();
      markFelt(document);
      const msg = $("#side-msg");
      if (msg) msg.textContent = "Spinning…";
      await animateRoulette(st);
      if (msg) msg.textContent = "Winning number " + st.number + " · payout " + money(st.payout || 0);
    } catch (err) { toast(err.message || "Failed", true); }
    finally { busy = false; }
  }

  function getRouletteBets() { return rouletteBets.slice(); }

  // ---- Video poker ----
  function paintVP(st) {
    const cards = (st && (st.cards || st.dealt)) || [null, null, null, null, null];
    const canDraw = st && !st.done && st.cards;
    const label = (st && (st.hand_label || (st.hand || "").replace(/_/g, " "))) || "";
    const banner = st && st.done ? resultBanner(
      st.result_banner || (st.result === "win" ? "YOU WIN" : st.result === "push" ? "PUSH" : "NO WIN"),
      st.result === "win" ? "win" : st.result === "push" ? "push" : "lose",
      (label ? label + " · " : "") + money(st.payout || 0)
    ) : "";
    const breakRows = st && st.done ? breakdownTable([
      { name: "Bet", status: "", statusLabel: "", amount: money(st.bet) },
      { name: "Returned", status: st.result, statusLabel: (st.hand_label || label || "—") + (st.mult ? " · " + st.mult + "×" : ""), amount: money(st.payout || 0) },
    ], (st.net != null ? st.net : (st.payout || 0) - (st.bet || 0))) : "";
    const root = stage("Video Poker — Jacks or Better", `
      <div class="felt-table vp-table">
        ${infoPanel("vp-info", "Jacks or Better · 9/6",
          `<p>Five-card draw. Hold any cards, then draw replacements. Jacks or better (a pair of Jacks, Queens, Kings or Aces) is the lowest paying hand. Pays are multiples of your bet returned, including the stake (Jacks or better pays 1× — a push).</p>
           <table class="pay-mini">${JOB_PAYS.map(([n, p]) => `<tr><th>${n}</th><td>${p}</td></tr>`).join("")}</table>`)}
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
            <div class="hand-name">${st && !st.done && label ? label : ""}</div>
            ${banner}
            ${breakRows}
            <div class="table-msg step-prompt" id="side-msg">${
              st && st.done ? ""
              : (canDraw ? "Tap cards to hold, then Draw." : "Choose a bet and Deal.")
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
    bindInfo(root);
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
    const done = st && st.done;
    const pLabel = st && (st.player_hand_label || (st.player_hand || "").replace(/_/g, " "));
    const dLabel = done && (st.dealer_hand_label || (st.dealer_hand || "").replace(/_/g, " "));
    let prompt = "Place Ante (and optional Pair Plus), then Deal.";
    if (waiting) prompt = "Play (match Ante) or Fold?";
    if (done) prompt = "";
    const hint = waiting
      ? (st.hint_play
        ? "Hint: this hand meets Q-6-4 — typically Play."
        : "Hint: below Q-6-4 — typically Fold.")
      : (!st ? "Optional hint: play with Queen-6-4 or better." : "");
    const qual = done ? `<div class="qual-badge ${st.dealer_qualifies ? "yes" : "no"}">
        ${st.dealer_qualifies ? "QUALIFIES" : "DOES NOT QUALIFY"}
        <small>Dealer qualifies with Queen high</small>
      </div>` : `<div class="qual-badge idle"><small>Dealer qualifies with Queen high</small></div>`;
    const kind = st && st.result === "lose" ? "lose" : st && st.result === "tie" ? "push" : st && st.result === "fold" ? "fold" : "win";
    const banner = done ? resultBanner(st.result_banner || "RESULT", kind, done && pLabel && dLabel ? `You: ${pLabel} · Dealer: ${dLabel}` : "") : "";
    const rows = done ? breakdownTable([
      { name: "Ante", status: st.ante_status, statusLabel: statusWord(st.ante_status), amount: st.ante_payout != null ? money(st.ante_payout) : "—" },
      { name: "Play", status: st.play_status, statusLabel: statusWord(st.play_status), amount: st.played ? money(st.play_payout || 0) : "—" },
      { name: "Pair Plus", status: st.pair_plus_status, statusLabel: statusWord(st.pair_plus_status), amount: st.pair_plus ? money(st.pair_plus_payout || 0) : "—" },
      { name: "Ante bonus", status: st.ante_bonus ? "win" : "", statusLabel: st.ante_bonus ? "Win" : "—", amount: money(st.ante_bonus || 0) },
    ], st.net != null ? st.net : (st.payout || 0) - (st.ante || 0) - (st.pair_plus || 0) - (st.play || 0)) : "";
    const root = stage("Three Card Poker", `
      <div class="felt-table tcp-table">
        ${infoPanel("tcp-info", "Three Card Poker",
          `<p>Place an Ante (and an optional Pair Plus). You get three cards, then Play (match the Ante) or Fold (lose the Ante; Pair Plus can still pay).</p>
           <p>The dealer qualifies with Queen high or better. If the dealer does not qualify, Ante pays 1:1 and Play pushes. If the dealer qualifies, the better hand wins Ante and Play at 1:1. Ties push.</p>
           <p>Ante bonus (if you Play): Straight flush 5:1, Three of a kind 4:1, Straight 1:1 — paid even if the dealer wins.</p>
           <p>Pair Plus pays independently: Pair 1:1, Flush 4:1, Straight 6:1, Three of a kind 30:1, Straight flush 40:1.</p>
           <p>Strategy hint: Play with Q-6-4 or better; otherwise Fold.</p>`)}
        <div class="seat dealer-spot">
          <div class="seat-label">Dealer</div>
          ${qual}
          <div class="hand">${((st && st.dealer) || []).map((c, i) => cardHTML(c, i)).join("")}</div>
          <div class="hand-name">${dLabel || (waiting ? "Waiting…" : "")}</div>
        </div>
        ${banner}
        <div class="seat player-spot">
          <div class="seat-label">You</div>
          <div class="hand">${((st && st.player) || []).map((c, i) => cardHTML(c, i)).join("")}</div>
          <div class="hand-name">${pLabel || ""}</div>
        </div>
        <div class="tcp-spots">
          <div class="bet-circle ${tcpPP ? "on" : ""}" id="tcp-pp"><span>${money(tcpPP)}</span><small>PAIR PLUS</small></div>
          <div class="bet-circle on" id="tcp-ante"><span>${money(tcpAnte)}</span><small>ANTE</small></div>
          <div class="bet-circle ${st && st.play ? "on" : ""}" id="tcp-play"><span>${st && st.play ? money(st.play) : "—"}</span><small>PLAY</small></div>
        </div>
        ${rows}
        <div class="table-msg step-prompt" id="side-msg">${prompt}</div>
        ${hint ? `<p class="strategy-hint">${hint}</p>` : ""}
        ${chipRack(`<div class="actions-row">
          ${waiting
            ? `<button type="button" class="btn btn-gold" id="tcp-play-btn">Play</button>
               <button type="button" class="btn btn-outline" id="tcp-fold">Fold</button>`
            : `<button type="button" class="btn btn-gold" id="tcp-deal">Deal</button>
               <button type="button" class="btn btn-outline" id="tcp-pp-toggle">${tcpPP ? "Clear Pair Plus" : "Add Pair Plus"}</button>`}
        </div>`)}
      </div>`, "#/poker");
    bindChips(root);
    bindInfo(root);
    const ante = $("#tcp-ante");
    if (ante && !waiting && !done) ante.addEventListener("click", () => { tcpAnte = chip; sfx("chip"); paintTCP(st); });
    const pp = $("#tcp-pp");
    if (pp && !waiting && !done) pp.addEventListener("click", () => { tcpPP = tcpPP ? 0 : chip; sfx("chip"); paintTCP(st); });
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
      const st = res.result || res;
      paintTCP(st);
      if (st.done) {
        document.querySelectorAll(".tcp-table .dealer-spot .pcard:not(.back)").forEach((el, i) => {
          el.classList.add("flip");
          el.style.animationDelay = (i * 90) + "ms";
        });
      }
    } catch (err) { toast(err.message || "Failed", true); }
    finally { busy = false; }
  }

  // ---- Casino War ----
  function warBanner(st) {
    if (!st) return "";
    if (st.awaiting_war) return resultBanner("TIE", "push", "Surrender half, or go to war (match the ante).");
    const map = {
      win: ["YOU WIN", "win"],
      lose: ["DEALER WINS", "lose"],
      war_win: ["YOU WIN THE WAR", "win"],
      war_lose: ["DEALER WINS THE WAR", "lose"],
      war_tie: ["PUSH", "push"],
      surrender: ["SURRENDERED", "fold"],
    };
    const pair = map[st.result] || [String(st.result || "").replace(/_/g, " ").toUpperCase(), ""];
    return resultBanner(pair[0], pair[1], money(st.payout || 0) + " returned");
  }

  function warBreakdown(st) {
    if (!st || (!st.done && !st.awaiting_war)) return "";
    const ante = st.bet || 0;
    const raise = st.raise || (st.war ? ante : 0);
    if (st.awaiting_war) {
      return breakdownTable([
        { name: "Ante", status: "push", statusLabel: "Tie", amount: money(ante) + " at risk" },
      ], 0);
    }
    const rows = [];
    if (st.result === "win") rows.push({ name: "Ante", status: "win", statusLabel: "Win 1:1", amount: money(ante * 2) });
    else if (st.result === "lose") rows.push({ name: "Ante", status: "lose", statusLabel: "Lose", amount: money(0) });
    else if (st.result === "surrender") rows.push({ name: "Ante", status: "lose", statusLabel: "Half back", amount: money(st.payout || 0) });
    else if (st.result === "war_win") {
      rows.push({ name: "Ante", status: "push", statusLabel: "Push", amount: money(ante) });
      rows.push({ name: "War raise", status: "win", statusLabel: "Win 1:1", amount: money(raise * 2) });
    } else if (st.result === "war_lose") {
      rows.push({ name: "Ante", status: "lose", statusLabel: "Lose", amount: money(0) });
      rows.push({ name: "War raise", status: "lose", statusLabel: "Lose", amount: money(0) });
    } else if (st.result === "war_tie") {
      rows.push({ name: "Ante", status: "push", statusLabel: "Push", amount: money(ante) });
      rows.push({ name: "War raise", status: "push", statusLabel: "Push", amount: money(raise) });
    }
    const spent = ante + (st.war ? raise : 0);
    const net = (st.payout || 0) - spent;
    return breakdownTable(rows, net);
  }

  function paintWar(st) {
    const root = stage("Casino War", `
      <div class="felt-table war-table">
        ${infoPanel("war-info", "Casino War",
          `<p>You and the dealer each get one card from a 6-deck shoe. Higher card wins 1:1 (Ace is high).</p>
           <p>On a tie, Surrender (half the ante is returned) or Go to war (match the ante). Three cards are burned, then one more card each. A war win pays 1:1 on the raise; the original ante pushes. A tie on war pushes both bets.</p>`)}
        <div class="war-row">
          <div class="war-spot seat">
            <div class="seat-label">You</div>
            <div class="hand">${st && st.player ? cardHTML(st.player, 0) : ""}</div>
            <div class="hand-name">${st && st.player ? st.player.rank : ""}</div>
            ${st && st.player_war ? `<div class="hand-meta">War</div><div class="hand">${cardHTML(st.player_war, 1)}</div><div class="hand-name">${st.player_war.rank}</div>` : ""}
          </div>
          <div class="war-spot seat">
            <div class="seat-label">Dealer</div>
            <div class="hand">${st && st.dealer ? cardHTML(st.dealer, 0) : ""}</div>
            <div class="hand-name">${st && st.dealer ? st.dealer.rank : ""}</div>
            ${st && st.dealer_war ? `<div class="hand-meta">War</div><div class="hand">${cardHTML(st.dealer_war, 1)}</div><div class="hand-name">${st.dealer_war.rank}</div>` : ""}
          </div>
        </div>
        <div class="bet-circle on"><span>${money(st && st.bet ? st.bet : chip)}</span><small>ANTE</small></div>
        ${warBanner(st)}
        ${warBreakdown(st)}
        <div class="table-msg step-prompt" id="side-msg">${
          st && st.awaiting_war ? "Tie — Surrender half, or Go to war (match the bet)."
          : (st && st.done ? "" : "Place a bet and Deal. Higher card wins even money.")
        }</div>
        ${chipRack(`<div class="actions-row">
          ${st && st.awaiting_war
            ? `<button type="button" class="btn btn-gold" id="war-go">Go to war</button>
               <button type="button" class="btn btn-outline" id="war-surrender">Surrender</button>`
            : `<button type="button" class="btn btn-gold" id="war-deal">Deal</button>`}
        </div>`)}
      </div>`);
    bindChips(root);
    bindInfo(root);
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

  window.CrystalShell = { go, apply, start, refreshHud, renderLobby, getRouletteBets, buildRouletteBet };
  wireShell();
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => { /* start() is called from app.js after ledger load */ });
})();
