# Additive migration: Live events calendar

**Status:** applied automatically on local SQLite and in unit tests. **Not applied** when a hosted `DATABASE_URL` is set, unless `ALLOW_SCHEMA_MIGRATE=1`.

**Do not run this branch against the production Render Postgres** (`crystal-casino-db`). This staging branch must not be merged to `main` (which auto-deploys) until sign-off. Never set `ALLOW_SCHEMA_MIGRATE=1` on production.

## Purpose

A server-side weekly calendar of coins-only live events (happy hour, season XP boost, club points boost, event chest, play challenge, and the existing weekend tournament). Boosts multiply season XP or club points only. They **never change game math, paytables, payouts, or RTP**.

Event prizes are **house-issued promotional virtual coins**. They have no cash value, cannot be redeemed, and cannot be transferred between players. Credits are not taken from the game house pool.

Each collect or challenge claim is atomic and idempotent per player per event, keyed by `event-claim:{event_id}:player:{player_id}`. Happy-hour bonuses are capped and keyed by `event-bonus:{event_id}:player:{player_id}:play:{n}`. There are no paid skips, no loot-box randomness, and no fake countdowns — each card shows the real `ends_at` in Australia/Perth.

## SQL (additive, safe)

```sql
CREATE TABLE IF NOT EXISTS event_progress (
    player_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    plays INTEGER NOT NULL DEFAULT 0,
    bonus_coins INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (player_id, event_id)
);

CREATE TABLE IF NOT EXISTS event_claims (
    claim_key TEXT PRIMARY KEY,
    player_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    amount INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS event_claims_unique
    ON event_claims(player_id, event_id);
```

## Gate

`ensure_schema` is a no-op unless:

1. `ALLOW_SCHEMA_MIGRATE=1`, or
2. `DATABASE_URL` is unset (local SQLite / tests).

To apply later on a **non-production** staging database after sign-off, set `ALLOW_SCHEMA_MIGRATE=1` and start the app, or run the SQL above once as a migration.

## Rollback

Drop in dependency order. This does not affect balances already credited, purchases, or game math.

```sql
DROP TABLE IF EXISTS event_claims;
DROP TABLE IF EXISTS event_progress;
```

Already-paid event rewards stay in `ledger_entries` (`kind = 'event_reward'`) and player balances. Do not reverse them as part of a schema rollback.
