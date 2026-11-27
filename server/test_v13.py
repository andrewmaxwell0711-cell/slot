#!/usr/bin/env python3
"""v13 clubs: create/join/leave, member cap, weekly goal via events.on_play,
atomic idempotent house-issued rewards, no player-to-player transfers.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import unittest
import uuid
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
os.environ.pop("ALLOW_SCHEMA_MIGRATE", None)

import db as dbmod
import events
import game
import ledger
import clubs
import prefs


def fresh_db() -> None:
    ledger.DB_PATH = Path(tempfile.mkdtemp()) / "t.db"
    ledger._local.conn = None
    dbmod.reset_local()
    ledger.init_db()


def pid() -> str:
    return "p_" + uuid.uuid4().hex


def house_pool() -> float:
    row = ledger.get_conn().execute("SELECT pool_aud FROM house WHERE id = 1").fetchone()
    return float(row["pool_aud"] if row else 0)


def seed_week_points(club_id: str, player_id: str, points: int, spins: int = 1) -> None:
    week = clubs.week_id()
    conn = ledger.get_conn()
    conn.execute(
        """
        INSERT INTO club_week_progress
            (club_id, week_id, player_id, spins, bet_coins, win_coins, points)
        VALUES (?, ?, ?, ?, ?, 0, ?)
        ON CONFLICT (club_id, week_id, player_id) DO UPDATE SET
            spins = excluded.spins,
            bet_coins = excluded.bet_coins,
            points = excluded.points
        """,
        (club_id, week, player_id, spins, points, points),
    )
    conn.commit()


def make_club(owner: str, name: str = "Gem Guild", vis: str = "open") -> dict:
    ledger.ensure_player(owner)
    return clubs.create_club(owner, name, "ruby", vis)


class ClubMembershipTests(unittest.TestCase):
    def test_create_join_leave_and_member_cap_enforced(self):
        fresh_db()
        leader = pid()
        state = make_club(leader, "Cap Test Club")
        cid = state["club"]["id"]
        self.assertEqual(state["club"]["member_count"], 1)
        self.assertEqual(state["club"]["cap"], 30)
        self.assertEqual(clubs.CLUB_CAP, 30)

        # Fill to the cap.
        for i in range(clubs.CLUB_CAP - 1):
            member = pid()
            ledger.ensure_player(member)
            clubs.join_club(member, club_id=cid)

        self.assertEqual(
            ledger.get_conn().execute(
                "SELECT COUNT(*) AS n FROM club_members WHERE club_id = ?", (cid,)
            ).fetchone()["n"],
            clubs.CLUB_CAP,
        )

        extra = pid()
        ledger.ensure_player(extra)
        with self.assertRaises(clubs.ClubError) as ctx:
            clubs.join_club(extra, club_id=cid)
        self.assertIn("full", str(ctx.exception).lower())
        self.assertEqual(
            ledger.get_conn().execute(
                "SELECT COUNT(*) AS n FROM club_members WHERE club_id = ?", (cid,)
            ).fetchone()["n"],
            clubs.CLUB_CAP,
        )
        self.assertIsNone(clubs.my_club_id(extra))

        # Leave frees a seat; a new player can join.
        clubs.leave_club(leader)
        clubs.join_club(extra, club_id=cid)
        self.assertEqual(clubs.my_club_id(extra), cid)

    def test_invite_only_requires_code(self):
        fresh_db()
        leader = pid()
        state = make_club(leader, "Invite Club", vis="invite")
        cid = state["club"]["id"]
        code = state["club"]["invite_code"]
        outsider = pid()
        ledger.ensure_player(outsider)
        with self.assertRaises(clubs.ClubError):
            clubs.join_club(outsider, club_id=cid)
        clubs.join_club(outsider, invite_code=code)
        self.assertEqual(clubs.my_club_id(outsider), cid)

    def test_one_club_per_player(self):
        fresh_db()
        a = pid()
        make_club(a, "First Club")
        with self.assertRaises(clubs.ClubError):
            make_club(a, "Second Club")


class ClubRewardTests(unittest.TestCase):
    def test_concurrent_reward_claim_does_not_double_pay(self):
        fresh_db()
        player = pid()
        state = make_club(player, "Race Club")
        cid = state["club"]["id"]
        seed_week_points(cid, player, clubs.TIERS[0]["points"], spins=3)
        start = ledger.snapshot(player)["coins"]
        pool_before = house_pool()
        results: list[tuple[str, int]] = []
        barrier = threading.Barrier(8)

        def worker() -> None:
            barrier.wait(timeout=10)
            dbmod.reset_local()
            ledger._local.conn = None
            try:
                out = clubs.claim_reward(player)
                results.append(("ok", int(out.get("awarded") or 0)))
            except clubs.ClubError as exc:
                results.append(("denied", 0 if "already" in str(exc).lower() else -1))
            except Exception as exc:  # pragma: no cover
                results.append(("err", 0))
                print("club claim race error", repr(exc), flush=True)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=25)

        # Some workers return already_claimed=True with awarded=0 instead of raising.
        paid = [r for r in results if r[0] == "ok" and r[1] > 0]
        zero_or_denied = [r for r in results if not (r[0] == "ok" and r[1] > 0)]
        self.assertEqual(len(results), 8, results)
        self.assertEqual(len(paid), 1, results)
        self.assertEqual(len(zero_or_denied), 7, results)
        self.assertEqual(paid[0][1], clubs.TIERS[0]["coins"])
        self.assertEqual(ledger.snapshot(player)["coins"], start + clubs.TIERS[0]["coins"])
        self.assertEqual(house_pool(), pool_before)

        again = clubs.claim_reward(player)
        self.assertTrue(again.get("already_claimed"))
        self.assertEqual(int(again.get("awarded") or 0), 0)
        self.assertEqual(ledger.snapshot(player)["coins"], start + clubs.TIERS[0]["coins"])
        # Unique claim key is present exactly once.
        week = clubs.week_id()
        key = clubs.claim_key(player, week)
        n = ledger.get_conn().execute(
            "SELECT COUNT(*) AS n FROM club_reward_claims WHERE claim_key = ?", (key,)
        ).fetchone()["n"]
        self.assertEqual(int(n), 1)
        entries = ledger.get_conn().execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(amount),0) AS amt FROM ledger_entries WHERE kind = 'club_reward' AND player_id = ?",
            (player,),
        ).fetchone()
        self.assertEqual(int(entries["n"]), 1)
        self.assertEqual(int(entries["amt"]), clubs.TIERS[0]["coins"])

    def test_leave_and_rejoin_same_week_does_not_double_claim(self):
        fresh_db()
        player = pid()
        mate = pid()
        state = make_club(player, "Rejoin Club")
        cid = state["club"]["id"]
        ledger.ensure_player(mate)
        clubs.join_club(mate, club_id=cid)
        seed_week_points(cid, player, clubs.TIERS[1]["points"], spins=5)
        start = ledger.snapshot(player)["coins"]
        first = clubs.claim_reward(player)
        self.assertEqual(int(first["awarded"]), clubs.TIERS[1]["coins"])
        self.assertEqual(ledger.snapshot(player)["coins"], start + clubs.TIERS[1]["coins"])

        clubs.leave_club(player)
        self.assertIsNone(clubs.my_club_id(player))
        # A teammate kept the club open. Rejoin the same week and try to claim again.
        clubs.join_club(player, club_id=cid)
        seed_week_points(cid, player, clubs.TIERS[2]["points"], spins=8)
        again = clubs.claim_reward(player)
        self.assertTrue(again.get("already_claimed"))
        self.assertEqual(int(again.get("awarded") or 0), 0)
        self.assertEqual(ledger.snapshot(player)["coins"], start + clubs.TIERS[1]["coins"])
        week = clubs.week_id()
        n = ledger.get_conn().execute(
            "SELECT COUNT(*) AS n FROM club_reward_claims WHERE player_id = ? AND week_id = ?",
            (player, week),
        ).fetchone()["n"]
        self.assertEqual(int(n), 1)

    def test_cannot_claim_from_another_club_same_week(self):
        fresh_db()
        player = pid()
        a = make_club(player, "Club A")
        seed_week_points(a["club"]["id"], player, clubs.TIERS[0]["points"], spins=2)
        clubs.claim_reward(player)
        clubs.leave_club(player)
        other = pid()
        b = make_club(other, "Club B")
        clubs.join_club(player, club_id=b["club"]["id"])
        seed_week_points(b["club"]["id"], player, clubs.TIERS[2]["points"], spins=2)
        again = clubs.claim_reward(player)
        self.assertTrue(again.get("already_claimed"))
        self.assertEqual(int(again.get("awarded") or 0), 0)


class ClubProgressAndPolicyTests(unittest.TestCase):
    def test_on_play_hook_adds_weekly_points(self):
        fresh_db()
        player = pid()
        state = make_club(player, "Spin Club")
        cid = state["club"]["id"]
        events.on_play(player, "slots", 100, 250)
        events.on_play(player, "roulette", 50, 0)
        week = clubs.week_id()
        row = ledger.get_conn().execute(
            "SELECT spins, bet_coins, win_coins, points FROM club_week_progress WHERE club_id = ? AND week_id = ? AND player_id = ?",
            (cid, week, player),
        ).fetchone()
        self.assertEqual(int(row["spins"]), 2)
        self.assertEqual(int(row["bet_coins"]), 150)
        self.assertEqual(int(row["win_coins"]), 250)
        self.assertEqual(int(row["points"]), 400)
        # Leaving stops new credit; prior points remain.
        clubs.leave_club(player)
        events.on_play(player, "slots", 1000, 1000)
        row2 = ledger.get_conn().execute(
            "SELECT points FROM club_week_progress WHERE club_id = ? AND week_id = ? AND player_id = ?",
            (cid, week, player),
        ).fetchone()
        self.assertEqual(int(row2["points"]), 400)

    def test_no_player_to_player_coin_transfer(self):
        fresh_db()
        self.assertFalse(hasattr(clubs, "transfer"))
        self.assertFalse(hasattr(clubs, "send_coins"))
        self.assertFalse(hasattr(clubs, "gift"))
        import app as app_module
        rules = [str(r) for r in app_module.app.url_map.iter_rules()]
        for path in rules:
            self.assertNotIn("transfer", path.lower())
            self.assertNotIn("send-coins", path.lower())
            self.assertNotIn("gift", path.lower())

    def test_schema_is_gated_and_documented(self):
        self.assertTrue((ROOT / "docs/migrations/2026-11-28-clubs.md").is_file())
        doc = (ROOT / "docs/migrations/2026-11-28-clubs.md").read_text()
        self.assertIn("ALLOW_SCHEMA_MIGRATE", doc)
        self.assertIn("Do not run this branch against the production", doc)
        self.assertTrue(prefs.schema_migrate_allowed())  # local SQLite
        # When a hosted URL is set without the flag, ensure_schema is a no-op.
        os.environ["DATABASE_URL"] = "postgres://example/db"
        os.environ.pop("ALLOW_SCHEMA_MIGRATE", None)
        try:
            self.assertFalse(prefs.schema_migrate_allowed())
        finally:
            os.environ.pop("DATABASE_URL", None)

    def test_quick_chat_rejects_free_text(self):
        fresh_db()
        player = pid()
        make_club(player, "Chat Club")
        with self.assertRaises(clubs.ClubError):
            clubs.post_chat(player, "hello there")
        out = clubs.post_chat(player, "gg")
        self.assertEqual(out["club"]["chat"][-1]["text"], "Good game!")
        self.assertEqual(out["club"]["chat"][-1]["phrase_id"], "gg")

    def test_spa_and_static_routes(self):
        import app as app_module
        self.assertIn("clubs", app_module.SPA_PAGES)
        self.assertIn("clubs.js", app_module.ALLOWED_STATIC)
        client = app_module.app.test_client()
        self.assertEqual(client.get("/clubs").status_code, 200)
        self.assertEqual(client.get("/clubs.js").status_code, 200)
        self.assertEqual(client.get("/css/clubs.css").status_code, 200)
        html = (ROOT / "index.html").read_text()
        self.assertIn("Practice or success at social casino gaming does not imply future success at real money gambling.", html)
        self.assertIn('href="#/clubs"', html)
        self.assertIn('id="clubs-page"', html)
        # No fifth bottom-nav item.
        self.assertIn("grid-template-columns:repeat(4,1fr)", html)
        self.assertNotIn('data-nav="clubs"', html)


if __name__ == "__main__":
    unittest.main()
