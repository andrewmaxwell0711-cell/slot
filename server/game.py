"""Shared slot rules: symbols, demo FX rates, RNG, payline + feature evaluation.

Every outcome is decided here on the server with secrets.SystemRandom; the
browser only animates the result it is sent. Wins are paid in full; the
house pool is an internal stat and does not cap payouts.
"""

from __future__ import annotations

import secrets
from typing import Any

REEL_COUNT = 5
VISIBLE_ROWS = 3

# Crystal theme. Feature symbols: Crystal WILD, Prism SCATTER (free spins)
# and a non-paying Ice Shard. Weights and pays are tuned with simulate_rtp.py
# for a long-run return of ~95%, including free spins, mini games and the
# Green Tea Jackpot (a fixed multiple of total bet).
SYMBOLS = [
    {"id": "quartz", "name": "Rose Quartz", "emoji": "🩷", "weight": 22, "pays": {3: 18, 4: 46, 5: 92}},
    {"id": "citrine", "name": "Citrine", "emoji": "💛", "weight": 20, "pays": {3: 18, 4: 46, 5: 92}},
    {"id": "topaz", "name": "Topaz", "emoji": "🧡", "weight": 18, "pays": {3: 28, 4: 74, 5: 184}},
    {"id": "amethyst", "name": "Amethyst", "emoji": "💜", "weight": 16, "pays": {3: 28, 4: 74, 5: 230}},
    {"id": "emerald", "name": "Emerald", "emoji": "💚", "weight": 12, "pays": {3: 46, 4: 138, 5: 368}},
    {"id": "sapphire", "name": "Sapphire", "emoji": "💙", "weight": 8, "pays": {3: 69, 4: 230, 5: 460}},
    {"id": "ruby", "name": "Ruby", "emoji": "❤️", "weight": 5, "pays": {3: 115, 4: 368, 5: 920}},
    # Top symbol: glowing Green Tea crystal cup (takes the old diamond slot/pays).
    {"id": "greentea", "name": "Green Tea", "emoji": "🍵", "weight": 3, "pays": {3: 230, 4: 690, 5: 2300}},
    # Crystal WILD: reels 2-4 only, substitutes on the payline, doubles the line win.
    {"id": "wild", "name": "Crystal Wild", "emoji": "🔮", "weight": 1, "pays": {3: 230, 4: 690, 5: 4600},
     "wild": True, "reels": (1, 2, 3)},
    # Prism SCATTER: 3+ anywhere pays and triggers free spins.
    {"id": "scatter", "name": "Prism Scatter", "emoji": "🌈", "weight": 3, "pays": {}, "scatter": True},
    # Non-paying ice shard (classic blank). Weight is tuned for hit frequency and ~95% RTP.
    {"id": "shard", "name": "Ice Shard", "emoji": "❄️", "weight": 11.7, "pays": {}, "blank": True},
    # Crystal Coin: does not pay on a line; 6+ on the paid spin start Hold & Spin.
    {"id": "coin", "name": "Crystal Coin", "emoji": "🪙", "weight": 10, "pays": {}, "blank": True, "hold": True},
]

WILD_ID = "wild"
SCATTER_ID = "scatter"
COIN_ID = "coin"
WILD_MULT = 2  # any line win that uses a wild is doubled

# Scatter count anywhere on the 5×3 grid -> (pay × bet, free spins awarded)
SCATTER_PAYS = {3: (9, 8), 4: (25, 12), 5: (100, 20)}
FREE_SPIN_MULT = 2  # every win during free spins is doubled
MAX_FREE_SPINS = 50  # retrigger ceiling per bonus round

# Green Tea Jackpot: a fixed prize of JACKPOT_MULT × total bet, on a paid
# spin or when the Tea Wheel lands on its (visually thin, weight-proportional)
# jackpot wedge. Landing on that wedge always pays the jackpot — there is no
# second roll and no staged near miss. Hit chance on a paid spin is constant,
# so expected jackpot return is JACKPOT_P * JACKPOT_MULT of stakes (~2%).
JACKPOT_MULT = 5000
JACKPOT_P = 0.02 / JACKPOT_MULT  # 2% RTP from the random jackpot
# Legacy names kept so older comments/imports do not break; they are unused
# for probability now that the prize is a fixed multiple, not a pool cap.
JACKPOT_C = JACKPOT_P
JACKPOT_MAX_P = JACKPOT_P

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

# Deprecated leftover: payouts are no longer capped by the house pool.
POOL_CAP_FRACTION = 0.0

# Social-casino virtual currency. 1 internal game unit = 1,000 coins.
# Internal math (bets, pays, jackpot) stays in the original game units.
# Players only ever see integer coins (1 unit = 1,000 coins).
COIN_SCALE = 1000
COIN_ASSET = "COIN"
STARTING_COINS = 25_000
DAILY_COINS = 8_000
HOURLY_COINS = 2_000
HOURLY_SECONDS = 60 * 60

# Shop packs: AUD is the Stripe charge currency only. Coins have no cash value
# and cannot be redeemed, transferred or exchanged for money or prizes.
COIN_PACKS = (
    {"id": "pack_5", "label": "Pouch", "price_aud": 4.99, "price_cents": 499, "coins": 50_000, "tag": None},
    {"id": "pack_10", "label": "Sack", "price_aud": 9.99, "price_cents": 999, "coins": 120_000, "tag": "Popular"},
    {"id": "pack_20", "label": "Chest", "price_aud": 19.99, "price_cents": 1999, "coins": 280_000, "tag": "Best value"},
    {"id": "pack_50", "label": "Vault", "price_aud": 49.99, "price_cents": 4999, "coins": 800_000, "tag": "Biggest"},
)

LEGAL_COINS = (
    "Coins are for entertainment only, have no monetary value and cannot be "
    "redeemed for cash or prizes."
)
RESPONSIBLE_PLAY = (
    "Play for fun. This is a social casino, not real-money gambling. "
    "If you need a break, step away. 18+ only."
)

# Legacy aliases kept so older helpers/tests that still mention asset lists
# do not break on import. The ledger no longer holds fiat or crypto.
RATES_TO_AUD = {"AUD": 1.0}
FIAT = ("AUD",)
CRYPTO = ()
ALL_ASSETS = (COIN_ASSET,)


def to_coins(units: float | int | None) -> int:
    return int(round(float(units or 0) * COIN_SCALE))


def from_coins(coins: float | int | None) -> float:
    return float(coins or 0) / COIN_SCALE


def pack_by_id(pack_id: str) -> dict | None:
    for pack in COIN_PACKS:
        if pack["id"] == pack_id:
            return pack
    return None

_rng = secrets.SystemRandom()
BLANK_ID = "shard"


def _reel_table(reel: int) -> tuple[list[dict[str, Any]], float]:
    syms = [s for s in SYMBOLS if reel in s.get("reels", range(REEL_COUNT))]
    return syms, float(sum(s["weight"] for s in syms))


_REEL_TABLES = [_reel_table(r) for r in range(REEL_COUNT)]


def to_aud(asset: str, amount: float) -> float:
    """Deprecated helper: leftover name. COIN amounts are already coins."""
    if asset == COIN_ASSET:
        return from_coins(amount)
    return amount * (RATES_TO_AUD.get(asset) or 1.0)


def from_aud(asset: str, aud_amount: float) -> float:
    if asset == COIN_ASSET:
        return float(to_coins(aud_amount))
    return aud_amount / (RATES_TO_AUD.get(asset) or 1.0)


def total_aud(balances: dict[str, float]) -> float:
    """Game-unit value of a balance map (coins / COIN_SCALE)."""
    if COIN_ASSET in balances:
        return from_coins(balances.get(COIN_ASSET, 0) or 0)
    return sum(to_aud(a, balances.get(a, 0.0) or 0.0) for a in balances)


def clean_amount(asset: str, amount: float) -> float:
    if amount < 1e-12:
        return 0.0
    if asset == COIN_ASSET:
        return float(int(round(amount)))
    if asset in FIAT:
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
        if sid in (SCATTER_ID, BLANK_ID, COIN_ID):
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



def coin_positions(grid: list[list[str]]) -> list[list[int]]:
    return [[c, r] for c, col in enumerate(grid) for r, sid in enumerate(col) if sid == COIN_ID]


def mw_coin_positions(cols: list[list[str]]) -> list[list[int]]:
    return [[c, r] for c, col in enumerate(cols) for r, sid in enumerate(col) if sid == COIN_ID]


def apply_surprise_wilds(grid: list[list[str]]) -> list[dict[str, Any]]:
    """Maybe replace 1–2 non-feature cells with wilds. Mutates `grid`. Paid spins only."""
    if _rng.random() >= SURPRISE_WILD_P:
        return []
    candidates: list[tuple[int, int, str]] = []
    shards: list[tuple[int, int, str]] = []
    for c, col in enumerate(grid):
        for r, sid in enumerate(col):
            if sid in (WILD_ID, SCATTER_ID, COIN_ID):
                continue
            item = (c, r, sid)
            candidates.append(item)
            if sid == BLANK_ID:
                shards.append(item)
    pool = shards or candidates
    if not pool:
        return []
    n = min(len(pool), _rng.choice(SURPRISE_WILD_COUNTS))
    _rng.shuffle(pool)
    placed = []
    for c, r, prev in pool[:n]:
        grid[c][r] = WILD_ID
        placed.append({"col": c, "row": r, "from": prev})
    return placed


def apply_surprise_wilds_mw(cols: list[list[str]]) -> list[dict[str, Any]]:
    if _rng.random() >= SURPRISE_WILD_P:
        return []
    candidates: list[tuple[int, int, str]] = []
    shards: list[tuple[int, int, str]] = []
    for c, col in enumerate(cols):
        for r, sid in enumerate(col):
            if sid in (WILD_ID, SCATTER_ID, COIN_ID):
                continue
            item = (c, r, sid)
            candidates.append(item)
            if sid == BLANK_ID:
                shards.append(item)
    pool = shards or candidates
    if not pool:
        return []
    n = min(len(pool), _rng.choice(SURPRISE_WILD_COUNTS))
    _rng.shuffle(pool)
    placed = []
    for c, r, prev in pool[:n]:
        cols[c][r] = WILD_ID
        placed.append({"col": c, "row": r, "from": prev})
    return placed


def _hold_value() -> float:
    return float(_weighted(HOLD_VALUES))


def play_hold_spin(stake: float, start_positions: list[list[int]] | None = None, start_count: int | None = None) -> dict[str, Any]:
    """Hold & Spin: locked coin values, 3 respins (reset when a new coin lands).
    Filling all 15 cells adds HOLD_GRAND_MULT × stake on top of the locked sum.
    """
    cells: list[float | None] = [None] * HOLD_CELLS
    starts = list(start_positions or [])
    if starts:
        for i, pos in enumerate(starts[:HOLD_CELLS]):
            cells[i] = _hold_value()
    else:
        n = max(HOLD_TRIGGER, int(start_count or HOLD_TRIGGER))
        n = min(HOLD_CELLS, n)
        chosen = list(range(HOLD_CELLS))
        _rng.shuffle(chosen)
        for i in chosen[:n]:
            cells[i] = _hold_value()
    respins = HOLD_RESPINS
    rounds: list[dict[str, Any]] = []
    while respins > 0:
        respins -= 1
        added: list[int] = []
        for i, val in enumerate(cells):
            if val is not None:
                continue
            if _rng.random() < HOLD_RESPIN_P:
                cells[i] = _hold_value()
                added.append(i)
        if added:
            respins = HOLD_RESPINS
        rounds.append({
            "cells": [v for v in cells],
            "added": added,
            "respins_left": respins,
        })
        if all(v is not None for v in cells):
            break
    locked = [v or 0.0 for v in cells]
    filled = all(v is not None for v in cells)
    raw = stake * sum(locked)
    if filled:
        raw += stake * HOLD_GRAND_MULT
    return {
        "kind": "hold_spin",
        "cells": cells,
        "values": locked,
        "rounds": rounds,
        "filled": filled,
        "grand": filled,
        "grand_mult": HOLD_GRAND_MULT if filled else 0,
        "raw_win_aud": round(raw, 8),
        "coins_locked": sum(1 for v in cells if v is not None),
    }


def collection_step(stake: float, meter: dict[str, int] | None = None) -> dict[str, Any]:
    """Advance the Crystal Collection meter. Completing a track pays COLLECT_PAY_MULT × stake."""
    state = {k: int((meter or {}).get(k) or 0) for k in COLLECT_TYPES}
    added = None
    paid = 0.0
    completed = None
    if _rng.random() < COLLECT_P:
        added = _rng.choice(COLLECT_TYPES)
        state[added] = int(state[added]) + 1
        if state[added] >= COLLECT_SET:
            paid = round(stake * COLLECT_PAY_MULT, 8)
            state[added] = 0
            completed = added
    return {"meter": state, "added": added, "completed": completed, "paid_aud": paid, "set_size": COLLECT_SET}


def progressive_step(stake: float, pot: float) -> dict[str, Any]:
    """Add PROG_RATE of the stake to the pot; rare random hit pays the pot and reseeds."""
    if stake <= 0:
        return {"contribution": 0.0, "pot": max(float(pot), PROG_SEED), "hit": False, "paid_aud": 0.0}
    contribution = round(float(stake) * PROG_RATE, 8)
    pot = max(float(pot), 0.0) + contribution
    hit = _rng.random() < PROG_HIT_P
    paid = 0.0
    if hit:
        paid = round(pot, 2)
        pot = float(PROG_SEED)
    return {"contribution": contribution, "pot": round(pot, 6), "hit": hit, "paid_aud": paid}


def play_one(bet_per_line: float, lines: int, multiplier: int = 1, surprise: bool = False) -> dict[str, Any]:
    """One spin's grid and raw win (no payout cap)."""
    grid = spin_grid()
    surprise_wilds = apply_surprise_wilds(grid) if surprise else []
    total_bet = bet_per_line * lines
    line_wins = evaluate_lines(grid, bet_per_line, lines)
    scatters = count_scatters(grid)
    scatter_mult, free_spins = SCATTER_PAYS.get(min(scatters, 5), (0, 0))
    scatter_win = total_bet * scatter_mult  # scatter pays on the total bet
    for w in line_wins:
        w["win_aud"] = round(w["win_aud"] * multiplier, 8)
    raw = sum(w["win_aud"] for w in line_wins) + scatter_win * multiplier
    coins = coin_positions(grid)
    return {
        "grid": grid,
        "line_wins": line_wins,
        "scatters": scatters,
        "scatter_pos": scatter_positions(grid),
        "scatter_win_aud": round(scatter_win * multiplier, 8),
        "free_spins_awarded": free_spins,
        "multiplier": multiplier,
        "raw_win_aud": round(raw, 8),
        "surprise_wilds": surprise_wilds,
        "coins": coins,
        "coin_count": len(coins),
    }


def jackpot_amount(total_bet: float) -> float:
    """Green Tea Jackpot prize in game units: JACKPOT_MULT × total bet."""
    if total_bet <= 0:
        return 0.0
    return round(float(total_bet) * JACKPOT_MULT, 2)


def jackpot_probability(total_bet: float, pool_aud: float = 0.0) -> float:
    """Fixed per-spin chance. `pool_aud` is ignored (kept for call-site compatibility)."""
    if total_bet <= 0:
        return 0.0
    return JACKPOT_P


def jackpot_roll(total_bet: float, pool_aud: float = 0.0) -> bool:
    return _rng.random() < jackpot_probability(total_bet, pool_aud)


def draw_card() -> dict[str, str]:
    suit, colour = _rng.choice(SUITS)
    return {"rank": _rng.choice(RANKS), "suit": suit, "colour": colour}


def cap_for_pool(pool_aud: float) -> float:
    """Deprecated: there is no payout cap. Always returns 0."""
    return 0.0


# ===========================================================================
# v4: Megaways mode, mini games (Crystal Pick, Tea Wheel) and shared settlement
# ===========================================================================

MODES = ("megaways", "classic")

# ---- Megaways -------------------------------------------------------------
# 6 reels. Reels 1 and 6 land 2-7 symbols; reels 2-5 land 2-6 plus one symbol
# on the horizontal top reel above them, so every reel shows 2-7 symbols and
# ways = product of reel heights (max 7^6 = 117,649).
MW_REELS = 6
MW_TOP_REELS = (1, 2, 3, 4)
MW_MIN_ROWS = 2
MW_MAX_ROWS = 7
MW_BET_AUD = [0.2, 0.4, 0.6, 1, 2, 4, 10, 20, 50, 100]
MW_MAX_CASCADES = 40

# Symbol weights per landing cell (wild only on reels 2-5, scatter never on the top reel).
MW_WEIGHTS = {
    "quartz": 20, "citrine": 20, "topaz": 16, "amethyst": 16, "emerald": 13,
    "sapphire": 11, "ruby": 8, "greentea": 5, "wild": 2, "scatter": 3.8, "shard": 56, "coin": 6,
}
# Free spins use a richer reel set (fewer Ice Shard blanks).
MW_FREE_WEIGHTS = {**MW_WEIGHTS, "shard": 42, "scatter": 3.0, "coin": 0}
# Pay × total stake PER WAY for 3/4/5/6 of a kind (scaled by MW_PAY_SCALE).
MW_PAYS = {
    "quartz": {3: 0.10, 4: 0.20, 5: 0.40, 6: 1.0},
    "citrine": {3: 0.10, 4: 0.20, 5: 0.40, 6: 1.0},
    "topaz": {3: 0.15, 4: 0.30, 5: 0.60, 6: 1.5},
    "amethyst": {3: 0.15, 4: 0.30, 5: 0.75, 6: 2.0},
    "emerald": {3: 0.20, 4: 0.50, 5: 1.0, 6: 3.0},
    "sapphire": {3: 0.30, 4: 0.75, 5: 1.5, 6: 5.0},
    "ruby": {3: 0.50, 4: 1.0, 5: 2.5, 6: 10.0},
    "greentea": {3: 1.0, 4: 2.5, 5: 10.0, 6: 50.0},
}
MW_PAY_SCALE = 1.40
# Scatters on the final board -> (pay × stake, free spins)
MW_SCATTER_PAYS = {4: (1, 10), 5: (5, 15), 6: (25, 20)}
MW_RETRIGGER = {3: 5, 4: 5, 5: 10, 6: 15}  # during free spins
MW_FREE_SPIN_START_MULT = 1  # multiplier +1 after every winning cascade, never resets in the bonus


def _mw_table(reel: int, top: bool, free: bool = False) -> tuple[list[tuple[str, float]], float]:
    items = []
    for sid, w in (MW_FREE_WEIGHTS if free else MW_WEIGHTS).items():
        if sid == WILD_ID and reel not in MW_TOP_REELS:
            continue
        if sid == SCATTER_ID and top:
            continue
        items.append((sid, float(w)))
    return items, sum(w for _, w in items)


def rebuild_mw_tables() -> None:
    _MW_TABLES.clear()
    _MW_TABLES.update({(r, t, f): _mw_table(r, t, f) for r in range(MW_REELS) for t in (False, True) for f in (False, True)})


_MW_TABLES: dict = {}


def mw_pick(reel: int, top: bool = False, free: bool = False) -> str:
    items, total = _MW_TABLES[(reel, top, free)]
    x = _rng.random() * total
    for sid, w in items:
        x -= w
        if x <= 0:
            return sid
    return items[0][0]


rebuild_mw_tables()


def mw_board(free: bool = False) -> list[list[str]]:
    """Combined columns. Columns 1-4 start with their top-reel cell."""
    cols = []
    for c in range(MW_REELS):
        if c in MW_TOP_REELS:
            h = _rng.randint(MW_MIN_ROWS, MW_MAX_ROWS - 1)
            col = [mw_pick(c, True, free)] + [mw_pick(c, False, free) for _ in range(h)]
        else:
            h = _rng.randint(MW_MIN_ROWS, MW_MAX_ROWS)
            col = [mw_pick(c, False, free) for _ in range(h)]
        cols.append(col)
    return cols


def mw_ways(cols: list[list[str]]) -> int:
    ways = 1
    for col in cols:
        ways *= len(col)
    return ways


def mw_evaluate(cols: list[list[str]], stake: float, mult: int = 1) -> list[dict[str, Any]]:
    """Ways wins: symbol (or wild) on adjacent reels from reel 1; ways = product of matches."""
    wins = []
    for sid, pays in MW_PAYS.items():
        counts = []
        for col in cols:
            n = sum(1 for x in col if x == sid or x == WILD_ID)
            if n == 0:
                break
            counts.append(n)
        # reel 1 has no wilds, so a run must start with the real symbol there
        if len(counts) < 3 or not any(x == sid for x in cols[0]):
            continue
        length = len(counts)
        ways = 1
        for n in counts:
            ways *= n
        pay = pays[length] * MW_PAY_SCALE
        cells = [[c, r] for c in range(length) for r, x in enumerate(cols[c]) if x == sid or x == WILD_ID]
        wins.append({
            "symbol": sid, "count": length, "ways": ways, "pay": pay, "multiplier": mult,
            "win_aud": round(stake * pay * ways * mult, 8), "cells": cells,
        })
    return wins


def mw_cascade(cols: list[list[str]], cells: set[tuple[int, int]], free: bool = False) -> tuple[list[list[str]], list[int], list[bool]]:
    """Shatter `cells`, drop survivors down, refill from above. Returns (cols, new_per_col, top_refilled)."""
    out, new_counts, top_new = [], [], []
    for c, col in enumerate(cols):
        has_top = c in MW_TOP_REELS
        start = 1 if has_top else 0
        top_cell = col[0] if has_top else None
        refilled = False
        if has_top and (c, 0) in cells:
            top_cell = mw_pick(c, True, free)
            refilled = True
        main = col[start:]
        kept = [x for r, x in enumerate(main) if (c, r + start) not in cells]
        fresh = [mw_pick(c, False, free) for _ in range(len(main) - len(kept))]
        new_col = ([top_cell] if has_top else []) + fresh + kept
        out.append(new_col)
        new_counts.append(len(fresh))
        top_new.append(refilled)
    return out, new_counts, top_new


def mw_play_one(stake: float, free: bool = False, mult: int = 1, surprise: bool = False) -> dict[str, Any]:
    """One Megaways spin with tumbling cascades. In free spins the multiplier
    applies to every win and grows +1 after each winning cascade."""
    cols = mw_board(free)
    surprise_wilds = apply_surprise_wilds_mw(cols) if (surprise and not free) else []
    stages = []
    raw = 0.0
    new_counts = [len(c) for c in cols]
    top_new = [c in MW_TOP_REELS for c in range(MW_REELS)]
    for k in range(MW_MAX_CASCADES + 1):
        # safety stop: after MW_MAX_CASCADES tumbles the last board is shown but not paid again
        wins = mw_evaluate(cols, stake, mult if free else 1) if k < MW_MAX_CASCADES else []
        stage_win = round(sum(w["win_aud"] for w in wins), 8)
        stages.append({"cols": [list(c) for c in cols], "ways": mw_ways(cols), "wins": wins,
                       "multiplier": mult if free else 1, "win_aud": stage_win,
                       "new": new_counts, "top_new": top_new})
        if not wins:
            break
        raw += stage_win
        hit = {tuple(cell) for w in wins for cell in w["cells"]}
        cols, new_counts, top_new = mw_cascade(cols, hit, free)
        if free:
            mult += 1
    final = stages[-1]["cols"]
    scat_pos = [[c, r] for c, col in enumerate(final) for r, x in enumerate(col) if x == SCATTER_ID]
    n_scat = len(scat_pos)
    if free:
        scatter_mult, fs = 0, MW_RETRIGGER.get(min(n_scat, 6), 0) if n_scat >= 3 else 0
    else:
        scatter_mult, fs = MW_SCATTER_PAYS.get(min(n_scat, 6), (0, 0)) if n_scat >= 4 else (0, 0)
    scatter_win = round(stake * scatter_mult, 8)
    raw += scatter_win
    return {
        "kind": "spin", "mode": "megaways", "stages": stages, "ways": stages[0]["ways"],
        "cascades": len(stages) - 1, "scatters": n_scat, "scatter_pos": scat_pos,
        "scatter_win_aud": scatter_win, "free_spins_awarded": fs,
        "multiplier": stages[0]["multiplier"], "multiplier_end": mult if free else 1,
        "has_wild": any(x == WILD_ID for col in final for x in col),
        "raw_win_aud": round(raw, 8),
        "surprise_wilds": surprise_wilds,
        "coins": mw_coin_positions(final),
        "coin_count": len(mw_coin_positions(final)),
    }


# ---- Mini games -----------------------------------------------------------
# Crystal Pick: random "mystery" trigger on any paid spin. Pick crystals; each
# reveals a prize (× total bet) until a COLLECT crystal ends the game. The
# reveal order is drawn on the server when the game triggers.
PICK_TRIGGER_P = 1 / 280
PICK_TILES = 12
PICK_COLLECT_P = 0.40  # chance each pick after the first is COLLECT
PICK_PRIZES = [(0.2, 25), (0.5, 28), (1, 22), (2, 13), (3, 7), (5, 3.5), (10, 1.2), (25, 0.3)]  # (× bet, weight)

# Tea Wheel: bonus combo — 2+ BONUS scatters together with a WILD on the final
# board (without triggering free spins). Wedge visual size is proportional to
# weight. The jackpot wedge is a thin sliver; landing on it always pays the
# Green Tea Jackpot. There is no second roll and no staged near miss.
WHEEL_WEDGES = [
    {"type": "mult", "value": 2, "weight": 1000}, {"type": "mult", "value": 5, "weight": 1000},
    {"type": "mult", "value": 3, "weight": 1000}, {"type": "mult", "value": 10, "weight": 1000},
    {"type": "mult", "value": 2, "weight": 1000}, {"type": "free_spins", "value": 8, "weight": 1000},
    {"type": "mult", "value": 4, "weight": 1000}, {"type": "mult", "value": 25, "weight": 1000},
    {"type": "mult", "value": 3, "weight": 1000}, {"type": "mult", "value": 6, "weight": 1000},
    {"type": "mult", "value": 2, "weight": 1000},
    # ~0.07% of the wheel (thin gold sliver). P × 5000 × typical wheel frequency ≈ 0.6–1% RTP.
    {"type": "jackpot", "value": 0, "weight": 8},
]
WHEEL_JACKPOT_INDEX = 11
WHEEL_PRIZE_SCALE = 1.0
WHEEL_MIN_SCATTERS = {"classic": 2, "megaways": 3}  # + a WILD, below the free-spins trigger
WHEEL_WEIGHT_TOTAL = sum(w["weight"] for w in WHEEL_WEDGES)

# ---- v6 slot features (funded inside the ~95% RTP budget) -----------------
# Progressive: 1% of every paid stake is added to a public pot. A rare random
# hit pays the pot and reseeds it. Re-seed EV is small and included in the 95%.
PROG_RATE = 0.01
PROG_SEED = 25.0  # game units (25,000 coins on the ticker at the floor)
PROG_HIT_P = 1 / 8_000

# Hold & Spin: 6+ Crystal Coins on a paid spin start 3 respins on a 5×3 grid.
HOLD_TRIGGER = 6
HOLD_COLS, HOLD_ROWS = 5, 3
HOLD_CELLS = HOLD_COLS * HOLD_ROWS
HOLD_RESPINS = 3
HOLD_GRAND_MULT = 50  # extra × bet when every cell is filled
HOLD_RESPIN_P = 0.10  # chance an empty cell becomes a coin on a respin
HOLD_VALUES = [(0.5, 36), (1, 30), (2, 16), (3, 8), (5, 5), (8, 3), (10, 1.5), (15, 0.4), (25, 0.1)]

# Crystal Collection: a persistent 3-track meter. Completing a track pays × bet.
COLLECT_TYPES = ("ruby", "emerald", "sapphire")
COLLECT_SET = 10
COLLECT_PAY_MULT = 2.0
COLLECT_P = 0.04

# Surprise wilds: on a paid spin, a chance to turn 1–2 non-feature cells wild.
SURPRISE_WILD_P = 0.06
SURPRISE_WILD_COUNTS = (1, 1, 1, 2)  # mostly one wild

# Slight classic-line scale so new feature EV stays inside the 95% band.
# Published paytable numbers stay as SYMBOLS["pays"]; this is applied at eval.
CLASSIC_PAY_SCALE = 0.955


def _weighted(items: list[tuple[float, float]]) -> float:
    total = sum(w for _, w in items)
    x = _rng.random() * total
    for v, w in items:
        x -= w
        if x <= 0:
            return v
    return items[-1][0]


def play_pick(stake: float) -> dict[str, Any]:
    picks = []
    while True:
        if picks and (_rng.random() < PICK_COLLECT_P or len(picks) >= PICK_TILES - 1):
            picks.append({"collect": True})
            break
        m = _weighted(PICK_PRIZES)
        picks.append({"prize_mult": m, "win_aud": round(stake * m, 8)})
    left = PICK_TILES - len(picks)  # unpicked crystals, revealed afterwards for show (one more COLLECT among them)
    decoys = ([{"collect": True}] if left > 0 else []) + [{"prize_mult": _weighted(PICK_PRIZES)} for _ in range(max(0, left - 1))]
    _rng.shuffle(decoys)
    raw = sum(p.get("win_aud", 0.0) for p in picks)
    return {"kind": "pick", "picks": picks, "decoys": decoys, "tiles": PICK_TILES, "raw_win_aud": round(raw, 8)}


def wheel_wedge_angles() -> list[float]:
    """Sweep angle in degrees for each wedge, proportional to weight."""
    total = float(WHEEL_WEIGHT_TOTAL) or 1.0
    return [360.0 * w["weight"] / total for w in WHEEL_WEDGES]


def play_wheel(stake: float) -> dict[str, Any]:
    """Weighted honest stop: the returned index is the outcome that is paid."""
    x = _rng.random() * WHEEL_WEIGHT_TOTAL
    idx = len(WHEEL_WEDGES) - 1
    for i, w in enumerate(WHEEL_WEDGES):
        x -= w["weight"]
        if x <= 0:
            idx = i
            break
    wedge = WHEEL_WEDGES[idx]
    out: dict[str, Any] = {
        "kind": "wheel", "wedges": WHEEL_WEDGES, "index": idx, "free_spins": 0,
        "jackpot": wedge["type"] == "jackpot", "raw_win_aud": 0.0, "prize_mult": 0,
        "angles": wheel_wedge_angles(),
    }
    if wedge["type"] == "jackpot":
        # Paid at settlement as JACKPOT_MULT × stake. No fallback, no near miss.
        out["raw_win_aud"] = 0.0
    elif wedge["type"] == "mult":
        out.update(prize_mult=wedge["value"], raw_win_aud=round(stake * wedge["value"] * WHEEL_PRIZE_SCALE, 8))
    else:
        out["free_spins"] = wedge["value"]
    return out


def _minigames(stake: float, base: dict[str, Any]) -> list[dict[str, Any]]:
    games = []
    need = WHEEL_MIN_SCATTERS[base.get("mode", "classic")]
    if base["free_spins_awarded"] == 0 and base["scatters"] >= need and base.get("has_wild"):
        games.append(play_wheel(stake))
    if _rng.random() < PICK_TRIGGER_P:
        games.append(play_pick(stake))
    coins = list(base.get("coins") or [])
    if len(coins) >= HOLD_TRIGGER:
        games.append(play_hold_spin(stake, start_positions=coins))
    return games


def _classic_has_wild(grid: list[list[str]]) -> bool:
    return any(x == WILD_ID for col in grid for x in col)


def play_classic(bet_per_line: float, lines: int) -> dict[str, Any]:
    """Classic 25-line round incl. mini games and free spins (wheel can add free spins)."""
    stake = round(bet_per_line * lines, 8)
    base = play_one(bet_per_line, lines, 1, surprise=True)
    base["kind"] = "spin"
    base["mode"] = "classic"
    base["has_wild"] = _classic_has_wild(base["grid"])
    games = _minigames(stake, base)
    remaining = base["free_spins_awarded"] + sum(g.get("free_spins", 0) for g in games)
    total_awarded = remaining
    free: list[dict[str, Any]] = []
    while remaining > 0:
        remaining -= 1
        fs = play_one(bet_per_line, lines, FREE_SPIN_MULT)
        fs["kind"] = "spin"
        fs["mode"] = "classic"
        if fs["free_spins_awarded"]:
            extra = max(0, min(fs["free_spins_awarded"], MAX_FREE_SPINS - total_awarded))
            fs["free_spins_awarded"] = extra
            remaining += extra
            total_awarded += extra
        free.append(fs)
    return {"mode": "classic", "stake": stake, "base": base, "minigames": games, "free_spins": free}


def play_megaways(stake: float) -> dict[str, Any]:
    base = mw_play_one(stake, surprise=True)
    games = _minigames(stake, base)
    remaining = base["free_spins_awarded"] + sum(g.get("free_spins", 0) for g in games)
    total_awarded = remaining
    free: list[dict[str, Any]] = []
    mult = MW_FREE_SPIN_START_MULT
    while remaining > 0:
        remaining -= 1
        fs = mw_play_one(stake, free=True, mult=mult)
        mult = fs["multiplier_end"]
        if fs["free_spins_awarded"]:
            extra = max(0, min(fs["free_spins_awarded"], MAX_FREE_SPINS - total_awarded))
            fs["free_spins_awarded"] = extra
            remaining += extra
            total_awarded += extra
        free.append(fs)
    return {"mode": "megaways", "stake": stake, "base": base, "minigames": games, "free_spins": free}


def round_steps(rnd: dict[str, Any]) -> list[dict[str, Any]]:
    """Payout order: paid spin, mini games, then free spins."""
    return [rnd["base"]] + list(rnd.get("minigames") or []) + list(rnd.get("free_spins") or [])


def settle_steps(
    rnd: dict[str, Any], stake: float, pool: float, jackpot_hit: bool,
    wheel_roll: Any = None,
) -> dict[str, Any]:
    """Pure settlement shared by the ledger and the simulator.

    `pool` already includes this round's stake and is updated as an internal
    stat only — it never limits a payout and is floored at 0. A Green Tea
    Jackpot pays the fixed JACKPOT_MULT × stake on the base spin or when the
    Tea Wheel lands on its jackpot wedge (the visual stop is the outcome).
    `wheel_roll` is ignored (kept for older call sites).
    """
    results = []
    total_paid = jackpot_paid = 0.0
    jp_prize = jackpot_amount(stake)
    for i, step in enumerate(round_steps(rnd)):
        raw = round(step["raw_win_aud"], 2)
        jp_step = i == 0 and jackpot_hit
        wheel_index = None
        if step.get("kind") == "wheel":
            wheel_index = step["index"]
            wedge = (step.get("wedges") or WHEEL_WEDGES)[wheel_index]
            if wedge.get("type") == "jackpot" or step.get("jackpot"):
                jp_step, raw = True, 0.0
        paid = raw
        jp = jp_prize if jp_step else 0.0
        step_total = round(paid + jp, 2)
        pool = max(0.0, round(pool - step_total, 6))
        total_paid += step_total
        jackpot_paid += jp
        res = {"kind": step.get("kind", "spin"), "raw_win_aud": raw, "paid_aud": paid,
               "capped": False, "jackpot_aud": jp}
        if wheel_index is not None:
            res["wheel_index"] = wheel_index
            res["wheel_jackpot"] = bool(jp_step and step.get("kind") == "wheel")
        results.append(res)
    return {"steps": results, "total_paid_aud": round(total_paid, 2), "jackpot_paid_aud": round(jackpot_paid, 2),
            "any_capped": False, "pool_after": pool}


def rebuild_tables() -> None:
    """Rebuild classic and Megaways reel tables after weights change."""
    global _REEL_TABLES
    _REEL_TABLES = [_reel_table(r) for r in range(REEL_COUNT)]
    rebuild_mw_tables()
