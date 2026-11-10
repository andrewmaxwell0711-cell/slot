#!/usr/bin/env python3
"""Unit-style checks: 20%-of-pool cap, jackpot == cap, multi-line evaluation,
gamble limits, and that public API responses never leak pool/max-win numbers."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))

import game  # noqa: E402
import ledger  # noqa: E402

NO_JP = lambda bet, pool: False  # noqa: E731
JP = lambda bet, pool: True  # noqa: E731


def fresh_db() -> None:
    ledger.DB_PATH = Path(tempfile.mkdtemp()) / "t.db"
    ledger._local.conn = None
    ledger.init_db()


def fund(pid: str, aud: float) -> None:
    ledger.ensure_player(pid)
    with ledger.transaction() as c:
        c.execute("UPDATE balances SET amount = ? WHERE player_id = ? AND asset = 'AUD'", (aud, pid))


def set_pool(pool: float) -> None:
    with ledger.transaction() as c:
        c.execute("UPDATE house SET pool_aud = ? WHERE id = 1", (pool,))


def step(raw: float, mult: int = 1) -> dict:
    return {"grid": [["shard"] * 3 for _ in range(5)], "line_wins": [], "scatters": 0, "scatter_pos": [],
            "scatter_win_aud": 0.0, "free_spins_awarded": 0, "multiplier": mult, "raw_win_aud": raw}


def rnd(raw_base: float, free: list[float] = ()) -> dict:
    return {"base": step(raw_base), "free_spins": [step(r, 2) for r in free]}


def new_player(aud: float) -> str:
    pid = str(uuid.uuid4())
    fund(pid, aud)
    return pid


# ---- cap -------------------------------------------------------------------

def test_empty_pool_tiny_bet() -> None:
    fresh_db()
    pid = new_player(10)
    snap = ledger.settle_round(pid, 0.5, rnd(250.0), "AUD", NO_JP)
    assert snap["total_paid_aud"] == 0.10 and snap["any_capped"]  # pool 0.50 -> cap 0.10
    assert abs(ledger.pool_status()["pool_aud"] - 0.40) < 1e-9
    assert abs(snap["balances"]["AUD"] - 9.60) < 1e-9


def test_example_100k() -> None:
    fresh_db()
    pid = new_player(1000)
    set_pool(100_000 - 100)
    snap = ledger.settle_round(pid, 100, rnd(50_000.0), "AUD", NO_JP)
    assert snap["total_paid_aud"] == 20_000.0
    assert ledger.pool_status()["pool_aud"] == 80_000.0


def test_small_win_uncapped() -> None:
    fresh_db()
    pid = new_player(100)
    set_pool(10_000)
    snap = ledger.settle_round(pid, 1, rnd(4.0), "AUD", NO_JP)
    assert snap["total_paid_aud"] == 4.0 and not snap["any_capped"]


def test_free_spins_each_capped() -> None:
    fresh_db()
    pid = new_player(100)
    set_pool(99)
    snap = ledger.settle_round(pid, 1, rnd(10.0, [1000.0, 1000.0, 1000.0]), "AUD", NO_JP)
    pool, expected = 100.0, 0.0
    for raw in (10.0, 1000.0, 1000.0, 1000.0):
        paid = min(raw, game.cap_for_pool(pool))
        pool -= paid
        expected += paid
    assert abs(snap["total_paid_aud"] - round(expected, 2)) < 0.011
    for s in snap["steps"]:
        assert s["paid_aud"] + s["jackpot_aud"] <= s["cap_aud"] + 1e-9
    assert ledger.pool_status()["pool_aud"] > 0


# ---- jackpot = cap ---------------------------------------------------------

def test_jackpot_pays_exactly_cap() -> None:
    fresh_db()
    pid = new_player(100)
    set_pool(100_000 - 1)
    snap = ledger.settle_round(pid, 1, rnd(3.0), "AUD", JP)
    assert snap["jackpot_hit"]
    assert snap["total_paid_aud"] == 20_000.0, snap["total_paid_aud"]  # line win 3 + jackpot 19,997
    assert snap["jackpot_paid_aud"] == 19_997.0
    assert ledger.pool_status()["pool_aud"] == 80_000.0


def test_jackpot_never_exceeds_cap_with_free_spins() -> None:
    fresh_db()
    pid = new_player(100)
    set_pool(999)
    snap = ledger.settle_round(pid, 1, rnd(5000.0, [5000.0, 5000.0]), "AUD", JP)
    first = snap["steps"][0]
    assert first["paid_aud"] + first["jackpot_aud"] == first["cap_aud"] == 200.0
    for s in snap["steps"]:
        assert s["paid_aud"] + s["jackpot_aud"] <= s["cap_aud"] + 1e-9
    assert ledger.pool_status()["pool_aud"] >= 0


def test_jackpot_probability_scales() -> None:
    assert game.jackpot_probability(1, 0) == 0.0
    assert game.jackpot_probability(1, 10) == game.JACKPOT_MAX_P  # clamped on tiny pools
    assert abs(game.jackpot_probability(1, 1_000_000) - game.JACKPOT_C / 1_000_000) < 1e-15
    # EV per A$1 staked = p * 0.2 * pool = JACKPOT_C * 0.2 regardless of pool size
    for pool in (5_000, 100_000, 10_000_000):
        ev = game.jackpot_probability(1, pool) * game.cap_for_pool(pool)
        assert abs(ev - game.JACKPOT_C * game.POOL_CAP_FRACTION) < 1e-3


def test_pool_never_negative_random() -> None:
    fresh_db()
    pid = new_player(10_000_000)
    for _ in range(2000):
        lines = game._rng.choice(game.LINE_OPTIONS)
        bpl = game._rng.choice(game.BET_PER_LINE_AUD)
        total = round(lines * bpl, 2)
        before = ledger.pool_status()["pool_aud"] + total
        snap = ledger.settle_round(pid, total, game.play_round(bpl, lines), "AUD",
                                   JP if game._rng.random() < 0.05 else NO_JP)
        for s in snap["steps"]:
            assert s["paid_aud"] + s["jackpot_aud"] <= s["cap_aud"] + 1e-9
            assert s["cap_aud"] <= 0.2 * before + 1e-6
        assert ledger.pool_status()["pool_aud"] >= 0


def test_zero_pool_cap() -> None:
    assert game.cap_for_pool(0) == 0.0
    assert game.cap_for_pool(-5) == 0.0
    assert game.cap_for_pool(100_000) == 20_000.0
    assert game.cap_for_pool(0.04) == 0.0


# ---- multi-line evaluation -------------------------------------------------

def grid_from_rows(top: str, mid: str, bot: str) -> list[list[str]]:
    rows = [top.split(), mid.split(), bot.split()]
    return [[rows[r][c] for r in range(3)] for c in range(5)]


def test_paylines_shape() -> None:
    assert len(game.PAYLINES) == 25 and len(set(game.PAYLINES)) == 25
    assert all(len(p) == 5 and all(r in (0, 1, 2) for r in p) for p in game.PAYLINES)
    assert game.PAYLINES[3] == (0, 1, 2, 1, 0)  # V
    assert game.PAYLINES[13] == (0, 1, 0, 1, 0)  # zigzag


def test_centre_line_only_with_one_line() -> None:
    g = grid_from_rows("ruby ruby ruby ruby ruby", "quartz quartz quartz shard topaz", "topaz topaz topaz topaz topaz")
    wins = game.evaluate_lines(g, 1, 1)
    assert [(w["line"], w["count"], w["symbol"], w["win_aud"]) for w in wins] == [(1, 3, "quartz", 4)]
    wins25 = {w["line"]: w for w in game.evaluate_lines(g, 1, 25)}
    assert wins25[2]["symbol"] == "ruby" and wins25[2]["count"] == 5 and wins25[2]["win_aud"] == 200
    assert wins25[3]["symbol"] == "topaz" and wins25[3]["win_aud"] == 40


def test_v_line_and_wild_double() -> None:
    g = grid_from_rows("sapphire citrine quartz citrine sapphire",
                       "topaz wild quartz wild topaz",
                       "amethyst citrine sapphire citrine amethyst")
    wins = {w["line"]: w for w in game.evaluate_lines(g, 0.5, 25)}
    v = wins[4]  # V: top, mid, bottom, mid, top -> sapphire wild sapphire wild sapphire
    assert v["count"] == 5 and v["symbol"] == "sapphire" and v["wild"] and v["mult"] == 200
    assert v["win_aud"] == 100.0 and v["cells"] == [[0, 0], [1, 1], [2, 2], [3, 1], [4, 0]]


def test_scatter_and_shard_break_lines() -> None:
    g = grid_from_rows("ruby ruby scatter ruby ruby", "emerald emerald shard emerald emerald", "quartz quartz quartz scatter quartz")
    wins = {w["line"]: w for w in game.evaluate_lines(g, 1, 25)}
    assert 1 not in wins and 2 not in wins
    assert wins[3]["count"] == 3 and wins[3]["symbol"] == "quartz"


def test_pure_wilds_and_leading_wilds() -> None:
    g = grid_from_rows("shard shard shard shard shard", "wild wild wild shard shard", "shard shard shard shard shard")
    w = game.evaluate_lines(g, 1, 1)[0]
    assert w["symbol"] == "wild" and w["count"] == 3 and w["mult"] == 50 and not w["wild"]
    g = grid_from_rows("shard shard shard shard shard", "wild wild ruby ruby citrine", "shard shard shard shard shard")
    w = game.evaluate_lines(g, 1, 1)[0]
    assert w["symbol"] == "ruby" and w["count"] == 4 and w["mult"] == 160


def test_scatter_pays_on_total_bet() -> None:
    g = grid_from_rows("scatter shard shard shard scatter", "shard shard scatter shard shard", "shard shard shard shard shard")
    assert game.count_scatters(g) == 3
    mult, fs = game.SCATTER_PAYS[3]
    assert (mult, fs) == (2, 8)


# ---- gamble ----------------------------------------------------------------

def card(colour: str):
    return lambda: {"rank": "A", "suit": "hearts" if colour == "red" else "spades", "colour": colour}


def test_gamble_win_lose_and_limit() -> None:
    fresh_db()
    pid = new_player(100)
    set_pool(10_000)
    ledger.settle_round(pid, 1, rnd(10.0), "AUD", NO_JP)  # win 10 -> gamble 10
    snap = ledger.gamble(pid, "red", card("red"))
    assert snap["won"] and snap["gamble_payout_aud"] == 20 and snap["gamble_aud"] == 20
    snap = ledger.gamble(pid, "black", card("red"))
    assert not snap["won"] and snap["gamble_aud"] == 0
    try:
        ledger.gamble(pid, "red", card("red"))
        raise AssertionError("should refuse with nothing to gamble")
    except ValueError:
        pass
    # Limit: double must fit under the cap
    fresh_db()
    pid = new_player(1000)
    set_pool(20)
    ledger.settle_round(pid, 1, rnd(4.0), "AUD", NO_JP)  # pool 21 -> cap 4.2 -> paid 4, pool 17
    try:
        ledger.gamble(pid, "red", card("red"))  # pool 21 with stake, cap 4.2 < 8
        raise AssertionError("should be limited")
    except ledger.GambleUnavailable:
        pass
    assert ledger.snapshot(pid)["gamble_aud"] == 0


def test_gamble_max_rounds() -> None:
    fresh_db()
    pid = new_player(100)
    set_pool(1_000_000)
    ledger.settle_round(pid, 1, rnd(1.0), "AUD", NO_JP)
    for i in range(game.GAMBLE_MAX_ROUNDS):
        snap = ledger.gamble(pid, "red", card("red"))
    assert snap["gamble_aud"] == 0 and snap["gamble_payout_aud"] == 32


# ---- public API never leaks pool numbers ----------------------------------

def test_public_api_hides_pool() -> None:
    fresh_db()
    os.environ.pop("STRIPE_SECRET_KEY", None)
    import app as app_module  # noqa: E402  (initialises against the temp DB)
    client = app_module.app.test_client()
    bad = ("pool", "max_win", "cap_aud", "cap_fraction", "jackpot_meter")
    r = client.get("/api/balance")
    pid = None
    for c in r.headers.getlist("Set-Cookie"):
        if c.startswith("fr_player="):
            pid = c.split("=", 1)[1].split(";", 1)[0]
    fund(pid, 500)
    set_pool(5000)
    bodies = [r.get_data(as_text=True)]
    for _ in range(40):
        r = client.post("/api/spin", json={"lines": 25, "bet_per_line_index": 2})
        assert r.status_code == 200, r.get_data(as_text=True)
        bodies.append(r.get_data(as_text=True))
    bodies.append(client.get("/api/config").get_data(as_text=True))
    for b in bodies:
        for k in bad:
            assert k not in b, (k, b[:200])
    assert client.get("/api/pool").status_code == 404
    assert client.post("/api/spin", json={"lines": 7, "bet_per_line_index": 0}).status_code == 400
    j = json.loads(bodies[1])
    assert j["bet_aud"] == 2.5 and j["lines"] == 25


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print(f"{len(tests)} tests passed")
