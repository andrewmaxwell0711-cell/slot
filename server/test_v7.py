#!/usr/bin/env python3
"""v7 casino games: Jacks or Better, Three Card Poker, Casino War,
paytables, session validation, and house-edge simulations.
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
import side


def fresh_db() -> None:
    ledger.DB_PATH = Path(tempfile.mkdtemp()) / "t.db"
    ledger._local.conn = None
    ledger.init_db()


def player(coins: int = 1_000_000) -> str:
    fresh_db()
    pid = "11111111-1111-4111-8111-111111111111"
    ledger.ensure_player(pid)
    with ledger.transaction() as conn:
        conn.execute(
            "UPDATE balances SET amount = ? WHERE player_id = ? AND asset = ?",
            (int(coins), pid, game.COIN_ASSET),
        )
    return pid


def C(rank: str, suit: str = "spades") -> dict:
    return side._card(rank, suit)


def cards(*spec: str) -> list[dict]:
    """'AH', 'TD', 'JS' — rank then suit letter."""
    suit = {"H": "hearts", "D": "diamonds", "C": "clubs", "S": "spades"}
    out = []
    for s in spec:
        s = s.upper()
        if s.startswith("10"):
            r, u = "10", s[2]
        else:
            r, u = s[0] if s[0] != "T" else "10", s[-1]
            if s[0] == "T":
                r = "10"
        out.append(C(r, suit[u]))
    return out


class VideoPokerRanking(unittest.TestCase):
    def test_royal_flush(self) -> None:
        h = cards("AH", "KH", "QH", "JH", "TH")
        self.assertEqual(side.job_hand_name(h), "royal_flush")
        self.assertEqual(side.job_payout(h, 100)[2], 800)
        self.assertEqual(side.job_payout(h, 100)[0], 80_000)

    def test_straight_flush_and_wheel(self) -> None:
        self.assertEqual(side.job_hand_name(cards("9S", "8S", "7S", "6S", "5S")), "straight_flush")
        self.assertEqual(side.job_hand_name(cards("AS", "2S", "3S", "4S", "5S")), "straight_flush")
        self.assertEqual(side.job_payout(cards("9S", "8S", "7S", "6S", "5S"), 10)[2], 50)

    def test_four_of_a_kind_full_house(self) -> None:
        self.assertEqual(side.job_hand_name(cards("AH", "AD", "AS", "AC", "2H")), "four_of_a_kind")
        self.assertEqual(side.job_payout(cards("AH", "AD", "AS", "AC", "2H"), 10)[2], 25)
        self.assertEqual(side.job_hand_name(cards("AH", "AD", "AS", "9C", "9H")), "full_house")
        self.assertEqual(side.job_payout(cards("AH", "AD", "AS", "9C", "9H"), 10)[2], 9)

    def test_flush_and_straight(self) -> None:
        self.assertEqual(side.job_hand_name(cards("AH", "9H", "6H", "3H", "2H")), "flush")
        self.assertEqual(side.job_payout(cards("AH", "9H", "6H", "3H", "2H"), 10)[2], 6)
        self.assertEqual(side.job_hand_name(cards("AH", "KD", "QC", "JS", "TH")), "straight")
        self.assertEqual(side.job_hand_name(cards("AH", "2D", "3C", "4S", "5H")), "straight")
        self.assertEqual(side.job_payout(cards("AH", "KD", "QC", "JS", "TH"), 10)[2], 4)

    def test_trips_two_pair_jacks(self) -> None:
        self.assertEqual(side.job_hand_name(cards("9H", "9D", "9S", "2C", "5H")), "three_of_a_kind")
        self.assertEqual(side.job_payout(cards("9H", "9D", "9S", "2C", "5H"), 10)[2], 3)
        self.assertEqual(side.job_hand_name(cards("9H", "9D", "5S", "5C", "2H")), "two_pair")
        self.assertEqual(side.job_payout(cards("9H", "9D", "5S", "5C", "2H"), 10)[2], 2)
        self.assertEqual(side.job_hand_name(cards("JH", "JD", "3S", "5C", "9H")), "jacks_or_better")
        self.assertEqual(side.job_payout(cards("JH", "JD", "3S", "5C", "9H"), 10)[2], 1)
        self.assertEqual(side.job_payout(cards("JH", "JD", "3S", "5C", "9H"), 10)[0], 10)  # 1× total (push)

    def test_low_pair_and_nothing_pay_zero(self) -> None:
        self.assertEqual(side.job_hand_name(cards("TH", "TD", "3S", "5C", "9H")), "nothing")
        self.assertEqual(side.job_payout(cards("TH", "TD", "3S", "5C", "9H"), 10)[0], 0)
        self.assertEqual(side.job_hand_name(cards("AH", "KD", "7C", "4S", "2H")), "nothing")
        self.assertEqual(side.job_payout(cards("AH", "KD", "7C", "4S", "2H"), 10)[0], 0)

    def test_ace_high_is_not_a_straight(self) -> None:
        self.assertEqual(side.job_hand_name(cards("AH", "KD", "QC", "JS", "9H")), "nothing")


class VideoPokerSession(unittest.TestCase):
    def test_deal_then_draw_credits_paytable(self) -> None:
        pid = player()
        before = 1_000_000
        res = ledger.play_side(pid, "videopoker", {"action": "deal", "bet": 1000})
        self.assertFalse(res["done"])
        self.assertEqual(len(res["cards"]), 5)
        self.assertNotIn("deck", res)
        mid = ledger.snapshot(pid)["coins"]
        self.assertEqual(mid, before - 1000)
        # Hold none so the draw is random; just ensure it settles.
        res2 = ledger.play_side(pid, "videopoker", {"action": "draw", "holds": []})
        self.assertTrue(res2["done"])
        self.assertIn(res2["hand"], list(side.JOB_PAYS) + ["nothing"])
        after = ledger.snapshot(pid)["coins"]
        self.assertEqual(after, mid + res2["payout"])

    def test_rejects_invalid_and_insufficient(self) -> None:
        pid = player(500)
        with self.assertRaises(ValueError):
            ledger.play_side(pid, "videopoker", {"action": "deal", "bet": 0})
        with self.assertRaises(ValueError):
            ledger.play_side(pid, "videopoker", {"action": "deal", "bet": -10})
        with self.assertRaises(ValueError):
            ledger.play_side(pid, "videopoker", {"action": "deal", "bet": 1000})
        with self.assertRaises(ValueError):
            ledger.play_side(pid, "videopoker", {"action": "draw", "holds": []})

    def test_cannot_start_second_hand(self) -> None:
        pid = player()
        ledger.play_side(pid, "videopoker", {"action": "deal", "bet": 100})
        with self.assertRaises(ValueError):
            ledger.play_side(pid, "dice", {"bet": 100})

    def test_hold_indices_respected(self) -> None:
        # Force a known deal by calling the engine, then draw through the helper.
        state = side.videopoker_deal(10)
        # Hold all five: final hand equals dealt hand.
        holds = [True, True, True, True, True]
        out = side.videopoker_draw(state, holds)
        self.assertEqual([c["rank"] + c["suit"] for c in out["cards"]],
                         [c["rank"] + c["suit"] for c in state["cards"]])
        self.assertEqual(out["payout"], side.job_payout(state["cards"], 10)[0])


class VideoPokerHouseEdge(unittest.TestCase):
    def test_job_strategy_edge_near_half_percent(self) -> None:
        """9/6 JoB with the built-in hold strategy should sit near 0.5% HE."""
        stake = 1
        wins = 0
        n = 40_000
        for _ in range(n):
            st = side.videopoker_deal(stake)
            holds = side.job_hold_strategy(st["cards"])
            out = side.videopoker_draw(st, holds)
            wins += out["payout"]
        rtp = wins / (n * stake)
        edge = 1 - rtp
        # 9/6 full-pay is ~0.46% with optimal play. The built-in hold strategy is
        # a close heuristic (not a full solver); 40k hands are also a little noisy.
        self.assertGreater(rtp, 0.94)
        self.assertLess(edge, 0.06)
        self.assertGreater(edge, -0.01)


class ThreeCardRanking(unittest.TestCase):
    def test_categories_order(self) -> None:
        sf = side.tcp_rank(cards("AH", "KH", "QH"))
        trips = side.tcp_rank(cards("9H", "9D", "9S"))
        straight = side.tcp_rank(cards("9H", "8D", "7S"))
        flush = side.tcp_rank(cards("AH", "9H", "2H"))
        pair = side.tcp_rank(cards("JH", "JD", "3S"))
        high = side.tcp_rank(cards("AH", "9D", "2S"))
        self.assertEqual(sf[0], "straight_flush")
        self.assertEqual(trips[0], "three_of_a_kind")
        self.assertEqual(straight[0], "straight")
        self.assertEqual(flush[0], "flush")
        self.assertEqual(pair[0], "pair")
        self.assertEqual(high[0], "high_card")
        self.assertGreater(sf[1], trips[1])
        self.assertGreater(trips[1], straight[1])
        self.assertGreater(straight[1], flush[1])
        self.assertGreater(flush[1], pair[1])
        self.assertGreater(pair[1], high[1])

    def test_wheel_straight_is_lowest(self) -> None:
        wheel = side.tcp_rank(cards("AH", "2D", "3S"))
        four = side.tcp_rank(cards("4H", "5D", "6S"))
        broadway = side.tcp_rank(cards("AH", "KD", "QS"))
        self.assertEqual(wheel[0], "straight")
        self.assertLess(wheel[1], four[1])
        self.assertLess(four[1], broadway[1])

    def test_dealer_qualifies_queen_high(self) -> None:
        self.assertTrue(side.tcp_qualifies(cards("QH", "6D", "4S")))
        self.assertTrue(side.tcp_qualifies(cards("KH", "2D", "3S")))
        self.assertTrue(side.tcp_qualifies(cards("9H", "9D", "2S")))
        self.assertFalse(side.tcp_qualifies(cards("JH", "9D", "7S")))
        self.assertFalse(side.tcp_qualifies(cards("JH", "6D", "4S")))

    def test_q64_strategy(self) -> None:
        self.assertTrue(side.tcp_should_play(cards("QH", "6D", "4S")))
        self.assertTrue(side.tcp_should_play(cards("QH", "7D", "2S")))
        self.assertFalse(side.tcp_should_play(cards("QH", "6D", "3S")))
        self.assertFalse(side.tcp_should_play(cards("JH", "9D", "7S")))
        self.assertTrue(side.tcp_should_play(cards("2H", "2D", "3S")))

    def test_ante_play_payouts(self) -> None:
        ante, pp = 100, 0
        # Player wins, dealer qualifies: ante 1:1 + play 1:1 → 400 back on 200 risked
        p, d = cards("AH", "AD", "9S"), cards("KH", "QD", "2S")
        r = side.tcp_settle(p, d, ante, pp, played=True)
        self.assertEqual(r["result"], "win")
        self.assertEqual(r["payout"], 400)

        # Dealer does not qualify: ante 1:1, play pushes → 300
        d2 = cards("JH", "9D", "2S")
        r = side.tcp_settle(p, d2, ante, pp, played=True)
        self.assertFalse(r["dealer_qualifies"])
        self.assertEqual(r["payout"], 300)

        # Dealer wins: 0 (high card vs king-high)
        r = side.tcp_settle(cards("9H", "6D", "2S"), cards("KH", "QD", "2S"), ante, pp, True)
        self.assertEqual(r["result"], "lose")
        self.assertEqual(r["payout"], 0)

        # Tie: both bets push → 200
        hand = cards("KH", "9D", "2S")
        r = side.tcp_settle(hand, cards("KS", "9C", "2H"), ante, pp, True)
        self.assertEqual(r["result"], "tie")
        self.assertEqual(r["payout"], 200)

        # Fold: lose ante
        r = side.tcp_settle(cards("4H", "3D", "2S"), d, ante, pp, False)
        self.assertEqual(r["result"], "fold")
        self.assertEqual(r["payout"], 0)

    def test_ante_bonus_and_pair_plus(self) -> None:
        # Straight flush ante bonus 5:1, pair plus 40:1, plus win vs qualifying dealer
        p = cards("AH", "KH", "QH")
        d = cards("9S", "9D", "2C")  # pair, qualifies, player wins
        r = side.tcp_settle(p, d, 100, 100, True)
        # ante 200 + play 200 + ante bonus 500 + pair plus 4100
        self.assertEqual(r["ante_bonus"], 500)
        self.assertEqual(r["pair_plus_payout"], 4100)
        self.assertEqual(r["payout"], 200 + 200 + 500 + 4100)

        # Fold still pays pair plus
        r = side.tcp_settle(cards("JH", "JD", "3S"), d, 100, 100, False)
        self.assertEqual(r["payout"], 200)  # pair 1:1
        self.assertEqual(r["ante_bonus"], 0)

        # Straight ante bonus 1:1 even if dealer wins? Paid if you play.
        p = cards("9H", "8D", "7S")
        d = cards("AH", "AD", "AS")  # dealer trips, wins
        r = side.tcp_settle(p, d, 100, 0, True)
        self.assertEqual(r["result"], "lose")
        self.assertEqual(r["ante_bonus"], 100)
        self.assertEqual(r["payout"], 100)


class ThreeCardSession(unittest.TestCase):
    def test_deal_play_and_fold(self) -> None:
        pid = player()
        res = ledger.play_side(pid, "threecard", {"action": "deal", "ante": 1000, "pair_plus": 500})
        self.assertFalse(res["done"])
        self.assertEqual(len(res["player"]), 3)
        self.assertTrue(all(c.get("hidden") or c.get("suit") == "back" for c in res["dealer"]))
        self.assertEqual(ledger.snapshot(pid)["coins"], 1_000_000 - 1500)
        # Play (debits another 1000 ante match)
        res2 = ledger.play_side(pid, "threecard", {"action": "play"})
        self.assertTrue(res2["done"])
        self.assertEqual(len(res2["dealer"]), 3)
        self.assertFalse(res2["dealer"][0].get("hidden"))
        after = ledger.snapshot(pid)["coins"]
        self.assertEqual(after, 1_000_000 - 1500 - 1000 + res2["payout"])

        # Fold path
        pid = player()
        ledger.play_side(pid, "threecard", {"action": "deal", "ante": 200, "pair_plus": 0})
        res = ledger.play_side(pid, "threecard", {"action": "fold"})
        self.assertEqual(res["result"], "fold")
        self.assertEqual(ledger.snapshot(pid)["coins"], 1_000_000 - 200 + res["payout"])

    def test_rejects_invalid(self) -> None:
        pid = player(100)
        with self.assertRaises(ValueError):
            ledger.play_side(pid, "threecard", {"action": "deal", "ante": 0})
        with self.assertRaises(ValueError):
            ledger.play_side(pid, "threecard", {"action": "deal", "ante": 500})
        with self.assertRaises(ValueError):
            ledger.play_side(pid, "threecard", {"action": "play"})


class ThreeCardHouseEdge(unittest.TestCase):
    def test_ante_edge_near_3_4_percent(self) -> None:
        """Q-6-4 strategy, ante/play only. House edge is ~3.37% of the ante."""
        ante = 10
        net = 0  # player net coins
        n = 40_000
        for _ in range(n):
            st = side.threecard_deal(ante, 0)
            play = side.tcp_should_play(st["player"])
            debit = ante + (ante if play else 0)
            out = side.threecard_act(st, "play" if play else "fold")
            net += out["payout"] - debit
        edge = -net / (n * ante)
        self.assertGreater(edge, 0.02)
        self.assertLess(edge, 0.05)


class CasinoWarRules(unittest.TestCase):
    def test_win_lose_tie_math(self) -> None:
        ace, king, two = C("A"), C("K"), C("2")
        self.assertEqual(side.war_settle(ace, king, 100)["payout"], 200)
        self.assertEqual(side.war_settle(ace, king, 100)["result"], "win")
        self.assertEqual(side.war_settle(two, king, 100)["payout"], 0)
        self.assertEqual(side.war_settle(two, king, 100)["result"], "lose")
        tie = side.war_settle(king, C("K", "hearts"), 100)
        self.assertEqual(tie["result"], "tie")
        self.assertTrue(tie["awaiting_war"])
        self.assertFalse(tie["done"])

    def test_war_raise_pays_even_money_on_raise_only(self) -> None:
        # War win: ante pushes + raise 1:1 → 300 on 100+100
        r = side.war_settle(C("K"), C("K", "hearts"), 100, war=True, raise_bet=100,
                            player_war=C("A"), dealer_war=C("2"))
        self.assertEqual(r["result"], "war_win")
        self.assertEqual(r["payout"], 300)
        r = side.war_settle(C("K"), C("K", "hearts"), 100, war=True, raise_bet=100,
                            player_war=C("2"), dealer_war=C("A"))
        self.assertEqual(r["result"], "war_lose")
        self.assertEqual(r["payout"], 0)
        r = side.war_settle(C("K"), C("K", "hearts"), 100, war=True, raise_bet=100,
                            player_war=C("9"), dealer_war=C("9", "hearts"))
        self.assertEqual(r["result"], "war_tie")
        self.assertEqual(r["payout"], 200)  # both bets push

    def test_surrender_returns_half(self) -> None:
        st = {
            "game": "war", "done": False, "awaiting_war": True, "bet": 100,
            "player": C("K"), "dealer": C("K", "hearts"), "shoe": side._fresh_shoe(6),
        }
        out = side.war_act(st, "surrender")
        self.assertEqual(out["payout"], 50)
        self.assertEqual(out["result"], "surrender")


class CasinoWarSession(unittest.TestCase):
    def test_play_and_rejects(self) -> None:
        pid = player()
        res = ledger.play_side(pid, "war", {"action": "deal", "bet": 1000})
        self.assertIn(res["result"], ("win", "lose", "tie"))
        if res.get("awaiting_war"):
            res2 = ledger.play_side(pid, "war", {"action": "surrender"})
            self.assertEqual(res2["result"], "surrender")
            self.assertEqual(ledger.snapshot(pid)["coins"], 1_000_000 - 1000 + 500)
        else:
            after = ledger.snapshot(pid)["coins"]
            self.assertEqual(after, 1_000_000 - 1000 + res["payout"])

        pid = player(200)
        with self.assertRaises(ValueError):
            ledger.play_side(pid, "war", {"action": "deal", "bet": 0})
        with self.assertRaises(ValueError):
            ledger.play_side(pid, "war", {"action": "deal", "bet": 500})
        with self.assertRaises(ValueError):
            ledger.play_side(pid, "war", {"action": "war"})

    def test_war_raise_insufficient_coins(self) -> None:
        # Keep dealing until a tie, with just enough for the ante but not the raise.
        # Use the engine to force a tie session in the ledger.
        pid = player(100)
        # Manually open a tie session.
        st = {
            "game": "war", "done": False, "awaiting_war": True, "bet": 100,
            "player": C("Q", "hearts"), "dealer": C("Q", "spades"),
            "shoe": side._fresh_shoe(6), "payout": 0, "result": "tie", "can": ["war", "surrender"],
        }
        import json
        with ledger.transaction() as conn:
            conn.execute(
                "INSERT INTO side_sessions (player_id, game, state, updated_at) VALUES (?, ?, ?, ?)",
                (pid, "war", json.dumps(st), "2026-01-01T00:00:00+00:00"),
            )
            conn.execute(
                "UPDATE balances SET amount = 100 WHERE player_id = ? AND asset = ?",
                (pid, game.COIN_ASSET),
            )
        # Ante already conceptually taken; balance is 100, not enough to go to war (needs another 100).
        # Actually after deal the ante would have been taken; here we set balance to 100 remaining.
        # War raise needs 100, so 100 is enough. Set to 50.
        with ledger.transaction() as conn:
            conn.execute(
                "UPDATE balances SET amount = 50 WHERE player_id = ? AND asset = ?",
                (pid, game.COIN_ASSET),
            )
        with self.assertRaises(ValueError):
            ledger.play_side(pid, "war", {"action": "war"})
        # Surrender still works
        res = ledger.play_side(pid, "war", {"action": "surrender"})
        self.assertEqual(res["payout"], 50)


class CasinoWarHouseEdge(unittest.TestCase):
    def test_always_war_edge_near_2_9_percent(self) -> None:
        """Always go to war on a tie. Six-deck shoe, both-bets-push on a war tie. HE ≈ 2.88%."""
        bet = 10
        net = 0
        n = 40_000
        for _ in range(n):
            st = side.war_deal(bet)
            debit = bet
            if st.get("awaiting_war"):
                debit += bet
                st = side.war_act(st, "war")
            net += st["payout"] - debit
        edge = -net / (n * bet)
        self.assertGreater(edge, 0.015)
        self.assertLess(edge, 0.045)


class CatalogueAndUnknown(unittest.TestCase):
    def test_catalogue_lists_new_games(self) -> None:
        cat = side.catalogue()
        ids = {g["id"] for g in cat["games"]}
        self.assertTrue({"videopoker", "threecard", "war"} <= ids)
        self.assertEqual(cat["videopoker"]["pays"]["full_house"], 9)
        self.assertEqual(cat["videopoker"]["pays"]["flush"], 6)
        self.assertEqual(cat["threecard"]["dealer_qualifies"], "Q-high")

    def test_unknown_game_rejected(self) -> None:
        pid = player()
        with self.assertRaises(ValueError):
            ledger.play_side(pid, "keno", {"bet": 100})


if __name__ == "__main__":
    unittest.main(verbosity=1)
