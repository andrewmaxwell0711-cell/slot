"""Google sign-in, session cookies, guest merge, and account deletion.

ID tokens are verified with google-auth against GOOGLE_CLIENT_ID.
If that env var is unset, sign-in is disabled and guest play is unchanged.
Coins have no cash value. Account data is only Google name/email/avatar
plus game progress; delete-my-account removes the account and player rows.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

SESSION_COOKIE = "cc_session"
CSRF_COOKIE = "cc_csrf"
SESSION_DAYS = 30
# What we store — also shown in the privacy note on the profile page.
PRIVACY_NOTE = (
    "If you sign in, we store your Google name, email and avatar, plus your "
    "game progress (coins, XP and VIP tier, trophies, themes, missions, "
    "bonus timers and coin-pack purchases). Coins have no cash value and "
    "cannot be cashed out. You can delete your account at any time; this "
    "permanently removes your account and progress."
)


def google_client_id() -> str:
    return (os.environ.get("GOOGLE_CLIENT_ID") or "").strip()


def google_enabled() -> bool:
    return bool(google_client_id())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def ensure_schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,
            google_sub TEXT NOT NULL UNIQUE,
            email TEXT,
            name TEXT,
            given_name TEXT,
            family_name TEXT,
            picture TEXT,
            display_name TEXT,
            player_id TEXT NOT NULL UNIQUE,
            merge_used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            last_login_at TEXT
        );
        CREATE TABLE IF NOT EXISTS auth_sessions (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            csrf_token TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS guest_merges (
            account_id TEXT NOT NULL,
            guest_player_id TEXT NOT NULL,
            merged_at TEXT NOT NULL,
            PRIMARY KEY (account_id, guest_player_id),
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
        );
        """
    )


def format_display_name(
    given_name: str | None = None,
    family_name: str | None = None,
    full_name: str | None = None,
) -> str:
    """First name + last initial. Never uses email."""
    given = " ".join(str(given_name or "").split())
    family = " ".join(str(family_name or "").split())
    full = " ".join(str(full_name or "").split())
    if given and family:
        return f"{given} {family[0].upper()}."
    if given:
        return given
    if full:
        parts = full.split()
        if len(parts) >= 2:
            return f"{parts[0]} {parts[1][0].upper()}."
        return parts[0]
    return "Player"


def safe_picture_url(url: str | None) -> str | None:
    raw = (url or "").strip()
    if not raw:
        return None
    try:
        parsed = urlparse(raw)
    except Exception:
        return None
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    host = parsed.netloc.lower()
    if host == "googleusercontent.com" or host.endswith(".googleusercontent.com"):
        return raw
    return None


def verify_google_token(token: str) -> dict[str, Any]:
    """Verify a GIS ID token. Tests may monkeypatch this function."""
    client_id = google_client_id()
    if not client_id:
        raise ValueError("Google sign-in is not configured")
    raw = (token or "").strip()
    if not raw:
        raise ValueError("Missing Google credential")
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    info = id_token.verify_oauth2_token(raw, google_requests.Request(), audience=client_id)
    iss = str(info.get("iss") or "")
    if iss not in ("accounts.google.com", "https://accounts.google.com"):
        raise ValueError("Invalid Google token issuer")
    sub = str(info.get("sub") or "").strip()
    if not sub:
        raise ValueError("Invalid Google token")
    return {
        "sub": sub,
        "email": (info.get("email") or "") or None,
        "email_verified": bool(info.get("email_verified")),
        "name": (info.get("name") or "") or None,
        "given_name": (info.get("given_name") or "") or None,
        "family_name": (info.get("family_name") or "") or None,
        "picture": safe_picture_url(info.get("picture")),
    }


def _hash_session(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def account_by_id(conn, account_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    return _account_row(row) if row else None


def account_by_player(conn, player_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM accounts WHERE player_id = ?", (player_id,)).fetchone()
    return _account_row(row) if row else None


def _account_row(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "google_sub": row["google_sub"],
        "email": row["email"],
        "name": row["name"],
        "given_name": row["given_name"],
        "family_name": row["family_name"],
        "picture": safe_picture_url(row["picture"]),
        "display_name": row["display_name"] or format_display_name(
            row["given_name"], row["family_name"], row["name"]
        ),
        "player_id": row["player_id"],
        "merge_used": int(row["merge_used"] or 0),
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
    }


def display_name_for(conn, player_id: str, fallback: str) -> str:
    acc = account_by_player(conn, player_id)
    if acc and acc["display_name"]:
        return acc["display_name"]
    return fallback


def load_session(token: str | None) -> dict[str, Any] | None:
    raw = (token or "").strip()
    if not raw:
        return None
    import ledger

    conn = ledger.get_conn()
    row = conn.execute(
        "SELECT * FROM auth_sessions WHERE id = ?",
        (_hash_session(raw),),
    ).fetchone()
    if not row:
        return None
    expires = _parse_iso(row["expires_at"])
    if expires is None or expires <= _utc_now():
        conn.execute("DELETE FROM auth_sessions WHERE id = ?", (row["id"],))
        return None
    account = account_by_id(conn, row["account_id"])
    if not account:
        conn.execute("DELETE FROM auth_sessions WHERE id = ?", (row["id"],))
        return None
    return {
        "token": raw,
        "account": account,
        "account_id": account["id"],
        "player_id": account["player_id"],
        "csrf_token": row["csrf_token"],
        "expires_at": row["expires_at"],
    }


def create_session(account_id: str) -> dict[str, str]:
    import ledger

    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    now = _utc_now()
    expires = now + timedelta(days=SESSION_DAYS)
    with ledger.transaction() as conn:
        conn.execute(
            """
            INSERT INTO auth_sessions (id, account_id, csrf_token, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (_hash_session(token), account_id, csrf, now.isoformat(), expires.isoformat()),
        )
    return {"token": token, "csrf_token": csrf, "expires_at": expires.isoformat()}


def revoke_session(token: str | None) -> None:
    raw = (token or "").strip()
    if not raw:
        return
    import ledger

    ledger.get_conn().execute("DELETE FROM auth_sessions WHERE id = ?", (_hash_session(raw),))


def csrf_ok(expected: str | None, provided: str | None) -> bool:
    a = (expected or "").strip()
    b = (provided or "").strip()
    if not a or not b or len(a) != len(b):
        return False
    return hmac.compare_digest(a, b)


def upsert_account_from_google(profile: dict[str, Any], guest_player_id: str) -> dict[str, Any]:
    """Find or create the Google account.

    First sign-in adopts the current guest player row (no copy, no second
    starting grant). Returning users keep their existing player_id.
    """
    import ledger

    sub = profile["sub"]
    display = format_display_name(
        profile.get("given_name"), profile.get("family_name"), profile.get("name")
    )
    picture = safe_picture_url(profile.get("picture"))
    now = _utc_now_iso()
    ledger.ensure_player(guest_player_id)
    with ledger.transaction() as conn:
        existing = conn.execute(
            "SELECT * FROM accounts WHERE google_sub = ?", (sub,)
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE accounts
                SET email = ?, name = ?, given_name = ?, family_name = ?,
                    picture = ?, display_name = ?, last_login_at = ?
                WHERE id = ?
                """,
                (
                    profile.get("email"),
                    profile.get("name"),
                    profile.get("given_name"),
                    profile.get("family_name"),
                    picture,
                    display,
                    now,
                    existing["id"],
                ),
            )
            created = False
            account_id = existing["id"]
        else:
            # If this guest row is already tied to a different Google account,
            # mint a fresh player instead of stealing it.
            taken = conn.execute(
                "SELECT id FROM accounts WHERE player_id = ?", (guest_player_id,)
            ).fetchone()
            player_id = guest_player_id if not taken else str(uuid.uuid4())
            if player_id != guest_player_id:
                _ensure_player_in_txn(conn, player_id)
            account_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO accounts (
                    id, google_sub, email, name, given_name, family_name,
                    picture, display_name, player_id, merge_used,
                    created_at, last_login_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    account_id,
                    sub,
                    profile.get("email"),
                    profile.get("name"),
                    profile.get("given_name"),
                    profile.get("family_name"),
                    picture,
                    display,
                    player_id,
                    now,
                    now,
                ),
            )
            created = True
    conn = ledger.get_conn()
    account = account_by_id(conn, account_id)
    assert account is not None
    account["created"] = created
    return account


def guest_has_progress(player_id: str) -> bool:
    import ledger
    from game import STARTING_COINS, COIN_ASSET

    conn = ledger.get_conn()
    row = conn.execute(
        """
        SELECT spins, last_daily_date, last_hourly_at, xp, level
        FROM players WHERE id = ?
        """,
        (player_id,),
    ).fetchone()
    if not row:
        return False
    if int(row["spins"] or 0) > 0:
        return True
    if row["last_daily_date"] or row["last_hourly_at"]:
        return True
    if int(row["xp"] or 0) > 0 or int(row["level"] or 1) > 1:
        return True
    bal = conn.execute(
        "SELECT amount FROM balances WHERE player_id = ? AND asset = ?",
        (player_id, COIN_ASSET),
    ).fetchone()
    coins = int(bal["amount"] or 0) if bal else 0
    if coins != int(STARTING_COINS):
        return True
    if conn.execute(
        "SELECT 1 FROM trophies WHERE player_id = ? LIMIT 1", (player_id,)
    ).fetchone():
        return True
    if conn.execute(
        "SELECT 1 FROM processed_sessions WHERE player_id = ? LIMIT 1", (player_id,)
    ).fetchone():
        return True
    return False


def merge_preview(account: dict[str, Any], guest_player_id: str | None) -> dict[str, Any] | None:
    if not guest_player_id or guest_player_id == account["player_id"]:
        return None
    if int(account.get("merge_used") or 0):
        return None
    if not guest_has_progress(guest_player_id):
        return None
    import ledger
    from game import COIN_ASSET, to_coins

    conn = ledger.get_conn()
    if conn.execute(
        "SELECT 1 FROM guest_merges WHERE account_id = ? AND guest_player_id = ?",
        (account["id"], guest_player_id),
    ).fetchone():
        return None

    def _snap(pid: str) -> dict[str, Any]:
        prow = conn.execute(
            "SELECT spins, xp, level, total_won_aud, total_bet_aud FROM players WHERE id = ?",
            (pid,),
        ).fetchone()
        bal = conn.execute(
            "SELECT amount FROM balances WHERE player_id = ? AND asset = ?",
            (pid, COIN_ASSET),
        ).fetchone()
        trophies = conn.execute(
            "SELECT COUNT(*) AS n FROM trophies WHERE player_id = ?", (pid,)
        ).fetchone()
        return {
            "coins": int(bal["amount"] or 0) if bal else 0,
            "spins": int(prow["spins"] or 0) if prow else 0,
            "xp": int(prow["xp"] or 0) if prow else 0,
            "level": int(prow["level"] or 1) if prow else 1,
            "total_won": to_coins(float(prow["total_won_aud"] or 0)) if prow else 0,
            "trophies": int(trophies["n"] or 0) if trophies else 0,
        }

    return {
        "guest": _snap(guest_player_id),
        "account": _snap(account["player_id"]),
        "once": True,
    }


def merge_guest(account_id: str, guest_player_id: str) -> dict[str, Any]:
    """Copy guest progress into the account once. No double-claiming bonuses
    or Stripe sessions. Raises ValueError if merge is not allowed.
    """
    import json as _json
    import ledger
    import prizes
    from game import COIN_ASSET
    from prizes import xp_needed

    guest_player_id = str(guest_player_id or "").strip()
    if not guest_player_id:
        raise ValueError("No guest progress to merge")

    def _total_xp(level: int, xp: int) -> int:
        total = int(xp or 0)
        for lvl in range(1, max(1, int(level or 1))):
            total += int(xp_needed(lvl))
        return total

    with ledger.transaction() as conn:
        acc_row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if not acc_row:
            raise ValueError("Account not found")
        account = _account_row(acc_row)
        dest = account["player_id"]
        if guest_player_id == dest:
            raise ValueError("Nothing to merge")
        if int(account["merge_used"] or 0):
            raise ValueError("This account has already merged guest progress once")
        already = conn.execute(
            "SELECT 1 FROM guest_merges WHERE account_id = ? AND guest_player_id = ?",
            (account_id, guest_player_id),
        ).fetchone()
        if already:
            raise ValueError("That guest progress was already merged")
        guest = conn.execute("SELECT * FROM players WHERE id = ?", (guest_player_id,)).fetchone()
        if not guest:
            raise ValueError("No guest progress to merge")
        dest_row = conn.execute("SELECT * FROM players WHERE id = ?", (dest,)).fetchone()
        if not dest_row:
            _ensure_player_in_txn(conn, dest)
            dest_row = conn.execute("SELECT * FROM players WHERE id = ?", (dest,)).fetchone()

        # Coins: add remaining guest balance (includes unspent starting coins
        # only when the guest actually played or bought — callers should
        # already have checked guest_has_progress).
        gbal = conn.execute(
            "SELECT amount FROM balances WHERE player_id = ? AND asset = ?",
            (guest_player_id, COIN_ASSET),
        ).fetchone()
        guest_coins = int(gbal["amount"] or 0) if gbal else 0
        if guest_coins:
            conn.execute(
                "UPDATE balances SET amount = amount + ? WHERE player_id = ? AND asset = ?",
                (guest_coins, dest, COIN_ASSET),
            )
            conn.execute(
                "UPDATE balances SET amount = 0 WHERE player_id = ? AND asset = ?",
                (guest_player_id, COIN_ASSET),
            )
            conn.execute(
                """
                INSERT INTO ledger_entries
                    (player_id, kind, asset, amount, note, created_at)
                VALUES (?, 'guest_merge', ?, ?, 'Merged guest coins — no cash value', ?)
                """,
                (dest, COIN_ASSET, guest_coins, _utc_now_iso()),
            )

        # Stats and XP.
        dest_xp = _total_xp(int(dest_row["level"] or 1), int(dest_row["xp"] or 0))
        guest_xp = _total_xp(int(guest["level"] or 1), int(guest["xp"] or 0))
        combined = dest_xp + guest_xp
        level, xp = 1, combined
        while xp >= xp_needed(level):
            xp -= xp_needed(level)
            level += 1
        dest_streak = int(dest_row["best_streak"] or 0)
        guest_streak = int(guest["best_streak"] or 0) if "best_streak" in guest.keys() else 0
        dest_cur = int(dest_row["current_streak"] or 0)
        guest_cur = int(guest["current_streak"] or 0) if "current_streak" in guest.keys() else 0
        # Daily / hourly: if either claimed, keep the later/more-recent claim
        # so the bonus cannot be claimed twice.
        last_daily = _later_date(dest_row["last_daily_date"], guest["last_daily_date"])
        last_hourly = _later_ts(dest_row["last_hourly_at"], guest["last_hourly_at"])
        theme = dest_row["theme"] or guest["theme"] or "crystal"
        dest_meter = _load_meter(dest_row["collect_meter"] if "collect_meter" in dest_row.keys() else "{}")
        guest_meter = _load_meter(guest["collect_meter"] if "collect_meter" in guest.keys() else "{}")
        meter = {k: max(int(dest_meter.get(k) or 0), int(guest_meter.get(k) or 0))
                 for k in set(dest_meter) | set(guest_meter)}
        conn.execute(
            """
            UPDATE players SET
                spins = spins + ?,
                total_won_aud = total_won_aud + ?,
                total_bet_aud = total_bet_aud + ?,
                last_win_aud = CASE WHEN last_win_aud >= ? THEN last_win_aud ELSE ? END,
                xp = ?,
                level = ?,
                best_streak = ?,
                current_streak = ?,
                last_daily_date = ?,
                last_hourly_at = ?,
                theme = ?,
                collect_meter = ?
            WHERE id = ?
            """,
            (
                int(guest["spins"] or 0),
                float(guest["total_won_aud"] or 0),
                float(guest["total_bet_aud"] or 0),
                float(guest["last_win_aud"] or 0),
                float(guest["last_win_aud"] or 0),
                int(xp),
                int(level),
                max(dest_streak, guest_streak),
                max(dest_cur, guest_cur),
                last_daily,
                last_hourly,
                theme,
                _json.dumps(meter),
                dest,
            ),
        )

        # Trophies: union, no duplicates (primary key).
        conn.execute(
            """
            INSERT INTO trophies (player_id, trophy_id, unlocked_at)
            SELECT ?, trophy_id, unlocked_at FROM trophies WHERE player_id = ?
            ON CONFLICT (player_id, trophy_id) DO NOTHING
            """,
            (dest, guest_player_id),
        )
        conn.execute("DELETE FROM trophies WHERE player_id = ?", (guest_player_id,))

        # Today's missions: take the better progress / claimed flag, then drop guest rows.
        _merge_missions(conn, dest, guest_player_id)

        conn.execute(
            "UPDATE spin_records SET player_id = ? WHERE player_id = ?",
            (dest, guest_player_id),
        )
        conn.execute(
            "UPDATE processed_sessions SET player_id = ? WHERE player_id = ?",
            (dest, guest_player_id),
        )
        conn.execute(
            "UPDATE ledger_entries SET player_id = ? WHERE player_id = ?",
            (dest, guest_player_id),
        )
        dest_side = conn.execute(
            "SELECT 1 FROM side_sessions WHERE player_id = ?", (dest,)
        ).fetchone()
        if dest_side:
            conn.execute("DELETE FROM side_sessions WHERE player_id = ?", (guest_player_id,))
        else:
            conn.execute(
                "UPDATE side_sessions SET player_id = ? WHERE player_id = ?",
                (dest, guest_player_id),
            )

        now = _utc_now_iso()
        conn.execute(
            "INSERT INTO guest_merges (account_id, guest_player_id, merged_at) VALUES (?, ?, ?)",
            (account_id, guest_player_id, now),
        )
        conn.execute("UPDATE accounts SET merge_used = 1 WHERE id = ?", (account_id,))

        _delete_player_rows(conn, guest_player_id)

    return account_by_id(ledger.get_conn(), account_id)  # type: ignore[return-value]


def _load_meter(raw: Any) -> dict:
    import json as _json

    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        data = _json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _later_date(a: str | None, b: str | None) -> str | None:
    if a and b:
        return a if a >= b else b
    return a or b


def _later_ts(a: str | None, b: str | None) -> str | None:
    da, db = _parse_iso(a), _parse_iso(b)
    if da and db:
        return a if da >= db else b
    return a or b


def _merge_missions(conn, dest: str, guest: str) -> None:
    rows = conn.execute("SELECT * FROM missions WHERE player_id = ?", (guest,)).fetchall()
    for row in rows:
        existing = conn.execute(
            """
            SELECT progress, claimed FROM missions
            WHERE player_id = ? AND mission_date = ? AND slot = ?
            """,
            (dest, row["mission_date"], row["slot"]),
        ).fetchone()
        if not existing:
            conn.execute(
                """
                INSERT INTO missions
                    (player_id, mission_date, slot, mission_id, progress, target, claimed)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dest,
                    row["mission_date"],
                    row["slot"],
                    row["mission_id"],
                    row["progress"],
                    row["target"],
                    row["claimed"],
                ),
            )
        else:
            conn.execute(
                """
                UPDATE missions
                SET progress = CASE WHEN progress > ? THEN progress ELSE ? END,
                    claimed = CASE WHEN claimed != 0 OR ? != 0 THEN 1 ELSE 0 END
                WHERE player_id = ? AND mission_date = ? AND slot = ?
                """,
                (
                    row["progress"],
                    row["progress"],
                    row["claimed"],
                    dest,
                    row["mission_date"],
                    row["slot"],
                ),
            )
    conn.execute("DELETE FROM missions WHERE player_id = ?", (guest,))


def _delete_player_rows(conn, player_id: str) -> None:
    for table in (
        "trophies",
        "missions",
        "spin_records",
        "processed_sessions",
        "ledger_entries",
        "side_sessions",
        "balances",
        "withdrawals",
        "leaderboard_payouts",
    ):
        conn.execute(f"DELETE FROM {table} WHERE player_id = ?", (player_id,))
    conn.execute("DELETE FROM players WHERE id = ?", (player_id,))


def delete_account(account_id: str) -> None:
    """Permanently delete the account row, sessions, and linked player progress."""
    import ledger

    with ledger.transaction() as conn:
        acc = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if not acc:
            raise ValueError("Account not found")
        player_id = acc["player_id"]
        conn.execute("DELETE FROM auth_sessions WHERE account_id = ?", (account_id,))
        conn.execute("DELETE FROM guest_merges WHERE account_id = ?", (account_id,))
        conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        _delete_player_rows(conn, player_id)


def account_public(
    account: dict[str, Any] | None,
    *,
    guest_id: str | None = None,
    include_email: bool = True,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "signed_in": bool(account),
        "google_enabled": google_enabled(),
        "privacy": PRIVACY_NOTE,
    }
    if not account:
        out["guest"] = True
        return out
    out.update(
        {
            "id": account["id"],
            "display_name": account["display_name"],
            "name": account.get("name"),
            "picture": account.get("picture"),
            "player_id": account["player_id"],
            "merge_used": int(account.get("merge_used") or 0),
        }
    )
    if include_email:
        out["email"] = account.get("email")
    offer = merge_preview(account, guest_id)
    if offer:
        out["needs_merge"] = True
        out["merge"] = offer
    else:
        out["needs_merge"] = False
    return out
