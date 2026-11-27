#!/usr/bin/env python3
"""v11 launch essentials: legal pages, disclosure, errors, tutorial prefs,
and ledger integrity under concurrent claims and duplicate purchases.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))
os.chdir(SERVER_DIR)

os.environ.pop("DATABASE_URL", None)
os.environ.pop("SENTRY_DSN", None)
os.environ.pop("SENTRY_PUBLIC_DSN", None)
os.environ.pop("GOOGLE_CLIENT_ID", None)
os.environ.pop("STRIPE_SECRET_KEY", None)

import db as dbmod
import errors
import game
import legal
import ledger
import prefs


def fresh_db() -> None:
    ledger.DB_PATH = Path(tempfile.mkdtemp()) / "t.db"
    ledger._local.conn = None
    dbmod.reset_local()
    ledger.init_db()


def pid() -> str:
    return str(uuid.uuid4())


SENTENCE = (
    "Practice or success at social casino gaming does not imply future success "
    "at real money gambling."
)


class LegalPageTests(unittest.TestCase):
    def test_exact_simulated_gambling_sentence(self):
        self.assertEqual(legal.SIMULATED_GAMBLING, SENTENCE)
        self.assertEqual(game.SIMULATED_GAMBLING, SENTENCE)
        self.assertIn(SENTENCE, legal.disclosure_block())
        self.assertIn(SENTENCE, legal.privacy_html())
        self.assertIn(SENTENCE, legal.terms_html())

    def test_privacy_covers_required_topics(self):
        text = legal.privacy_html().lower()
        for needle in (
            "google", "name", "email", "avatar", "game progress",
            "purchase", "delete", "no cash value", "18",
        ):
            self.assertIn(needle, text, needle)
        self.assertNotIn("pool_aud", text)
        self.assertNotIn("house pool", text)

    def test_terms_cover_coins_and_age(self):
        text = legal.terms_html().lower()
        self.assertIn("cannot be redeemed", text)
        self.assertIn("18", text)
        self.assertIn("google play billing", text)
        self.assertIn("stripe", text)

    def test_routes_and_config(self):
        import app as app_module

        client = app_module.app.test_client()
        for path in ("/privacy", "/terms"):
            r = client.get(path)
            self.assertEqual(r.status_code, 200, path)
            body = r.get_data(as_text=True)
            self.assertIn(SENTENCE, body)
            self.assertIn("18+", body)
            self.assertIn("cannot be redeemed", body.lower())
        cfg = client.get("/api/config").get_json()
        self.assertEqual(cfg["simulated_gambling"], SENTENCE)
        self.assertEqual(cfg["age_limit"], 18)
        self.assertEqual(cfg["privacy_url"], "/privacy")
        self.assertEqual(cfg["terms_url"], "/terms")
        self.assertIn(SENTENCE, cfg["disclosure"])
        self.assertTrue(cfg.get("sentry_dsn") in (None, ""))
        # existing legal field is unchanged for older clients/tests
        self.assertIn("no monetary value", cfg["legal"].lower())
        text = json.dumps(cfg)
        for banned in ("pool_aud", "cap_aud", "sk_live", "sk_test"):
            self.assertNotIn(banned, text)

    def test_age_gate_and_shop_html_include_sentence(self):
        html = (SERVER_DIR.parent / "index.html").read_text()
        self.assertIn(SENTENCE, html)
        self.assertIn('id="age-simulated"', html)
        self.assertIn('id="shop-legal"', html)
        self.assertIn('id="footer-simulated"', html)
        self.assertIn("/privacy", html)
        self.assertIn("/terms", html)
        self.assertIn("I am 18 or older", html)


class ErrorReportingTests(unittest.TestCase):
    def test_no_dsn_hardcoded_in_source(self):
        root = SERVER_DIR.parent
        paths = [
            root / "server" / "errors.py",
            root / "server" / "app.py",
            root / "server" / "legal.py",
            root / "errors.js",
            root / "app.js",
            root / "index.html",
        ]
        for path in paths:
            text = path.read_text()
            self.assertNotIn("SENTRY_DSN=", text, path.name)
            self.assertNotRegex(text, r"ingest\.sentry\.io", path.name)
            self.assertNotIn("ingest.sentry.io", text, path.name)

    def test_client_error_endpoint_and_rate_limit(self):
        import app as app_module

        errors._hits.clear()
        client = app_module.app.test_client()
        r = client.post("/api/errors", json={"message": "boom", "url": "/slots"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        # Same client is rate limited after the cap
        codes = []
        for i in range(20):
            resp = client.post("/api/errors", json={"message": f"n{i}"})
            codes.append(resp.status_code)
        self.assertIn(429, codes)
        self.assertTrue(any(c == 200 for c in codes))


class TutorialPrefsTests(unittest.TestCase):
    def test_schema_only_when_allowed(self):
        self.assertTrue(prefs.schema_migrate_allowed())
        fresh_db()
        player = pid()
        ledger.ensure_player(player)
        with ledger.transaction() as conn:
            state = prefs.set_tutorial(conn, player, {"status": "done"})
        self.assertEqual(state["status"], "done")
        with ledger.transaction() as conn:
            got = prefs.get_tutorial(conn, player)
        self.assertEqual(got["status"], "done")

    def test_prefs_api(self):
        import app as app_module

        fresh_db()
        # Re-bind the app to this isolated db (init_db already ran at import).
        app_module.ledger.DB_PATH = ledger.DB_PATH
        app_module.ledger._local.conn = None
        dbmod.reset_local()
        ledger.init_db()
        client = app_module.app.test_client()
        r = client.get("/api/prefs")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["tutorial"].get("status"), "pending")
        r2 = client.post("/api/prefs", json={"tutorial": {"status": "skipped"}})
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.get_json()["tutorial"]["status"], "skipped")


class LedgerIntegrityTests(unittest.TestCase):
    def test_rapid_double_claim_daily_only_pays_once(self):
        fresh_db()
        player = pid()
        ledger.ensure_player(player)
        start = ledger.snapshot(player)["coins"]
        results: list[tuple[str, int]] = []
        barrier = threading.Barrier(8)

        def worker() -> None:
            barrier.wait(timeout=10)
            dbmod.reset_local()
            ledger._local.conn = None
            try:
                snap = ledger.claim_daily(player)
                results.append(("ok", int(snap["awarded"])))
            except ledger.BonusUnavailable:
                results.append(("denied", 0))
            except Exception as exc:  # pragma: no cover
                results.append(("err", 0))
                results.append(("err-msg", 0))
                print("claim race error", repr(exc), flush=True)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=25)
        oks = [r for r in results if r[0] == "ok"]
        denied = [r for r in results if r[0] == "denied"]
        self.assertEqual(len(oks), 1, results)
        self.assertEqual(len(denied), 7, results)
        self.assertEqual(ledger.snapshot(player)["coins"], start + game.DAILY_COINS)
        # A follow-up claim is still rejected.
        with self.assertRaises(ledger.BonusUnavailable):
            ledger.claim_daily(player)

    def test_duplicate_purchase_is_idempotent_under_race(self):
        fresh_db()
        player = pid()
        ledger.ensure_player(player)
        start = ledger.snapshot(player)["coins"]
        pack = game.COIN_PACKS[0]
        session = "cs_test_race_" + uuid.uuid4().hex
        results: list[tuple[bool, str]] = []
        barrier = threading.Barrier(8)

        def worker() -> None:
            barrier.wait(timeout=10)
            dbmod.reset_local()
            ledger._local.conn = None
            try:
                ok, msg, snap = ledger.credit_coin_pack(
                    session, player, pack["id"], pack["coins"], pack["price_aud"]
                )
                results.append((ok, msg, snap["coins"] if snap else 0))
            except Exception as exc:  # pragma: no cover
                results.append((False, repr(exc), -1))
                print("purchase race error", repr(exc), flush=True)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=25)
        credited = [r for r in results if r[0] is True]
        already = [r for r in results if r[0] is False and "already" in str(r[1]).lower()]
        self.assertEqual(len(results), 8, results)
        self.assertEqual(len(credited), 1, results)
        self.assertEqual(len(already), 7, results)
        self.assertEqual(ledger.snapshot(player)["coins"], start + pack["coins"])
        # Serial retry remains idempotent.
        ok, msg, snap = ledger.credit_coin_pack(
            session, player, pack["id"], pack["coins"], pack["price_aud"]
        )
        self.assertFalse(ok)
        self.assertIn("already", msg.lower())
        self.assertEqual(snap["coins"], start + pack["coins"])


if __name__ == "__main__":
    unittest.main()
