#!/usr/bin/env python3
"""v10: baccarat rules and payouts, keno exact EV, themed slots share the Crystal engine."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
import uuid
from fractions import Fraction
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))
os.chdir(SERVER_DIR)

os.environ.pop("DATABASE_URL", None)
os.environ.pop("GOOGLE_CLIENT_ID", None)

import baccarat
import events
import game
import keno
import ledger
import prizes
import side
import themes
import db as dbmod
import simulate_rtp


def fresh_db() -> None:
    ledger.DB_PATH = Path(tempfile.mkdtemp()) / "t.db"
    ledger._local.conn = None
    dbmod.reset_local()
    ledger.init_db()


def pid() -> str:
    return str(uuid.uuid4())


def card(rank: str, suit: str = "spades") -> dict:
    return {
        "rank": rank,
        "suit": suit,
        "colour": "red" if suit in ("hearts", "diamonds") else "black",
        "value": baccarat._card_value(rank),
    }


def scripted_shoe(*ranks_and_suits: tuple[str, str]) -> list[dict]:
    cards = [card(r, s) for r, s in ranks_and_suits]
    # Keep the scripted prefix; pad so deal() does not reshuffle (< 52 left).
    pad = baccarat._fresh_shoe()
    return cards + pad


class BaccaratRuleTests(unittest.TestCase):
    def test_card_values_and_modulo(self):
        self.assertEqual(baccarat.point([card("A"), card("K")]), 1)
        self.assertEqual(baccarat.point([card("10"), card("J")]), 0)
        self.assertEqual(baccarat.point([card("7"), card("8")]), 5)
        self.assertEqual(baccarat.point([card("9"), card("9")]), 8)
        self.assertTrue(baccarat.is_natural([card("8"), card("K")]))
        self.assertTrue(baccarat.is_natural([card("4"), card("5")]))
        self.assertFalse(baccarat.is_natural([card("7"), card("K")]))
        self.assertTrue(baccarat.is_pair([card("9", "hearts"), card("9", "clubs")]))
        self.assertFalse(baccarat.is_pair([card("9"), card("8")]))

    def test_player_draw_chart(self):
        for total in range(0, 6):
            self.assertTrue(baccarat.player_draws_third(total), total)
        for total in (6, 7):
            self.assertFalse(baccarat.player_draws_third(total), total)

    def test_banker_chart_when_player_stands(self):
        for total in range(0, 6):
            self.assertTrue(baccarat.banker_draws_third(total, None), total)
        for total in (6, 7, 8, 9):
            self.assertFalse(baccarat.banker_draws_third(total, None), total)

    def test_banker_third_card_tableau(self):
        for p in range(10):
            self.assertTrue(baccarat.banker_draws_third(0, p))
            self.assertTrue(baccarat.banker_draws_third(1, p))
            self.assertTrue(baccarat.banker_draws_third(2, p))
            self.assertFalse(baccarat.banker_draws_third(7, p))
        for p in range(10):
            self.assertEqual(baccarat.banker_draws_third(3, p), p != 8, p)
            self.assertEqual(baccarat.banker_draws_third(4, p), p in (2, 3, 4, 5, 6, 7), p)
            self.assertEqual(baccarat.banker_draws_third(5, p), p in (4, 5, 6, 7), p)
            self.assertEqual(baccarat.banker_draws_third(6, p), p in (6, 7), p)

    def _deal(self, bets, *ranks):
        shoe = scripted_shoe(*((r, "spades" if i % 2 == 0 else "hearts") for i, r in enumerate(ranks)))
        return baccarat.deal(bets, shoe)

    def test_natural_player_wins_no_third(self):
        # P A + 8 = 9, B 2 + 3 = 5
        r = self._deal({"player": 1000}, "A", "2", "8", "3")
        self.assertTrue(r["natural"])
        self.assertFalse(r["player_drew"])
        self.assertFalse(r["banker_drew"])
        self.assertEqual(r["winner"], "player")
        self.assertEqual(r["player_point"], 9)
        self.assertEqual(r["payout"], 2000)

    def test_banker_win_takes_five_percent_commission(self):
        # P 2+3=5, B 4+4=8 natural
        r = self._deal({"banker": 1000}, "2", "4", "3", "4")
        self.assertEqual(r["winner"], "banker")
        self.assertTrue(r["natural"])
        self.assertEqual(r["payout"], 1000 + 950)

    def test_commission_exact_for_every_listed_stake(self):
        for stake in side.BETS:
            profit = stake * 95 // 100
            self.assertEqual(profit * 100, stake * 95, f"stake {stake} not divisible")
            r = self._deal({"banker": stake}, "2", "4", "3", "4")
            self.assertEqual(r["payout"], stake + profit)

    def test_tie_pushes_main_bets_and_pays_eight_to_one(self):
        # P 9+K=9, B 4+5=9 naturals tie
        r = self._deal({"player": 1000, "banker": 1000, "tie": 100}, "9", "4", "K", "5")
        self.assertEqual(r["winner"], "tie")
        by = {row["spot"]: row for row in r["breakdown"]}
        self.assertEqual(by["player"]["outcome"], "push")
        self.assertEqual(by["player"]["payout"], 1000)
        self.assertEqual(by["banker"]["outcome"], "push")
        self.assertEqual(by["banker"]["payout"], 1000)
        self.assertEqual(by["tie"]["payout"], 100 + 800)
        self.assertEqual(r["payout"], 1000 + 1000 + 900)

    def test_pairs_pay_eleven_to_one_independently(self):
        # Player pair of 2s, banker 9 natural — main player bet loses, pair wins
        r = self._deal({"player": 100, "player_pair": 100}, "2", "9", "2", "K")
        self.assertTrue(r["player_pair"])
        self.assertEqual(r["winner"], "banker")
        by = {row["spot"]: row for row in r["breakdown"]}
        self.assertEqual(by["player"]["payout"], 0)
        self.assertEqual(by["player_pair"]["payout"], 100 + 1100)
        self.assertEqual(r["payout"], 1200)

    def test_player_draws_on_five_banker_stands_on_seven(self):
        # P 2+3=5 draws 9 → 4; B 3+4=7 stands
        r = self._deal({"player": 1000}, "2", "3", "3", "4", "9")
        self.assertFalse(r["natural"])
        self.assertTrue(r["player_drew"])
        self.assertFalse(r["banker_drew"])
        self.assertEqual(r["player_point"], 4)
        self.assertEqual(r["banker_point"], 7)
        self.assertEqual(r["winner"], "banker")

    def test_why_explains_the_result(self):
        r = self._deal({"player": 1000}, "A", "2", "8", "3")
        self.assertIn("natural", r["why"].lower())
        self.assertIn("Player wins", r["why"])

    def test_unknown_spot_ignored_and_empty_rejected(self):
        with self.assertRaises(side.SideError):
            baccarat.deal({})
        with self.assertRaises(side.SideError):
            baccarat.deal({"player": 7})


class KenoEvTests(unittest.TestCase):
    def test_paytable_rtp_in_band_for_every_pick_size(self):
        for k in range(keno.PICK_MIN, keno.PICK_MAX + 1):
            rtp = keno.exact_rtp(k)
            self.assertIsInstance(rtp, Fraction)
            self.assertGreaterEqual(float(rtp), 0.92, f"k={k} RTP {float(rtp)}")
            self.assertLessEqual(float(rtp), 0.95, f"k={k} RTP {float(rtp)}")

    def test_known_exact_rtps(self):
        self.assertEqual(keno.exact_rtp(1), Fraction(15, 16))
        self.assertAlmostEqual(float(keno.exact_rtp(1)), 0.9375, places=6)
        self.assertAlmostEqual(float(keno.exact_rtp(10)), 0.940034, places=5)

    def test_pay_coins_uses_published_fractions(self):
        # 1-spot catch-all is 15/4 × stake
        self.assertEqual(keno.pay_coins(1000, 1, 1), 1000 * 15 // 4)
        self.assertEqual(keno.pay_coins(1000, 1, 0), 0)
        self.assertEqual(keno.pay_coins(200, 10, 0), 0)

    def test_play_quick_pick_and_bounds(self):
        r = keno.play(1000, picks=[], count=5)
        self.assertTrue(r["quick"])
        self.assertEqual(len(r["picks"]), 5)
        self.assertEqual(len(r["drawn"]), 20)
        self.assertEqual(r["caught"], len(set(r["picks"]) & set(r["drawn"])))
        self.assertEqual(r["payout"], keno.pay_coins(1000, 5, r["caught"]))
        with self.assertRaises(side.SideError):
            keno.play(1000, picks=[], count=0)
        with self.assertRaises(side.SideError):
            keno.play(7, picks=[1], count=1)


class ThemeRtpTests(unittest.TestCase):
    def test_themes_reuse_crystal_engine(self):
        ids = {t["id"] for t in themes.SLOT_THEMES}
        self.assertGreaterEqual(len(ids), 4)
        self.assertTrue({"crystal", "dragon", "pharaoh", "neon"} <= ids)
        for t in themes.SLOT_THEMES:
            self.assertEqual(t.get("megaways_rtp", themes.MEGAWAYS_RTP), themes.MEGAWAYS_RTP)
            self.assertEqual(themes.get(t["id"])["id"], t["id"])

    def test_official_ev_within_half_point_of_95(self):
        for rtp in (themes.MEGAWAYS_RTP, themes.CLASSIC_RTP, 0.95113, 0.95071):
            self.assertLessEqual(abs(rtp - simulate_rtp.TARGET_RTP), simulate_rtp.TOLERANCE)
        # Shared symbol table: themes must not retune pays or ids.
        ids = [s["id"] for s in game.SYMBOLS]
        self.assertEqual(ids, [
            "quartz", "citrine", "topaz", "amethyst",
            "emerald", "sapphire", "ruby", "greentea",
            "wild", "scatter", "shard", "coin",
        ])
        # Every themed name override refers to a real symbol.
        real = set(ids)
        for t in themes.SLOT_THEMES:
            for sid in t["symbols"]:
                self.assertIn(sid, real)

    def test_catalogue_exposes_themes_and_new_games(self):
        cat = side.catalogue()
        ids = {g["id"] for g in cat["games"]}
        self.assertIn("baccarat", ids)
        self.assertIn("keno", ids)
        self.assertIn("baccarat", side.GAMES)
        self.assertIn("keno", side.GAMES)
        self.assertIn("payouts", cat["baccarat"])
        self.assertIn("pays", cat["keno"])


class SideWiringTests(unittest.TestCase):
    def test_keno_play_side_awards_xp_and_events(self):
        fresh_db()
        player = pid()
        ledger.ensure_player(player)
        seen: list[tuple] = []

        def hook(**kwargs):
            seen.append((kwargs["game"], kwargs["bet_coins"], kwargs["win_coins"]))

        events.register(hook)
        try:
            snap = ledger.snapshot(player)
            before = snap["coins"]
            xp_before = (snap.get("profile") or {}).get("xp") or prizes.attach(player, snap)["profile"]["xp"]
            # Credit enough just in case; starting coins should cover 1000.
            pub = ledger.play_side(player, "keno", {"bet": 1000, "count": 4})
            self.assertTrue(pub.get("done"))
            self.assertEqual(pub["game"], "keno")
            self.assertEqual(pub["bet"], 1000)
            self.assertEqual(pub["coins"], before - 1000 + pub["payout"])
            self.assertTrue(any(g == "keno" and b == 1000 for g, b, w in seen))
            after = prizes.attach(player, ledger.snapshot(player))
            self.assertGreater(after["profile"]["xp"], 0)
        finally:
            events._handlers.remove(hook)

    def test_baccarat_play_side_settles_commission(self):
        fresh_db()
        player = pid()
        ledger.ensure_player(player)
        before = ledger.snapshot(player)["coins"]
        pub = ledger.play_side(player, "baccarat", {"bets": {"banker": 1000}})
        self.assertTrue(pub.get("done"))
        self.assertEqual(pub["game"], "baccarat")
        self.assertIn(pub["winner"], ("player", "banker", "tie"))
        self.assertIn("why", pub)
        self.assertIsInstance(pub.get("road"), list)
        self.assertNotIn("_shoe", pub)
        self.assertEqual(pub["coins"], before - 1000 + pub["payout"])
        if pub["winner"] == "banker":
            self.assertEqual(pub["payout"], 1950)
        if pub["winner"] == "tie":
            self.assertEqual(pub["payout"], 1000)

    def test_unknown_game_still_rejected(self):
        fresh_db()
        with self.assertRaises(ValueError):
            ledger.play_side(pid(), "poker-bots", {"bet": 1000})


class EventsHookTests(unittest.TestCase):
    def test_register_and_dispatch(self):
        seen = []

        def hook(**kwargs):
            seen.append(kwargs)

        events.register(hook)
        try:
            events.on_play("p1", "slots", 500, 0, meta={"kind": "slots"})
            self.assertEqual(seen[0]["game"], "slots")
            self.assertEqual(seen[0]["bet_coins"], 500)
        finally:
            events._handlers.remove(hook)


if __name__ == "__main__":
    unittest.main()
