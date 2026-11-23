#!/usr/bin/env python3
"""v9 player accounts: mocked Google sign-in, guest merge, persistence,
delete-my-account, and Stripe credits to the signed-in player.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))
os.chdir(SERVER_DIR)

# Isolate tests from any developer DATABASE_URL / Google client.
os.environ.pop("DATABASE_URL", None)
os.environ["GOOGLE_CLIENT_ID"] = "test-client.apps.googleusercontent.com"

import auth
import db as dbmod
import game
import ledger
import prizes


def fresh_db() -> None:
    ledger.DB_PATH = Path(tempfile.mkdtemp()) / "t.db"
    ledger._local.conn = None
    dbmod.reset_local()
    ledger.init_db()


def pid() -> str:
    return str(uuid.uuid4())


def google_profile(sub: str = "sub-alice", **extra) -> dict:
    base = {
        "sub": sub,
        "email": "alice@example.com",
        "email_verified": True,
        "name": "Alice Example",
        "given_name": "Alice",
        "family_name": "Example",
        "picture": "https://lh3.googleusercontent.com/a/test-photo",
    }
    base.update(extra)
    return base


class DisplayNameTests(unittest.TestCase):
    def test_first_name_and_initial(self):
        self.assertEqual(auth.format_display_name("Alice", "Example", "Alice Example"), "Alice E.")
        self.assertEqual(auth.format_display_name("Bob", None, None), "Bob")
        self.assertEqual(auth.format_display_name(None, None, "Carol Diaz"), "Carol D.")
        self.assertNotIn("@", auth.format_display_name(None, None, None))

    def test_picture_only_allows_https_googleusercontent(self):
        self.assertIsNotNone(auth.safe_picture_url("https://lh3.googleusercontent.com/a/x"))
        self.assertIsNone(auth.safe_picture_url("http://lh3.googleusercontent.com/a/x"))
        self.assertIsNone(auth.safe_picture_url("https://evil.example/x.png"))
        self.assertIsNone(auth.safe_picture_url("javascript:alert(1)"))


class PersistenceTests(unittest.TestCase):
    def test_progress_survives_reconnect(self):
        fresh_db()
        path = ledger.DB_PATH
        player = pid()
        ledger.ensure_player(player)
        with ledger.transaction() as conn:
            conn.execute(
                "UPDATE balances SET amount = 41000 WHERE player_id = ? AND asset = ?",
                (player, game.COIN_ASSET),
            )
            conn.execute("UPDATE players SET spins = 7, xp = 20, level = 2 WHERE id = ?", (player,))
        ledger._local.conn = None
        dbmod.reset_local()
        ledger.DB_PATH = path
        snap = ledger.snapshot(player)
        self.assertEqual(snap["coins"], 41000)
        self.assertEqual(snap["stats"]["spins"], 7)
        self.assertEqual(snap["profile"]["level"], 2)

    def test_sqlite_used_when_path_overridden(self):
        fresh_db()
        self.assertEqual(dbmod.backend_name(ledger.DB_PATH), "sqlite")
        self.assertFalse(ledger.get_conn().postgres)


class GoogleAuthTests(unittest.TestCase):
    def setUp(self):
        fresh_db()
        os.environ["GOOGLE_CLIENT_ID"] = "test-client.apps.googleusercontent.com"
        import app as appmod

        self.appmod = appmod
        self.app = appmod.app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def _sign_in(self, profile, guest_cookie: str | None = None):
        if guest_cookie:
            self.client.set_cookie(auth.SESSION_COOKIE, "", path="/")  # no-op if missing
            self.client.set_cookie("fr_player", guest_cookie, path="/")
        with patch.object(auth, "verify_google_token", return_value=profile):
            res = self.client.post(
                "/api/auth/google",
                json={"credential": "fake-token"},
            )
        return res

    def test_verify_is_mocked_and_session_cookie_is_httponly(self):
        guest = self.client.get("/api/balance")
        self.assertEqual(guest.status_code, 200)
        body = guest.get_json()
        self.assertFalse(body["account"]["signed_in"])
        self.assertTrue(body["account"]["google_enabled"])

        res = self._sign_in(google_profile())
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["account"]["signed_in"])
        self.assertEqual(data["account"]["display_name"], "Alice E.")
        self.assertEqual(data["account"]["email"], "alice@example.com")
        self.assertNotIn("google_sub", data["account"])

        # Session cookie is HttpOnly; CSRF cookie is readable.
        set_cookie = "; ".join(res.headers.getlist("Set-Cookie"))
        self.assertIn(auth.SESSION_COOKIE + "=", set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=Lax", set_cookie, set_cookie)
        self.assertIn(auth.CSRF_COOKIE + "=", set_cookie)

        me = self.client.get("/api/auth/me")
        self.assertTrue(me.get_json()["account"]["signed_in"])

    def test_google_disabled_when_client_id_missing(self):
        prev = os.environ.pop("GOOGLE_CLIENT_ID", None)
        try:
            cfg = self.client.get("/api/config").get_json()
            self.assertFalse(cfg["google_enabled"])
            self.assertIsNone(cfg["google_client_id"])
            res = self.client.post("/api/auth/google", json={"credential": "x"})
            self.assertEqual(res.status_code, 503)
            # Guest mode still works.
            bal = self.client.get("/api/balance")
            self.assertEqual(bal.status_code, 200)
            self.assertFalse(bal.get_json()["account"]["signed_in"])
            self.assertEqual(bal.get_json()["coins"], game.STARTING_COINS)
        finally:
            if prev is not None:
                os.environ["GOOGLE_CLIENT_ID"] = prev

    def test_logout_requires_csrf_and_mints_new_guest(self):
        self._sign_in(google_profile("sub-logout"))
        res = self.client.post("/api/auth/logout", json={})
        self.assertEqual(res.status_code, 403)
        csrf = None
        for header in self.client.get("/api/auth/me").headers.getlist("Set-Cookie"):
            pass
        # CSRF was set at sign-in; pull from the cookie jar.
        csrf = self.client.get_cookie(auth.CSRF_COOKIE)
        token = csrf.value if csrf else None
        self.assertTrue(token)
        out = self.client.post(
            "/api/auth/logout",
            json={},
            headers={"X-CSRF-Token": token},
        )
        self.assertEqual(out.status_code, 200)
        data = out.get_json()
        self.assertFalse(data["account"]["signed_in"])
        me = self.client.get("/api/auth/me").get_json()
        self.assertFalse(me["account"]["signed_in"])
        self.assertEqual(me["coins"], game.STARTING_COINS)


class MergeTests(unittest.TestCase):
    def test_first_login_adopts_guest_without_double_grant(self):
        fresh_db()
        guest = pid()
        ledger.ensure_player(guest)
        with ledger.transaction() as conn:
            conn.execute(
                "UPDATE balances SET amount = 33000 WHERE player_id = ? AND asset = ?",
                (guest, game.COIN_ASSET),
            )
            conn.execute("UPDATE players SET spins = 4 WHERE id = ?", (guest,))
        account = auth.upsert_account_from_google(google_profile("sub-adopt"), guest)
        self.assertEqual(account["player_id"], guest)
        self.assertTrue(account["created"])
        snap = ledger.snapshot(account["player_id"])
        self.assertEqual(snap["coins"], 33000)
        self.assertEqual(snap["stats"]["spins"], 4)

    def test_merge_adds_guest_progress_once_and_blocks_double_daily(self):
        fresh_db()
        from prizes import perth_date

        account_player = pid()
        guest = pid()
        ledger.ensure_player(account_player)
        ledger.ensure_player(guest)
        today = perth_date()
        # Account already claimed today's daily; guest has coins, xp, a trophy
        # and also "claimed" today — merge must not reset the claim.
        with ledger.transaction() as conn:
            conn.execute(
                "UPDATE balances SET amount = 40000 WHERE player_id = ? AND asset = ?",
                (account_player, game.COIN_ASSET),
            )
            conn.execute(
                "UPDATE players SET spins = 10, xp = 10, level = 1, last_daily_date = ? WHERE id = ?",
                (today, account_player),
            )
            conn.execute(
                "UPDATE balances SET amount = 12000 WHERE player_id = ? AND asset = ?",
                (guest, game.COIN_ASSET),
            )
            conn.execute(
                "UPDATE players SET spins = 3, xp = 15, level = 1, last_daily_date = ? WHERE id = ?",
                (today, guest),
            )
            conn.execute(
                "INSERT INTO trophies (player_id, trophy_id, unlocked_at) VALUES (?, ?, ?)",
                (guest, "first-spin", "2026-01-01T00:00:00+00:00"),
            )
        account = auth.upsert_account_from_google(google_profile("sub-merge"), account_player)
        # Returning user: player_id stays the pre-existing account player, not the guest.
        # upsert will adopt guest only on first create. Simulate returning: create account
        # on account_player first (already done if we pass account_player as guest at
        # creation). Re-build: the first upsert used account_player as the adopted row.
        self.assertEqual(account["player_id"], account_player)

        # Fresh "other device" guest merge.
        merged = auth.merge_guest(account["id"], guest)
        self.assertEqual(merged["merge_used"], 1)
        snap = ledger.snapshot(account_player)
        self.assertEqual(snap["coins"], 52000)
        self.assertEqual(snap["stats"]["spins"], 13)
        self.assertIn("first-spin", snap["trophies"]["unlocked"])
        self.assertFalse(snap["bonuses"]["daily_available"])
        # Guest row is gone.
        gone = ledger.get_conn().execute("SELECT id FROM players WHERE id = ?", (guest,)).fetchone()
        self.assertIsNone(gone)
        # Second merge is refused.
        other = pid()
        ledger.ensure_player(other)
        with ledger.transaction() as conn:
            conn.execute(
                "UPDATE balances SET amount = 90000 WHERE player_id = ? AND asset = ?",
                (other, game.COIN_ASSET),
            )
            conn.execute("UPDATE players SET spins = 9 WHERE id = ?", (other,))
        with self.assertRaises(ValueError):
            auth.merge_guest(account["id"], other)
        # Coins unchanged after the refused merge.
        self.assertEqual(ledger.snapshot(account_player)["coins"], 52000)

    def test_leaderboard_uses_display_name_not_email(self):
        fresh_db()
        player = pid()
        ledger.ensure_player(player)
        auth.upsert_account_from_google(google_profile("sub-board"), player)
        day = prizes.perth_date()
        week = prizes.perth_week()
        weekend = prizes.perth_weekend()
        ledger.get_conn().execute(
            """
            INSERT INTO spin_records (player_id, created_at, perth_date, perth_week, perth_weekend, bet_aud, win_aud)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (player, "2026-11-24T00:00:00+00:00", day, week, weekend, 1.0, 5.0),
        )
        board = prizes.leaderboard("daily", "biggest", viewer_id=player)
        self.assertTrue(board["entries"])
        names = [e["nickname"] for e in board["entries"]]
        self.assertIn("Alice E.", names)
        for name in names:
            self.assertNotIn("@", name)
            self.assertNotIn("example.com", name.lower())


class DeleteAccountTests(unittest.TestCase):
    def test_delete_removes_account_and_player_row(self):
        fresh_db()
        player = pid()
        ledger.ensure_player(player)
        account = auth.upsert_account_from_google(google_profile("sub-del"), player)
        aid, pid_ = account["id"], account["player_id"]
        session = auth.create_session(aid)
        self.assertIsNotNone(auth.load_session(session["token"]))
        auth.delete_account(aid)
        conn = ledger.get_conn()
        self.assertIsNone(conn.execute("SELECT id FROM accounts WHERE id = ?", (aid,)).fetchone())
        self.assertIsNone(conn.execute("SELECT id FROM players WHERE id = ?", (pid_,)).fetchone())
        self.assertIsNone(conn.execute("SELECT * FROM balances WHERE player_id = ?", (pid_,)).fetchone())
        self.assertIsNone(auth.load_session(session["token"]))


class StripeCreditTests(unittest.TestCase):
    def test_pack_credits_signed_in_account_and_is_idempotent(self):
        fresh_db()
        player = pid()
        ledger.ensure_player(player)
        account = auth.upsert_account_from_google(google_profile("sub-stripe"), player)
        pid_ = account["player_id"]
        before = ledger.snapshot(pid_)["coins"]
        pack = game.COIN_PACKS[0]
        session_id = "cs_test_account_credit_1"
        credited, msg, snap = ledger.credit_coin_pack(
            session_id, pid_, pack["id"], pack["coins"], pack["price_aud"]
        )
        self.assertTrue(credited)
        self.assertEqual(snap["coins"], before + pack["coins"])
        # Same Checkout session must not credit twice, including if a guest id is used.
        guest = pid()
        ledger.ensure_player(guest)
        credited2, _, snap2 = ledger.credit_coin_pack(
            session_id, guest, pack["id"], pack["coins"], pack["price_aud"]
        )
        self.assertFalse(credited2)
        self.assertEqual(ledger.snapshot(pid_)["coins"], before + pack["coins"])
        self.assertEqual(ledger.snapshot(guest)["coins"], game.STARTING_COINS)
        rec = ledger.get_processed_session(session_id)
        self.assertEqual(rec["player_id"], pid_)

    def test_guest_purchase_still_works(self):
        fresh_db()
        guest = pid()
        ledger.ensure_player(guest)
        pack = game.COIN_PACKS[0]
        credited, _, snap = ledger.credit_coin_pack(
            "cs_test_guest_1", guest, pack["id"], pack["coins"], pack["price_aud"]
        )
        self.assertTrue(credited)
        self.assertEqual(snap["coins"], game.STARTING_COINS + pack["coins"])


class TokenVerificationTests(unittest.TestCase):
    def test_missing_token_raises(self):
        os.environ["GOOGLE_CLIENT_ID"] = "test-client.apps.googleusercontent.com"
        with self.assertRaises(ValueError):
            auth.verify_google_token("")

    def test_unconfigured_raises(self):
        prev = os.environ.pop("GOOGLE_CLIENT_ID", None)
        try:
            with self.assertRaises(ValueError):
                auth.verify_google_token("whatever")
        finally:
            if prev is not None:
                os.environ["GOOGLE_CLIENT_ID"] = prev

    def test_verify_oauth2_token_is_called_with_audience(self):
        os.environ["GOOGLE_CLIENT_ID"] = "test-client.apps.googleusercontent.com"
        fake = {
            "iss": "accounts.google.com",
            "sub": "sub-xyz",
            "email": "bob@example.com",
            "email_verified": True,
            "name": "Bob Zee",
            "given_name": "Bob",
            "family_name": "Zee",
            "picture": "https://lh3.googleusercontent.com/a/bob",
        }
        with patch("google.oauth2.id_token.verify_oauth2_token", return_value=fake) as mock_verify:
            info = auth.verify_google_token("real-looking-token")
        self.assertEqual(info["sub"], "sub-xyz")
        self.assertEqual(info["email"], "bob@example.com")
        args, kwargs = mock_verify.call_args
        self.assertEqual(args[0], "real-looking-token")
        audience = kwargs.get("audience")
        if audience is None and len(args) >= 3:
            audience = args[2]
        self.assertEqual(audience, "test-client.apps.googleusercontent.com")


if __name__ == "__main__":
    unittest.main()
