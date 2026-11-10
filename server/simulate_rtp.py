#!/usr/bin/env python3
"""Monte Carlo check of Crystal Casino return-to-player, both modes.

Runs the live round code (game.play_megaways / game.play_classic, incl.
cascades, free spins, Crystal Pick and Tea Wheel) through the same
settlement as the ledger (game.settle_steps): every step capped at 20% of
the pool, Green Tea Jackpot paying exactly the cap.

    python server/simulate_rtp.py [spins] [mode megaways|classic|both] [start_pool]

Jackpots are pool-scaled and very rare, so the PASS check uses the
expected-value RTP (jackpots at their exact EV, everything else realised).
Target 20% ± 1 pp.
"""

from __future__ import annotations

import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))

import game  # noqa: E402

TARGET_RTP = 0.20
TOLERANCE = 0.01


def simulate(spins: int, mode: str = "megaways", start_pool: float = 0.0) -> dict:
    pool = start_pool
    stake = 1.0
    cats = {k: 0.0 for k in ("base", "scatter", "free", "pick", "wheel", "jackpot", "wheel_jackpot")}
    jp_ev = wjp_ev = 0.0
    staked = won = 0.0
    n = {"bonus": 0, "pick": 0, "wheel": 0, "jackpots": 0, "wheel_jackpots": 0, "capped": 0, "cascades": 0, "max_ways": 0}
    biggest = 0.0
    for _ in range(spins):
        rnd = game.play_megaways(stake) if mode == "megaways" else game.play_classic(stake / 25, 25)
        staked += stake
        pool += stake
        p_hit = game.jackpot_probability(stake, pool)
        hit = game._rng.random() < p_hit
        steps = game.round_steps(rnd)
        # analytic EVs for both jackpot kinds (evaluated against the pool at that step)
        flags = {}

        def wroll(s, p):
            q = game.wheel_jackpot_probability(s, p)
            flags["q"] = q
            flags["cap"] = game.cap_for_pool(p)
            return game._rng.random() < q

        cap0 = game.cap_for_pool(pool)
        settled = game.settle_steps(rnd, stake, pool, hit, wroll)
        base_paid_nojp = min(round(rnd["base"]["raw_win_aud"], 2), cap0)
        jp_ev += p_hit * max(0.0, cap0 - base_paid_nojp)
        pool = settled["pool_after"]
        assert pool >= -1e-9
        won += settled["total_paid_aud"]
        biggest = max(biggest, settled["total_paid_aud"])
        if rnd["free_spins"]:
            n["bonus"] += 1
        b = rnd["base"]
        n["cascades"] += b.get("cascades", 0)
        n["max_ways"] = max(n["max_ways"], b.get("ways", 0))
        for st, se in zip(steps, settled["steps"]):
            n["capped"] += se["capped"]
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
                if st.get("jackpot_pending"):
                    fb = min(round(st["raw_win_aud"], 2), flags["cap"])
                    # EV of the wedge = q*cap + (1-q)*fallback; realised fallback counted in "wheel"
                    wjp_ev += flags["q"] * (flags["cap"] - fb)
            else:
                cats["free"] += se["paid_aud"]
    rtp_ev = (won - cats["jackpot"] - cats["wheel_jackpot"] + jp_ev + wjp_ev) / staked
    return {"mode": mode, "spins": spins, "staked": staked, "won": won, "rtp": won / staked, "rtp_ev": rtp_ev,
            "cats": {k: v / staked for k, v in cats.items()}, "jp_ev": jp_ev / staked, "wjp_ev": wjp_ev / staked,
            "n": n, "biggest": biggest, "end_pool": pool}


def report(s: dict, start_pool: float) -> None:
    c, n = s["cats"], s["n"]
    print(f"== {s['mode'].upper()} · {s['spins']:,} spins at A$1 · pool starts at {start_pool:,.0f} ==")
    print(f"Realised RTP {s['rtp'] * 100:.3f}%   Expected-value RTP {s['rtp_ev'] * 100:.3f}%")
    print(f"  base {c['base'] * 100:.2f}%  scatter {c['scatter'] * 100:.2f}%  free spins {c['free'] * 100:.2f}%  "
          f"crystal pick {c['pick'] * 100:.2f}%  tea wheel {c['wheel'] * 100:.2f}%")
    print(f"  jackpot EV {s['jp_ev'] * 100:.2f}% (realised {c['jackpot'] * 100:.2f}%)   "
          f"wheel jackpot EV {s['wjp_ev'] * 100:.2f}% (realised {c['wheel_jackpot'] * 100:.2f}%)")
    sp = s["spins"]
    print(f"  free spins 1 in {sp / max(1, n['bonus']):,.0f}   crystal pick 1 in {sp / max(1, n['pick']):,.0f}   "
          f"tea wheel 1 in {sp / max(1, n['wheel']):,.0f}   jackpots {n['jackpots']}+{n['wheel_jackpots']} wheel")
    if s["mode"] == "megaways":
        print(f"  avg cascades/spin {n['cascades'] / sp:.3f}   max ways seen {n['max_ways']:,}")
    print(f"  capped steps {n['capped']}   biggest round {s['biggest']:,.2f}   end pool {s['end_pool']:,.2f}\n")


def main() -> int:
    spins = int(sys.argv[1]) if len(sys.argv) > 1 else 300_000
    mode = sys.argv[2] if len(sys.argv) > 2 else "both"
    start_pool = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
    ok = True
    for m in (game.MODES if mode == "both" else (mode,)):
        s = simulate(spins, m, start_pool)
        report(s, start_pool)
        ok = ok and abs(s["rtp_ev"] - TARGET_RTP) <= TOLERANCE
    print("Result:", "PASS — expected RTP within ±1 pp of 20%." if ok else "FAIL — outside ±1 pp of 20%.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
