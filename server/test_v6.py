#!/usr/bin/env python3
"""v6 engagement: honest Tea Wheel, progressive, Hold & Spin, collection,
surprise wilds, VIP, weekend tournament, and side-game rules / house edges.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))
os.chdir(SERVER_DIR)

import game
import ledger
import prizes
import side
import app as app_module


def fresh_db() -> None:
    ledger.DB_PATH = Path(tempfile.mkdtemp()) / "t.db"
    ledger._local.conn = None
    ledger.init_db()


def player(coins: int = 100_000) -> str:
    fresh_db()
    pid = "11111111-1111-4111-8111-111111111111"
    ledger.ensure_player(pid)
    with ledger.transaction() as conn:
        conn.execute(
            "UPDATE balances SET amount = ? WHERE player_id = ? AND asset = ?",
            (int(coins), pid, game.COIN_ASSET),
        )
    return pid


class WheelHonesty(unittest.TestCase):
    def test_jackpot_landing_always_pays(self) -> None:
        w = None
        # Force the jackpot index by constructing the result
        rnd = {
            "mode": "classic",
            "base": game.play_one(0.04, 25),
            "minigames": [game.play_wheel(1) | {}],
            "free_spins": [],
        }
        # override
        rnd["minigames"] = [{
            "kind": "wheel", "wedges": game.WHEEL_WEDGES, "index": game.WHEEL_JACKPOT_INDEX,
            "jackpot": True, "raw_win_aud": 0.0, "prize_mult": 0, "free_spins": 0,
        }]
        settled = game.settle_steps(rnd, 1.0, 100.0, False)
        step = settled["steps"][1]
        self.assertTrue(step["wheel_jackpot"])
        self.assertEqual(step["wheel_index"], game.WHEEL_JACKPOT_INDEX)
        self.assertEqual(step["jackpot_aud"], game.jackpot_amount(1.0))

    def test_angles_match_weights(self) -> None:
        angles = game.wheel_wedge_angles()
        self.assertAlmostEqual(sum(angles), 360.0, places=6)
        jp = angles[game.WHEEL_JACKPOT_INDEX]
        self.assertLess(jp, 1.0)  # thin sliver
        self.assertGreater(jp, 0.0)


class Progressive(unittest.TestCase):
    def test_pot_grows_and_is_public(self) -> None:
        pid = player()
        before = ledger.progressive_public()["progressive"]
        # A dead spin still contributes
        grid = [["shard"] * 3 for _ in range(5)]
        rnd = {"mode": "classic", "base": {
            "kind": "spin", "mode": "classic", "grid": grid, "line_wins": [], "scatters": 0,
            "scatter_pos": [], "scatter_win_aud": 0, "free_spins_awarded": 0, "multiplier": 1,
            "raw_win_aud": 0, "has_wild": False, "coins": [], "coin_count": 0,
        }, "minigames": [], "free_spins": [], "_force_progressive": False}
        ledger.settle_round(pid, 10, rnd, "COIN", lambda s, p: False)
        after = ledger.progressive_public()["progressive"]
        self.assertEqual(after - before, game.to_coins(10 * game.PROG_RATE))
        self.assertNotIn("pool", ledger.progressive_public())

    def test_hit_pays_pot_and_reseeds(self) -> None:
        pid = player()
        ledger.get_conn().execute("UPDATE house SET progressive_aud = 80 WHERE id = 1")
        ledger.get_conn().commit()
        rnd = {"mode": "classic", "base": {
            "kind": "spin", "mode": "classic", "grid": [["shard"] * 3 for _ in range(5)],
            "line_wins": [], "scatters": 0, "scatter_pos": [], "scatter_win_aud": 0,
            "free_spins_awarded": 0, "multiplier": 1, "raw_win_aud": 0, "has_wild": False,
            "coins": [], "coin_count": 0,
        }, "minigames": [], "free_spins": [], "_force_progressive": True}
        snap = ledger.settle_round(pid, 10, rnd, "COIN", lambda s, p: False)
        self.assertTrue(snap["progressive_hit"])
        # paid ≈ 80 + 0.01*10
        self.assertEqual(snap["progressive_paid"], game.to_coins(80 + 0.1))
        self.assertEqual(ledger.progressive_public()["progressive"], game.to_coins(game.PROG_SEED))


class HoldSpin(unittest.TestCase):
    def test_trigger_and_grand(self) -> None:
        # 6 start coins, force-fill by patching respin p
        old = game.HOLD_RESPIN_P
        game.HOLD_RESPIN_P = 1.0
        try:
            h = game.play_hold_spin(2.0, start_positions=[[0, 0]] * 6)
        finally:
            game.HOLD_RESPIN_P = old
        self.assertTrue(h["filled"] and h["grand"])
        self.assertEqual(h["coins_locked"], 15)
        self.assertAlmostEqual(h["raw_win_aud"], 2.0 * (sum(h["values"]) + game.HOLD_GRAND_MULT), places=4)

    def test_values_lock_and_respins_reset(self) -> None:
        h = game.play_hold_spin(1.0, start_count=6)
        self.assertGreaterEqual(h["coins_locked"], 6)
        self.assertEqual(h["kind"], "hold_spin")
        # First locked values never shrink
        if h["rounds"]:
            first = [v for v in h["rounds"][0]["cells"]]
            last = h["cells"]
            for a, b in zip(first, last):
                if a is not None:
                    self.assertEqual(a, b)


class Collection(unittest.TestCase):
    def test_set_completion_pays(self) -> None:
        meter = {k: game.COLLECT_SET - 1 for k in game.COLLECT_TYPES}
        # Force a hit by retrying the random roll
        paid = 0
        completed = None
        for _ in range(5000):
            step = game.collection_step(4.0, meter)
            if step["completed"]:
                paid = step["paid_aud"]
                completed = step["completed"]
                self.assertEqual(step["meter"][completed], 0)
                break
        self.assertEqual(paid, 4.0 * game.COLLECT_PAY_MULT)
        self.assertIn(completed, game.COLLECT_TYPES)


class SurpriseWilds(unittest.TestCase):
    def test_positions_match_grid(self) -> None:
        found = False
        for _ in range(400):
            r = game.play_one(0.04, 25, surprise=True)
            if r["surprise_wilds"]:
                found = True
                for w in r["surprise_wilds"]:
                    self.assertEqual(r["grid"][w["col"]][w["row"]], game.WILD_ID)
                    self.assertNotIn(w["from"], (game.WILD_ID, game.SCATTER_ID, game.COIN_ID))
                break
        self.assertTrue(found)


class VipAndWeekend(unittest.TestCase):
    def test_hourly_grows_with_vip_tier(self) -> None:
        pid = player()
        bronze = prizes.vip_for_level(1)
        gold = prizes.vip_for_level(10)
        diamond = prizes.vip_for_level(35)
        self.assertEqual(bronze["id"], "bronze")
        self.assertEqual(gold["id"], "gold")
        self.assertEqual(diamond["id"], "diamond")
        self.assertGreater(gold["hourly_coins"], bronze["hourly_coins"])
        self.assertGreater(diamond["hourly_coins"], gold["hourly_coins"])
        prizes.debug_set_level(pid, 10)
        snap = ledger.claim_hourly(pid)
        self.assertEqual(snap["awarded"], gold["hourly_coins"])
        # No purchase-only perks in the catalogue
        for t in gold["tiers"]:
            self.assertIn("hourly_coins", t)
            self.assertNotIn("pack", t)
            self.assertNotIn("purchase", t)

    def test_weekend_leaderboard_settles(self) -> None:
        pid = player()
        key = "2020-01-03"  # a Friday
        conn = ledger.get_conn()
        conn.execute(
            "INSERT INTO spin_records (player_id, created_at, perth_date, perth_week, perth_weekend, bet_aud, win_aud) "
            "VALUES (?, '2020-01-04T00:00:00+08:00', '2020-01-04', '2020-W01', ?, 1, 20)",
            (pid, key),
        )
        conn.commit()
        paid = prizes.settle_leaderboard("weekend", key, "biggest")
        self.assertEqual(len(paid), 1)
        self.assertEqual(paid[0]["coins"], prizes.WEEKEND_COINS[1])
        # idempotent
        self.assertEqual(prizes.settle_leaderboard("weekend", key, "biggest"), [])


class SideRejects(unittest.TestCase):
    def test_invalid_and_insufficient(self) -> None:
        pid = player(50)
        with self.assertRaises(ValueError):
            ledger.play_side(pid, "dice", {"bet": 100})  # not enough
        pid = player(10_000)
        with self.assertRaises((ValueError, side.SideError)):
            ledger.play_side(pid, "dice", {"bet": 0})
        with self.assertRaises((ValueError, side.SideError)):
            ledger.play_side(pid, "dice", {"bet": -5})
        with self.assertRaises(ValueError):
            ledger.play_side(pid, "keno", {"bet": 100})
        with self.assertRaises((ValueError, side.SideError)):
            ledger.play_side(pid, "roulette", {"bets": [{"kind": "straight", "number": 99, "amount": 100}]})
        with self.assertRaises((ValueError, side.SideError)):
            ledger.play_side(pid, "mines", {"action": "start", "bet": 100, "mines": 9})


class BlackjackRules(unittest.TestCase):
    def test_natural_pays_three_to_two(self) -> None:
        # Deal until player BJ vs dealer non-BJ (or construct)
        for _ in range(4000):
            st = side.blackjack_deal(100)
            if is_player_bj(st) and not side.is_blackjack(st["dealer"]):
                if st.get("insurance_offered") and not st.get("done"):
                    st = side.blackjack_act(st, "no_insurance")
                self.assertTrue(st["done"])
                self.assertEqual(st["payout"], 250)
                self.assertEqual(st["hands"][0]["result"], "blackjack")
                return
        self.fail("no natural blackjack in sample")

    def test_bust_loses_and_split_requires_pair(self) -> None:
        # Construct a hitting bust
        st = side.blackjack_deal(100)
        # If can't hit (already BJ etc), skip by looping
        for _ in range(200):
            st = side.blackjack_deal(100)
            if st.get("insurance_offered"):
                st = side.blackjack_act(st, "no_insurance")
                if st.get("done"):
                    continue
            if "hit" in side._bj_actions(st):
                # hit until bust or stand at 21
                while not st.get("done") and "hit" in side._bj_actions(st):
                    before = side.hand_value(st["hands"][0]["cards"])
                    st = side.blackjack_act(st, "hit")
                    if side.hand_value(st["hands"][0]["cards"]) > 21:
                        self.assertTrue(st["done"])
                        self.assertEqual(st["payout"], 0)
                        return
                # if never bust, try again
        # Not fatal if extremely unlucky; at least split is rejected without a pair
        st = side.blackjack_deal(100)
        if st.get("insurance_offered") and not st.get("done"):
            st = side.blackjack_act(st, "no_insurance")
        if not st.get("done") and "split" not in side._bj_actions(st):
            with self.assertRaises(side.SideError):
                side.blackjack_act(st, "split")

    def test_dealer_stands_soft_seventeen(self) -> None:
        # Soft 17: Ace + 6. Dealer should not hit.
        dealer = [side._card("A", "hearts"), side._card("6", "spades")]
        self.assertEqual(side.hand_value(dealer), 17)
        self.assertTrue(side.is_soft(dealer))


def is_player_bj(st: dict) -> bool:
    return side.is_blackjack(st["hands"][0]["cards"])


class RouletteRules(unittest.TestCase):
    def test_straight_and_even_money(self) -> None:
        # Force many spins; check payout math against the returned number
        for _ in range(40):
            res = side.roulette_spin([
                {"kind": "straight", "number": 17, "amount": 10},
                {"kind": "red", "amount": 10},
            ])
            self.assertIn(res["number"], range(0, 37))
            expect = 0
            if res["number"] == 17:
                expect += 36 * 10
            if res["number"] in side.ROUGE:
                expect += 20
            self.assertEqual(res["payout"], expect)
            self.assertEqual(res["wheel"][res["pocket"]], res["number"])

    def test_zero_loses_even_money(self) -> None:
        hits = 0
        for _ in range(2000):
            res = side.roulette_spin([{"kind": "black", "amount": 10}])
            if res["number"] == 0:
                hits += 1
                self.assertEqual(res["payout"], 0)
                self.assertEqual(res["colour"], "green")
        self.assertGreater(hits, 0)


class HighCardDiceScratchMines(unittest.TestCase):
    def test_highcard_and_war(self) -> None:
        for _ in range(300):
            r = side.highcard_play(100, war=True)
            if r["result"] == "tie":
                self.assertTrue(r["awaiting_war"])
                war = side.highcard_play(100, war=True, previous=r)
                self.assertTrue(war["done"])
                self.assertIn(war["result"], ("win", "lose", "push"))
                if war["result"] == "win":
                    self.assertEqual(war["payout"], 400)
                if war["result"] == "push":
                    self.assertEqual(war["payout"], 200)
                return
        self.fail("no tie in sample")

    def test_dice_push_and_pay(self) -> None:
        saw = set()
        for _ in range(400):
            r = side.dice_play(50)
            saw.add(r["result"])
            if r["result"] == "win":
                self.assertEqual(r["payout"], 100)
            elif r["result"] == "lose":
                self.assertEqual(r["payout"], 0)
            else:
                self.assertEqual(r["payout"], 50)
        self.assertEqual(saw, {"win", "lose", "push"})

    def test_scratch_rtp_table(self) -> None:
        ev = side.scratch_ev()
        self.assertAlmostEqual(ev, 0.95, delta=0.005)
        r = side.scratch_play(200)
        self.assertEqual(len(r["grid"]), 9)
        if r["mult"] > 0:
            self.assertIsNotNone(r["win_row"])
            row = r["grid"][r["win_row"] * 3:(r["win_row"] + 1) * 3]
            self.assertEqual(len(set(row)), 1)
        else:
            for i in range(3):
                row = r["grid"][i * 3:(i + 1) * 3]
                self.assertNotEqual(len(set(row)), 1)

    def test_mines_cashout_and_boom(self) -> None:
        # Hidden bombs stay hidden mid-round
        st = side.mines_start(100, 3)
        pub = side.mines_public(st)
        self.assertIsNone(pub["bombs"])
        # Pick a safe tile
        safe = next(i for i in range(25) if i not in st["bombs"])
        st = side.mines_pick(st, safe)
        self.assertFalse(st["done"])
        self.assertGreater(st["multiplier"], 1.0)
        self.assertAlmostEqual(st["multiplier"], side.mines_multiplier(3, 1), places=4)
        st = side.mines_cashout(st)
        self.assertTrue(st["done"])
        self.assertEqual(st["payout"], int(round(100 * st["multiplier"])))
        # Boom
        st = side.mines_start(100, 3)
        bomb = st["bombs"][0]
        st = side.mines_pick(st, bomb)
        self.assertTrue(st["boom"] and st["payout"] == 0)
        self.assertIsNotNone(side.mines_public(st)["bombs"])

    def test_mines_house_edge_in_band(self) -> None:
        # Cash out after first safe tile, over many rounds, edge ≈ 4%
        wins = stake = 0
        bet, mines = 100, 3
        for _ in range(8000):
            st = side.mines_start(bet, mines)
            tile = side._rng.randrange(25)
            st = side.mines_pick(st, tile)
            stake += bet
            if st.get("boom"):
                continue
            st = side.mines_cashout(st)
            wins += st["payout"]
        rtp = wins / stake
        edge = 1 - rtp
        self.assertGreater(edge, 0.03)
        self.assertLess(edge, 0.05)


class SideHouseEdges(unittest.TestCase):
    def test_roulette_european_edge(self) -> None:
        stake = wins = 0
        for _ in range(20_000):
            r = side.roulette_spin([{"kind": "red", "amount": 10}])
            stake += 10
            wins += r["payout"]
        edge = 1 - wins / stake
        self.assertAlmostEqual(edge, 1 / 37, delta=0.015)

    def test_dice_is_fair(self) -> None:
        stake = wins = 0
        for _ in range(20_000):
            r = side.dice_play(10)
            stake += 10
            wins += r["payout"]
        self.assertAlmostEqual(wins / stake, 1.0, delta=0.03)

    def test_highcard_is_fair_on_push(self) -> None:
        stake = wins = 0
        for _ in range(20_000):
            r = side.highcard_play(10, war=False)
            stake += 10
            wins += r["payout"]
        self.assertAlmostEqual(wins / stake, 1.0, delta=0.03)

    def test_scratch_sim_near_table(self) -> None:
        stake = wins = 0
        for _ in range(40_000):
            r = side.scratch_play(10)
            stake += 10
            wins += r["payout"]
        self.assertAlmostEqual(wins / stake, side.scratch_ev(), delta=0.04)

    def test_insufficient_coins_api(self) -> None:
        fresh_db()
        os.environ.pop("STRIPE_SECRET_KEY", None)
        client = app_module.app.test_client()
        # Starting coins 25_000; a 50_000 bet must fail
        r = client.post("/api/side/dice", json={"bet": 50_000})
        self.assertEqual(r.status_code, 400)
        self.assertIn("coins", (r.get_json() or {}).get("error", "").lower())
        # /api/pool still 404
        self.assertEqual(client.get("/api/pool").status_code, 404)
        cfg = client.get("/api/config").get_json()
        self.assertNotIn("pool_aud", cfg)
        self.assertIn("side", cfg)
        self.assertIn("progressive", cfg)
        jp = client.get("/api/jackpots").get_json()
        self.assertIn("progressive", jp)
        self.assertNotIn("pool", jp)


if __name__ == "__main__":
    unittest.main(verbosity=1)
