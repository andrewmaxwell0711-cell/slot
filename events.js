/* Crystal Casino live events — coins-only. Claims may celebrate; plays never do. */
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

  let state = { events: [], available: true, legal: "" };

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

  function icon(type) {
    if (type === "tournament") return "/assets/ui/logo.webp";
    if (type === "xp_boost") return "/assets/symbols/shard.webp";
    if (type === "club_boost") return "/assets/symbols/ruby.webp";
    if (type === "collect") return "/assets/symbols/coin.webp";
    if (type === "challenge") return "/assets/symbols/emerald.webp";
    return "/assets/symbols/citrine.webp";
  }

  async function load() {
    const data = await api("/api/events");
    state = data || state;
    render();
    return data;
  }

  function statusLabel(status) {
    if (status === "active") return "Live";
    if (status === "upcoming") return "Upcoming";
    return "Ended";
  }

  function actionHtml(ev) {
    if (ev.claimed) return `<button type="button" class="event-claim" disabled>Claimed</button>`;
    if (ev.can_claim) {
      return `<button type="button" class="event-claim js-event-claim" data-event-id="${esc(ev.id)}">Claim</button>`;
    }
    if (ev.type === "tournament") {
      return `<button type="button" class="event-prizes js-event-prizes">View prizes</button>`;
    }
    if (ev.status === "ended") return `<button type="button" class="event-claim" disabled>Ended</button>`;
    if (ev.status === "upcoming") return `<button type="button" class="event-claim" disabled>Opens later</button>`;
    if (ev.type === "challenge") return `<button type="button" class="event-claim" disabled>In progress</button>`;
    return "";
  }

  function progressHtml(ev) {
    if (ev.type === "challenge" && (ev.status === "active" || Number(ev.plays || 0) > 0)) {
      const target = Number(ev.target || ev.target_plays || 0);
      const plays = Number(ev.plays || 0);
      const pct = target <= 0 ? 0 : Math.max(0, Math.min(100, Math.round(plays / target * 100)));
      return `<div class="hint">${num(plays)} / ${num(target)} plays</div>
        <div class="event-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}">
          <span style="width:${pct}%"></span>
        </div>`;
    }
    if (ev.type === "happy_hour" && (ev.status === "active" || Number(ev.plays || ev.bonus_coins || 0) > 0)) {
      const target = Number(ev.target || ev.cap_plays || 0);
      const plays = Math.min(Number(ev.plays || 0), target);
      const pct = target <= 0 ? 0 : Math.max(0, Math.min(100, Math.round(plays / target * 100)));
      return `<div class="hint">${num(ev.bonus_coins || 0)} bonus coins · ${num(plays)} / ${num(target)} plays</div>
        <div class="event-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}">
          <span style="width:${pct}%"></span>
        </div>`;
    }
    return "";
  }

  function whenLine(ev) {
    const endLabel = ev.ends_at_label || ev.ends_at || "";
    if (ev.status === "upcoming") {
      const startLabel = ev.starts_at_label || ev.starts_at || "";
      return `Opens ${esc(startLabel)}. Ends ${esc(endLabel)}.`;
    }
    if (ev.status === "ended") return `Ended ${esc(endLabel)}.`;
    return `Ends ${esc(endLabel)}.`;
  }

  function group(title, list) {
    if (!list.length) return "";
    const rows = list.map((ev) => `<div class="event-item">
      <img src="${esc(icon(ev.type))}" width="40" height="40" alt="">
      <div class="event-copy">
        <span class="event-status is-${esc(ev.status || "")}">${esc(statusLabel(ev.status))}</span>
        <strong>${esc(ev.title)}</strong>
        <p class="hint">${esc(ev.description || "")}</p>
        <p class="event-when">${whenLine(ev)}</p>
        ${ev.reward_label ? `<p class="hint">${esc(ev.reward_label)}</p>` : ""}
        ${progressHtml(ev)}
      </div>
      <div class="event-actions">${actionHtml(ev)}</div>
    </div>`).join("");
    return `<div class="events-card"><h3>${esc(title)}</h3><div class="events-list">${rows}</div></div>`;
  }

  function render() {
    const root = $("#events-body");
    if (!root) return;
    const legal = state.legal
      || "Event rewards are virtual and have no cash value. Boosts never change game payouts.";
    if (state.available === false) {
      root.innerHTML = `<div class="events-card"><p class="hint">Live events are not available on this database yet.</p></div><p class="events-legal">${esc(legal)}</p>`;
      return;
    }
    const all = state.events || [];
    const live = all.filter((e) => e.status === "active");
    const upcoming = all.filter((e) => e.status === "upcoming");
    const ended = all.filter((e) => e.status === "ended");
    root.innerHTML = `
      ${group("Live now", live) || `<div class="events-card"><h3>Live now</h3><p class="hint">No events are running right now. Upcoming times are listed below.</p></div>`}
      ${group("Upcoming", upcoming)}
      ${group("Recently ended", ended)}
      <p class="events-legal">${esc(legal)}</p>
    `;
    bind();
  }

  function bind() {
    $$(".js-event-claim").forEach((btn) => {
      btn.addEventListener("click", () => onClaim(btn.getAttribute("data-event-id") || ""));
    });
    $$(".js-event-prizes").forEach((btn) => {
      btn.addEventListener("click", () => {
        const open = document.querySelector(".js-prizes");
        if (open) open.click();
        else toast("Open Prizes from Home to see the weekend board.");
      });
    });
  }

  async function onClaim(eventId) {
    try {
      const res = await api("/api/events/claim", {
        method: "POST",
        body: JSON.stringify({ event_id: eventId }),
      });
      applySnap(res);
      if (res && res.error && !res.already_claimed) { toast(res.error, true); return; }
      if (res && res.already_claimed) {
        toast("Already claimed this event prize.");
      } else if (res && res.celebrate) {
        if (CC() && CC().celebrate) {
          await CC().celebrate({
            kind: "chest",
            title: "EVENT PRIZE",
            amountAud: res.awarded || null,
            sub: "Event reward — virtual coins, no cash value.",
            kicker: "LIVE EVENTS",
            hold: 3200,
          });
        } else {
          toast("Claimed " + num(res.awarded || 0) + " coins");
        }
      }
      state = res;
      render();
    } catch (e) {
      toast((e && e.message) || "Could not claim that prize", true);
    }
  }

  window.CrystalEvents = { load, render };
})();
