#!/usr/bin/env python3
"""Crystal Casino — social casino, test-mode-only Flask backend.

Virtual coins, a Stripe test-mode coin shop, free starting/daily/hourly
coins, and a server-side slot RNG. Coins have no cash value and cannot be
withdrawn, redeemed or exchanged for money or prizes. Live Stripe keys
(sk_live_) are refused.
"""

from __future__ import annotations

import gzip
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

import auth  # noqa: E402
import db as dbmod  # noqa: E402
import game  # noqa: E402
import ledger  # noqa: E402
import prizes  # noqa: E402
import errors  # noqa: E402
import legal  # noqa: E402
import prefs  # noqa: E402

PLAYER_COOKIE = "fr_player"
ALLOWED_STATIC = {"index.html", "styles.css", "fx.css", "app.js", "gems.js", "lobby.js", "casino.js", "errors.js", "settings.js", "fx.js"}
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
errors.init_sentry(app)
ledger.init_db()
print(f"Crystal Casino ledger: {dbmod.backend_name(ledger.DB_PATH)}", file=sys.stderr)


def _valid_player_id(value: str | None) -> bool:
    if not value:
        return False
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError):
        return False


def _cookie_secure() -> bool:
    xf = (request.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
    return xf == "https" or bool(request.is_secure)


def _cookie_kwargs(max_age: int, httponly: bool) -> dict:
    kw = {
        "max_age": max_age,
        "httponly": httponly,
        "samesite": "Lax",
        "path": "/",
    }
    if _cookie_secure():
        kw["secure"] = True
    return kw


def _mint_guest() -> str:
    guest_id = str(uuid.uuid4())
    g.guest_id = guest_id
    g.set_player_cookie = True
    ledger.ensure_player(guest_id)
    return guest_id


@app.before_request
def ensure_player() -> None:
    # Webhooks are signed by Stripe and must not mint a player cookie.
    if request.path == "/api/stripe/webhook":
        return
    g.account = None
    g.csrf_token = None
    g.set_session_cookie = None
    g.clear_session_cookie = False
    guest = request.cookies.get(PLAYER_COOKIE)
    if not _valid_player_id(guest):
        guest = _mint_guest()
    else:
        g.guest_id = guest
        g.set_player_cookie = False
        ledger.ensure_player(guest)
    sess = auth.load_session(request.cookies.get(auth.SESSION_COOKIE))
    if sess:
        g.account = sess["account"]
        g.player_id = sess["player_id"]
        g.csrf_token = sess["csrf_token"]
        ledger.ensure_player(g.player_id)
    else:
        g.player_id = g.guest_id
        # already ensured above


_GZIP_TYPES = (
    "text/",
    "javascript",
    "json",
    "xml",
    "svg+xml",
    "manifest",
    "x-javascript",
)


@app.after_request
def gzip_response(response):
    """Compress text responses when the client accepts gzip."""
    if response.status_code < 200 or response.status_code >= 300:
        return response
    if "gzip" not in (request.headers.get("Accept-Encoding") or "").lower():
        return response
    if response.headers.get("Content-Encoding"):
        return response
    mime = (response.mimetype or "").lower()
    if not any(token in mime for token in _GZIP_TYPES):
        return response
    try:
        if response.direct_passthrough:
            response.direct_passthrough = False
        data = response.get_data()
    except Exception:
        return response
    if not data or len(data) < 400:
        return response
    compressed = gzip.compress(data, compresslevel=5)
    if len(compressed) >= len(data):
        return response
    response.set_data(compressed)
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Length"] = str(len(compressed))
    vary = response.headers.get("Vary", "")
    if "Accept-Encoding" not in vary:
        response.headers["Vary"] = (vary + ", Accept-Encoding").lstrip(", ").strip()
    return response


@app.after_request
def set_player_cookie(response):
    if getattr(g, "set_player_cookie", False) and getattr(g, "guest_id", None):
        response.set_cookie(
            PLAYER_COOKIE,
            g.guest_id,
            **_cookie_kwargs(365 * 24 * 3600, True),
        )
    sess = getattr(g, "set_session_cookie", None)
    if sess:
        age = auth.SESSION_DAYS * 24 * 3600
        response.set_cookie(auth.SESSION_COOKIE, sess["token"], **_cookie_kwargs(age, True))
        response.set_cookie(auth.CSRF_COOKIE, sess["csrf_token"], **_cookie_kwargs(age, False))
    if getattr(g, "clear_session_cookie", False):
        response.delete_cookie(auth.SESSION_COOKIE, path="/")
        response.delete_cookie(auth.CSRF_COOKIE, path="/")
    return response


def _require_signed_in_csrf():
    if not getattr(g, "account", None):
        return _json_error("Sign in required", 401)
    provided = request.headers.get("X-CSRF-Token")
    if provided is None:
        provided = (request.get_json(silent=True) or {}).get("csrf")
    if not auth.csrf_ok(getattr(g, "csrf_token", None), provided):
        return _json_error("Invalid or missing CSRF token", 403)
    return None


def _become_fresh_guest() -> None:
    g.account = None
    g.csrf_token = None
    g.player_id = _mint_guest()


def _json_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _public_base_url() -> str:
    configured = (os.environ.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    return request.host_url.rstrip("/")


def _config_payload() -> dict:
    payload = {
        "stripe_enabled": STRIPE_ENABLED,
        "test_mode": True,
        "social_casino": True,
        "banner": None
        if STRIPE_ENABLED
        else "Add a Stripe test key to enable the coin shop",
        "legal": game.LEGAL_COINS,
        "responsible_play": game.RESPONSIBLE_PLAY,
        "coin_scale": game.COIN_SCALE,
        "starting_coins": game.STARTING_COINS,
        "jackpot_mult": game.JACKPOT_MULT,
        "prizes": prizes.catalogue(),
        "prize_legal": prizes.PRIZE_LEGAL,
        "google_client_id": auth.google_client_id() or None,
        "google_enabled": auth.google_enabled(),
        "privacy": auth.PRIVACY_NOTE,
        "packs": [
            {
                "id": p["id"],
                "label": p["label"],
                "price": p["price_aud"],
                "price_cents": p["price_cents"],
                "currency": "AUD",
                "coins": p["coins"],
                "tag": p["tag"],
            }
            for p in game.COIN_PACKS
        ],
        "line_options": game.LINE_OPTIONS,
        "bet_per_line": [game.to_coins(x) for x in game.BET_PER_LINE_AUD],
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
            "bet": [game.to_coins(x) for x in game.MW_BET_AUD],
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
            "wheel_angles": game.wheel_wedge_angles(),
        },
        "hold_spin": {
            "trigger": game.HOLD_TRIGGER,
            "cells": game.HOLD_CELLS,
            "cols": game.HOLD_COLS,
            "rows": game.HOLD_ROWS,
            "respins": game.HOLD_RESPINS,
            "grand_mult": game.HOLD_GRAND_MULT,
        },
        "collection": {
            "types": list(game.COLLECT_TYPES),
            "set_size": game.COLLECT_SET,
            "pay_mult": game.COLLECT_PAY_MULT,
        },
        "surprise_wilds": True,
        "progressive": ledger.progressive_public(),
        "side": __import__("side").catalogue(),
        "slot_themes": __import__("themes").catalogue(),
        "simulated_gambling": game.SIMULATED_GAMBLING,
        "age_limit": game.AGE_LIMIT,
        "disclosure": legal.disclosure_block(),
        "privacy_url": legal.PRIVACY_URL,
        "terms_url": legal.TERMS_URL,
        "sentry_dsn": errors.sentry_public_dsn() or None,
    }

    try:
        import baccarat as _bac
        _conn = ledger.get_conn()
        _bac.ensure_schema(_conn)
        payload.setdefault("side", {}).setdefault("baccarat", {})["road"] = _bac.load_road(_conn)
        _conn.commit()
    except Exception:
        pass
    return payload


@app.get("/")
def index():
    return send_from_directory(ROOT, "index.html")


@app.get("/privacy")
def privacy_page():
    return render_template(
        "legal.html",
        title="Privacy Policy",
        description="Crystal Casino privacy policy. Social casino, 18+, coins have no cash value.",
        body=legal.privacy_html(),
        notice=game.SIMULATED_GAMBLING,
    )


@app.get("/terms")
def terms_page():
    return render_template(
        "legal.html",
        title="Terms of Use",
        description="Crystal Casino terms of use. Social casino, 18+, coins have no cash value.",
        body=legal.terms_html(),
        notice=game.SIMULATED_GAMBLING,
    )


@app.get("/styles.css")
def styles():
    return send_from_directory(ROOT, "styles.css")


@app.get("/gems.js")
def gems_js():
    return send_from_directory(ROOT, "gems.js")


@app.get("/app.js")
def app_js():
    return send_from_directory(ROOT, "app.js")


@app.get("/errors.js")
def errors_js():
    return send_from_directory(ROOT, "errors.js")


@app.get("/lobby.js")
def lobby_js():
    return send_from_directory(ROOT, "lobby.js")


@app.get("/casino.js")
def casino_js():
    return send_from_directory(ROOT, "casino.js")


@app.get("/settings.js")
def settings_js():
    return send_from_directory(ROOT, "settings.js")


@app.get("/fx.js")
def fx_js():
    return send_from_directory(ROOT, "fx.js")


@app.get("/fx.css")
def fx_css():
    return send_from_directory(ROOT, "fx.css")


@app.get("/manifest.webmanifest")
def manifest():
    return send_from_directory(ROOT, "manifest.webmanifest", max_age=24 * 3600, mimetype="application/manifest+json")


ASSETS_DIR = ROOT / "assets"


@app.get("/assets/<path:filename>")
def assets(filename: str):
    # send_from_directory rejects path traversal outside ASSETS_DIR.
    resp = send_from_directory(ASSETS_DIR, filename, max_age=7 * 24 * 3600)
    return resp



def _public_snap(snap: dict, include_config: bool = False) -> dict:
    """Player-facing ledger view: coins only, no pool or cash-out fields."""
    out = {
        "coins": snap["coins"],
        "stats": snap["stats"],
        "last_win": snap["last_win"],
        "gamble": snap["gamble"],
        "bonuses": snap["bonuses"],
    }
    for key in ("profile", "trophies", "missions", "themes", "prize_legal", "level_up",
                "progressive", "progressive_hit", "progressive_paid", "collection", "weekend"):
        if key in snap:
            out[key] = snap[key]
    if include_config:
        out["config"] = _config_payload()
    if "awarded" in snap:
        out["awarded"] = snap["awarded"]
        out["bonus"] = snap.get("bonus")
    if request.path != "/api/stripe/webhook":
        out["account"] = auth.account_public(
            getattr(g, "account", None),
            guest_id=getattr(g, "guest_id", None),
        )
    return out


@app.get("/api/auth/me")
def api_auth_me():
    return jsonify(_public_snap(ledger.snapshot(g.player_id), include_config=True))


@app.post("/api/auth/google")
def api_auth_google():
    if not auth.google_enabled():
        return _json_error("Google sign-in is not configured", 503)
    data = request.get_json(silent=True) or {}
    credential = data.get("credential") or data.get("id_token") or ""
    try:
        profile = auth.verify_google_token(credential)
    except ValueError as exc:
        return _json_error(str(exc), 401)
    except Exception:
        return _json_error("Could not verify Google sign-in", 401)
    guest_id = getattr(g, "guest_id", None) or g.player_id
    account = auth.upsert_account_from_google(profile, guest_id)
    session = auth.create_session(account["id"])
    g.account = account
    g.player_id = account["player_id"]
    g.csrf_token = session["csrf_token"]
    g.set_session_cookie = session
    return jsonify(_public_snap(ledger.snapshot(g.player_id), include_config=True))


@app.post("/api/auth/logout")
def api_auth_logout():
    err = _require_signed_in_csrf()
    if err:
        return err
    auth.revoke_session(request.cookies.get(auth.SESSION_COOKIE))
    g.clear_session_cookie = True
    _become_fresh_guest()
    return jsonify(_public_snap(ledger.snapshot(g.player_id), include_config=True))


@app.post("/api/auth/merge")
def api_auth_merge():
    err = _require_signed_in_csrf()
    if err:
        return err
    guest_id = getattr(g, "guest_id", None)
    try:
        account = auth.merge_guest(g.account["id"], guest_id)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    g.account = account
    g.player_id = account["player_id"]
    # Replace the merged guest cookie so it cannot be merged again.
    g.guest_id = str(uuid.uuid4())
    g.set_player_cookie = True
    ledger.ensure_player(g.guest_id)
    return jsonify(_public_snap(ledger.snapshot(g.player_id), include_config=True))


@app.post("/api/auth/delete")
def api_auth_delete():
    err = _require_signed_in_csrf()
    if err:
        return err
    try:
        auth.delete_account(g.account["id"])
    except ValueError as exc:
        return _json_error(str(exc), 400)
    g.clear_session_cookie = True
    _become_fresh_guest()
    return jsonify(_public_snap(ledger.snapshot(g.player_id), include_config=True))


@app.get("/api/prefs")
def api_prefs_get():
    with ledger.transaction() as conn:
        prefs.ensure_schema(conn)
        state = prefs.get_tutorial(conn, g.player_id)
    return jsonify({"tutorial": state})


@app.post("/api/prefs")
def api_prefs_set():
    data = request.get_json(silent=True) or {}
    tut = data.get("tutorial") if isinstance(data.get("tutorial"), dict) else data
    with ledger.transaction() as conn:
        ledger.lock_player(conn, g.player_id)
        prefs.ensure_schema(conn)
        state = prefs.set_tutorial(conn, g.player_id, tut or {})
    return jsonify({"tutorial": state})


@app.post("/api/errors")
def api_client_errors():
    raw = request.get_data(cache=True) or b""
    if len(raw) > errors.MAX_BODY:
        return _json_error("Report too large", 413)
    data = request.get_json(silent=True) or {}
    ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "unknown").split(",")[0].strip()
    player = getattr(g, "player_id", "") or "anon"
    if not errors.allow_report(f"ip:{ip}") or not errors.allow_report(f"p:{player}", limit=20):
        return _json_error("Too many reports", 429)
    errors.record_client_error(data if isinstance(data, dict) else {}, source=ip)
    return jsonify({"ok": True})


@app.get("/api/config")
def api_config():
    return jsonify(_config_payload())


@app.get("/api/balance")
def api_balance():
    return jsonify(_public_snap(ledger.snapshot(g.player_id), include_config=True))


@app.post("/api/shop/checkout")
def api_shop_checkout():
    if not STRIPE_ENABLED:
        return _json_error("Add a Stripe test key to enable the coin shop", 503)
    data = request.get_json(silent=True) or {}
    pack = game.pack_by_id(str(data.get("pack_id") or ""))
    if not pack:
        return _json_error("Unknown coin pack")
    base = _public_base_url()
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": "aud",
                        "product_data": {
                            "name": f"Crystal Casino — {pack['coins']:,} Coins ({pack['label']})",
                            "description": (
                                f"{game.LEGAL_COINS} TEST MODE only. Not real-money gambling."
                            ),
                        },
                        "unit_amount": pack["price_cents"],
                    },
                    "quantity": 1,
                }
            ],
            success_url=base + "/shop/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=base + "/shop/cancel",
            client_reference_id=g.player_id,
            metadata={
                "player_id": g.player_id,
                "pack_id": pack["id"],
                "coins": str(pack["coins"]),
                "price_cents": str(pack["price_cents"]),
                "app": "crystal-casino-social",
            },
        )
    except Exception as exc:
        return _json_error(f"Could not start Stripe Checkout: {exc}", 502)
    return jsonify({"url": session.url, "session_id": session.id, "test_mode": True, "pack_id": pack["id"]})


def _credit_from_stripe_session(session: dict) -> tuple[bool, str, dict | None]:
    session_id = session.get("id") or ""
    payment_status = session.get("payment_status")
    if payment_status != "paid":
        return False, f"Payment is not complete (status: {payment_status or 'unknown'}).", None

    metadata = session.get("metadata") or {}
    player_id = metadata.get("player_id") or session.get("client_reference_id")
    pack_id = metadata.get("pack_id") or ""
    pack = game.pack_by_id(str(pack_id))
    if not pack:
        return False, "Checkout session is missing a valid coin pack.", None
    if not player_id:
        return False, "Checkout session is missing a player id.", None

    amount_total = session.get("amount_total")
    currency = (session.get("currency") or "").lower()
    if amount_total is None:
        return False, "Checkout session is missing an amount.", None
    if currency != "aud" or int(amount_total) != int(pack["price_cents"]):
        return False, "Checkout session does not match the coin pack price.", None
    return ledger.credit_coin_pack(
        session_id, str(player_id), pack["id"], pack["coins"], pack["price_aud"]
    )


@app.get("/shop/success")
def shop_success():
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
            message="Add a Stripe test key to enable the coin shop.",
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
            heading="Coins not credited",
            message=str(exc),
            amount_label=None,
        ), 400

    processed = ledger.get_processed_session(session_id)
    amount_label = None
    if processed:
        amount_label = f"{int(processed['amount']):,} coins"
        if credited:
            heading = "Coins added to your account"
            detail = (
                "Your coin pack has been credited once for this Checkout session. "
                + game.LEGAL_COINS
            )
        else:
            heading = "Already credited"
            detail = (
                "This Checkout session was already applied to your coin balance (idempotent). "
                + game.LEGAL_COINS
            )
    else:
        heading = "Coins not credited"
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


@app.get("/shop/cancel")
def shop_cancel():
    return render_template("cancel.html")


@app.post("/api/bonus/daily")
def api_bonus_daily():
    try:
        snap = ledger.claim_daily(g.player_id)
    except ledger.BonusUnavailable as exc:
        out = _public_snap(ledger.snapshot(g.player_id))
        out["error"] = str(exc)
        return jsonify(out), 429
    except ValueError as exc:
        return _json_error(str(exc))
    return jsonify(_public_snap(snap))


@app.post("/api/bonus/hourly")
def api_bonus_hourly():
    try:
        snap = ledger.claim_hourly(g.player_id)
    except ledger.BonusUnavailable as exc:
        out = _public_snap(ledger.snapshot(g.player_id))
        out["error"] = str(exc)
        out["hourly_seconds"] = getattr(exc, "seconds", 0)
        return jsonify(out), 429
    except ValueError as exc:
        return _json_error(str(exc))
    return jsonify(_public_snap(snap))



@app.post("/api/profile")
def api_profile():
    data = request.get_json(silent=True) or {}
    try:
        snap = prizes.set_nickname(g.player_id, str(data.get("nickname") or ""))
    except ValueError as exc:
        return _json_error(str(exc))
    return jsonify(_public_snap(snap))


@app.post("/api/theme")
def api_theme():
    data = request.get_json(silent=True) or {}
    try:
        snap = prizes.set_theme(g.player_id, str(data.get("theme") or ""))
    except prizes.ThemeLocked as exc:
        return _json_error(str(exc), 403)
    except ValueError as exc:
        return _json_error(str(exc))
    return jsonify(_public_snap(snap))


@app.get("/api/leaderboard")
def api_leaderboard():
    period = str(request.args.get("period") or "daily").lower()
    board = str(request.args.get("board") or "biggest").lower()
    try:
        prizes.settle_due_periods()
        data = prizes.leaderboard(period, board, viewer_id=g.player_id)
    except ValueError as exc:
        return _json_error(str(exc))
    return jsonify(data)


@app.post("/api/missions/claim")
def api_missions_claim():
    data = request.get_json(silent=True) or {}
    try:
        snap = prizes.claim_mission(g.player_id, str(data.get("mission_id") or ""))
    except prizes.MissionUnavailable as exc:
        out = _public_snap(ledger.snapshot(g.player_id))
        out["error"] = str(exc)
        return jsonify(out), 429
    except ValueError as exc:
        return _json_error(str(exc))
    return jsonify(_public_snap(snap))


@app.post("/api/stripe/webhook")
def stripe_webhook():
    payload = request.get_data()
    if not STRIPE_ENABLED:
        return _json_error("Add a Stripe test key to enable the coin shop", 503)
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
            return jsonify({"received": True, "credited": False, "error": str(exc)}), 200
        return jsonify({"received": True, "credited": credited, "message": message})
    return jsonify({"received": True, "ignored": event_type})



def _to_coins_tree(obj):
    """Convert game-unit money fields to integer coins and drop _aud suffixes."""
    rename = {
        "raw_win_aud": "raw_win",
        "win_aud": "win",
        "jackpot_aud": "jackpot",
        "scatter_win_aud": "scatter_win",
        "bet_aud": "bet",
        "bet_per_line_aud": "bet_per_line",
        "gamble_aud": "gamble",
        "gamble_stake_aud": "gamble_stake",
        "gamble_payout_aud": "gamble_payout",
        "total_paid_aud": "win",
        "jackpot_paid_aud": "jackpot_paid",
        "last_win_aud": "last_win",
        "total_won_aud": "total_won",
        "total_bet_aud": "total_bet",
    }
    if isinstance(obj, list):
        return [_to_coins_tree(x) for x in obj]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in rename:
                out[rename[k]] = game.to_coins(v) if isinstance(v, (int, float)) else _to_coins_tree(v)
            else:
                out[k] = _to_coins_tree(v)
        return out
    return obj


def _spin_payload(step: dict, settled: dict) -> dict:
    """Allow-listed player-facing fields only: never pool size, cap or max-win."""
    out = {
        "kind": step.get("kind", "spin"),
        "raw_win_aud": settled["raw_win_aud"],
        "win_aud": settled["paid_aud"],
        "jackpot_aud": settled["jackpot_aud"],
    }
    kind = out["kind"]
    if kind == "pick":
        out.update(picks=step["picks"], decoys=step["decoys"], tiles=step["tiles"])
    elif kind == "wheel":
        idx = settled.get("wheel_index", step["index"])
        jackpot = bool(settled.get("wheel_jackpot") or step.get("jackpot"))
        wedge = game.WHEEL_WEDGES[idx]
        out.update(
            wedges=step["wedges"], index=idx, jackpot=jackpot,
            angles=step.get("angles") or game.wheel_wedge_angles(),
            prize_mult=0 if jackpot else wedge.get("value", 0) if wedge["type"] == "mult" else 0,
            free_spins=step.get("free_spins", 0),
        )
    elif kind == "hold_spin":
        out.update(
            cells=step.get("cells"), values=step.get("values"),
            rounds=step.get("rounds"), filled=bool(step.get("filled")),
            grand=bool(step.get("grand")), grand_mult=step.get("grand_mult") or 0,
            coins_locked=step.get("coins_locked"),
        )
    elif step.get("mode") == "megaways":
        out.update(
            mode="megaways", stages=step["stages"], ways=step["ways"], cascades=step["cascades"],
            scatters=step["scatters"], scatter_pos=step["scatter_pos"], scatter_win_aud=step["scatter_win_aud"],
            free_spins_awarded=step["free_spins_awarded"], multiplier=step["multiplier"],
            multiplier_end=step["multiplier_end"],
            surprise_wilds=step.get("surprise_wilds") or [],
            coins=step.get("coins") or [],
            coin_count=step.get("coin_count") or 0,
        )
    else:
        out.update(
            mode="classic", grid=step["grid"], line_wins=step["line_wins"], scatters=step["scatters"],
            scatter_pos=step["scatter_pos"], scatter_win_aud=step["scatter_win_aud"],
            free_spins_awarded=step["free_spins_awarded"], multiplier=step["multiplier"],
            surprise_wilds=step.get("surprise_wilds") or [],
            coins=step.get("coins") or [],
            coin_count=step.get("coin_count") or 0,
        )
    return _to_coins_tree(out)


@app.post("/api/spin")
def api_spin():
    data = request.get_json(silent=True) or {}
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
        snap = ledger.settle_round(g.player_id, total_bet, rnd, "COIN")
    except ValueError as exc:
        return _json_error(str(exc))

    steps = game.round_steps(rnd)
    payload = [_spin_payload(st, se) for st, se in zip(steps, snap["steps"])]
    n_games = len(rnd.get("minigames") or [])
    pub = _public_snap(snap)
    return jsonify(
        {
            "mode": mode,
            "lines": lines,
            "bet_per_line": game.to_coins(bpl) if bpl is not None else None,
            "bet": game.to_coins(total_bet),
            "base": payload[0],
            "minigames": payload[1:1 + n_games],
            "free_spins": payload[1 + n_games:],
            "jackpot_hit": snap["jackpot_hit"],
            "jackpot_paid": game.to_coins(snap["jackpot_paid_aud"]),
            "win": game.to_coins(snap["total_paid_aud"]),
            **pub,
        }
    )


@app.post("/api/gamble")
def api_gamble():
    data = request.get_json(silent=True) or {}
    choice = str(data.get("choice") or "").lower()
    try:
        snap = ledger.gamble(g.player_id, choice, game.draw_card)
    except ledger.GambleUnavailable as exc:
        out = _public_snap(ledger.snapshot(g.player_id))
        out["error"] = str(exc)
        out["gamble_closed"] = True
        return jsonify(out), 409
    except ValueError as exc:
        return _json_error(str(exc))
    out = _public_snap(snap)
    out.update(
        card=snap["card"],
        won=snap["won"],
        gamble_stake=game.to_coins(snap["gamble_stake_aud"]),
        gamble_payout=game.to_coins(snap["gamble_payout_aud"]),
        rounds_left=snap["rounds_left"],
    )
    return jsonify(out)


@app.post("/api/gamble/collect")
def api_gamble_collect():
    return jsonify(_public_snap(ledger.gamble_collect(g.player_id)))


@app.get("/api/jackpots")
def api_jackpots():
    return jsonify(ledger.progressive_public())


@app.post("/api/side/cancel")
def api_side_cancel():
    ledger.clear_side_session(g.player_id)
    return jsonify({**_public_snap(ledger.snapshot(g.player_id)), "session": None})


@app.get("/api/side/session")
def api_side_session():
    sess = ledger.side_session(g.player_id)
    if not sess:
        return jsonify({"session": None, **_public_snap(ledger.snapshot(g.player_id))})
    out = _public_snap(ledger.snapshot(g.player_id))
    out["session"] = sess
    return jsonify(out)


@app.post("/api/side/<game>")
def api_side(game: str):
    data = request.get_json(silent=True) or {}
    try:
        result = ledger.play_side(g.player_id, game, data)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    snap = _public_snap(ledger.snapshot(g.player_id))
    snap["result"] = result
    # result already includes coins after the action
    if "coins" in result:
        snap["coins"] = result["coins"]
    return jsonify(snap)



@app.errorhandler(Exception)
def on_uncaught(exc):
    from werkzeug.exceptions import HTTPException

    if isinstance(exc, HTTPException):
        return exc
    errors.capture(exc)
    return _json_error("Something went wrong", 500)


def main() -> None:
    mode = "Stripe test coin shop enabled" if STRIPE_ENABLED else "no Stripe key — coin shop disabled"
    print(f"Crystal Casino SOCIAL · TEST MODE listening on http://0.0.0.0:{PORT}/ ({mode})")
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
