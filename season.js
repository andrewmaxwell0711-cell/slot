/* Crystal Casino season pass — coins-only. Claims may celebrate; plays never do. */
(function () {
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  function CC() { return window.CrystalCasino; }
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

  let state = { season: null, free: [], premium: [], missions: {}, available: true };

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
    const data = await api("/api/season");
    state = data || state;
    render();
    scrollToCurrent();
    return data;
  }

  function rewardInner(reward, premium) {
    if (!reward) return "";
    if (reward.kind === "emblem" && reward.src) {
      return `<img src="${esc(reward.src)}" alt="" width="36" height="36"><span>${esc(reward.label)}</span>`;
    }
    if (reward.kind === "frame") {
      const color = reward.color || "#e8c97a";
      return `<span class="frame-swatch" style="border-color:${esc(color)}"></span><span>${esc(reward.label)}</span>`;
    }
    return `<img src="/assets/symbols/coin.webp" alt="" width="36" height="36"><span>${esc(reward.label || (num(reward.amount) + " coins"))}</span>`;
  }

  function trackHtml() {
    const free = state.free || (state.catalog && state.catalog.free) || [];
    const premium = state.premium || (state.catalog && state.catalog.premium) || [];
    const current = Number(state.tier) || 0;
    const cols = free.map((f, i) => {
      const p = premium[i] || { reward: {}, locked: true };
      const claimed = !!f.claimed;
      const can = !!f.can_claim;
      let btn;
      if (claimed) btn = `<button type="button" class="season-claim" disabled>Claimed</button>`;
      else if (can) btn = `<button type="button" class="season-claim js-season-claim" data-tier="${f.tier}">Claim</button>`;
      else btn = `<button type="button" class="season-claim" disabled>${f.reached ? "Claimed" : num(f.xp_required) + " XP"}</button>`;
      return `<div class="season-tier${current === f.tier ? " is-current" : ""}${claimed ? " is-claimed" : ""}" data-tier="${f.tier}">
        <div class="season-chest premium" title="Premium coming soon">${rewardInner(p.reward, true)}<small>Coming soon</small></div>
        <div class="season-tier-num">Tier ${f.tier}</div>
        <div class="season-chest">${rewardInner(f.reward, false)}</div>
        ${btn}
      </div>`;
    }).join("");
    return `<div class="season-track-legend"><span>Premium coming soon</span><span>Free track</span></div>
      <div class="season-track-wrap" id="season-track-wrap"><div class="season-track">${cols}</div></div>`;
  }

  function missionsHtml() {
    const daily = (state.missions && state.missions.daily) || [];
    const weekly = (state.missions && state.missions.weekly) || [];
    const item = (m) => `<li>
      <div><strong>${esc(m.title)}</strong><div class="hint">${num(m.progress)} / ${num(m.target)}${m.completed ? " · complete" : ""}</div></div>
      <span class="xp">${num(m.xp)} XP</span>
    </li>`;
    return `<div class="season-card"><h3>Today's missions</h3>
      <p class="hint">Three missions each day. Completing one grants XP once — it cannot pay twice.</p>
      <ul class="season-missions">${daily.map(item).join("") || "<li>No missions today.</li>"}</ul>
    </div>
    <div class="season-card"><h3>Weekly missions</h3>
      <ul class="season-missions">${weekly.map(item).join("") || "<li>No weekly missions.</li>"}</ul>
    </div>`;
  }

  function render() {
    const root = $("#season-body");
    if (!root) return;
    const season = state.season || (state.catalog && state.catalog.season) || {};
    const legal = (state.catalog && state.catalog.legal) || season.legal
      || "Season rewards are virtual and have no cash value.";
    const note = (state.catalog && state.catalog.premium_note) || season.premium_note || "";
    if (state.available === false) {
      root.innerHTML = `<div class="season-card"><p class="hint">The season pass is not available on this database yet.</p></div><p class="season-legal">${esc(legal)}</p>`;
      return;
    }
    const xp = Number(state.xp) || 0;
    const next = Number(state.next_xp) || 0;
    const pct = next <= 0 ? 100 : Math.max(0, Math.min(100, Math.round(xp / next * 100)));
    const endLabel = season.ends_at_label || season.ends_at || "";
    root.innerHTML = `
      <div class="season-card">
        <h3>${esc(season.title || "Season pass")}</h3>
        <p class="season-end">Season ends <strong>${esc(endLabel)}</strong>.</p>
        <div class="season-xp">
          <div class="season-xp-meta"><span>Tier ${Number(state.tier) || 0} of 30</span><span>${num(xp)} / ${num(next)} XP</span></div>
          <div class="season-xp-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}">
            <span class="season-xp-fill" style="width:${pct}%"></span>
          </div>
        </div>
        ${trackHtml()}
        <p class="hint">${esc(note)}</p>
      </div>
      ${missionsHtml()}
      <p class="season-legal">${esc(legal)}</p>
    `;
    bind();
  }

  function scrollToCurrent() {
    const wrap = $("#season-track-wrap");
    const current = $(".season-tier.is-current") || $$(".season-tier").find((el) => el.classList.contains("is-claimed") === false);
    if (wrap && current) {
      const left = current.offsetLeft - wrap.clientWidth / 2 + current.clientWidth / 2;
      wrap.scrollLeft = Math.max(0, left);
    }
  }

  function bind() {
    $$(".js-season-claim").forEach((btn) => {
      btn.addEventListener("click", () => onClaim(Number(btn.getAttribute("data-tier") || 0)));
    });
  }

  async function onClaim(tier) {
    try {
      const res = await api("/api/season/claim", {
        method: "POST",
        body: JSON.stringify({ track: "free", tier }),
      });
      applySnap(res);
      if (res && res.error && !res.already_claimed) { toast(res.error, true); return; }
      if (res && res.already_claimed) {
        toast("Already claimed this season tier.");
      } else if (res && res.celebrate) {
        const reward = res.reward || {};
        const title = (reward.label || ("Tier " + tier)).toUpperCase();
        if (CC() && CC().celebrate) {
          await CC().celebrate({
            kind: "chest",
            title,
            amountAud: res.awarded || null,
            sub: "Season reward — virtual item, no cash value.",
            kicker: "SEASON PASS",
            hold: 3200,
          });
        } else {
          toast(reward.label || ("Claimed tier " + tier));
        }
      }
      state = res;
      render();
      scrollToCurrent();
    } catch (e) {
      toast((e && e.message) || "Could not claim that tier", true);
    }
  }

  window.CrystalSeason = { load, render };
})();
