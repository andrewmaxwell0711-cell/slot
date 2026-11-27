/**
 * Client error reports. Posts to /api/errors (rate limited). If the server
 * later sends a public Sentry DSN in config, reports can also go there.
 * No DSN is hardcoded here.
 */
(() => {
  "use strict";
  const sent = [];
  function post(payload) {
    const key = String(payload.message || "") + String(payload.url || "");
    const now = Date.now();
    if (sent.some((s) => s.key === key && now - s.at < 10000)) return;
    sent.push({ key, at: now });
    try {
      const body = JSON.stringify(payload);
      if (navigator.sendBeacon) {
        const blob = new Blob([body], { type: "application/json" });
        navigator.sendBeacon("/api/errors", blob);
      } else {
        fetch("/api/errors", { method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: true }).catch(() => {});
      }
    } catch (e) { /* never break play */ }
  }
  window.addEventListener("error", (ev) => {
    post({
      message: ev.message || "error",
      url: ev.filename || location.href,
      line: ev.lineno,
      col: ev.colno,
      stack: ev.error && ev.error.stack,
    });
  });
  window.addEventListener("unhandledrejection", (ev) => {
    const r = ev.reason;
    post({
      message: (r && (r.message || String(r))) || "unhandledrejection",
      url: location.href,
      stack: r && r.stack,
    });
  });
  window.CrystalErrors = { report: post };
})();
