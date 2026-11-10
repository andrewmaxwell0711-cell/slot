#!/usr/bin/env python3
"""Fortune Reels — test-mode-only Flask backend.

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
ALLOWED_STATIC = {"index.html", "styles.css", "app.js"}
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
        "bet_steps_aud": game.BET_STEPS_AUD,
        "symbols": [
            {"id": s["id"], "emoji": s["emoji"], "pays": {str(k): v for k, v in s["pays"].items()}}
            for s in game.SYMBOLS
        ],
    }


@app.get("/")
def index():
    return send_from_directory(ROOT, "index.html")


@app.get("/styles.css")
def styles():
    return send_from_directory(ROOT, "styles.css")


@app.get("/app.js")
def app_js():
    return send_from_directory(ROOT, "app.js")


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
                            "name": f"Fortune Reels test deposit ({currency})",
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
                "app": "fortune-reels-test",
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


@app.post("/api/spin")
def api_spin():
    data = request.get_json(silent=True) or {}
    bet_index = data.get("bet_index")
    bet_aud = data.get("bet_aud")
    display_currency = str(data.get("display_currency") or "AUD").upper()
    if display_currency not in game.FIAT:
        display_currency = "AUD"

    try:
        if bet_index is not None:
            idx = int(bet_index)
            if idx < 0 or idx >= len(game.BET_STEPS_AUD):
                return _json_error("Invalid bet")
            bet = float(game.BET_STEPS_AUD[idx])
        else:
            bet = float(bet_aud)
            if bet not in game.BET_STEPS_AUD:
                return _json_error("Invalid bet")
    except (TypeError, ValueError):
        return _json_error("Invalid bet")

    grid = game.spin_grid()
    result = game.evaluate_win(grid, bet)
    try:
        snap = ledger.debit_bet_and_maybe_credit_win(
            g.player_id,
            bet,
            result["win_aud"],
            display_currency,
        )
    except ValueError as exc:
        return _json_error(str(exc))

    return jsonify(
        {
            "grid": grid,
            "bet_aud": bet,
            "win_aud": result["win_aud"],
            "count": result["count"],
            "symbol": result["symbol"],
            "mult": result["mult"],
            "line": result["line"],
            "balances": snap["balances"],
            "total_aud": snap["total_aud"],
            "stats": snap["stats"],
            "last_win_aud": snap["last_win_aud"],
            "display_currency": snap["display_currency"],
        }
    )


def main() -> None:
    mode = "Stripe test checkout enabled" if STRIPE_ENABLED else "no Stripe key — checkout disabled"
    print(f"Fortune Reels TEST MODE listening on http://0.0.0.0:{PORT}/ ({mode})")
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
