#!/usr/bin/env python3
"""Monte Carlo check of Crystal Casino return-to-player, both modes.

Runs the live round code (game.play_megaways / game.play_classic, incl.
cascades, free spins, Crystal Pick and Tea Wheel) through the same
settlement as the ledger (game.settle_steps). There is no payout cap.
The Green Tea Jackpot is a fixed multiple of total bet (game.JACKPOT_MULT).

    python server/simulate_rtp.py [spins] [mode megaways|classic|both]

Jackpots are rare, so the PASS check uses the expected-value RTP
(jackpots at their exact EV, everything else realised). Target 95% ± 0.5 pp.
"""

from __future__ import annotations

import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))

import game  # noqa: E402

TARGET_RTP = 0.95
TOLERANCE = 0.005  # 94.5–95.5%


def simulate(spins: int, mode: str = "megaways") -> dict:
    pool = 0.0
    stake = 1.0
    cats = {k: 0.0 for k in ("base", "scatter", "free", "pick", "wheel", "jackpot", "wheel_jackpot")}
    jp_ev = wjp_ev = 0.0
    staked = won = 0.0
    hits = 0
    n = {"bonus": 0, "pick": 0, "wheel": 0, "jackpots": 0, "wheel_jackpots": 0, "cascades": 0, "max_ways": 0, "pending": 0}
    biggest = 0.0
    for _ in range(spins):
        rnd = game.play_megaways(stake) if mode == "megaways" else game.play_classic(stake / 25, 25)
        staked += stake
        pool += stake
        p_hit = game.jackpot_probability(stake, pool)
        hit = game._rng.random() < p_hit
        steps = game.round_steps(rnd)
        flags = {}

        def wroll(s, p):
            q = game.wheel_jackpot_probability(s, p)
            flags["q"] = q
            return game._rng.random() < q

        settled = game.settle_steps(rnd, stake, pool, hit, wroll)
        jp_ev += p_hit * game.jackpot_amount(stake)
        pool = settled["pool_after"]
        assert pool >= -1e-9
        won += settled["total_paid_aud"]
        biggest = max(biggest, settled["total_paid_aud"])
        if rnd["free_spins"]:
            n["bonus"] += 1
        b = rnd["base"]
        n["cascades"] += b.get("cascades", 0)
        n["max_ways"] = max(n["max_ways"], b.get("ways", 0))
        if settled["total_paid_aud"] > 0 or rnd.get("free_spins") or rnd.get("minigames"):
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
                if st.get("jackpot_pending"):
                    n["pending"] += 1
                    wjp_ev += flags["q"] * game.jackpot_amount(stake)
            else:
                cats["free"] += se["paid_aud"]
    rtp_ev = (won - cats["jackpot"] - cats["wheel_jackpot"] + jp_ev + wjp_ev) / staked
    return {
        "mode": mode, "spins": spins, "staked": staked, "won": won,
        "rtp": won / staked, "rtp_ev": rtp_ev, "hit": hits / spins,
        "cats": {k: v / staked for k, v in cats.items()},
        "jp_ev": jp_ev / staked, "wjp_ev": wjp_ev / staked,
        "n": n, "biggest": biggest, "end_pool": pool,
    }


def report(s: dict) -> None:
    c, n = s["cats"], s["n"]
    print(f"== {s['mode'].upper()} · {s['spins']:,} spins at A$1 (uncapped) ==")
    print(f"Realised RTP {s['rtp'] * 100:.3f}%   Expected-value RTP {s['rtp_ev'] * 100:.3f}%   "
          f"hit frequency {s['hit'] * 100:.2f}%")
    print(f"  base {c['base'] * 100:.2f}%  scatter {c['scatter'] * 100:.2f}%  free spins {c['free'] * 100:.2f}%  "
          f"crystal pick {c['pick'] * 100:.2f}%  tea wheel {c['wheel'] * 100:.2f}%")
    print(f"  jackpot EV {s['jp_ev'] * 100:.2f}% (realised {c['jackpot'] * 100:.2f}%)   "
          f"wheel jackpot EV {s['wjp_ev'] * 100:.2f}% (realised {c['wheel_jackpot'] * 100:.2f}%)")
    sp = s["spins"]
    print(f"  free spins 1 in {sp / max(1, n['bonus']):,.0f}   crystal pick 1 in {sp / max(1, n['pick']):,.0f}   "
          f"tea wheel 1 in {sp / max(1, n['wheel']):,.0f}   jackpots {n['jackpots']}+{n['wheel_jackpots']} wheel")
    if s["mode"] == "megaways":
        print(f"  avg cascades/spin {n['cascades'] / sp:.3f}   max ways seen {n['max_ways']:,}")
    print(f"  biggest round {s['biggest']:,.2f}   end pool (internal stat) {s['end_pool']:,.2f}\n")


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
