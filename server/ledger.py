"""SQLite ledger — authoritative coin balances, idempotent Stripe coin-pack credits.

Social casino: coins have no cash value and cannot be withdrawn, redeemed,
transferred or exchanged for money or prizes. There is no cash-out path.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo

from game import jackpot_roll as game_jackpot_roll
from game import settle_steps as game_settle_steps
from game import (
    COIN_ASSET,
    COIN_PACKS,
    DAILY_COINS,
    GAMBLE_MAX_ROUNDS,
    HOURLY_COINS,
    HOURLY_SECONDS,
    STARTING_COINS,
    clean_amount,
    from_coins,
    pack_by_id,
    to_coins,
)

PERTH = ZoneInfo("Australia/Perth")

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

        -- Single-row house pool: every stake goes in, every payout comes out.
        -- jackpot_aud is legacy (unused): the jackpot now pays a fixed multiple of bet.
        CREATE TABLE IF NOT EXISTS house (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            pool_aud REAL NOT NULL DEFAULT 0 CHECK (pool_aud >= 0),
            jackpot_aud REAL NOT NULL DEFAULT 0 CHECK (jackpot_aud >= 0),
            total_staked_aud REAL NOT NULL DEFAULT 0,
            total_paid_aud REAL NOT NULL DEFAULT 0,
            biggest_win_aud REAL NOT NULL DEFAULT 0,
            updated_at TEXT
        );
        INSERT OR IGNORE INTO house (id, pool_aud, jackpot_aud) VALUES (1, 0, 0);

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
    _migrate(c)
    from prizes import ensure_schema
    ensure_schema(c)


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
        c.execute(
            "INSERT INTO balances (player_id, asset, amount) VALUES (?, ?, ?)",
            (player_id, COIN_ASSET, STARTING_COINS),
        )
        c.execute(
            """
            INSERT INTO ledger_entries
                (player_id, kind, asset, amount, note, created_at)
            VALUES (?, 'welcome_grant', ?, ?, 'Free starting coins — no cash value', ?)
            """,
            (player_id, COIN_ASSET, STARTING_COINS, now),
        )


def _coin_balance(conn: sqlite3.Connection, player_id: str) -> int:
    row = conn.execute(
        "SELECT amount FROM balances WHERE player_id = ? AND asset = ?",
        (player_id, COIN_ASSET),
    ).fetchone()
    if not row:
        conn.execute(
            "INSERT INTO balances (player_id, asset, amount) VALUES (?, ?, 0)",
            (player_id, COIN_ASSET),
        )
        return 0
    return int(round(float(row["amount"])))


def _player_stats(conn: sqlite3.Connection, player_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT display_currency, spins, total_won_aud, total_bet_aud, last_win_aud, gamble_aud
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
            "gamble_aud": 0.0,
        }
    return {
        "display_currency": row["display_currency"],
        "spins": int(row["spins"]),
        "total_won_aud": float(row["total_won_aud"]),
        "total_bet_aud": float(row["total_bet_aud"]),
        "last_win_aud": float(row["last_win_aud"]),
        "gamble_aud": float(row["gamble_aud"] or 0),
    }


def _bonus_status(conn: sqlite3.Connection, player_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT last_daily_date, last_hourly_at FROM players WHERE id = ?",
        (player_id,),
    ).fetchone()
    today = datetime.now(PERTH).date().isoformat()
    last_daily = (row["last_daily_date"] if row else None) or ""
    daily_available = last_daily != today
    last_hourly = (row["last_hourly_at"] if row else None) or ""
    remaining = 0
    hourly_available = True
    if last_hourly:
        try:
            ts = datetime.fromisoformat(last_hourly)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds()
            if elapsed < HOURLY_SECONDS:
                hourly_available = False
                remaining = int(max(0, HOURLY_SECONDS - elapsed))
        except ValueError:
            hourly_available = True
    # VIP tiers bump the free hourly (and a little of the daily) grant.
    daily_coins, hourly_coins = DAILY_COINS, HOURLY_COINS
    try:
        import prizes as _prizes
        row2 = conn.execute("SELECT level FROM players WHERE id = ?", (player_id,)).fetchone()
        level = int((row2["level"] if row2 else 1) or 1)
        vip = _prizes.vip_for_level(level)
        daily_coins = int(vip["daily_coins"])
        hourly_coins = int(vip["hourly_coins"])
    except Exception:
        pass
    return {
        "daily_available": daily_available,
        "daily_coins": daily_coins,
        "hourly_available": hourly_available,
        "hourly_seconds": remaining,
        "hourly_coins": hourly_coins,
        "starting_coins": STARTING_COINS,
    }


def snapshot(player_id: str) -> dict[str, Any]:
    """Player-facing snapshot. Coins only — no fiat, crypto, pool or cash-out fields."""
    ensure_player(player_id)
    conn = get_conn()
    stats = _player_stats(conn, player_id)
    coins = _coin_balance(conn, player_id)
    out = {
        "coins": coins,
        "stats": {
            "spins": stats["spins"],
            "total_won": to_coins(stats["total_won_aud"]),
            "total_bet": to_coins(stats["total_bet_aud"]),
        },
        "last_win": to_coins(stats["last_win_aud"]),
        "gamble": to_coins(stats["gamble_aud"]),
        "bonuses": _bonus_status(conn, player_id),
        "progressive": progressive_public()["progressive"],
    }
    import json as _json
    from game import COLLECT_SET, COLLECT_TYPES, COLLECT_PAY_MULT
    rowm = conn.execute("SELECT collect_meter FROM players WHERE id = ?", (player_id,)).fetchone()
    try:
        meter = _json.loads(rowm["collect_meter"] if rowm and "collect_meter" in rowm.keys() and rowm["collect_meter"] else "{}")
    except Exception:
        meter = {}
    out["collection"] = {
        "meter": {k: int(meter.get(k) or 0) for k in COLLECT_TYPES},
        "set_size": COLLECT_SET,
        "pay_mult": COLLECT_PAY_MULT,
    }
    from prizes import attach
    return attach(player_id, out)


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


def credit_coin_pack(
    session_id: str,
    player_id: str,
    pack_id: str,
    coins: int,
    price_aud: float | None = None,
) -> tuple[bool, str, dict[str, Any] | None]:
    """Credit a paid coin-pack Checkout Session once. Idempotent per session_id.

    Returns (credited_now, message, snapshot_or_none).
    Coins are virtual only — this never creates a redeemable or cash balance.
    """
    if not session_id or not player_id:
        raise ValueError("Missing session or player id")
    pack = pack_by_id(pack_id)
    if not pack:
        raise ValueError("Unknown coin pack")
    coins = int(coins)
    if coins != int(pack["coins"]):
        raise ValueError("Coin pack amount does not match the catalogue")
    if coins <= 0:
        raise ValueError("Invalid coin pack")
    if price_aud is not None and abs(float(price_aud) - float(pack["price_aud"])) > 0.001:
        raise ValueError("Coin pack price does not match the catalogue")
    ensure_player(player_id)
    with transaction() as conn:
        existing = conn.execute(
            "SELECT session_id, player_id, asset, amount FROM processed_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if existing:
            return False, "already credited", snapshot(player_id)
        _credit(conn, player_id, COIN_ASSET, coins)
        now = _utc_now()
        conn.execute(
            """
            INSERT INTO processed_sessions (session_id, player_id, asset, amount, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, player_id, COIN_ASSET, coins, now),
        )
        conn.execute(
            """
            INSERT INTO ledger_entries
                (player_id, kind, asset, amount, stripe_session_id, note, created_at)
            VALUES (?, 'shop_pack', ?, ?, ?, ?, ?)
            """,
            (
                player_id,
                COIN_ASSET,
                coins,
                session_id,
                f"Stripe test-mode coin pack {pack_id} — virtual coins, no cash value",
                now,
            ),
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


class BonusUnavailable(ValueError):
    def __init__(self, message: str, seconds: int = 0):
        super().__init__(message)
        self.seconds = seconds


def claim_daily(player_id: str) -> dict[str, Any]:
    """Free daily chest. Once per Australia/Perth calendar day."""
    ensure_player(player_id)
    today = datetime.now(PERTH).date().isoformat()
    with transaction() as conn:
        status = _bonus_status(conn, player_id)
        if not status["daily_available"]:
            raise BonusUnavailable("Daily bonus already claimed — come back tomorrow")
        awarded = int(status["daily_coins"])
        _credit(conn, player_id, COIN_ASSET, awarded)
        conn.execute(
            "UPDATE players SET last_daily_date = ? WHERE id = ?",
            (today, player_id),
        )
        conn.execute(
            """
            INSERT INTO ledger_entries
                (player_id, kind, asset, amount, note, created_at)
            VALUES (?, 'daily_bonus', ?, ?, 'Free daily coins — no cash value', ?)
            """,
            (player_id, COIN_ASSET, awarded, _utc_now()),
        )
    snap = snapshot(player_id)
    snap["awarded"] = awarded
    snap["bonus"] = "daily"
    return snap


def claim_hourly(player_id: str) -> dict[str, Any]:
    """Free hourly coin drop so play never requires a purchase."""
    ensure_player(player_id)
    with transaction() as conn:
        status = _bonus_status(conn, player_id)
        if not status["hourly_available"]:
            raise BonusUnavailable(
                "Hourly bonus is not ready yet",
                seconds=status["hourly_seconds"],
            )
        awarded = int(status["hourly_coins"])
        _credit(conn, player_id, COIN_ASSET, awarded)
        conn.execute(
            "UPDATE players SET last_hourly_at = ? WHERE id = ?",
            (_utc_now(), player_id),
        )
        conn.execute(
            """
            INSERT INTO ledger_entries
                (player_id, kind, asset, amount, note, created_at)
            VALUES (?, 'hourly_bonus', ?, ?, 'Free hourly coins — no cash value', ?)
            """,
            (player_id, COIN_ASSET, awarded, _utc_now()),
        )
    snap = snapshot(player_id)
    snap["awarded"] = awarded
    snap["bonus"] = "hourly"
    return snap


# ---------------------------------------------------------------------------
# House pool (internal stat only — never sent to players, does not limit wins)
# ---------------------------------------------------------------------------


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(players)").fetchall()}
    if "gamble_aud" not in cols:
        conn.execute("ALTER TABLE players ADD COLUMN gamble_aud REAL NOT NULL DEFAULT 0")
    if "gamble_rounds" not in cols:
        conn.execute("ALTER TABLE players ADD COLUMN gamble_rounds INTEGER NOT NULL DEFAULT 0")
    if "last_daily_date" not in cols:
        conn.execute("ALTER TABLE players ADD COLUMN last_daily_date TEXT")
    if "last_hourly_at" not in cols:
        conn.execute("ALTER TABLE players ADD COLUMN last_hourly_at TEXT")
    if "collect_meter" not in cols:
        conn.execute("ALTER TABLE players ADD COLUMN collect_meter TEXT NOT NULL DEFAULT '{}'")
    house_cols = {r["name"] for r in conn.execute("PRAGMA table_info(house)").fetchall()}
    if "progressive_aud" not in house_cols:
        conn.execute("ALTER TABLE house ADD COLUMN progressive_aud REAL NOT NULL DEFAULT 25")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS side_sessions (
            player_id TEXT PRIMARY KEY,
            game TEXT NOT NULL,
            state TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _house_row(conn: sqlite3.Connection) -> dict[str, float]:
    row = conn.execute(
        "SELECT pool_aud, total_staked_aud, total_paid_aud, biggest_win_aud, progressive_aud FROM house WHERE id = 1"
    ).fetchone()
    if not row:
        conn.execute("INSERT OR IGNORE INTO house (id) VALUES (1)")
        return {"pool_aud": 0.0, "total_staked_aud": 0.0, "total_paid_aud": 0.0, "biggest_win_aud": 0.0,
                "progressive_aud": 25.0}
    out = {k: float(row[k]) for k in row.keys() if k in row.keys()}
    if "progressive_aud" not in out:
        out["progressive_aud"] = 25.0
    return out


def pool_status() -> dict[str, Any]:
    """Internal/admin view for tests and scripts. Not exposed by the public API."""
    h = _house_row(get_conn())
    pool = max(0.0, h["pool_aud"])
    return {
        "pool_aud": round(pool, 2),
        "total_staked_aud": round(h["total_staked_aud"], 2),
        "total_paid_aud": round(h["total_paid_aud"], 2),
        "biggest_win_aud": round(h["biggest_win_aud"], 2),
        "progressive_aud": round(float(h.get("progressive_aud") or 25), 2),
    }


def progressive_public() -> dict[str, Any]:
    """Published progressive ticker in coins. Never includes the hidden house pool."""
    from game import PROG_SEED, PROG_RATE, PROG_HIT_P, to_coins
    h = _house_row(get_conn())
    pot = max(float(h.get("progressive_aud") or PROG_SEED), 0.0)
    return {
        "progressive": to_coins(pot),
        "seed": to_coins(PROG_SEED),
        "contribution_rate": PROG_RATE,
    }


def _take_stake(conn: sqlite3.Connection, player_id: str, amount_units: float, kind: str, note: str) -> None:
    """Debit the coin equivalent of a game-unit stake. No cash leaves the ledger."""
    coins = to_coins(amount_units)
    if coins <= 0:
        raise ValueError("Invalid bet")
    if _coin_balance(conn, player_id) < coins:
        raise ValueError("Not enough coins — claim a free bonus or buy coins in the shop")
    _debit(conn, player_id, COIN_ASSET, coins)
    conn.execute(
        "INSERT INTO ledger_entries (player_id, kind, asset, amount, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (player_id, kind, COIN_ASSET, coins, note, _utc_now()),
    )


def _pay(conn: sqlite3.Connection, player_id: str, amount_units: float, kind: str, note: str) -> None:
    if amount_units <= 0:
        return
    coins = to_coins(amount_units)
    if coins <= 0:
        return
    _credit(conn, player_id, COIN_ASSET, coins)
    conn.execute(
        "INSERT INTO ledger_entries (player_id, kind, asset, amount, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (player_id, kind, COIN_ASSET, coins, note, _utc_now()),
    )


def settle_round(
    player_id: str,
    total_bet_aud: float,
    rnd: dict[str, Any],
    display_currency: str,
    jackpot_roll: Callable[[float, float], bool] | None = None,
    wheel_roll: Callable[[float, float], bool] | None = None,
) -> dict[str, Any]:
    """Atomically: take the stake, add it to the internal house pool, roll the
    Green Tea Jackpot (fixed multiple of the bet), and pay each step of the
    round in full. The pool is an internal stat only — it never limits wins
    and is floored at 0.
    """
    if total_bet_aud <= 0:
        raise ValueError("Invalid bet")
    roll = jackpot_roll or game_jackpot_roll
    ensure_player(player_id)
    with transaction() as conn:
        _take_stake(conn, player_id, total_bet_aud, "spin_bet", f"bet {to_coins(total_bet_aud)} coins")
        h = _house_row(conn)
        pool = h["pool_aud"] + total_bet_aud
        jackpot_hit = bool(roll(total_bet_aud, pool))

        settled = game_settle_steps(rnd, total_bet_aud, pool, jackpot_hit, wheel_roll)
        results = settled["steps"]
        total_paid = settled["total_paid_aud"]
        jackpot_paid = settled["jackpot_paid_aud"]
        any_capped = settled["any_capped"]
        pool = settled["pool_after"]
        total_paid = round(total_paid, 2)

        import json as _json
        from game import collection_step, progressive_step, PROG_SEED
        pot = float(h.get("progressive_aud") or PROG_SEED)
        prog = progressive_step(total_bet_aud, pot)
        # Force a provided progressive roll in tests via rnd hook.
        if rnd.get("_force_progressive") is True:
            prog = {"contribution": total_bet_aud * 0.01, "pot": PROG_SEED, "hit": True,
                    "paid_aud": round(pot + total_bet_aud * 0.01, 2)}
        elif rnd.get("_force_progressive") is False:
            prog["hit"] = False
            prog["paid_aud"] = 0.0
            prog["pot"] = pot + total_bet_aud * 0.01
        prog_paid = float(prog["paid_aud"] or 0)
        rowm = conn.execute("SELECT collect_meter FROM players WHERE id = ?", (player_id,)).fetchone()
        try:
            meter = _json.loads(rowm["collect_meter"] if rowm and rowm["collect_meter"] else "{}")
        except Exception:
            meter = {}
        coll = collection_step(total_bet_aud, meter)
        if rnd.get("_force_collection"):
            coll = dict(coll)
            # tests may inject a completed set
        coll_paid = float(coll.get("paid_aud") or 0)
        extra = round(prog_paid + coll_paid, 2)
        if extra:
            total_paid = round(total_paid + extra, 2)
            pool = max(0.0, round(pool - extra, 6))
        _pay(conn, player_id, total_paid, "spin_win",
             f"win {to_coins(total_paid)} coins" + (" (jackpot)" if jackpot_paid else "")
             + (" (progressive)" if prog_paid else "") + (" (collection)" if coll_paid else ""))
        now = _utc_now()
        conn.execute(
            """
            UPDATE house SET pool_aud = ?, total_staked_aud = total_staked_aud + ?,
                total_paid_aud = total_paid_aud + ?, biggest_win_aud = MAX(biggest_win_aud, ?),
                progressive_aud = ?, updated_at = ?
            WHERE id = 1
            """,
            (round(pool, 6), total_bet_aud, total_paid, total_paid, float(prog["pot"]), now),
        )
        conn.execute(
            "UPDATE players SET collect_meter = ? WHERE id = ?",
            (_json.dumps(coll["meter"]), player_id),
        )
        conn.execute(
            """
            UPDATE players
            SET spins = spins + 1, total_bet_aud = total_bet_aud + ?, total_won_aud = total_won_aud + ?,
                last_win_aud = ?, gamble_aud = ?, gamble_rounds = 0
            WHERE id = ?
            """,
            (total_bet_aud, total_paid, total_paid, total_paid if total_paid > 0 else 0.0, player_id),
        )
    from prizes import after_spin
    if prog.get("hit"):
        rnd["_progressive_hit"] = True
    if coll.get("completed"):
        rnd["_collection_completed"] = True
    prize = after_spin(player_id, total_bet_aud, total_paid, jackpot_paid, rnd, results)
    snap = snapshot(player_id)
    snap["trophies"]["new"] = prize.get("trophies", {}).get("new") or []
    if prize.get("level_up"):
        snap["level_up"] = prize["level_up"]
    snap["steps"] = results
    snap["total_paid_aud"] = total_paid
    snap["jackpot_hit"] = jackpot_paid > 0
    snap["jackpot_paid_aud"] = jackpot_paid
    snap["any_capped"] = any_capped
    snap["progressive"] = to_coins(prog["pot"])
    snap["progressive_hit"] = bool(prog["hit"])
    snap["progressive_paid"] = to_coins(prog_paid)
    snap["collection"] = {
        "meter": coll["meter"],
        "added": coll.get("added"),
        "completed": coll.get("completed"),
        "paid": to_coins(coll_paid),
        "set_size": coll.get("set_size"),
    }
    return snap


def gamble(player_id: str, choice: str, draw: Callable[[], dict[str, str]]) -> dict[str, Any]:
    """Double-up: stake the last win on red/black. Fair 50/50, decided server-side.

    The gamble is a fresh bet of S = current gamble amount. A win pays 2S.
    There is no pool cap; the only limit is GAMBLE_MAX_ROUNDS in a row.
    """
    if choice not in ("red", "black"):
        raise ValueError("Pick red or black")
    ensure_player(player_id)
    with transaction() as conn:
        row = conn.execute("SELECT gamble_aud, gamble_rounds FROM players WHERE id = ?", (player_id,)).fetchone()
        stake = round(float(row["gamble_aud"]), 2)
        rounds = int(row["gamble_rounds"])
        if stake <= 0:
            raise ValueError("Nothing to gamble — win a spin first")
        if rounds >= GAMBLE_MAX_ROUNDS:
            raise ValueError("Gamble limit reached — win collected")
        h = _house_row(conn)
        pool_with_stake = h["pool_aud"] + stake
        _take_stake(conn, player_id, stake, "gamble_bet", f"gamble {to_coins(stake)} coins on {choice}")
        card = draw()
        won = card["colour"] == choice
        payout = round(2 * stake, 2) if won else 0.0
        _pay(conn, player_id, payout, "gamble_win", f"gamble win {to_coins(payout)} coins")
        pool = max(0.0, pool_with_stake - payout)
        new_stake = payout if won and rounds + 1 < GAMBLE_MAX_ROUNDS else 0.0
        conn.execute(
            """
            UPDATE house SET pool_aud = ?, total_staked_aud = total_staked_aud + ?,
                total_paid_aud = total_paid_aud + ?, updated_at = ? WHERE id = 1
            """,
            (round(pool, 6), stake, payout, _utc_now()),
        )
        conn.execute(
            "UPDATE players SET gamble_aud = ?, gamble_rounds = ?, last_win_aud = ? WHERE id = ?",
            (new_stake, rounds + 1 if new_stake else 0, payout, player_id),
        )
    snap = snapshot(player_id)
    snap["card"] = card
    snap["won"] = won
    snap["gamble_aud"] = new_stake  # game units, for tests
    snap["gamble_stake_aud"] = stake
    snap["gamble_payout_aud"] = payout
    snap["rounds_left"] = (GAMBLE_MAX_ROUNDS - rounds - 1) if new_stake else 0
    return snap


def gamble_collect(player_id: str) -> dict[str, Any]:
    ensure_player(player_id)
    with transaction() as conn:
        conn.execute("UPDATE players SET gamble_aud = 0, gamble_rounds = 0 WHERE id = ?", (player_id,))
    return snapshot(player_id)


class GambleUnavailable(ValueError):
    pass


# ---------------------------------------------------------------------------
# Side games (lobby). Bets are integer coins; outcomes come from side.py.
# ---------------------------------------------------------------------------

def _take_coins(conn: sqlite3.Connection, player_id: str, coins: int, kind: str, note: str) -> None:
    coins = int(coins)
    if coins <= 0:
        raise ValueError("Invalid bet")
    if _coin_balance(conn, player_id) < coins:
        raise ValueError("Not enough coins — claim a free bonus or buy coins in the shop")
    _debit(conn, player_id, COIN_ASSET, coins)
    conn.execute(
        "INSERT INTO ledger_entries (player_id, kind, asset, amount, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (player_id, kind, COIN_ASSET, coins, note, _utc_now()),
    )


def _pay_coins(conn: sqlite3.Connection, player_id: str, coins: int, kind: str, note: str) -> None:
    coins = int(coins)
    if coins <= 0:
        return
    _credit(conn, player_id, COIN_ASSET, coins)
    conn.execute(
        "INSERT INTO ledger_entries (player_id, kind, asset, amount, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (player_id, kind, COIN_ASSET, coins, note, _utc_now()),
    )


def side_session(player_id: str) -> dict | None:
    ensure_player(player_id)
    import json as _json
    import side as _side
    row = get_conn().execute(
        "SELECT game, state FROM side_sessions WHERE player_id = ?", (player_id,)
    ).fetchone()
    if not row:
        return None
    state = _json.loads(row["state"])
    return {"game": row["game"], **_side.public_state(state)}


def clear_side_session(player_id: str) -> None:
    with transaction() as conn:
        conn.execute("DELETE FROM side_sessions WHERE player_id = ?", (player_id,))


def play_side(player_id: str, game: str, payload: dict | None = None) -> dict:
    """Debit/credit coins around a side-game action and persist any open hand."""
    import json as _json
    import side as _side
    payload = payload or {}
    game = str(game or "").lower().strip()
    if game not in _side.GAMES:
        raise ValueError("Unknown game")
    ensure_player(player_id)
    action = str(payload.get("action") or "").lower().strip()

    with transaction() as conn:
        row = conn.execute(
            "SELECT game, state FROM side_sessions WHERE player_id = ?", (player_id,)
        ).fetchone()
        existing = _json.loads(row["state"]) if row else None
        existing_game = row["game"] if row else None

        def _save(state: dict | None) -> None:
            if state is None or state.get("done"):
                conn.execute("DELETE FROM side_sessions WHERE player_id = ?", (player_id,))
            else:
                conn.execute(
                    """
                    INSERT INTO side_sessions (player_id, game, state, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(player_id) DO UPDATE SET game = excluded.game, state = excluded.state,
                        updated_at = excluded.updated_at
                    """,
                    (player_id, game, _json.dumps(state), _utc_now()),
                )

        def _finish(state: dict, debit: int, payout: int) -> dict:
            # debit already taken; credit payout (includes returned stakes where the rules pay them)
            _pay_coins(conn, player_id, int(payout), "side_win", f"{game} payout {int(payout)} coins")
            pub = _side.public_state(state)
            pub["coins"] = _coin_balance(conn, player_id)
            return pub

        # --- one-shot games ---
        if game == "roulette":
            if existing:
                raise ValueError("Finish your current game first")
            bets = payload.get("bets") or []
            result = _side.roulette_spin(bets)
            _take_coins(conn, player_id, result["bet"], "side_bet", f"roulette {result['bet']} coins")
            _save(None)
            return _finish(result, result["bet"], result["payout"])

        if game == "scratch":
            if existing:
                raise ValueError("Finish your current game first")
            result = _side.scratch_play(payload.get("bet") or payload.get("coins") or 0)
            _take_coins(conn, player_id, result["bet"], "side_bet", f"scratch {result['bet']} coins")
            _save(None)
            return _finish(result, result["bet"], result["payout"])

        if game == "dice":
            if existing:
                raise ValueError("Finish your current game first")
            result = _side.dice_play(payload.get("bet") or payload.get("coins") or 0)
            _take_coins(conn, player_id, result["bet"], "side_bet", f"dice {result['bet']} coins")
            _save(None)
            return _finish(result, result["bet"], result["payout"])

        if game == "highcard":
            if existing and existing.get("awaiting_war"):
                if action == "push":
                    # Stake already taken; pay the push (return bet) and close.
                    payout = int(existing.get("payout") or existing.get("bet") or 0)
                    existing["done"] = True
                    existing["result"] = "push"
                    existing["awaiting_war"] = False
                    _save(None)
                    return _finish(existing, 0, payout)
                if action == "war":
                    extra = int(existing["bet"])
                    _take_coins(conn, player_id, extra, "side_bet", f"highcard war {extra} coins")
                    result = _side.highcard_play(extra, war=True, previous=existing)
                    _save(None)
                    return _finish(result, extra, result["payout"])
                raise ValueError("Choose war or push")
            if existing:
                raise ValueError("Finish your current game first")
            want_offer = bool(payload.get("war_option") or payload.get("war"))
            result = _side.highcard_play(payload.get("bet") or payload.get("coins") or 0, war=want_offer)
            _take_coins(conn, player_id, result["bet"], "side_bet", f"highcard {result['bet']} coins")
            if result.get("awaiting_war"):
                _save(result)
                pub = _side.public_state(result)
                pub["coins"] = _coin_balance(conn, player_id)
                return pub
            _save(None)
            return _finish(result, result["bet"], result["payout"])

        if game == "mines":
            if action in ("", "start", "deal"):
                if existing and not existing.get("done"):
                    raise ValueError("Finish your current game first")
                state = _side.mines_start(payload.get("bet") or payload.get("coins") or 0,
                                          payload.get("mines") or 3)
                _take_coins(conn, player_id, state["bet"], "side_bet", f"mines {state['bet']} coins")
                _save(state)
                pub = _side.public_state(state)
                pub["coins"] = _coin_balance(conn, player_id)
                return pub
            if not existing or existing_game != "mines":
                raise ValueError("No Crystal Mines round in play")
            if action == "pick":
                state = _side.mines_pick(existing, payload.get("tile"))
            elif action in ("cashout", "cash_out", "collect"):
                state = _side.mines_cashout(existing)
            else:
                raise ValueError("Unknown mines action")
            if state.get("done"):
                _save(None)
                return _finish(state, 0, int(state.get("payout") or 0))
            _save(state)
            pub = _side.public_state(state)
            pub["coins"] = _coin_balance(conn, player_id)
            return pub

        if game == "blackjack":
            if action in ("", "deal"):
                if existing and not existing.get("done"):
                    raise ValueError("Finish your current game first")
                bet = int(payload.get("bet") or payload.get("coins") or 0)
                state = _side.blackjack_deal(bet)
                _take_coins(conn, player_id, bet, "side_bet", f"blackjack {bet} coins")
                if state.get("done"):
                    _save(None)
                    return _finish(state, bet, int(state.get("payout") or 0))
                _save(state)
                pub = _side.public_state(state)
                pub["coins"] = _coin_balance(conn, player_id)
                return pub
            if not existing or existing_game != "blackjack":
                raise ValueError("No blackjack hand in play")
            extra = _side.blackjack_extra_needed(existing, action)
            if extra:
                _take_coins(conn, player_id, extra, "side_bet", f"blackjack {action} {extra} coins")
            state = _side.blackjack_act(existing, action, extra)
            if state.get("done"):
                _save(None)
                return _finish(state, extra, int(state.get("payout") or 0))
            _save(state)
            pub = _side.public_state(state)
            pub["coins"] = _coin_balance(conn, player_id)
            return pub

        raise ValueError("Unknown game")
