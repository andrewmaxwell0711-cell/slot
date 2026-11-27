/* Crystal Casino clubs — coins-only team play. Preset chat only. */
(function () {
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  function CC() { return window.CrystalCasino; }
  function money(n) { return CC() && CC().money ? CC().money(n) : String(n); }
  function num(n) {
    if (CC() && CC().moneyShort) return CC().moneyShort(n);
    return Math.round(Number(n) || 0).toLocaleString("en-US");
  }
  function toast(msg, err) {
    if (CC() && CC().toast) CC().toast(msg, !!err);
  }
  function api(path, opts) {
    if (!CC() || !CC().api) return Promise.reject(new Error("Casino is still loading"));
    return CC().api(path, opts);
  }

  let state = { club: null, catalog: null, open: [], board: [] };
  let pickedEmblem = "ruby";
  let pickedVis = "open";

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function applySnap(res) {
    if (res && CC() && CC().applySnapshot && (res.coins != null || res.snapshot)) {
      CC().applySnapshot(res.snapshot || res);
    }
  }

  async function load() {
    const data = await api("/api/clubs");
    state = data || state;
    if (data && data.catalog && data.catalog.emblems && !pickedEmblem) {
      pickedEmblem = data.catalog.emblems[0].id;
    }
    render();
    return data;
  }

  function progressPct(prog) {
    if (!prog) return 0;
    const cap = (prog.tiers && prog.tiers.length) ? prog.tiers[prog.tiers.length - 1].points : 1;
    return Math.max(0, Math.min(100, Math.round((Number(prog.points) || 0) / cap * 100)));
  }

  function renderBrowse() {
    const cat = state.catalog || {};
    const emblems = cat.emblems || [];
    const open = state.open || [];
    const board = (state.board && state.board.clubs) || [];
    const emblemBtns = emblems.map((e) =>
      `<button type="button" class="club-emblem-pick${e.id === pickedEmblem ? " is-on" : ""}" data-emblem="${esc(e.id)}" aria-label="${esc(e.label)}">` +
      `<img src="${esc(e.src)}" alt="" width="44" height="44"></button>`
    ).join("");
    const openItems = open.length
      ? open.map((c) =>
          `<li>` +
          `<img src="${esc(c.emblem_src)}" alt="">` +
          `<div><strong>${esc(c.name)}</strong><div class="club-meta">${c.member_count}/${c.cap} · ${num(c.points)} pts this week</div></div>` +
          `<button type="button" class="btn btn-gold js-join-open" data-id="${esc(c.id)}" ${c.full ? "disabled" : ""}>${c.full ? "Full" : "Join"}</button>` +
          `</li>`
        ).join("")
      : `<li><div>No open clubs yet. Create one and invite friends.</div></li>`;
    const boardItems = board.length
      ? board.map((c) =>
          `<li>` +
          `<img src="${esc(c.emblem_src)}" alt="">` +
          `<div><strong>#${c.rank} ${esc(c.name)}</strong><div class="club-meta">${c.member_count} members</div></div>` +
          `<strong>${num(c.points)} pts</strong>` +
          `</li>`
        ).join("")
      : `<li><div>No club scores yet this week.</div></li>`;
    return `
      <div class="clubs-card" id="club-create-card">
        <h3>Create a club</h3>
        <p class="hint">Pick a name and emblem. Clubs hold up to 30 members. Coins cannot be sent between players.</p>
        <label for="club-name">Club name</label>
        <input id="club-name" type="text" maxlength="24" minlength="3" autocomplete="off" placeholder="Crystal Guild">
        <label>Emblem</label>
        <div class="emblem-row" id="club-emblems">${emblemBtns}</div>
        <label>Visibility</label>
        <div class="club-vis-row">
          <button type="button" class="btn btn-outline js-vis ${pickedVis === "open" ? "is-on" : ""}" data-vis="open">Open</button>
          <button type="button" class="btn btn-outline js-vis ${pickedVis === "invite" ? "is-on" : ""}" data-vis="invite">Invite only</button>
        </div>
        <div class="clubs-actions">
          <button type="button" class="btn btn-gold" id="btn-club-create">Create club</button>
        </div>
      </div>
      <div class="clubs-card">
        <h3>Join with an invite code</h3>
        <label for="club-invite">Invite code</label>
        <input id="club-invite" type="text" maxlength="12" autocomplete="off" placeholder="ABC123" spellcheck="false">
        <div class="clubs-actions">
          <button type="button" class="btn btn-gold" id="btn-club-join-code">Join club</button>
        </div>
      </div>
      <div class="clubs-card">
        <h3>Open clubs</h3>
        <ul class="club-open-list">${openItems}</ul>
      </div>
      <div class="clubs-card">
        <h3>Weekly club leaderboard</h3>
        <p class="hint">Resets Monday 00:00, Australia/Perth. ${esc(cat.week_id || "")}</p>
        <ul class="club-board">${boardItems}</ul>
      </div>
    `;
  }

  function renderMine() {
    const club = state.club;
    const cat = state.catalog || {};
    const prog = club.progress || {};
    const pct = progressPct(prog);
    const tiers = (prog.tiers || []).map((t) =>
      `<div class="club-tier${prog.tier >= t.tier ? " is-reached" : ""}">` +
      `<strong>${esc(t.label)}</strong>${num(t.points)} pts` +
      `<div>${num(t.coins)} coins</div></div>`
    ).join("");
    const members = (club.members || []).map((m, i) =>
      `<li>` +
      `<img src="${esc(club.emblem_src)}" alt="">` +
      `<div><strong>${i + 1}. ${esc(m.nickname)}</strong><div class="club-meta">${esc(m.role)} · ${m.spins} plays</div></div>` +
      `<strong>${num(m.points)} pts</strong>` +
      `</li>`
    ).join("");
    const phrases = (cat.phrases || []).map((p) =>
      `<button type="button" class="club-phrase" data-phrase="${esc(p.id)}">${esc(p.text)}</button>`
    ).join("");
    const chat = (club.chat || []).map((c) =>
      `<li><strong>${esc(c.nickname)}</strong> ${esc(c.text)}</li>`
    ).join("") || `<li class="hint">No messages yet. Use a preset phrase.</li>`;
    const board = (state.board && state.board.clubs) || [];
    const boardItems = board.map((c) =>
      `<li>` +
      `<img src="${esc(c.emblem_src)}" alt="">` +
      `<div><strong>#${c.rank} ${esc(c.name)}</strong><div class="club-meta">${c.member_count} members</div></div>` +
      `<strong>${num(c.points)} pts</strong>` +
      `</li>`
    ).join("") || `<li><div>No club scores yet this week.</div></li>`;
    const claimLabel = club.claimed
      ? `Claimed ${num(club.claimed_amount)} coins`
      : (club.can_claim ? `Claim ${num(prog.reward_coins)} coins` : "Reward locked");
    return `
      <div class="clubs-card">
        <div class="club-identity">
          <img class="club-emblem" src="${esc(club.emblem_src)}" alt="" width="64" height="64">
          <div>
            <h3>${esc(club.name)}</h3>
            <p class="club-meta">${club.member_count}/${club.cap} members · ${club.visibility === "invite" ? "Invite only" : "Open"}</p>
          </div>
        </div>
        <div class="club-progress">
          <p class="club-meta">Weekly goal · ${esc(prog.week_id || "")} · ${num(prog.points)} pts</p>
          <div class="club-progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}">
            <span class="club-progress-fill" style="width:${pct}%"></span>
          </div>
          <div class="club-tiers">${tiers}</div>
        </div>
        <div class="clubs-actions">
          <button type="button" class="btn btn-gold" id="btn-club-claim" ${club.can_claim ? "" : "disabled"}>${claimLabel}</button>
          <button type="button" class="btn btn-outline" id="btn-club-leave">Leave club</button>
        </div>
        <p class="club-meta">Invite code: <span class="invite-code">${esc(club.invite_code)}</span></p>
      </div>
      <div class="clubs-card">
        <h3>This week's contributions</h3>
        <ul class="club-members">${members}</ul>
      </div>
      <div class="clubs-card">
        <h3>Quick chat</h3>
        <p class="hint">Preset phrases only — no free text.</p>
        <ul class="club-chat-log">${chat}</ul>
        <div class="phrase-row">${phrases}</div>
      </div>
      <div class="clubs-card">
        <h3>Weekly club leaderboard</h3>
        <ul class="club-board">${boardItems}</ul>
      </div>
    `;
  }

  function render() {
    const root = $("#clubs-body");
    if (!root) return;
    const legal = (state.catalog && state.catalog.legal)
      || "Club rewards are virtual coins issued by the house. Coins have no cash value and cannot be transferred between players.";
    if (!state.available && state.catalog) {
      /* available may be missing on older payloads; treat as true when catalog exists */
    }
    if (state.available === false) {
      root.innerHTML = `<div class="clubs-card"><p class="hint">Clubs are not available on this database yet.</p></div><p class="club-legal">${esc(legal)}</p>`;
      return;
    }
    root.innerHTML = (state.club ? renderMine() : renderBrowse()) + `<p class="club-legal">${esc(legal)}</p>`;
    bind();
  }

  function bind() {
    const root = $("#clubs-page");
    if (!root || root.dataset.bound === "1") {
      /* re-rendered HTML needs fresh listeners each time; always bind on new nodes */
    }
    $$("#club-emblems .club-emblem-pick").forEach((btn) => {
      btn.addEventListener("click", () => {
        pickedEmblem = btn.getAttribute("data-emblem") || "ruby";
        $$("#club-emblems .club-emblem-pick").forEach((b) => b.classList.toggle("is-on", b === btn));
      });
    });
    $$(".js-vis").forEach((btn) => {
      btn.addEventListener("click", () => {
        pickedVis = btn.getAttribute("data-vis") || "open";
        $$(".js-vis").forEach((b) => b.classList.toggle("is-on", b === btn));
      });
    });
    const createBtn = $("#btn-club-create");
    if (createBtn) createBtn.addEventListener("click", onCreate);
    const joinCode = $("#btn-club-join-code");
    if (joinCode) joinCode.addEventListener("click", onJoinCode);
    $$(".js-join-open").forEach((btn) => {
      btn.addEventListener("click", () => onJoin({ club_id: btn.getAttribute("data-id") }));
    });
    const claim = $("#btn-club-claim");
    if (claim) claim.addEventListener("click", onClaim);
    const leave = $("#btn-club-leave");
    if (leave) leave.addEventListener("click", onLeave);
    $$(".club-phrase").forEach((btn) => {
      btn.addEventListener("click", () => onChat(btn.getAttribute("data-phrase")));
    });
  }

  async function onCreate() {
    const name = ($("#club-name") && $("#club-name").value) || "";
    try {
      const res = await api("/api/clubs", {
        method: "POST",
        body: JSON.stringify({ name, emblem: pickedEmblem, visibility: pickedVis }),
      });
      if (res && res.error) { toast(res.error, true); return; }
      state = res;
      render();
      toast("Club created. Coins have no cash value.");
    } catch (e) {
      toast((e && e.message) || "Could not create the club", true);
    }
  }

  async function onJoinCode() {
    const code = ($("#club-invite") && $("#club-invite").value) || "";
    return onJoin({ invite_code: code });
  }

  async function onJoin(body) {
    try {
      const res = await api("/api/clubs/join", { method: "POST", body: JSON.stringify(body) });
      if (res && res.error) { toast(res.error, true); return; }
      state = res;
      render();
      toast("Welcome to the club.");
    } catch (e) {
      toast((e && e.message) || "Could not join that club", true);
    }
  }

  async function onLeave() {
    if (!window.confirm("Leave this club? You can rejoin if a seat is free, but you cannot claim this week's reward twice.")) return;
    try {
      const res = await api("/api/clubs/leave", { method: "POST", body: "{}" });
      if (res && res.error) { toast(res.error, true); return; }
      state = res;
      render();
      toast("You left the club.");
    } catch (e) {
      toast((e && e.message) || "Could not leave the club", true);
    }
  }

  async function onClaim() {
    try {
      const res = await api("/api/clubs/claim", { method: "POST", body: "{}" });
      applySnap(res);
      if (res && res.error && !res.already_claimed) { toast(res.error, true); return; }
      if (res && res.already_claimed) {
        toast("Already claimed this week's club reward.");
      } else if (res && res.awarded) {
        toast(`Club reward: ${num(res.awarded)} coins. Virtual coins, no cash value.`);
      }
      state = res;
      render();
    } catch (e) {
      toast((e && e.message) || "Could not claim the reward", true);
    }
  }

  async function onChat(phraseId) {
    try {
      const res = await api("/api/clubs/chat", { method: "POST", body: JSON.stringify({ phrase_id: phraseId }) });
      if (res && res.error) { toast(res.error, true); return; }
      state = res;
      render();
    } catch (e) {
      toast((e && e.message) || "Could not send that phrase", true);
    }
  }

  window.CrystalClubs = { load, render };
})();
