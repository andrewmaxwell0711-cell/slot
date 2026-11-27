"""Crash and error reporting.

If SENTRY_DSN is set in the environment, Sentry is initialised. The DSN is
never hardcoded. Without a DSN, errors are written as structured logs, and
the client may POST to /api/errors (rate limited).
"""

from __future__ import annotations

import json
import logging
import os
import time
from threading import Lock
from typing import Any

log = logging.getLogger("crystal.errors")
if not log.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)

_sentry_inited = False
_hits: dict[str, list[float]] = {}
_hits_lock = Lock()

RATE_LIMIT = 10
RATE_WINDOW = 60.0
MAX_BODY = 8_192


def sentry_dsn() -> str:
    return (os.environ.get("SENTRY_DSN") or "").strip()


def sentry_public_dsn() -> str:
    """Browser DSN only — never fall back to the server DSN."""
    return (os.environ.get("SENTRY_PUBLIC_DSN") or "").strip()


def init_sentry(app: Any | None = None) -> bool:
    """Init Sentry when a DSN is present. Returns True if enabled."""
    global _sentry_inited
    dsn = sentry_dsn()
    if not dsn or _sentry_inited:
        return bool(dsn and _sentry_inited)
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration

        sentry_sdk.init(
            dsn=dsn,
            integrations=[FlaskIntegration()] if app is not None else [],
            send_default_pii=False,
            traces_sample_rate=0.0,
        )
        _sentry_inited = True
        log.info(json.dumps({"event": "sentry_enabled"}))
        return True
    except Exception:
        log.exception(json.dumps({"event": "sentry_init_failed"}))
        return False


def capture(exc: BaseException | None = None, message: str | None = None, extra: dict | None = None) -> None:
    payload = {"event": "server_error", "message": message or (str(exc) if exc else "error")}
    if extra:
        payload["extra"] = {k: extra[k] for k in list(extra)[:12]}
    log.error(json.dumps(payload, default=str))
    if _sentry_inited:
        try:
            import sentry_sdk

            if exc is not None:
                sentry_sdk.capture_exception(exc)
            elif message:
                sentry_sdk.capture_message(message)
        except Exception:
            pass


def allow_report(key: str, limit: int = RATE_LIMIT, window: float = RATE_WINDOW) -> bool:
    now = time.time()
    with _hits_lock:
        q = [t for t in _hits.get(key, []) if now - t < window]
        if len(q) >= limit:
            _hits[key] = q
            return False
        q.append(now)
        _hits[key] = q
        return True


def record_client_error(body: dict[str, Any], source: str) -> None:
    safe = {
        "event": "client_error",
        "source": source,
        "message": str(body.get("message") or "")[:500],
        "url": str(body.get("url") or "")[:300],
        "line": body.get("line"),
        "col": body.get("col"),
    }
    stack = str(body.get("stack") or "")
    if stack:
        safe["stack"] = stack[:2000]
    log.error(json.dumps(safe, default=str))
    if _sentry_inited:
        try:
            import sentry_sdk

            sentry_sdk.capture_message(safe["message"] or "client_error")
        except Exception:
            pass
