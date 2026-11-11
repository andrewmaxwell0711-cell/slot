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

GAMES = ("blackjack", "roulette", "highcard", "mines", "scratch", "dice", "videopoker", "threecard", "war")

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
            {"id": "blackjack", "name": "Blackjack", "tag": "3:2 · stand soft 17 · 6-deck", "category": "Card Games"},
            {"id": "roulette", "name": "European Roulette", "tag": "Single zero · 2.70% house edge", "category": "Table Games"},
            {"id": "videopoker", "name": "Video Poker", "tag": "Jacks or Better 9/6 · ~0.5% house edge", "category": "Card Games"},
            {"id": "threecard", "name": "Three Card Poker", "tag": "Ante/Play + Pair Plus · dealer Q-high", "category": "Card Games"},
            {"id": "war", "name": "Casino War", "tag": "Higher card wins · war on a tie · 6-deck", "category": "Card Games"},
            {"id": "highcard", "name": "High Card", "tag": "Higher card wins 1:1 · tie push or war", "category": "Card Games"},
            {"id": "mines", "name": "Crystal Mines", "tag": "Cash out anytime · ~4% house edge", "category": "Instant/Mini"},
            {"id": "scratch", "name": "Dragon Scratch", "tag": "Scratch card · ~95% RTP", "category": "Instant/Mini"},
            {"id": "dice", "name": "Lucky Dice", "tag": "2d6 duel · tie is a push", "category": "Instant/Mini"},
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
        "videopoker": {
            "variant": "jacks_or_better",
            "paytable": "9/6",
            "pays": {
                "royal_flush": 800, "straight_flush": 50, "four_of_a_kind": 25,
                "full_house": 9, "flush": 6, "straight": 4, "three_of_a_kind": 3,
                "two_pair": 2, "jacks_or_better": 1,
            },
        },
        "threecard": {
            "dealer_qualifies": "Q-high",
            "ante_bonus": {"straight_flush": 5, "three_of_a_kind": 4, "straight": 1},
            "pair_plus": {"straight_flush": 40, "three_of_a_kind": 30, "straight": 6, "flush": 4, "pair": 1},
        },
        "war": {
            "decks": 6,
            "war_win": "1:1 on the raise; original bet pushes",
            "surrender": "half the ante",
            "tie_on_war": "both bets push",
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
    if kind in ("dozen", "dozens"):
        # NOTE: `x or y if c else z` binds as `(x or y) if c else z`.
        # Clients send {kind:"dozen", dozen:1} with no `numbers`; the old
        # form therefore collapsed to 0 and rejected every 1st/2nd/3rd 12 bet.
        raw = b.get("dozen")
        if raw is None and numbers:
            if len(numbers) == 1 and int(numbers[0]) in (1, 2, 3):
                raw = numbers[0]
            elif set(numbers) == set(range(1, 13)):
                raw = 1
            elif set(numbers) == set(range(13, 25)):
                raw = 2
            elif set(numbers) == set(range(25, 37)):
                raw = 3
        try:
            d = int(raw)
        except (TypeError, ValueError) as exc:
            raise SideError("Dozen is 1, 2 or 3") from exc
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


def roulette_settle(bets: list[dict[str, Any]], winning: int) -> dict[str, Any]:
    """Settle a European-roulette spin on a known winning number (0–36).

    Payout is total coins returned. Even-money and dozen/column bets pay 2:1
    (3× the stake back); a straight pays 35:1 (36× back).
    """
    if not bets:
        raise SideError("Place at least one bet")
    try:
        winning = int(winning)
    except (TypeError, ValueError) as exc:
        raise SideError("Invalid number") from exc
    if winning < 0 or winning > 36:
        raise SideError("Winning number is 0–36")
    parsed = [_validate_roulette_bet(b) for b in bets]
    total = sum(b["amount"] for b in parsed)
    if total <= 0:
        raise SideError("Invalid bet")
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


def roulette_spin(bets: list[dict[str, Any]]) -> dict[str, Any]:
    return roulette_settle(bets, _rng.randrange(0, 37))


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



# ---------------------------------------------------------------------------
# Video Poker — Jacks or Better, 9/6 full-pay
# ---------------------------------------------------------------------------

JOB_PAYS = {
    "royal_flush": 800,
    "straight_flush": 50,
    "four_of_a_kind": 25,
    "full_house": 9,
    "flush": 6,
    "straight": 4,
    "three_of_a_kind": 3,
    "two_pair": 2,
    "jacks_or_better": 1,
}

_HIGH = {11, 12, 13, 14}  # J, Q, K, A


def _rank5(cards: list[dict[str, Any]]) -> tuple[str, tuple]:
    """Rank a 5-card Jacks-or-Better hand. Returns (name, tiebreak)."""
    if len(cards) != 5:
        raise SideError("Video poker hands have five cards")
    ranks = [ACE_HIGH[c["rank"]] for c in cards]
    suits = [c["suit"] for c in cards]
    flush = len(set(suits)) == 1
    counts: dict[int, int] = {}
    for r in ranks:
        counts[r] = counts.get(r, 0) + 1
    uniq = sorted(set(ranks))

    def straight_high(rs: list[int]) -> int:
        s = sorted(set(rs))
        if len(s) != 5:
            return 0
        if s[-1] - s[0] == 4:
            return s[-1]
        if s == [2, 3, 4, 5, 14]:
            return 5  # 5-high wheel
        return 0

    sh = straight_high(ranks)
    if flush and sh == 14:
        return "royal_flush", (14,)
    if flush and sh:
        return "straight_flush", (sh,)
    of_a_kind = sorted(((n, r) for r, n in counts.items()), reverse=True)
    if of_a_kind[0][0] == 4:
        kicker = next(r for r in uniq if r != of_a_kind[0][1])
        return "four_of_a_kind", (of_a_kind[0][1], kicker)
    if of_a_kind[0][0] == 3 and of_a_kind[1][0] == 2:
        return "full_house", (of_a_kind[0][1], of_a_kind[1][1])
    if flush:
        return "flush", tuple(sorted(ranks, reverse=True))
    if sh:
        return "straight", (sh,)
    if of_a_kind[0][0] == 3:
        kick = tuple(sorted((r for r in ranks if r != of_a_kind[0][1]), reverse=True))
        return "three_of_a_kind", (of_a_kind[0][1],) + kick
    if of_a_kind[0][0] == 2 and of_a_kind[1][0] == 2:
        pairs = sorted((of_a_kind[0][1], of_a_kind[1][1]), reverse=True)
        kicker = next(r for r in uniq if r not in pairs)
        return "two_pair", (pairs[0], pairs[1], kicker)
    if of_a_kind[0][0] == 2:
        pair = of_a_kind[0][1]
        kick = tuple(sorted((r for r in ranks if r != pair), reverse=True))
        if pair >= 11:
            return "jacks_or_better", (pair,) + kick
        return "nothing", (pair,) + kick
    return "nothing", tuple(sorted(ranks, reverse=True))


def job_hand_name(cards: list[dict[str, Any]]) -> str:
    return _rank5(cards)[0]


def job_payout(cards: list[dict[str, Any]], bet: int) -> tuple[int, str, int]:
    """Return (payout_including_stake_if_any, hand_name, multiplier)."""
    bet = valid_bet(bet)
    name, _ = _rank5(cards)
    # 9/6 paytable values are total return multiples (Jacks or Better pays 1× = a push).
    mult = JOB_PAYS.get(name, 0)
    return bet * mult, name, mult


def _fresh_deck() -> list[dict[str, Any]]:
    return _fresh_shoe(1)


def videopoker_deal(bet: int) -> dict[str, Any]:
    bet = valid_bet(bet)
    deck = _fresh_deck()
    cards = [_draw(deck) for _ in range(5)]
    name = job_hand_name(cards)
    return {
        "game": "videopoker",
        "done": False,
        "bet": bet,
        "cards": cards,
        "held": [False] * 5,
        "deck": deck,
        "hand": name,
        "hand_label": job_hand_label(name),
        "can": ["draw", "hold"],
        "payout": 0,
    }


def videopoker_draw(state: dict[str, Any], holds: list[Any]) -> dict[str, Any]:
    if state.get("done"):
        raise SideError("Hand is already finished")
    if state.get("game") != "videopoker":
        raise SideError("Not a video poker hand")
    flags = _parse_holds(holds, state.get("held") or [False] * 5)
    deck = list(state["deck"])
    cards = list(state["cards"])
    for i in range(5):
        if not flags[i]:
            cards[i] = _draw(deck)
    payout, name, mult = job_payout(cards, int(state["bet"]))
    return {
        "game": "videopoker",
        "done": True,
        "bet": int(state["bet"]),
        "cards": cards,
        "held": flags,
        "dealt": list(state["cards"]),
        "hand": name,
        "hand_label": job_hand_label(name),
        "mult": mult,
        "payout": payout,
        "net": payout - int(state["bet"]),
        "result": "win" if payout > int(state["bet"]) else ("push" if payout == int(state["bet"]) else "lose"),
        "result_banner": "YOU WIN" if payout > int(state["bet"]) else ("PUSH" if payout == int(state["bet"]) else "NO WIN"),
        "can": [],
    }


def _parse_holds(holds: list[Any], current: list[bool]) -> list[bool]:
    flags = [bool(x) for x in current] + [False] * 5
    flags = flags[:5]
    if holds is None:
        return flags
    if not isinstance(holds, (list, tuple)):
        raise SideError("Invalid holds")
    # list of indices, or list of 5 booleans
    if len(holds) == 5 and all(isinstance(x, (bool, int)) and not (isinstance(x, int) and x not in (0, 1)) or isinstance(x, bool) for x in holds):
        # 5 booleans / 0/1 — but indices 0,1 could be confused. If any value is > 1, treat as indices.
        if all(x in (0, 1, True, False) for x in holds) and max((int(x) for x in holds), default=0) <= 1:
            return [bool(x) for x in holds]
    for h in holds:
        try:
            i = int(h)
        except (TypeError, ValueError) as exc:
            raise SideError("Invalid hold index") from exc
        if i < 0 or i >= 5:
            raise SideError("Hold index out of range")
        flags[i] = True
    return flags


def job_hold_strategy(cards: list[dict[str, Any]]) -> list[bool]:
    """A strong Jacks-or-Better hold strategy used for house-edge simulation."""
    idx = list(range(5))
    ranks = [ACE_HIGH[c["rank"]] for c in cards]
    suits = [c["suit"] for c in cards]
    name, _ = _rank5(cards)
    if name in ("royal_flush", "straight_flush", "four_of_a_kind", "full_house", "flush", "straight"):
        return [True] * 5
    if name == "three_of_a_kind":
        trips = max(r for r in set(ranks) if ranks.count(r) == 3)
        return [r == trips for r in ranks]
    if name == "two_pair":
        pairs = {r for r in set(ranks) if ranks.count(r) == 2}
        return [r in pairs for r in ranks]
    if name == "jacks_or_better":
        pair = max(r for r in set(ranks) if ranks.count(r) == 2)
        return [r == pair for r in ranks]

    def combo(ids: list[int]) -> list[dict[str, Any]]:
        return [cards[i] for i in ids]

    # Four to a royal
    for suit in SUITS:
        royal = [i for i in idx if suits[i] == suit and ranks[i] in (10, 11, 12, 13, 14)]
        if len(royal) == 4:
            return [i in royal for i in idx]
    # Four to a straight flush (including insides)
    for suit in SUITS:
        group = [i for i in idx if suits[i] == suit]
        if len(group) >= 4:
            rs = sorted(ACE_HIGH[cards[i]["rank"]] for i in group)
            # any 4 that can make a SF
            from itertools import combinations
            for pick in combinations(group, 4):
                pr = sorted(ACE_HIGH[cards[i]["rank"]] for i in pick)
                span = pr[-1] - pr[0]
                wheel = pr == [2, 3, 4, 5] or set(pr) <= {14, 2, 3, 4, 5}
                if span <= 4 or wheel:
                    return [i in pick for i in idx]

    # Low pair
    if any(ranks.count(r) == 2 for r in set(ranks)):
        pair = max(r for r in set(ranks) if ranks.count(r) == 2)
        return [r == pair for r in ranks]

    # Three to a royal
    for suit in SUITS:
        royal = [i for i in idx if suits[i] == suit and ranks[i] in (10, 11, 12, 13, 14)]
        if len(royal) == 3:
            return [i in royal for i in idx]

    # Four to a flush
    for suit in SUITS:
        group = [i for i in idx if suits[i] == suit]
        if len(group) == 4:
            return [i in group for i in idx]

    # Four to an outside straight
    uniq = sorted(set(ranks))
    if len(uniq) >= 4:
        from itertools import combinations
        for pick in combinations(range(5), 4):
            pr = sorted(ACE_HIGH[cards[i]["rank"]] for i in pick)
            if len(set(pr)) == 4 and pr[-1] - pr[0] == 3 and 14 not in pr:
                return [i in pick for i in idx]

    # Two suited high cards (or 10 + high suited for a royal)
    suited_high: dict[str, list[int]] = {}
    for i in idx:
        if ranks[i] in _HIGH or ranks[i] == 10:
            suited_high.setdefault(suits[i], []).append(i)
    best = None
    for group in suited_high.values():
        highs = [i for i in group if ranks[i] in _HIGH or ranks[i] == 10]
        if len([i for i in highs if ranks[i] in _HIGH]) >= 2 or (
            any(ranks[i] == 10 for i in highs) and any(ranks[i] in _HIGH for i in highs)
        ):
            pick = [i for i in highs if ranks[i] in _HIGH or ranks[i] == 10]
            pick = sorted(pick, key=lambda i: ranks[i], reverse=True)[:2]
            if best is None or sum(ranks[i] for i in pick) > sum(ranks[i] for i in best):
                best = pick
    if best:
        return [i in best for i in idx]

    # Three to a straight flush
    for suit in SUITS:
        group = [i for i in idx if suits[i] == suit]
        if len(group) >= 3:
            from itertools import combinations
            for pick in combinations(group, 3):
                pr = sorted(ACE_HIGH[cards[i]["rank"]] for i in pick)
                span = pr[-1] - pr[0]
                wheel = len(set(pr) & {14, 2, 3, 4, 5}) == 3
                if span <= 4 or wheel:
                    return [i in pick for i in idx]

    # Unsuited high cards — hold the two highest (but never 3+)
    highs = [i for i in idx if ranks[i] in _HIGH]
    if len(highs) >= 2:
        highs = sorted(highs, key=lambda i: ranks[i], reverse=True)[:2]
        return [i in highs for i in idx]
    if len(highs) == 1:
        return [i in highs for i in idx]
    return [False] * 5


# ---------------------------------------------------------------------------
# Three Card Poker — Ante/Play + Pair Plus, dealer qualifies Q-high
# ---------------------------------------------------------------------------

TCP_ANTE_BONUS = {"straight_flush": 5, "three_of_a_kind": 4, "straight": 1}
TCP_PAIR_PLUS = {"straight_flush": 40, "three_of_a_kind": 30, "straight": 6, "flush": 4, "pair": 1}
# Categories, high to low: SF=6, trips=5, straight=4, flush=3, pair=2, high=1
TCP_CAT = {
    "straight_flush": 6,
    "three_of_a_kind": 5,
    "straight": 4,
    "flush": 3,
    "pair": 2,
    "high_card": 1,
}


def _tcp_straight_high(ranks: list[int]) -> int:
    s = sorted(ranks)
    if s == [2, 3, 14]:
        return 3  # 3-high wheel, lowest straight
    if s[0] + 1 == s[1] and s[1] + 1 == s[2]:
        return s[2]
    return 0


def tcp_rank(cards: list[dict[str, Any]]) -> tuple[str, tuple]:
    """Rank a 3-card poker hand. Higher tuple wins."""
    if len(cards) != 3:
        raise SideError("Three Card Poker hands have three cards")
    ranks = [ACE_HIGH[c["rank"]] for c in cards]
    suits = [c["suit"] for c in cards]
    flush = len(set(suits)) == 1
    sh = _tcp_straight_high(ranks)
    counts: dict[int, int] = {}
    for r in ranks:
        counts[r] = counts.get(r, 0) + 1
    if flush and sh:
        return "straight_flush", (TCP_CAT["straight_flush"], sh)
    if 3 in counts.values():
        trips = next(r for r, n in counts.items() if n == 3)
        return "three_of_a_kind", (TCP_CAT["three_of_a_kind"], trips)
    if sh:
        return "straight", (TCP_CAT["straight"], sh)
    if flush:
        return "flush", (TCP_CAT["flush"],) + tuple(sorted(ranks, reverse=True))
    if 2 in counts.values():
        pair = next(r for r, n in counts.items() if n == 2)
        kicker = next(r for r in ranks if r != pair)
        return "pair", (TCP_CAT["pair"], pair, kicker)
    return "high_card", (TCP_CAT["high_card"],) + tuple(sorted(ranks, reverse=True))



def _rank_word(n: int, plural: bool = False) -> str:
    names = {14: "Ace", 13: "King", 12: "Queen", 11: "Jack", 10: "10"}
    w = names.get(int(n), str(int(n)))
    if not plural:
        return w
    if w == "6":
        return "6s"
    if w in ("Ace", "King", "Queen", "Jack"):
        return w + "s"
    return w + "s"


def job_hand_label(name: str) -> str:
    labels = {
        "royal_flush": "Royal flush",
        "straight_flush": "Straight flush",
        "four_of_a_kind": "Four of a kind",
        "full_house": "Full house",
        "flush": "Flush",
        "straight": "Straight",
        "three_of_a_kind": "Three of a kind",
        "two_pair": "Two pair",
        "jacks_or_better": "Jacks or better",
        "nothing": "Nothing",
    }
    return labels.get(name, (name or "Nothing").replace("_", " ").title())


def tcp_hand_label(cards: list[dict[str, Any]]) -> str:
    """Friendly three-card hand name, e.g. 'Pair of 8s', 'Queen high'."""
    name, key = tcp_rank(cards)
    if name == "straight_flush":
        return "Straight flush" if key[1] != 14 else "Straight flush (A-K-Q)"
    if name == "three_of_a_kind":
        return "Three " + _rank_word(key[1], True)
    if name == "straight":
        return "Straight"
    if name == "flush":
        return f"Flush, {_rank_word(key[1])} high"
    if name == "pair":
        return "Pair of " + _rank_word(key[1], True)
    return f"{_rank_word(key[1])} high"


def tcp_hand_name(cards: list[dict[str, Any]]) -> str:
    return tcp_rank(cards)[0]


def tcp_qualifies(cards: list[dict[str, Any]]) -> bool:
    """Dealer qualifies with Queen-high or better."""
    name, key = tcp_rank(cards)
    if name != "high_card":
        return True
    return key[1] >= 12  # Queen or better as the highest card


def tcp_should_play(cards: list[dict[str, Any]]) -> bool:
    """Optimal-ish Q-6-4 strategy: play Q-6-4 or better."""
    name, key = tcp_rank(cards)
    if name != "high_card":
        return True
    return tuple(key[1:]) >= (12, 6, 4)


def tcp_settle(player: list[dict[str, Any]], dealer: list[dict[str, Any]],
               ante: int, pair_plus: int, played: bool) -> dict[str, Any]:
    ante = valid_bet(ante)
    try:
        pair_plus = int(pair_plus or 0)
    except (TypeError, ValueError) as exc:
        raise SideError("Invalid Pair Plus bet") from exc
    if pair_plus < 0:
        raise SideError("Invalid Pair Plus bet")
    p_name, p_key = tcp_rank(player)
    d_name, d_key = tcp_rank(dealer)
    pp_mult = TCP_PAIR_PLUS.get(p_name, 0)
    pp_payout = (pair_plus + pair_plus * pp_mult) if pair_plus and pp_mult else 0
    ante_bonus_mult = TCP_ANTE_BONUS.get(p_name, 0) if played else 0
    ante_bonus = ante * ante_bonus_mult
    play_bet = ante if played else 0

    if not played:
        result = "fold"
        payout = pp_payout
        ante_payout = 0
        play_payout = 0
    else:
        qualifies = tcp_qualifies(dealer)
        if not qualifies:
            # Ante 1:1, Play pushes.
            result = "dealer_does_not_qualify"
            ante_payout = ante * 2
            play_payout = play_bet
        elif p_key > d_key:
            result = "win"
            ante_payout = ante * 2
            play_payout = play_bet * 2
        elif p_key < d_key:
            result = "lose"
            ante_payout = 0
            play_payout = 0
        else:
            result = "tie"
            ante_payout = ante
            play_payout = play_bet
        payout = ante_payout + play_payout + ante_bonus + pp_payout

    return {
        "game": "threecard",
        "done": True,
        "ante": ante,
        "pair_plus": pair_plus,
        "play": play_bet,
        "bet": ante + pair_plus + play_bet,
        "player": player,
        "dealer": dealer,
        "player_hand": p_name,
        "dealer_hand": d_name,
        "player_hand_label": tcp_hand_label(player),
        "dealer_hand_label": tcp_hand_label(dealer),
        "dealer_qualifies": tcp_qualifies(dealer),
        "played": played,
        "ante_bonus": ante_bonus,
        "pair_plus_payout": pp_payout,
        "ante_payout": ante_payout if played else 0,
        "play_payout": play_payout if played else 0,
        "ante_status": ("folded" if not played else "win" if ante_payout > ante else "push" if ante_payout == ante else "lose"),
        "play_status": ("—" if not played else "win" if play_payout > play_bet else "push" if play_payout == play_bet else "lose"),
        "pair_plus_status": ("—" if not pair_plus else "win" if pp_payout > pair_plus else "lose"),
        "payout": payout,
        "net": payout - ante - pair_plus - play_bet,
        "result": result,
        "result_banner": (
            "FOLDED" if result == "fold" else
            "PUSH" if result == "tie" else
            "DEALER WINS" if result == "lose" else
            "YOU WIN"
        ),
        "can": [],
    }


def threecard_deal(ante: int, pair_plus: int = 0) -> dict[str, Any]:
    ante = valid_bet(ante)
    try:
        pair_plus = int(pair_plus or 0)
    except (TypeError, ValueError) as exc:
        raise SideError("Invalid Pair Plus bet") from exc
    if pair_plus < 0:
        raise SideError("Invalid Pair Plus bet")
    shoe = _fresh_shoe(1)
    player = [_draw(shoe) for _ in range(3)]
    dealer = [_draw(shoe) for _ in range(3)]
    return {
        "game": "threecard",
        "done": False,
        "ante": ante,
        "pair_plus": pair_plus,
        "bet": ante + pair_plus,
        "player": player,
        "dealer": dealer,  # hidden in public_state until done
        "player_hand": tcp_hand_name(player),
        "player_hand_label": tcp_hand_label(player),
        "hint_play": tcp_should_play(player),
        "played": False,
        "payout": 0,
        "can": ["play", "fold"],
        "shoe": shoe,
    }


def threecard_act(state: dict[str, Any], action: str) -> dict[str, Any]:
    if state.get("done"):
        raise SideError("Hand is already finished")
    action = str(action or "").lower().strip()
    if action not in ("play", "fold"):
        raise SideError("Choose play or fold")
    return tcp_settle(state["player"], state["dealer"], int(state["ante"]),
                      int(state.get("pair_plus") or 0), played=(action == "play"))


def threecard_public(state: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in state.items() if k not in {"shoe"}}
    if not state.get("done"):
        out["dealer"] = [{"rank": "?", "suit": "back", "value": 0, "colour": "back", "hidden": True} for _ in state["dealer"]]
        out.pop("dealer_hand", None)
        out.pop("dealer_qualifies", None)
    return out


# ---------------------------------------------------------------------------
# Casino War — 6-deck shoe, surrender half or go to war
# ---------------------------------------------------------------------------

def war_card_value(card: dict[str, Any]) -> int:
    return ACE_HIGH[card["rank"]]


def war_settle(player: dict[str, Any], dealer: dict[str, Any], bet: int,
               war: bool = False, raise_bet: int = 0,
               player_war: dict[str, Any] | None = None,
               dealer_war: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure payout helper (also used by tests). Payout is total coins returned."""
    bet = valid_bet(bet)
    if not war:
        pv, dv = war_card_value(player), war_card_value(dealer)
        if pv > dv:
            return {"result": "win", "payout": bet * 2, "done": True}
        if pv < dv:
            return {"result": "lose", "payout": 0, "done": True}
        return {"result": "tie", "payout": 0, "done": False, "awaiting_war": True}

    raise_bet = valid_bet(raise_bet or bet)
    if player_war is None or dealer_war is None:
        raise SideError("War cards required")
    pv, dv = war_card_value(player_war), war_card_value(dealer_war)
    # Win: 1:1 on the raise, original ante pushes → return ante + 2×raise
    if pv > dv:
        return {"result": "war_win", "payout": bet + raise_bet * 2, "done": True}
    if pv < dv:
        return {"result": "war_lose", "payout": 0, "done": True}
    # Tie on war: both bets push (optional bonus not applied — keeps HE ~2.9%).
    return {"result": "war_tie", "payout": bet + raise_bet, "done": True}


def war_deal(bet: int) -> dict[str, Any]:
    bet = valid_bet(bet)
    shoe = _fresh_shoe(6)
    player = _draw(shoe)
    dealer = _draw(shoe)
    settled = war_settle(player, dealer, bet, war=False)
    state = {
        "game": "war",
        "bet": bet,
        "player": player,
        "dealer": dealer,
        "shoe": shoe,
        "war": False,
        "payout": settled["payout"],
        "result": settled["result"],
        "done": settled["done"],
        "awaiting_war": bool(settled.get("awaiting_war")),
        "can": ["war", "surrender"] if settled.get("awaiting_war") else [],
    }
    return state


def war_act(state: dict[str, Any], action: str) -> dict[str, Any]:
    if state.get("done"):
        raise SideError("Hand is already finished")
    if not state.get("awaiting_war"):
        raise SideError("No tie to resolve")
    action = str(action or "").lower().strip()
    bet = int(state["bet"])
    if action == "surrender":
        # Half the ante is returned (integer coins; odd bets lose the leftover).
        payout = bet // 2
        state = {**state, "done": True, "awaiting_war": False, "war": False,
                 "result": "surrender", "payout": payout, "can": [], "raise": 0}
        return state
    if action != "war":
        raise SideError("Choose war or surrender")
    shoe = list(state.get("shoe") or _fresh_shoe(6))
    # Standard casino war: burn three each, then one card each.
    for _ in range(3):
        if shoe:
            _draw(shoe)
        if shoe:
            _draw(shoe)
    player_war = _draw(shoe)
    dealer_war = _draw(shoe)
    settled = war_settle(state["player"], state["dealer"], bet, war=True,
                         raise_bet=bet, player_war=player_war, dealer_war=dealer_war)
    return {
        "game": "war",
        "done": True,
        "bet": bet,
        "raise": bet,
        "player": state["player"],
        "dealer": state["dealer"],
        "player_war": player_war,
        "dealer_war": dealer_war,
        "war": True,
        "awaiting_war": False,
        "payout": settled["payout"],
        "result": settled["result"],
        "can": [],
    }



def public_state(state: dict[str, Any]) -> dict[str, Any]:
    """Drop private fields (shoe, mine locations mid-round) for the client."""
    game = state.get("game")
    if game == "blackjack":
        out = _bj_public(state, hide_hole=not state.get("done"))
        return out
    if game == "mines":
        return mines_public(state)
    if game == "threecard":
        return threecard_public(state)
    # Other games are one-shot or already public.
    banned = {"shoe", "bombs", "deck"} if not state.get("done") else {"shoe", "deck"}
    return {k: v for k, v in state.items() if k not in banned}
