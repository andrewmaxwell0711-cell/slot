#!/usr/bin/env python3
"""Monte Carlo check of Fortune Reels return-to-player.

Uses the same spin_grid() / evaluate_win() path as the live server, so
every trial is an independent fair RNG outcome with no player state.

Target RTP is 20% (10,000 paid back per 50,000 wagered), accepted
within ±1 percentage point.
"""

from __future__ import annotations

import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))

import game  # noqa: E402

DEFAULT_SPINS = 1_000_000
TARGET_RTP = 0.20
TOLERANCE = 0.01  # ±1 percentage point
BET_AUD = 1.0


def theoretical_rtp() -> float:
    total_weight = sum(s["weight"] for s in game.SYMBOLS)
    rtp = 0.0
    for symbol in game.SYMBOLS:
        p = symbol["weight"] / total_weight
        pays = symbol["pays"]
        rtp += (p**3) * (1 - p) * pays.get(3, 0)
        rtp += (p**4) * (1 - p) * pays.get(4, 0)
        rtp += (p**5) * pays.get(5, 0)
    return rtp


def simulate(spins: int = DEFAULT_SPINS, bet_aud: float = BET_AUD) -> dict[str, float]:
    total_bet = 0.0
    total_won = 0.0
    wins = 0
    for _ in range(spins):
        result = game.evaluate_win(game.spin_grid(), bet_aud)
        total_bet += bet_aud
        win = result["win_aud"]
        total_won += win
        if win > 0:
            wins += 1
    rtp = total_won / total_bet if total_bet else 0.0
    return {
        "spins": float(spins),
        "total_bet": total_bet,
        "total_won": total_won,
        "wins": float(wins),
        "rtp": rtp,
    }


def main() -> int:
    spins = DEFAULT_SPINS
    if len(sys.argv) > 1:
        spins = int(sys.argv[1])

    theo = theoretical_rtp()
    stats = simulate(spins)
    rtp = stats["rtp"]
    delta = rtp - TARGET_RTP
    ok = abs(delta) <= TOLERANCE

    print(f"Spins:            {int(stats['spins']):,}")
    print(f"Total bet:        {stats['total_bet']:,.2f}")
    print(f"Total won:        {stats['total_won']:,.2f}")
    print(f"Winning spins:    {int(stats['wins']):,} ({100 * stats['wins'] / stats['spins']:.3f}%)")
    print(f"Simulated RTP:    {rtp * 100:.4f}%")
    print(f"Theoretical RTP:  {theo * 100:.4f}%")
    print(f"Target RTP:       {TARGET_RTP * 100:.2f}%  (10,000 / 50,000)")
    print(f"Delta vs target:  {delta * 100:+.4f} pp")
    if ok:
        print("Result: PASS — simulated RTP is within ±1% of 20%.")
        return 0
    print("Result: FAIL — simulated RTP is outside ±1% of 20%.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
