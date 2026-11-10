#!/usr/bin/env python3
"""Crystal Reels — test-mode-only Flask backend.

Serves the static demo slot and exposes a server-side ledger, spin RNG,
Stripe Checkout (sk_test_ keys only), and simulated withdrawals.
"""

from __future__ import annotations

import os
import secrets
import sys
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    g,
    jsonify,
    render_template,
    request,
    send_from_directory,
)

ROOT = Path(__file__).resolve().parent.parent
SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))

load_dotenv(ROOT / ".env")

import game  # noqa: E402
import ledger  # noqa: E402

PLAYER_COOKIE = "fr_player"
ALLOWED_STATIC = {"index.html", "styles.css", "app.js", "gems.js"}
MIN_FIAT_CENTS = 50
MAX_FIAT_CENTS = 100_000  # $1,000.00 test cap
PORT = int(os.environ.get("PORT", "8765"))


def _load_flask_secret() -> str:
    env = os.environ.get("FLASK_SECRET_KEY", "").strip()
    if env:
        return env
    path = SERVER_DIR / ".flask_secret"
    if path.exists():
        return path.read_text().strip()
    value = secrets.token_hex(32)
    path.write_text(value)
    path.chmod(0o600)
    return value


def _read_stripe_secret() -> str | None:
    raw = (os.environ.get("STRIPE_SECRET_KEY") or "").strip()
    if not raw:
        return None
    if not raw.startswith("sk_test_"):
        print(
            "Refusing to start: STRIPE_SECRET_KEY must be a Stripe test key "
            "(it must start with sk_test_). Live keys are not accepted.",
            file=sys.stderr,
        )
        sys.exit(1)
    return raw


STRIPE_SECRET_KEY = _read_stripe_secret()
STRIPE_WEBHOOK_SECRET = (os.environ.get("STRIPE_WEBHOOK_SECRET") or "").strip() or None
STRIPE_ENABLED = STRIPE_SECRET_KEY is not None

stripe = None
if STRIPE_ENABLED:
    import stripe as stripe_module

    stripe = stripe_module
    stripe.api_key = STRIPE_SECRET_KEY


app = Flask(
    __name__,
    template_folder=str(SERVER_DIR / "templates"),
    static_folder=None,
)
app.secret_key = _load_flask_secret()
ledger.init_db()


def _valid_player_id(value: str | None) -> bool:
    if not value:
        return False
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError):
        return False


@app.before_request
def ensure_player() -> None:
    # Webhooks are signed by Stripe and must not mint a player cookie.
    if request.path == "/api/stripe/webhook":
        return
    player_id = request.cookies.get(PLAYER_COOKIE)
    if not _valid_player_id(player_id):
        player_id = str(uuid.uuid4())
        g.set_player_cookie = True
    else:
        g.set_player_cookie = False
    g.player_id = player_id
    ledger.ensure_player(player_id)


@app.after_request
def set_player_cookie(response):
    if getattr(g, "set_player_cookie", False) and getattr(g, "player_id", None):
        response.set_cookie(
            PLAYER_COOKIE,
            g.player_id,
            max_age=365 * 24 * 3600,
            httponly=True,
            samesite="Lax",
            path="/",
        )
    return response


def _json_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _public_base_url() -> str:
    configured = (os.environ.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    return request.host_url.rstrip("/")


def _config_payload() -> dict:
    return {
        "stripe_enabled": STRIPE_ENABLED,
        "test_mode": True,
        "banner": None
        if STRIPE_ENABLED
        else "Add a Stripe test key to enable checkout",
        "fiat": list(game.FIAT),
        "crypto": list(game.CRYPTO),
        "rates_to_aud": game.RATES_TO_AUD,
        "line_options": game.LINE_OPTIONS,
        "bet_per_line_aud": game.BET_PER_LINE_AUD,
        "paylines": [list(p) for p in game.PAYLINES],
        "symbols": [
            {
                "id": s["id"],
                "name": s["name"],
                "emoji": s["emoji"],
                "pays": {str(k): v for k, v in s["pays"].items()},
                "wild": bool(s.get("wild")),
                "scatter": bool(s.get("scatter")),
                "blank": bool(s.get("blank")),
            }
            for s in game.SYMBOLS
        ],
        "features": {
            "wild_mult": game.WILD_MULT,
            "wild_reels": [1, 2, 3],
            "scatter_pays": {str(k): {"pay": v[0], "free_spins": v[1]} for k, v in game.SCATTER_PAYS.items()},
            "free_spin_mult": game.FREE_SPIN_MULT,
            "max_free_spins": game.MAX_FREE_SPINS,
            "gamble_max_rounds": game.GAMBLE_MAX_ROUNDS,
        },
        "modes": list(game.MODES),
        "megaways": {
            "bet_aud": game.MW_BET_AUD,
            "reels": game.MW_REELS,
            "top_reels": list(game.MW_TOP_REELS),
            "min_rows": game.MW_MIN_ROWS,
            "max_rows": game.MW_MAX_ROWS,
            "max_ways": game.MW_MAX_ROWS ** game.MW_REELS,
            "pays": {sid: {str(k): round(v * game.MW_PAY_SCALE, 4) for k, v in p.items()} for sid, p in game.MW_PAYS.items()},
            "scatter_pays": {str(k): {"pay": v[0], "free_spins": v[1]} for k, v in game.MW_SCATTER_PAYS.items()},
            "retrigger": {str(k): v for k, v in game.MW_RETRIGGER.items()},
        },
        "minigames": {
            "pick_tiles": game.PICK_TILES,
            "pick_prizes": [p for p, _ in game.PICK_PRIZES],
            "wheel_wedges": game.WHEEL_WEDGES,
            "wheel_min_scatters": game.WHEEL_MIN_SCATTERS,
        },
    }


@app.get("/")
def index():
    return send_from_directory(ROOT, "index.html")


@app.get("/styles.css")
def styles():
    return send_from_directory(ROOT, "styles.css")


@app.get("/gems.js")
def gems_js():
    return send_from_directory(ROOT, "gems.js")


@app.get("/app.js")
def app_js():
    return send_from_directory(ROOT, "app.js")


ASSETS_DIR = ROOT / "assets"


@app.get("/assets/<path:filename>")
def assets(filename: str):
    # send_from_directory rejects path traversal outside ASSETS_DIR.
    resp = send_from_directory(ASSETS_DIR, filename, max_age=7 * 24 * 3600)
    return resp


@app.get("/api/config")
def api_config():
    return jsonify(_config_payload())


@app.get("/api/balance")
def api_balance():
    snap = ledger.snapshot(g.player_id)
    snap["config"] = _config_payload()
    return jsonify(snap)


@app.post("/api/prefs")
def api_prefs():
    data = request.get_json(silent=True) or {}
    currency = str(data.get("display_currency") or "").upper()
    try:
        snap = ledger.set_display_currency(g.player_id, currency)
    except ValueError as exc:
        return _json_error(str(exc))
    return jsonify(snap)


def _parse_amount(raw) -> Decimal:
    try:
        amount = Decimal(str(raw))
    except (InvalidOperation, TypeError):
        raise ValueError("Enter a valid amount")
    if amount <= 0:
        raise ValueError("Enter a valid amount")
    return amount


@app.post("/api/deposit/checkout")
def api_deposit_checkout():
    if not STRIPE_ENABLED:
        return _json_error("Add a Stripe test key to enable checkout", 503)

    data = request.get_json(silent=True) or {}
    currency = str(data.get("currency") or data.get("asset") or "").upper()
    if currency not in game.FIAT:
        return _json_error("Fiat deposits must be AUD, USD, or EUR")

    try:
        amount = _parse_amount(data.get("amount"))
    except ValueError as exc:
        return _json_error(str(exc))

    # Stripe expects integer minor units for these currencies.
    cents = int((amount * 100).quantize(Decimal("1")))
    if amount != (Decimal(cents) / 100):
        return _json_error("Amount must have at most two decimal places")
    if cents < MIN_FIAT_CENTS:
        return _json_error("Minimum test deposit is 0.50")
    if cents > MAX_FIAT_CENTS:
        return _json_error("Maximum test deposit is 1000.00")

    base = _public_base_url()
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": currency.lower(),
                        "product_data": {
                            "name": f"Crystal Reels test deposit ({currency})",
                            "description": (
                                "TEST MODE only. Demo ledger credit — not real-money gambling."
                            ),
                        },
                        "unit_amount": cents,
                    },
                    "quantity": 1,
                }
            ],
            success_url=base + "/deposit/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=base + "/deposit/cancel",
            client_reference_id=g.player_id,
            metadata={
                "player_id": g.player_id,
                "asset": currency,
                "amount": str(Decimal(cents) / 100),
                "app": "crystal-reels-test",
            },
        )
    except Exception as exc:  # stripe.error.StripeError and network errors
        return _json_error(f"Could not start Stripe Checkout: {exc}", 502)

    return jsonify({"url": session.url, "session_id": session.id, "test_mode": True})


@app.post("/api/deposit/play")
def api_deposit_play():
    """Play-money crypto credit only. Fiat must go through Stripe test Checkout."""
    data = request.get_json(silent=True) or {}
    asset = str(data.get("asset") or data.get("currency") or "").upper()
    try:
        amount = float(_parse_amount(data.get("amount")))
        snap = ledger.credit_play_money(g.player_id, asset, amount)
    except ValueError as exc:
        return _json_error(str(exc))
    return jsonify(snap)


def _credit_from_stripe_session(session: dict) -> tuple[bool, str, dict | None]:
    session_id = session.get("id") or ""
    payment_status = session.get("payment_status")
    if payment_status != "paid":
        return False, f"Payment is not complete (status: {payment_status or 'unknown'}).", None

    metadata = session.get("metadata") or {}
    player_id = metadata.get("player_id") or session.get("client_reference_id")
    asset = (metadata.get("asset") or session.get("currency") or "").upper()
    amount_total = session.get("amount_total")
    if amount_total is None:
        return False, "Checkout session is missing an amount.", None
    amount = float(Decimal(int(amount_total)) / 100)
    if not player_id:
        return False, "Checkout session is missing a player id.", None
    if asset not in game.FIAT:
        return False, "Unsupported deposit currency.", None
    return ledger.credit_stripe_session(session_id, str(player_id), asset, amount)


@app.get("/deposit/success")
def deposit_success():
    session_id = (request.args.get("session_id") or "").strip()
    if not session_id:
        return render_template(
            "success.html",
            ok=False,
            status_label="incomplete",
            heading="Missing session",
            message="No Checkout session id was provided.",
            amount_label=None,
        )

    if not STRIPE_ENABLED:
        return render_template(
            "success.html",
            ok=False,
            status_label="unavailable",
            heading="Stripe is not configured",
            message="Add a Stripe test key to enable checkout.",
            amount_label=None,
        )

    try:
        session = stripe.checkout.Session.retrieve(session_id)
        session_dict = session.to_dict() if hasattr(session, "to_dict") else dict(session)
    except Exception as exc:
        return render_template(
            "success.html",
            ok=False,
            status_label="error",
            heading="Could not verify session",
            message=str(exc),
            amount_label=None,
        ), 400

    try:
        credited, message, snap = _credit_from_stripe_session(session_dict)
    except ValueError as exc:
        return render_template(
            "success.html",
            ok=False,
            status_label="error",
            heading="Deposit not credited",
            message=str(exc),
            amount_label=None,
        ), 400

    processed = ledger.get_processed_session(session_id)
    amount_label = None
    if processed:
        amount_label = f"{processed['amount']:.2f} {processed['asset']}"
        if credited:
            heading = "Test deposit credited"
            detail = "Your server-side ledger has been credited once for this Checkout session."
        else:
            heading = "Already credited"
            detail = "This Checkout session was already applied to the ledger (idempotent)."
    else:
        heading = "Deposit not credited"
        detail = message
        credited = False

    return render_template(
        "success.html",
        ok=bool(processed),
        status_label="credited" if processed else "incomplete",
        heading=heading,
        message=detail,
        amount_label=amount_label,
    )


@app.get("/deposit/cancel")
def deposit_cancel():
    return render_template("cancel.html")


@app.post("/api/stripe/webhook")
def stripe_webhook():
    payload = request.get_data()
    if not STRIPE_ENABLED:
        return _json_error("Add a Stripe test key to enable checkout", 503)
    if not STRIPE_WEBHOOK_SECRET:
        return _json_error(
            "STRIPE_WEBHOOK_SECRET is not set. Run: stripe listen --forward-to "
            f"localhost:{PORT}/api/stripe/webhook",
            503,
        )

    sig = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception as exc:
        return _json_error(f"Webhook signature verification failed: {exc}", 400)

    event_type = event.get("type") if isinstance(event, dict) else event["type"]
    obj = event["data"]["object"] if isinstance(event, dict) else event.data.object
    if hasattr(obj, "to_dict"):
        obj = obj.to_dict()
    elif not isinstance(obj, dict):
        obj = dict(obj)

    if event_type == "checkout.session.completed":
        try:
            credited, message, _snap = _credit_from_stripe_session(obj)
        except ValueError as exc:
            # Don't retry permanently invalid sessions.
            return jsonify({"received": True, "credited": False, "error": str(exc)}), 200
        return jsonify({"received": True, "credited": credited, "message": message})

    return jsonify({"received": True, "ignored": event_type})


@app.post("/api/withdraw")
def api_withdraw():
    data = request.get_json(silent=True) or {}
    asset = str(data.get("asset") or data.get("currency") or "").upper()
    try:
        amount = float(_parse_amount(data.get("amount")))
        snap = ledger.withdraw(g.player_id, asset, amount)
    except ValueError as exc:
        return _json_error(str(exc))
    return jsonify(snap)


def _spin_payload(step: dict, settled: dict) -> dict:
    """Allow-listed player-facing fields only: never pool size, cap or max-win."""
    out = {
        "kind": step.get("kind", "spin"),
        "raw_win_aud": settled["raw_win_aud"],
        "win_aud": settled["paid_aud"],
        "jackpot_aud": settled["jackpot_aud"],
        "limited": settled["capped"],
    }
    kind = out["kind"]
    if kind == "pick":
        out.update(picks=step["picks"], decoys=step["decoys"], tiles=step["tiles"])
    elif kind == "wheel":
        idx = settled.get("wheel_index", step["index"])
        jackpot = bool(settled.get("wheel_jackpot"))
        out.update(
            wedges=step["wedges"], index=idx, jackpot=jackpot,
            near_miss=bool(step.get("jackpot_pending")) and not jackpot,
            prize_mult=0 if jackpot else game.WHEEL_WEDGES[idx].get("value", 0) if game.WHEEL_WEDGES[idx]["type"] == "mult" else 0,
            free_spins=step.get("free_spins", 0),
        )
    elif step.get("mode") == "megaways":
        out.update(
            mode="megaways", stages=step["stages"], ways=step["ways"], cascades=step["cascades"],
            scatters=step["scatters"], scatter_pos=step["scatter_pos"], scatter_win_aud=step["scatter_win_aud"],
            free_spins_awarded=step["free_spins_awarded"], multiplier=step["multiplier"],
            multiplier_end=step["multiplier_end"],
        )
    else:
        out.update(
            mode="classic", grid=step["grid"], line_wins=step["line_wins"], scatters=step["scatters"],
            scatter_pos=step["scatter_pos"], scatter_win_aud=step["scatter_win_aud"],
            free_spins_awarded=step["free_spins_awarded"], multiplier=step["multiplier"],
        )
    return out


@app.post("/api/spin")
def api_spin():
    data = request.get_json(silent=True) or {}
    display_currency = str(data.get("display_currency") or "AUD").upper()
    if display_currency not in game.FIAT:
        display_currency = "AUD"
    mode = str(data.get("mode") or "classic").lower()
    if mode not in game.MODES:
        return _json_error("Invalid mode")
    try:
        if mode == "megaways":
            bet_index = int(data.get("bet_index", 0))
            if not 0 <= bet_index < len(game.MW_BET_AUD):
                return _json_error("Invalid bet")
            total_bet = round(float(game.MW_BET_AUD[bet_index]), 2)
            lines, bpl = None, None
        else:
            lines = int(data.get("lines", 25))
            bpl_index = int(data.get("bet_per_line_index", 0))
            if lines not in game.LINE_OPTIONS or not 0 <= bpl_index < len(game.BET_PER_LINE_AUD):
                return _json_error("Invalid bet")
            bpl = float(game.BET_PER_LINE_AUD[bpl_index])
            total_bet = round(bpl * lines, 2)
    except (TypeError, ValueError):
        return _json_error("Invalid bet")

    rnd = game.play_megaways(total_bet) if mode == "megaways" else game.play_classic(bpl, lines)
    try:
        snap = ledger.settle_round(g.player_id, total_bet, rnd, display_currency)
    except ValueError as exc:
        return _json_error(str(exc))

    steps = game.round_steps(rnd)
    payload = [_spin_payload(st, se) for st, se in zip(steps, snap["steps"])]
    n_games = len(rnd.get("minigames") or [])
    return jsonify(
        {
            "mode": mode,
            "lines": lines,
            "bet_per_line_aud": bpl,
            "bet_aud": total_bet,
            "base": payload[0],
            "minigames": payload[1:1 + n_games],
            "free_spins": payload[1 + n_games:],
            "jackpot_hit": snap["jackpot_hit"],
            "jackpot_paid_aud": snap["jackpot_paid_aud"],
            "win_aud": snap["total_paid_aud"],
            "limited": snap["any_capped"],
            "gamble_aud": snap["gamble_aud"],
            "balances": snap["balances"],
            "total_aud": snap["total_aud"],
            "stats": snap["stats"],
            "last_win_aud": snap["last_win_aud"],
            "display_currency": snap["display_currency"],
        }
    )


@app.post("/api/gamble")
def api_gamble():
    data = request.get_json(silent=True) or {}
    choice = str(data.get("choice") or "").lower()
    try:
        snap = ledger.gamble(g.player_id, choice, game.draw_card)
    except ledger.GambleUnavailable as exc:
        out = ledger.snapshot(g.player_id)
        out["error"] = str(exc)
        out["gamble_closed"] = True
        return jsonify(out), 409
    except ValueError as exc:
        return _json_error(str(exc))
    return jsonify(snap)


@app.post("/api/gamble/collect")
def api_gamble_collect():
    return jsonify(ledger.gamble_collect(g.player_id))


def main() -> None:
    mode = "Stripe test checkout enabled" if STRIPE_ENABLED else "no Stripe key — checkout disabled"
    print(f"Crystal Reels TEST MODE listening on http://0.0.0.0:{PORT}/ ({mode})")
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
