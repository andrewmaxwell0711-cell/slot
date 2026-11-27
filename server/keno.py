"""Crystal Keno: 80 balls, pick 1–10, 20 drawn.

Pays are published multipliers of the stake. Expected return is computed
exactly from the hypergeometric distribution and sits in the 92–95% band
for every pick size. Draws use secrets.SystemRandom. Coins have no cash value.
"""

from __future__ import annotations

from fractions import Fraction
from math import comb
from typing import Any

import secrets

_rng = secrets.SystemRandom()

BALLS = 80
DRAWN = 20
PICK_MIN, PICK_MAX = 1, 10

# Multipliers of the stake for each (picks, hits) pair. Missing hits pay 0.
# Tuned so exact combinatorial EV is inside 92–95% for every pick size.
PAYS: dict[int, dict[int, Fraction]] = {
    1: {1: Fraction(15, 4)},  # 3.75
    2: {2: Fraction(31, 2)},  # 15.5
    3: {3: 43, 2: Fraction(5, 2)},
    4: {4: 155, 3: 6, 2: 1},
    5: {5: 730, 4: 18, 3: 3},
    6: {6: 2550, 5: 40, 4: 8, 3: 2},
    7: {7: 18300, 6: 80, 5: 12, 4: 3, 3: 1},
    8: {8: 137000, 7: 150, 6: 20, 5: 6, 4: 2},
    9: {9: 880000, 8: 300, 7: 40, 6: 10, 5: 3, 4: 1},
    10: {10: 6610000, 9: 500, 8: 80, 7: 15, 6: 5, 5: 2},
}


def _comb(n: int, k: int) -> int:
    if k < 0 or k > n:
        return 0
    return comb(n, k)


def hit_probability(picks: int, hits: int) -> Fraction:
    """P(exactly `hits` matches) = C(20, hits) * C(60, picks-hits) / C(80, picks)."""
    k = int(picks)
    x = int(hits)
    if k < PICK_MIN or k > PICK_MAX or x < 0 or x > k or x > DRAWN or (k - x) > (BALLS - DRAWN):
        return Fraction(0)
    return Fraction(_comb(DRAWN, x) * _comb(BALLS - DRAWN, k - x), _comb(BALLS, k))


def exact_rtp(picks: int) -> Fraction:
    k = int(picks)
    if k not in PAYS:
        raise ValueError("Pick 1 to 10 numbers")
    return sum(hit_probability(k, x) * Fraction(PAYS[k].get(x, 0)) for x in range(0, k + 1))


def multiplier(picks: int, hits: int) -> Fraction:
    return Fraction(PAYS.get(int(picks), {}).get(int(hits), 0))


def pay_coins(bet: int, picks: int, hits: int) -> int:
    m = multiplier(picks, hits)
    if m == 0 or bet <= 0:
        return 0
    return int(bet) * m.numerator // m.denominator


def published_paytable() -> dict[str, Any]:
    table = {}
    for k, pays in PAYS.items():
        table[str(k)] = {str(h): float(v) for h, v in sorted(pays.items())}
    rtp = {str(k): float(exact_rtp(k)) for k in PAYS}
    return {
        "balls": BALLS,
        "drawn": DRAWN,
        "pick_min": PICK_MIN,
        "pick_max": PICK_MAX,
        "pays": table,
        "rtp": rtp,
        "legal": "Keno pays are fixed multipliers of your stake. Coins have no cash value.",
    }


def _clean_picks(raw: Any, count: int | None = None) -> list[int]:
    if raw is None:
        picks: list[int] = []
    else:
        picks = []
        for n in raw:
            try:
                v = int(n)
            except (TypeError, ValueError):
                raise ValueError("Keno numbers must be integers from 1 to 80")
            if v < 1 or v > BALLS:
                raise ValueError("Keno numbers are 1 to 80")
            if v not in picks:
                picks.append(v)
    if count is not None:
        count = int(count)
        if count < PICK_MIN or count > PICK_MAX:
            raise ValueError("Pick 1 to 10 numbers")
        if picks and len(picks) != count:
            raise ValueError(f"Select exactly {count} number{'s' if count != 1 else ''}")
    if not picks:
        k = int(count or 0)
        if k < PICK_MIN or k > PICK_MAX:
            raise ValueError("Pick 1 to 10 numbers")
        picks = _rng.sample(range(1, BALLS + 1), k)
        picks.sort()
        quick = True
    else:
        quick = False
        if len(picks) < PICK_MIN or len(picks) > PICK_MAX:
            raise ValueError("Pick 1 to 10 numbers")
        picks = sorted(picks)
    return picks, quick  # type: ignore[return-value]


def play(bet: int, picks: Any = None, count: int | None = None) -> dict[str, Any]:
    from side import BETS, SideError

    bet = int(bet or 0)
    if bet not in BETS:
        raise SideError("Choose one of the listed coin stakes")
    try:
        chosen, quick = _clean_picks(picks, count)
    except ValueError as exc:
        raise SideError(str(exc)) from exc
    drawn = sorted(_rng.sample(range(1, BALLS + 1), DRAWN))
    hit_set = set(chosen) & set(drawn)
    hits = sorted(hit_set)
    k = len(chosen)
    caught = len(hits)
    mult = multiplier(k, caught)
    payout = pay_coins(bet, k, caught)
    return {
        "game": "keno",
        "done": True,
        "bet": bet,
        "picks": chosen,
        "quick": quick,
        "drawn": drawn,
        "hits": hits,
        "caught": caught,
        "pick_count": k,
        "multiplier": float(mult),
        "payout": payout,
        "win": payout > bet,
        "push": payout == bet and bet > 0,
        "result": (
            f"Caught {caught} of {k} · {float(mult):g}× · "
            + ("paid" if payout else "no win")
        ),
    }


def catalogue_block() -> dict[str, Any]:
    return published_paytable()
