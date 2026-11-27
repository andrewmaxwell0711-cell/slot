"""Punto Banco baccarat: 8-deck shoe, standard third-card rules.

Payouts (virtual coins, no cash value):
  Player 1:1, Banker 0.95:1 (5% commission), Tie 8:1,
  optional Player Pair / Banker Pair 11:1 on the first two cards.
All randomness uses secrets.SystemRandom. Player/Banker bets push on a tie.
"""

from __future__ import annotations

import json
from typing import Any

import secrets

_rng = secrets.SystemRandom()

DECKS = 8
RESHUFFLE_AT = 52
RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
SUITS = ("hearts", "diamonds", "clubs", "spades")
# 1:1, 0.95:1, 8:1, 11:1 — commission is 5% of the banker win, exact for BETS.
PLAYER_ODDS = (1, 1)       # profit = stake * 1 / 1
BANKER_ODDS = (95, 100)    # profit = stake * 95 / 100
TIE_ODDS = (8, 1)
PAIR_ODDS = (11, 1)
SPOTS = ("player", "banker", "tie", "player_pair", "banker_pair")
ROAD_LIMIT = 64


def _card_value(rank: str) -> int:
    if rank in ("10", "J", "Q", "K"):
        return 0
    if rank == "A":
        return 1
    return int(rank)


def point(cards: list[dict[str, Any]]) -> int:
    return sum(_card_value(c["rank"]) for c in cards) % 10


def is_pair(cards: list[dict[str, Any]]) -> bool:
    return len(cards) >= 2 and cards[0]["rank"] == cards[1]["rank"]


def is_natural(cards: list[dict[str, Any]]) -> bool:
    return len(cards) == 2 and point(cards) in (8, 9)


def player_draws_third(player_total: int) -> bool:
    """Player draws on 0–5, stands on 6–7. Naturals are handled first."""
    return int(player_total) <= 5


def banker_draws_third(banker_total: int, player_third: int | None) -> bool:
    """Standard Punto Banco banker third-card chart.

    If the player stood (player_third is None), banker draws on 0–5 and
    stands on 6–7. If the player drew a third card with value P:
      0–2 always draw; 3 unless P=8; 4 if P in 2–7; 5 if P in 4–7;
      6 if P in 6–7; 7 always stands.
    """
    b = int(banker_total)
    if b >= 8:
        return False
    if player_third is None:
        return b <= 5
    p = int(player_third)
    if b <= 2:
        return True
    if b == 3:
        return p != 8
    if b == 4:
        return p in (2, 3, 4, 5, 6, 7)
    if b == 5:
        return p in (4, 5, 6, 7)
    if b == 6:
        return p in (6, 7)
    return False


def _fresh_shoe() -> list[dict[str, Any]]:
    cards = [
        {
            "rank": rank,
            "suit": suit,
            "colour": "red" if suit in ("hearts", "diamonds") else "black",
            "value": _card_value(rank),
        }
        for _ in range(DECKS)
        for suit in SUITS
        for rank in RANKS
    ]
    _rng.shuffle(cards)
    return cards


def _draw(shoe: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if len(shoe) < 1:
        shoe = _fresh_shoe()
    card = shoe[0]
    return card, shoe[1:]


def _profit(stake: int, odds: tuple[int, int]) -> int:
    num, den = odds
    return int(stake) * int(num) // int(den)


def _clean_bets(raw: Any) -> dict[str, int]:
    from side import BETS, SideError

    src = raw or {}
    if not isinstance(src, dict):
        raise SideError("Place Player, Banker, Tie or Pair bets")
    bets = {spot: 0 for spot in SPOTS}
    for spot in SPOTS:
        val = src.get(spot) or src.get(spot.replace("_", "")) or 0
        try:
            amt = int(val)
        except (TypeError, ValueError):
            raise SideError("Bets must be whole coins")
        if amt < 0:
            raise SideError("Bets cannot be negative")
        if amt and amt not in BETS:
            raise SideError("Choose one of the listed coin stakes")
        bets[spot] = amt
    if sum(bets.values()) <= 0:
        raise SideError("Place at least one baccarat bet")
    return bets


def _why(player: list, banker: list, winner: str, natural: bool, p_drew: bool, b_drew: bool) -> str:
    pp, bp = point(player), point(banker)
    bits = [f"Player {pp}", f"Banker {bp}"]
    if natural:
        who = "Player" if pp > bp else ("Banker" if bp > pp else "Both")
        bits.append(f"{who} natural {max(pp, bp)}")
    else:
        if p_drew:
            bits.append(f"Player drew {player[2]['rank']} for {pp}")
        else:
            bits.append(f"Player stood on {point(player[:2])}")
        if b_drew:
            bits.append(f"Banker drew {banker[2]['rank']} for {bp}")
        else:
            bits.append(f"Banker stood on {point(banker[:2])}")
    if winner == "tie":
        bits.append("Tie — Player and Banker bets push")
    elif winner == "player":
        bits.append("Player wins")
    else:
        bits.append("Banker wins (5% commission on the win)")
    if is_pair(player):
        bits.append("Player pair")
    if is_pair(banker):
        bits.append("Banker pair")
    return ". ".join(bits) + "."


def deal(bets: Any, shoe: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Deal one Punto Banco hand from an 8-deck shoe and settle all bets."""
    from side import SideError

    bets = _clean_bets(bets)
    shoe = list(shoe or [])
    if len(shoe) < RESHUFFLE_AT:
        shoe = _fresh_shoe()

    # Standard deal order: Player, Banker, Player, Banker.
    p1, shoe = _draw(shoe)
    b1, shoe = _draw(shoe)
    p2, shoe = _draw(shoe)
    b2, shoe = _draw(shoe)
    player = [p1, p2]
    banker = [b1, b2]
    p_two, b_two = point(player), point(banker)
    natural = p_two in (8, 9) or b_two in (8, 9)
    p_drew = b_drew = False
    if not natural:
        if player_draws_third(p_two):
            card, shoe = _draw(shoe)
            player.append(card)
            p_drew = True
        p_third = _card_value(player[2]["rank"]) if p_drew else None
        if banker_draws_third(b_two, p_third):
            card, shoe = _draw(shoe)
            banker.append(card)
            b_drew = True

    pp, bp = point(player), point(banker)
    if pp > bp:
        winner = "player"
    elif bp > pp:
        winner = "banker"
    else:
        winner = "tie"
    ppair, bpair = is_pair(player), is_pair(banker)

    breakdown: list[dict[str, Any]] = []
    payout = 0

    def settle(spot: str, won: bool, odds: tuple[int, int], push: bool = False) -> None:
        nonlocal payout
        stake = bets[spot]
        if stake <= 0:
            return
        if push:
            paid = stake
            outcome = "push"
        elif won:
            paid = stake + _profit(stake, odds)
            outcome = "win"
        else:
            paid = 0
            outcome = "lose"
        payout += paid
        breakdown.append({"spot": spot, "stake": stake, "payout": paid, "outcome": outcome})

    settle("player", winner == "player", PLAYER_ODDS, push=(winner == "tie"))
    settle("banker", winner == "banker", BANKER_ODDS, push=(winner == "tie"))
    settle("tie", winner == "tie", TIE_ODDS)
    settle("player_pair", ppair, PAIR_ODDS)
    settle("banker_pair", bpair, PAIR_ODDS)

    why = _why(player, banker, winner, natural, p_drew, b_drew)
    result = {
        "game": "baccarat",
        "done": True,
        "bets": bets,
        "bet": sum(bets.values()),
        "payout": payout,
        "player": player,
        "banker": banker,
        "player_point": pp,
        "banker_point": bp,
        "player_pair": ppair,
        "banker_pair": bpair,
        "natural": natural,
        "player_drew": p_drew,
        "banker_drew": b_drew,
        "winner": winner,
        "why": why,
        "breakdown": breakdown,
        "result": why,
        "shoe_left": len(shoe),
        "reshuffled": len(shoe) < RESHUFFLE_AT,  # next hand will reshuffle
    }
    result["_shoe"] = shoe
    return result


def ensure_schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS baccarat_shoes (
            player_id TEXT PRIMARY KEY,
            shoe TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS baccarat_road (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            road TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    row = conn.execute("SELECT id FROM baccarat_road WHERE id = 1").fetchone()
    if not row:
        conn.execute(
            "INSERT INTO baccarat_road (id, road, updated_at) VALUES (1, '[]', ?)",
            (__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),),
        )


def load_shoe(conn, player_id: str) -> list[dict[str, Any]]:
    row = conn.execute("SELECT shoe FROM baccarat_shoes WHERE player_id = ?", (player_id,)).fetchone()
    if not row:
        return []
    try:
        data = json.loads(row["shoe"])
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_shoe(conn, player_id: str, shoe: list[dict[str, Any]]) -> None:
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO baccarat_shoes (player_id, shoe, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT (player_id) DO UPDATE SET shoe = excluded.shoe, updated_at = excluded.updated_at
        """,
        (player_id, json.dumps(shoe), now),
    )


def load_road(conn) -> list[dict[str, Any]]:
    row = conn.execute("SELECT road FROM baccarat_road WHERE id = 1").fetchone()
    if not row:
        return []
    try:
        data = json.loads(row["road"])
        return data if isinstance(data, list) else []
    except Exception:
        return []


def append_road(conn, entry: dict[str, Any]) -> list[dict[str, Any]]:
    road = load_road(conn)
    road.append(entry)
    road = road[-ROAD_LIMIT:]
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    conn.execute(
        "UPDATE baccarat_road SET road = ?, updated_at = ? WHERE id = 1",
        (json.dumps(road), now),
    )
    return road


def public_road_entry(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "winner": result["winner"],
        "player_point": result["player_point"],
        "banker_point": result["banker_point"],
        "player_pair": bool(result["player_pair"]),
        "banker_pair": bool(result["banker_pair"]),
        "natural": bool(result["natural"]),
    }


def catalogue_block() -> dict[str, Any]:
    return {
        "decks": DECKS,
        "reshuffle_at": RESHUFFLE_AT,
        "payouts": {
            "player": "1:1",
            "banker": "0.95:1 (5% commission)",
            "tie": "8:1",
            "player_pair": "11:1",
            "banker_pair": "11:1",
        },
        "rules": (
            "Punto Banco, 8-deck shoe. Cards 10/J/Q/K count 0, Ace counts 1, "
            "totals are modulo 10. Naturals (8 or 9) stand. Player draws on 0–5 "
            "and stands on 6–7. Banker uses the standard third-card chart. "
            "Player and Banker bets push on a Tie. Pair bets pay on the first "
            "two cards of that hand. Coins have no cash value."
        ),
        "spots": list(SPOTS),
    }
