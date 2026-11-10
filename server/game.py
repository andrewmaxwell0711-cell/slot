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
    {"id": "shard", "name": "Ice Shard", "emoji": "❄️", "weight": 13, "pays": {}, "blank": True},
]

WILD_ID = "wild"
SCATTER_ID = "scatter"
WILD_MULT = 2  # any line win that uses a wild is doubled

# Scatter count anywhere on the 5×3 grid -> (pay × bet, free spins awarded)
SCATTER_PAYS = {3: (2, 8), 4: (5, 12), 5: (20, 20)}
FREE_SPIN_MULT = 2  # every win during free spins is doubled
MAX_FREE_SPINS = 50  # retrigger ceiling per bonus round

# Progressive jackpot: this slice of every stake feeds the meter (it stays
# part of the house pool). Chance to hit scales with the bet size.
JACKPOT_CONTRIB = 0.01
JACKPOT_HIT_PER_AUD = 1 / 50_000  # A$1 bet -> 1 in 50,000; A$100 -> 1 in 500

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
BET_STEPS_AUD = [0.5, 1, 2, 5, 10, 20, 50, 100]

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


def evaluate_line(grid: list[list[str]], bet_aud: float) -> dict[str, Any]:
    """Left-to-right run on the centre payline; wilds substitute, scatters break."""
    line = [col[1] for col in grid]
    target = None
    count = 0
    used_wild = False
    for sid in line:
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
        return {"win_aud": 0.0, "count": 0, "symbol": None, "mult": 0, "wild": False, "line": line}
    pure_wild = target is None
    symbol = symbol_by_id(WILD_ID if pure_wild else target)
    mult = symbol["pays"].get(count, 0)
    wild_mult = WILD_MULT if (used_wild and not pure_wild) else 1
    return {
        "win_aud": round(bet_aud * mult * wild_mult, 8),
        "count": count,
        "symbol": {"id": symbol["id"], "emoji": symbol["emoji"], "name": symbol["name"]},
        "mult": mult * wild_mult,
        "wild": used_wild,
        "line": line,
    }


# Backwards-compatible name used by older scripts.
evaluate_win = evaluate_line


def count_scatters(grid: list[list[str]]) -> int:
    return sum(1 for col in grid for sid in col if sid == SCATTER_ID)


def scatter_positions(grid: list[list[str]]) -> list[list[int]]:
    return [[c, r] for c, col in enumerate(grid) for r, sid in enumerate(col) if sid == SCATTER_ID]


def play_one(bet_aud: float, multiplier: int = 1) -> dict[str, Any]:
    """One spin's grid and RAW (uncapped) win, before the pool cap is applied."""
    grid = spin_grid()
    line = evaluate_line(grid, bet_aud)
    scatters = count_scatters(grid)
    scatter_mult, free_spins = SCATTER_PAYS.get(min(scatters, 5), (0, 0))
    scatter_win = round(bet_aud * scatter_mult, 8)
    raw = (line["win_aud"] + scatter_win) * multiplier
    return {
        "grid": grid,
        "line": line,
        "scatters": scatters,
        "scatter_pos": scatter_positions(grid),
        "scatter_win_aud": scatter_win * multiplier,
        "free_spins_awarded": free_spins,
        "multiplier": multiplier,
        "raw_win_aud": round(raw, 8),
    }


def play_round(bet_aud: float) -> dict[str, Any]:
    """Paid spin plus any free-spin bonus it triggers, and the jackpot roll.

    Everything is decided up front so the ledger can apply stake, caps and
    credits in one atomic transaction.
    """
    base = play_one(bet_aud, 1)
    free: list[dict[str, Any]] = []
    remaining = base["free_spins_awarded"]
    total_awarded = remaining
    while remaining > 0:
        remaining -= 1
        fs = play_one(bet_aud, FREE_SPIN_MULT)
        if fs["free_spins_awarded"]:
            extra = min(fs["free_spins_awarded"], MAX_FREE_SPINS - total_awarded)
            fs["free_spins_awarded"] = max(0, extra)
            remaining += fs["free_spins_awarded"]
            total_awarded += fs["free_spins_awarded"]
        free.append(fs)
    jackpot_hit = _rng.random() < min(1.0, bet_aud * JACKPOT_HIT_PER_AUD)
    return {"base": base, "free_spins": free, "jackpot_hit": jackpot_hit}


def cap_for_pool(pool_aud: float) -> float:
    """Max single-spin payout for a pool, rounded down to the cent, never < 0."""
    if pool_aud <= 0:
        return 0.0
    return int(pool_aud * POOL_CAP_FRACTION * 100 + 1e-9) / 100.0
