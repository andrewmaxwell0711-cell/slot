"""Central play hook for Crystal Casino.

Slots and side games call on_play after a settled round. Today this is a
documented extension point (handlers can be registered). It is kept
side-effect free by default so a future live-events calendar, season pass
or clubs feature can subscribe without changing game math.
"""

from __future__ import annotations

from typing import Any, Callable

Handler = Callable[..., None]
_handlers: list[Handler] = []


def register(handler: Handler) -> None:
    if handler not in _handlers:
        _handlers.append(handler)


def on_play(
    player_id: str,
    game: str,
    bet_coins: int,
    win_coins: int,
    *,
    meta: dict[str, Any] | None = None,
) -> None:
    payload = meta or {}
    for handler in list(_handlers):
        handler(
            player_id=player_id,
            game=game,
            bet_coins=int(bet_coins or 0),
            win_coins=int(win_coins or 0),
            meta=payload,
        )
