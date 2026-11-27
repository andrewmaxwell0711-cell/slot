/* Crystal Casino v12 settings. Pure helpers, safe to test in Node. */
(function (root) {
  const KEY = "crystal-casino-settings-v12";
  const DEFAULTS = {
    master: 70,
    sfx: true,
    sfxVolume: 70,
    music: true,
    musicVolume: 55,
    haptics: true,
    reduceEffects: false,
  };

  function clamp(n, lo, hi) {
    n = Number(n);
    if (!Number.isFinite(n)) return lo;
    return Math.min(hi, Math.max(lo, n));
  }

  function osReduce(matchMedia) {
    try {
      const mm = matchMedia || (root.matchMedia && root.matchMedia.bind(root));
      return !!(mm && mm("(prefers-reduced-motion: reduce)").matches);
    } catch (e) {
      return false;
    }
  }

  function load(raw, opts) {
    let data = {};
    if (typeof raw === "string") {
      try { data = JSON.parse(raw) || {}; } catch (e) { data = {}; }
    } else if (raw && typeof raw === "object") {
      data = raw;
    } else if (root.localStorage) {
      try { data = JSON.parse(root.localStorage.getItem(KEY) || "{}") || {}; } catch (e) { data = {}; }
    }
    const out = Object.assign({}, DEFAULTS, data);
    out.master = clamp(out.master, 0, 100);
    out.sfxVolume = clamp(out.sfxVolume != null ? out.sfxVolume : out.master, 0, 100);
    out.musicVolume = clamp(out.musicVolume, 0, 100);
    out.sfx = out.sfx !== false;
    out.music = out.music !== false;
    out.haptics = out.haptics !== false;
    out.reduceEffects = !!out.reduceEffects;
    const preferred = opts && Object.prototype.hasOwnProperty.call(opts, "osReduce")
      ? !!opts.osReduce
      : osReduce();
    if (!Object.prototype.hasOwnProperty.call(data, "reduceEffects") && preferred) {
      out.reduceEffects = true;
    }
    return out;
  }

  function save(state, storage) {
    const payload = load(state, { osReduce: false });
    payload.reduceEffects = !!(state && state.reduceEffects);
    try {
      const store = storage || (root.localStorage || null);
      if (store && store.setItem) store.setItem(KEY, JSON.stringify(payload));
    } catch (e) { /* ignore quota / private mode */ }
    return payload;
  }

  function effectsOn(state, opts) {
    const st = state || load(undefined, opts);
    const preferred = opts && Object.prototype.hasOwnProperty.call(opts, "osReduce")
      ? !!opts.osReduce
      : osReduce();
    return !st.reduceEffects && !preferred;
  }

  const api = { KEY, DEFAULTS, clamp, osReduce, load, save, effectsOn };
  root.CrystalSettings = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
