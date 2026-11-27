"""Lobby slot themes. Each skin reuses the Crystal Slots engine and ~95% RTP.

Display names, art paths and jackpot labels change; weights, pays and
features stay exactly those in game.py. Official EV RTP (Megaways 95.113%,
Classic 95.071%) therefore applies to every theme.
"""

from __future__ import annotations

from typing import Any

# Official long-run EV RTP from simulate_rtp.py (uncapped, including features).
MEGAWAYS_RTP = 0.95113
CLASSIC_RTP = 0.95071

SLOT_THEMES: tuple[dict[str, Any], ...] = (
    {
        "id": "crystal",
        "name": "Crystal Slots",
        "path": "/slots",
        "tag": "Megaways & 25-line classic · ~95% RTP",
        "jackpot": "Green Tea Jackpot",
        "art": "/assets/tiles/slots.webp",
        "art_sm": "/assets/tiles/slots-sm.webp",
        "background": "/assets/ui/bg-cavern.webp",
        "frame": None,
        "ribbon": "hot",
        "ribbon_label": "HOT",
        "symbols": {},  # default game names
    },
    {
        "id": "dragon",
        "name": "Dragon's Gold",
        "path": "/dragon",
        "tag": "Imperial dragons · same ~95% slot engine",
        "jackpot": "Dragon Pearl Jackpot",
        "art": "/assets/tiles/dragon.webp",
        "art_sm": "/assets/tiles/dragon-sm.webp",
        "background": "/assets/themes/dragon/bg.webp",
        "frame": "/assets/themes/dragon/frame.webp",
        "ribbon": "new",
        "ribbon_label": "NEW",
        "symbols": {
            "quartz": "Gold Ingot",
            "citrine": "Lucky Coins",
            "topaz": "Red Lantern",
            "amethyst": "Jade Disc",
            "emerald": "Jade Pixiu",
            "sapphire": "Blue Phoenix",
            "ruby": "Red Dragon",
            "greentea": "Dragon Pearl",
            "wild": "Dragon Wild",
            "scatter": "Temple Gong",
            "shard": "Jade Shard",
            "coin": "Dragon Coin",
        },
    },
    {
        "id": "pharaoh",
        "name": "Pharaoh's Sun",
        "path": "/pharaoh",
        "tag": "Temple of Ra · same ~95% slot engine",
        "jackpot": "Sun Disk Jackpot",
        "art": "/assets/tiles/pharaoh.webp",
        "art_sm": "/assets/tiles/pharaoh-sm.webp",
        "background": "/assets/themes/pharaoh/bg.webp",
        "frame": "/assets/themes/pharaoh/frame.webp",
        "ribbon": "new",
        "ribbon_label": "NEW",
        "symbols": {
            "quartz": "Canopic Jar",
            "citrine": "Ankh",
            "topaz": "Sandstone Urn",
            "amethyst": "Scarab",
            "emerald": "Eye of Horus",
            "sapphire": "Sphinx",
            "ruby": "Pharaoh",
            "greentea": "Sun Disk",
            "wild": "Anubis Wild",
            "scatter": "Cartouche",
            "shard": "Temple Shard",
            "coin": "Scarab Coin",
        },
    },
    {
        "id": "neon",
        "name": "Neon Nights",
        "path": "/neon",
        "tag": "Cyber city neon · same ~95% slot engine",
        "jackpot": "Neon Crown Jackpot",
        "art": "/assets/tiles/neon.webp",
        "art_sm": "/assets/tiles/neon-sm.webp",
        "background": "/assets/themes/neon/bg.webp",
        "frame": "/assets/themes/neon/frame.webp",
        "ribbon": "new",
        "ribbon_label": "NEW",
        "symbols": {
            "quartz": "Neon Heart",
            "citrine": "Lightning",
            "topaz": "Neon Star",
            "amethyst": "Neon Diamond",
            "emerald": "Neon Palm",
            "sapphire": "Night Rider",
            "ruby": "Skyline",
            "greentea": "Neon Crown",
            "wild": "Neon Wild",
            "scatter": "Disco Ball",
            "shard": "Crystal Shard",
            "coin": "Neon Coin",
        },
    },
)

_BY_ID = {t["id"]: t for t in SLOT_THEMES}
_BY_PATH = {t["path"].lstrip("/"): t["id"] for t in SLOT_THEMES}


def get(theme_id: str | None) -> dict[str, Any]:
    return dict(_BY_ID.get(theme_id or "crystal") or _BY_ID["crystal"])


def from_path(path: str) -> dict[str, Any]:
    key = (path or "").strip("/").split("/")[-1]
    return get(_BY_PATH.get(key, "crystal"))


def catalogue() -> list[dict[str, Any]]:
    out = []
    for t in SLOT_THEMES:
        item = {k: t[k] for k in t if k != "symbols"}
        item["symbols"] = dict(t["symbols"])
        item["megaways_rtp"] = MEGAWAYS_RTP
        item["classic_rtp"] = CLASSIC_RTP
        out.append(item)
    return out
