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
        # Full styles.css remains a fallback, but is not render-blocking for modern clients.
        head, _, _ = html.partition("<body")
        # styles.css is only a noscript fallback, not a render-blocking stylesheet.
        self.assertIn("<noscript>", head)
        self.assertNotIn('rel="stylesheet" href="styles.css"', head.split("<noscript>")[0])




if __name__ == "__main__":
    unittest.main()
