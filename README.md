# Crystal Casino — Social Casino (TEST MODE)

A social-casino slot (Megaways + 25-line Classic) with a **server-side ledger**, **server-side RNG**, free coin grants, and optional **Stripe Checkout in test mode** for coin packs.

This is **not** real-money gambling.

- **Virtual coins only.** Coins are for entertainment only, have no monetary value and cannot be redeemed for cash or prizes. They cannot be withdrawn, transferred, or exchanged for money.
- **There is no cash-out.** Withdrawal and crypto deposit/withdraw demo flows have been removed.
- **TEST MODE only.** The server refuses to start if `STRIPE_SECRET_KEY` is set and does not begin with `sk_test_`. Live keys (`sk_live_`) are never accepted.
- Buying coins is optional. New players receive a free starting grant, plus a free **daily chest** and a free **hourly bonus**, so play never requires a purchase.
- An **18+ age gate** is shown on first visit. A responsible-play note appears in the footer and shop.

## Coin economy

Internal game math still uses the original game units (so paytables, the hidden 20% cap, and RTP are unchanged). The public API and UI speak **integer coins** at `COIN_SCALE = 1000` (1 game unit = 1,000 coins).

| Grant / pack | Coins | Price (AUD, Stripe test charge only) |
|--------------|------:|--------------------------------------|
| Starting grant | 25,000 | Free |
| Daily chest (once per Australia/Perth calendar day) | 8,000 | Free |
| Hourly bonus (every 60 minutes) | 2,000 | Free |
| Pouch (`pack_5`) | 50,000 | A$4.99 |
| Sack (`pack_10`, Popular) | 120,000 | A$9.99 |
| Chest (`pack_20`, Best value) | 280,000 | A$19.99 |
| Vault (`pack_50`, Biggest) | 800,000 | A$49.99 |

Shop prices are what Stripe charges in AUD. The coins themselves have no cash value.

Classic bets: 20–4,000 coins per line (1/5/10/20/25 lines). Megaways bets: 200–100,000 coins.


## In-game prizes (virtual only)

All prizes are cosmetic or virtual coins. They have **no cash or real-world value** and cannot be redeemed, transferred, or exchanged for money or prizes.

- **Trophies & badges** for the Green Tea Jackpot, Big/Mega/Epic wins, free-spin triggers, Crystal Pick and Tea Wheel, level milestones, and win streaks. New unlocks play a toast and a sound. The **trophy cabinet** is in the Prizes panel.
- **Unlockable themes**: Crystal (default), Ruby Palace (level 2), Jade Garden (level 5), Sapphire Night (level 8). The theme picker only applies a skin the player has unlocked.
- **Missions**: three daily rotating missions (Australia/Perth), tracked on the server, with a progress bar and a one-time claim for bonus coins or a cosmetic badge.
- **Leaderboards**: daily and weekly (Perth time) top players by biggest win and total won, computed from real spin records. Players set a nickname (2–16 characters, sanitised, basic profanity filter). When a period ends, top 3 receive promotional coins and an exclusive badge.

XP and level are server-authoritative. Mission and leaderboard coin grants are promotional house grants, like the daily chest — they do not change RTP or the hidden 20% cap.

New routes: `POST /api/profile`, `POST /api/theme`, `GET /api/leaderboard`, `POST /api/missions/claim`.

## Features

- Megaways (up to 117,649 ways, tumbling reels, unlimited free-spin multiplier) and 25-line Classic, with Green Tea Jackpot, Crystal Pick, Tea Wheel, and red/black gamble
- v5 animation, sound, XP/streak engagement, autoplay, turbo, MAX BET, info, history
- Wallet shows a single **Coins** balance — no AUD/USDT display, no currency picker
- Coin shop via **Stripe test Checkout**; credits only after the session is retrieved and verified `paid`, matching the catalogue pack, **idempotent per session id**
- Authoritative balances in SQLite (`server/ledger.db`), keyed by an HTTP-only player cookie
- Spin outcomes and payouts computed on the server (`POST /api/spin`)
- Dark casino UI, mobile-friendly, 18+ age gate, legal footer

The house pool and 20% per-spin cap still exist **server-side only**, now measured in the same hidden game units / coin scale. `/api/pool` stays 404. Cap and max-win fields are never sent to players.

The paytable is tuned for a long-run **return to player of ~20%**. Every spin is an independent fair RNG outcome computed on the server. Game math was not changed for the social-casino conversion, so `simulate_rtp.py` does not need a re-run unless weights or settle logic are edited:

```bash
.venv/bin/python server/simulate_rtp.py
```

## Setup

```bash
cd /workspace/slot-app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional: copy `.env.example` to `.env` and fill in a **test** secret key.

```bash
cp .env.example .env
# edit .env
```

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `STRIPE_SECRET_KEY` | No | Stripe **test** secret key. Must start with `sk_test_`. If unset, the app still runs and shows: *Add a Stripe test key to enable the coin shop*. |
| `STRIPE_WEBHOOK_SECRET` | No | Webhook signing secret (`whsec_...`) from the Stripe CLI or Dashboard. When set, `POST /api/stripe/webhook` verifies signatures. |
| `PUBLIC_BASE_URL` | No | Public origin used in Checkout success/cancel URLs (default: request host, e.g. `http://localhost:8765`). |
| `PORT` | No | Listen port (default `8765`). |
| `FLASK_SECRET_KEY` | No | Flask cookie-signing secret. A random value is stored in `server/.flask_secret` if unset. |

Keys are read from the environment or from a `.env` file in this directory. **Never hardcode keys in source.**

## How to run

Stop any old static server on port 8765 first, then:

```bash
cd /workspace/slot-app
# leave STRIPE_SECRET_KEY unset to run without the shop, or export a sk_test_ key
.venv/bin/python server/app.py
```

The app listens on **http://0.0.0.0:8765/**.

Open: **http://localhost:8765/**

## Stripe test Checkout (coin shop)

1. Put a test secret key in `.env` or the environment:

   ```bash
   export STRIPE_SECRET_KEY=sk_test_...
   ```

2. Restart the server. If the value does not start with `sk_test_`, it will refuse to start.

3. In the app, click **Buy Coins**, choose a pack, and pay with the Stripe test card:

   - Card: `4242 4242 4242 4242`
   - Expiry: any future date
   - CVC: any 3 digits
   - ZIP: any value

4. After payment you land on `/shop/success`, which **retrieves the Checkout Session from Stripe** and credits the catalogue coin amount **once** (idempotent per session id). The webhook does the same if it is configured. The credited amount is the pack's coin count, never a conversion of `amount_total` into cash-out value.

### Webhooks (optional but recommended)

In another terminal, with the [Stripe CLI](https://stripe.com/docs/stripe-cli) installed and logged in:

```bash
stripe listen --forward-to localhost:8765/api/stripe/webhook
```

Copy the printed `whsec_...` value into `STRIPE_WEBHOOK_SECRET` (or `.env`) and restart the server. The endpoint handles `checkout.session.completed` and verifies the signature when the secret is set.

If `STRIPE_WEBHOOK_SECRET` is not set, the webhook returns 503. Packs still credit when the player returns to the success page.

## API

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/` | App shell |
| `GET` | `/api/balance` | Server ledger snapshot (coins, stats, bonuses; works without a Stripe key) |
| `GET` | `/api/config` | Social-casino flags, legal copy, coin packs, paytable |
| `POST` | `/api/shop/checkout` | Create a Stripe Checkout Session for a catalogue pack and return its URL |
| `GET` | `/shop/success` | Verify the session server-side and credit the pack once |
| `GET` | `/shop/cancel` | Cancelled Checkout |
| `POST` | `/api/stripe/webhook` | `checkout.session.completed` (signature verified when secret is set) |
| `POST` | `/api/bonus/daily` | Claim the free daily coin chest |
| `POST` | `/api/bonus/hourly` | Claim the free hourly coin bonus |
| `POST` | `/api/spin` | Server RNG + payout against the ledger |
| `POST` | `/api/gamble` | Red/black double-up |
| `POST` | `/api/gamble/collect` | Collect a gamble stake |

Removed (return 404): `/api/withdraw`, `/api/deposit/checkout`, `/api/deposit/play`, `/api/prefs`, `/deposit/success`, `/deposit/cancel`, `/api/pool`.

## How to play

1. Confirm you are 18 or older.
2. Play with your free starting coins, or claim the daily / hourly bonuses. Buying packs is optional.
3. Toggle **MEGAWAYS** or **25 LINES**, set the bet, and hit **SPIN** (or press Space). The server rolls the reels and pays wins in coins.
4. After a win you can **GAMBLE** (red/black) or spin again.

## Tests

```bash
.venv/bin/python server/test_cap.py
```

Coverage includes the hidden 20% cap, jackpot = cap, multi-line and Megaways evaluation, gamble, public API hiding the pool, **no withdraw route**, **idempotent coin-pack checkout credit**, **coins never converting out**, **trophy unlock**, **mission progress and claim-once**, **leaderboard ordering and nickname sanitising**, and **themes locked until level**.

## Deploy on Render

The app is a Python web service (Flask + gunicorn). A Blueprint is in `render.yaml`.

1. Push this repo to GitHub (or another Git provider Render supports) and create a new Blueprint in the [Render Dashboard](https://dashboard.render.com/), pointing at the repo root.
2. When prompted, enter a Stripe **test** secret key (`sk_test_...`) for `STRIPE_SECRET_KEY`. Live keys are rejected at startup.
3. After the first deploy, set `PUBLIC_BASE_URL` to the public origin (for example `https://slot-yqoa.onrender.com`) and redeploy so Stripe Checkout success/cancel URLs are correct. `FLASK_SECRET_KEY` is generated automatically.
4. The start command is `gunicorn server.app:app --bind 0.0.0.0:$PORT`. Render provides `PORT`; the app also honours it when you run `server/app.py` locally.

**SQLite on Render's free tier is ephemeral.** The ledger lives in `server/ledger.db` on the instance disk. Free web services have no persistent disk, so balances, spin history, and player cookies' matching rows are **wiped on every redeploy and typically lost when the instance spins down**. That is fine for this demo. For anything longer-lived, use a managed Postgres database (and a persistent session secret).

Free web services also spin down after inactivity, so the first request after a rest can be slow.

## Going live with real coin purchases

This demo stays in Stripe **test mode**. Accepting real payments for coin packs would still need, at least:

- A Stripe account approved to sell virtual currency / social-casino coins. This is often a **restricted business** category and can require a Stripe review even though coins are not redeemable for cash.
- Clear terms, 18+ enforcement, and the legal copy that coins have no monetary value and cannot be redeemed for cash or prizes.
- Confirmation that the product is a **non-redeemable social casino** in the target jurisdiction (in Australia, real-money online slots need a licence; a social casino with no cash-out is the intended legal path, but you should get legal advice before charging real money).
- Switching the secret key is **not** enough: the server will refuse `sk_live_`. Enabling live keys would be a deliberate, reviewed change after those approvals — and even then there must still be **no withdrawals or cash-out**.

## Demo caveats

- No real money moves except Stripe *test* charges, which never settle live funds.
- Coins cannot be withdrawn or converted to cash.
- The ledger lives in `server/ledger.db`. A browser cookie identifies the player. Mute / bet size still persist in `localStorage` as UI prefs only. The 18+ gate is stored in `localStorage` (`crystal-casino-age-ok-v1`).
- On Render's free tier, that SQLite file is wiped on redeploy (see above).
- Sound uses the Web Audio API; use the mute button to silence.
- This ~20% RTP is social-casino / demo math only. Licensed real-money slots are typically required to return around 85–95%.

## Files

| File | Purpose |
|------|---------|
| `index.html` | App shell, shop, age gate, footer |
| `styles.css` | Dark casino styling |
| `app.js` | UI, reel animation, API client |
| `gems.js` | Procedural gem art |
| `server/app.py` | Flask app: static files, Stripe shop, API |
| `server/ledger.py` | SQLite ledger (coins, bonuses, idempotent pack credit) |
| `server/game.py` | Symbol weights, RNG, paytables, coin scale (~20% RTP) |
| `server/simulate_rtp.py` | 1,000,000-spin RTP check |
| `server/test_cap.py` | Cap, API, shop, and social-casino tests |
| `server/templates/` | Shop success / cancel pages |
| `requirements.txt` | Python dependencies (includes gunicorn) |
| `render.yaml` | Render Blueprint for a Python web service |
| `.env.example` | Env var template |
| `README.md` | This file |

## Earlier versions (Nov 2026)

v3–v5 added 25-line Classic, Megaways, mini games, sound, and richer animation. Those game features remain. v5's client-side daily USDT play-money credit has been replaced by the server-authoritative daily and hourly **coin** bonuses. Fiat/crypto wallet display and simulated withdrawals were removed in the social-casino conversion.

Internal math (weights, paytables, 20% per-step cap, hidden house pool) is unchanged from v5. Public amounts are coins (`COIN_SCALE = 1000`).
