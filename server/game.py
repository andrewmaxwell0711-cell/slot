"""Shared slot rules: symbols, demo FX rates, RNG, payline + feature evaluation.

Every outcome is decided here on the server with secrets.SystemRandom; the
browser only animates the result it is sent. Raw wins computed here are
later clamped by the ledger to the house-pool cap (see ledger.py).
"""

from __future__ import annotations

import secrets
from typing import Any

REEL_COUNT = 5
VISIBLE_ROWS = 3

# Crystal theme. The line paytable (× bet) is the same as the 20% RTP build,
# mapped onto gems (cherry->rose quartz ... diamond->Green Tea, the top symbol). Feature
# symbols: Crystal WILD, Prism SCATTER (free spins) and a non-paying Ice
# Shard. Weights were tuned with simulate_rtp.py so the total long-run
# return, including free spins and the progressive jackpot, stays ~20%.
SYMBOLS = [
    {"id": "quartz", "name": "Rose Quartz", "emoji": "🩷", "weight": 22, "pays": {3: 4, 4: 10, 5: 20}},
    {"id": "citrine", "name": "Citrine", "emoji": "💛", "weight": 20, "pays": {3: 4, 4: 10, 5: 20}},
    {"id": "topaz", "name": "Topaz", "emoji": "🧡", "weight": 18, "pays": {3: 6, 4: 16, 5: 40}},
    {"id": "amethyst", "name": "Amethyst", "emoji": "💜", "weight": 16, "pays": {3: 6, 4: 16, 5: 50}},
    {"id": "emerald", "name": "Emerald", "emoji": "💚", "weight": 12, "pays": {3: 10, 4: 30, 5: 80}},
    {"id": "sapphire", "name": "Sapphire", "emoji": "💙", "weight": 8, "pays": {3: 15, 4: 50, 5: 100}},
    {"id": "ruby", "name": "Ruby", "emoji": "❤️", "weight": 5, "pays": {3: 25, 4: 80, 5: 200}},
    # Top symbol: glowing Green Tea crystal cup (takes the old diamond slot/pays).
    {"id": "greentea", "name": "Green Tea", "emoji": "🍵", "weight": 3, "pays": {3: 50, 4: 150, 5: 500}},
    # Crystal WILD: reels 2-4 only, substitutes on the payline, doubles the line win.
    {"id": "wild", "name": "Crystal Wild", "emoji": "🔮", "weight": 1, "pays": {3: 50, 4: 150, 5: 1000},
     "wild": True, "reels": (1, 2, 3)},
    # Prism SCATTER: 3+ anywhere pays and triggers free spins.
    {"id": "scatter", "name": "Prism Scatter", "emoji": "🌈", "weight": 3, "pays": {}, "scatter": True},
    # Non-paying ice shard (like a classic blank) that keeps the total RTP at ~20%.
    {"id": "shard", "name": "Ice Shard", "emoji": "❄️", "weight": 19, "pays": {}, "blank": True},
]

WILD_ID = "wild"
SCATTER_ID = "scatter"
WILD_MULT = 2  # any line win that uses a wild is doubled

# Scatter count anywhere on the 5×3 grid -> (pay × bet, free spins awarded)
SCATTER_PAYS = {3: (2, 8), 4: (5, 12), 5: (20, 20)}
FREE_SPIN_MULT = 2  # every win during free spins is doubled
MAX_FREE_SPINS = 50  # retrigger ceiling per bonus round

# Green Tea Jackpot: when it hits, the spin pays the full cap (20% of the
# house pool at that moment). To keep long-run RTP fixed however big the
# pool grows, hit chance = JACKPOT_C * total_bet / pool, so the expected
# jackpot return per A$1 staked is JACKPOT_C * 0.20 (~4%). The chance is
# capped at JACKPOT_MAX_P so a tiny pool can't make it near-certain.
JACKPOT_C = 0.20
JACKPOT_MAX_P = 1 / 1_000

# 25 standard casino paylines over the 5x3 grid (row per reel: 0 top, 1 mid, 2 bottom).
PAYLINES = [
    (1, 1, 1, 1, 1), (0, 0, 0, 0, 0), (2, 2, 2, 2, 2), (0, 1, 2, 1, 0), (2, 1, 0, 1, 2),
    (0, 0, 1, 2, 2), (2, 2, 1, 0, 0), (1, 0, 0, 0, 1), (1, 2, 2, 2, 1), (0, 1, 1, 1, 0),
    (2, 1, 1, 1, 2), (1, 0, 1, 2, 1), (1, 2, 1, 0, 1), (0, 1, 0, 1, 0), (2, 1, 2, 1, 2),
    (1, 1, 0, 1, 1), (1, 1, 2, 1, 1), (0, 0, 2, 0, 0), (2, 2, 0, 2, 2), (0, 2, 0, 2, 0),
    (2, 0, 2, 0, 2), (1, 0, 2, 0, 1), (1, 2, 0, 2, 1), (0, 2, 2, 2, 0), (2, 0, 0, 0, 2),
]
LINE_OPTIONS = [1, 5, 10, 20, 25]
BET_PER_LINE_AUD = [0.02, 0.05, 0.1, 0.2, 0.4, 1, 2, 4]  # max bet 25 x 4 = A$100

# Gamble / double-up (50/50 card colour), at most this many doubles in a row.
GAMBLE_MAX_ROUNDS = 5
SUITS = (("hearts", "red"), ("diamonds", "red"), ("clubs", "black"), ("spades", "black"))
RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")

# No single spin may pay more than this fraction of the house pool.
POOL_CAP_FRACTION = 0.20

# Illustrative demo rates only — not live market prices.
RATES_TO_AUD = {
    "AUD": 1.0,
    "USD": 1.52,
    "EUR": 1.65,
    "BTC": 145000.0,
    "ETH": 5200.0,
    "USDT": 1.52,
    "SOL": 280.0,
}

FIAT = ("AUD", "USD", "EUR")
CRYPTO = ("BTC", "ETH", "USDT", "SOL")
ALL_ASSETS = FIAT + CRYPTO

_rng = secrets.SystemRandom()
BLANK_ID = "shard"


def _reel_table(reel: int) -> tuple[list[dict[str, Any]], float]:
    syms = [s for s in SYMBOLS if reel in s.get("reels", range(REEL_COUNT))]
    return syms, float(sum(s["weight"] for s in syms))


_REEL_TABLES = [_reel_table(r) for r in range(REEL_COUNT)]


def to_aud(asset: str, amount: float) -> float:
    return amount * (RATES_TO_AUD.get(asset) or 1.0)


def from_aud(asset: str, aud_amount: float) -> float:
    return aud_amount / (RATES_TO_AUD.get(asset) or 1.0)


def total_aud(balances: dict[str, float]) -> float:
    return sum(to_aud(a, balances.get(a, 0.0) or 0.0) for a in ALL_ASSETS)


def clean_amount(asset: str, amount: float) -> float:
    if amount < 1e-12:
        return 0.0
    if asset in FIAT or asset == "USDT":
        return round(amount, 2)
    return round(amount, 8)


def symbol_by_id(symbol_id: str) -> dict[str, Any]:
    for symbol in SYMBOLS:
        if symbol["id"] == symbol_id:
            return symbol
    return SYMBOLS[0]


def weighted_pick(reel: int = 0) -> dict[str, Any]:
    syms, total = _REEL_TABLES[reel]
    r = _rng.random() * total
    for symbol in syms:
        r -= symbol["weight"]
        if r <= 0:
            return symbol
    return SYMBOLS[0]


def spin_grid() -> list[list[str]]:
    """Return a 5-column grid; each column is [top, mid/payline, bottom] symbol ids."""
    return [[weighted_pick(c)["id"] for _ in range(VISIBLE_ROWS)] for c in range(REEL_COUNT)]


def evaluate_payline(symbols: list[str]) -> tuple[int, str | None, bool]:
    """Left-to-right run on one line. Returns (count, paying symbol id, used_wild)."""
    target = None
    count = 0
    used_wild = False
    for sid in symbols:
        if sid in (SCATTER_ID, BLANK_ID):
            break
        if sid == WILD_ID:
            count += 1
            used_wild = True
            continue
        if target is None:
            target = sid
            count += 1
        elif sid == target:
            count += 1
        else:
            break
    if count < 3:
        return 0, None, False
    return count, (WILD_ID if target is None else target), used_wild and target is not None


def evaluate_lines(grid: list[list[str]], bet_per_line: float, lines: int) -> list[dict[str, Any]]:
    """All winning paylines among the first `lines` active lines."""
    wins = []
    for idx in range(lines):
        rows = PAYLINES[idx]
        symbols = [grid[c][rows[c]] for c in range(REEL_COUNT)]
        count, sid, wild = evaluate_payline(symbols)
        if not count:
            continue
        sym = symbol_by_id(sid)
        mult = sym["pays"].get(count, 0) * (WILD_MULT if wild else 1)
        if mult <= 0:
            continue
        wins.append({
            "line": idx + 1,
            "count": count,
            "symbol": sid,
            "mult": mult,
            "wild": wild,
            "win_aud": round(bet_per_line * mult, 8),
            "cells": [[c, rows[c]] for c in range(count)],
        })
    return wins


def count_scatters(grid: list[list[str]]) -> int:
    return sum(1 for col in grid for sid in col if sid == SCATTER_ID)


def scatter_positions(grid: list[list[str]]) -> list[list[int]]:
    return [[c, r] for c, col in enumerate(grid) for r, sid in enumerate(col) if sid == SCATTER_ID]


def play_one(bet_per_line: float, lines: int, multiplier: int = 1) -> dict[str, Any]:
    """One spin's grid and RAW (uncapped) win, before the pool cap is applied."""
    grid = spin_grid()
    total_bet = bet_per_line * lines
    line_wins = evaluate_lines(grid, bet_per_line, lines)
    scatters = count_scatters(grid)
    scatter_mult, free_spins = SCATTER_PAYS.get(min(scatters, 5), (0, 0))
    scatter_win = total_bet * scatter_mult  # scatter pays on the total bet
    for w in line_wins:
        w["win_aud"] = round(w["win_aud"] * multiplier, 8)
    raw = sum(w["win_aud"] for w in line_wins) + scatter_win * multiplier
    return {
        "grid": grid,
        "line_wins": line_wins,
        "scatters": scatters,
        "scatter_pos": scatter_positions(grid),
        "scatter_win_aud": round(scatter_win * multiplier, 8),
        "free_spins_awarded": free_spins,
        "multiplier": multiplier,
        "raw_win_aud": round(raw, 8),
    }


def play_round(bet_per_line: float, lines: int) -> dict[str, Any]:
    """Paid spin plus any free-spin bonus it triggers (same lines and bet).

    The jackpot roll needs the live pool, so the ledger does it inside the
    settlement transaction via jackpot_roll().
    """
    base = play_one(bet_per_line, lines, 1)
    free: list[dict[str, Any]] = []
    remaining = base["free_spins_awarded"]
    total_awarded = remaining
    while remaining > 0:
        remaining -= 1
        fs = play_one(bet_per_line, lines, FREE_SPIN_MULT)
        if fs["free_spins_awarded"]:
            extra = max(0, min(fs["free_spins_awarded"], MAX_FREE_SPINS - total_awarded))
            fs["free_spins_awarded"] = extra
            remaining += extra
            total_awarded += extra
        free.append(fs)
    return {"base": base, "free_spins": free}


def jackpot_probability(total_bet: float, pool_aud: float) -> float:
    if pool_aud <= 0 or total_bet <= 0:
        return 0.0
    return min(JACKPOT_MAX_P, JACKPOT_C * total_bet / pool_aud)


def jackpot_roll(total_bet: float, pool_aud: float) -> bool:
    return _rng.random() < jackpot_probability(total_bet, pool_aud)


def draw_card() -> dict[str, str]:
    suit, colour = _rng.choice(SUITS)
    return {"rank": _rng.choice(RANKS), "suit": suit, "colour": colour}


def cap_for_pool(pool_aud: float) -> float:
    """Max single-spin payout for a pool, rounded down to the cent, never < 0."""
    if pool_aud <= 0:
        return 0.0
    return int(pool_aud * POOL_CAP_FRACTION * 100 + 1e-9) / 100.0
