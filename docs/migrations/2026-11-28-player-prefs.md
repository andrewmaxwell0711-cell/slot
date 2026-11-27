# Additive migration: `player_prefs`

**Status:** applied automatically on local SQLite and in unit tests. **Not applied** when a hosted `DATABASE_URL` is set, unless `ALLOW_SCHEMA_MIGRATE=1`.

**Do not run this branch against the production Render Postgres** (`crystal-casino-db`). This staging branch must not be merged to `main` (which auto-deploys) until sign-off.

## Purpose

Store first-time tutorial completion per player (guest or signed-in), so the walkthrough can be skipped or finished once.

## SQL (additive, safe)

```sql
CREATE TABLE IF NOT EXISTS player_prefs (
    player_id TEXT PRIMARY KEY,
    tutorial TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL,
    FOREIGN KEY (player_id) REFERENCES players(id)
);
```

- No existing tables or columns are altered or dropped.
- The table is empty until a player finishes or skips the tutorial.
- `tutorial` is a JSON object: `{ "status": "pending"|"done"|"skipped", "slots": bool, "table": bool }`.

## How it is applied

`prefs.ensure_schema(conn)` is called from `ledger.init_db()` only when:

1. `ALLOW_SCHEMA_MIGRATE=1`, or
2. `DATABASE_URL` is unset (local SQLite / tests).

To apply later on a **non-production** staging database after sign-off, set `ALLOW_SCHEMA_MIGRATE=1` and start the app, or run the SQL above once as a migration.

## Rollback

`DROP TABLE IF EXISTS player_prefs;` — does not affect balances, purchases, or game math.
