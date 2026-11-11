"""Fair side games: blackjack, European roulette, high card, crystal mines,
dragon scratch and lucky dice. All randomness uses secrets.SystemRandom.
Bets and payouts are in integer coins. Outcomes are fully determined here;
the client only animates the result it is sent.
"""

from __future__ import annotations

import secrets
from typing import Any

_rng = secrets.SystemRandom()

# Standard coin stakes offered in the lobby (virtual coins, no cash value).
BETS = (100, 200, 500, 1_000, 2_000, 5_000, 10_000, 25_000, 50_000)

GAMES = ("blackjack", "roulette", "highcard", "mines", "scratch", "dice")

SUITS = ("hearts", "diamonds", "clubs", "spades")
RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
RANK_VALUE = {**{str(n): n for n in range(2, 11)}, "J": 10, "Q": 10, "K": 10, "A": 11}
RANK_ORDER = {r: i for i, r in enumerate(RANKS, start=1)}  # A is low here; high-card uses Ace-high below
ACE_HIGH = {**{str(n): n for n in range(2, 11)}, "J": 11, "Q": 12, "K": 13, "A": 14}

# European roulette
ROUGE = frozenset({1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36})
NOIR = frozenset(n for n in range(1, 37) if n not in ROUGE)
# Wheel order (European cylinder), used for honest animation of the landing pocket.
WHEEL_ORDER = (
    0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10,
    5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26,
)

# Crystal Mines: 5×5, player chooses 1–5 mines, house edge ~4%.
MINES_SIZE = 25
MINES_MIN, MINES_MAX = 1, 5
MINES_EDGE = 0.04

# Dragon Scratch: 3×3 card, ~95% RTP from the prize table.
SCRATCH_SIZE = 9
SCRATCH_ROWS = 3
# Overall prize in × bet, with weights tuned so EV ≈ 0.95.
SCRATCH_PRIZES = (
    (0.0, 512.5), (0.5, 180), (1.0, 147.5), (2.0, 80), (3.0, 40),
    (5.0, 22), (10.0, 12), (25.0, 4.5), (50.0, 1.2), (100.0, 0.3),
)

# Lucky Dice: 2d6 vs dealer, higher total wins 1:1, tie is a push (fair).
DICE_SIDES = 6
DICE_COUNT = 2


class SideError(ValueError):
    pass


def catalogue() -> dict[str, Any]:
    return {
        "bets": list(BETS),
        "games": [
            {"id": "blackjack", "name": "Blackjack", "tag": "3:2 · stand soft 17 · 6-deck"},
            {"id": "roulette", "name": "European Roulette", "tag": "Single zero · 2.70% house edge"},
            {"id": "highcard", "name": "High Card", "tag": "Higher card wins 1:1 · tie push or war"},
            {"id": "mines", "name": "Crystal Mines", "tag": "Cash out anytime · ~4% house edge"},
            {"id": "scratch", "name": "Dragon Scratch", "tag": "Scratch card · ~95% RTP"},
            {"id": "dice", "name": "Lucky Dice", "tag": "2d6 duel · tie is a push"},
        ],
        "roulette": {
            "wheel": list(WHEEL_ORDER),
            "red": sorted(ROUGE),
            "payouts": {
                "straight": 35, "split": 17, "street": 11, "corner": 8, "line": 5,
                "dozen": 2, "column": 2, "red": 1, "black": 1, "odd": 1, "even": 1,
                "high": 1, "low": 1,
            },
        },
        "mines": {"size": MINES_SIZE, "min_mines": MINES_MIN, "max_mines": MINES_MAX, "edge": MINES_EDGE},
        "scratch": {"size": SCRATCH_SIZE, "rtp": 0.95},
        "dice": {"sides": DICE_SIDES, "count": DICE_COUNT},
        "blackjack": {
            "decks": 6, "soft_17": "stand", "blackjack_pays": "3:2",
            "insurance": True, "double": True, "split": True,
        },
    }


def valid_bet(coins: int) -> int:
    try:
        n = int(coins)
    except (TypeError, ValueError) as exc:
        raise SideError("Invalid bet") from exc
    if n <= 0:
        raise SideError("Invalid bet")
    return n


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------

def _card(rank: str, suit: str) -> dict[str, Any]:
    return {"rank": rank, "suit": suit, "value": RANK_VALUE[rank], "colour": "red" if suit in ("hearts", "diamonds") else "black"}


def _fresh_shoe(decks: int = 6) -> list[dict[str, Any]]:
    shoe = [_card(r, s) for _ in range(decks) for s in SUITS for r in RANKS]
    _rng.shuffle(shoe)
    return shoe


def _draw(shoe: list[dict[str, Any]]) -> dict[str, Any]:
    if not shoe:
        raise SideError("Shoe is empty")
    return shoe.pop()


def hand_value(cards: list[dict[str, Any]]) -> int:
    total = 0
    aces = 0
    for c in cards:
        if c["rank"] == "A":
            aces += 1
            total += 11
        else:
            total += int(c["value"])
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def is_soft(cards: list[dict[str, Any]]) -> bool:
    total = 0
    aces = 0
    for c in cards:
        if c["rank"] == "A":
            aces += 1
            total += 11
        else:
            total += int(c["value"])
    return aces > 0 and total <= 21 and total >= 11


def is_blackjack(cards: list[dict[str, Any]]) -> bool:
    return len(cards) == 2 and hand_value(cards) == 21


# ---------------------------------------------------------------------------
# Blackjack
# ---------------------------------------------------------------------------

def _bj_public(state: dict[str, Any], hide_hole: bool = True) -> dict[str, Any]:
    dealer = list(state["dealer"])
    if hide_hole and not state.get("done") and len(dealer) >= 2:
        shown = [dealer[0], {"rank": "?", "suit": "back", "value": 0, "colour": "back", "hidden": True}]
        dealer_total = None
    else:
        shown = dealer
        dealer_total = hand_value(dealer)
    hands = []
    for h in state["hands"]:
        hands.append({
            "cards": h["cards"],
            "total": hand_value(h["cards"]),
            "stood": bool(h.get("stood")),
            "bust": hand_value(h["cards"]) > 21,
            "blackjack": bool(h.get("from_deal")) and is_blackjack(h["cards"]),
            "doubled": bool(h.get("doubled")),
            "bet": int(h["bet"]),
            "payout": h.get("payout"),
            "result": h.get("result"),
        })
    return {
        "game": "blackjack",
        "hands": hands,
        "active": state.get("active", 0),
        "dealer": shown,
        "dealer_total": dealer_total,
        "insurance_offered": bool(state.get("insurance_offered")),
        "insurance_bet": int(state.get("insurance_bet") or 0),
        "insurance_payout": state.get("insurance_payout"),
        "done": bool(state.get("done")),
        "payout": int(state.get("payout") or 0),
        "bet": int(state.get("bet") or 0),
        "can": _bj_actions(state) if not state.get("done") else [],
    }


def _bj_actions(state: dict[str, Any]) -> list[str]:
    if state.get("done"):
        return []
    if state.get("insurance_offered") and state.get("insurance_bet") is None:
        return ["insurance", "no_insurance"]
    i = state.get("active", 0)
    if i >= len(state["hands"]):
        return []
    h = state["hands"][i]
    if h.get("stood") or hand_value(h["cards"]) >= 21:
        return []
    acts = ["hit", "stand"]
    if len(h["cards"]) == 2 and not h.get("doubled"):
        acts.append("double")
        if (not state.get("has_split")
                and h["cards"][0]["rank"] == h["cards"][1]["rank"]
                and len(state["hands"]) == 1):
            acts.append("split")
    return acts


def _bj_settle_hand(player: list[dict], dealer: list[dict], bet: int, from_split: bool) -> tuple[int, str]:
    pv, dv = hand_value(player), hand_value(dealer)
    pbj = (not from_split) and is_blackjack(player)
    dbj = is_blackjack(dealer)
    if pbj and dbj:
        return bet, "push"
    if pbj:
        return bet + (bet * 3) // 2, "blackjack"
    if dbj:
        return 0, "lose"
    if pv > 21:
        return 0, "bust"
    if dv > 21:
        return bet * 2, "win"
    if pv > dv:
        return bet * 2, "win"
    if pv == dv:
        return bet, "push"
    return 0, "lose"


def _bj_finish(state: dict[str, Any]) -> dict[str, Any]:
    shoe = state["shoe"]
    dealer = state["dealer"]
    # Peek already handled; complete dealer hand unless every player hand is bust
    # or original blackjack vs no dealer BJ (already settled in deal).
    need = any(hand_value(h["cards"]) <= 21 for h in state["hands"])
    if need:
        while True:
            tot = hand_value(dealer)
            if tot > 17:
                break
            if tot == 17 and not is_soft(dealer):
                break
            if tot == 17 and is_soft(dealer):
                break  # stands on soft 17
            if tot < 17:
                dealer.append(_draw(shoe))
                continue
            break
    total_payout = 0
    from_split = bool(state.get("has_split"))
    for h in state["hands"]:
        pay, result = _bj_settle_hand(h["cards"], dealer, int(h["bet"]), from_split or not h.get("from_deal", True))
        # Split tens that make 21 are not blackjack.
        if from_split and is_blackjack(h["cards"]) and result == "blackjack":
            pay, result = (h["bet"] * 2, "win") if hand_value(dealer) != 21 or len(dealer) > 2 else (h["bet"], "push")
        h["payout"] = pay
        h["result"] = result
        total_payout += pay
    ins = int(state.get("insurance_bet") or 0)
    ins_pay = 0
    if ins:
        if is_blackjack(dealer):
            ins_pay = ins * 3  # 2:1 plus returned stake
        state["insurance_payout"] = ins_pay
        total_payout += ins_pay
    state["payout"] = int(total_payout)
    state["done"] = True
    state["active"] = len(state["hands"])
    return state


def _bj_advance(state: dict[str, Any]) -> dict[str, Any]:
    while state["active"] < len(state["hands"]):
        h = state["hands"][state["active"]]
        if h.get("stood") or hand_value(h["cards"]) >= 21:
            h["stood"] = True
            state["active"] += 1
            continue
        break
    if state["active"] >= len(state["hands"]):
        return _bj_finish(state)
    return state


def blackjack_deal(bet: int) -> dict[str, Any]:
    bet = valid_bet(bet)
    shoe = _fresh_shoe(6)
    player = [_draw(shoe), _draw(shoe)]
    dealer = [_draw(shoe), _draw(shoe)]
    state: dict[str, Any] = {
        "game": "blackjack",
        "shoe": shoe,
        "hands": [{"cards": player, "bet": bet, "stood": False, "doubled": False, "from_deal": True}],
        "dealer": dealer,
        "active": 0,
        "bet": bet,
        "has_split": False,
        "insurance_offered": dealer[0]["rank"] == "A",
        "insurance_bet": None,
        "done": False,
        "payout": 0,
    }
    # Peek for dealer blackjack when upcard is Ace or ten-value.
    up = dealer[0]
    if up["rank"] == "A" or up["value"] == 10:
        if is_blackjack(dealer):
            # Insurance is still resolved if offered; then settle immediately.
            if not state["insurance_offered"]:
                return _bj_finish(state)
            # Wait for insurance decision, then finish (see act).
            state["dealer_bj_peek"] = True
            return state
    if is_blackjack(player) and not state["insurance_offered"]:
        return _bj_finish(state)
    if state["insurance_offered"]:
        return state
    return state


def blackjack_act(state: dict[str, Any], action: str, extra_bet: int = 0) -> dict[str, Any]:
    if state.get("done"):
        raise SideError("Hand is already finished")
    action = str(action or "").lower().strip()
    allowed = _bj_actions(state)
    if action not in allowed:
        raise SideError(f"Cannot {action or 'act'} now")

    if action in ("insurance", "no_insurance"):
        if action == "insurance":
            # Half the original bet, 2:1 if dealer has blackjack.
            ins = int(state["bet"]) // 2
            if ins <= 0:
                raise SideError("Invalid insurance")
            state["insurance_bet"] = ins
        else:
            state["insurance_bet"] = 0
        state["insurance_offered"] = False
        if state.get("dealer_bj_peek") or is_blackjack(state["dealer"]):
            return _bj_finish(state)
        if is_blackjack(state["hands"][0]["cards"]) and not state.get("has_split"):
            return _bj_finish(state)
        return state

    i = state["active"]
    h = state["hands"][i]
    shoe = state["shoe"]

    if action == "hit":
        h["cards"].append(_draw(shoe))
        if hand_value(h["cards"]) >= 21:
            h["stood"] = True
            return _bj_advance(state)
        return state

    if action == "stand":
        h["stood"] = True
        return _bj_advance(state)

    if action == "double":
        # extra_bet must equal the hand bet; ledger checks funds.
        if extra_bet and int(extra_bet) != int(h["bet"]):
            raise SideError("Double must match the hand bet")
        h["bet"] = int(h["bet"])
        h["doubled"] = True
        h["cards"].append(_draw(shoe))
        h["stood"] = True
        return _bj_advance(state)

    if action == "split":
        if extra_bet and int(extra_bet) != int(h["bet"]):
            raise SideError("Split must match the original bet")
        a, b = h["cards"]
        h["cards"] = [a, _draw(shoe)]
        h["from_deal"] = False
        other = {"cards": [b, _draw(shoe)], "bet": int(h["bet"]), "stood": False, "doubled": False, "from_deal": False}
        state["hands"] = [h, other]
        state["has_split"] = True
        # Split aces: one card each, then stand.
        if a["rank"] == "A":
            h["stood"] = True
            other["stood"] = True
            return _bj_advance(state)
        return _bj_advance(state)

    raise SideError("Unknown action")


def blackjack_extra_needed(state: dict[str, Any], action: str) -> int:
    action = str(action or "").lower()
    if action == "insurance":
        return int(state["bet"]) // 2
    if action in ("double", "split"):
        i = state.get("active", 0)
        if i < len(state["hands"]):
            return int(state["hands"][i]["bet"])
    return 0


def blackjack_debit_on_deal(bet: int) -> int:
    return valid_bet(bet)


# ---------------------------------------------------------------------------
# European Roulette
# ---------------------------------------------------------------------------

def _neighbours(n: int) -> set[int]:
    """Numeric (table) neighbours for split validation, plus 0 with 1, 2, 3."""
    if n == 0:
        return {1, 2, 3}
    out = set()
    if n - 1 >= 1 and (n - 1) % 3 != 0:
        out.add(n - 1)
    if n + 1 <= 36 and n % 3 != 0:
        out.add(n + 1)
    if n - 3 >= 1:
        out.add(n - 3)
    if n + 3 <= 36:
        out.add(n + 3)
    if n in (1, 2, 3):
        out.add(0)
    return out


def _validate_roulette_bet(b: dict[str, Any]) -> dict[str, Any]:
    kind = str(b.get("kind") or b.get("type") or "").lower()
    amount = valid_bet(b.get("amount") or b.get("coins") or 0)
    numbers = b.get("numbers")
    if numbers is not None:
        try:
            numbers = [int(x) for x in numbers]
        except (TypeError, ValueError) as exc:
            raise SideError("Invalid numbers") from exc
    if kind == "straight":
        n = int(b["number"]) if b.get("number") is not None else (numbers[0] if numbers else -1)
        if n < 0 or n > 36:
            raise SideError("Straight is 0–36")
        return {"kind": "straight", "numbers": [n], "amount": amount, "payout": 35}
    if kind == "split":
        if not numbers or len(numbers) != 2:
            raise SideError("Split needs two adjacent numbers")
        a, c = numbers
        if a == c or a < 0 or c < 0 or a > 36 or c > 36 or (c not in _neighbours(a) and a not in _neighbours(c)):
            raise SideError("Split numbers must be adjacent")
        return {"kind": "split", "numbers": sorted([a, c]), "amount": amount, "payout": 17}
    if kind == "street":
        if not numbers or len(numbers) != 3:
            raise SideError("Street needs three numbers")
        ns = sorted(numbers)
        if ns[0] < 1 or ns[2] > 36 or ns[1] != ns[0] + 1 or ns[2] != ns[0] + 2 or (ns[0] - 1) % 3 != 0:
            raise SideError("Street must be a row of three")
        return {"kind": "street", "numbers": ns, "amount": amount, "payout": 11}
    if kind == "corner":
        if not numbers or len(numbers) != 4:
            raise SideError("Corner needs four numbers")
        ns = sorted(numbers)
        # 2×2 block: n, n+1, n+3, n+4 with n not on the right column.
        n = ns[0]
        if ns != sorted([n, n + 1, n + 3, n + 4]) or n % 3 == 0 or n < 1 or n + 4 > 36:
            raise SideError("Corner must be a 2×2 block")
        return {"kind": "corner", "numbers": ns, "amount": amount, "payout": 8}
    if kind == "line":
        if not numbers or len(numbers) != 6:
            raise SideError("Line needs six numbers")
        ns = sorted(numbers)
        n = ns[0]
        expect = list(range(n, n + 6))
        if ns != expect or (n - 1) % 3 != 0 or n < 1 or n + 5 > 36:
            raise SideError("Line must be two adjacent streets")
        return {"kind": "line", "numbers": ns, "amount": amount, "payout": 5}
    if kind in ("dozen",):
        d = int(b.get("dozen") or (numbers or [0])[0] if numbers else 0)
        if d not in (1, 2, 3):
            raise SideError("Dozen is 1, 2 or 3")
        lo = (d - 1) * 12 + 1
        return {"kind": "dozen", "dozen": d, "numbers": list(range(lo, lo + 12)), "amount": amount, "payout": 2}
    if kind in ("column",):
        c = int(b.get("column") or 0)
        if c not in (1, 2, 3):
            raise SideError("Column is 1, 2 or 3")
        return {"kind": "column", "column": c, "numbers": list(range(c, 37, 3)), "amount": amount, "payout": 2}
    if kind == "red":
        return {"kind": "red", "numbers": sorted(ROUGE), "amount": amount, "payout": 1}
    if kind == "black":
        return {"kind": "black", "numbers": sorted(NOIR), "amount": amount, "payout": 1}
    if kind == "odd":
        return {"kind": "odd", "numbers": list(range(1, 37, 2)), "amount": amount, "payout": 1}
    if kind == "even":
        return {"kind": "even", "numbers": list(range(2, 37, 2)), "amount": amount, "payout": 1}
    if kind == "low":
        return {"kind": "low", "numbers": list(range(1, 19)), "amount": amount, "payout": 1}
    if kind == "high":
        return {"kind": "high", "numbers": list(range(19, 37)), "amount": amount, "payout": 1}
    raise SideError("Unknown roulette bet")


def roulette_spin(bets: list[dict[str, Any]]) -> dict[str, Any]:
    if not bets:
        raise SideError("Place at least one bet")
    parsed = [_validate_roulette_bet(b) for b in bets]
    total = sum(b["amount"] for b in parsed)
    if total <= 0:
        raise SideError("Invalid bet")
    winning = _rng.randrange(0, 37)
    colour = "green" if winning == 0 else ("red" if winning in ROUGE else "black")
    results = []
    payout = 0
    for b in parsed:
        hit = winning in b["numbers"]
        win = (b["payout"] + 1) * b["amount"] if hit else 0
        payout += win
        results.append({**b, "hit": hit, "win": win})
    pocket = WHEEL_ORDER.index(winning)
    return {
        "game": "roulette",
        "done": True,
        "bet": total,
        "number": winning,
        "colour": colour,
        "pocket": pocket,
        "wheel": list(WHEEL_ORDER),
        "bets": results,
        "payout": payout,
    }


# ---------------------------------------------------------------------------
# High Card
# ---------------------------------------------------------------------------

def _draw_one() -> dict[str, Any]:
    return _card(_rng.choice(RANKS), _rng.choice(SUITS))


def highcard_play(bet: int, war: bool = False, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    bet = valid_bet(bet)
    if previous and previous.get("awaiting_war"):
        # War: extra equal stake already taken; deal a new card each.
        player = _draw_one()
        dealer = _draw_one()
        pr, dr = ACE_HIGH[player["rank"]], ACE_HIGH[dealer["rank"]]
        stake = int(previous["bet"]) * 2
        if pr > dr:
            payout, result = stake * 2, "win"
        elif pr < dr:
            payout, result = 0, "lose"
        else:
            payout, result = stake, "push"
        return {
            "game": "highcard", "done": True, "war": True,
            "player": player, "dealer": dealer,
            "bet": stake, "payout": payout, "result": result,
            "awaiting_war": False,
        }

    player = _draw_one()
    dealer = _draw_one()
    pr, dr = ACE_HIGH[player["rank"]], ACE_HIGH[dealer["rank"]]
    if pr > dr:
        return {"game": "highcard", "done": True, "war": False, "player": player, "dealer": dealer,
                "bet": bet, "payout": bet * 2, "result": "win", "awaiting_war": False}
    if pr < dr:
        return {"game": "highcard", "done": True, "war": False, "player": player, "dealer": dealer,
                "bet": bet, "payout": 0, "result": "lose", "awaiting_war": False}
    # Tie: push, or offer war.
    if war:
        # First deal was a tie; hold state so the client can confirm war or collect the push.
        return {"game": "highcard", "done": False, "war": False, "player": player, "dealer": dealer,
                "bet": bet, "payout": bet, "result": "tie", "awaiting_war": True, "can": ["war", "push"]}
    return {"game": "highcard", "done": True, "war": False, "player": player, "dealer": dealer,
            "bet": bet, "payout": bet, "result": "push", "awaiting_war": False}


# ---------------------------------------------------------------------------
# Crystal Mines
# ---------------------------------------------------------------------------

def mines_fair_multiplier(mines: int, picks: int) -> float:
    """Fair cash-out multiplier after `picks` safe tiles (no house edge)."""
    if picks <= 0:
        return 1.0
    if mines < MINES_MIN or mines > MINES_MAX:
        raise SideError("Mines must be 1–5")
    if picks > MINES_SIZE - mines:
        raise SideError("Too many picks")
    num = 1.0
    for t in range(picks):
        num *= (MINES_SIZE - t) / (MINES_SIZE - mines - t)
    return num


def mines_multiplier(mines: int, picks: int) -> float:
    return round(mines_fair_multiplier(mines, picks) * (1.0 - MINES_EDGE), 4)


def mines_start(bet: int, mines: int = 3) -> dict[str, Any]:
    bet = valid_bet(bet)
    mines = int(mines)
    if mines < MINES_MIN or mines > MINES_MAX:
        raise SideError("Mines must be 1–5")
    positions = list(range(MINES_SIZE))
    _rng.shuffle(positions)
    bombs = sorted(positions[:mines])
    return {
        "game": "mines",
        "done": False,
        "bet": bet,
        "mines": mines,
        "bombs": bombs,  # kept server-side; public view hides them
        "picks": [],
        "multiplier": 1.0,
        "payout": 0,
        "boom": False,
        "can": ["pick", "cashout"],
    }


def mines_public(state: dict[str, Any]) -> dict[str, Any]:
    reveal = bool(state.get("done"))
    return {
        "game": "mines",
        "done": bool(state.get("done")),
        "bet": int(state["bet"]),
        "mines": int(state["mines"]),
        "picks": list(state.get("picks") or []),
        "multiplier": float(state.get("multiplier") or 1.0),
        "payout": int(state.get("payout") or 0),
        "boom": bool(state.get("boom")),
        "bombs": list(state["bombs"]) if reveal else None,
        "can": [] if state.get("done") else ["pick", "cashout"],
        "next_multiplier": mines_multiplier(int(state["mines"]), len(state.get("picks") or []) + 1)
        if not state.get("done") and len(state.get("picks") or []) + 1 <= MINES_SIZE - int(state["mines"]) else None,
    }


def mines_pick(state: dict[str, Any], tile: int) -> dict[str, Any]:
    if state.get("done"):
        raise SideError("Round is already finished")
    try:
        tile = int(tile)
    except (TypeError, ValueError) as exc:
        raise SideError("Invalid tile") from exc
    if tile < 0 or tile >= MINES_SIZE:
        raise SideError("Tile is off the board")
    if tile in state["picks"]:
        raise SideError("Tile already picked")
    state["picks"] = list(state["picks"]) + [tile]
    if tile in state["bombs"]:
        state["boom"] = True
        state["done"] = True
        state["payout"] = 0
        state["multiplier"] = 0.0
        return state
    picks = len(state["picks"])
    state["multiplier"] = mines_multiplier(int(state["mines"]), picks)
    if picks >= MINES_SIZE - int(state["mines"]):
        # Board cleared: auto cash out at the full multiplier.
        state["payout"] = int(round(state["bet"] * state["multiplier"]))
        state["done"] = True
    return state


def mines_cashout(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("done"):
        raise SideError("Round is already finished")
    if not state.get("picks"):
        raise SideError("Pick at least one safe tile before cashing out")
    state["payout"] = int(round(state["bet"] * float(state["multiplier"])))
    state["done"] = True
    return state


# ---------------------------------------------------------------------------
# Dragon Scratch
# ---------------------------------------------------------------------------

def _weighted_prize(table: tuple[tuple[float, float], ...]) -> float:
    total = sum(w for _, w in table)
    x = _rng.random() * total
    for value, w in table:
        x -= w
        if x <= 0:
            return value
    return table[-1][0]


def scratch_play(bet: int) -> dict[str, Any]:
    """Buy a card. Prize is drawn first; the 3×3 grid is built to match it honestly."""
    bet = valid_bet(bet)
    mult = _weighted_prize(SCRATCH_PRIZES)
    payout = int(round(bet * mult))
    # Symbols for the three rows. A paying card has exactly one matching row
    # (all three the same) whose label reflects the prize; losing cards have
    # no three-of-a-kind row (not a staged two-plus-miss).
    symbols = ["dragon", "orb", "fire", "scale", "pearl", "claw"]
    grid: list[str] = []
    if mult <= 0:
        # Three mixed rows, no three identical.
        for _ in range(3):
            row = [symbols[0], symbols[1], symbols[2]]
            _rng.shuffle(row)
            # Ensure not accidentally matched
            if row[0] == row[1] == row[2]:
                row[2] = symbols[(symbols.index(row[2]) + 1) % len(symbols)]
            grid.extend(row)
    else:
        win_sym = _rng.choice(symbols)
        win_row = _rng.randrange(3)
        for r in range(3):
            if r == win_row:
                grid.extend([win_sym, win_sym, win_sym])
            else:
                a, b, c = _rng.sample(symbols, 3)
                if a == b == c:
                    c = symbols[(symbols.index(c) + 1) % len(symbols)]
                grid.extend([a, b, c])
    order = list(range(SCRATCH_SIZE))
    _rng.shuffle(order)
    return {
        "game": "scratch",
        "done": True,
        "bet": bet,
        "mult": mult,
        "payout": payout,
        "grid": grid,
        "reveal_order": order,
        "win_row": next((r for r in range(3) if len(set(grid[r * 3:(r + 1) * 3])) == 1), None) if mult > 0 else None,
    }


def scratch_ev() -> float:
    total = sum(w for _, w in SCRATCH_PRIZES)
    return sum(v * w for v, w in SCRATCH_PRIZES) / total


# ---------------------------------------------------------------------------
# Lucky Dice
# ---------------------------------------------------------------------------

def _roll(n: int = DICE_COUNT) -> list[int]:
    return [_rng.randint(1, DICE_SIDES) for _ in range(n)]


def dice_play(bet: int) -> dict[str, Any]:
    bet = valid_bet(bet)
    player = _roll()
    dealer = _roll()
    ps, ds = sum(player), sum(dealer)
    if ps > ds:
        result, payout = "win", bet * 2
    elif ps < ds:
        result, payout = "lose", 0
    else:
        result, payout = "push", bet
    return {
        "game": "dice",
        "done": True,
        "bet": bet,
        "player": player,
        "dealer": dealer,
        "player_total": ps,
        "dealer_total": ds,
        "result": result,
        "payout": payout,
    }


def public_state(state: dict[str, Any]) -> dict[str, Any]:
    """Drop private fields (shoe, mine locations mid-round) for the client."""
    game = state.get("game")
    if game == "blackjack":
        out = _bj_public(state, hide_hole=not state.get("done"))
        return out
    if game == "mines":
        return mines_public(state)
    # Other games are one-shot or already public.
    banned = {"shoe", "bombs"} if not state.get("done") else {"shoe"}
    return {k: v for k, v in state.items() if k not in banned}
