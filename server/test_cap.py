#!/usr/bin/env python3
"""Unit-style checks for the 20%-of-pool payout cap (uses a temp SQLite DB)."""

from __future__ import annotations

import sys
import tempfile
import uuid
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))

import game  # noqa: E402
import ledger  # noqa: E402


def fresh_db() -> None:
    tmp = Path(tempfile.mkdtemp()) / "t.db"
    ledger.DB_PATH = tmp
    ledger._local.conn = None
    ledger.init_db()


def fund(pid: str, aud: float) -> None:
    ledger.ensure_player(pid)
    with ledger.transaction() as c:
        c.execute("UPDATE balances SET amount = ? WHERE player_id = ? AND asset = 'AUD'", (aud, pid))


def fake_round(raw_base: float, free: list[float] = (), jackpot: bool = False) -> dict:
    def step(raw, mult=1):
        grid = [["shard"] * 3 for _ in range(5)]
        return {"grid": grid, "line": game.evaluate_line(grid, 1), "scatters": 0, "scatter_pos": [],
                "scatter_win_aud": 0.0, "free_spins_awarded": 0, "multiplier": mult, "raw_win_aud": raw}
    return {"base": step(raw_base), "free_spins": [step(r, 2) for r in free], "jackpot_hit": jackpot}


def set_house(pool: float, meter: float = 0.0) -> None:
    with ledger.transaction() as c:
        c.execute("UPDATE house SET pool_aud = ?, jackpot_aud = ? WHERE id = 1", (pool, meter))


def test_empty_pool_tiny_bet() -> None:
    fresh_db()
    pid = str(uuid.uuid4())
    fund(pid, 10)
    snap = ledger.settle_round(pid, 0.5, fake_round(250.0), "AUD")  # 500× win on 0.50 bet
    # Pool after stake = 0.50 -> cap = 0.10
    assert snap["total_paid_aud"] == 0.10, snap["total_paid_aud"]
    assert snap["any_capped"]
    assert abs(snap["pool"]["pool_aud"] - 0.40) < 1e-9, snap["pool"]
    assert abs(snap["balances"]["AUD"] - 9.60) < 1e-9, snap["balances"]


def test_example_100k() -> None:
    fresh_db()
    pid = str(uuid.uuid4())
    fund(pid, 1000)
    set_house(100_000 - 100)  # + 100 stake = 100,000
    snap = ledger.settle_round(pid, 100, fake_round(50_000.0), "AUD")
    assert snap["total_paid_aud"] == 20_000.0, snap["total_paid_aud"]
    assert snap["pool"]["pool_aud"] == 80_000.0


def test_uncapped_small_win() -> None:
    fresh_db()
    pid = str(uuid.uuid4())
    fund(pid, 100)
    set_house(10_000)
    snap = ledger.settle_round(pid, 1, fake_round(4.0), "AUD")
    assert snap["total_paid_aud"] == 4.0 and not snap["any_capped"]


def test_free_spins_and_jackpot_capped_each_step() -> None:
    fresh_db()
    pid = str(uuid.uuid4())
    fund(pid, 100)
    set_house(99, meter=50)  # pool 100 after stake
    snap = ledger.settle_round(pid, 1, fake_round(10.0, [1000.0, 1000.0, 1000.0], jackpot=True), "AUD")
    pool = 100.0
    expected = 0.0
    # base: line 10 (cap 20) + jackpot min(meter 50.01, 10 remaining) = 20
    for raw, is_base in [(10.0, True), (1000.0, False), (1000.0, False), (1000.0, False)]:
        cap = game.cap_for_pool(pool)
        paid = cap if is_base else min(raw, cap)
        pool -= paid
        expected += paid
    assert abs(snap["total_paid_aud"] - round(expected, 2)) < 0.011, (snap["total_paid_aud"], expected)
    for s in snap["steps"]:
        assert s["paid_aud"] + s["jackpot_aud"] <= s["cap_aud"] + 1e-9
    assert snap["pool"]["pool_aud"] > 0


def test_pool_never_negative_random() -> None:
    fresh_db()
    pid = str(uuid.uuid4())
    fund(pid, 1_000_000)
    for _ in range(3000):
        bet = game._rng.choice(game.BET_STEPS_AUD)
        rnd = game.play_round(bet)
        before = ledger.pool_status()["pool_aud"] + bet
        snap = ledger.settle_round(pid, bet, rnd, "AUD")
        for s in snap["steps"]:
            assert s["paid_aud"] + s["jackpot_aud"] <= s["cap_aud"] + 1e-9
            assert s["cap_aud"] <= 0.2 * before + 1e-9
        assert snap["pool"]["pool_aud"] >= 0
        assert snap["pool"]["jackpot_aud"] <= snap["pool"]["max_win_aud"] + 1e-9


def test_zero_pool_cap() -> None:
    assert game.cap_for_pool(0) == 0.0
    assert game.cap_for_pool(-5) == 0.0
    assert game.cap_for_pool(100_000) == 20_000.0
    assert game.cap_for_pool(0.04) == 0.0  # under a cent


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print(f"{len(tests)} tests passed")
