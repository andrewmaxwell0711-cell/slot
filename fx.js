/* Crystal Casino v12 motion layer. Transform/opacity only, pooled particles. */
(function (root) {
  const Settings = root.CrystalSettings;

  function on() {
    return Settings ? Settings.effectsOn() : !prefersReduce();
  }
  function prefersReduce() {
    return Settings ? Settings.osReduce() : false;
  }
  function settings() {
    return Settings ? Settings.load() : {};
  }

  /* ---- anticipation: only when the bonus will actually complete ---- */
  function shouldAnticipate(landedBefore, remainingCounts, need) {
    need = need || 3;
    const later = (remainingCounts || []).reduce((a, n) => a + Number(n || 0), 0);
    const total = Number(landedBefore || 0) + later;
    if (total < need) return false;          // would be a staged near-miss
    if (landedBefore < need - 1) return false; // wait until one more is needed
    return landedBefore < need;
  }

  /* ---- haptics ---- */
  function vibrate(pattern) {
    const s = settings();
    if (!s.haptics || !on()) return;
    try {
      if (root.navigator && typeof root.navigator.vibrate === "function") {
        root.navigator.vibrate(pattern);
      }
    } catch (e) { /* unsupported */ }
  }

  const HAPTIC = {
    spin: 10,
    stop: 8,
    click: 6,
    chip: 7,
    card: 9,
    win: [10, 30, 12],
    big: [16, 40, 16, 40, 24],
    mega: [18, 30, 18, 30, 18, 30, 36],
    epic: [22, 30, 22, 30, 22, 30, 22, 40, 50],
    jackpot: [30, 40, 30, 40, 30, 50, 60],
    scatter: [8, 20, 14],
    chest: [12, 30, 20],
    level: [14, 30, 14, 30, 24],
  };


  const MAX_LIVE = 64;

  function formatCelebrateSub(sub, current, final) {
    sub = sub || "";
    const m = /^(\d+)\s*× your total bet$/.exec(sub);
    if (!m) return (!final || current >= final) ? sub : "";
    if (!final || current <= 0) return "";
    const shown = Math.max(1, Math.round(Number(m[1]) * (current / final)));
    return shown + "× your total bet";
  }

  /* ---- particle pool (DOM) ---- */
  let layer;
  const pool = [];
  function fxLayer() {
    if (layer && layer.isConnected) return layer;
    layer = document.getElementById("fx-layer");
    if (!layer && document.body) {
      layer = document.createElement("div");
      layer.id = "fx-layer";
      layer.setAttribute("aria-hidden", "true");
      document.body.appendChild(layer);
    }
    return layer;
  }
  function alloc(cls) {
    const el = pool.pop() || document.createElement("span");
    el.className = cls;
    el.style.cssText = "";
    fxLayer() && fxLayer().appendChild(el);
    return el;
  }
  function release(el) {
    if (!el) return;
    if (el.parentNode) el.parentNode.removeChild(el);
    el.style.cssText = "";
    el.className = "";
    if (pool.length < 64) pool.push(el);
  }

  function fountain(n, x, y) {
    if (!on()) return;
    const host = fxLayer();
    if (!host) return;
    const room = Math.max(0, MAX_LIVE - host.childElementCount);
    const count = Math.max(0, Math.min(n || 24, 48, room));
    const panel = document.querySelector("#celebrate .celebrate-panel") || document.querySelector(".celebrate-inner");
    const r = panel && panel.getBoundingClientRect();
    const cx = x != null ? x : (r ? r.left + r.width / 2 : (root.innerWidth || 390) / 2);
    const cy = y != null ? y : (r ? r.top + r.height * 0.35 : (root.innerHeight || 700) * 0.42);
    for (let i = 0; i < count; i++) {
      const el = alloc("fx-coin");
      let ox = cx, oy = cy, dx, dy;
      const slot = Math.random();
      if (r && x == null && y == null) {
        if (slot < 0.28) {
          ox = r.left + r.width * (0.12 + Math.random() * 0.76);
          oy = r.top + 6;
          dx = (Math.random() - 0.5) * 160;
          dy = -90 - Math.random() * 150;
        } else if (slot < 0.64) {
          ox = r.left + (Math.random() * 16 - 8);
          oy = r.top + r.height * (0.1 + Math.random() * 0.8);
          dx = -50 - Math.random() * 160;
          dy = -80 - Math.random() * 110;
        } else {
          ox = r.right + (Math.random() * 16 - 8);
          oy = r.top + r.height * (0.1 + Math.random() * 0.8);
          dx = 50 + Math.random() * 160;
          dy = -80 - Math.random() * 110;
        }
      } else {
        dx = (Math.random() - 0.5) * 260;
        dy = -80 - Math.random() * 160;
      }
      el.style.left = ox + "px";
      el.style.top = oy + "px";
      el.style.setProperty("--dx", dx + "px");
      el.style.setProperty("--dy", dy + "px");
      el.style.setProperty("--rot", (Math.random() * 360) + "deg");
      el.style.animationDuration = (700 + Math.random() * 500) + "ms";
      window.setTimeout(() => release(el), 1300);
    }
  }

  function shine(el) {
    if (!on() || !el) return;
    el.classList.add("fx-win");
    window.setTimeout(() => el.classList.remove("fx-win"), 1400);
  }

  function lockCell(el) {
    if (!el) return;
    el.classList.add("fx-lock");
    if (on()) vibrate(HAPTIC.scatter);
  }

  function rollNumber(el, from, to, ms, format) {
    if (!el) return Promise.resolve();
    const start = Number(from) || 0;
    const end = Number(to) || 0;
    const fmt = format || ((n) => String(Math.round(n)));
    if (!on() || ms <= 0 || start === end) {
      el.textContent = fmt(end);
      return Promise.resolve();
    }
    return new Promise((resolve) => {
      const t0 = performance.now();
      const step = (now) => {
        const k = Math.min(1, (now - t0) / ms);
        const eased = 1 - Math.pow(1 - k, 3);
        el.textContent = fmt(start + (end - start) * eased);
        if (k < 1) requestAnimationFrame(step);
        else resolve();
      };
      requestAnimationFrame(step);
    });
  }

  /* ---- gem background parallax (transform only) ---- */
  let gemX = 0, gemY = 0, gemS = 0, gemRaf = 0;
  function applyGemVars() {
    const rootEl = document.documentElement;
    if (!rootEl) return;
    rootEl.style.setProperty("--gem-x", gemX.toFixed(3));
    rootEl.style.setProperty("--gem-y", gemY.toFixed(3));
    rootEl.style.setProperty("--gem-scroll", gemS.toFixed(3));
    gemRaf = 0;
  }
  function setGem(x, y, s) {
    gemX = Math.max(-1, Math.min(1, x));
    gemY = Math.max(-1, Math.min(1, y));
    if (s != null) gemS = Math.max(-1, Math.min(1, s));
    if (!gemRaf) gemRaf = requestAnimationFrame(applyGemVars);
  }
  function bindGemParallax() {
    if (!on()) {
      setGem(0, 0, 0);
      return;
    }
    const onScroll = () => {
      if (!on()) return;
      const y = (root.scrollY || document.documentElement.scrollTop || 0) / Math.max(1, root.innerHeight || 1);
      setGem(gemX, gemY, Math.max(-1, Math.min(1, y * 0.6)));
    };
    const onPointer = (e) => {
      if (!on()) return;
      const w = root.innerWidth || 1, h = root.innerHeight || 1;
      const cx = e.clientX != null ? e.clientX : (e.touches && e.touches[0] && e.touches[0].clientX) || w / 2;
      const cy = e.clientY != null ? e.clientY : (e.touches && e.touches[0] && e.touches[0].clientY) || h / 2;
      setGem((cx / w) * 2 - 1, (cy / h) * 2 - 1, gemS);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("pointermove", onPointer, { passive: true });
    if (root.DeviceOrientationEvent) {
      window.addEventListener("deviceorientation", (e) => {
        if (!on()) return;
        const gx = Math.max(-1, Math.min(1, (e.gamma || 0) / 25));
        const gy = Math.max(-1, Math.min(1, (e.beta || 0) / 35));
        setGem(gx, gy, gemS);
      }, { passive: true });
    }
    onScroll();
  }

  /* ---- cards / chips / tables ---- */
  function dealCard(el, i) {
    if (!el) return;
    el.style.setProperty("--deal-i", String(i || 0));
    el.classList.add("fx-deal");
    if (on()) vibrate(HAPTIC.card);
  }
  function flipCard(el) {
    if (!el) return;
    el.classList.add("fx-flip");
    if (on()) vibrate(HAPTIC.card);
  }
  function tossChip(fromEl, toEl) {
    if (!on() || !fromEl || !toEl) return;
    const a = fromEl.getBoundingClientRect();
    const b = toEl.getBoundingClientRect();
    const el = alloc("fx-fly-chip");
    el.style.left = (a.left + a.width / 2) + "px";
    el.style.top = (a.top + a.height / 2) + "px";
    el.style.setProperty("--tx", ((b.left + b.width / 2) - (a.left + a.width / 2)) + "px");
    el.style.setProperty("--ty", ((b.top + b.height / 2) - (a.top + a.height / 2)) + "px");
    vibrate(HAPTIC.chip);
    window.setTimeout(() => release(el), 600);
  }
  function highlightRoulette(number) {
    document.querySelectorAll("#felt .felt-hit").forEach((n) => n.classList.remove("felt-hit"));
    const btn = document.querySelector('#felt button[data-kind="straight"][data-n="' + number + '"]');
    if (btn) {
      btn.classList.add("felt-hit");
      btn.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }
  function squeezeCard(el) {
    if (!el) return;
    el.classList.add("fx-squeeze");
    if (on()) vibrate(HAPTIC.card);
  }
  function kenoBall(el, i) {
    if (!el) return;
    el.style.setProperty("--keno-i", String(i || 0));
    el.classList.add("fx-keno-ball");
  }

  function viewTransition() {
    if (!on()) return;
    document.body.classList.remove("fx-view-in");
    void document.body.offsetWidth;
    document.body.classList.add("fx-view-in");
  }

  function openChest(el) {
    if (!el) return;
    el.classList.add("fx-chest-open");
    vibrate(HAPTIC.chest);
    window.setTimeout(() => el.classList.remove("fx-chest-open"), 1400);
  }

  const api = {
    on, shouldAnticipate, vibrate, HAPTIC, fountain, shine, lockCell, rollNumber, formatCelebrateSub,
    bindGemParallax, setGem, dealCard, flipCard, tossChip, highlightRoulette,
    squeezeCard, kenoBall, viewTransition, openChest, fxLayer,
  };
  root.CrystalFX = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);

if (typeof document !== "undefined" && document.addEventListener) {
  document.addEventListener("DOMContentLoaded", () => {
    try { if (window.CrystalFX) window.CrystalFX.bindGemParallax(); } catch (e) { /* ignore */ }
  });
}
