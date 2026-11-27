# Additive migration: Season pass

**Status:** applied automatically on local SQLite and in unit tests. **Not applied** when a hosted `DATABASE_URL` is set, unless `ALLOW_SCHEMA_MIGRATE=1`.

**Do not run this branch against the production Render Postgres** (`crystal-casino-db`). This staging branch must not be merged to `main` (which auto-deploys) until sign-off. Never set `ALLOW_SCHEMA_MIGRATE=1` on production.

## Purpose

A 4-week, 30-tier coins-only season pass. XP comes from settled play (including losses) through `events.on_play`, plus daily and weekly missions. The free track pays **house-issued promotional virtual coins and cosmetics** (frames and emblems). They have no cash value, cannot be redeemed, and cannot be transferred between players. Credits are not taken from the game house pool, so they cannot change slot RTP.

The premium track is catalogued and shown up front (no loot-box randomness) but is **not sold in this build**. A future Android build may unlock it with Google Play Billing. Do not add a Stripe or other real-money purchase for the pass on the web.

Each claim is atomic and idempotent per player, per season and per tier, keyed by `season-claim:{season_id}:player:{player_id}:track:{track}:tier:{n}`.

## SQL (additive, safe)

```sql
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
```

- No existing tables or columns are altered or dropped.
- Mission XP is granted only when `xp_granted` flips from 0 to 1, so a mission cannot pay twice.
- Season progress is keyed by `season_id`, so a rollover starts a fresh track without rewriting history.

## How it is applied

`season.ensure_schema(conn)` is called from `ledger.init_db()` only when:

1. `ALLOW_SCHEMA_MIGRATE=1`, or
2. `DATABASE_URL` is unset (local SQLite / tests).

To apply later on a **non-production** staging database after sign-off, set `ALLOW_SCHEMA_MIGRATE=1` and start the app, or run the SQL above once as a migration.

## Rollback

Drop in dependency order. This does not affect balances already credited, purchases, or game math.

```sql
DROP TABLE IF EXISTS season_cosmetics;
DROP TABLE IF EXISTS season_missions;
DROP TABLE IF EXISTS season_claims;
DROP TABLE IF EXISTS season_progress;
```

Already-paid season rewards stay in `ledger_entries` (`kind = 'season_reward'`) and player balances. Do not reverse them as part of a schema rollback.
