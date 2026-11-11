#!/usr/bin/env python3
"""Monte Carlo check of Crystal Casino return-to-player, both modes.

Runs the live round code (including tumbles, free spins, mini games, Hold &
Spin, surprise wilds, the honest Tea Wheel, the Crystal Collection meter and
the Crystal Crown progressive) through game.settle_steps. There is no payout
cap. The Green Tea Jackpot is a fixed JACKPOT_MULT × total bet.

    python server/simulate_rtp.py [spins] [mode megaways|classic|both]

Jackpots and the progressive are rare, so the PASS check uses expected-value
RTP (those prizes at their exact EV, everything else realised). Target 95% ± 0.5 pp.
"""

from __future__ import annotations

import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))

import game  # noqa: E402

TARGET_RTP = 0.95
TOLERANCE = 0.005  # 94.5–95.5%

# Exact EV of the public progressive (contribution rate + re-seed on a hit).
PROG_EV = game.PROG_RATE + game.PROG_SEED * game.PROG_HIT_P
COLLECT_EV = game.COLLECT_P * game.COLLECT_PAY_MULT / game.COLLECT_SET
WHEEL_JP_SHARE = game.WHEEL_WEDGES[game.WHEEL_JACKPOT_INDEX]["weight"] / game.WHEEL_WEIGHT_TOTAL


def simulate(spins: int, mode: str = "megaways") -> dict:
    pool = 0.0
    pot = float(game.PROG_SEED)
    meter = {k: 0 for k in game.COLLECT_TYPES}
    stake = 1.0
    cats = {k: 0.0 for k in (
        "base", "scatter", "free", "pick", "wheel", "hold", "jackpot",
        "wheel_jackpot", "progressive", "collection",
    )}
    jp_ev = 0.0
    staked = won = 0.0
    hits = 0
    n = {"bonus": 0, "pick": 0, "wheel": 0, "hold": 0, "jackpots": 0, "wheel_jackpots": 0,
         "cascades": 0, "max_ways": 0, "surprise": 0, "prog_hits": 0, "sets": 0}
    biggest = 0.0
    for _ in range(spins):
        rnd = game.play_megaways(stake) if mode == "megaways" else game.play_classic(stake / 25, 25)
        staked += stake
        pool += stake
        p_hit = game.jackpot_probability(stake, pool)
        hit = game._rng.random() < p_hit
        steps = game.round_steps(rnd)
        settled = game.settle_steps(rnd, stake, pool, hit)
        jp_ev += p_hit * game.jackpot_amount(stake)
        pool = settled["pool_after"]
        paid = settled["total_paid_aud"]

        prog = game.progressive_step(stake, pot)
        pot = prog["pot"]
        paid += prog["paid_aud"]
        cats["progressive"] += prog["paid_aud"]
        n["prog_hits"] += int(prog["hit"])

        coll = game.collection_step(stake, meter)
        meter = coll["meter"]
        paid += coll["paid_aud"]
        cats["collection"] += coll["paid_aud"]
        n["sets"] += int(bool(coll["completed"]))

        pool = max(0.0, pool - prog["paid_aud"] - coll["paid_aud"])
        won += paid
        biggest = max(biggest, paid)
        if rnd["free_spins"]:
            n["bonus"] += 1
        b = rnd["base"]
        n["cascades"] += b.get("cascades", 0)
        n["max_ways"] = max(n["max_ways"], b.get("ways", 0))
        n["surprise"] += int(bool(b.get("surprise_wilds")))
        if paid > 0 or rnd.get("free_spins") or rnd.get("minigames"):
            hits += 1
        for st, se in zip(steps, settled["steps"]):
            kind = st.get("kind", "spin")
            if st is b:
                sc = min(se["paid_aud"], round(b["scatter_win_aud"], 2))
                cats["scatter"] += sc
                cats["base"] += se["paid_aud"] - sc
                cats["jackpot"] += se["jackpot_aud"]
                n["jackpots"] += se["jackpot_aud"] > 0
            elif kind == "pick":
                n["pick"] += 1
                cats["pick"] += se["paid_aud"]
            elif kind == "wheel":
                n["wheel"] += 1
                cats["wheel"] += se["paid_aud"]
                if se.get("wheel_jackpot"):
                    cats["wheel_jackpot"] += se["jackpot_aud"]
                    n["wheel_jackpots"] += 1
            elif kind == "hold_spin":
                n["hold"] += 1
                cats["hold"] += se["paid_aud"]
            else:
                cats["free"] += se["paid_aud"]
    wjp_ev = (n["wheel"] / max(1, spins)) * WHEEL_JP_SHARE * game.JACKPOT_MULT
    # EV RTP replaces rare jackpots / progressive with their exact expectation.
    rtp_ev = (won - cats["jackpot"] - cats["wheel_jackpot"] - cats["progressive"]
              - cats["collection"] + jp_ev + wjp_ev * staked + PROG_EV * staked + COLLECT_EV * staked) / staked
    return {
        "mode": mode, "spins": spins, "staked": staked, "won": won,
        "rtp": won / staked, "rtp_ev": rtp_ev, "hit": hits / spins,
        "cats": {k: v / staked for k, v in cats.items()},
        "jp_ev": jp_ev / staked, "wjp_ev": wjp_ev, "prog_ev": PROG_EV, "collect_ev": COLLECT_EV,
        "n": n, "biggest": biggest, "end_pool": pool, "end_pot": pot,
    }


def report(s: dict) -> None:
    c, n = s["cats"], s["n"]
    print(f"== {s['mode'].upper()} · {s['spins']:,} spins at A$1 (uncapped, incl. progressive) ==")
    print(f"Realised RTP {s['rtp'] * 100:.3f}%   Expected-value RTP {s['rtp_ev'] * 100:.3f}%   "
          f"hit frequency {s['hit'] * 100:.2f}%")
    print(f"  base {c['base'] * 100:.2f}%  scatter {c['scatter'] * 100:.2f}%  free spins {c['free'] * 100:.2f}%  "
          f"crystal pick {c['pick'] * 100:.2f}%  tea wheel {c['wheel'] * 100:.2f}%  hold & spin {c['hold'] * 100:.2f}%")
    print(f"  jackpot EV {s['jp_ev'] * 100:.2f}% (realised {c['jackpot'] * 100:.2f}%)   "
          f"wheel jackpot EV {s['wjp_ev'] * 100:.2f}% (realised {c['wheel_jackpot'] * 100:.2f}%)")
    print(f"  progressive EV {s['prog_ev'] * 100:.2f}% (realised {c['progressive'] * 100:.2f}%)   "
          f"collection EV {s['collect_ev'] * 100:.2f}% (realised {c['collection'] * 100:.2f}%)")
    sp = s["spins"]
    print(f"  free spins 1 in {sp / max(1, n['bonus']):,.0f}   hold & spin 1 in {sp / max(1, n['hold']):,.0f}   "
          f"tea wheel 1 in {sp / max(1, n['wheel']):,.0f}   surprise wilds {n['surprise'] / sp * 100:.2f}%")
    print(f"  jackpots {n['jackpots']}+{n['wheel_jackpots']} wheel   progressive hits {n['prog_hits']}   "
          f"collection sets {n['sets']}")
    if s["mode"] == "megaways":
        print(f"  avg cascades/spin {n['cascades'] / sp:.3f}   max ways seen {n['max_ways']:,}")
    print(f"  biggest round {s['biggest']:,.2f}   end progressive pot {s['end_pot']:,.2f}   "
          f"end pool (internal) {s['end_pool']:,.2f}\n")


def main() -> int:
    spins = int(sys.argv[1]) if len(sys.argv) > 1 else 300_000
    mode = sys.argv[2] if len(sys.argv) > 2 else "both"
    ok = True
    for m in (game.MODES if mode == "both" else (mode,)):
        s = simulate(spins, m)
        report(s)
        in_band = abs(s["rtp_ev"] - TARGET_RTP) <= TOLERANCE
        hit_ok = 0.25 <= s["hit"] <= 0.35
        ok = ok and in_band and hit_ok
        if not hit_ok:
            print(f"  NOTE: hit frequency {s['hit']*100:.2f}% is outside the 25–35% aim.\n")
    lo, hi = (TARGET_RTP - TOLERANCE) * 100, (TARGET_RTP + TOLERANCE) * 100
    print("Result:", "PASS — expected RTP within "
          f"{lo:.1f}–{hi:.1f}% and hit frequency in range." if ok
          else "FAIL — expected RTP or hit frequency outside target.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
