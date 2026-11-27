"""Season pass — coins-only battle pass (Slotomania / Huuuge style).

A 4-week season with 30 tiers. XP comes from settled play (including losses)
through the v10 events.on_play hook, plus 3 daily missions and weekly
missions. The free track pays house-issued virtual coins and cosmetics
(frames and emblems). The premium track is shown with fixed rewards up
front and labelled "Premium coming soon" in this build.

TODO(android): Premium unlock will use Google Play Billing in a future
Android build. Do not add a Stripe (or any real-money) purchase for the
season pass on the web. Stripe remains test-mode coin packs only.

Rewards have no cash value, cannot be redeemed, and cannot be transferred.
Each claim is atomic and idempotent per player, per season and per tier,
with a unique claim key. There are no paid skips, no loot-box randomness,
and no fake countdowns — the season end date is the real ends_at.

Schema is additive and applied only when prefs.schema_migrate_allowed()
is true. See docs/migrations/2026-11-28-season-pass.md. Do not run this
against production Postgres.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import prefs
from prizes import PERTH, perth_date, perth_now, perth_week

# Monday 00:00 Australia/Perth. Seasons are exactly 28 days.
# Override at launch with SEASON_EPOCH (YYYY-MM-DD or an ISO datetime).
# Naive values are interpreted in Australia/Perth. Invalid values fall
# back to this default so a typo cannot take the app down.
_DEFAULT_EPOCH = datetime(2026, 11, 23, 0, 0, 0, tzinfo=PERTH)
SEASON_EPOCH = _DEFAULT_EPOCH


def season_epoch() -> datetime:
    """Return the configured season-1 start, honouring SEASON_EPOCH."""
    raw = (os.environ.get("SEASON_EPOCH") or "").strip()
    if not raw:
        return _DEFAULT_EPOCH
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return _DEFAULT_EPOCH
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=PERTH)
    return dt.astimezone(PERTH)
SEASON_DAYS = 28
TIER_COUNT = 30

# TODO(android): Do not flip this on for a web/Stripe purchase.
PREMIUM_PURCHASE_ENABLED = False
PREMIUM_NOTE = "Premium coming soon. Not for sale on the web."

SEASON_NAMES = (
    "Crystal Crown",
    "Emerald Reign",
    "Sapphire Gala",
    "Amethyst Night",
    "Citrine Parade",
    "Ruby Jubilee",
)

# Frames and emblems are cosmetic virtual items — no cash value.
FRAMES = (
    {"id": "frame-gold", "label": "Gilded frame", "color": "#e8c97a"},
    {"id": "frame-violet", "label": "Violet frame", "color": "#b07cff"},
    {"id": "frame-teal", "label": "Teal frame", "color": "#5ee0c8"},
)
EMBLEMS = (
    {"id": "ruby", "label": "Ruby emblem", "src": "/assets/symbols/ruby.webp"},
    {"id": "emerald", "label": "Emerald emblem", "src": "/assets/symbols/emerald.webp"},
    {"id": "sapphire", "label": "Sapphire emblem", "src": "/assets/symbols/sapphire.webp"},
    {"id": "amethyst", "label": "Amethyst emblem", "src": "/assets/symbols/amethyst.webp"},
    {"id": "citrine", "label": "Citrine emblem", "src": "/assets/symbols/citrine.webp"},
    {"id": "shard", "label": "Shard emblem", "src": "/assets/symbols/shard.webp"},
)

DAILY_POOL = (
    {"id": "d_spin_50", "title": "Spin 50 times", "type": "spins", "target": 50, "xp": 200},
    {"id": "d_bj_win_3", "title": "Win at blackjack 3 times", "type": "game_wins", "game": "blackjack", "target": 3, "xp": 250},
    {"id": "d_play_20", "title": "Play 20 games", "type": "plays", "target": 20, "xp": 150},
    {"id": "d_win_5", "title": "Win 5 games", "type": "wins", "target": 5, "xp": 200},
    {"id": "d_bet_10k", "title": "Bet 10,000 coins", "type": "bet", "target": 10_000, "xp": 200},
    {"id": "d_roulette_10", "title": "Play roulette 10 times", "type": "game_plays", "game": "roulette", "target": 10, "xp": 180},
)

WEEKLY_MISSIONS = (
    {"id": "w_spin_200", "title": "Spin 200 times this week", "type": "spins", "target": 200, "xp": 600},
    {"id": "w_win_25", "title": "Win 25 games this week", "type": "wins", "target": 25, "xp": 600},
    {"id": "w_bet_100k", "title": "Bet 100,000 coins this week", "type": "bet", "target": 100_000, "xp": 700},
)

LEGAL = (
    "Season rewards are virtual coins and cosmetics issued by the house for "
    "entertainment only. They have no cash value, cannot be redeemed, and "
    "cannot be transferred between players."
)

# Test clock. None means Australia/Perth now.
_clock: datetime | None = None


class SeasonError(ValueError):
    """User-facing season-pass error."""


def set_clock(when: datetime | None) -> None:
    """Freeze or clear the season clock (tests only)."""
    global _clock
    _clock = when


def now(when: datetime | None = None) -> datetime:
    dt = when or _clock or perth_now()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=PERTH)
    return dt.astimezone(PERTH)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def xp_cost(tier: int) -> int:
    """XP needed to reach this tier from the previous one."""
    t = max(1, min(TIER_COUNT, int(tier)))
    return 80 + (t - 1) * 25


def cumulative_xp(tier: int) -> int:
    t = max(0, min(TIER_COUNT, int(tier)))
    if t <= 0:
        return 0
    # sum_{k=1..t} (80 + (k-1)*25) = 80t + 25*t*(t-1)/2
    return 80 * t + 25 * t * (t - 1) // 2


def tier_for_xp(xp: int) -> int:
    xp = max(0, int(xp or 0))
    reached = 0
    for t in range(1, TIER_COUNT + 1):
        if xp >= cumulative_xp(t):
            reached = t
        else:
            break
    return reached


def play_xp(bet_coins: int, win_coins: int = 0) -> int:
    """XP for a settled play. Losses count; win_coins never gates the grant."""
    del win_coins  # wins do not change play XP and must not trigger a celebration
    return 1 + max(0, int(bet_coins or 0)) // 50


def claim_key(player_id: str, season_id: str, track: str, tier: int) -> str:
    return f"season-claim:{season_id}:player:{player_id}:track:{track}:tier:{int(tier)}"


def _reward_for(track: str, tier: int) -> dict[str, Any]:
    t = int(tier)
    if track == "premium":
        if t % 10 == 0:
            item = EMBLEMS[(t // 10 + 2) % len(EMBLEMS)]
            return {"kind": "emblem", "id": f"premium-{item['id']}", "label": f"Premium {item['label']}", "src": item["src"], "amount": 0}
        if t % 5 == 0:
            item = FRAMES[(t // 5) % len(FRAMES)]
            return {"kind": "frame", "id": f"premium-{item['id']}", "label": f"Premium {item['label']}", "color": item["color"], "amount": 0}
        return {"kind": "coins", "id": "", "label": f"{800 + t * 120:,} coins", "amount": 800 + t * 120}
    # Free track
    if t % 10 == 0:
        item = EMBLEMS[(t // 10 - 1) % len(EMBLEMS)]
        return {"kind": "emblem", "id": item["id"], "label": item["label"], "src": item["src"], "amount": 0}
    if t % 5 == 0:
        item = FRAMES[(t // 5 - 1) % len(FRAMES)]
        return {"kind": "frame", "id": item["id"], "label": item["label"], "color": item["color"], "amount": 0}
    return {"kind": "coins", "id": "", "label": f"{400 + t * 80:,} coins", "amount": 400 + t * 80}


def _tiers_payload(track: str) -> list[dict[str, Any]]:
    out = []
    for t in range(1, TIER_COUNT + 1):
        reward = _reward_for(track, t)
        out.append({
            "tier": t,
            "xp_required": cumulative_xp(t),
            "xp_cost": xp_cost(t),
            "reward": reward,
        })
    return out


def current_season(when: datetime | None = None) -> dict[str, Any]:
    dt = now(when)
    epoch = season_epoch()
    days = (dt.date() - epoch.date()).days
    if days < 0:
        idx = 0
        start = epoch
    else:
        idx = days // SEASON_DAYS
        start = epoch + timedelta(days=idx * SEASON_DAYS)
    end = start + timedelta(days=SEASON_DAYS)
    name = SEASON_NAMES[idx % len(SEASON_NAMES)]
    return {
        "id": "S" + start.strftime("%Y%m%d"),
        "index": idx + 1,
        "name": name,
        "title": f"Season {idx + 1}: {name}",
        "starts_at": start.isoformat(),
        "ends_at": end.isoformat(),
        "ends_at_label": end.strftime("%d %b %Y, %H:%M").lstrip("0") + " Australia/Perth",
        "days": SEASON_DAYS,
        "active": start <= dt < end,
        "legal": LEGAL,
        "premium_note": PREMIUM_NOTE,
        "premium_purchase_enabled": PREMIUM_PURCHASE_ENABLED,
    }


def season_open(when: datetime | None = None) -> bool:
    return bool(current_season(when)["active"])


def daily_missions_for(when: datetime | None = None) -> list[dict[str, Any]]:
    day = now(when).date()
    start = day.toordinal() % len(DAILY_POOL)
    return [dict(DAILY_POOL[(start + i) % len(DAILY_POOL)]) for i in range(3)]


def catalogue(when: datetime | None = None) -> dict[str, Any]:
    season = current_season(when)
    return {
        "season": season,
        "tier_count": TIER_COUNT,
        "free": _tiers_payload("free"),
        "premium": _tiers_payload("premium"),
        "daily": daily_missions_for(when),
        "weekly": [dict(m) for m in WEEKLY_MISSIONS],
        "legal": LEGAL,
        "premium_note": PREMIUM_NOTE,
    }


def ensure_schema(conn: Any) -> None:
    if not prefs.schema_migrate_allowed():
        return
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS season_progress (
            player_id TEXT NOT NULL,
            season_id TEXT NOT NULL,
            xp INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (player_id, season_id)
        );
        CREATE TABLE IF NOT EXISTS season_claims (
            claim_key TEXT PRIMARY KEY,
            player_id TEXT NOT NULL,
            season_id TEXT NOT NULL,
            track TEXT NOT NULL,
            tier INTEGER NOT NULL,
            reward_kind TEXT NOT NULL,
            reward_id TEXT,
            amount INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS season_claims_unique
            ON season_claims(player_id, season_id, track, tier);
        CREATE TABLE IF NOT EXISTS season_missions (
            player_id TEXT NOT NULL,
            season_id TEXT NOT NULL,
            period TEXT NOT NULL,
            mission_id TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            target INTEGER NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,
            xp_granted INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (player_id, season_id, period, mission_id)
        );
        CREATE TABLE IF NOT EXISTS season_cosmetics (
            player_id TEXT NOT NULL,
            item_kind TEXT NOT NULL,
            item_id TEXT NOT NULL,
            season_id TEXT NOT NULL,
            equipped INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            PRIMARY KEY (player_id, item_kind, item_id)
        );
        """
    )


def _ensure_progress(conn: Any, player_id: str, season_id: str) -> None:
    conn.execute(
        """
        INSERT INTO season_progress (player_id, season_id, xp, updated_at)
        VALUES (?, ?, 0, ?)
        ON CONFLICT (player_id, season_id) DO NOTHING
        """,
        (player_id, season_id, _utc_iso()),
    )


def _ensure_missions(conn: Any, player_id: str, season_id: str, when: datetime | None = None) -> None:
    day = perth_date(now(when))
    week = perth_week(now(when))
    for spec in daily_missions_for(when):
        conn.execute(
            """
            INSERT INTO season_missions
                (player_id, season_id, period, mission_id, progress, target, completed, xp_granted)
            VALUES (?, ?, ?, ?, 0, ?, 0, 0)
            ON CONFLICT (player_id, season_id, period, mission_id) DO NOTHING
            """,
            (player_id, season_id, day, spec["id"], int(spec["target"])),
        )
    for spec in WEEKLY_MISSIONS:
        conn.execute(
            """
            INSERT INTO season_missions
                (player_id, season_id, period, mission_id, progress, target, completed, xp_granted)
            VALUES (?, ?, ?, ?, 0, ?, 0, 0)
            ON CONFLICT (player_id, season_id, period, mission_id) DO NOTHING
            """,
            (player_id, season_id, week, spec["id"], int(spec["target"])),
        )


def _spec_by_id(mission_id: str) -> dict[str, Any] | None:
    for m in DAILY_POOL:
        if m["id"] == mission_id:
            return dict(m)
    for m in WEEKLY_MISSIONS:
        if m["id"] == mission_id:
            return dict(m)
    return None


def _mission_inc(spec: dict[str, Any], game: str, bet_coins: int, win_coins: int) -> int:
    typ = spec.get("type")
    g = (game or "").lower()
    if typ in ("spins", "plays"):
        return 1
    if typ == "wins":
        return 1 if int(win_coins or 0) > 0 else 0
    if typ == "game_wins":
        return 1 if g == (spec.get("game") or "") and int(win_coins or 0) > 0 else 0
    if typ == "game_plays":
        return 1 if g == (spec.get("game") or "") else 0
    if typ == "bet":
        return max(0, int(bet_coins or 0))
    return 0


def _add_xp(conn: Any, player_id: str, season_id: str, amount: int) -> None:
    if amount <= 0:
        return
    _ensure_progress(conn, player_id, season_id)
    conn.execute(
        """
        UPDATE season_progress
        SET xp = xp + ?, updated_at = ?
        WHERE player_id = ? AND season_id = ?
        """,
        (int(amount), _utc_iso(), player_id, season_id),
    )


def on_play(player_id: str, game: str, bet_coins: int, win_coins: int, meta: dict[str, Any] | None = None, **_kw: Any) -> None:
    """events.on_play subscriber. Never raises into the game path. Never celebrates."""
    try:
        record_play(player_id, game, int(bet_coins or 0), int(win_coins or 0))
    except Exception:
        return


def record_play(player_id: str, game: str, bet_coins: int, win_coins: int, when: datetime | None = None) -> dict[str, Any]:
    """Apply play XP and mission progress. Returns a no-celebration payload."""
    import ledger

    out = {"xp_gained": 0, "celebrate": False, "win_celebration": False}
    if not prefs.schema_migrate_allowed():
        return out
    if not season_open(when):
        return out
    season = current_season(when)
    sid = season["id"]
    gained = play_xp(bet_coins, win_coins)
    with ledger.transaction() as conn:
        ensure_schema(conn)
        _ensure_progress(conn, player_id, sid)
        _ensure_missions(conn, player_id, sid, when)
        if gained > 0:
            _add_xp(conn, player_id, sid, gained)
            out["xp_gained"] = gained
        day = perth_date(now(when))
        week = perth_week(now(when))
        rows = conn.execute(
            """
            SELECT period, mission_id, progress, target, xp_granted
            FROM season_missions
            WHERE player_id = ? AND season_id = ? AND period IN (?, ?)
            """,
            (player_id, sid, day, week),
        ).fetchall()
        for row in rows:
            spec = _spec_by_id(row["mission_id"])
            if not spec:
                continue
            inc = _mission_inc(spec, game, bet_coins, win_coins)
            if inc <= 0:
                continue
            new_p = min(int(row["target"]), int(row["progress"]) + inc)
            conn.execute(
                """
                UPDATE season_missions
                SET progress = ?
                WHERE player_id = ? AND season_id = ? AND period = ? AND mission_id = ?
                """,
                (new_p, player_id, sid, row["period"], row["mission_id"]),
            )
            if new_p >= int(row["target"]) and int(row["xp_granted"] or 0) == 0:
                # Idempotent grant: only the first UPDATE that flips xp_granted pays XP.
                flipped = conn.execute(
                    """
                    UPDATE season_missions
                    SET completed = 1, xp_granted = 1
                    WHERE player_id = ? AND season_id = ? AND period = ? AND mission_id = ?
                      AND xp_granted = 0
                    """,
                    (player_id, sid, row["period"], row["mission_id"]),
                )
                if int(getattr(flipped, "rowcount", 0) or 0) == 1:
                    _add_xp(conn, player_id, sid, int(spec.get("xp") or 0))
                    out["xp_gained"] += int(spec.get("xp") or 0)
    return out


def claim_tier(player_id: str, tier: int, track: str = "free", when: datetime | None = None) -> dict[str, Any]:
    """Pay a reached free-track reward once. Idempotent per player/season/tier."""
    import ledger
    from game import COIN_ASSET

    ledger.ensure_player(player_id)
    if not prefs.schema_migrate_allowed():
        raise SeasonError("The season pass is not available on this database yet")
    track = str(track or "free").strip().lower()
    if track not in ("free", "premium"):
        raise SeasonError("Choose the free or premium track")
    if track == "premium":
        # TODO(android): Play Billing may unlock this track later. Not sold on the web.
        raise SeasonError(PREMIUM_NOTE)
    if not season_open(when):
        raise SeasonError("This season has ended. Unclaimed tiers cannot be collected after the end date.")
    season = current_season(when)
    sid = season["id"]
    t = int(tier)
    if t < 1 or t > TIER_COUNT:
        raise SeasonError("That season tier was not found")
    reward = _reward_for("free", t)
    key = claim_key(player_id, sid, "free", t)
    awarded = 0
    already = False
    granted: dict[str, Any] | None = None
    with ledger.transaction() as conn:
        ensure_schema(conn)
        ledger.lock_player(conn, player_id)
        _ensure_progress(conn, player_id, sid)
        row = conn.execute(
            "SELECT xp FROM season_progress WHERE player_id = ? AND season_id = ?",
            (player_id, sid),
        ).fetchone()
        xp = int(row["xp"] if row else 0)
        if tier_for_xp(xp) < t:
            raise SeasonError("You have not reached that tier yet")
        existing = conn.execute(
            "SELECT claim_key, amount, reward_kind FROM season_claims WHERE claim_key = ?",
            (key,),
        ).fetchone()
        if existing:
            already = True
        else:
            inserted = conn.execute(
                """
                INSERT INTO season_claims
                    (claim_key, player_id, season_id, track, tier, reward_kind, reward_id, amount, created_at)
                VALUES (?, ?, ?, 'free', ?, ?, ?, ?, ?)
                ON CONFLICT (claim_key) DO NOTHING
                """,
                (key, player_id, sid, t, reward["kind"], reward.get("id") or "", int(reward.get("amount") or 0), _utc_iso()),
            )
            if int(getattr(inserted, "rowcount", 0) or 0) == 0:
                already = True
            else:
                if reward["kind"] == "coins":
                    awarded = int(reward.get("amount") or 0)
                    if awarded > 0:
                        ledger._credit(conn, player_id, COIN_ASSET, awarded)
                        conn.execute(
                            """
                            INSERT INTO ledger_entries
                                (player_id, kind, asset, amount, stripe_session_id, note, created_at)
                            VALUES (?, 'season_reward', ?, ?, ?, ?, ?)
                            """,
                            (
                                player_id,
                                COIN_ASSET,
                                awarded,
                                key,
                                f"Season {sid} free tier {t} — virtual coins, no cash value",
                                _utc_iso(),
                            ),
                        )
                else:
                    conn.execute(
                        """
                        INSERT INTO season_cosmetics
                            (player_id, item_kind, item_id, season_id, equipped, created_at)
                        VALUES (?, ?, ?, ?, 0, ?)
                        ON CONFLICT (player_id, item_kind, item_id) DO NOTHING
                        """,
                        (player_id, reward["kind"], reward.get("id") or "", sid, _utc_iso()),
                    )
                granted = dict(reward)
    snap = ledger.snapshot(player_id)
    state = season_state(player_id, when=when)
    state["snapshot"] = snap
    state["awarded"] = 0 if already else awarded
    state["reward"] = granted
    state["already_claimed"] = already
    state["celebrate"] = (not already) and granted is not None
    state["bonus"] = "season"
    if already:
        state["error"] = "Already claimed this season tier"
    return state


def season_state(player_id: str, when: datetime | None = None) -> dict[str, Any]:
    import ledger

    cat = catalogue(when)
    out: dict[str, Any] = {
        "available": prefs.schema_migrate_allowed(),
        "catalog": cat,
        "season": cat["season"],
        "xp": 0,
        "tier": 0,
        "next_xp": cumulative_xp(1),
        "claims": {"free": [], "premium": []},
        "missions": {"daily": [], "weekly": []},
        "cosmetics": [],
        "celebrate": False,
        "win_celebration": False,
    }
    if not out["available"]:
        return out
    try:
        ensure_schema(ledger.get_conn())
        conn = ledger.get_conn()
        sid = cat["season"]["id"]
        _ensure_progress(conn, player_id, sid)
        _ensure_missions(conn, player_id, sid, when)
        # _ensure_* may have written; commit if the connection is autocommit is fine.
        try:
            conn.commit()
        except Exception:
            pass
        prow = conn.execute(
            "SELECT xp FROM season_progress WHERE player_id = ? AND season_id = ?",
            (player_id, sid),
        ).fetchone()
        xp = int(prow["xp"] if prow else 0)
        reached = tier_for_xp(xp)
        out["xp"] = xp
        out["tier"] = reached
        out["next_xp"] = cumulative_xp(min(TIER_COUNT, reached + 1))
        claimed_rows = conn.execute(
            "SELECT track, tier, reward_kind, reward_id, amount FROM season_claims WHERE player_id = ? AND season_id = ?",
            (player_id, sid),
        ).fetchall()
        claims = {"free": [], "premium": []}
        claimed_set = set()
        for r in claimed_rows:
            claims.setdefault(r["track"], []).append(int(r["tier"]))
            claimed_set.add((r["track"], int(r["tier"])))
        out["claims"] = claims

        def _fill(track: str) -> list[dict[str, Any]]:
            rows = []
            for item in cat[track]:
                t = int(item["tier"])
                claimed = (track, t) in claimed_set
                reached_t = reached >= t
                rows.append({
                    **item,
                    "claimed": claimed,
                    "reached": reached_t,
                    "can_claim": track == "free" and reached_t and not claimed and bool(cat["season"]["active"]),
                    "locked": track == "premium" or not reached_t,
                })
            return rows

        out["free"] = _fill("free")
        out["premium"] = _fill("premium")
        day = perth_date(now(when))
        week = perth_week(now(when))

        def _mission_view(spec: dict[str, Any], period: str) -> dict[str, Any]:
            row = conn.execute(
                """
                SELECT progress, target, completed, xp_granted
                FROM season_missions
                WHERE player_id = ? AND season_id = ? AND period = ? AND mission_id = ?
                """,
                (player_id, sid, period, spec["id"]),
            ).fetchone()
            progress = int(row["progress"]) if row else 0
            target = int(row["target"]) if row else int(spec["target"])
            return {
                "id": spec["id"],
                "title": spec["title"],
                "type": spec["type"],
                "game": spec.get("game"),
                "progress": progress,
                "target": target,
                "xp": int(spec["xp"]),
                "completed": bool(row and (int(row["completed"]) or progress >= target)),
                "xp_granted": bool(row and int(row["xp_granted"] or 0) == 1),
                "period": period,
            }

        out["missions"] = {
            "daily": [_mission_view(m, day) for m in daily_missions_for(when)],
            "weekly": [_mission_view(m, week) for m in WEEKLY_MISSIONS],
        }
        cos = conn.execute(
            "SELECT item_kind, item_id, season_id, equipped FROM season_cosmetics WHERE player_id = ?",
            (player_id,),
        ).fetchall()
        out["cosmetics"] = [
            {"kind": r["item_kind"], "id": r["item_id"], "season_id": r["season_id"], "equipped": bool(int(r["equipped"]))}
            for r in cos
        ]
        return out
    except Exception:
        out["available"] = False
        return out

import events as _events
_events.register(on_play)
