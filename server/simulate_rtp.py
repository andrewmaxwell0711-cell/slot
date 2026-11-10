#!/usr/bin/env python3
"""Monte Carlo check of Crystal Reels return-to-player.

Runs the live play_round() path (25 paylines, wilds, scatters, free spins
with retriggers) and the same settlement rules as the ledger: each spin
capped at 20% of the pool, and the Green Tea Jackpot paying exactly the cap
with hit chance JACKPOT_C * bet / pool (rolled against the live pool).

    python server/simulate_rtp.py [spins] [lines] [start_pool]

Target total RTP is 20% (10,000 back per 50,000 wagered), ±1 pp.
"""

from __future__ import annotations

import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))

import game  # noqa: E402

TARGET_RTP = 0.20
TOLERANCE = 0.01


def simulate(spins: int, lines: int = 25, bet_per_line: float = 0.04, start_pool: float = 0.0) -> dict:
    pool = start_pool
    total_bet = bet_per_line * lines
    staked = won = line_won = scatter_won = free_won = jackpot_won = 0.0
    capped = bonuses = jackpots = 0
    biggest_jp = 0.0
    jp_expected = 0.0
    for _ in range(spins):
        rnd = game.play_round(bet_per_line, lines)
        staked += total_bet
        pool += total_bet
        p_hit = game.jackpot_probability(total_bet, pool)
        hit = game._rng.random() < p_hit
        steps = [rnd["base"]] + rnd["free_spins"]
        if rnd["free_spins"]:
            bonuses += 1
        for i, step in enumerate(steps):
            cap = game.cap_for_pool(pool)
            raw = round(step["raw_win_aud"], 2)
            paid = min(raw, cap)
            if paid < raw - 1e-9:
                capped += 1
            jp = 0.0
            if i == 0:
                jp_expected += p_hit * max(0.0, cap - paid)
            if i == 0 and hit:
                jp = max(0.0, cap - paid)
                jackpots += 1
                jackpot_won += jp
                biggest_jp = max(biggest_jp, jp)
            pool -= paid + jp
            assert pool >= -1e-9
            won += paid + jp
            if i == 0:
                lw = sum(w["win_aud"] for w in step["line_wins"])
                line_won += min(lw, paid)
                scatter_won += max(0.0, paid - lw)
            else:
                free_won += paid
    return {
        "spins": spins, "lines": lines, "staked": staked, "won": won, "rtp": won / staked,
        "line": line_won / staked, "scatter": scatter_won / staked, "free": free_won / staked,
        "jackpot": jackpot_won / staked,
        "jackpot_ev": jp_expected / staked,
        "rtp_ev": (won - jackpot_won + jp_expected) / staked, "bonuses": bonuses, "jackpots": jackpots,
        "biggest_jp": biggest_jp, "capped": capped, "end_pool": pool,
    }


def report(title: str, s: dict) -> None:
    print(f"== {title} ==")
    print(f"Spins {s['spins']:,} x {s['lines']} lines   staked {s['staked']:,.2f}   won {s['won']:,.2f}")
    print(f"Total RTP:  {s['rtp'] * 100:.3f}%")
    print(f"  lines {s['line'] * 100:.3f}%  scatter {s['scatter'] * 100:.3f}%  free spins {s['free'] * 100:.3f}%  jackpot {s['jackpot'] * 100:.3f}%")
    print(f"Expected-value RTP (jackpot at its exact EV): {s['rtp_ev'] * 100:.3f}%  (jackpot EV {s['jackpot_ev'] * 100:.3f}%)")
    print(f"  bonus rounds 1 in {s['spins'] / max(1, s['bonuses']):,.0f}   jackpots {s['jackpots']} (biggest {s['biggest_jp']:,.2f})   capped spins {s['capped']}")
    print(f"  end pool {s['end_pool']:,.2f}\n")


def main() -> int:
    spins = int(sys.argv[1]) if len(sys.argv) > 1 else 400_000
    lines = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    start_pool = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
    print(f"Expected jackpot RTP once the pool is large: {game.JACKPOT_C * game.POOL_CAP_FRACTION * 100:.2f}%\n")
    s = simulate(spins, lines, 1.0 / lines, start_pool)
    report(f"{lines} lines, A$1 total bet, pool starts at {start_pool:,.0f}", s)
    ok = abs(s["rtp_ev"] - TARGET_RTP) <= TOLERANCE
    print("Result:", "PASS — within ±1 pp of 20%." if ok else "FAIL — outside ±1 pp of 20%.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
