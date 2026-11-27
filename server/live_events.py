"""Live events calendar — coins-only, server-side schedule.

A weekly Australia/Perth calendar of six event types:

* happy_hour — a short window that pays a fixed house coin bonus per play
  (capped). This is not a payout multiplier and does not change RTP.
* xp_boost — doubles season XP from play for the window. Game payouts
  are unchanged.
* club_boost — doubles club weekly points for the window. Game payouts
  are unchanged.
* collect — a timed event chest that can be claimed once.
* challenge — a timed play challenge with a single fixed coin prize.
* tournament — the existing Friday–Sunday weekend tournament, surfaced
  on the calendar. Settlement stays in prizes.py.

Prizes are house-issued promotional virtual coins with no cash value.
They are not taken from the game house pool, so they cannot change slot
RTP. Each collect or challenge claim is atomic and idempotent per player
per event, with a unique claim key. Happy-hour bonuses are capped and
granted under a player lock. There are no paid skips, no loot-box
randomness, and no fake countdowns — each card shows the real ends_at.

Schema is additive and applied only when prefs.schema_migrate_allowed()
is true. See docs/migrations/2026-11-28-live-events.md. Do not run this
against production Postgres.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import prefs
from prizes import PERTH, perth_now

LEGAL = (
    "Event rewards are virtual coins issued by the house for entertainment "
    "only. They have no cash value, cannot be redeemed, and cannot be "
    "transferred between players. Event boosts never change game payouts or RTP."
)

# Weekly templates. Times are Australia/Perth. The schedule is determined
# on the server; clients cannot invent or extend events.
TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "type": "happy_hour",
        "title": "Happy Hour",
        "description": (
            "Each play grants a small house coin bonus, up to a cap. "
            "Game payouts and RTP are unchanged."
        ),
        "weekdays": (0, 2, 4),  # Mon, Wed, Fri
        "start_hour": 18,
        "duration_hours": 1,
        "bonus_per_play": 25,
        "cap_plays": 40,
    },
    {
        "type": "xp_boost",
        "title": "Season XP Boost",
        "description": (
            "Season XP from play is doubled until the end date. "
            "Game payouts and RTP are unchanged."
        ),
        "weekdays": (1, 3),  # Tue, Thu
        "start_hour": 12,
        "duration_hours": 3,
        "season_xp_mult": 2,
    },
    {
        "type": "club_boost",
        "title": "Club Points Boost",
        "description": (
            "Club weekly points from play are doubled until the end date. "
            "Game payouts and RTP are unchanged."
        ),
        "weekdays": (5,),  # Sat
        "start_hour": 10,
        "duration_hours": 4,
        "club_points_mult": 2,
    },
    {
        "type": "collect",
        "title": "Event Chest",
        "description": "Claim a fixed house coin chest once during this event.",
        "weekdays": (6,),  # Sun
        "start_hour": 0,
        "duration_hours": 24,
        "reward_coins": 2_000,
    },
    {
        "type": "challenge",
        "title": "Play Challenge",
        "description": "Play 30 games during the window, then claim a fixed coin prize once.",
        "weekdays": (2,),  # Wed 00:00 through Fri 00:00
        "start_hour": 0,
        "duration_hours": 48,
        "target_plays": 30,
        "reward_coins": 3_000,
    },
    {
        "type": "tournament",
        "title": "Weekend Tournament",
        "description": (
            "Play Friday through Sunday for a place on the weekend board. "
            "Rewards are listed up front on the Prizes board. "
            "There is no countdown to buy coins."
        ),
        "weekdays": (4,),  # Fri 00:00 through Mon 00:00
        "start_hour": 0,
        "duration_hours": 72,
    },
)

_TYPE_BY_NAME = {t["type"]: t for t in TEMPLATES}


class EventError(ValueError):
    """User-facing live-events error."""


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def now(when: datetime | None = None) -> datetime:
    """Australia/Perth now, honouring the shared season test clock."""
    import season

    return season.now(when)


def set_clock(when: datetime | None) -> None:
    import season

    season.set_clock(when)


def _monday(when: datetime | None = None) -> datetime:
    dt = now(when)
    start = (dt - timedelta(days=dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    if start.tzinfo is None:
        start = start.replace(tzinfo=PERTH)
    return start.astimezone(PERTH)


def _label(dt: datetime) -> str:
    return dt.strftime("%d %b %Y, %H:%M").lstrip("0") + " Australia/Perth"


def event_id(kind: str, start: datetime) -> str:
    return f"{kind}:{start.date().isoformat()}:{start.hour:02d}"


def claim_key(player_id: str, eid: str) -> str:
    return f"event-claim:{eid}:player:{player_id}"


def instances(when: datetime | None = None, weeks: int = 2, lookback_weeks: int = 1) -> list[dict[str, Any]]:
    """Deterministic calendar instances for the surrounding weeks.

    Status is always computed against `when` (or the test clock), even when
    looking back one week so a just-ended event can still be identified.
    """
    current = now(when)
    back = max(0, int(lookback_weeks))
    monday = _monday(when) - timedelta(days=7 * back)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for week in range(back + max(1, weeks)):
        base = monday + timedelta(days=7 * week)
        for tmpl in TEMPLATES:
            for wd in tmpl["weekdays"]:
                start = (base + timedelta(days=int(wd))).replace(
                    hour=int(tmpl["start_hour"]),
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                end = start + timedelta(hours=int(tmpl["duration_hours"]))
                eid = event_id(tmpl["type"], start)
                if eid in seen:
                    continue
                seen.add(eid)
                if start <= current < end:
                    status = "active"
                elif current < start:
                    status = "upcoming"
                else:
                    status = "ended"
                item = {
                    "id": eid,
                    "type": tmpl["type"],
                    "title": tmpl["title"],
                    "description": tmpl["description"],
                    "starts_at": start.isoformat(),
                    "ends_at": end.isoformat(),
                    "ends_at_label": _label(end),
                    "starts_at_label": _label(start),
                    "status": status,
                    "legal": LEGAL,
                }
                if tmpl["type"] == "happy_hour":
                    item["bonus_per_play"] = int(tmpl["bonus_per_play"])
                    item["cap_plays"] = int(tmpl["cap_plays"])
                    item["reward_label"] = (
                        f"{int(tmpl['bonus_per_play'])} coins per play, "
                        f"up to {int(tmpl['cap_plays'])} plays"
                    )
                elif tmpl["type"] == "xp_boost":
                    item["season_xp_mult"] = int(tmpl["season_xp_mult"])
                    item["reward_label"] = "2× season XP from play"
                elif tmpl["type"] == "club_boost":
                    item["club_points_mult"] = int(tmpl["club_points_mult"])
                    item["reward_label"] = "2× club weekly points"
                elif tmpl["type"] == "collect":
                    item["reward_coins"] = int(tmpl["reward_coins"])
                    item["reward_label"] = f"{int(tmpl['reward_coins']):,} coins"
                    item["claimable"] = True
                elif tmpl["type"] == "challenge":
                    item["target_plays"] = int(tmpl["target_plays"])
                    item["reward_coins"] = int(tmpl["reward_coins"])
                    item["reward_label"] = (
                        f"{int(tmpl['reward_coins']):,} coins after "
                        f"{int(tmpl['target_plays'])} plays"
                    )
                    item["claimable"] = True
                elif tmpl["type"] == "tournament":
                    from prizes import WEEKEND_COINS

                    item["reward_label"] = (
                        "1st {:,} · 2nd {:,} · 3rd {:,} coins".format(
                            WEEKEND_COINS[1], WEEKEND_COINS[2], WEEKEND_COINS[3]
                        )
                    )
                    item["href"] = "prizes"
                out.append(item)
    out.sort(key=lambda e: (e["starts_at"], e["type"]))
    return out


def active_events(when: datetime | None = None) -> list[dict[str, Any]]:
    return [e for e in instances(when) if e["status"] == "active"]


def event_by_id(eid: str, when: datetime | None = None) -> dict[str, Any] | None:
    for item in instances(when, weeks=3, lookback_weeks=2):
        if item["id"] == eid:
            return item
    return None


def xp_multiplier(when: datetime | None = None) -> int:
    """Season play-XP multiplier. Never used for game payouts."""
    for ev in active_events(when):
        if ev["type"] == "xp_boost":
            return max(1, min(3, int(ev.get("season_xp_mult") or 2)))
    return 1


def club_points_multiplier(when: datetime | None = None) -> int:
    """Club weekly-points multiplier. Never used for game payouts."""
    for ev in active_events(when):
        if ev["type"] == "club_boost":
            return max(1, min(3, int(ev.get("club_points_mult") or 2)))
    return 1


def ensure_schema(conn: Any) -> None:
    if not prefs.schema_migrate_allowed():
        return
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_progress (
            player_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            plays INTEGER NOT NULL DEFAULT 0,
            bonus_coins INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (player_id, event_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_claims (
            claim_key TEXT PRIMARY KEY,
            player_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            amount INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS event_claims_unique
            ON event_claims(player_id, event_id)
        """
    )


def _progress(conn: Any, player_id: str, eid: str) -> dict[str, int]:
    row = conn.execute(
        "SELECT plays, bonus_coins FROM event_progress WHERE player_id = ? AND event_id = ?",
        (player_id, eid),
    ).fetchone()
    if not row:
        return {"plays": 0, "bonus_coins": 0}
    return {"plays": int(row["plays"] or 0), "bonus_coins": int(row["bonus_coins"] or 0)}


def _claimed_amount(conn: Any, player_id: str, eid: str) -> int | None:
    row = conn.execute(
        "SELECT amount FROM event_claims WHERE player_id = ? AND event_id = ?",
        (player_id, eid),
    ).fetchone()
    if not row:
        return None
    return int(row["amount"] or 0)


def on_play(
    player_id: str,
    game: str,
    bet_coins: int,
    win_coins: int,
    meta: dict[str, Any] | None = None,
    **_kw: Any,
) -> None:
    """events.on_play subscriber. Never raises into the game path.

    Does not inspect or change win_coins, game math, or the house pool.
    """
    del game, win_coins, meta
    try:
        record_play(player_id, int(bet_coins or 0))
    except Exception:
        return


def record_play(player_id: str, bet_coins: int = 0, when: datetime | None = None) -> dict[str, Any]:
    """Record challenge progress and grant a capped happy-hour bonus."""
    import ledger
    from game import COIN_ASSET

    del bet_coins
    out = {"bonus": 0, "plays": {}}
    if not prefs.schema_migrate_allowed():
        return out
    ledger.ensure_player(player_id)
    active = active_events(when)
    if not active:
        return out
    with ledger.transaction() as conn:
        ensure_schema(conn)
        ledger.lock_player(conn, player_id)
        for ev in active:
            if ev["type"] not in ("happy_hour", "challenge"):
                continue
            eid = ev["id"]
            prev = _progress(conn, player_id, eid)
            plays = prev["plays"] + 1
            bonus = prev["bonus_coins"]
            grant = 0
            if ev["type"] == "happy_hour" and plays <= int(ev["cap_plays"]):
                grant = int(ev["bonus_per_play"])
                bonus += grant
                if grant > 0:
                    ledger._credit(conn, player_id, COIN_ASSET, grant)
                    key = f"event-bonus:{eid}:player:{player_id}:play:{plays}"
                    conn.execute(
                        """
                        INSERT INTO ledger_entries
                            (player_id, kind, asset, amount, stripe_session_id, note, created_at)
                        VALUES (?, 'event_reward', ?, ?, ?, ?, ?)
                        """,
                        (
                            player_id,
                            COIN_ASSET,
                            grant,
                            key,
                            f"Happy Hour {eid} play {plays} — virtual coins, no cash value",
                            _utc_iso(),
                        ),
                    )
            conn.execute(
                """
                INSERT INTO event_progress (player_id, event_id, plays, bonus_coins, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (player_id, event_id) DO UPDATE SET
                    plays = excluded.plays,
                    bonus_coins = excluded.bonus_coins,
                    updated_at = excluded.updated_at
                """,
                (player_id, eid, plays, bonus, _utc_iso()),
            )
            out["plays"][eid] = plays
            if grant:
                out["bonus"] = int(out["bonus"]) + grant
    return out


def claim_prize(player_id: str, eid: str, when: datetime | None = None) -> dict[str, Any]:
    """Claim a collect or challenge prize once. Idempotent per player per event."""
    import ledger
    from game import COIN_ASSET

    ledger.ensure_player(player_id)
    if not prefs.schema_migrate_allowed():
        raise EventError("Live events are not available on this database yet")
    ev = event_by_id(str(eid or ""), when)
    if not ev:
        raise EventError("That event was not found")
    if ev["type"] not in ("collect", "challenge"):
        raise EventError("This event has no prize to claim")
    key = claim_key(player_id, ev["id"])
    awarded = 0
    already = False
    with ledger.transaction() as conn:
        ensure_schema(conn)
        ledger.lock_player(conn, player_id)
        existing = conn.execute(
            "SELECT amount FROM event_claims WHERE claim_key = ?",
            (key,),
        ).fetchone()
        if existing:
            already = True
        else:
            if ev["status"] != "active":
                if ev["status"] == "ended":
                    raise EventError("This event has ended. Unclaimed prizes cannot be collected after the end date.")
                raise EventError("This event has not started yet")
            if ev["type"] == "challenge":
                prog = _progress(conn, player_id, ev["id"])
                if prog["plays"] < int(ev["target_plays"]):
                    raise EventError("You have not finished this challenge yet")
            amount = int(ev["reward_coins"])
            inserted = conn.execute(
                """
                INSERT INTO event_claims (claim_key, player_id, event_id, amount, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (claim_key) DO NOTHING
                """,
                (key, player_id, ev["id"], amount, _utc_iso()),
            )
            if int(getattr(inserted, "rowcount", 0) or 0) == 0:
                already = True
            else:
                awarded = amount
                if awarded > 0:
                    ledger._credit(conn, player_id, COIN_ASSET, awarded)
                    conn.execute(
                        """
                        INSERT INTO ledger_entries
                            (player_id, kind, asset, amount, stripe_session_id, note, created_at)
                        VALUES (?, 'event_reward', ?, ?, ?, ?, ?)
                        """,
                        (
                            player_id,
                            COIN_ASSET,
                            awarded,
                            key,
                            f"Live event {ev['id']} — virtual coins, no cash value",
                            _utc_iso(),
                        ),
                    )
    state = events_state(player_id, when=when)
    state["awarded"] = 0 if already else awarded
    state["already_claimed"] = already
    state["celebrate"] = (not already) and awarded > 0
    state["bonus"] = "event"
    if already:
        state["error"] = "Already claimed this event prize"
    return state


def events_state(player_id: str, when: datetime | None = None) -> dict[str, Any]:
    import ledger

    current = now(when)
    catalog = instances(when)
    out: dict[str, Any] = {
        "available": prefs.schema_migrate_allowed(),
        "now": current.isoformat(),
        "legal": LEGAL,
        "events": [],
        "celebrate": False,
        "win_celebration": False,
    }
    if not out["available"]:
        out["events"] = catalog
        return out
    try:
        ensure_schema(ledger.get_conn())
        conn = ledger.get_conn()
        progress_rows = conn.execute(
            "SELECT event_id, plays, bonus_coins FROM event_progress WHERE player_id = ?",
            (player_id,),
        ).fetchall()
        claim_rows = conn.execute(
            "SELECT event_id, amount FROM event_claims WHERE player_id = ?",
            (player_id,),
        ).fetchall()
    except Exception:
        progress_rows = []
        claim_rows = []
    progress = {str(r["event_id"]): r for r in progress_rows}
    claims = {str(r["event_id"]): int(r["amount"] or 0) for r in claim_rows}
    events = []
    for ev in catalog:
        item = dict(ev)
        row = progress.get(ev["id"])
        plays = int(row["plays"] if row else 0)
        bonus = int(row["bonus_coins"] if row else 0)
        item["plays"] = plays
        item["bonus_coins"] = bonus
        item["claimed"] = ev["id"] in claims
        item["claimed_amount"] = claims.get(ev["id"])
        can = False
        if ev.get("claimable") and ev["status"] == "active" and ev["id"] not in claims:
            if ev["type"] == "collect":
                can = True
            elif ev["type"] == "challenge":
                can = plays >= int(ev.get("target_plays") or 0)
        item["can_claim"] = can
        if ev["type"] == "challenge":
            item["target"] = int(ev.get("target_plays") or 0)
        if ev["type"] == "happy_hour":
            item["target"] = int(ev.get("cap_plays") or 0)
        events.append(item)
    out["events"] = events
    return out


def catalogue(when: datetime | None = None) -> dict[str, Any]:
    return {"legal": LEGAL, "events": instances(when)}


import events as _events

_events.register(on_play)
