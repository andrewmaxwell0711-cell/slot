"""SQLite ledger — authoritative balances, idempotent Stripe credits, simulated withdrawals."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from game import (
    ALL_ASSETS,
    CRYPTO,
    FIAT,
    clean_amount,
    from_aud,
    to_aud,
    total_aud,
)

DB_PATH = Path(__file__).resolve().parent / "ledger.db"

_local = threading.local()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or DB_PATH
    conn = sqlite3.connect(str(db_path), check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = connect()
        _local.conn = conn
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    c = conn or get_conn()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS players (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            display_currency TEXT NOT NULL DEFAULT 'AUD',
            spins INTEGER NOT NULL DEFAULT 0,
            total_won_aud REAL NOT NULL DEFAULT 0,
            total_bet_aud REAL NOT NULL DEFAULT 0,
            last_win_aud REAL NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS balances (
            player_id TEXT NOT NULL,
            asset TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (player_id, asset),
            FOREIGN KEY (player_id) REFERENCES players(id)
        );

        CREATE TABLE IF NOT EXISTS processed_sessions (
            session_id TEXT PRIMARY KEY,
            player_id TEXT NOT NULL,
            asset TEXT NOT NULL,
            amount REAL NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ledger_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            asset TEXT NOT NULL,
            amount REAL NOT NULL,
            stripe_session_id TEXT,
            note TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id TEXT NOT NULL,
            asset TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    conn = get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def ensure_player(player_id: str) -> None:
    conn = get_conn()
    existing = conn.execute("SELECT id FROM players WHERE id = ?", (player_id,)).fetchone()
    if existing:
        return
    with transaction() as c:
        row = c.execute("SELECT id FROM players WHERE id = ?", (player_id,)).fetchone()
        if row:
            return
        now = _utc_now()
        c.execute(
            "INSERT INTO players (id, created_at) VALUES (?, ?)",
            (player_id, now),
        )
        for asset in ALL_ASSETS:
            c.execute(
                "INSERT INTO balances (player_id, asset, amount) VALUES (?, ?, 0)",
                (player_id, asset),
            )


def _balances_map(conn: sqlite3.Connection, player_id: str) -> dict[str, float]:
    rows = conn.execute(
        "SELECT asset, amount FROM balances WHERE player_id = ?",
        (player_id,),
    ).fetchall()
    balances = {asset: 0.0 for asset in ALL_ASSETS}
    for row in rows:
        balances[row["asset"]] = float(row["amount"])
    return balances


def _player_stats(conn: sqlite3.Connection, player_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT display_currency, spins, total_won_aud, total_bet_aud, last_win_aud
        FROM players WHERE id = ?
        """,
        (player_id,),
    ).fetchone()
    if not row:
        return {
            "display_currency": "AUD",
            "spins": 0,
            "total_won_aud": 0.0,
            "total_bet_aud": 0.0,
            "last_win_aud": 0.0,
        }
    return {
        "display_currency": row["display_currency"],
        "spins": int(row["spins"]),
        "total_won_aud": float(row["total_won_aud"]),
        "total_bet_aud": float(row["total_bet_aud"]),
        "last_win_aud": float(row["last_win_aud"]),
    }


def snapshot(player_id: str) -> dict[str, Any]:
    ensure_player(player_id)
    conn = get_conn()
    balances = _balances_map(conn, player_id)
    stats = _player_stats(conn, player_id)
    return {
        "balances": balances,
        "total_aud": total_aud(balances),
        "stats": {
            "spins": stats["spins"],
            "total_won_aud": stats["total_won_aud"],
            "total_bet_aud": stats["total_bet_aud"],
        },
        "last_win_aud": stats["last_win_aud"],
        "display_currency": stats["display_currency"],
    }


def set_display_currency(player_id: str, currency: str) -> dict[str, Any]:
    if currency not in FIAT:
        raise ValueError("Display currency must be AUD, USD, or EUR")
    ensure_player(player_id)
    with transaction() as conn:
        conn.execute(
            "UPDATE players SET display_currency = ? WHERE id = ?",
            (currency, player_id),
        )
    return snapshot(player_id)


def _credit(conn: sqlite3.Connection, player_id: str, asset: str, amount: float) -> None:
    amount = clean_amount(asset, amount)
    if amount <= 0:
        raise ValueError("Credit amount must be positive")
    conn.execute(
        """
        UPDATE balances SET amount = amount + ?
        WHERE player_id = ? AND asset = ?
        """,
        (amount, player_id, asset),
    )


def _debit(conn: sqlite3.Connection, player_id: str, asset: str, amount: float) -> None:
    amount = clean_amount(asset, amount)
    if amount <= 0:
        raise ValueError("Debit amount must be positive")
    row = conn.execute(
        "SELECT amount FROM balances WHERE player_id = ? AND asset = ?",
        (player_id, asset),
    ).fetchone()
    current = float(row["amount"]) if row else 0.0
    if amount > current + 1e-12:
        raise ValueError("Amount exceeds available balance")
    new_amount = clean_amount(asset, max(0.0, current - amount))
    conn.execute(
        "UPDATE balances SET amount = ? WHERE player_id = ? AND asset = ?",
        (new_amount, player_id, asset),
    )


def credit_play_money(player_id: str, asset: str, amount: float) -> dict[str, Any]:
    """Play-money crypto (or any explicitly allowed demo) credit — not a real transfer."""
    if asset not in CRYPTO:
        raise ValueError("Play-money deposits are only available for crypto assets")
    if amount <= 0:
        raise ValueError("Enter a valid amount")
    if amount > 1e9:
        raise ValueError("Amount too large for demo")
    ensure_player(player_id)
    amount = clean_amount(asset, amount)
    with transaction() as conn:
        _credit(conn, player_id, asset, amount)
        conn.execute(
            """
            INSERT INTO ledger_entries
                (player_id, kind, asset, amount, note, created_at)
            VALUES (?, 'deposit_play', ?, ?, 'Play-money crypto credit', ?)
            """,
            (player_id, asset, amount, _utc_now()),
        )
    return snapshot(player_id)


def credit_stripe_session(
    session_id: str,
    player_id: str,
    asset: str,
    amount: float,
) -> tuple[bool, str, dict[str, Any] | None]:
    """Credit a paid Checkout Session once. Idempotent per session_id.

    Returns (credited_now, message, snapshot_or_none).
    """
    if asset not in FIAT:
        raise ValueError("Stripe deposits are only accepted in AUD, USD, or EUR")
    if not session_id or not player_id:
        raise ValueError("Missing session or player id")
    if amount <= 0:
        raise ValueError("Invalid deposit amount")
    amount = clean_amount(asset, amount)
    ensure_player(player_id)
    with transaction() as conn:
        existing = conn.execute(
            "SELECT session_id, player_id, asset, amount FROM processed_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if existing:
            snap = snapshot(player_id)
            return False, "already credited", snap
        _credit(conn, player_id, asset, amount)
        now = _utc_now()
        conn.execute(
            """
            INSERT INTO processed_sessions (session_id, player_id, asset, amount, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, player_id, asset, amount, now),
        )
        conn.execute(
            """
            INSERT INTO ledger_entries
                (player_id, kind, asset, amount, stripe_session_id, note, created_at)
            VALUES (?, 'deposit_stripe', ?, ?, ?, 'Stripe test-mode Checkout credit', ?)
            """,
            (player_id, asset, amount, session_id, now),
        )
    return True, "credited", snapshot(player_id)


def get_processed_session(session_id: str) -> dict[str, Any] | None:
    row = get_conn().execute(
        "SELECT session_id, player_id, asset, amount, created_at FROM processed_sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "session_id": row["session_id"],
        "player_id": row["player_id"],
        "asset": row["asset"],
        "amount": float(row["amount"]),
        "created_at": row["created_at"],
    }


WITHDRAWAL_STATUS = "test withdrawal recorded"


def withdraw(player_id: str, asset: str, amount: float) -> dict[str, Any]:
    """Simulated test withdrawal: debit the ledger only. No Stripe payouts/transfers."""
    if asset not in ALL_ASSETS:
        raise ValueError("Unknown asset")
    if amount <= 0:
        raise ValueError("Enter a valid amount")
    amount = clean_amount(asset, amount)
    ensure_player(player_id)
    with transaction() as conn:
        _debit(conn, player_id, asset, amount)
        now = _utc_now()
        cur = conn.execute(
            """
            INSERT INTO withdrawals (player_id, asset, amount, status, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (player_id, asset, amount, WITHDRAWAL_STATUS, now),
        )
        conn.execute(
            """
            INSERT INTO ledger_entries
                (player_id, kind, asset, amount, note, created_at)
            VALUES (?, 'withdraw', ?, ?, ?, ?)
            """,
            (player_id, asset, amount, WITHDRAWAL_STATUS, now),
        )
        withdrawal_id = cur.lastrowid
    snap = snapshot(player_id)
    snap["withdrawal"] = {
        "id": withdrawal_id,
        "asset": asset,
        "amount": amount,
        "status": WITHDRAWAL_STATUS,
    }
    return snap


def debit_bet_and_maybe_credit_win(
    player_id: str,
    bet_aud: float,
    win_aud: float,
    display_currency: str,
) -> dict[str, Any]:
    """Atomically take the bet (fiat first, then crypto) and credit any win."""
    if bet_aud <= 0:
        raise ValueError("Invalid bet")
    if display_currency not in FIAT:
        display_currency = "AUD"
    ensure_player(player_id)
    with transaction() as conn:
        balances = _balances_map(conn, player_id)
        if total_aud(balances) + 1e-9 < bet_aud:
            raise ValueError("Insufficient balance — deposit first")

        remaining = bet_aud
        now = _utc_now()
        for asset in list(FIAT) + list(CRYPTO):
            if remaining <= 0:
                break
            bal_aud = to_aud(asset, balances.get(asset, 0.0) or 0.0)
            if bal_aud <= 0:
                continue
            take_aud = min(bal_aud, remaining)
            take_asset = from_aud(asset, take_aud)
            _debit(conn, player_id, asset, take_asset)
            conn.execute(
                """
                INSERT INTO ledger_entries
                    (player_id, kind, asset, amount, note, created_at)
                VALUES (?, 'spin_bet', ?, ?, ?, ?)
                """,
                (player_id, asset, clean_amount(asset, take_asset), f"bet {bet_aud} AUD", now),
            )
            remaining -= take_aud

        if remaining > 0.0001:
            raise ValueError("Insufficient balance — deposit first")

        if win_aud > 0:
            win_asset_amount = from_aud(display_currency, win_aud)
            _credit(conn, player_id, display_currency, win_asset_amount)
            conn.execute(
                """
                INSERT INTO ledger_entries
                    (player_id, kind, asset, amount, note, created_at)
                VALUES (?, 'spin_win', ?, ?, ?, ?)
                """,
                (
                    player_id,
                    display_currency,
                    clean_amount(display_currency, win_asset_amount),
                    f"win {win_aud} AUD",
                    now,
                ),
            )

        conn.execute(
            """
            UPDATE players
            SET spins = spins + 1,
                total_bet_aud = total_bet_aud + ?,
                total_won_aud = total_won_aud + ?,
                last_win_aud = ?,
                display_currency = ?
            WHERE id = ?
            """,
            (bet_aud, max(0.0, win_aud), max(0.0, win_aud), display_currency, player_id),
        )
    return snapshot(player_id)
