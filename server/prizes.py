"""In-game prizes for the social casino: trophies, themes, missions, leaderboards.

All prizes are virtual — coins, cosmetics and bragging rights only.
They have no cash or real-world value and cannot be redeemed, transferred
or exchanged for money or prizes.
"""

from __future__ import annotations

import math
import random
import re
import html
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from game import to_coins

PERTH = ZoneInfo("Australia/Perth")

NICK_MIN = 2
NICK_MAX = 16
DEFAULT_THEME = "crystal"
XP_BASE = 80
MAX_LEVEL = 99
BIG_WIN_X = 15
MEGA_WIN_X = 50
EPIC_WIN_X = 150

# Top-3 coin grants (promotional, like the daily chest). Coins only.
LEADERBOARD_COINS = {1: 25_000, 2: 10_000, 3: 5_000}
LEADERBOARD_LIMIT = 10

PROFANITY = frozenset(
    {
        "anal", "anus", "arse", "ass", "asshole", "bastard", "bitch", "boob",
        "clit", "cock", "coon", "crap", "cunt", "cum", "dick", "dildo", "dyke",
        "fag", "faggot", "fuck", "fucker", "fucking", "homo", "jizz", "kike",
        "nazi", "nigger", "nigga", "pedo", "penis", "piss", "porn", "pussy",
        "queer", "rape", "rapist", "retard", "shit", "slut", "spank", "spic",
        "tit", "twat", "vagina", "wank", "whore",
    }
)


class ThemeLocked(ValueError):
    pass


class MissionUnavailable(ValueError):
    pass


THEMES = (
    {"id": "crystal", "name": "Crystal", "unlock_level": 1},
    {"id": "ruby", "name": "Ruby Palace", "unlock_level": 2},
    {"id": "jade", "name": "Jade Garden", "unlock_level": 5},
    {"id": "sapphire", "name": "Sapphire Night", "unlock_level": 8},
)

TROPHIES = (
    {"id": "greentea_jackpot", "name": "Green Tea Jackpot", "desc": "Hit the Green Tea Jackpot", "icon": "🍵", "group": "jackpot"},
    {"id": "big_win", "name": "Big Win", "desc": "Win 15× your bet or more", "icon": "💎", "group": "wins"},
    {"id": "mega_win", "name": "Mega Win", "desc": "Win 50× your bet or more", "icon": "🌟", "group": "wins"},
    {"id": "epic_win", "name": "Epic Win", "desc": "Win 150× your bet or more", "icon": "👑", "group": "wins"},
    {"id": "free_spins", "name": "Bonus Unlocked", "desc": "Trigger a free-spins bonus", "icon": "🎰", "group": "features"},
    {"id": "crystal_pick", "name": "Crystal Pick", "desc": "Win a Crystal Pick mini game", "icon": "🔮", "group": "features"},
    {"id": "tea_wheel", "name": "Tea Wheel", "desc": "Spin the Tea Wheel", "icon": "🎡", "group": "features"},
    {"id": "level_5", "name": "Level 5", "desc": "Reach level 5", "icon": "⑤", "group": "level"},
    {"id": "level_10", "name": "Level 10", "desc": "Reach level 10", "icon": "⑩", "group": "level"},
    {"id": "level_25", "name": "Level 25", "desc": "Reach level 25", "icon": "★", "group": "level"},
    {"id": "streak_5", "name": "Hot Streak", "desc": "Win 5 spins in a row", "icon": "🔥", "group": "streak"},
    {"id": "streak_10", "name": "On Fire", "desc": "Win 10 spins in a row", "icon": "⚡", "group": "streak"},
    {"id": "lb_daily_gold", "name": "Daily Champion", "desc": "Finish 1st on a daily leaderboard", "icon": "🥇", "group": "leaders"},
    {"id": "lb_daily_silver", "name": "Daily Silver", "desc": "Finish 2nd on a daily leaderboard", "icon": "🥈", "group": "leaders"},
    {"id": "lb_daily_bronze", "name": "Daily Bronze", "desc": "Finish 3rd on a daily leaderboard", "icon": "🥉", "group": "leaders"},
    {"id": "lb_weekly_gold", "name": "Weekly Champion", "desc": "Finish 1st on a weekly leaderboard", "icon": "🏆", "group": "leaders"},
    {"id": "lb_weekly_silver", "name": "Weekly Silver", "desc": "Finish 2nd on a weekly leaderboard", "icon": "🥈", "group": "leaders"},
    {"id": "lb_weekly_bronze", "name": "Weekly Bronze", "desc": "Finish 3rd on a weekly leaderboard", "icon": "🥉", "group": "leaders"},
    {"id": "badge_big_hunter", "name": "Big Hunter", "desc": "Complete the Land a Big Win mission", "icon": "🎯", "group": "missions"},
    {"id": "hold_spin", "name": "Hold & Spin", "desc": "Trigger the Crystal Hold & Spin bonus", "icon": "🪙", "group": "features"},
    {"id": "hold_grand", "name": "All Locked", "desc": "Fill every cell in Hold & Spin", "icon": "💍", "group": "features"},
    {"id": "progressive_hit", "name": "Crown Jackpot", "desc": "Hit the Crystal Crown progressive", "icon": "👑", "group": "jackpot"},
    {"id": "collection_set", "name": "Collector", "desc": "Complete a Crystal Collection set", "icon": "📦", "group": "features"},
    {"id": "vip_gold", "name": "VIP Gold", "desc": "Reach the Gold VIP tier", "icon": "🥇", "group": "vip"},
    {"id": "vip_diamond", "name": "VIP Diamond", "desc": "Reach the Diamond VIP tier", "icon": "💎", "group": "vip"},
    {"id": "lb_weekend_gold", "name": "Weekend Champion", "desc": "Finish 1st in a weekend tournament", "icon": "🏅", "group": "leaders"},
    {"id": "lb_weekend_silver", "name": "Weekend Silver", "desc": "Finish 2nd in a weekend tournament", "icon": "🥈", "group": "leaders"},
    {"id": "lb_weekend_bronze", "name": "Weekend Bronze", "desc": "Finish 3rd in a weekend tournament", "icon": "🥉", "group": "leaders"},
)

MISSION_CATALOGUE = (
    {"id": "spin_50", "title": "Spin 50 times", "type": "spins", "target": 50, "reward_coins": 4000, "reward_trophy": None},
    {"id": "spin_25", "title": "Spin 25 times", "type": "spins", "target": 25, "reward_coins": 2000, "reward_trophy": None},
    {"id": "trigger_fs", "title": "Trigger free spins", "type": "free_spins", "target": 1, "reward_coins": 5000, "reward_trophy": None},
    {"id": "win_10x", "title": "Win 10× your bet", "type": "win_mult", "target": 1, "mult": 10, "reward_coins": 5000, "reward_trophy": None},
    {"id": "win_15", "title": "Win 15 spins", "type": "win_spins", "target": 15, "reward_coins": 3000, "reward_trophy": None},
    {"id": "big_hit", "title": "Land a Big Win (15×)", "type": "win_mult", "target": 1, "mult": 15, "reward_coins": 8000, "reward_trophy": "badge_big_hunter"},
    {"id": "mini_play", "title": "Win a mini game", "type": "minigame", "target": 1, "reward_coins": 4000, "reward_trophy": None},
)

_TROPHY_BY_ID = {t["id"]: t for t in TROPHIES}
_MISSION_BY_ID = {m["id"]: m for m in MISSION_CATALOGUE}
_THEME_BY_ID = {t["id"]: t for t in THEMES}

PRIZE_LEGAL = (
    "All in-game prizes are for entertainment only. Trophies, themes, badges "
    "and bonus coins have no cash or real-world value and cannot be redeemed "
    "for money or prizes."
)


def perth_now() -> datetime:
    return datetime.now(PERTH)


def perth_date(when: datetime | None = None) -> str:
    return (when or perth_now()).date().isoformat()


def perth_week(when: datetime | None = None) -> str:
    dt = when or perth_now()
    y, w, _ = dt.isocalendar()
    return f"{y}-W{int(w):02d}"


# VIP tiers by level. Perks are free-play only (bigger hourly/daily coins).
# Nothing here is locked behind a coin-pack purchase.
VIP_TIERS = (
    {"id": "bronze", "name": "Bronze", "min_level": 1, "hourly_mult": 1.0, "daily_mult": 1.0},
    {"id": "silver", "name": "Silver", "min_level": 5, "hourly_mult": 1.25, "daily_mult": 1.1},
    {"id": "gold", "name": "Gold", "min_level": 10, "hourly_mult": 1.5, "daily_mult": 1.2},
    {"id": "platinum", "name": "Platinum", "min_level": 20, "hourly_mult": 2.0, "daily_mult": 1.3},
    {"id": "diamond", "name": "Diamond", "min_level": 35, "hourly_mult": 2.5, "daily_mult": 1.5},
)
WEEKEND_COINS = {1: 50_000, 2: 20_000, 3: 10_000}


def vip_for_level(level: int) -> dict[str, Any]:
    from game import HOURLY_COINS, DAILY_COINS
    level = max(1, int(level or 1))
    chosen = VIP_TIERS[0]
    for tier in VIP_TIERS:
        if level >= int(tier["min_level"]):
            chosen = tier
    nxt = None
    for tier in VIP_TIERS:
        if int(tier["min_level"]) > level:
            nxt = {"id": tier["id"], "name": tier["name"], "min_level": tier["min_level"]}
            break
    return {
        "id": chosen["id"],
        "name": chosen["name"],
        "min_level": chosen["min_level"],
        "hourly_coins": int(round(HOURLY_COINS * chosen["hourly_mult"])),
        "daily_coins": int(round(DAILY_COINS * chosen["daily_mult"])),
        "next": nxt,
        "tiers": [
            {
                "id": t["id"], "name": t["name"], "min_level": t["min_level"],
                "hourly_coins": int(round(HOURLY_COINS * t["hourly_mult"])),
                "daily_coins": int(round(DAILY_COINS * t["daily_mult"])),
            }
            for t in VIP_TIERS
        ],
    }


def weekend_friday(when: datetime | None = None) -> datetime:
    """The Friday 00:00 that starts the weekend window containing `when`, or the most recent Friday."""
    dt = when or perth_now()
    # Monday=0 ... Sunday=6. Weekend tournament: Friday 00:00 through Sunday 23:59:59.
    wd = dt.weekday()
    if wd >= 4:
        days_back = wd - 4
    else:
        days_back = wd + 3
    start = (dt - timedelta(days=days_back)).replace(hour=0, minute=0, second=0, microsecond=0)
    return start


def perth_weekend(when: datetime | None = None) -> str:
    return weekend_friday(when).date().isoformat()


def weekend_active(when: datetime | None = None) -> bool:
    dt = when or perth_now()
    return dt.weekday() >= 4


def weekend_ends_at(when: datetime | None = None) -> str:
    start = weekend_friday(when)
    end = start + timedelta(days=3)  # Monday 00:00
    return end.isoformat()


def xp_needed(level: int) -> int:
    return XP_BASE * max(1, min(MAX_LEVEL, int(level)))


def default_nickname(player_id: str) -> str:
    tail = re.sub(r"[^A-Za-z0-9]", "", player_id or "")[-4:] or "0000"
    return f"Hopper{tail}"


def sanitize_nickname(raw: str) -> str:
    text = html.unescape(str(raw or ""))
    text = re.sub(r"<[^>]*>", " ", text)
    text = "".join(ch for ch in text if ch.isalnum() or ch in " -_.'")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > NICK_MAX:
        text = text[:NICK_MAX].rstrip()
    if len(text) < NICK_MIN:
        raise ValueError(f"Nickname must be {NICK_MIN}–{NICK_MAX} letters, numbers or spaces")
    compact = re.sub(r"[^a-z0-9]", "", text.lower())
    tokens = [tok for tok in re.split(r"[^a-z0-9]+", text.lower()) if tok]
    stems = {w for w in PROFANITY if len(w) >= 4}
    for word in PROFANITY:
        if word == compact or word in tokens:
            raise ValueError("Please choose another nickname")
    for stem in stems:
        if stem in compact:
            raise ValueError("Please choose another nickname")
    return text


def catalogue() -> dict[str, Any]:
    return {
        "trophies": [dict(t) for t in TROPHIES],
        "themes": [dict(t) for t in THEMES],
        "missions": [
            {
                "id": m["id"],
                "title": m["title"],
                "target": m["target"],
                "reward_coins": m["reward_coins"],
                "reward_trophy": m["reward_trophy"],
            }
            for m in MISSION_CATALOGUE
        ],
        "legal": PRIZE_LEGAL,
        "xp_base": XP_BASE,
        "leaderboard_coins": dict(LEADERBOARD_COINS),
        "weekend_coins": dict(WEEKEND_COINS),
        "vip": [dict(t) for t in VIP_TIERS],
    }


def ensure_schema(conn) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(players)").fetchall()}
    additions = {
        "nickname": "TEXT",
        "xp": "INTEGER NOT NULL DEFAULT 0",
        "level": "INTEGER NOT NULL DEFAULT 1",
        "best_streak": "INTEGER NOT NULL DEFAULT 0",
        "current_streak": "INTEGER NOT NULL DEFAULT 0",
        "theme": "TEXT NOT NULL DEFAULT 'crystal'",
    }
    for name, decl in additions.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE players ADD COLUMN {name} {decl}")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS trophies (
            player_id TEXT NOT NULL,
            trophy_id TEXT NOT NULL,
            unlocked_at TEXT NOT NULL,
            PRIMARY KEY (player_id, trophy_id)
        );
        CREATE TABLE IF NOT EXISTS spin_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            perth_date TEXT NOT NULL,
            perth_week TEXT NOT NULL,
            perth_weekend TEXT,
            bet_aud REAL NOT NULL,
            win_aud REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_spin_records_daily
            ON spin_records (perth_date, player_id);
        CREATE INDEX IF NOT EXISTS idx_spin_records_weekly
            ON spin_records (perth_week, player_id);
        CREATE TABLE IF NOT EXISTS missions (
            player_id TEXT NOT NULL,
            mission_date TEXT NOT NULL,
            slot INTEGER NOT NULL,
            mission_id TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            target INTEGER NOT NULL,
            claimed INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (player_id, mission_date, slot)
        );
        CREATE TABLE IF NOT EXISTS leaderboard_payouts (
            period_type TEXT NOT NULL,
            period_key TEXT NOT NULL,
            board TEXT NOT NULL,
            place INTEGER NOT NULL,
            player_id TEXT NOT NULL,
            coins INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (period_type, period_key, board, place)
        );
        """
    )


def _conn():
    import ledger
    return ledger.get_conn()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def daily_mission_ids(date_str: str) -> list[str]:
    ids = [m["id"] for m in MISSION_CATALOGUE]
    rng = random.Random(f"{date_str}:crystal-missions-v1")
    return rng.sample(ids, 3)


def ensure_daily_missions(player_id: str, date_str: str | None = None, ids: list[str] | None = None) -> list[dict[str, Any]]:
    import ledger
    ledger.ensure_player(player_id)
    day = date_str or perth_date()
    chosen = list(ids or daily_mission_ids(day))
    if len(chosen) != 3:
        raise ValueError("Daily missions come in threes")
    conn = _conn()
    rows = conn.execute(
        "SELECT slot, mission_id, progress, target, claimed FROM missions WHERE player_id = ? AND mission_date = ? ORDER BY slot",
        (player_id, day),
    ).fetchall()
    if not rows:
        with ledger.transaction() as c:
            existing = c.execute(
                "SELECT slot FROM missions WHERE player_id = ? AND mission_date = ?",
                (player_id, day),
            ).fetchone()
            if not existing:
                for slot, mid in enumerate(chosen):
                    spec = _MISSION_BY_ID.get(mid)
                    if not spec:
                        raise ValueError("Unknown mission")
                    c.execute(
                        """
                        INSERT INTO missions (player_id, mission_date, slot, mission_id, progress, target, claimed)
                        VALUES (?, ?, ?, ?, 0, ?, 0)
                        """,
                        (player_id, day, slot, mid, int(spec["target"])),
                    )
        rows = conn.execute(
            "SELECT slot, mission_id, progress, target, claimed FROM missions WHERE player_id = ? AND mission_date = ? ORDER BY slot",
            (player_id, day),
        ).fetchall()
    return [_mission_view(r) for r in rows]


def _mission_view(row) -> dict[str, Any]:
    mid = row["mission_id"]
    spec = _MISSION_BY_ID.get(mid) or {"title": mid, "reward_coins": 0, "reward_trophy": None, "target": row["target"]}
    progress = int(row["progress"])
    target = int(row["target"])
    claimed = int(row["claimed"]) == 1
    return {
        "id": mid,
        "slot": int(row["slot"]),
        "title": spec["title"],
        "progress": progress,
        "target": target,
        "complete": progress >= target,
        "claimed": claimed,
        "reward_coins": int(spec.get("reward_coins") or 0),
        "reward_trophy": spec.get("reward_trophy"),
        "claimable": progress >= target and not claimed,
    }


def mission_state(player_id: str, date_str: str | None = None) -> list[dict[str, Any]]:
    return ensure_daily_missions(player_id, date_str)


def unlocked_ids(player_id: str) -> set[str]:
    rows = _conn().execute(
        "SELECT trophy_id FROM trophies WHERE player_id = ?",
        (player_id,),
    ).fetchall()
    return {r["trophy_id"] for r in rows}


def _unlock(conn, player_id: str, trophy_id: str, now: str, newly: list[dict[str, Any]]) -> None:
    if trophy_id not in _TROPHY_BY_ID:
        return
    try:
        conn.execute(
            "INSERT INTO trophies (player_id, trophy_id, unlocked_at) VALUES (?, ?, ?)",
            (player_id, trophy_id, now),
        )
    except Exception:
        return
    # unique constraint: already owned
    row = conn.execute(
        "SELECT changes() AS n"
    ).fetchone()
    # INSERT OR IGNORE is cleaner
    newly.append(dict(_TROPHY_BY_ID[trophy_id]))


def _unlock_many(conn, player_id: str, ids: list[str], now: str) -> list[dict[str, Any]]:
    newly: list[dict[str, Any]] = []
    have = {
        r["trophy_id"]
        for r in conn.execute(
            "SELECT trophy_id FROM trophies WHERE player_id = ?",
            (player_id,),
        ).fetchall()
    }
    for tid in ids:
        if tid in have or tid not in _TROPHY_BY_ID:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO trophies (player_id, trophy_id, unlocked_at) VALUES (?, ?, ?)",
            (player_id, tid, now),
        )
        have.add(tid)
        newly.append(dict(_TROPHY_BY_ID[tid]))
    return newly


def _profile_row(conn, player_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT nickname, xp, level, best_streak, current_streak, theme FROM players WHERE id = ?",
        (player_id,),
    ).fetchone()
    if not row:
        return {
            "nickname": default_nickname(player_id),
            "xp": 0,
            "level": 1,
            "best_streak": 0,
            "current_streak": 0,
            "theme": DEFAULT_THEME,
        }
    return {
        "nickname": row["nickname"] or default_nickname(player_id),
        "xp": int(row["xp"] or 0),
        "level": int(row["level"] or 1),
        "best_streak": int(row["best_streak"] or 0),
        "current_streak": int(row["current_streak"] or 0),
        "theme": row["theme"] or DEFAULT_THEME,
    }


def profile_public(player_id: str) -> dict[str, Any]:
    p = _profile_row(_conn(), player_id)
    p["xp_needed"] = xp_needed(p["level"])
    p["theme"] = p["theme"] if theme_unlocked_at(p["level"], p["theme"]) else DEFAULT_THEME
    p["vip"] = vip_for_level(p["level"])
    return p


def theme_unlocked_at(level: int, theme_id: str) -> bool:
    spec = _THEME_BY_ID.get(theme_id)
    if not spec:
        return False
    return int(level) >= int(spec["unlock_level"])


def themes_public(player_id: str) -> list[dict[str, Any]]:
    p = _profile_row(_conn(), player_id)
    selected = p["theme"] if theme_unlocked_at(p["level"], p["theme"]) else DEFAULT_THEME
    out = []
    for t in THEMES:
        unlocked = theme_unlocked_at(p["level"], t["id"])
        out.append({
            "id": t["id"],
            "name": t["name"],
            "unlock_level": t["unlock_level"],
            "unlocked": unlocked,
            "selected": t["id"] == selected,
        })
    return out


def trophies_public(player_id: str, newly: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    have = unlocked_ids(player_id)
    return {
        "unlocked": sorted(have),
        "new": list(newly or []),
        "items": [
            {**dict(t), "unlocked": t["id"] in have}
            for t in TROPHIES
        ],
    }


def attach(player_id: str, snap: dict[str, Any] | None = None, newly: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Add prize fields to a ledger snapshot (never pool/cap)."""
    import ledger
    ledger.ensure_player(player_id)
    ensure_daily_missions(player_id)
    out = snap if snap is not None else {}
    out["profile"] = profile_public(player_id)
    out["trophies"] = trophies_public(player_id, newly)
    out["missions"] = mission_state(player_id)
    out["themes"] = themes_public(player_id)
    out["prize_legal"] = PRIZE_LEGAL
    out["weekend"] = {
        "active": weekend_active(),
        "key": perth_weekend(),
        "ends_at": weekend_ends_at(),
        "rewards": [{"place": p, "coins": c} for p, c in WEEKEND_COINS.items()],
    }
    return out


def set_nickname(player_id: str, raw: str) -> dict[str, Any]:
    import ledger
    ledger.ensure_player(player_id)
    nick = sanitize_nickname(raw)
    with ledger.transaction() as conn:
        conn.execute("UPDATE players SET nickname = ? WHERE id = ?", (nick, player_id))
    return attach(player_id, ledger.snapshot(player_id))


def set_theme(player_id: str, theme_id: str) -> dict[str, Any]:
    import ledger
    ledger.ensure_player(player_id)
    spec = _THEME_BY_ID.get(theme_id)
    if not spec:
        raise ValueError("Unknown theme")
    level = profile_public(player_id)["level"]
    if not theme_unlocked_at(level, theme_id):
        raise ThemeLocked(f"{spec['name']} unlocks at level {spec['unlock_level']}")
    with ledger.transaction() as conn:
        conn.execute("UPDATE players SET theme = ? WHERE id = ?", (theme_id, player_id))
    return attach(player_id, ledger.snapshot(player_id))


def debug_set_level(player_id: str, level: int, xp: int = 0) -> None:
    """Test helper: set an authoritative level."""
    import ledger
    ledger.ensure_player(player_id)
    level = max(1, min(MAX_LEVEL, int(level)))
    with ledger.transaction() as conn:
        conn.execute("UPDATE players SET level = ?, xp = ? WHERE id = ?", (level, int(xp), player_id))
        _unlock_many(conn, player_id, _level_trophies(level), _now_iso())


def _level_trophies(level: int) -> list[str]:
    out = []
    if level >= 5:
        out.append("level_5")
    if level >= 10:
        out.append("level_10")
    if level >= 25:
        out.append("level_25")
    return out


def _xp_for_spin(bet: float, win: float, bonus: bool, big: bool) -> int:
    xp = 8
    if win > 0 and bet > 0:
        xp += int(round(min(50, 5 * math.sqrt(win / bet))))
    if bonus:
        xp += 25
    if big:
        xp += 40
    return xp


def _advance_xp(level: int, xp: int, gained: int) -> tuple[int, int, int]:
    """Returns (level, xp, new_level_or_0)."""
    xp = int(xp) + int(gained)
    leveled = 0
    while level < MAX_LEVEL and xp >= xp_needed(level):
        xp -= xp_needed(level)
        level += 1
        leveled = level
    if level >= MAX_LEVEL:
        level = MAX_LEVEL
        xp = min(xp, xp_needed(level) - 1)
    return level, xp, leveled


def after_spin(
    player_id: str,
    bet_aud: float,
    win_aud: float,
    jackpot_paid_aud: float,
    rnd: dict[str, Any],
    settled_steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Record a settled paid spin, update streaks/XP/missions/trophies.

    Does not change game math or the house pool.
    """
    import ledger
    now = _now_iso()
    when = perth_now()
    day = perth_date(when)
    week = perth_week(when)
    steps = settled_steps or []
    base = rnd.get("base") or {}
    games = list(rnd.get("minigames") or [])
    free_awarded = int(base.get("free_spins_awarded") or 0) + sum(int(g.get("free_spins") or 0) for g in games)
    for fs in rnd.get("free_spins") or []:
        if int(fs.get("free_spins_awarded") or 0) > 0:
            free_awarded += int(fs["free_spins_awarded"])
    pick_win = False
    wheel = False
    for step, se in zip(
        [base] + games + list(rnd.get("free_spins") or []),
        steps or [None] * (1 + len(games) + len(rnd.get("free_spins") or [])),
    ):
        kind = (se or {}).get("kind") or step.get("kind") or "spin"
        paid = float((se or {}).get("paid_aud") or 0) + float((se or {}).get("jackpot_aud") or 0)
        if kind == "pick" and (paid > 0 or float(step.get("raw_win_aud") or 0) > 0):
            pick_win = True
        if kind == "wheel":
            wheel = True
    # If settled_steps shorter, still detect from rnd
    if not pick_win:
        pick_win = any(g.get("kind") == "pick" and float(g.get("raw_win_aud") or 0) > 0 for g in games)
    if not wheel:
        wheel = any(g.get("kind") == "wheel" for g in games)

    ratio = (float(win_aud) / float(bet_aud)) if bet_aud else 0.0
    bonus = free_awarded > 0 or bool(games)
    big = ratio >= BIG_WIN_X or float(jackpot_paid_aud) > 0
    gained = _xp_for_spin(float(bet_aud), float(win_aud), bonus, big)

    ensure_daily_missions(player_id, day)
    newly: list[dict[str, Any]] = []
    level_up = 0
    with ledger.transaction() as conn:
        conn.execute(
            """
            INSERT INTO spin_records (player_id, created_at, perth_date, perth_week, perth_weekend, bet_aud, win_aud)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (player_id, now, day, week, perth_weekend(when), float(bet_aud), float(win_aud)),
        )
        row = conn.execute(
            "SELECT xp, level, current_streak, best_streak FROM players WHERE id = ?",
            (player_id,),
        ).fetchone()
        xp = int(row["xp"] or 0)
        level = int(row["level"] or 1)
        streak = int(row["current_streak"] or 0)
        best = int(row["best_streak"] or 0)
        if float(win_aud) > 0:
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
        level, xp, level_up = _advance_xp(level, xp, gained)
        conn.execute(
            "UPDATE players SET xp = ?, level = ?, current_streak = ?, best_streak = ? WHERE id = ?",
            (xp, level, streak, best, player_id),
        )

        want: list[str] = []
        if float(jackpot_paid_aud) > 0:
            want.append("greentea_jackpot")
        if ratio >= BIG_WIN_X:
            want.append("big_win")
        if ratio >= MEGA_WIN_X:
            want.append("mega_win")
        if ratio >= EPIC_WIN_X:
            want.append("epic_win")
        if free_awarded > 0:
            want.append("free_spins")
        if pick_win:
            want.append("crystal_pick")
        if wheel:
            want.append("tea_wheel")
        if any(g.get("kind") == "hold_spin" for g in games):
            want.append("hold_spin")
            if any(g.get("filled") or g.get("grand") for g in games):
                want.append("hold_grand")
        if rnd.get("progressive_hit") or rnd.get("_progressive_hit"):
            want.append("progressive_hit")
        if rnd.get("collection_completed") or rnd.get("_collection_completed"):
            want.append("collection_set")
        if level >= 10:
            want.append("vip_gold")
        if level >= 35:
            want.append("vip_diamond")
        if streak >= 5:
            want.append("streak_5")
        if streak >= 10:
            want.append("streak_10")
        want.extend(_level_trophies(level))
        newly = _unlock_many(conn, player_id, want, now)

        rows = conn.execute(
            "SELECT slot, mission_id, progress, target, claimed FROM missions WHERE player_id = ? AND mission_date = ?",
            (player_id, day),
        ).fetchall()
        for m in rows:
            if int(m["claimed"]) == 1 or int(m["progress"]) >= int(m["target"]):
                # still allow progress cap
                pass
            spec = _MISSION_BY_ID.get(m["mission_id"])
            if not spec:
                continue
            inc = 0
            typ = spec["type"]
            if typ == "spins":
                inc = 1
            elif typ == "win_spins" and float(win_aud) > 0:
                inc = 1
            elif typ == "free_spins" and free_awarded > 0:
                inc = 1
            elif typ == "win_mult" and ratio >= float(spec.get("mult") or 0):
                inc = 1
            elif typ == "minigame" and (pick_win or wheel):
                inc = 1
            if inc:
                new_p = min(int(m["target"]), int(m["progress"]) + inc)
                conn.execute(
                    "UPDATE missions SET progress = ? WHERE player_id = ? AND mission_date = ? AND slot = ?",
                    (new_p, player_id, day, int(m["slot"])),
                )

    out = attach(player_id, {}, newly)
    if level_up:
        out["level_up"] = level_up
    return out


def claim_mission(player_id: str, mission_id: str, date_str: str | None = None) -> dict[str, Any]:
    import ledger
    from game import COIN_ASSET

    ledger.ensure_player(player_id)
    day = date_str or perth_date()
    ensure_daily_missions(player_id, day)
    spec = _MISSION_BY_ID.get(mission_id)
    if not spec:
        raise ValueError("Unknown mission")
    newly: list[dict[str, Any]] = []
    awarded = 0
    with ledger.transaction() as conn:
        row = conn.execute(
            """
            SELECT slot, mission_id, progress, target, claimed
            FROM missions
            WHERE player_id = ? AND mission_date = ? AND mission_id = ?
            """,
            (player_id, day, mission_id),
        ).fetchone()
        if not row:
            raise MissionUnavailable("That mission is not active today")
        if int(row["claimed"]) == 1:
            raise MissionUnavailable("Mission already claimed")
        if int(row["progress"]) < int(row["target"]):
            raise MissionUnavailable("Mission is not complete yet")
        awarded = int(spec.get("reward_coins") or 0)
        if awarded > 0:
            ledger._credit(conn, player_id, COIN_ASSET, awarded)
            conn.execute(
                """
                INSERT INTO ledger_entries
                    (player_id, kind, asset, amount, note, created_at)
                VALUES (?, 'mission_reward', ?, ?, ?, ?)
                """,
                (player_id, COIN_ASSET, awarded, f"Mission {mission_id} — virtual coins, no cash value", _now_iso()),
            )
        conn.execute(
            "UPDATE missions SET claimed = 1 WHERE player_id = ? AND mission_date = ? AND mission_id = ?",
            (player_id, day, mission_id),
        )
        trophy = spec.get("reward_trophy")
        if trophy:
            newly = _unlock_many(conn, player_id, [trophy], _now_iso())
    snap = attach(player_id, ledger.snapshot(player_id), newly)
    snap["awarded"] = awarded
    snap["bonus"] = "mission"
    return snap


def _board_sql(period_type: str) -> tuple[str, str]:
    if period_type == "weekly":
        return "perth_week", "SUM(win_aud)" if False else "perth_week"
    return "perth_date", "perth_date"


def _period_column(period_type: str) -> str:
    if period_type == "weekly":
        return "perth_week"
    if period_type == "weekend":
        return "perth_weekend"
    return "perth_date"


def current_period_key(period_type: str) -> str:
    if period_type == "weekly":
        return perth_week()
    if period_type == "weekend":
        return perth_weekend()
    return perth_date()


def previous_period_key(period_type: str) -> str:
    if period_type == "weekly":
        dt = perth_now() - timedelta(days=7)
        return perth_week(dt)
    if period_type == "weekend":
        # The Friday of the previous weekend window.
        dt = weekend_friday() - timedelta(days=7)
        return perth_weekend(dt)
    dt = perth_now() - timedelta(days=1)
    return perth_date(dt)


def leaderboard(period_type: str, board: str, period_key: str | None = None, viewer_id: str | None = None) -> dict[str, Any]:
    if period_type not in ("daily", "weekly", "weekend"):
        raise ValueError("Period must be daily, weekly or weekend")
    if board not in ("biggest", "total"):
        raise ValueError("Board must be biggest or total")
    key = period_key or current_period_key(period_type)
    col = _period_column(period_type)
    agg = "MAX(win_aud)" if board == "biggest" else "SUM(win_aud)"
    conn = _conn()
    rows = conn.execute(
        f"""
        SELECT player_id, {agg} AS score
        FROM spin_records
        WHERE {col} = ?
        GROUP BY player_id
        HAVING score > 0
        ORDER BY score DESC, player_id ASC
        LIMIT 50
        """,
        (key,),
    ).fetchall()
    entries = []
    my_rank = None
    my_score = 0
    for i, row in enumerate(rows, start=1):
        pid = row["player_id"]
        score = float(row["score"] or 0)
        nick_row = conn.execute("SELECT nickname FROM players WHERE id = ?", (pid,)).fetchone()
        nick = (nick_row["nickname"] if nick_row and nick_row["nickname"] else default_nickname(pid))
        item = {
            "place": i,
            "nickname": nick,
            "score": to_coins(score),
            "me": bool(viewer_id and viewer_id == pid),
        }
        if viewer_id and viewer_id == pid:
            my_rank = i
            my_score = to_coins(score)
        if i <= LEADERBOARD_LIMIT:
            entries.append(item)
    if viewer_id and my_rank is None:
        mine = conn.execute(
            f"SELECT {agg} AS score FROM spin_records WHERE {col} = ? AND player_id = ?",
            (key, viewer_id),
        ).fetchone()
        my_score = to_coins(float(mine["score"] or 0)) if mine else 0
    return {
        "period": period_type,
        "board": board,
        "key": key,
        "entries": entries,
        "me": {"place": my_rank, "score": my_score},
        "rewards": [{"place": p, "coins": c} for p, c in (WEEKEND_COINS if period_type == "weekend" else LEADERBOARD_COINS).items()],
        "legal": PRIZE_LEGAL,
        "active": weekend_active() if period_type == "weekend" else True,
    }


def settle_leaderboard(period_type: str, period_key: str, board: str | None = None) -> list[dict[str, Any]]:
    """Award top-3 coin grants + exclusive badges for a closed period. Idempotent."""
    import ledger
    from game import COIN_ASSET

    if period_type not in ("daily", "weekly", "weekend"):
        raise ValueError("Period must be daily, weekly or weekend")
    boards = [board] if board else ["biggest", "total"]
    paid: list[dict[str, Any]] = []
    badge = {
        ("daily", 1): "lb_daily_gold",
        ("daily", 2): "lb_daily_silver",
        ("daily", 3): "lb_daily_bronze",
        ("weekly", 1): "lb_weekly_gold",
        ("weekly", 2): "lb_weekly_silver",
        ("weekly", 3): "lb_weekly_bronze",
        ("weekend", 1): "lb_weekend_gold",
        ("weekend", 2): "lb_weekend_silver",
        ("weekend", 3): "lb_weekend_bronze",
    }
    now = _now_iso()
    for b in boards:
        data = leaderboard(period_type, b, period_key)
        # Need player ids — leaderboard public view hides them. Query again.
        col = _period_column(period_type)
        agg = "MAX(win_aud)" if b == "biggest" else "SUM(win_aud)"
        with ledger.transaction() as conn:
            rows = conn.execute(
                f"""
                SELECT player_id, {agg} AS score
                FROM spin_records
                WHERE {col} = ?
                GROUP BY player_id
                HAVING score > 0
                ORDER BY score DESC, player_id ASC
                LIMIT 3
                """,
                (period_key,),
            ).fetchall()
            for place, row in enumerate(rows, start=1):
                table = WEEKEND_COINS if period_type == "weekend" else LEADERBOARD_COINS
                coins = int(table.get(place) or 0)
                existing = conn.execute(
                    """
                    SELECT player_id FROM leaderboard_payouts
                    WHERE period_type = ? AND period_key = ? AND board = ? AND place = ?
                    """,
                    (period_type, period_key, b, place),
                ).fetchone()
                if existing:
                    continue
                pid = row["player_id"]
                if coins > 0:
                    ledger._credit(conn, pid, COIN_ASSET, coins)
                    conn.execute(
                        """
                        INSERT INTO ledger_entries
                            (player_id, kind, asset, amount, note, created_at)
                        VALUES (?, 'leaderboard_reward', ?, ?, ?, ?)
                        """,
                        (
                            pid,
                            COIN_ASSET,
                            coins,
                            f"{period_type} {b} place {place} ({period_key}) — virtual coins, no cash value",
                            now,
                        ),
                    )
                conn.execute(
                    """
                    INSERT INTO leaderboard_payouts
                        (period_type, period_key, board, place, player_id, coins, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (period_type, period_key, b, place, pid, coins, now),
                )
                tid = badge.get((period_type, place))
                if tid:
                    _unlock_many(conn, pid, [tid], now)
                paid.append({"period": period_type, "key": period_key, "board": b, "place": place, "player_id": pid, "coins": coins})
    return paid


def settle_due_periods() -> list[dict[str, Any]]:
    """Settle yesterday and last week if not already paid."""
    paid = []
    paid.extend(settle_leaderboard("daily", previous_period_key("daily")))
    paid.extend(settle_leaderboard("weekly", previous_period_key("weekly")))
    last_weekend = previous_period_key("weekend")
    if last_weekend != perth_weekend() or not weekend_active():
        # Always settle the previous window; if still in the current weekend, only settle the prior one.
        paid.extend(settle_leaderboard("weekend", last_weekend))
    return paid
