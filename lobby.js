/**
 * Crystal Casino side-games lobby. Outcomes come from the server;
 * this file only animates them. Coins have no cash value.
 */
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const CC = () => window.CrystalCasino;
  const GAMES = [
    { id: "blackjack", name: "Blackjack", glyph: "🂡", tag: "3:2 · stand soft 17 · 6-deck" },
    { id: "roulette", name: "European Roulette", glyph: "🎡", tag: "Single zero · 2.70% house edge" },
    { id: "highcard", name: "High Card", glyph: "🃏", tag: "Higher card wins 1:1 · tie push or war" },
    { id: "mines", name: "Crystal Mines", glyph: "💎", tag: "Cash out anytime · ~4% house edge" },
    { id: "scratch", name: "Dragon Scratch", glyph: "🐉", tag: "Scratch card · ~95% RTP" },
    { id: "dice", name: "Lucky Dice", glyph: "🎲", tag: "2d6 duel · tie is a push" },
  ];

  let bet = 1000;
  let betsList = [100, 200, 500, 1000, 2000, 5000, 10000, 25000];
  let current = null;
  let busy = false;
  let rouletteBets = [];
  let minesCount = 3;

  function money(n) { return CC() ? CC().money(n) : String(n); }
  function sfx(name, ...a) { const s = CC() && CC().sfx; if (s && s[name]) s[name](...a); }
  async function api(path, body) {
    return CC().api(path, { method: "POST", body: JSON.stringify(body || {}) });
  }

  function renderGrid() {
    const grid = $("#lobby-grid");
    if (!grid) return;
    grid.innerHTML = GAMES.map((g) =>
      `<button type="button" class="lobby-card" data-game="${g.id}">
        <span class="glyph">${g.glyph}</span><h3>${g.name}</h3><p>${g.tag}</p>
      </button>`
    ).join("");
    grid.querySelectorAll(".lobby-card").forEach((b) => b.addEventListener("click", () => openGame(b.dataset.game)));
  }

  function betPicker(extra = "") {
    return `<div class="bet-row" id="side-bets">
      <span>Bet</span>
      ${betsList.map((n) => `<button type="button" data-bet="${n}" class="${n === bet ? "on" : ""}">${money(n)}</button>`).join("")}
      ${extra}
    </div>`;
  }

  function bindBets(root) {
    root.querySelectorAll("[data-bet]").forEach((b) => {
      b.addEventListener("click", () => {
        bet = Number(b.dataset.bet);
        root.querySelectorAll("[data-bet]").forEach((x) => x.classList.toggle("on", Number(x.dataset.bet) === bet));
      });
    });
  }

  function showTable(html) {
    const table = $("#lobby-table");
    const grid = $("#lobby-grid");
    table.hidden = false;
    grid.hidden = true;
    table.innerHTML = html;
  }

  async function closeTable(forfeit = true) {
    current = null;
    rouletteBets = [];
    if (forfeit && CC()) {
      try { await CC().api("/api/side/cancel", { method: "POST", body: "{}" }); } catch (e) { /* no session */ }
    }
    const table = $("#lobby-table");
    const grid = $("#lobby-grid");
    table.hidden = true;
    table.innerHTML = "";
    grid.hidden = false;
  }

  function applyCoins(res) {
    if (res && CC() && CC().applySnapshot) CC().applySnapshot(res);
  }

  function cardHTML(c) {
    if (!c || c.hidden || c.suit === "back") return `<div class="pcard back"><span class="r">✦</span><span class="s">✦</span></div>`;
    const red = c.colour === "red" || c.suit === "hearts" || c.suit === "diamonds";
    const suit = { hearts: "♥", diamonds: "♦", clubs: "♣", spades: "♠" }[c.suit] || c.suit;
    return `<div class="pcard ${red ? "red" : ""}"><span class="r">${c.rank}</span><span class="s">${suit}</span></div>`;
  }

  // ---- Blackjack ----
  function paintBJ(state) {
    const hands = (state.hands || []).map((h, i) => {
      const act = state.active === i && !state.done ? " (playing)" : "";
      return `<div>
        <small>You${act} · ${h.total || ""}${h.result ? " · " + h.result : ""} · bet ${money(h.bet)}</small>
        <div class="hand">${(h.cards || []).map(cardHTML).join("")}</div>
      </div>`;
    }).join("");
    const can = new Set(state.can || []);
    const acts = ["hit", "stand", "double", "split", "insurance", "no_insurance"]
      .filter((a) => can.has(a))
      .map((a) => `<button type="button" data-act="${a}">${a.replace("_", " ")}</button>`)
      .join("");
    showTable(`
      <div class="table-top"><h3>Blackjack</h3>${betPicker()}
        <button type="button" class="btn btn-outline" id="side-close">Close</button></div>
      <small>Dealer${state.dealer_total != null ? " · " + state.dealer_total : ""}</small>
      <div class="hand" id="dealer-hand">${(state.dealer || []).map(cardHTML).join("")}</div>
      ${hands || "<div class='hand'></div>"}
      <div class="table-msg" id="side-msg">${state.done ? "Payout " + money(state.payout || 0) : "Place a bet and deal."}</div>
      <div class="actions-row">
        ${state.done || !state.hands ? `<button type="button" class="btn btn-gold" id="bj-deal">Deal</button>` : acts}
      </div>`);
    bindBets($("#lobby-table"));
    $("#side-close").addEventListener("click", closeTable);
    const deal = $("#bj-deal");
    if (deal) deal.addEventListener("click", () => bjAct("deal"));
    $("#lobby-table").querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => bjAct(b.dataset.act)));
  }

  async function bjAct(action) {
    if (busy) return;
    busy = true;
    try {
      sfx("chip");
      const res = await api("/api/side/blackjack", action === "deal" ? { action: "deal", bet } : { action });
      applyCoins(res);
      const st = res.result || res.session || res;
      current = "blackjack";
      sfx("card");
      paintBJ(st);
    } catch (err) {
      CC() && CC().toast(err.message || "Failed", true);
    } finally { busy = false; }
  }

  // ---- Roulette ----
  function wheelSVG(order) {
    const n = order.length, cx = 130, cy = 130, R = 124, r = 42;
    let wedges = "";
    order.forEach((num, i) => {
      const a0 = (i / n) * Math.PI * 2 - Math.PI / 2;
      const a1 = ((i + 1) / n) * Math.PI * 2 - Math.PI / 2;
      const colour = num === 0 ? "#15803d" : (window._rouge || new Set()).has ? "" : "";
      const isRed = [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36].includes(num);
      const fill = num === 0 ? "#15803d" : isRed ? "#b91c1c" : "#111";
      const p = (a, rad) => [cx + Math.cos(a) * rad, cy + Math.sin(a) * rad];
      const p0 = p(a0, R), p1 = p(a1, R), i0 = p(a0, r), i1 = p(a1, r);
      const mid = p((a0 + a1) / 2, 86);
      wedges += `<path d="M${i0[0]},${i0[1]} L${p0[0]},${p0[1]} A${R},${R} 0 0 1 ${p1[0]},${p1[1]} L${i1[0]},${i1[1]} A${r},${r} 0 0 0 ${i0[0]},${i0[1]}" fill="${fill}" stroke="#fbe08a" stroke-width=".4"/>
        <text x="${mid[0]}" y="${mid[1]}" text-anchor="middle" dominant-baseline="middle" font-size="9" fill="#fff" font-weight="700">${num}</text>`;
    });
    return `<svg viewBox="0 0 260 260"><g class="wheel-rotor" id="wheel-rotor">${wedges}<circle cx="130" cy="130" r="38" fill="#1a0d00" stroke="#f3c441" stroke-width="3"/></g>
      <polygon points="130,8 138,26 122,26" fill="#f3c441"/></svg>`;
  }

  function paintRoulette(result) {
    const order = (result && result.wheel) || [0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26];
    const nums = Array.from({ length: 36 }, (_, i) => i + 1);
    const felt = `<div class="felt" id="felt">
      <button type="button" class="n0" data-n="0">0</button>
      ${nums.map((n) => {
        const red = [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36].includes(n);
        return `<button type="button" class="${red ? "nr" : "nb"}" data-n="${n}">${n}</button>`;
      }).join("")}
    </div>
    <div class="bet-row" style="margin-top:.6rem">
      ${["red","black","odd","even","low","high"].map((k) => `<button type="button" data-out="${k}">${k}</button>`).join("")}
      ${[1,2,3].map((d) => `<button type="button" data-out="dozen:${d}">D${d}</button>`).join("")}
    </div>`;
    showTable(`
      <div class="table-top"><h3>European Roulette</h3>${betPicker()}
        <button type="button" class="btn btn-outline" id="side-close">Close</button></div>
      <div class="roulette-wrap">
        <div class="wheel-box">${wheelSVG(order)}<div class="ball-dot" id="ball-dot"></div></div>
        <div>${felt}
          <div class="table-msg" id="side-msg">${result && result.number != null ? "Winning number " + result.number + " · payout " + money(result.payout) : "Click numbers or even-money bets, then spin."}</div>
          <div class="actions-row"><button type="button" class="btn btn-gold" id="rl-spin">Spin</button>
          <button type="button" class="btn btn-outline" id="rl-clear">Clear bets</button></div>
        </div>
      </div>`);
    bindBets($("#lobby-table"));
    $("#side-close").addEventListener("click", closeTable);
    $("#felt").querySelectorAll("[data-n]").forEach((b) => b.addEventListener("click", () => {
      const n = Number(b.dataset.n);
      rouletteBets.push({ kind: "straight", number: n, amount: bet });
      b.classList.add("on");
      sfx("chip");
      $("#side-msg").textContent = `${rouletteBets.length} bet${rouletteBets.length > 1 ? "s" : ""} on the table`;
    }));
    $("#lobby-table").querySelectorAll("[data-out]").forEach((b) => b.addEventListener("click", () => {
      const v = b.dataset.out;
      if (v.startsWith("dozen:")) rouletteBets.push({ kind: "dozen", dozen: Number(v.split(":")[1]), amount: bet });
      else rouletteBets.push({ kind: v, amount: bet });
      b.classList.add("on");
      sfx("chip");
    }));
    $("#rl-clear").addEventListener("click", () => { rouletteBets = []; paintRoulette({}); });
    $("#rl-spin").addEventListener("click", spinRoulette);
    if (result && result.number != null) landRoulette(result);
  }

  function landRoulette(result) {
    const order = result.wheel;
    const n = order.length;
    const idx = result.pocket;
    const rotor = $("#wheel-rotor");
    if (!rotor) return;
    const deg = 360 * 6 + (360 - (idx + 0.5) * (360 / n));
    rotor.style.transition = "transform 4.2s cubic-bezier(.15,.7,.05,1)";
    rotor.style.transform = `rotate(${deg}deg)`;
    sfx("roulette");
  }

  async function spinRoulette() {
    if (busy) return;
    if (!rouletteBets.length) { CC() && CC().toast("Place a bet first", true); return; }
    busy = true;
    try {
      const res = await api("/api/side/roulette", { bets: rouletteBets });
      applyCoins(res);
      const st = res.result;
      rouletteBets = [];
      paintRoulette(st);
    } catch (err) {
      CC() && CC().toast(err.message || "Failed", true);
    } finally { busy = false; }
  }

  // ---- High card / dice ----
  function paintHigh(st) {
    showTable(`
      <div class="table-top"><h3>High Card</h3>${betPicker()}
        <button type="button" class="btn btn-outline" id="side-close">Close</button></div>
      <div class="hand" style="justify-content:center;gap:2rem">
        <div><small>You</small>${st && st.player ? cardHTML(st.player) : ""}</div>
        <div><small>Dealer</small>${st && st.dealer ? cardHTML(st.dealer) : ""}</div>
      </div>
      <div class="table-msg">${st ? (st.result + " · " + money(st.payout || 0)) : "Higher card wins even money. Ties can be pushed or taken to war."}</div>
      <div class="actions-row">
        ${st && st.awaiting_war
          ? `<button type="button" class="btn btn-gold" id="hc-war">War</button><button type="button" class="btn btn-outline" id="hc-push">Push</button>`
          : `<button type="button" class="btn btn-gold" id="hc-play">Play</button>`}
      </div>`);
    bindBets($("#lobby-table"));
    $("#side-close").addEventListener("click", closeTable);
    const play = $("#hc-play");
    if (play) play.addEventListener("click", () => hcPlay("deal"));
    const war = $("#hc-war"); if (war) war.addEventListener("click", () => hcPlay("war"));
    const push = $("#hc-push"); if (push) push.addEventListener("click", () => hcPlay("push"));
  }

  async function hcPlay(action) {
    if (busy) return;
    busy = true;
    try {
      sfx("card");
      const body = action === "deal" ? { bet, war_option: true } : { action };
      const res = await api("/api/side/highcard", body);
      applyCoins(res);
      paintHigh(res.result);
    } catch (err) { CC() && CC().toast(err.message || "Failed", true); }
    finally { busy = false; }
  }

  function paintDice(st) {
    const die = (n) => `<div class="die">${n || "?"}</div>`;
    showTable(`
      <div class="table-top"><h3>Lucky Dice</h3>${betPicker()}
        <button type="button" class="btn btn-outline" id="side-close">Close</button></div>
      <div class="dice-pair"><div>${(st && st.player ? st.player : [0,0]).map(die).join("")}<div class="hint">You ${st && st.player_total != null ? st.player_total : ""}</div></div>
        <div>${(st && st.dealer ? st.dealer : [0,0]).map(die).join("")}<div class="hint">Dealer ${st && st.dealer_total != null ? st.dealer_total : ""}</div></div></div>
      <div class="table-msg">${st ? st.result + " · " + money(st.payout || 0) : "Roll 2d6 against the dealer. Higher total wins even money; ties push."}</div>
      <div class="actions-row"><button type="button" class="btn btn-gold" id="dc-play">Roll</button></div>`);
    bindBets($("#lobby-table"));
    $("#side-close").addEventListener("click", closeTable);
    $("#dc-play").addEventListener("click", async () => {
      if (busy) return; busy = true;
      try {
        sfx("dice");
        const res = await api("/api/side/dice", { bet });
        applyCoins(res);
        paintDice(res.result);
      } catch (err) { CC() && CC().toast(err.message || "Failed", true); }
      finally { busy = false; }
    });
  }

  function paintMines(st) {
    const picks = new Set(st && st.picks || []);
    const bombs = new Set((st && st.done && st.bombs) || []);
    const cells = Array.from({ length: 25 }, (_, i) => {
      const cls = picks.has(i) ? (bombs.has(i) || (st && st.boom && i === (st.picks || []).slice(-1)[0]) ? "bomb" : "safe") : "";
      const label = picks.has(i) ? (cls === "bomb" ? "💥" : "✦") : "";
      return `<button type="button" class="${cls}" data-tile="${i}" ${st && !st.done ? "" : "disabled"}>${label}</button>`;
    }).join("");
    const minePick = [1,2,3,4,5].map((n) => `<button type="button" data-mines="${n}" class="${n === minesCount ? "on" : ""}">${n} mines</button>`).join("");
    showTable(`
      <div class="table-top"><h3>Crystal Mines</h3>${betPicker(minePick)}
        <button type="button" class="btn btn-outline" id="side-close">Close</button></div>
      <div class="mines-grid">${cells}</div>
      <div class="table-msg">${st ? (st.boom ? "Mine! " : (st.done ? "Cashed out " : "Multiplier ")) + (st.done ? money(st.payout || 0) : ((st.multiplier || 1).toFixed(2) + "× · next " + ((st.next_multiplier || 0).toFixed ? st.next_multiplier.toFixed(2) : "") + "×")) : "Pick safe crystals, then cash out. Hitting a mine loses the bet."}</div>
      <div class="actions-row">
        ${!st || st.done ? `<button type="button" class="btn btn-gold" id="mn-start">Start</button>` : `<button type="button" class="btn btn-gold" id="mn-cash">Cash out</button>`}
      </div>`);
    bindBets($("#lobby-table"));
    $("#lobby-table").querySelectorAll("[data-mines]").forEach((b) => b.addEventListener("click", () => {
      minesCount = Number(b.dataset.mines);
      $("#lobby-table").querySelectorAll("[data-mines]").forEach((x) => x.classList.toggle("on", Number(x.dataset.mines) === minesCount));
    }));
    $("#side-close").addEventListener("click", closeTable);
    const start = $("#mn-start");
    if (start) start.addEventListener("click", () => minesAct("start"));
    const cash = $("#mn-cash");
    if (cash) cash.addEventListener("click", () => minesAct("cashout"));
    $("#lobby-table").querySelectorAll("[data-tile]").forEach((b) => b.addEventListener("click", () => minesAct("pick", Number(b.dataset.tile))));
  }

  async function minesAct(action, tile) {
    if (busy) return; busy = true;
    try {
      sfx("chip");
      const body = action === "start" ? { action: "start", bet, mines: minesCount } : { action, tile };
      const res = await api("/api/side/mines", body);
      applyCoins(res);
      paintMines(res.result);
    } catch (err) { CC() && CC().toast(err.message || "Failed", true); }
    finally { busy = false; }
  }

  function paintScratch(st) {
    const revealed = new Set();
    const cells = Array.from({ length: 9 }, (_, i) => {
      const sym = st && st.grid ? st.grid[i] : "";
      return `<button type="button" data-i="${i}" class="${st ? "revealed" : ""}">${st ? (sym || "").slice(0, 2) : "✦"}</button>`;
    }).join("");
    showTable(`
      <div class="table-top"><h3>Dragon Scratch</h3>${betPicker()}
        <button type="button" class="btn btn-outline" id="side-close">Close</button></div>
      <div class="scratch-grid" id="scratch-grid">${cells}</div>
      <div class="table-msg" id="side-msg">${st ? ("Prize " + money(st.payout || 0) + (st.mult ? " · " + st.mult + "×" : "")) : "Buy a card and scratch. Three of a kind on a row pays."}</div>
      <div class="actions-row"><button type="button" class="btn btn-gold" id="sc-play">Buy card</button></div>`);
    bindBets($("#lobby-table"));
    $("#side-close").addEventListener("click", closeTable);
    $("#sc-play").addEventListener("click", async () => {
      if (busy) return; busy = true;
      try {
        const res = await api("/api/side/scratch", { bet });
        applyCoins(res);
        const r = res.result;
        // Reveal in the server-provided order so the animation is honest.
        const grid = $("#scratch-grid");
        grid.querySelectorAll("button").forEach((b) => { b.className = ""; b.textContent = "✦"; });
        for (const i of r.reveal_order || []) {
          sfx("scratch");
          const b = grid.querySelector(`[data-i="${i}"]`);
          if (b) { b.classList.add("revealed"); b.textContent = (r.grid[i] || "").slice(0, 6); }
          await sleep(160);
        }
        $("#side-msg").textContent = "Prize " + money(r.payout || 0) + (r.mult ? " · " + r.mult + "×" : "");
      } catch (err) { CC() && CC().toast(err.message || "Failed", true); }
      finally { busy = false; }
    });
  }

  function openGame(id) {
    current = id;
    if (id === "blackjack") paintBJ({});
    else if (id === "roulette") { rouletteBets = []; paintRoulette({}); }
    else if (id === "highcard") paintHigh(null);
    else if (id === "mines") paintMines(null);
    else if (id === "scratch") paintScratch(null);
    else if (id === "dice") paintDice(null);
  }

  function init() {
    // v7 casino.js owns the floor, home, and full-screen tables.
    if (document.getElementById("home") && document.getElementById("game-stage")) return;
    const cfg = CC() && CC().config;
    if (cfg && cfg.side && cfg.side.bets) betsList = cfg.side.bets;
    renderGrid();
    const back = $("#btn-lobby-back");
    if (back) back.addEventListener("click", () => { closeTable(); CC() && CC().setView("slots"); });
  }

  window.CrystalLobby = { init, openGame, closeTable, renderGrid };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => setTimeout(init, 0));
  else setTimeout(init, 0);
})();
