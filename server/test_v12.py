#!/usr/bin/env python3
"""v12 polish: settings persistence, reduced-motion flag, static assets, legal copy."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
ROOT = SERVER_DIR.parent
sys.path.insert(0, str(SERVER_DIR))
os.chdir(SERVER_DIR)

os.environ.pop("DATABASE_URL", None)
os.environ.pop("SENTRY_DSN", None)
os.environ.pop("SENTRY_PUBLIC_DSN", None)
os.environ.pop("GOOGLE_CLIENT_ID", None)
os.environ.pop("STRIPE_SECRET_KEY", None)

SENTENCE = (
    "Practice or success at social casino gaming does not imply future success "
    "at real money gambling."
)


class SettingsAndMotionTests(unittest.TestCase):
    def test_node_settings_and_anticipation(self):
        out = subprocess.check_output(
            [os.environ.get("NODE", "node"), str(ROOT / "tools" / "test_settings.js")],
            text=True,
        )
        self.assertIn("ok", out)


class LaunchSurfaceTests(unittest.TestCase):
    def test_static_and_legal_still_present(self):
        import app as app_module

        self.assertIn("settings.js", app_module.ALLOWED_STATIC)
        self.assertIn("fx.js", app_module.ALLOWED_STATIC)
        self.assertIn("fx.css", app_module.ALLOWED_STATIC)
        client = app_module.app.test_client()
        for path in ("/settings.js", "/fx.js", "/fx.css", "/privacy", "/terms"):
            r = client.get(path)
            self.assertEqual(r.status_code, 200, path)
        priv = client.get("/privacy").get_data(as_text=True)
        self.assertIn(SENTENCE, priv)
        self.assertIn("18+", priv)
        cfg = client.get("/api/config").get_json()
        self.assertEqual(cfg["simulated_gambling"], SENTENCE)
        self.assertEqual(cfg["age_limit"], 18)
        html = (ROOT / "index.html").read_text()
        self.assertIn(SENTENCE, html)
        self.assertIn('id="gem-bg"', html)
        self.assertIn("Reduce effects", html)
        self.assertIn("Haptic feedback", html)
        self.assertIn("Master volume", html)
        self.assertIn("/privacy", html)
        self.assertIn("/terms", html)

    def test_fx_uses_transform_and_respects_reduce(self):
        css = (ROOT / "fx.css").read_text()
        self.assertIn("gem-bg", css)
        self.assertIn("reduce-motion", css)
        self.assertIn("reduce-effects", css)
        self.assertIn("prefers-reduced-motion", (ROOT / "styles.css").read_text())
        self.assertIn("translate3d", css)
        self.assertIn("gem-interior", css)
        js = (ROOT / "fx.js").read_text()
        self.assertIn("shouldAnticipate", js)
        self.assertIn("bindGemParallax", js)
        self.assertIn("navigator.vibrate", js)

    def test_celebrate_overlay_and_sound_bank(self):
        html = (ROOT / "index.html").read_text()
        self.assertIn("celebrate-scrim", html)
        self.assertIn("celebrate-panel", html)
        self.assertIn("celebrate-legal", html)
        self.assertIn("A social-casino win — coins have no cash value", html)
        css = (ROOT / "fx.css").read_text()
        self.assertIn("celebrate-scrim", css)
        self.assertIn("medal-glow", css)
        js = (ROOT / "app.js").read_text()
        for token in (
            "function celebrate",
            "syncMeters",
            "payoutCoins",
            "setCreditDisplay",
            "sfx.epic()",
            "sfx.mega()",
            "cardDeal",
            "cardFlip",
            "startBgMusic",
        ):
            self.assertIn(token, js)
        # Celebrated amount is the rounded server payout, not a display-only figure.
        self.assertIn("amountAud: totalWin", js)



    def test_gzip_and_lazy_heroes(self):
        import app as app_module

        client = app_module.app.test_client()
        r = client.get("/styles.css", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("Content-Encoding"), "gzip")
        html = (ROOT / "index.html").read_text()
        self.assertIn('loading="lazy"', html)
        self.assertIn("celebrate-scrim", html)
        self.assertGreater(html.count('loading="lazy"'), 2)



    def test_split_css_and_deferred_js(self):
        import app as app_module

        client = app_module.app.test_client()
        for path in ("/css/core.css", "/css/home.css", "/css/lobby.css", "/css/slots.css", "/css/tables.css", "/neon", "/lobby"):
            r = client.get(path)
            self.assertEqual(r.status_code, 200, path)
        self.assertEqual(client.get("/not-a-page").status_code, 404)
        html = (ROOT / "index.html").read_text()
        self.assertIn('id="critical-css"', html)
        self.assertIn("css/core.css", html)
        self.assertIn("css/home.css", html)
        self.assertIn('defer src="app.js"', html)
        self.assertIn("Recently played", (ROOT / "casino.js").read_text())
        self.assertIn("celebrate-open", (ROOT / "app.js").read_text())
        self.assertIn("formatCelebrateSub", (ROOT / "app.js").read_text() + (ROOT / "fx.js").read_text())
        self.assertIn("/assets/fonts/cinzel-900.woff2", html)
        self.assertNotIn("fonts.googleapis.com", html)
        self.assertIn("[hidden]", html)
        self.assertIn("recent-empty", (ROOT / "casino.js").read_text())
        self.assertIn("tableWinBeat", (ROOT / "app.js").read_text())
        app_js = (ROOT / "app.js").read_text()
        fx_js = (ROOT / "fx.js").read_text()
        casino_js = (ROOT / "casino.js").read_text()
        self.assertIn("tableWinPresentation", fx_js)
        self.assertIn("tableMedallion", fx_js)
        self.assertIn("table-win-toast", (ROOT / "index.html").read_text() + app_js)
        self.assertIn("kind: \"table\"", app_js)
        self.assertIn("isTableNatural", casino_js)
        self.assertIn("natural:", casino_js)
        self.assertNotIn("greentea", fx_js[fx_js.find("function tableMedallion"):fx_js.find("function tableMedallion")+1800])

        self.assertIn("level-up-overlay", html)
        self.assertIn("tile-preview", (ROOT / "casino.js").read_text())
        # Full styles.css remains a fallback, but is not render-blocking for modern clients.
        head, _, _ = html.partition("<body")
        # styles.css is only a noscript fallback, not a render-blocking stylesheet.
        self.assertIn("<noscript>", head)
        self.assertNotIn('rel="stylesheet" href="styles.css"', head.split("<noscript>")[0])



    def test_r5_slot_cls_previews_table_motion_a11y(self):
        html = (ROOT / "index.html").read_text()
        core = (ROOT / "css/core.css").read_text()
        fx = (ROOT / "fx.css").read_text()
        casino = (ROOT / "casino.js").read_text()
        # First-paint slot layout is locked before slots.css arrives.
        packed = html.replace(" ", "").replace("\n", "")
        self.assertIn("html.view-slots.layout,body.view-slots.layout", packed)
        self.assertIn("margin:.9remauto2rem", packed)
        self.assertIn('document.documentElement.classList.add("view-" + view)', html)
        self.assertIn('document.write(\'<link rel="preload" as="style" href="\'+viewCss+\'">\')', html)
        self.assertIn('html.classList.toggle("view-slots"', casino.replace(" ", ""))
        # Lobby previews stay quiet but readable.
        self.assertIn('width="22"', casino)
        self.assertIn("tile-preview", fx)
        self.assertIn("22px", fx[fx.find(".tile-preview img"):fx.find(".tile-preview img")+280])
        # Table motion and three-card win beat (wins only, via maybeTableWinBeat).
        self.assertIn("function tossFromChip", casino)
        self.assertIn("CrystalFX.kenoBall", casino)
        self.assertIn('maybeTableWinBeat(st, "THREE CARD")', casino)
        self.assertIn('maybeTableWinBeat(r, "BACCARAT")', casino)
        self.assertIn('maybeTableWinBeat(vpSt, "VIDEO POKER")', casino)
        self.assertIn('maybeTableWinBeat(warSt, "CASINO WAR")', casino)
        # Accessibility: 48px targets, focus rings, labeled icon buttons.
        self.assertIn(":focus-visible", core)
        self.assertIn("min-height: 48px", core)
        self.assertIn("min-width: 48px", core)
        self.assertGreater(html.count("aria-label="), 8)
        self.assertIn('aria-label="Open settings"', html)
        self.assertIn('aria-label="Bet on ${n}"', casino)

    def test_r6_roulette_felt_lobby_notice(self):
        html = (ROOT / "index.html").read_text()
        casino = (ROOT / "casino.js").read_text()
        tables = (ROOT / "css/tables.css").read_text()
        core = (ROOT / "css/core.css").read_text()
        fx = (ROOT / "fx.css").read_text()
        app = (ROOT / "app.js").read_text()
        # Classic 14-column felt, not a 3-wide 48px stack.
        self.assertIn('data-rl-view="split"', casino)
        self.assertIn("function bindRlViews", casino)
        self.assertIn("grid-template-columns: 1.2fr repeat(12, minmax(0, 1fr)) 1.1fr", tables)
        self.assertNotIn("minmax(48px, 1fr));\n    grid-auto-rows: minmax(48px, auto)", tables)
        self.assertIn("rl-view-toggle", tables)
        self.assertIn("chip-badge", tables)
        # Lobby chrome
        self.assertIn("site-notice", html)
        self.assertIn("site-notice-dismiss", html)
        self.assertIn("Coins have no cash value and cannot be redeemed.", html)
        self.assertIn("function updateSiteNotice", app)
        self.assertIn("a.btn { text-decoration: none; }", core)
        self.assertIn("width: 22px", fx)
        self.assertIn("is-press", casino)
        self.assertIn('reduce-effects', casino[casino.find("function reduceMotion"):casino.find("function reduceMotion")+400])
        self.assertIn('rel="preload" as="style" href="css/core.css"', html)
        self.assertIn("fetchpriority=\"high\"", html)



if __name__ == "__main__":
    unittest.main()
