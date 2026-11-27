"""Clubs and team play — coins-only social clubs.

Members create or join a club, contribute to a weekly goal through the
v10 events.on_play hook, and claim house-issued coin rewards. Coins are
never transferred between players. Rewards are promotional virtual coins
with no cash value; they are not taken from the game house pool (so club
rewards cannot change slot RTP).

Schema is additive and applied only when prefs.schema_migrate_allowed()
is true. See docs/migrations/2026-11-28-clubs.md. Do not run this against
production Postgres.
"""

from __future__ import annotations

import re
import secrets
from datetime import timedelta
from typing import Any

import prefs

CLUB_CAP = 30
NAME_MIN = 3
NAME_MAX = 24
CHAT_LIMIT = 40
CHAT_COOLDOWN_S = 3

# Weekly goal: club points = bet_coins + win_coins from settled plays.
# Tiers pay a single lump sum (highest reached) once per member per week.
TIERS = (
    {"tier": 1, "points": 100_000, "coins": 1_000, "label": "Bronze chest"},
    {"tier": 2, "points": 400_000, "coins": 4_000, "label": "Silver chest"},
    {"tier": 3, "points": 1_200_000, "coins": 12_000, "label": "Gold chest"},
)

EMBLEMS = (
    {"id": "ruby", "src": "/assets/symbols/ruby.webp", "label": "Ruby"},
    {"id": "emerald", "src": "/assets/symbols/emerald.webp", "label": "Emerald"},
    {"id": "sapphire", "src": "/assets/symbols/sapphire.webp", "label": "Sapphire"},
    {"id": "amethyst", "src": "/assets/symbols/amethyst.webp", "label": "Amethyst"},
    {"id": "citrine", "src": "/assets/symbols/citrine.webp", "label": "Citrine"},
    {"id": "quartz", "src": "/assets/symbols/quartz.webp", "label": "Quartz"},
    {"id": "shard", "src": "/assets/symbols/shard.webp", "label": "Shard"},
    {"id": "crown", "src": "/assets/ui/logo.webp", "label": "Crown"},
)
_EMBLEM_IDS = {e["id"] for e in EMBLEMS}

# Preset phrases only — never store free text from players.
QUICK_CHAT = (
    {"id": "gg", "text": "Good game!"},
    {"id": "spin", "text": "Let's spin!"},
    {"id": "goal", "text": "So close to the goal!"},
    {"id": "nice", "text": "Nice win!"},
    {"id": "welcome", "text": "Welcome to the club!"},
    {"id": "thanks", "text": "Thanks, team!"},
    {"id": "luck", "text": "Good luck!"},
    {"id": "fun", "text": "Play for fun — coins have no cash value."},
)
_PHRASE_BY_ID = {p["id"]: p["text"] for p in QUICK_CHAT}


class ClubError(ValueError):
    """User-facing club error."""


def week_id(when=None) -> str:
    from prizes import perth_week
    return perth_week(when)


def week_ends_at(when=None) -> str:
    from prizes import perth_now, PERTH
    dt = when or perth_now()
    # Next Monday 00:00 Perth.
    days = (7 - dt.weekday()) % 7
    if days == 0:
        days = 7
    end = (dt + timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    return end.isoformat()


def claim_key(player_id: str, week: str) -> str:
    """Unique ledger/claim key: one claim per player per week."""
    return f"club-week:{week}:player:{player_id}"


def ensure_schema(conn: Any) -> None:
    if not prefs.schema_migrate_allowed():
        return
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS clubs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            emblem TEXT NOT NULL,
            visibility TEXT NOT NULL,
            invite_code TEXT NOT NULL,
            leader_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            disbanded_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS clubs_invite_code ON clubs(invite_code);
        CREATE TABLE IF NOT EXISTS club_members (
            club_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            joined_at TEXT NOT NULL,
            PRIMARY KEY (club_id, player_id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS club_members_one_club ON club_members(player_id);
        CREATE TABLE IF NOT EXISTS club_week_progress (
            club_id TEXT NOT NULL,
            week_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            spins INTEGER NOT NULL DEFAULT 0,
            bet_coins INTEGER NOT NULL DEFAULT 0,
            win_coins INTEGER NOT NULL DEFAULT 0,
            points INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (club_id, week_id, player_id)
        );
        CREATE TABLE IF NOT EXISTS club_reward_claims (
            claim_key TEXT PRIMARY KEY,
            club_id TEXT NOT NULL,
            week_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            tier INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS club_claims_player_week
            ON club_reward_claims(player_id, week_id);
        CREATE TABLE IF NOT EXISTS club_chat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            club_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            phrase_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return "c_" + secrets.token_hex(8)


def _invite_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(6))


def sanitize_club_name(raw: str) -> str:
    import html
    text = str(raw or "")
    text = html.unescape(text)
    text = re.sub(r"<[^>]*>", " ", text)
    text = "".join(ch for ch in text if ch.isalnum() or ch in " -_'")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > NAME_MAX:
        text = text[:NAME_MAX].rstrip()
    if len(text) < NAME_MIN:
        raise ClubError(f"Club name must be {NAME_MIN}–{NAME_MAX} letters, numbers or spaces")
    compact = re.sub(r"[^a-z0-9]", "", text.lower())
    from prizes import PROFANITY
    tokens = [tok for tok in re.split(r"[^a-z0-9]+", text.lower()) if tok]
    stems = {w for w in PROFANITY if len(w) >= 4}
    for word in PROFANITY:
        if word == compact or word in tokens:
            raise ClubError("Please choose another club name")
    for stem in stems:
        if stem in compact:
            raise ClubError("Please choose another club name")
    return text


def catalogue() -> dict[str, Any]:
    return {
        "cap": CLUB_CAP,
        "emblems": [dict(e) for e in EMBLEMS],
        "tiers": [dict(t) for t in TIERS],
        "phrases": [dict(p) for p in QUICK_CHAT],
        "week_id": week_id(),
        "week_ends_at": week_ends_at(),
        "legal": "Club rewards are virtual coins issued by the house for entertainment only. Coins have no cash value, cannot be redeemed, and cannot be transferred between players.",
    }


def _lock_club(conn: Any, club_id: str) -> Any:
    return conn.execute(
        "SELECT id, name, emblem, visibility, invite_code, leader_id, disbanded_at FROM clubs WHERE id = ? FOR UPDATE",
        (club_id,),
    ).fetchone()


def _member_count(conn: Any, club_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM club_members WHERE club_id = ?",
        (club_id,),
    ).fetchone()
    return int(row["n"] if row else 0)


def _membership(conn: Any, player_id: str) -> Any:
    return conn.execute(
        """
        SELECT m.club_id, m.role, m.joined_at, c.name, c.emblem, c.visibility,
               c.invite_code, c.leader_id, c.disbanded_at
        FROM club_members m
        JOIN clubs c ON c.id = m.club_id
        WHERE m.player_id = ?
        """,
        (player_id,),
    ).fetchone()


def my_club_id(player_id: str) -> str | None:
    import ledger
    try:
        row = ledger.get_conn().execute(
            "SELECT club_id FROM club_members WHERE player_id = ?",
            (player_id,),
        ).fetchone()
    except Exception:
        return None
    return row["club_id"] if row else None


def _club_points(conn: Any, club_id: str, week: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(points), 0) AS pts FROM club_week_progress WHERE club_id = ? AND week_id = ?",
        (club_id, week),
    ).fetchone()
    return int(row["pts"] if row else 0)


def _tier_for(points: int) -> dict[str, Any] | None:
    reached = None
    for t in TIERS:
        if points >= int(t["points"]):
            reached = dict(t)
    return reached


def _progress_payload(conn: Any, club_id: str, week: str) -> dict[str, Any]:
    pts = _club_points(conn, club_id, week)
    reached = _tier_for(pts)
    next_t = None
    for t in TIERS:
        if pts < int(t["points"]):
            next_t = dict(t)
            break
    return {
        "week_id": week,
        "week_ends_at": week_ends_at(),
        "points": pts,
        "tier": int(reached["tier"]) if reached else 0,
        "tier_label": reached["label"] if reached else None,
        "reward_coins": int(reached["coins"]) if reached else 0,
        "next_tier": next_t,
        "tiers": [dict(t) for t in TIERS],
    }


def create_club(player_id: str, name: str, emblem: str, visibility: str) -> dict[str, Any]:
    import ledger
    ledger.ensure_player(player_id)
    name = sanitize_club_name(name)
    if emblem not in _EMBLEM_IDS:
        raise ClubError("Choose a club emblem from the preset set")
    vis = str(visibility or "open").strip().lower()
    if vis not in ("open", "invite"):
        raise ClubError("Club must be open or invite-only")
    if not prefs.schema_migrate_allowed():
        raise ClubError("Clubs are not available on this database yet")
    cid = _new_id()
    now = _now()
    with ledger.transaction() as conn:
        ensure_schema(conn)
        ledger.lock_player(conn, player_id)
        existing = _membership(conn, player_id)
        if existing:
            raise ClubError("Leave your current club before creating a new one")
        taken = conn.execute(
            "SELECT id FROM clubs WHERE lower(name) = lower(?) AND disbanded_at IS NULL",
            (name,),
        ).fetchone()
        if taken:
            raise ClubError("That club name is already taken")
        code = _invite_code()
        # Extremely unlikely collision; retry a few times.
        for _ in range(8):
            clash = conn.execute("SELECT id FROM clubs WHERE invite_code = ?", (code,)).fetchone()
            if not clash:
                break
            code = _invite_code()
        conn.execute(
            """
            INSERT INTO clubs (id, name, emblem, visibility, invite_code, leader_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (cid, name, emblem, vis, code, player_id, now),
        )
        conn.execute(
            """
            INSERT INTO club_members (club_id, player_id, role, joined_at)
            VALUES (?, ?, 'leader', ?)
            """,
            (cid, player_id, now),
        )
    return club_state(player_id)


def join_club(player_id: str, club_id: str | None = None, invite_code: str | None = None) -> dict[str, Any]:
    import ledger
    ledger.ensure_player(player_id)
    if not prefs.schema_migrate_allowed():
        raise ClubError("Clubs are not available on this database yet")
    code = re.sub(r"[^A-Za-z0-9]", "", str(invite_code or "")).upper()
    cid = str(club_id or "").strip()
    now = _now()
    with ledger.transaction() as conn:
        ensure_schema(conn)
        ledger.lock_player(conn, player_id)
        if _membership(conn, player_id):
            raise ClubError("You are already in a club")
        row = None
        if code:
            row = conn.execute(
                "SELECT id FROM clubs WHERE invite_code = ? AND disbanded_at IS NULL",
                (code,),
            ).fetchone()
            if not row:
                raise ClubError("That invite code was not found")
            cid = row["id"]
        if not cid:
            raise ClubError("Choose a club or enter an invite code")
        club = _lock_club(conn, cid)
        if not club or club["disbanded_at"]:
            raise ClubError("That club was not found")
        if club["visibility"] == "invite" and (not code or code != club["invite_code"]):
            raise ClubError("This club is invite-only. Ask a member for the invite code.")
        n = _member_count(conn, cid)
        if n >= CLUB_CAP:
            raise ClubError(f"This club is full ({CLUB_CAP} members)")
        try:
            conn.execute(
                """
                INSERT INTO club_members (club_id, player_id, role, joined_at)
                VALUES (?, ?, 'member', ?)
                """,
                (cid, player_id, now),
            )
        except Exception as exc:
            # Unique player index: already in a club (race).
            raise ClubError("You are already in a club") from exc
        # Re-check cap after insert in case of a race; roll back if over.
        if _member_count(conn, cid) > CLUB_CAP:
            raise ClubError(f"This club is full ({CLUB_CAP} members)")
    return club_state(player_id)


def leave_club(player_id: str) -> dict[str, Any]:
    import ledger
    ledger.ensure_player(player_id)
    if not prefs.schema_migrate_allowed():
        raise ClubError("Clubs are not available on this database yet")
    now = _now()
    with ledger.transaction() as conn:
        ensure_schema(conn)
        ledger.lock_player(conn, player_id)
        mem = _membership(conn, player_id)
        if not mem:
            raise ClubError("You are not in a club")
        cid = mem["club_id"]
        _lock_club(conn, cid)
        conn.execute(
            "DELETE FROM club_members WHERE club_id = ? AND player_id = ?",
            (cid, player_id),
        )
        remaining = conn.execute(
            "SELECT player_id, role, joined_at FROM club_members WHERE club_id = ? ORDER BY joined_at ASC",
            (cid,),
        ).fetchall()
        if not remaining:
            conn.execute(
                "UPDATE clubs SET disbanded_at = ? WHERE id = ?",
                (now, cid),
            )
        elif mem["role"] == "leader" or mem["leader_id"] == player_id:
            nxt = remaining[0]["player_id"]
            conn.execute("UPDATE clubs SET leader_id = ? WHERE id = ?", (nxt, cid))
            conn.execute(
                "UPDATE club_members SET role = 'leader' WHERE club_id = ? AND player_id = ?",
                (cid, nxt),
            )
    return {"left": True, "club": None, **catalogue()}


def on_play(player_id: str, game: str, bet_coins: int, win_coins: int, meta: dict[str, Any] | None = None, **_kw: Any) -> None:
    """events.on_play subscriber. Never raises into the game path."""
    try:
        _record_play(player_id, int(bet_coins or 0), int(win_coins or 0))
    except Exception:
        return


def _record_play(player_id: str, bet_coins: int, win_coins: int) -> None:
    import ledger
    if not prefs.schema_migrate_allowed():
        return
    if bet_coins < 0:
        bet_coins = 0
    if win_coins < 0:
        win_coins = 0
    points = bet_coins + win_coins
    try:
        import live_events
        points *= max(1, min(3, int(live_events.club_points_multiplier())))
    except Exception:
        pass
    if points == 0 and bet_coins == 0:
        # Still count a settled spin with a zero bet? Unlikely. Skip empty.
        if win_coins == 0:
            return
    week = week_id()
    with ledger.transaction() as conn:
        ensure_schema(conn)
        mem = _membership(conn, player_id)
        if not mem or mem["disbanded_at"]:
            return
        cid = mem["club_id"]
        conn.execute(
            """
            INSERT INTO club_week_progress
                (club_id, week_id, player_id, spins, bet_coins, win_coins, points)
            VALUES (?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT (club_id, week_id, player_id) DO UPDATE SET
                spins = club_week_progress.spins + 1,
                bet_coins = club_week_progress.bet_coins + excluded.bet_coins,
                win_coins = club_week_progress.win_coins + excluded.win_coins,
                points = club_week_progress.points + excluded.points
            """,
            (cid, week, player_id, bet_coins, win_coins, points),
        )


def _claimed(conn: Any, player_id: str, week: str) -> Any:
    return conn.execute(
        "SELECT claim_key, club_id, amount, tier FROM club_reward_claims WHERE player_id = ? AND week_id = ?",
        (player_id, week),
    ).fetchone()


def claim_reward(player_id: str, week: str | None = None) -> dict[str, Any]:
    """Pay the highest unlocked weekly tier once. Idempotent per player per week."""
    import ledger
    from game import COIN_ASSET

    ledger.ensure_player(player_id)
    if not prefs.schema_migrate_allowed():
        raise ClubError("Clubs are not available on this database yet")
    week = week or week_id()
    key = claim_key(player_id, week)
    awarded = 0
    already = False
    with ledger.transaction() as conn:
        ensure_schema(conn)
        ledger.lock_player(conn, player_id)
        mem = _membership(conn, player_id)
        if not mem or mem["disbanded_at"]:
            raise ClubError("Join a club to claim a weekly reward")
        cid = mem["club_id"]
        _lock_club(conn, cid)
        existing = _claimed(conn, player_id, week)
        if existing:
            already = True
        else:
            contrib = conn.execute(
                """
                SELECT spins FROM club_week_progress
                WHERE club_id = ? AND week_id = ? AND player_id = ?
                """,
                (cid, week, player_id),
            ).fetchone()
            if not contrib or int(contrib["spins"] or 0) < 1:
                raise ClubError("Play at least one game this week while in this club to claim")
            prog = _progress_payload(conn, cid, week)
            if int(prog["tier"]) < 1:
                raise ClubError("The club has not reached a reward tier yet")
            awarded = int(prog["reward_coins"])
            if awarded <= 0:
                raise ClubError("The club has not reached a reward tier yet")
            inserted = conn.execute(
                """
                INSERT INTO club_reward_claims
                    (claim_key, club_id, week_id, player_id, tier, amount, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (claim_key) DO NOTHING
                """,
                (key, cid, week, player_id, int(prog["tier"]), awarded, _now()),
            )
            if int(getattr(inserted, "rowcount", 0) or 0) == 0:
                already = True
                awarded = 0
            else:
                ledger._credit(conn, player_id, COIN_ASSET, awarded)
                conn.execute(
                    """
                    INSERT INTO ledger_entries
                        (player_id, kind, asset, amount, stripe_session_id, note, created_at)
                    VALUES (?, 'club_reward', ?, ?, ?, ?, ?)
                    """,
                    (
                        player_id,
                        COIN_ASSET,
                        awarded,
                        key,
                        f"Club weekly goal {week} tier {prog['tier']} — virtual coins, no cash value",
                        _now(),
                    ),
                )
    snap = ledger.snapshot(player_id)
    state = club_state(player_id)
    state["snapshot"] = snap
    state["awarded"] = 0 if already else awarded
    state["already_claimed"] = already
    state["bonus"] = "club"
    if already:
        state["error"] = "Already claimed this week's club reward"
    return state


def post_chat(player_id: str, phrase_id: str) -> dict[str, Any]:
    import ledger
    if phrase_id not in _PHRASE_BY_ID:
        raise ClubError("Choose a preset phrase")
    if not prefs.schema_migrate_allowed():
        raise ClubError("Clubs are not available on this database yet")
    ledger.ensure_player(player_id)
    now = _now()
    with ledger.transaction() as conn:
        ensure_schema(conn)
        mem = _membership(conn, player_id)
        if not mem or mem["disbanded_at"]:
            raise ClubError("Join a club to send a message")
        last = conn.execute(
            """
            SELECT created_at FROM club_chat
            WHERE club_id = ? AND player_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (mem["club_id"], player_id),
        ).fetchone()
        if last and last["created_at"]:
            from datetime import datetime, timezone
            try:
                prev = datetime.fromisoformat(str(last["created_at"]))
                if prev.tzinfo is None:
                    prev = prev.replace(tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - prev).total_seconds() < CHAT_COOLDOWN_S:
                    raise ClubError("Please wait a moment before sending another phrase")
            except ClubError:
                raise
            except Exception:
                pass
        conn.execute(
            """
            INSERT INTO club_chat (club_id, player_id, phrase_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (mem["club_id"], player_id, phrase_id, now),
        )
    return club_state(player_id)


def _chat_rows(conn: Any, club_id: str) -> list[dict[str, Any]]:
    from prizes import default_nickname
    rows = conn.execute(
        """
        SELECT c.player_id, c.phrase_id, c.created_at
        FROM club_chat c
        WHERE c.club_id = ?
        ORDER BY c.id DESC
        LIMIT ?
        """,
        (club_id, CHAT_LIMIT),
    ).fetchall()
    out = []
    for r in reversed(list(rows)):
        phrase = _PHRASE_BY_ID.get(r["phrase_id"])
        if not phrase:
            continue
        nick_row = conn.execute("SELECT nickname FROM players WHERE id = ?", (r["player_id"],)).fetchone()
        nick = (nick_row["nickname"] if nick_row and nick_row["nickname"] else default_nickname(r["player_id"]))
        out.append({
            "player_id": r["player_id"],
            "nickname": nick,
            "phrase_id": r["phrase_id"],
            "text": phrase,
            "created_at": r["created_at"],
        })
    return out


def _contributions(conn: Any, club_id: str, week: str) -> list[dict[str, Any]]:
    from prizes import default_nickname
    members = conn.execute(
        "SELECT player_id, role, joined_at FROM club_members WHERE club_id = ? ORDER BY joined_at",
        (club_id,),
    ).fetchall()
    prog = {
        r["player_id"]: r
        for r in conn.execute(
            """
            SELECT player_id, spins, bet_coins, win_coins, points
            FROM club_week_progress WHERE club_id = ? AND week_id = ?
            """,
            (club_id, week),
        ).fetchall()
    }
    out = []
    for m in members:
        pid = m["player_id"]
        nick_row = conn.execute("SELECT nickname FROM players WHERE id = ?", (pid,)).fetchone()
        nick = (nick_row["nickname"] if nick_row and nick_row["nickname"] else default_nickname(pid))
        p = prog.get(pid)
        out.append({
            "player_id": pid,
            "nickname": nick,
            "role": m["role"],
            "joined_at": m["joined_at"],
            "spins": int(p["spins"]) if p else 0,
            "bet_coins": int(p["bet_coins"]) if p else 0,
            "win_coins": int(p["win_coins"]) if p else 0,
            "points": int(p["points"]) if p else 0,
        })
    out.sort(key=lambda x: (-x["points"], x["nickname"].lower()))
    return out


def club_state(player_id: str) -> dict[str, Any]:
    import ledger
    out = {"club": None, "catalog": catalogue(), "available": prefs.schema_migrate_allowed()}
    if not out["available"]:
        return out
    try:
        ensure_schema(ledger.get_conn())
        conn = ledger.get_conn()
        mem = _membership(conn, player_id)
        if not mem or mem["disbanded_at"]:
            return out
        week = week_id()
        cid = mem["club_id"]
        claimed = _claimed(conn, player_id, week)
        members = _contributions(conn, cid, week)
        prog = _progress_payload(conn, cid, week)
        out["club"] = {
            "id": cid,
            "name": mem["name"],
            "emblem": mem["emblem"],
            "emblem_src": next((e["src"] for e in EMBLEMS if e["id"] == mem["emblem"]), EMBLEMS[0]["src"]),
            "visibility": mem["visibility"],
            "invite_code": mem["invite_code"],
            "role": mem["role"],
            "leader_id": mem["leader_id"],
            "member_count": len(members),
            "cap": CLUB_CAP,
            "progress": prog,
            "members": members,
            "chat": _chat_rows(conn, cid),
            "claimed": bool(claimed),
            "claimed_amount": int(claimed["amount"]) if claimed else 0,
            "can_claim": (not claimed and int(prog["tier"]) >= 1 and any(
                m["player_id"] == player_id and m["spins"] >= 1 for m in members
            )),
        }
        return out
    except Exception:
        out["available"] = False
        return out


def list_open_clubs(limit: int = 24) -> list[dict[str, Any]]:
    import ledger
    if not prefs.schema_migrate_allowed():
        return []
    try:
        ensure_schema(ledger.get_conn())
        week = week_id()
        rows = ledger.get_conn().execute(
            """
            SELECT c.id, c.name, c.emblem, c.visibility,
                   (SELECT COUNT(*) FROM club_members m WHERE m.club_id = c.id) AS member_count,
                   COALESCE((SELECT SUM(p.points) FROM club_week_progress p
                             WHERE p.club_id = c.id AND p.week_id = ?), 0) AS points
            FROM clubs c
            WHERE c.visibility = 'open' AND c.disbanded_at IS NULL
            ORDER BY points DESC, member_count DESC, c.created_at ASC
            LIMIT ?
            """,
            (week, int(limit)),
        ).fetchall()
        out = []
        for r in rows:
            out.append({
                "id": r["id"],
                "name": r["name"],
                "emblem": r["emblem"],
                "emblem_src": next((e["src"] for e in EMBLEMS if e["id"] == r["emblem"]), EMBLEMS[0]["src"]),
                "visibility": r["visibility"],
                "member_count": int(r["member_count"]),
                "cap": CLUB_CAP,
                "points": int(r["points"]),
                "full": int(r["member_count"]) >= CLUB_CAP,
            })
        return out
    except Exception:
        return []


def leaderboard(limit: int = 20) -> dict[str, Any]:
    import ledger
    week = week_id()
    out = {"week_id": week, "week_ends_at": week_ends_at(), "clubs": []}
    if not prefs.schema_migrate_allowed():
        return out
    try:
        ensure_schema(ledger.get_conn())
        rows = ledger.get_conn().execute(
            """
            SELECT c.id, c.name, c.emblem,
                   (SELECT COUNT(*) FROM club_members m WHERE m.club_id = c.id) AS member_count,
                   COALESCE((SELECT SUM(p.points) FROM club_week_progress p
                             WHERE p.club_id = c.id AND p.week_id = ?), 0) AS points
            FROM clubs c
            WHERE c.disbanded_at IS NULL
            ORDER BY points DESC, member_count DESC, c.name ASC
            LIMIT ?
            """,
            (week, int(limit)),
        ).fetchall()
        clubs = []
        for i, r in enumerate(rows, 1):
            clubs.append({
                "rank": i,
                "id": r["id"],
                "name": r["name"],
                "emblem": r["emblem"],
                "emblem_src": next((e["src"] for e in EMBLEMS if e["id"] == r["emblem"]), EMBLEMS[0]["src"]),
                "member_count": int(r["member_count"]),
                "points": int(r["points"]),
                "tier": int((_tier_for(int(r["points"])) or {}).get("tier") or 0),
            })
        out["clubs"] = clubs
        return out
    except Exception:
        return out

import events as _events
_events.register(on_play)
