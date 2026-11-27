#!/usr/bin/env python3
"""v15 live events: server-side schedule, concurrent idempotent prizes,
boosts that never touch RTP or payouts, and no dark patterns.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import unittest
import uuid
from datetime import datetime, timedelta
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
os.environ.pop("SEASON_EPOCH", None)

import clubs
import db as dbmod
import events
import game
import ledger
import live_events
import prefs
import prizes
import season


def fresh_db() -> None:
    season.set_clock(None)
    ledger.DB_PATH = Path(tempfile.mkdtemp()) / "t.db"
    ledger._local.conn = None
    dbmod.reset_local()
    ledger.init_db()


def pid() -> str:
    return "p_" + uuid.uuid4().hex


def house_pool() -> float:
    row = ledger.get_conn().execute("SELECT pool_aud FROM house WHERE id = 1").fetchone()
    return float(row["pool_aud"] if row else 0)


def coins_of(player_id: str) -> int:
    snap = ledger.snapshot(player_id)
    return int(snap.get("coins") or snap.get("credit") or 0)


def at(*parts: int) -> datetime:
    """Build an Australia/Perth datetime. Parts: Y, M, D, [h, m]."""
    year, month, day = parts[0], parts[1], parts[2]
    hour = parts[3] if len(parts) > 3 else 0
    minute = parts[4] if len(parts) > 4 else 0
    return datetime(year, month, day, hour, minute, tzinfo=prizes.PERTH)


# Monday 23 Nov 2026 is the default season epoch, used as a known week.
MON = at(2026, 11, 23)
# Sunday 29 Nov 2026 12:00 — Event Chest is active.
SUN_NOON = at(2026, 11, 29, 12)
# Wednesday 25 Nov 18:30 — Happy Hour + Play Challenge overlap.
WED_HH = at(2026, 11, 25, 18, 30)
# Thursday 26 Nov 13:00 — Season XP Boost.
THU_XP = at(2026, 11, 26, 13)
# Saturday 28 Nov 11:00 — Club Points Boost + weekend tournament.
SAT_CLUB = at(2026, 11, 28, 11)
# Friday 27 Nov 18:30 — Happy Hour + tournament.
FRI_HH = at(2026, 11, 27, 18, 30)


class LiveEventsPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        fresh_db()
        self.addCleanup(season.set_clock, None)

    def test_schema_is_gated_and_documented(self) -> None:
        self.assertTrue(prefs.schema_migrate_allowed())
        os.environ["DATABASE_URL"] = "postgresql://example.invalid/db"
        self.addCleanup(os.environ.pop, "DATABASE_URL", None)
        self.assertFalse(prefs.schema_migrate_allowed())
        os.environ["ALLOW_SCHEMA_MIGRATE"] = "1"
        self.addCleanup(os.environ.pop, "ALLOW_SCHEMA_MIGRATE", None)
        self.assertTrue(prefs.schema_migrate_allowed())
        doc = (ROOT / "docs/migrations/2026-11-28-live-events.md").read_text()
        self.assertIn("ALLOW_SCHEMA_MIGRATE", doc)
        self.assertIn("event_claims", doc)
        self.assertIn("event_progress", doc)
        self.assertIn("crystal-casino-db", doc)
        self.assertIn("never change game math", doc.lower())

    def test_spa_and_static_routes(self) -> None:
        import app as appmod

        client = appmod.app.test_client()
        self.assertEqual(client.get("/events").status_code, 200)
        self.assertEqual(client.get("/events.js").status_code, 200)
        self.assertEqual(client.get("/css/events.css").status_code, 200)
        self.assertIn("events", appmod.SPA_PAGES)
        self.assertIn("events.js", appmod.ALLOWED_STATIC)

    def test_no_dark_patterns_in_player_copy(self) -> None:
        js = (ROOT / "events.js").read_text()
        css = (ROOT / "css/events.css").read_text()
        # Player-facing copy only — module docs may name the banned patterns to forbid them.
        src = js + "\n" + css + "\n" + live_events.LEGAL
        lowered = src.lower()
        for banned in (
            "fake countdown",
            "paid skip",
            "loot box",
            "loot-box",
            "buy coins to extend",
            "hurry before",
            "limited time only",
        ):
            self.assertNotIn(banned, lowered)
        # Real end dates are what the UI is told to print.
        self.assertIn("ends_at_label", js)
        html = (ROOT / "index.html").read_text()
        self.assertIn("Australia/Perth", html.split('id="events-page"')[1].split("</section>")[0])

    def test_boosts_module_never_touches_house_or_payouts(self) -> None:
        src = Path(live_events.__file__).read_text()
        self.assertNotIn("lock_house", src)
        self.assertNotIn("pool_aud", src)
        self.assertNotIn("paytable", src.lower())
        # win_coins may appear only as an unused on_play argument that is discarded.
        self.assertIn("del game, win_coins, meta", src)
        self.assertNotIn("win_coins *", src)
        compact = " ".join(src.lower().split())
        self.assertIn("cannot change slot rtp", compact)
        self.assertIn("never change game payouts", compact)


class ScheduleTests(unittest.TestCase):
    def setUp(self) -> None:
        fresh_db()
        self.addCleanup(season.set_clock, None)

    def test_server_schedule_windows(self) -> None:
        season.set_clock(SUN_NOON)
        types = {e["type"] for e in live_events.active_events()}
        self.assertIn("collect", types)
        self.assertIn("tournament", types)
        self.assertNotIn("happy_hour", types)

        season.set_clock(WED_HH)
        types = {e["type"] for e in live_events.active_events()}
        self.assertIn("happy_hour", types)
        self.assertIn("challenge", types)
        self.assertNotIn("collect", types)

        season.set_clock(THU_XP)
        types = {e["type"] for e in live_events.active_events()}
        self.assertEqual(types, {"xp_boost", "challenge"})

        season.set_clock(SAT_CLUB)
        types = {e["type"] for e in live_events.active_events()}
        self.assertIn("club_boost", types)
        self.assertIn("tournament", types)

        # Just after happy hour ends, it is not active.
        season.set_clock(at(2026, 11, 25, 19, 0))
        types = {e["type"] for e in live_events.active_events()}
        self.assertNotIn("happy_hour", types)

    def test_weekend_tournament_matches_prizes_window(self) -> None:
        season.set_clock(FRI_HH)
        ev = next(e for e in live_events.active_events() if e["type"] == "tournament")
        self.assertTrue(prizes.weekend_active(FRI_HH))
        self.assertEqual(ev["ends_at"], prizes.weekend_ends_at(FRI_HH))
        self.assertIn("Australia/Perth", ev["ends_at_label"])

    def test_upcoming_week_is_on_the_calendar(self) -> None:
        season.set_clock(MON.replace(hour=9))
        ids = [e["id"] for e in live_events.instances()]
        self.assertTrue(any(i.startswith("collect:2026-11-29") for i in ids))
        self.assertTrue(any(i.startswith("collect:2026-12-06") for i in ids))


class PrizeTests(unittest.TestCase):
    def setUp(self) -> None:
        fresh_db()
        self.addCleanup(season.set_clock, None)

    def test_concurrent_collect_claim_does_not_double_pay(self) -> None:
        season.set_clock(SUN_NOON)
        player = pid()
        ledger.ensure_player(player)
        before = coins_of(player)
        pool_before = house_pool()
        ev = next(e for e in live_events.active_events() if e["type"] == "collect")
        barrier = threading.Barrier(8)
        results: list[dict] = []
        errors: list[str] = []

        def worker() -> None:
            barrier.wait()
            try:
                results.append(live_events.claim_prize(player, ev["id"]))
            except live_events.EventError as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        awarded = [r for r in results if int(r.get("awarded") or 0) > 0]
        self.assertEqual(len(awarded), 1)
        self.assertEqual(int(awarded[0]["awarded"]), 2_000)
        already = [r for r in results if r.get("already_claimed")]
        self.assertEqual(len(awarded) + len(already) + len(errors), 8)
        self.assertEqual(coins_of(player), before + 2_000)
        self.assertEqual(house_pool(), pool_before)
        # A later claim is idempotent and pays nothing.
        again = live_events.claim_prize(player, ev["id"])
        self.assertTrue(again["already_claimed"])
        self.assertEqual(int(again["awarded"] or 0), 0)
        self.assertEqual(coins_of(player), before + 2_000)

    def test_claim_after_event_ends_is_rejected(self) -> None:
        season.set_clock(SUN_NOON)
        player = pid()
        ev = next(e for e in live_events.active_events() if e["type"] == "collect")
        season.set_clock(at(2026, 11, 30, 0, 1))
        before = coins_of(player)
        with self.assertRaises(live_events.EventError) as ctx:
            live_events.claim_prize(player, ev["id"])
        self.assertIn("ended", str(ctx.exception).lower())
        self.assertEqual(coins_of(player), before)

    def test_challenge_requires_target_plays_then_pays_once(self) -> None:
        season.set_clock(WED_HH)
        player = pid()
        ev = next(e for e in live_events.active_events() if e["type"] == "challenge")
        for _ in range(29):
            events.on_play(player, "slots", 100, 0)
        with self.assertRaises(live_events.EventError):
            live_events.claim_prize(player, ev["id"])
        events.on_play(player, "slots", 100, 0)
        pool_before = house_pool()
        out = live_events.claim_prize(player, ev["id"])
        self.assertEqual(int(out["awarded"]), 3_000)
        self.assertEqual(house_pool(), pool_before)
        again = live_events.claim_prize(player, ev["id"])
        self.assertTrue(again["already_claimed"])
        self.assertEqual(int(again["awarded"] or 0), 0)

    def test_happy_hour_bonus_is_capped_and_not_from_the_house_pool(self) -> None:
        season.set_clock(WED_HH)
        player = pid()
        ledger.ensure_player(player)
        before = coins_of(player)
        pool_before = house_pool()
        ev = next(e for e in live_events.active_events() if e["type"] == "happy_hour")
        cap = int(ev["cap_plays"])
        per = int(ev["bonus_per_play"])
        for _ in range(cap + 5):
            live_events.record_play(player, 50)
        self.assertEqual(coins_of(player), before + cap * per)
        self.assertEqual(house_pool(), pool_before)
        state = live_events.events_state(player)
        row = next(e for e in state["events"] if e["id"] == ev["id"])
        self.assertEqual(row["plays"], cap + 5)
        self.assertEqual(row["bonus_coins"], cap * per)


class BoostTests(unittest.TestCase):
    def setUp(self) -> None:
        fresh_db()
        self.addCleanup(season.set_clock, None)

    def test_xp_boost_doubles_season_xp_not_payouts(self) -> None:
        player = pid()
        ledger.ensure_player(player)
        # Control: no boost (Monday morning).
        season.set_clock(MON.replace(hour=9))
        self.assertEqual(live_events.xp_multiplier(), 1)
        base = season.play_xp(200, 10_000)
        season.record_play(player, "slots", 200, 10_000)
        sid = season.current_season()["id"]
        row = ledger.get_conn().execute(
            "SELECT xp FROM season_progress WHERE player_id = ? AND season_id = ?",
            (player, sid),
        ).fetchone()
        xp_no_boost = int(row["xp"])
        self.assertEqual(xp_no_boost, base)

        # Boost window: same play, double XP, payout argument ignored.
        season.set_clock(THU_XP)
        self.assertEqual(live_events.xp_multiplier(), 2)
        pool_before = house_pool()
        coins_before = coins_of(player)
        season.record_play(player, "slots", 200, 10_000)
        row = ledger.get_conn().execute(
            "SELECT xp FROM season_progress WHERE player_id = ? AND season_id = ?",
            (player, sid),
        ).fetchone()
        self.assertEqual(int(row["xp"]), xp_no_boost + base * 2)
        self.assertEqual(house_pool(), pool_before)
        self.assertEqual(coins_of(player), coins_before)

    def test_club_boost_doubles_points_not_payouts(self) -> None:
        owner = pid()
        ledger.ensure_player(owner)
        created = clubs.create_club(owner, "Boost Club", "ruby", "open")
        cid = created["club"]["id"]
        # No boost (Thursday).
        season.set_clock(THU_XP)
        self.assertEqual(live_events.club_points_multiplier(), 1)
        clubs._record_play(owner, 100, 50)
        week = clubs.week_id()
        row = ledger.get_conn().execute(
            "SELECT points, win_coins FROM club_week_progress WHERE club_id = ? AND week_id = ? AND player_id = ?",
            (cid, week, owner),
        ).fetchone()
        self.assertEqual(int(row["points"]), 150)
        self.assertEqual(int(row["win_coins"]), 50)

        season.set_clock(SAT_CLUB)
        self.assertEqual(live_events.club_points_multiplier(), 2)
        pool_before = house_pool()
        coins_before = coins_of(owner)
        clubs._record_play(owner, 100, 50)
        row = ledger.get_conn().execute(
            "SELECT points, win_coins FROM club_week_progress WHERE club_id = ? AND week_id = ? AND player_id = ?",
            (cid, week, owner),
        ).fetchone()
        self.assertEqual(int(row["points"]), 150 + 300)
        self.assertEqual(int(row["win_coins"]), 100)
        self.assertEqual(house_pool(), pool_before)
        self.assertEqual(coins_of(owner), coins_before)

    def test_game_payout_path_unchanged_during_a_boost(self) -> None:
        # A settled ledger play still moves the house pool by the stake and
        # payout only — event boosts must not alter that path.
        season.set_clock(THU_XP)
        self.assertEqual(live_events.xp_multiplier(), 2)
        player = pid()
        ledger.ensure_player(player)
        coins_before = coins_of(player)
        pool_before = house_pool()
        events.on_play(player, "slots", 200, 0)
        self.assertEqual(house_pool(), pool_before)
        # Thursday has an XP boost only — no happy-hour coin credit.
        self.assertEqual(coins_of(player), coins_before)


if __name__ == "__main__":
    unittest.main()
