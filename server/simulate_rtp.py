#!/usr/bin/env python3
"""Monte Carlo check of Fortune Reels return-to-player.

Runs the same play_round() path as the live server (line wins, wilds,
scatters, free spins with retriggers, progressive jackpot) and applies the
same 20%-of-pool cap logic as the ledger.

Two scenarios:
  * uncapped  – a huge house pool, so the cap never binds (pure game RTP)
  * from-zero – the pool starts at 0 like a fresh deploy, cap enforced

Target RTP is 20% (10,000 paid back per 50,000 wagered), ±1 pp.
"""

from __future__ import annotations

import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))

import game  # noqa: E402

DEFAULT_SPINS = 1_000_000
TARGET_RTP = 0.20
TOLERANCE = 0.01
BET_AUD = 1.0


def simulate(spins: int, bet_aud: float = BET_AUD, start_pool: float | None = None) -> dict:
    pool = 1e18 if start_pool is None else start_pool
    meter = 0.0
    bet_total = won = line_won = scatter_won = free_won = jackpot_won = 0.0
    capped = bonuses = jackpots = 0
    for _ in range(spins):
        rnd = game.play_round(bet_aud)
        bet_total += bet_aud
        pool += bet_aud
        meter += bet_aud * game.JACKPOT_CONTRIB
        steps = [rnd["base"]] + rnd["free_spins"]
        if rnd["free_spins"]:
            bonuses += 1
        for i, step in enumerate(steps):
            cap = game.cap_for_pool(pool)
            paid = min(step["raw_win_aud"], cap)
            if paid < step["raw_win_aud"] - 1e-9:
                capped += 1
            if i == 0 and rnd["jackpot_hit"]:
                jp = max(0.0, min(meter, cap - paid))
                meter -= jp
                jackpot_won += jp
                jackpots += 1
                paid_total = paid + jp
            else:
                paid_total = paid
            pool -= paid_total
            won += paid_total
            if i == 0:
                line_won += min(step["line"]["win_aud"], paid)
                scatter_won += max(0.0, paid - step["line"]["win_aud"])
            else:
                free_won += paid
    return {
        "spins": spins,
        "bet": bet_total,
        "won": won,
        "rtp": won / bet_total,
        "line": line_won / bet_total,
        "scatter": scatter_won / bet_total,
        "free": free_won / bet_total,
        "jackpot": jackpot_won / bet_total,
        "bonuses": bonuses,
        "jackpots": jackpots,
        "capped": capped,
        "end_pool": pool if start_pool is not None else None,
        "end_meter": meter,
    }


def report(title: str, s: dict) -> None:
    print(f"== {title} ==")
    print(f"Spins:           {s['spins']:,}   bet {s['bet']:,.2f}   won {s['won']:,.2f}")
    print(f"Total RTP:       {s['rtp'] * 100:.3f}%")
    print(
        f"  base line+scatter {(s['line'] + s['scatter']) * 100:.3f}%  free spins {s['free'] * 100:.3f}%"
        f"  jackpot {s['jackpot'] * 100:.3f}%"
    )
    print(f"Bonus rounds:    {s['bonuses']:,} (1 in {s['spins'] / max(1, s['bonuses']):,.0f})")
    print(f"Jackpot hits:    {s['jackpots']:,}   capped payouts: {s['capped']:,}")
    if s["end_pool"] is not None:
        print(f"End pool:        {s['end_pool']:,.2f}  (max win now {game.cap_for_pool(s['end_pool']):,.2f})")
    print()


def main() -> int:
    spins = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SPINS
    big = simulate(spins)
    report("Uncapped (large pool)", big)
    report("Fresh deploy (pool starts at 0, cap enforced)", simulate(min(spins, 200_000), start_pool=0.0))
    ok = abs(big["rtp"] - TARGET_RTP) <= TOLERANCE
    print("Result:", "PASS — within ±1 pp of 20%." if ok else "FAIL — outside ±1 pp of 20%.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
