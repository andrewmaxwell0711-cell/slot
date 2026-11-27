#!/usr/bin/env python3
"""v14 season pass: concurrent claims, mission XP once, season rollover,
and losing-spin XP without a win celebration.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import unittest
import uuid
from datetime import timedelta
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
import ledger
import prefs
import season


def fresh_db() -> None:
    season.set_clock(None)
    ledger.DB_PATH = Path(tempfile.mkdtemp()) / "t.db"
    ledger._local.conn = None
    dbmod.reset_local()
    ledger.init_db()


def pid() -> str:
    return "p_" + uuid.uuid4().hex


def grant_xp(player: str, amount: int) -> None:
    sid = season.current_season()["id"]
    with ledger.transaction() as conn:
        season.ensure_schema(conn)
        season._ensure_progress(conn, player, sid)
        season._add_xp(conn, player, sid, amount)


class SeasonClaimTests(unittest.TestCase):
    def tearDown(self) -> None:
        season.set_clock(None)

    def test_concurrent_tier_claim_does_not_double_pay(self):
        fresh_db()
        player = pid()
        ledger.ensure_player(player)
        reward = season._reward_for("free", 1)
        self.assertEqual(reward["kind"], "coins")
        grant_xp(player, season.cumulative_xp(1))
        start = ledger.snapshot(player)["coins"]
        pool_row = ledger.get_conn().execute("SELECT pool_aud FROM house WHERE id = 1").fetchone()
        pool_before = float(pool_row["pool_aud"])
        results: list[tuple[str, int]] = []
        barrier = threading.Barrier(8)

        def worker() -> None:
            barrier.wait(timeout=10)
            dbmod.reset_local()
            ledger._local.conn = None
            try:
                out = season.claim_tier(player, 1, "free")
                results.append(("ok", int(out.get("awarded") or 0)))
            except season.SeasonError as exc:
                results.append(("denied", 0 if "already" in str(exc).lower() else -1))
            except Exception as exc:  # pragma: no cover
                results.append(("err", 0))
                print("season claim race error", repr(exc), flush=True)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=25)

        paid = [r for r in results if r[0] == "ok" and r[1] > 0]
        zero_or_denied = [r for r in results if not (r[0] == "ok" and r[1] > 0)]
        self.assertEqual(len(results), 8, results)
        self.assertEqual(len(paid), 1, results)
        self.assertEqual(len(zero_or_denied), 7, results)
        self.assertEqual(paid[0][1], int(reward["amount"]))
        self.assertEqual(ledger.snapshot(player)["coins"], start + int(reward["amount"]))
        pool_after = ledger.get_conn().execute("SELECT pool_aud FROM house WHERE id = 1").fetchone()
        self.assertEqual(float(pool_after["pool_aud"]), pool_before)

        again = season.claim_tier(player, 1, "free")
        self.assertTrue(again.get("already_claimed"))
        self.assertEqual(int(again.get("awarded") or 0), 0)
        self.assertEqual(ledger.snapshot(player)["coins"], start + int(reward["amount"]))
        key = season.claim_key(player, season.current_season()["id"], "free", 1)
        n = ledger.get_conn().execute(
            "SELECT COUNT(*) AS n FROM season_claims WHERE claim_key = ?", (key,)
        ).fetchone()["n"]
        self.assertEqual(int(n), 1)
        entries = ledger.get_conn().execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(amount),0) AS amt FROM ledger_entries WHERE kind = 'season_reward' AND player_id = ?",
            (player,),
        ).fetchone()
        self.assertEqual(int(entries["n"]), 1)
        self.assertEqual(int(entries["amt"]), int(reward["amount"]))

    def test_premium_is_not_sold(self):
        fresh_db()
        player = pid()
        ledger.ensure_player(player)
        grant_xp(player, season.cumulative_xp(1))
        with self.assertRaises(season.SeasonError) as ctx:
            season.claim_tier(player, 1, "premium")
        self.assertIn("coming soon", str(ctx.exception).lower())
        self.assertFalse(season.PREMIUM_PURCHASE_ENABLED)
        src = (ROOT / "server/season.py").read_text()
        self.assertIn("TODO(android)", src)
        self.assertIn("Play Billing", src)
        self.assertIn("Stripe remains test-mode", src)


class SeasonMissionAndPlayTests(unittest.TestCase):
    def tearDown(self) -> None:
        season.set_clock(None)

    def test_mission_completing_twice_does_not_double_xp(self):
        fresh_db()
        player = pid()
        ledger.ensure_player(player)
        # Use a tiny mission: the "play 20 games" daily, or force progress on a known id.
        # Pick a day whose dailies include d_play_20, otherwise drive a weekly bet mission
        # by applying the same completion twice via record_play after target is met.
        found = None
        start = season.now()
        for i in range(8):
            when = start + timedelta(days=i)
            dailies = season.daily_missions_for(when)
            if any(m["id"] == "d_play_20" for m in dailies):
                found = when
                break
        self.assertIsNotNone(found, "d_play_20 should appear in the 6-day rotation")
        season.set_clock(found)
        # 20 plays complete the mission (150 XP) plus 20 * play_xp(100, 0) play XP.
        first = None
        for _ in range(20):
            first = season.record_play(player, "slots", 100, 0)
        st = season.season_state(player)
        play_only = 20 * season.play_xp(100, 0)
        self.assertEqual(st["xp"], play_only + 150)
        daily = {m["id"]: m for m in st["missions"]["daily"]}
        self.assertTrue(daily["d_play_20"]["completed"])
        self.assertTrue(daily["d_play_20"]["xp_granted"])
        # Completing / playing past the target must not pay mission XP again.
        for _ in range(10):
            season.record_play(player, "slots", 100, 0)
        st2 = season.season_state(player)
        self.assertEqual(st2["xp"], st["xp"] + 10 * season.play_xp(100, 0))
        self.assertTrue({m["id"]: m for m in st2["missions"]["daily"]}["d_play_20"]["xp_granted"])
        self.assertEqual(season.season_state(player)["xp"], st2["xp"])

    def test_losing_spin_counts_xp_without_win_celebration(self):
        fresh_db()
        player = pid()
        ledger.ensure_player(player)
        result = season.record_play(player, "slots", 250, 0)
        self.assertEqual(result["xp_gained"], season.play_xp(250, 0))
        self.assertGreater(result["xp_gained"], 0)
        self.assertFalse(result["celebrate"])
        self.assertFalse(result["win_celebration"])
        # A win grants the same play XP — wins do not inflate play XP or auto-celebrate.
        win = season.record_play(player, "slots", 250, 10_000)
        self.assertEqual(win["xp_gained"], season.play_xp(250, 10_000))
        self.assertEqual(win["xp_gained"], result["xp_gained"])
        self.assertFalse(win["celebrate"])
        self.assertFalse(win["win_celebration"])
        st = season.season_state(player)
        self.assertEqual(st["xp"], result["xp_gained"] + win["xp_gained"])
        self.assertFalse(st["celebrate"])
        self.assertFalse(st["win_celebration"])
        # Frontend must never celebrate a losing table/slot result.
        casino = (ROOT / "casino.js").read_text()
        self.assertIn("never celebrate a loss", casino)
        self.assertIn("if (!(net > 0 && payout > 0)) return;", casino)
        # Season UI may celebrate a *claim*, never a play.
        js = (ROOT / "season.js").read_text()
        self.assertIn("celebrate", js)
        self.assertNotIn("record_play", js)
        self.assertIn("onClaim", js)


class SeasonRolloverTests(unittest.TestCase):
    def tearDown(self) -> None:
        season.set_clock(None)

    def test_season_rollover_starts_a_fresh_track(self):
        fresh_db()
        player = pid()
        ledger.ensure_player(player)
        # Mid-season 1 (epoch is 2 Nov 2026).
        mid = season.SEASON_EPOCH + timedelta(days=10, hours=12)
        season.set_clock(mid)
        sid1 = season.current_season()["id"]
        self.assertTrue(season.season_open())
        grant_xp(player, season.cumulative_xp(3))
        first = season.claim_tier(player, 1, "free")
        self.assertGreater(int(first["awarded"] or 0), 0)
        st1 = season.season_state(player)
        self.assertEqual(st1["season"]["id"], sid1)
        self.assertEqual(st1["tier"], 3)
        self.assertIn(1, st1["claims"]["free"])
        coins_after = ledger.snapshot(player)["coins"]

        # Exact end instant is the start of the next season.
        season.set_clock(season.SEASON_EPOCH + timedelta(days=season.SEASON_DAYS))
        st2 = season.season_state(player)
        self.assertNotEqual(st2["season"]["id"], sid1)
        self.assertEqual(st2["xp"], 0)
        self.assertEqual(st2["tier"], 0)
        self.assertEqual(st2["claims"]["free"], [])
        # Old claims remain on the previous season key; they cannot be cashed again.
        n = ledger.get_conn().execute(
            "SELECT COUNT(*) AS n FROM season_claims WHERE player_id = ? AND season_id = ?",
            (player, sid1),
        ).fetchone()["n"]
        self.assertEqual(int(n), 1)
        # Unclaimed season-1 tiers expire with the rollover; only the current season can be claimed.
        # A claim in the new season is refused until that track is earned again.
        with self.assertRaises(season.SeasonError):
            season.claim_tier(player, 1, "free")
        self.assertEqual(ledger.snapshot(player)["coins"], coins_after)
        # End date is the real clock, not a fake countdown string.
        self.assertIn("Australia/Perth", st2["season"]["ends_at_label"])
        self.assertEqual(st2["season"]["ends_at"], season.current_season()["ends_at"])
        # Going back to season 1, the already-paid claim stays idempotent.
        season.set_clock(mid)
        again = season.claim_tier(player, 1, "free")
        self.assertTrue(again.get("already_claimed"))
        self.assertEqual(int(again.get("awarded") or 0), 0)
        self.assertEqual(ledger.snapshot(player)["coins"], coins_after)


class SeasonPolicyTests(unittest.TestCase):
    def tearDown(self) -> None:
        season.set_clock(None)

    def test_schema_is_gated_and_documented(self):
        self.assertTrue((ROOT / "docs/migrations/2026-11-28-season-pass.md").is_file())
        doc = (ROOT / "docs/migrations/2026-11-28-season-pass.md").read_text()
        self.assertIn("ALLOW_SCHEMA_MIGRATE", doc)
        self.assertIn("Do not run this branch against the production", doc)
        self.assertIn("Play Billing", doc)
        self.assertTrue(prefs.schema_migrate_allowed())
        os.environ["DATABASE_URL"] = "postgres://example/db"
        os.environ.pop("ALLOW_SCHEMA_MIGRATE", None)
        try:
            self.assertFalse(prefs.schema_migrate_allowed())
        finally:
            os.environ.pop("DATABASE_URL", None)

    def test_rewards_are_fixed_and_shown_up_front(self):
        cat = season.catalogue()
        self.assertEqual(len(cat["free"]), 30)
        self.assertEqual(len(cat["premium"]), 30)
        self.assertEqual(len(cat["daily"]), 3)
        kinds = {t["reward"]["kind"] for t in cat["free"]}
        self.assertEqual(kinds, {"coins", "frame", "emblem"})
        # No loot-box language; amounts are deterministic.
        self.assertEqual(season._reward_for("free", 1), season._reward_for("free", 1))
        self.assertIn("coming soon", cat["premium_note"].lower())

    def test_spa_and_static_routes(self):
        import app as app_module
        self.assertIn("season", app_module.SPA_PAGES)
        self.assertIn("season.js", app_module.ALLOWED_STATIC)
        client = app_module.app.test_client()
        self.assertEqual(client.get("/season").status_code, 200)
        self.assertEqual(client.get("/season.js").status_code, 200)
        self.assertEqual(client.get("/css/season.css").status_code, 200)
        html = (ROOT / "index.html").read_text()
        self.assertIn('href="#/season"', html)
        self.assertIn('id="season-page"', html)
        self.assertIn("grid-template-columns:repeat(4,1fr)", html)
        self.assertNotIn('data-nav="season"', html)
        self.assertIn("Practice or success at social casino gaming does not imply future success at real money gambling.", html)


if __name__ == "__main__":
    unittest.main()
