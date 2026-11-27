#!/usr/bin/env python3
"""Split styles.css into per-view stylesheets. Source styles.css stays as a fallback."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "styles.css").read_text()
OUT = ROOT / "css"

CORE_ALWAYS = re.compile(
    r":root|html|body|\*\s*,|@font-face|\.top-bar|\.bottom-nav|\.brand|\.splash|"
    r"\.modal|\.toast|\.btn(?:-|\s|,|\:|\{)|\.panel|\.legal|\.site-footer|\.age-|"
    r"\.tutorial|\.bg-aurora|\.bg-cavern|\.bg-float|\.icon-btn|\.header-actions|"
    r"\.hud-|\.demo-badge|\.mode-banner|\.mode-banners"
, re.I)

SLOTS = re.compile(
    r"cabinet|\.reel|reel-strip|\.symbol|btn-spin|\.console|\.meter|mw-|"
    r"megaways|\.marquee|\.bezel|hold-cell|hold-grid|\.sting|#sting|"
    r"win-strip|line-badge|fs-banner|collection-meter|jackpot-sign|"
    r"fly-win|reel-land|sym-land|anticipate|shatter|\.tumble|"
    r"ways-counter|classic-only|mw-only|\.layout|cabinet-wrap|"
    r"wallet-panel|info-panel|primary-balance|spin-breathe|spin-pulse|"
    r"shake-heavy|#win-meter|#btn-spin|tease|scatter-hit"
, re.I)

TABLES = re.compile(
    r"felt-table|felt-eu|felt-col|\.pcard|chip-rack|\.chip(?:\s|,|\.|:|\{)|"
    r"roulette|\.keno|keno-|baccarat|\.bac-|#bac-|wheel-box|game-stage|"
    r"table-msg|court-art|bet-circle|actions-row|\.vp-|poker-|"
    r"\.rl-|highcard|mines-|\.scratch|\.dice|tcp-|fx-squeeze|stage-head|"
    r"stage-body|stage-balance|#btn-stage|stage-title|#felt|#rl-"
, re.I)

HOME = re.compile(
    r"#home|\.home(?:-|\s|,|\.|:|\{)|\.hero|home-marquee|jackpot-plaque|"
    r"home-ticker|home-hud|home-profile|home-title|home-kicker|home-sub|"
    r"home-balance|home-actions|home-features|feature-tile|hero-carousel|"
    r"hero-bg|hero-copy|hero-shade|hero-tag|hero-dots"
, re.I)

LOBBY = re.compile(
    r"#lobby|\.lobby|lobby-tile|lobby-grid|lobby-cat|lobby-head|cat-label|"
    r"tile-media|tile-art|tile-copy|tile-shine|lobby-card|game-floor|"
    r"recent-row|lobby-skel|skel-"
, re.I)

PROFILE = re.compile(
    r"profile-|\.profile|#profile|vip-badge|google-slot|privacy-note|"
    r"btn-signin|btn-signout|hud-auth|hud-who|hud-name|hud-level"
, re.I)

KEYFRAMES = {
    "twinkle-bg": "core",
    "reel-land": "slots",
    "sym-land": "slots",
    "sheen": "slots",
    "wild-pulse": "slots",
    "win-ring": "slots",
    "gem-win": "slots",
    "run-line": "slots",
    "win-punch": "slots",
    "fly-win": "slots",
    "spin-breathe": "slots",
    "btn-press": "slots",
    "shake-heavy": "slots",
    "spin-pulse": "slots",
    "antic": "slots",
    "title-boom": "slots",
    "tea-zoom": "slots",
    "tea-glow": "slots",
    "float": "slots",
    "rays-spin": "slots",
    "burst-pulse": "slots",
    "gold-burst": "slots",
    "fade-in": "core",
    "pop": "core",
}


def walk(css: str) -> list[str]:
    blocks: list[str] = []
    i, n = 0, len(css)
    start = 0

    def skip_comment(j: int) -> int:
        if css.startswith("/*", j):
            k = css.find("*/", j + 2)
            return n if k < 0 else k + 2
        return j

    def skip_string(j: int) -> int:
        q = css[j]
        j += 1
        while j < n:
            if css[j] == "\\":
                j += 2
                continue
            if css[j] == q:
                return j + 1
            j += 1
        return j

    while i < n:
        if css.startswith("/*", i):
            i = skip_comment(i)
            continue
        ch = css[i]
        if ch in ('"', "'"):
            i = skip_string(i)
            continue
        if ch == "{":
            depth = 1
            i += 1
            while i < n and depth:
                if css.startswith("/*", i):
                    i = skip_comment(i)
                    continue
                if css[i] in ('"', "'"):
                    i = skip_string(i)
                    continue
                if css[i] == "{":
                    depth += 1
                elif css[i] == "}":
                    depth -= 1
                i += 1
            blocks.append(css[start:i])
            start = i
            continue
        i += 1
    tail = css[start:].strip()
    if tail:
        blocks.append(css[start:])
    return blocks


def prelude(block: str) -> str:
    cut = block.find("{")
    return block[:cut] if cut >= 0 else block


def classify(block: str) -> set[str]:
    head = prelude(block)
    text = block
    buckets: set[str] = set()
    if head.lstrip().startswith("@keyframes") or head.lstrip().startswith("@-webkit-keyframes"):
        name = re.sub(r"@[-\w]*keyframes\s+", "", head, flags=re.I).strip().split()[0]
        buckets.add(KEYFRAMES.get(name, "core"))
        return buckets
    if SLOTS.search(text):
        buckets.add("slots")
    if TABLES.search(text):
        buckets.add("tables")
    if HOME.search(text):
        buckets.add("home")
    if LOBBY.search(text):
        buckets.add("lobby")
    if PROFILE.search(text):
        buckets.add("core")  # profile is small; keep with core so it always loads
    if CORE_ALWAYS.search(head) or CORE_ALWAYS.search(text[:200]):
        buckets.add("core")
    if not buckets:
        buckets.add("core")
    return buckets


def split_media(block: str) -> dict[str, str]:
    head = prelude(block).strip()
    inner_start = block.find("{")
    inner = block[inner_start + 1 : block.rfind("}")]
    parts: dict[str, list[str]] = {k: [] for k in ("core", "home", "lobby", "slots", "tables")}
    for child in walk(inner):
        child = child.strip()
        if not child:
            continue
        for b in classify(child):
            parts[b].append(child)
    out = {}
    for k, rules in parts.items():
        if rules:
            out[k] = f"{head} {{\n" + "\n".join(rules) + "\n}\n"
    return out


def main() -> None:
    OUT.mkdir(exist_ok=True)
    buckets = {k: [] for k in ("core", "home", "lobby", "slots", "tables")}
    for block in walk(SRC):
        raw = block.strip()
        if not raw:
            continue
        head = prelude(raw).strip()
        if head.startswith("@media") or head.startswith("@supports"):
            split = split_media(raw)
            for k, css in split.items():
                buckets[k].append(css)
            continue
        for k in classify(raw):
            buckets[k].append(raw if raw.endswith("}") or raw.endswith(";") else raw)

    banner = "/* Split from styles.css — do not edit by hand; regenerate with tools/split_styles.py */\n"
    for name, rules in buckets.items():
        body = banner + "\n\n".join(rules) + "\n"
        (OUT / f"{name}.css").write_text(body)
        print(f"{name:8} {len(body):7} bytes  {len(rules):4} blocks")


if __name__ == "__main__":
    main()
