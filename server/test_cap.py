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
        snap = ledger.settle_round(pid, total, game.play_classic(bpl, lines), "AUD",
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
    assert m["mode"] == "megaways" and m["bet_aud"] == 1 and m["base"]["stages"] and m["base"]["ways"] >= 324
    j = json.loads(bodies[1])
    assert j["bet_aud"] == 2.5 and j["lines"] == 25


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


def test_cap_across_cascades_and_minigames() -> None:
    fresh_db()
    pid = new_player(100)
    set_pool(999)  # + stake 1 -> 1000
    snap = ledger.settle_round(pid, 1, mw_rnd(50_000, [pick_game(50_000), wheel_game(7, 50_000)], [50_000, 50_000]),
                               "AUD", NO_JP, lambda s, p: False)
    caps = [s["cap_aud"] for s in snap["steps"]]
    paid = [s["paid_aud"] for s in snap["steps"]]
    assert caps[0] == 200.0 and paid[0] == 200.0              # base spin incl. all cascades
    assert caps[1] == 160.0 and paid[1] == 160.0              # Crystal Pick capped on the reduced pool
    assert caps[2] == 128.0 and paid[2] == 128.0              # Tea Wheel
    assert all(p <= c + 1e-9 for p, c in zip(paid, caps)) and all(s["capped"] for s in snap["steps"])
    assert ledger.pool_status()["pool_aud"] >= 0
    assert abs(snap["total_paid_aud"] - sum(paid)) < 1e-6


def test_jackpot_equals_cap_megaways() -> None:
    fresh_db()
    pid = new_player(100)
    set_pool(49_999)
    snap = ledger.settle_round(pid, 1, mw_rnd(12.34), "AUD", JP)
    s0 = snap["steps"][0]
    assert s0["cap_aud"] == 10_000.0 and s0["paid_aud"] + s0["jackpot_aud"] == 10_000.0
    assert snap["jackpot_paid_aud"] == round(10_000.0 - 12.34, 2)


def test_wheel_jackpot_wedge_pays_cap() -> None:
    fresh_db()
    pid = new_player(100)
    set_pool(19_999)
    snap = ledger.settle_round(pid, 1, mw_rnd(0.0, [wheel_game(11, 2.0, pending=True)]), "AUD", NO_JP, lambda s, p: True)
    w = snap["steps"][1]
    assert w["kind"] == "wheel" and w["wheel_jackpot"] and w["wheel_index"] == 11
    assert w["paid_aud"] == 0 and w["jackpot_aud"] == w["cap_aud"] == 4000.0
    # miss: ticks on to the neighbouring 2x wedge
    snap = ledger.settle_round(pid, 1, mw_rnd(0.0, [wheel_game(11, 2.0, pending=True, fallback=0)]), "AUD", NO_JP, lambda s, p: False)
    w = snap["steps"][1]
    assert not w["wheel_jackpot"] and w["wheel_index"] == 0 and w["paid_aud"] == 2.0 and w["jackpot_aud"] == 0


def test_wheel_jackpot_probability_bounded_ev() -> None:
    assert game.wheel_jackpot_probability(1, 0) == 0.0
    assert game.wheel_jackpot_probability(1, 10) == 1.0
    for pool in (10_000, 1_000_000):
        ev = game.wheel_jackpot_probability(1, pool) * game.cap_for_pool(pool)
        assert abs(ev - game.WHEEL_JP_K * game.POOL_CAP_FRACTION) < 1e-2


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
            assert s["paid_aud"] + s["jackpot_aud"] <= s["cap_aud"] + 1e-9
            assert s["cap_aud"] <= 0.2 * before + 1e-6
        assert ledger.pool_status()["pool_aud"] >= 0


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print(f"{len(tests)} tests passed")
