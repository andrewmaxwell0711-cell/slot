"""Shared slot rules: symbols, demo FX rates, RNG, and payline evaluation."""

from __future__ import annotations

import secrets
from typing import Any

REEL_COUNT = 5
VISIBLE_ROWS = 3

# Target long-run RTP is 20% (about 10,000 paid back per 50,000 wagered).
# Weights are unchanged so hit frequency stays the same; multipliers were
# raised so the theoretical return is ~20.008%. Every spin is decided by
# the shared RNG below — there is no per-player or balance-based rigging.
SYMBOLS = [
    {"id": "cherry", "emoji": "🍒", "weight": 22, "pays": {3: 4, 4: 10, 5: 20}},
    {"id": "lemon", "emoji": "🍋", "weight": 20, "pays": {3: 4, 4: 10, 5: 20}},
    {"id": "orange", "emoji": "🍊", "weight": 18, "pays": {3: 6, 4: 16, 5: 40}},
    {"id": "plum", "emoji": "🍇", "weight": 16, "pays": {3: 6, 4: 16, 5: 50}},
    {"id": "bell", "emoji": "🔔", "weight": 12, "pays": {3: 10, 4: 30, 5: 80}},
    {"id": "bar", "emoji": "⬛", "weight": 8, "pays": {3: 15, 4: 50, 5: 100}},
    {"id": "seven", "emoji": "7️⃣", "weight": 5, "pays": {3: 25, 4: 80, 5: 200}},
    {"id": "diamond", "emoji": "💎", "weight": 3, "pays": {3: 50, 4: 150, 5: 500}},
]

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


def weighted_pick() -> dict[str, Any]:
    total = sum(s["weight"] for s in SYMBOLS)
    r = _rng.random() * total
    for symbol in SYMBOLS:
        r -= symbol["weight"]
        if r <= 0:
            return symbol
    return SYMBOLS[0]


def spin_grid() -> list[list[str]]:
    """Return a 5-column grid; each column is [top, mid/payline, bottom] symbol ids."""
    grid: list[list[str]] = []
    for _ in range(REEL_COUNT):
        grid.append([weighted_pick()["id"] for _ in range(VISIBLE_ROWS)])
    return grid


def evaluate_win(grid: list[list[str]], bet_aud: float) -> dict[str, Any]:
    line = [col[1] for col in grid]
    first = line[0]
    count = 1
    for symbol_id in line[1:]:
        if symbol_id == first:
            count += 1
        else:
            break
    if count < 3:
        return {"win_aud": 0.0, "count": 0, "symbol": None, "mult": 0, "line": line}
    symbol = symbol_by_id(first)
    mult = symbol["pays"].get(count, 0)
    win_aud = round(bet_aud * mult, 8)
    return {
        "win_aud": win_aud,
        "count": count,
        "symbol": {"id": symbol["id"], "emoji": symbol["emoji"]},
        "mult": mult,
        "line": line,
    }
