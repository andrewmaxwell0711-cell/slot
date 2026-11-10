# Crystal Casino · Crystal Reels — Demo Slot Machine (TEST MODE)

A 5-reel demo slot with a **server-side ledger**, **server-side RNG**, and optional **Stripe Checkout in test mode** for fiat deposits (AUD, USD, EUR).

This is **not** real-money gambling.

- **TEST MODE only.** The server refuses to start if `STRIPE_SECRET_KEY` is set and does not begin with `sk_test_`. Live keys are never accepted.
- **Withdrawals are simulated.** The ledger is debited and marked `test withdrawal recorded`. There are no Stripe Connect accounts, payouts, or transfers.
- **Crypto deposits are play money only.** They never touch a chain or a payment processor.
- Real-money play would need a **gambling licence plus Stripe approval**. Stripe prohibits unlicensed gambling, and real-money online gambling is illegal in Australia without a licence.

## Features

- 5-reel slot with spin animation, center payline wins, and optional sound
- Wallet with:
  - Fiat deposits via **Stripe test Checkout** (AUD, USD, EUR)
  - Play-money crypto credits (BTC, ETH, USDT, SOL)
  - Simulated withdrawals
- Authoritative balances in SQLite (`server/ledger.db`), keyed by an HTTP-only player cookie
- Spin outcomes and payouts computed on the server (`POST /api/spin`) so the client cannot fake wins
- Dark casino UI — mobile-friendly

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
| `STRIPE_SECRET_KEY` | No | Stripe **test** secret key. Must start with `sk_test_`. If unset, the app still runs and shows: *Add a Stripe test key to enable checkout*. |
| `STRIPE_WEBHOOK_SECRET` | No | Webhook signing secret (`whsec_...`) from the Stripe CLI or Dashboard. When set, `POST /api/stripe/webhook` verifies signatures. |
| `PUBLIC_BASE_URL` | No | Public origin used in Checkout success/cancel URLs (default: request host, e.g. `http://localhost:8765`). |
| `PORT` | No | Listen port (default `8765`). |
| `FLASK_SECRET_KEY` | No | Flask cookie-signing secret. A random value is stored in `server/.flask_secret` if unset. |

Keys are read from the environment or from a `.env` file in this directory. **Never hardcode keys in source.**

## How to run

Stop any old static server on port 8765 first, then:

```bash
cd /workspace/slot-app
# leave STRIPE_SECRET_KEY unset to run without checkout, or export a sk_test_ key
.venv/bin/python server/app.py
```

The app listens on **http://0.0.0.0:8765/**.

Open: **http://localhost:8765/**

## Stripe test Checkout

1. Put a test secret key in `.env` or the environment:

   ```bash
   export STRIPE_SECRET_KEY=sk_test_...
   ```

2. Restart the server. If the value does not start with `sk_test_`, it will refuse to start.

3. In the app, click **Deposit**, choose a fiat currency, enter an amount (minimum 0.50), and click **Pay with Stripe (test mode)**.

4. Pay with the Stripe test card:

   - Card: `4242 4242 4242 4242`
   - Expiry: any future date
   - CVC: any 3 digits
   - ZIP: any value

5. After payment you land on `/deposit/success`, which **retrieves the Checkout Session from Stripe** and credits the ledger **once** (idempotent per session id). The webhook does the same if it is configured.

### Webhooks (optional but recommended)

In another terminal, with the [Stripe CLI](https://stripe.com/docs/stripe-cli) installed and logged in:

```bash
stripe listen --forward-to localhost:8765/api/stripe/webhook
```

Copy the printed `whsec_...` value into `STRIPE_WEBHOOK_SECRET` (or `.env`) and restart the server. The endpoint handles `checkout.session.completed` and verifies the signature when the secret is set.

If `STRIPE_WEBHOOK_SECRET` is not set, the webhook returns 503. Deposits still credit when the player returns to the success page.

## API

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/` | App shell |
| `GET` | `/api/balance` | Server ledger snapshot (works without a Stripe key) |
| `GET` | `/api/config` | Test-mode flags, rates, paytable |
| `POST` | `/api/deposit/checkout` | Create a Stripe Checkout Session (`mode=payment`) and return its URL |
| `GET` | `/deposit/success` | Verify the session server-side and credit once |
| `GET` | `/deposit/cancel` | Cancelled Checkout |
| `POST` | `/api/stripe/webhook` | `checkout.session.completed` (signature verified when secret is set) |
| `POST` | `/api/deposit/play` | Play-money crypto credit only |
| `POST` | `/api/withdraw` | Simulated test withdrawal |
| `POST` | `/api/spin` | Server RNG + payout against the ledger |
| `POST` | `/api/prefs` | Display currency |

## How to play

1. Deposit fiat via Stripe test Checkout, or add play-money crypto.
2. Adjust **Bet** with − / +.
3. Hit **SPIN** (or press Space). The server rolls the reels and pays wins.
4. Match **3+ identical symbols** on the center payline (payout = multiplier × bet).
5. Click **Withdraw** to debit the test ledger (status: **test withdrawal recorded**).

The paytable is tuned for a long-run **return to player of 20%** (about 10,000 paid back for every 50,000 wagered). Every spin is an independent fair RNG outcome computed on the server — there is no per-player rigging. Confirm with:

```bash
.venv/bin/python server/simulate_rtp.py
```

## Deploy on Render

The app is a Python web service (Flask + gunicorn). A Blueprint is in `render.yaml`.

1. Push this repo to GitHub (or another Git provider Render supports) and create a new Blueprint in the [Render Dashboard](https://dashboard.render.com/), pointing at the repo root.
2. When prompted, enter a Stripe **test** secret key (`sk_test_...`) for `STRIPE_SECRET_KEY`. Live keys are rejected at startup.
3. After the first deploy, set `PUBLIC_BASE_URL` to the public origin (for example `https://fortune-reels.onrender.com`) and redeploy so Stripe Checkout success/cancel URLs are correct. `FLASK_SECRET_KEY` is generated automatically.
4. The start command is `gunicorn server.app:app --bind 0.0.0.0:$PORT`. Render provides `PORT`; the app also honours it when you run `server/app.py` locally.

**SQLite on Render's free tier is ephemeral.** The ledger lives in `server/ledger.db` on the instance disk. Free web services have no persistent disk, so balances, spin history, and player cookies' matching rows are **wiped on every redeploy and typically lost when the instance spins down**. That is fine for this demo. For anything longer-lived, use a managed Postgres database (and a persistent session secret).

Free web services also spin down after inactivity, so the first request after a rest can be slow.

## Demo caveats

- No real money moves except Stripe *test* charges, which never settle live funds.
- Withdrawals never leave this app.
- Bets debit wallet balances (fiat first, then crypto) by AUD-equivalent value.
- Wins credit into the selected **display currency**.
- The ledger lives in `server/ledger.db`. A browser cookie (`fr_player`) identifies the player. Mute / bet size still persist in `localStorage` as UI prefs only.
- On Render's free tier, that SQLite file is wiped on redeploy (see above).
- Sound uses the Web Audio API; use the mute button to silence.
- This 20% RTP is demo math only. Licensed real-money slots are typically required to return around 85–95%.

## Files

| File | Purpose |
|------|---------|
| `index.html` | App shell & modals |
| `styles.css` | Dark casino styling |
| `app.js` | UI, reel animation, API client |
| `server/app.py` | Flask app: static files, Stripe, API |
| `server/ledger.py` | SQLite ledger |
| `server/game.py` | Symbol weights, RNG, payline (20% RTP) |
| `server/simulate_rtp.py` | 1,000,000-spin RTP check |
| `server/templates/` | Checkout success / cancel pages |
| `requirements.txt` | Python dependencies (includes gunicorn) |
| `render.yaml` | Render Blueprint for a Python web service |
| `.env.example` | Env var template |
| `README.md` | This file |


## Crystal Casino v3 (Nov 2026)

- 5×3 reels, **25 paylines** (standard patterns incl. V, ^ and zigzags). Choose 1/5/10/20/25 lines and
  bet per line A$0.02–A$4; total bet = lines × bet per line (max A$100). Wins pay left to right on active
  lines; winning lines are drawn over the reels with numbered line badges on both edges.
- Symbols (pays × bet per line for 3/4/5): Green Tea 50/150/500 (top symbol, packet art in `assets/`),
  Ruby 25/80/200, Sapphire 15/50/100, Emerald 10/30/80, Amethyst 6/16/50, Topaz 6/16/40,
  Citrine 4/10/20, Rose Quartz 4/10/20. Crystal Wild (reels 2–4) substitutes and doubles line wins;
  Prism Scatter 3/4/5 anywhere pays 2/5/20× total bet + 8/12/20 free spins at ×2. Ice Shard is non-paying.
  Gem art is procedural faceted SVG (`gems.js`).
- **Green Tea Jackpot** pays the table maximum: the spin's total win becomes exactly 20% of the house pool.
  Hit chance = 0.20 × total bet / pool (max 1/1000), so expected jackpot return is a fixed 4% of stakes.
- **Gamble / double-up**: after a win, pick red/black (server-drawn card, 50/50), up to 5 times. A double
  is refused (auto-collect) if 2× the stake would exceed 20% of the pool.
- **House pool and cap** (server only): pool = all stakes − all payouts (SQLite `house` table). Every
  spin's total (lines + scatter + jackpot, and each free spin) is clamped to 20% of the pool; pool never
  negative. Pool, cap and max-win are **not** exposed to players (no `/api/pool`; not in any response).
- Auto spin (10/25/50/100/∞ with stop on bonus / big win / balance below X), turbo, MAX BET, info screen
  (paytable, paylines, features), spin history, win roll-up, anticipation, celebrations, Web Audio.
- `python server/test_cap.py` (cap, jackpot = cap, multi-line evaluation, gamble, API hides pool) and
  `python server/simulate_rtp.py [spins] [lines] [start_pool]` (expected total RTP ~19.9%).
- On Render's free plan SQLite resets on each deploy: the pool restarts at 0, so early wins and jackpots
  are small until players have bet.
