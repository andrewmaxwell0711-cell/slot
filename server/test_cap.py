#!/usr/bin/env python3
"""Unit-style checks: uncapped payouts, fixed Green Tea Jackpot (× total bet),
multi-line evaluation, fair 50/50 gamble, and that public API responses never
leak pool / cap / max-win numbers."""

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


def fund(pid: str, units: float) -> None:
    """Set a player's coin balance to the coin equivalent of `units` (game units)."""
    ledger.ensure_player(pid)
    coins = game.to_coins(units)
    with ledger.transaction() as c:
        c.execute(
            "UPDATE balances SET amount = ? WHERE player_id = ? AND asset = ?",
            (coins, pid, game.COIN_ASSET),
        )


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

def test_empty_pool_pays_in_full() -> None:
    fresh_db()
    pid = new_player(10)
    snap = ledger.settle_round(pid, 0.5, rnd(250.0), "AUD", NO_JP)
    # No payout cap: a 250-unit win is paid even if the internal pool starts at 0.
    assert snap["total_paid_aud"] == 250.0 and not snap["any_capped"]
    assert ledger.pool_status()["pool_aud"] == 0.0
    assert snap["coins"] == game.to_coins(10 - 0.5 + 250)


def test_example_100k() -> None:
    fresh_db()
    pid = new_player(1000)
    set_pool(100_000 - 100)
    snap = ledger.settle_round(pid, 100, rnd(50_000.0), "AUD", NO_JP)
    assert snap["total_paid_aud"] == 50_000.0
    assert ledger.pool_status()["pool_aud"] == 50_000.0


def test_small_win_uncapped() -> None:
    fresh_db()
    pid = new_player(100)
    set_pool(10_000)
    snap = ledger.settle_round(pid, 1, rnd(4.0), "AUD", NO_JP)
    assert snap["total_paid_aud"] == 4.0 and not snap["any_capped"]


def test_free_spins_each_pay_in_full() -> None:
    fresh_db()
    pid = new_player(100)
    set_pool(99)
    snap = ledger.settle_round(pid, 1, rnd(10.0, [1000.0, 1000.0, 1000.0]), "AUD", NO_JP)
    assert snap["total_paid_aud"] == 3010.0
    assert all(not s.get("capped") and "cap_aud" not in s for s in snap["steps"])
    assert [s["paid_aud"] for s in snap["steps"]] == [10.0, 1000.0, 1000.0, 1000.0]
    assert ledger.pool_status()["pool_aud"] >= 0


# ---- jackpot = cap ---------------------------------------------------------

def test_jackpot_pays_fixed_multiple() -> None:
    fresh_db()
    pid = new_player(100)
    set_pool(100_000 - 1)
    snap = ledger.settle_round(pid, 1, rnd(3.0), "AUD", JP)
    assert snap["jackpot_hit"]
    prize = game.jackpot_amount(1)
    assert prize == 5000.0
    assert snap["jackpot_paid_aud"] == prize
    assert snap["total_paid_aud"] == 3.0 + prize
    # Internal pool is reduced but never blocks the payout.
    assert ledger.pool_status()["pool_aud"] == 100_000.0 - prize - 3.0


def test_jackpot_plus_free_spins_pay_in_full() -> None:
    fresh_db()
    pid = new_player(100)
    set_pool(999)
    snap = ledger.settle_round(pid, 1, rnd(40.0, [50.0, 60.0]), "AUD", JP)
    first = snap["steps"][0]
    prize = game.jackpot_amount(1)
    assert first["paid_aud"] == 40.0 and first["jackpot_aud"] == prize
    assert "cap_aud" not in first
    assert [s["paid_aud"] for s in snap["steps"][1:]] == [50.0, 60.0]
    assert snap["total_paid_aud"] == 40.0 + 50.0 + 60.0 + prize
    assert ledger.pool_status()["pool_aud"] >= 0


def test_jackpot_probability_is_fixed() -> None:
    assert game.jackpot_probability(0) == 0.0
    p = game.jackpot_probability(1)
    assert p == game.JACKPOT_P
    # Chance does not depend on the hidden house pool or bet size (prize is × bet).
    for pool in (0, 10, 1_000_000):
        assert game.jackpot_probability(1, pool) == p
        assert game.jackpot_probability(50, pool) == p
    ev = p * game.JACKPOT_MULT
    assert abs(ev - 0.02) < 1e-12
    assert game.jackpot_amount(2) == 10_000.0


def test_pool_never_negative_random() -> None:
    fresh_db()
    pid = new_player(10_000_000)
    for _ in range(2000):
        lines = game._rng.choice(game.LINE_OPTIONS)
        bpl = game._rng.choice(game.BET_PER_LINE_AUD)
        total = round(lines * bpl, 2)
        snap = ledger.settle_round(pid, total, game.play_classic(bpl, lines), "AUD",
                                   JP if game._rng.random() < 0.05 else NO_JP)
        assert snap["total_paid_aud"] >= 0
        for s in snap["steps"]:
            assert "cap_aud" not in s
            assert not s.get("capped")
        assert ledger.pool_status()["pool_aud"] >= 0


def test_no_payout_cap() -> None:
    # cap_for_pool is a deprecated stub and must not be used to limit wins.
    assert game.cap_for_pool(0) == 0.0
    assert game.cap_for_pool(100_000) == 0.0
    assert game.POOL_CAP_FRACTION == 0.0


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
    assert [(w["line"], w["count"], w["symbol"], w["win_aud"]) for w in wins] == [(1, 3, "quartz", 18)]
    wins25 = {w["line"]: w for w in game.evaluate_lines(g, 1, 25)}
    assert wins25[2]["symbol"] == "ruby" and wins25[2]["count"] == 5 and wins25[2]["win_aud"] == 920
    assert wins25[3]["symbol"] == "topaz" and wins25[3]["win_aud"] == 184


def test_v_line_and_wild_double() -> None:
    g = grid_from_rows("sapphire citrine quartz citrine sapphire",
                       "topaz wild quartz wild topaz",
                       "amethyst citrine sapphire citrine amethyst")
    wins = {w["line"]: w for w in game.evaluate_lines(g, 0.5, 25)}
    v = wins[4]  # V: top, mid, bottom, mid, top -> sapphire wild sapphire wild sapphire
    assert v["count"] == 5 and v["symbol"] == "sapphire" and v["wild"] and v["mult"] == 920
    assert v["win_aud"] == 460.0 and v["cells"] == [[0, 0], [1, 1], [2, 2], [3, 1], [4, 0]]


def test_scatter_and_shard_break_lines() -> None:
    g = grid_from_rows("ruby ruby scatter ruby ruby", "emerald emerald shard emerald emerald", "quartz quartz quartz scatter quartz")
    wins = {w["line"]: w for w in game.evaluate_lines(g, 1, 25)}
    assert 1 not in wins and 2 not in wins
    assert wins[3]["count"] == 3 and wins[3]["symbol"] == "quartz"


def test_pure_wilds_and_leading_wilds() -> None:
    g = grid_from_rows("shard shard shard shard shard", "wild wild wild shard shard", "shard shard shard shard shard")
    w = game.evaluate_lines(g, 1, 1)[0]
    assert w["symbol"] == "wild" and w["count"] == 3 and w["mult"] == 230 and not w["wild"]
    g = grid_from_rows("shard shard shard shard shard", "wild wild ruby ruby citrine", "shard shard shard shard shard")
    w = game.evaluate_lines(g, 1, 1)[0]
    assert w["symbol"] == "ruby" and w["count"] == 4 and w["mult"] == 736


def test_scatter_pays_on_total_bet() -> None:
    g = grid_from_rows("scatter shard shard shard scatter", "shard shard scatter shard shard", "shard shard shard shard shard")
    assert game.count_scatters(g) == 3
    mult, fs = game.SCATTER_PAYS[3]
    assert (mult, fs) == (9, 8)


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
    # No pool cap on the double-up: a small hidden pool must not block a fair 50/50.
    fresh_db()
    pid = new_player(1000)
    set_pool(20)
    ledger.settle_round(pid, 1, rnd(4.0), "AUD", NO_JP)
    snap = ledger.gamble(pid, "red", card("red"))
    assert snap["won"] and snap["gamble_payout_aud"] == 8


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
    assert client.post("/api/spin", json={"mode": "nope"}).status_code == 400
    assert client.post("/api/spin", json={"mode": "megaways", "bet_index": 99}).status_code == 400
    mw = []
    for _ in range(40):
        r = client.post("/api/spin", json={"mode": "megaways", "bet_index": 3})
        assert r.status_code == 200, r.get_data(as_text=True)
        mw.append(r.get_data(as_text=True))
    for b in mw:
        for k in bad + ("fallback_index", "jackpot_pending", "wheel_roll"):
            assert k not in b, (k, b[:200])
    m = json.loads(mw[0])
    assert m["mode"] == "megaways" and m["bet"] == game.to_coins(1) and m["base"]["stages"] and m["base"]["ways"] >= 324
    assert "coins" in m and "balances" not in m and "total_aud" not in m
    j = json.loads(bodies[1])
    assert j["bet"] == game.to_coins(2.5) and j["lines"] == 25


# ---- v4: Megaways ----------------------------------------------------------

def mw_cols(*cols: str) -> list[list[str]]:
    """Columns as space-separated symbol ids (top-reel cell first for reels 2-5)."""
    return [c.split() for c in cols]


def test_mw_ways_range() -> None:
    seen_min, seen_max = 10**9, 0
    for _ in range(3000):
        cols = game.mw_board()
        assert len(cols) == 6
        for c, col in enumerate(cols):
            assert 2 <= len(col) <= 7
            if c in game.MW_TOP_REELS:
                assert len(col) >= 3  # 2-6 main + 1 top
            assert game.SCATTER_ID not in (col[:1] if c in game.MW_TOP_REELS else [])
            if c not in game.MW_TOP_REELS:
                assert game.WILD_ID not in col
        w = game.mw_ways(cols)
        assert w == __import__("math").prod(len(c) for c in cols)
        seen_min, seen_max = min(seen_min, w), max(seen_max, w)
    assert seen_min >= 2 * 3 ** 4 * 2 and seen_max <= 117_649
    assert game.mw_ways([["x"] * 7] * 6) == 117_649


def test_mw_ways_multiplication() -> None:
    cols = mw_cols("ruby ruby shard", "ruby wild ruby topaz", "shard ruby quartz", "ruby topaz shard", "quartz quartz", "ruby ruby")
    wins = game.mw_evaluate(cols, 1.0)
    assert len(wins) == 1
    w = wins[0]
    # reel1: 2 ruby, reel2: ruby+wild+ruby = 3, reel3: 1, reel4: 1, reel5: none -> 4 of a kind, 2*3*1*1 = 6 ways
    assert w["symbol"] == "ruby" and w["count"] == 4 and w["ways"] == 6
    assert abs(w["win_aud"] - 6 * game.MW_PAYS["ruby"][4] * game.MW_PAY_SCALE) < 1e-9
    assert len(w["cells"]) == 2 + 3 + 1 + 1
    # need the real symbol on reel 1 and 3+ adjacent reels
    assert game.mw_evaluate(mw_cols("topaz quartz", "wild ruby ruby", "ruby ruby", "ruby x", "x x", "x x"), 1.0) == []
    assert game.mw_evaluate(mw_cols("ruby x", "shard ruby x", "shard x", "ruby x x", "ruby x x", "ruby x"), 1.0) == []
    six = game.mw_evaluate(mw_cols(*["greentea greentea"] * 6), 2.0, 3)
    assert six[0]["count"] == 6 and six[0]["ways"] == 64
    assert abs(six[0]["win_aud"] - 2.0 * 64 * game.MW_PAYS["greentea"][6] * game.MW_PAY_SCALE * 3) < 1e-9


def test_mw_cascade_drop() -> None:
    orig = game.mw_pick
    game.mw_pick = lambda reel, top=False, free=False: "NEW"
    try:
        cols = mw_cols("a b c", "T x y z", "T3 p q", "T2 r s", "T4 u v", "w x")
        out, new, top_new = game.mw_cascade(cols, {(0, 1), (1, 0), (1, 2), (2, 1), (2, 2)})
    finally:
        game.mw_pick = orig
    assert out[0] == ["NEW", "a", "c"]          # survivors fall, new on top
    assert out[1] == ["NEW", "NEW", "x", "z"]   # top-reel cell refilled in place, main cell refilled
    assert out[2] == ["T3", "NEW", "NEW"]
    assert out[3] == cols[3] and out[4] == cols[4]
    assert new == [1, 1, 2, 0, 0, 0] and top_new == [False, True, False, False, False, False]
    assert [len(c) for c in out] == [len(c) for c in cols]  # heights fixed during a spin


def _fixed_mw(board: list[list[str]]):
    """Patch the RNG so the first board is `board` and every refill is a blank."""
    o_board, o_pick = game.mw_board, game.mw_pick
    game.mw_board = lambda free=False: [list(c) for c in board]
    game.mw_pick = lambda reel, top=False, free=False: "shard"
    return lambda: (setattr(game, "mw_board", o_board), setattr(game, "mw_pick", o_pick))


def test_mw_cascades_and_free_multiplier() -> None:
    board = mw_cols("ruby ruby", "shard ruby shard", "shard ruby", "shard shard topaz", "x x", "x x")
    undo = _fixed_mw(board)
    try:
        base = game.mw_play_one(1.0)
        free = game.mw_play_one(1.0, free=True, mult=3)
    finally:
        undo()
    one = 2 * 1 * 1 * game.MW_PAYS["ruby"][3] * game.MW_PAY_SCALE
    assert base["cascades"] == 1 and len(base["stages"]) == 2
    assert abs(base["raw_win_aud"] - one) < 1e-9 and base["multiplier_end"] == 1
    assert base["stages"][1]["wins"] == [] and base["stages"][1]["new"] == [2, 1, 1, 0, 0, 0]
    # free spins: win x3, then multiplier grows +1 per winning cascade (unlimited)
    assert abs(free["raw_win_aud"] - one * 3) < 1e-9 and free["multiplier_end"] == 4


def test_mw_multi_cascade_multiplier_grows() -> None:
    # every refill is ruby -> keeps cascading until MW_MAX_CASCADES; multiplier +1 each time
    o_board, o_pick = game.mw_board, game.mw_pick
    game.mw_board = lambda free=False: [["ruby"] * 2] + [["shard"] + ["ruby"] * 2 for _ in range(4)] + [["ruby"] * 2]
    game.mw_pick = lambda reel, top=False, free=False: "ruby" if not top else "shard"
    try:
        f = game.mw_play_one(0.1, free=True, mult=1)
    finally:
        game.mw_board, game.mw_pick = o_board, o_pick
    assert f["cascades"] == game.MW_MAX_CASCADES and f["multiplier_end"] == 1 + game.MW_MAX_CASCADES
    mults = [s["multiplier"] for s in f["stages"]]
    assert mults == list(range(1, len(mults) + 1))


def mw_rnd(base_raw: float, games: list[dict] = (), free: list[float] = ()) -> dict:
    def st(raw: float) -> dict:
        return {"kind": "spin", "mode": "megaways", "stages": [], "ways": 324, "cascades": 3, "scatters": 0,
                "scatter_pos": [], "scatter_win_aud": 0.0, "free_spins_awarded": 0, "multiplier": 1,
                "multiplier_end": 1, "raw_win_aud": raw}
    return {"mode": "megaways", "base": st(base_raw), "minigames": list(games), "free_spins": [st(r) for r in free]}


def pick_game(raw: float) -> dict:
    return {"kind": "pick", "picks": [{"prize_mult": raw, "win_aud": raw}, {"collect": True}], "decoys": [], "tiles": 12, "raw_win_aud": raw}


def wheel_game(index: int, raw: float, pending: bool = False, fallback: int = 10) -> dict:
    g = {"kind": "wheel", "wedges": game.WHEEL_WEDGES, "index": index, "free_spins": 0, "jackpot_pending": pending,
         "raw_win_aud": raw, "prize_mult": raw}
    if pending:
        g["fallback_index"] = fallback
    return g


def test_cascades_and_minigames_pay_in_full() -> None:
    fresh_db()
    pid = new_player(100)
    set_pool(999)  # + stake 1 -> 1000, far below these wins — still paid in full
    snap = ledger.settle_round(pid, 1, mw_rnd(50_000, [pick_game(50_000), wheel_game(7, 50_000)], [50_000, 50_000]),
                               "AUD", NO_JP, lambda s, p: False)
    paid = [s["paid_aud"] for s in snap["steps"]]
    assert paid == [50_000.0, 50_000.0, 50_000.0, 50_000.0, 50_000.0]
    assert all("cap_aud" not in s and not s.get("capped") for s in snap["steps"])
    assert snap["total_paid_aud"] == 250_000.0
    assert ledger.pool_status()["pool_aud"] >= 0


def test_jackpot_equals_fixed_multiple_megaways() -> None:
    fresh_db()
    pid = new_player(100)
    set_pool(49_999)
    snap = ledger.settle_round(pid, 1, mw_rnd(12.34), "AUD", JP)
    s0 = snap["steps"][0]
    prize = game.jackpot_amount(1)
    assert s0["paid_aud"] == 12.34 and s0["jackpot_aud"] == prize
    assert snap["jackpot_paid_aud"] == prize
    assert snap["total_paid_aud"] == round(12.34 + prize, 2)
    assert "cap_aud" not in s0


def test_wheel_jackpot_wedge_pays_fixed_multiple() -> None:
    fresh_db()
    pid = new_player(100)
    set_pool(19_999)
    snap = ledger.settle_round(pid, 1, mw_rnd(0.0, [wheel_game(11, 2.0, pending=True)]), "AUD", NO_JP, lambda s, p: True)
    w = snap["steps"][1]
    prize = game.jackpot_amount(1)
    assert w["kind"] == "wheel" and w["wheel_jackpot"] and w["wheel_index"] == 11
    assert w["paid_aud"] == 0 and w["jackpot_aud"] == prize
    # miss: ticks on to the neighbouring 2x wedge
    snap = ledger.settle_round(pid, 1, mw_rnd(0.0, [wheel_game(11, 2.0, pending=True, fallback=0)]), "AUD", NO_JP, lambda s, p: False)
    w = snap["steps"][1]
    assert not w["wheel_jackpot"] and w["wheel_index"] == 0 and w["paid_aud"] == 2.0 and w["jackpot_aud"] == 0


def test_wheel_jackpot_probability_is_fixed() -> None:
    assert game.wheel_jackpot_probability(0) == 0.0
    p = game.wheel_jackpot_probability(1)
    assert p == game.WHEEL_JP_P
    for pool in (0, 10, 1_000_000):
        assert game.wheel_jackpot_probability(1, pool) == p
    # EV if the jackpot wedge is already landed: p * 5000× bet
    assert abs(p * game.JACKPOT_MULT - (game.WHEEL_JP_P * game.JACKPOT_MULT)) < 1e-12


def test_minigame_shapes() -> None:
    for _ in range(500):
        p = game.play_pick(1.0)
        assert p["picks"][-1] == {"collect": True} and "collect" not in p["picks"][0]
        assert len(p["picks"]) + len(p["decoys"]) == p["tiles"]
        assert abs(p["raw_win_aud"] - sum(x.get("win_aud", 0) for x in p["picks"])) < 1e-9
        w = game.play_wheel(2.0)
        wedge = game.WHEEL_WEDGES[w["index"]]
        if wedge["type"] == "mult":
            assert w["raw_win_aud"] == 2.0 * wedge["value"]
        elif wedge["type"] == "free_spins":
            assert w["free_spins"] == wedge["value"] and w["raw_win_aud"] == 0
        else:
            assert w["jackpot_pending"] and game.WHEEL_WEDGES[w["fallback_index"]]["type"] == "mult"


def test_pool_never_negative_random_megaways() -> None:
    fresh_db()
    pid = new_player(10_000_000)
    for i in range(1500):
        stake = game._rng.choice(game.MW_BET_AUD)
        before = ledger.pool_status()["pool_aud"] + stake
        rnd = game.play_megaways(stake)
        if i % 50 == 0:
            rnd["minigames"].append(game.play_pick(stake))
            rnd["minigames"].append(game.play_wheel(stake))
        snap = ledger.settle_round(pid, stake, rnd, "AUD", JP if game._rng.random() < 0.05 else NO_JP,
                                   (lambda s, p: True) if game._rng.random() < 0.5 else (lambda s, p: False))
        assert len(snap["steps"]) == len(game.round_steps(rnd))
        for s in snap["steps"]:
            assert "cap_aud" not in s
            assert not s.get("capped")
        assert ledger.pool_status()["pool_aud"] >= 0




# ---- social casino: no cash-out, coin packs, free coins --------------------

def test_no_withdraw_route() -> None:
    fresh_db()
    os.environ.pop("STRIPE_SECRET_KEY", None)
    import app as app_module
    client = app_module.app.test_client()
    for path in (
        "/api/withdraw",
        "/api/deposit/play",
        "/api/deposit/checkout",
        "/api/prefs",
        "/deposit/success",
        "/deposit/cancel",
    ):
        for meth in ("get", "post"):
            r = getattr(client, meth)(path, json={})
            assert r.status_code == 404, (path, meth, r.status_code)


def test_coin_pack_checkout_credit_is_idempotent() -> None:
    fresh_db()
    pid = str(uuid.uuid4())
    ledger.ensure_player(pid)
    start = ledger.snapshot(pid)["coins"]
    assert start == game.STARTING_COINS
    pack = game.COIN_PACKS[0]
    ok, msg, snap = ledger.credit_coin_pack("cs_test_sess_1", pid, pack["id"], pack["coins"], pack["price_aud"])
    assert ok and "credit" in msg
    assert snap["coins"] == start + pack["coins"]
    ok2, msg2, snap2 = ledger.credit_coin_pack("cs_test_sess_1", pid, pack["id"], pack["coins"], pack["price_aud"])
    assert not ok2 and "already" in msg2.lower()
    assert snap2["coins"] == start + pack["coins"]
    # a second session can credit again
    ok3, _, snap3 = ledger.credit_coin_pack("cs_test_sess_2", pid, pack["id"], pack["coins"], pack["price_aud"])
    assert ok3 and snap3["coins"] == start + 2 * pack["coins"]
    # mismatched catalogue amount is rejected and does not credit
    try:
        ledger.credit_coin_pack("cs_test_bad", pid, pack["id"], pack["coins"] + 1, pack["price_aud"])
        raise AssertionError("mismatched pack should fail")
    except ValueError:
        assert ledger.snapshot(pid)["coins"] == start + 2 * pack["coins"]


def test_coins_never_convert_out() -> None:
    fresh_db()
    os.environ.pop("STRIPE_SECRET_KEY", None)
    import app as app_module
    client = app_module.app.test_client()
    assert not hasattr(ledger, "withdraw")
    assert not hasattr(ledger, "credit_play_money")
    r = client.get("/api/balance")
    assert r.status_code == 200
    body = r.get_json()
    assert isinstance(body["coins"], int) and body["coins"] == game.STARTING_COINS
    assert "balances" not in body
    assert "total_aud" not in body
    assert "display_currency" not in body
    text = r.get_data(as_text=True)
    for banned in ("withdraw", "cash-out", "cash_out", "payout_aud", "USDT", "BTC"):
        assert banned not in text, banned
    # no conversion / redeem endpoint
    for path in ("/api/redeem", "/api/cashout", "/api/exchange", "/api/withdraw"):
        assert client.post(path, json={"coins": 1000}).status_code == 404
    # official pack catalogue is purchase-only; coins are not priced as cash on the way out
    packs = body["config"]["packs"]
    assert len(packs) == 4
    assert all(p["coins"] > 0 and p["price_cents"] > 0 and p["currency"] == "AUD" for p in packs)
    legal = body["config"]["legal"]
    assert "no monetary value" in legal.lower()
    assert "cannot be redeemed" in legal.lower()
    # daily + hourly free coins work and never debit a cash account
    d = client.post("/api/bonus/daily")
    assert d.status_code == 200, d.get_data(as_text=True)
    dj = d.get_json()
    assert dj["awarded"] == game.DAILY_COINS
    assert dj["coins"] == game.STARTING_COINS + game.DAILY_COINS
    assert client.post("/api/bonus/daily").status_code == 429
    h = client.post("/api/bonus/hourly")
    assert h.status_code == 200
    assert h.get_json()["awarded"] == game.HOURLY_COINS
    assert client.post("/api/bonus/hourly").status_code == 429

# ---- in-game prizes (virtual only) -----------------------------------------

import prizes  # noqa: E402


def test_trophy_unlock() -> None:
    fresh_db()
    pid = new_player(200)
    set_pool(100000)
    # Green Tea Jackpot
    snap = ledger.settle_round(pid, 1, rnd(0), "COIN", jackpot_roll=JP)
    ids = set(snap["trophies"]["unlocked"])
    assert "greentea_jackpot" in ids
    names = {t["id"] for t in snap["trophies"]["new"]}
    assert "greentea_jackpot" in names
    # second jackpot does not re-announce as a new unlock if already owned —
    # still in unlocked, and new list may be empty
    snap2 = ledger.settle_round(pid, 1, rnd(0), "COIN", jackpot_roll=JP)
    assert "greentea_jackpot" in snap2["trophies"]["unlocked"]
    assert "greentea_jackpot" not in {t["id"] for t in snap2["trophies"]["new"]}
    # Big / Mega / Epic from win multiple (uncapped; large pool)
    pid2 = new_player(400)
    set_pool(100000)
    big = ledger.settle_round(pid2, 1, rnd(20), "COIN", jackpot_roll=NO_JP)
    assert "big_win" in big["trophies"]["unlocked"]
    assert "mega_win" not in big["trophies"]["unlocked"]
    mega = ledger.settle_round(pid2, 1, rnd(60), "COIN", jackpot_roll=NO_JP)
    assert "mega_win" in mega["trophies"]["unlocked"]
    epic = ledger.settle_round(pid2, 1, rnd(160), "COIN", jackpot_roll=NO_JP)
    assert "epic_win" in epic["trophies"]["unlocked"]
    # Free-spin trigger
    pid3 = new_player(100)
    set_pool(100000)
    r = rnd(0, free=[0, 0, 0, 0, 0, 0, 0, 0])
    r["base"]["free_spins_awarded"] = 8
    fs = ledger.settle_round(pid3, 1, r, "COIN", jackpot_roll=NO_JP)
    assert "free_spins" in fs["trophies"]["unlocked"]
    # Mini games
    r2 = rnd(0)
    r2["minigames"] = [{"kind": "pick", "picks": [], "decoys": [], "tiles": 12, "raw_win_aud": 5.0}]
    pk = ledger.settle_round(pid3, 1, r2, "COIN", jackpot_roll=NO_JP)
    assert "crystal_pick" in pk["trophies"]["unlocked"]
    r3 = rnd(0)
    r3["minigames"] = [{"kind": "wheel", "wedges": [], "index": 0, "raw_win_aud": 2.0, "jackpot_pending": False}]
    wh = ledger.settle_round(pid3, 1, r3, "COIN", jackpot_roll=NO_JP)
    assert "tea_wheel" in wh["trophies"]["unlocked"]
    # Level milestone
    prizes.debug_set_level(pid3, 5)
    assert "level_5" in prizes.unlocked_ids(pid3)
    # Streak of 5 wins
    pid4 = new_player(200)
    set_pool(100000)
    for _ in range(5):
        st = ledger.settle_round(pid4, 1, rnd(1), "COIN", jackpot_roll=NO_JP)
    assert "streak_5" in st["trophies"]["unlocked"]
    assert st["profile"]["current_streak"] == 5


def test_mission_progress_and_claim_once() -> None:
    fresh_db()
    pid = new_player(400)
    set_pool(100000)
    day = prizes.perth_date()
    prizes.ensure_daily_missions(pid, day, ids=["spin_25", "win_10x", "trigger_fs"])
    start = ledger.snapshot(pid)["coins"]
    # one spin advances spin_25 only
    ledger.settle_round(pid, 1, rnd(0), "COIN", jackpot_roll=NO_JP)
    state = {m["id"]: m for m in prizes.mission_state(pid, day)}
    assert state["spin_25"]["progress"] == 1
    assert state["win_10x"]["progress"] == 0
    assert not state["spin_25"]["claimable"]
    try:
        prizes.claim_mission(pid, "spin_25", day)
        raise AssertionError("incomplete mission should not claim")
    except prizes.MissionUnavailable:
        pass
    after_spin = ledger.snapshot(pid)["coins"]
    assert after_spin == start - game.to_coins(1)
    # finish win_10x in one hit
    ledger.settle_round(pid, 1, rnd(12), "COIN", jackpot_roll=NO_JP)
    state = {m["id"]: m for m in prizes.mission_state(pid, day)}
    assert state["win_10x"]["complete"] and state["win_10x"]["claimable"]
    before_claim = ledger.snapshot(pid)["coins"]
    snap = prizes.claim_mission(pid, "win_10x", day)
    assert snap["awarded"] == 5000
    assert snap["coins"] == before_claim + 5000
    try:
        prizes.claim_mission(pid, "win_10x", day)
        raise AssertionError("mission must be claim-once")
    except prizes.MissionUnavailable as exc:
        assert "already" in str(exc).lower()
    assert ledger.snapshot(pid)["coins"] == before_claim + 5000
    # trigger free spins mission
    r = rnd(0, free=[0, 0])
    r["base"]["free_spins_awarded"] = 2
    ledger.settle_round(pid, 1, r, "COIN", jackpot_roll=NO_JP)
    state = {m["id"]: m for m in prizes.mission_state(pid, day)}
    assert state["trigger_fs"]["complete"]
    # API claim-once
    os.environ.pop("STRIPE_SECRET_KEY", None)
    import app as app_module
    client = app_module.app.test_client()
    # bind this temp db player via cookie? easier to claim remaining via ledger.
    claimed = prizes.claim_mission(pid, "trigger_fs", day)
    assert claimed["awarded"] == 5000
    # public snapshot still hides the pool
    body = ledger.snapshot(pid)
    assert "pool" not in str(body["missions"])
    assert "cap" not in str(body["trophies"])


def test_leaderboard_ordering_and_nickname_sanitising() -> None:
    fresh_db()
    set_pool(100000)
    a, b, c = new_player(500), new_player(500), new_player(500)
    prizes.set_nickname(a, "  Alpha Star  ")
    prizes.set_nickname(b, "Bravo")
    prizes.set_nickname(c, "Charlie")
    # a: one huge win; b: several medium; c: small
    ledger.settle_round(a, 1, rnd(80), "COIN", jackpot_roll=NO_JP)
    for _ in range(5):
        ledger.settle_round(b, 1, rnd(20), "COIN", jackpot_roll=NO_JP)
    ledger.settle_round(c, 1, rnd(5), "COIN", jackpot_roll=NO_JP)
    day = prizes.perth_date()
    biggest = prizes.leaderboard("daily", "biggest", day, viewer_id=a)
    assert [e["nickname"] for e in biggest["entries"][:3]] == ["Alpha Star", "Bravo", "Charlie"]
    assert biggest["entries"][0]["score"] == game.to_coins(80)
    assert biggest["me"]["place"] == 1
    total = prizes.leaderboard("daily", "total", day, viewer_id=b)
    assert total["entries"][0]["nickname"] == "Bravo"
    assert total["entries"][0]["score"] == game.to_coins(100)
    assert total["me"]["place"] == 1
    weekly = prizes.leaderboard("weekly", "biggest")
    assert weekly["entries"][0]["nickname"] == "Alpha Star"

    # sanitising
    assert prizes.sanitize_nickname("  Good  Name!! ") == "Good Name"
    assert prizes.sanitize_nickname("<script>Bob</script>") == "Bob"
    assert len(prizes.sanitize_nickname("A" * 40)) == 16
    try:
        prizes.sanitize_nickname("fuck")
        raise AssertionError("profanity should be rejected")
    except ValueError:
        pass
    try:
        prizes.set_nickname(a, "shithead")
        raise AssertionError("profane nickname should be rejected")
    except ValueError:
        pass
    assert prizes.profile_public(a)["nickname"] == "Alpha Star"
    try:
        prizes.sanitize_nickname("x")
        raise AssertionError("too short")
    except ValueError:
        pass
    # closed-period payouts are idempotent and grant coins + badge
    before = ledger.snapshot(a)["coins"]
    paid = prizes.settle_leaderboard("daily", day, "biggest")
    assert any(p["player_id"] == a and p["place"] == 1 and p["coins"] == 25000 for p in paid)
    assert "lb_daily_gold" in prizes.unlocked_ids(a)
    assert ledger.snapshot(a)["coins"] == before + 25000
    paid2 = prizes.settle_leaderboard("daily", day, "biggest")
    assert paid2 == []
    assert ledger.snapshot(a)["coins"] == before + 25000

    # API
    os.environ.pop("STRIPE_SECRET_KEY", None)
    import app as app_module
    client = app_module.app.test_client()
    r = client.post("/api/profile", json={"nickname": "NiceOne"})
    assert r.status_code == 200
    assert r.get_json()["profile"]["nickname"] == "NiceOne"
    bad = client.post("/api/profile", json={"nickname": "fuckyou"})
    assert bad.status_code == 400
    lb = client.get("/api/leaderboard?period=daily&board=biggest")
    assert lb.status_code == 200
    body = lb.get_data(as_text=True)
    for k in ("pool", "max_win", "cap_aud"):
        assert k not in body


def test_themes_locked_until_level() -> None:
    fresh_db()
    pid = new_player(50)
    themes = {t["id"]: t for t in prizes.themes_public(pid)}
    assert themes["crystal"]["unlocked"] and themes["crystal"]["selected"]
    assert not themes["ruby"]["unlocked"]
    assert not themes["jade"]["unlocked"]
    assert not themes["sapphire"]["unlocked"]
    try:
        prizes.set_theme(pid, "ruby")
        raise AssertionError("ruby should be locked at level 1")
    except prizes.ThemeLocked:
        pass
    assert prizes.profile_public(pid)["theme"] == "crystal"
    prizes.debug_set_level(pid, 2)
    prizes.set_theme(pid, "ruby")
    assert prizes.profile_public(pid)["theme"] == "ruby"
    themes = {t["id"]: t for t in prizes.themes_public(pid)}
    assert themes["ruby"]["unlocked"] and themes["ruby"]["selected"]
    assert not themes["jade"]["unlocked"]
    try:
        prizes.set_theme(pid, "jade")
        raise AssertionError("jade should stay locked")
    except prizes.ThemeLocked:
        pass
    prizes.debug_set_level(pid, 5)
    prizes.set_theme(pid, "jade")
    assert prizes.profile_public(pid)["theme"] == "jade"
    prizes.debug_set_level(pid, 8)
    prizes.set_theme(pid, "sapphire")
    assert prizes.profile_public(pid)["theme"] == "sapphire"

    os.environ.pop("STRIPE_SECRET_KEY", None)
    import app as app_module
    client = app_module.app.test_client()
    locked = client.post("/api/theme", json={"theme": "ruby"})
    assert locked.status_code == 403
    ok = client.post("/api/theme", json={"theme": "crystal"})
    assert ok.status_code == 200
    assert ok.get_json()["profile"]["theme"] == "crystal"
    # no cap leak
    for path in ("/api/balance", "/api/config"):
        text = client.get(path).get_data(as_text=True)
        for k in ("pool", "max_win", "cap_aud", "cap_fraction"):
            assert k not in text, (path, k)


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print(f"{len(tests)} tests passed")
