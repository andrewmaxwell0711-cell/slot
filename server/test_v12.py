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


if __name__ == "__main__":
    unittest.main()
