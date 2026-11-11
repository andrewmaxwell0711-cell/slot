#!/usr/bin/env python3
"""v7.1 roulette payouts (especially 1st 12 / dozens / columns) and bet validation.

The client sends {kind:"dozen", dozen:1, amount:N} with no `numbers` field.
A parser precedence bug used to reject every dozen bet as "Dozen is 1, 2 or 3".
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


# Exact shape the v7 client posts (no `numbers` array).
def dozen_bet(n: int, amount: int = 100) -> dict:
    return {"kind": "dozen", "dozen": n, "amount": amount}


def column_bet(n: int, amount: int = 100) -> dict:
    return {"kind": "column", "column": n, "amount": amount}


class DozenFirstTwelve(unittest.TestCase):
    def test_client_payload_without_numbers_is_first_dozen(self) -> None:
        parsed = side._validate_roulette_bet(dozen_bet(1, 30_000))
        self.assertEqual(parsed["dozen"], 1)
        self.assertEqual(parsed["numbers"], list(range(1, 13)))
        self.assertEqual(parsed["payout"], 2)

    def test_first_twelve_wins_2_to_1_on_1_through_12(self) -> None:
        for n in range(1, 13):
            res = side.roulette_settle([dozen_bet(1, 100)], n)
            self.assertTrue(res["bets"][0]["hit"], f"{n} should win 1st 12")
            self.assertEqual(res["payout"], 300, f"1st 12 must pay 3× stake on {n}")

    def test_first_twelve_loses_on_13_24_zero_and_36(self) -> None:
        for n in (0, 13, 24, 25, 36):
            res = side.roulette_settle([dozen_bet(1, 30_000)], n)
            self.assertFalse(res["bets"][0]["hit"])
            self.assertEqual(res["payout"], 0)

    def test_second_and_third_dozen_win_and_loss(self) -> None:
        r = side.roulette_settle([dozen_bet(2, 100)], 13)
        self.assertEqual(r["payout"], 300)
        r = side.roulette_settle([dozen_bet(2, 100)], 24)
        self.assertEqual(r["payout"], 300)
        r = side.roulette_settle([dozen_bet(2, 100)], 12)
        self.assertEqual(r["payout"], 0)
        r = side.roulette_settle([dozen_bet(3, 100)], 25)
        self.assertEqual(r["payout"], 300)
        r = side.roulette_settle([dozen_bet(3, 100)], 36)
        self.assertEqual(r["payout"], 300)
        r = side.roulette_settle([dozen_bet(3, 100)], 24)
        self.assertEqual(r["payout"], 0)
        r = side.roulette_settle([dozen_bet(3, 100)], 0)
        self.assertEqual(r["payout"], 0)

    def test_dozen_string_index_and_invalid(self) -> None:
        parsed = side._validate_roulette_bet({"kind": "dozen", "dozen": "1", "amount": 50})
        self.assertEqual(parsed["dozen"], 1)
        with self.assertRaises(side.SideError):
            side._validate_roulette_bet({"kind": "dozen", "amount": 50})
        with self.assertRaises(side.SideError):
            side._validate_roulette_bet({"kind": "dozen", "dozen": 0, "amount": 50})
        with self.assertRaises(side.SideError):
            side._validate_roulette_bet({"kind": "dozen", "dozen": 4, "amount": 50})


class ColumnsAndOutside(unittest.TestCase):
    def test_all_three_columns(self) -> None:
        # Column 1: 1,4,7,...,34
        self.assertEqual(side._validate_roulette_bet(column_bet(1))["numbers"], list(range(1, 37, 3)))
        self.assertEqual(side.roulette_settle([column_bet(1, 100)], 1)["payout"], 300)
        self.assertEqual(side.roulette_settle([column_bet(1, 100)], 34)["payout"], 300)
        self.assertEqual(side.roulette_settle([column_bet(1, 100)], 2)["payout"], 0)
        self.assertEqual(side.roulette_settle([column_bet(1, 100)], 0)["payout"], 0)
        # Column 2: 2,5,...,35
        self.assertEqual(side.roulette_settle([column_bet(2, 100)], 2)["payout"], 300)
        self.assertEqual(side.roulette_settle([column_bet(2, 100)], 35)["payout"], 300)
        self.assertEqual(side.roulette_settle([column_bet(2, 100)], 3)["payout"], 0)
        # Column 3: 3,6,...,36
        self.assertEqual(side.roulette_settle([column_bet(3, 100)], 3)["payout"], 300)
        self.assertEqual(side.roulette_settle([column_bet(3, 100)], 36)["payout"], 300)
        self.assertEqual(side.roulette_settle([column_bet(3, 100)], 1)["payout"], 0)

    def test_even_money_bets(self) -> None:
        self.assertEqual(side.roulette_settle([{"kind": "red", "amount": 10}], 1)["payout"], 20)
        self.assertEqual(side.roulette_settle([{"kind": "red", "amount": 10}], 2)["payout"], 0)
        self.assertEqual(side.roulette_settle([{"kind": "black", "amount": 10}], 2)["payout"], 20)
        self.assertEqual(side.roulette_settle([{"kind": "odd", "amount": 10}], 7)["payout"], 20)
        self.assertEqual(side.roulette_settle([{"kind": "even", "amount": 10}], 8)["payout"], 20)
        self.assertEqual(side.roulette_settle([{"kind": "low", "amount": 10}], 1)["payout"], 20)
        self.assertEqual(side.roulette_settle([{"kind": "low", "amount": 10}], 18)["payout"], 20)
        self.assertEqual(side.roulette_settle([{"kind": "low", "amount": 10}], 19)["payout"], 0)
        self.assertEqual(side.roulette_settle([{"kind": "high", "amount": 10}], 19)["payout"], 20)
        self.assertEqual(side.roulette_settle([{"kind": "high", "amount": 10}], 36)["payout"], 20)
        self.assertEqual(side.roulette_settle([{"kind": "high", "amount": 10}], 18)["payout"], 0)
        for kind in ("red", "black", "odd", "even", "low", "high"):
            self.assertEqual(side.roulette_settle([{"kind": kind, "amount": 10}], 0)["payout"], 0)

    def test_straight_zero_through_a_sample(self) -> None:
        for n in (0, 1, 17, 24, 36):
            res = side.roulette_settle([{"kind": "straight", "number": n, "amount": 10}], n)
            self.assertEqual(res["payout"], 360)
            res = side.roulette_settle([{"kind": "straight", "number": n, "amount": 10}], (n + 1) % 37)
            self.assertEqual(res["payout"], 0)

    def test_split_adjacent_pays_17_to_1(self) -> None:
        res = side.roulette_settle([{"kind": "split", "numbers": [2, 3], "amount": 10}], 2)
        self.assertEqual(res["payout"], 180)
        res = side.roulette_settle([{"kind": "split", "numbers": [2, 3], "amount": 10}], 4)
        self.assertEqual(res["payout"], 0)
        with self.assertRaises(side.SideError):
            side._validate_roulette_bet({"kind": "split", "numbers": [1, 3], "amount": 10})


class LedgerClientPayload(unittest.TestCase):
    def test_play_side_accepts_client_dozen_and_credits_3x_on_win(self) -> None:
        # Deterministic via settle; ledger path uses rng. Here we only check
        # the client-shaped payload is accepted (no "Dozen is 1, 2 or 3").
        pid = player()
        res = ledger.play_side(pid, "roulette", {"bets": [dozen_bet(1, 1000)]})
        self.assertEqual(res["game"], "roulette")
        self.assertIn(res["number"], range(0, 37))
        if 1 <= res["number"] <= 12:
            self.assertEqual(res["payout"], 3000)
            self.assertEqual(ledger.snapshot(pid)["coins"], 1_000_000 - 1000 + 3000)
        else:
            self.assertEqual(res["payout"], 0)
            self.assertEqual(ledger.snapshot(pid)["coins"], 1_000_000 - 1000)

    def test_play_side_rejects_invalid_outside_bets(self) -> None:
        pid = player()
        with self.assertRaises((ValueError, side.SideError)):
            ledger.play_side(pid, "roulette", {"bets": [{"kind": "dozen", "dozen": 0, "amount": 100}]})
        with self.assertRaises((ValueError, side.SideError)):
            ledger.play_side(pid, "roulette", {"bets": [{"kind": "column", "column": 4, "amount": 100}]})



def C(rank: str, suit: str = "spades") -> dict:
    return side._card(rank, suit)


def cards(*spec: str) -> list[dict]:
    suit = {"H": "hearts", "D": "diamonds", "C": "clubs", "S": "spades"}
    out = []
    for s in spec:
        s = s.upper()
        if s.startswith("10"):
            r, u = "10", s[2]
        else:
            r, u = s[0], s[-1]
            if s[0] == "T":
                r = "10"
        out.append(C(r, suit[u]))
    return out


class ThreeCardClarity(unittest.TestCase):
    def test_hand_labels(self) -> None:
        self.assertEqual(side.tcp_hand_label(cards("8H", "8D", "KS")), "Pair of 8s")
        self.assertEqual(side.tcp_hand_label(cards("AH", "AD", "AS")), "Three Aces")
        self.assertEqual(side.tcp_hand_label(cards("QH", "6D", "4S")), "Queen high")
        self.assertEqual(side.tcp_hand_label(cards("9H", "8D", "7S")), "Straight")
        self.assertEqual(side.tcp_hand_label(cards("QH", "9H", "2H")), "Flush, Queen high")
        self.assertEqual(side.tcp_hand_label(cards("9H", "8H", "7H")), "Straight flush")

    def test_settle_includes_labels_banner_and_breakdown(self) -> None:
        r = side.tcp_settle(cards("AH", "AD", "9S"), cards("KH", "QD", "2S"), 100, 0, True)
        self.assertEqual(r["player_hand_label"], "Pair of Aces")
        self.assertEqual(r["dealer_hand_label"], "King high")
        self.assertTrue(r["dealer_qualifies"])
        self.assertEqual(r["result_banner"], "YOU WIN")
        self.assertEqual(r["ante_status"], "win")
        self.assertEqual(r["play_status"], "win")
        self.assertEqual(r["net"], 200)  # risked 200, returned 400

    def test_dealer_does_not_qualify_banner(self) -> None:
        r = side.tcp_settle(cards("9H", "6D", "2S"), cards("JH", "9D", "7S"), 100, 0, True)
        self.assertFalse(r["dealer_qualifies"])
        self.assertEqual(r["result_banner"], "YOU WIN")
        self.assertEqual(r["ante_status"], "win")
        self.assertEqual(r["play_status"], "push")

    def test_deal_includes_player_label_and_hint(self) -> None:
        st = side.threecard_deal(100, 0)
        self.assertIn("player_hand_label", st)
        self.assertIn(st["hint_play"], (True, False))
        pub = side.threecard_public(st)
        self.assertTrue(all(c.get("hidden") or c.get("suit") == "back" for c in pub["dealer"]))
        self.assertIn("player_hand_label", pub)


class VideoPokerClarity(unittest.TestCase):
    def test_job_hand_label(self) -> None:
        self.assertEqual(side.job_hand_label("jacks_or_better"), "Jacks or better")
        self.assertEqual(side.job_hand_label("royal_flush"), "Royal flush")
        self.assertEqual(side.job_hand_label("nothing"), "Nothing")


if __name__ == "__main__":
    unittest.main(verbosity=1)
