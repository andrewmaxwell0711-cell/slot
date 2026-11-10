/**
 * Crystal Reels gem art: procedurally faceted SVG gems (brilliant, step and
 * crystal-cluster cuts) with per-facet shading, glow and highlights.
 * Exposes window.CrystalGems = { url(id), svg(id), ids }.
 */
(() => {
  "use strict";
  const S = 120; // viewBox size
  const C = { x: 60, y: 60 };
  const LIGHT = (-125 * Math.PI) / 180; // light from the upper-left

  const hsl = (h, s, l, a = 1) => `hsla(${h.toFixed(1)},${s.toFixed(1)}%,${Math.max(2, Math.min(98, l)).toFixed(1)}%,${a})`;
  const pts = (arr) => arr.map((p) => `${p[0].toFixed(2)},${p[1].toFixed(2)}`).join(" ");
  const centroid = (arr) => [arr.reduce((s, p) => s + p[0], 0) / arr.length, arr.reduce((s, p) => s + p[1], 0) / arr.length];
  const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
  const scaleAbout = (p, c, k) => [c[0] + (p[0] - c[0]) * k, c[1] + (p[1] - c[1]) * k];

  // Deterministic pseudo-random so every load draws identical gems.
  function rng(seed) {
    let s = seed >>> 0;
    return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
  }

  function lightFor(p, c, amp) {
    const ang = Math.atan2(p[1] - c[1], p[0] - c[0]);
    return Math.cos(ang - LIGHT) * amp;
  }

  // ---- Outlines ----
  function outlineRound(n = 16, r = 44) {
    return Array.from({ length: n }, (_, i) => {
      const a = (i / n) * Math.PI * 2 - Math.PI / 2;
      return [C.x + Math.cos(a) * r, C.y + Math.sin(a) * r];
    });
  }
  function outlineOval(n = 16, rx = 34, ry = 46) {
    return Array.from({ length: n }, (_, i) => {
      const a = (i / n) * Math.PI * 2 - Math.PI / 2;
      return [C.x + Math.cos(a) * rx, C.y + Math.sin(a) * ry];
    });
  }
  function outlineCushion(n = 16, r = 43, e = 4) {
    return Array.from({ length: n }, (_, i) => {
      const a = (i / n) * Math.PI * 2 - Math.PI / 2 + Math.PI / n;
      const c = Math.cos(a), s = Math.sin(a);
      const x = Math.sign(c) * Math.pow(Math.abs(c), 2 / e);
      const y = Math.sign(s) * Math.pow(Math.abs(s), 2 / e);
      return [C.x + x * r, C.y + y * r];
    });
  }
  function outlineHeart(n = 24) {
    const out = [];
    for (let i = 0; i < n; i++) {
      const t = (i / n) * Math.PI * 2;
      const x = 16 * Math.pow(Math.sin(t), 3);
      const y = -(13 * Math.cos(t) - 5 * Math.cos(2 * t) - 2 * Math.cos(3 * t) - Math.cos(4 * t));
      out.push([C.x + x * 2.75, C.y + 4 + y * 2.75]);
    }
    return out;
  }
  function outlineTrillion(n = 18, r = 48) {
    const corners = [-90, 30, 150].map((d) => [C.x + Math.cos((d * Math.PI) / 180) * r, C.y + 6 + Math.sin((d * Math.PI) / 180) * r]);
    const out = [];
    const per = n / 3;
    for (let k = 0; k < 3; k++) {
      const a = corners[k], b = corners[(k + 1) % 3];
      for (let i = 0; i < per; i++) {
        const t = i / per;
        const p = lerp(a, b, t);
        // bow the sides outward slightly
        const bow = Math.sin(t * Math.PI) * 7;
        const mid = lerp(a, b, 0.5);
        const dir = [mid[0] - C.x, mid[1] - (C.y + 6)];
        const len = Math.hypot(dir[0], dir[1]) || 1;
        out.push([p[0] + (dir[0] / len) * bow, p[1] + (dir[1] / len) * bow]);
      }
    }
    return out;
  }

  // ---- Brilliant cut facets for any outline ----
  function brilliant(outline, hue, sat, light, seed) {
    const r = rng(seed);
    const n = outline.length;
    const c = centroid(outline);
    const table = outline.map((p, i) => scaleAbout(lerp(p, outline[(i + 1) % n], 0.5), c, 0.5));
    const mid = outline.map((p) => scaleAbout(p, c, 0.76));
    const facets = [];
    // table
    facets.push({ p: table, l: light + 16, kind: "table" });
    for (let i = 0; i < n; i++) {
      const T0 = table[(i - 1 + n) % n], T1 = table[i];
      const O0 = outline[i], O1 = outline[(i + 1) % n];
      const M0 = mid[i], M1 = mid[(i + 1) % n];
      // star facet
      const star = [T0, T1, M0];
      facets.push({ p: [T0, M0, T1], l: light + 8 + lightFor(centroid(star), c, 18) + (i % 2 ? 6 : -4) + r() * 6 });
      // kite (bezel)
      const kite = [T1, M0, O1, M1];
      facets.push({ p: [M0, O1, M1, T1], l: light + lightFor(centroid(kite), c, 26) + (i % 2 ? -6 : 4) + r() * 8 });
      // upper girdle halves
      const g1 = [M0, O0, O1];
      facets.push({ p: g1, l: light - 6 + lightFor(centroid(g1), c, 30) + r() * 10 });
    }
    return { facets, outline, c };
  }

  // ---- Step (emerald) cut ----
  function stepCut(hue, sat, light) {
    const w = 40, h = 46, k = 12;
    const oct = [[C.x - w + k, C.y - h], [C.x + w - k, C.y - h], [C.x + w, C.y - h + k], [C.x + w, C.y + h - k],
      [C.x + w - k, C.y + h], [C.x - w + k, C.y + h], [C.x - w, C.y + h - k], [C.x - w, C.y - h + k]];
    const rings = [1, 0.84, 0.68, 0.5].map((s) => oct.map((p) => scaleAbout(p, [C.x, C.y], s)));
    const facets = [];
    for (let ring = 0; ring < rings.length - 1; ring++) {
      const A = rings[ring], B = rings[ring + 1];
      for (let i = 0; i < 8; i++) {
        const q = [A[i], A[(i + 1) % 8], B[(i + 1) % 8], B[i]];
        const cc = centroid(q);
        facets.push({ p: q, l: light + lightFor(cc, [C.x, C.y], 24 - ring * 5) + (ring % 2 ? 6 : -3) });
      }
    }
    facets.push({ p: rings[3], l: light + 12, kind: "table" });
    return { facets, outline: oct, c: [C.x, C.y] };
  }

  // ---- Crystal cluster (amethyst) ----
  function prism(cx, by, w, h, tip, rot) {
    const ca = Math.cos(rot), sa = Math.sin(rot);
    const tr = ([x, y]) => [cx + x * ca - y * sa, by + x * sa + y * ca];
    const L = -w / 2, R = w / 2, M1 = -w / 6, M2 = w / 6;
    return {
      left: [[L, 0], [M1, 4], [M1, -h], [L, -h + 4]].map(tr),
      front: [[M1, 4], [M2, 4], [M2, -h], [M1, -h]].map(tr),
      right: [[M2, 4], [R, 0], [R, -h + 4], [M2, -h]].map(tr),
      tipL: [[L, -h + 4], [M1, -h], [0, -h - tip]].map(tr),
      tipF: [[M1, -h], [M2, -h], [0, -h - tip]].map(tr),
      tipR: [[M2, -h], [R, -h + 4], [0, -h - tip]].map(tr),
    };
  }
  function cluster(light) {
    const parts = [prism(38, 100, 22, 40, 14, -0.42), prism(84, 100, 22, 36, 13, 0.45), prism(60, 104, 30, 56, 20, 0)];
    const facets = [];
    parts.forEach((pr, k) => {
      const d = k === 2 ? 4 : -4;
      facets.push({ p: pr.left, l: light + 14 + d }, { p: pr.front, l: light + 2 + d }, { p: pr.right, l: light - 14 + d });
      facets.push({ p: pr.tipL, l: light + 26 + d }, { p: pr.tipF, l: light + 12 + d }, { p: pr.tipR, l: light - 4 + d });
    });
    const outline = [[20, 100], [100, 100]];
    return { facets, outline: null, c: [60, 70] };
  }

  // ---- SVG assembly ----
  function sparkle(x, y, s, o = 1) {
    return `<path d="M${x} ${y - s} L${x + s * 0.22} ${y - s * 0.22} L${x + s} ${y} L${x + s * 0.22} ${y + s * 0.22} L${x} ${y + s} L${x - s * 0.22} ${y + s * 0.22} L${x - s} ${y} L${x - s * 0.22} ${y - s * 0.22}Z" fill="#fff" opacity="${o}"/>`;
  }

  function gemSVG(id, spec) {
    const { hue, sat, light } = spec;
    const g = spec.build();
    const uid = `${id}`;
    const glow = hsl(hue, sat, light + 10, 0.55);
    let body = "";
    for (const f of g.facets) {
      const fill = f.kind === "table" ? `url(#tb-${uid})` : hsl(hue, sat, f.l);
      body += `<polygon points="${pts(f.p)}" fill="${fill}" stroke="${hsl(hue, sat * 0.5, Math.min(95, f.l + 30), 0.55)}" stroke-width="0.7" stroke-linejoin="round"/>`;
    }
    const outlinePath = g.outline ? `<polygon points="${pts(g.outline)}" fill="none" stroke="${hsl(hue, sat * 0.6, light + 40, 0.9)}" stroke-width="1.6" stroke-linejoin="round"/>` : "";
    const clipShape = g.outline ? `<clipPath id="cl-${uid}"><polygon points="${pts(g.outline)}"/></clipPath>` : "";
    const sheen = g.outline
      ? `<g clip-path="url(#cl-${uid})"><rect x="0" y="0" width="${S}" height="${S}" fill="url(#sh-${uid})"/><polygon points="10,10 70,10 30,70" fill="#fff" opacity=".10"/></g>`
      : "";
    const [cx, cy] = g.c;
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${S} ${S}" width="${S}" height="${S}">
<defs>
<radialGradient id="gl-${uid}" cx="50%" cy="52%" r="50%"><stop offset="0" stop-color="${glow}"/><stop offset="1" stop-color="${hsl(hue, sat, light, 0)}"/></radialGradient>
<linearGradient id="tb-${uid}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${hsl(hue, sat * 0.7, light + 34)}"/><stop offset=".55" stop-color="${hsl(hue, sat, light + 10)}"/><stop offset="1" stop-color="${hsl(hue, sat, light - 6)}"/></linearGradient>
<linearGradient id="sh-${uid}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".45"/><stop offset=".35" stop-color="#fff" stop-opacity="0"/><stop offset=".8" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".25"/></linearGradient>
<filter id="bl-${uid}" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="2.2"/></filter>
${clipShape}
</defs>
<circle cx="${cx}" cy="${cy}" r="58" fill="url(#gl-${uid})"/>
<g filter="url(#bl-${uid})" opacity=".55" transform="translate(0 3)">${g.outline ? `<polygon points="${pts(g.outline)}" fill="#000"/>` : ""}</g>
${body}${sheen}${outlinePath}
${sparkle(cx - 16, cy - 20, 7, 0.95)}${sparkle(cx + 20, cy + 14, 4, 0.7)}
<ellipse cx="${cx - 12}" cy="${cy - 24}" rx="7" ry="3.2" fill="#fff" opacity=".55" transform="rotate(-30 ${cx - 12} ${cy - 24})"/>
</svg>`;
  }

  function banner(text, y, w = 86) {
    const x = (S - w) / 2;
    return `<g><rect x="${x}" y="${y}" width="${w}" height="22" rx="6" fill="url(#gold)" stroke="#5a3a00" stroke-width="1.2"/>
<rect x="${x + 2}" y="${y + 2}" width="${w - 4}" height="8" rx="4" fill="#fff" opacity=".35"/>
<text x="60" y="${y + 16.5}" text-anchor="middle" font-family="Georgia, 'Times New Roman', serif" font-weight="900" font-size="15" letter-spacing="2" fill="#3a2200">${text}</text></g>`;
  }
  const GOLD = `<linearGradient id="gold" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff3b0"/><stop offset=".45" stop-color="#f3c441"/><stop offset=".55" stop-color="#d79b12"/><stop offset="1" stop-color="#fbe08a"/></linearGradient>`;

  function wildSVG() {
    const parts = [prism(34, 84, 20, 34, 13, -0.5), prism(86, 84, 20, 32, 12, 0.5), prism(48, 86, 20, 46, 16, -0.18), prism(72, 86, 20, 44, 16, 0.18), prism(60, 88, 26, 58, 20, 0)];
    let b = "";
    parts.forEach((pr, k) => {
      const L = 50 + (k === 4 ? 6 : 0);
      [["left", 16], ["front", 2], ["right", -14], ["tipL", 30], ["tipF", 14], ["tipR", -2]].forEach(([f, d]) => {
        b += `<polygon points="${pts(pr[f])}" fill="${hsl(282, 80, L + d)}" stroke="${hsl(290, 90, 88, 0.7)}" stroke-width=".7" stroke-linejoin="round"/>`;
      });
    });
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="120" height="120"><defs>${GOLD}
<radialGradient id="wgl"><stop offset="0" stop-color="#f0c8ff" stop-opacity=".95"/><stop offset=".55" stop-color="#a34dff" stop-opacity=".45"/><stop offset="1" stop-color="#5a1fa8" stop-opacity="0"/></radialGradient></defs>
<circle cx="60" cy="52" r="58" fill="url(#wgl)"/>${b}
${sparkle(60, 14, 9)}${sparkle(30, 44, 5, 0.8)}${sparkle(92, 40, 5, 0.8)}${banner("WILD", 86)}</svg>`;
  }

  function scatterSVG() {
    const tri = [[60, 14], [98, 82], [22, 82]];
    const c = centroid(tri);
    const inner = tri.map((p) => scaleAbout(p, c, 0.45));
    const faces = [
      [tri[0], tri[1], inner[1], inner[0]], [tri[1], tri[2], inner[2], inner[1]], [tri[2], tri[0], inner[0], inner[2]],
    ];
    const beams = ["#ff5a7a", "#ffb648", "#fff35c", "#4dffa6", "#4fb6ff", "#b76bff"].map((col, i) =>
      `<polygon points="70,48 120,${30 + i * 9} 120,${38 + i * 9}" fill="${col}" opacity=".85"/>`).join("");
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="120" height="120"><defs>${GOLD}
<radialGradient id="sgl"><stop offset="0" stop-color="#fff" stop-opacity=".8"/><stop offset=".5" stop-color="#b77bff" stop-opacity=".35"/><stop offset="1" stop-color="#4fb6ff" stop-opacity="0"/></radialGradient>
<linearGradient id="sface" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f4fdff"/><stop offset=".5" stop-color="#bfe8ff"/><stop offset="1" stop-color="#9d8cff"/></linearGradient></defs>
<circle cx="60" cy="54" r="58" fill="url(#sgl)"/>
<polygon points="0,46 52,50 52,54 0,52" fill="#fff" opacity=".9"/>
${beams}
<polygon points="${pts(tri)}" fill="url(#sface)" stroke="#fff" stroke-width="2"/>
<polygon points="${pts(faces[0])}" fill="#fff" opacity=".35"/><polygon points="${pts(faces[1])}" fill="#5a3fd1" opacity=".25"/>
<polygon points="${pts(faces[2])}" fill="#fff" opacity=".55"/><polygon points="${pts(inner)}" fill="#e9f8ff" opacity=".8"/>
${sparkle(60, 22, 8)}${banner("BONUS", 90, 92)}</svg>`;
  }

  function shardSVG() {
    const p1 = prism(54, 96, 16, 46, 16, -0.25), p2 = prism(74, 96, 12, 30, 12, 0.3);
    let b = "";
    [p1, p2].forEach((p) => {
      b += `<polygon points="${pts(p.left)}" fill="#cfe9ff" opacity=".35"/><polygon points="${pts(p.front)}" fill="#a9cbe8" opacity=".28"/><polygon points="${pts(p.right)}" fill="#7d9fc0" opacity=".25"/>`;
      b += `<polygon points="${pts(p.tipL)}" fill="#eaf6ff" opacity=".45"/><polygon points="${pts(p.tipF)}" fill="#cfe9ff" opacity=".35"/><polygon points="${pts(p.tipR)}" fill="#9cbcd8" opacity=".3"/>`;
    });
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="120" height="120">${b}</svg>`;
  }

  const SPECS = {
    quartz: { hue: 330, sat: 85, light: 64, build: () => brilliant(outlineHeart(24), 330, 85, 64, 11) },
    citrine: { hue: 46, sat: 95, light: 55, build: () => brilliant(outlineTrillion(18), 46, 95, 55, 12) },
    topaz: { hue: 24, sat: 95, light: 52, build: () => brilliant(outlineOval(16), 24, 95, 52, 13) },
    amethyst: { hue: 278, sat: 75, light: 52, build: () => brilliant(outlineCushion(16), 278, 75, 52, 16) },
    emerald: { hue: 152, sat: 80, light: 40, build: () => stepCut(152, 80, 40) },
    sapphire: { hue: 212, sat: 90, light: 52, build: () => cluster(52) },
    ruby: { hue: 350, sat: 92, light: 44, build: () => brilliant(outlineRound(16), 350, 92, 44, 15) },
  };

  const cache = {};
  function svg(id) {
    if (cache[id]) return cache[id];
    let out;
    if (id === "wild") out = wildSVG();
    else if (id === "scatter") out = scatterSVG();
    else if (id === "shard") out = shardSVG();
    else if (SPECS[id]) out = gemSVG(id, SPECS[id]);
    else out = shardSVG();
    cache[id] = out;
    return out;
  }
  const urls = {};
  function url(id) {
    if (id === "greentea") return "/assets/green-tea-256.webp";
    if (!urls[id]) urls[id] = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg(id));
    return urls[id];
  }
    function decorCluster(hue) {
    const parts = [prism(30, 118, 22, 50, 16, -0.45), prism(92, 118, 22, 46, 15, 0.45), prism(46, 118, 22, 70, 22, -0.18), prism(76, 118, 22, 66, 22, 0.2), prism(60, 120, 30, 90, 28, 0)];
    let b = "";
    parts.forEach((pr) => {
      [["left", 18], ["front", 4], ["right", -12], ["tipL", 32], ["tipF", 16], ["tipR", 0]].forEach(([f, d]) => {
        b += `<polygon points="${pts(pr[f])}" fill="${hsl(hue, 80, 50 + d, 0.92)}" stroke="${hsl(hue, 90, 90, 0.6)}" stroke-width=".6"/>`;
      });
    });
    return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">${b}${sparkle(60, 8, 7)}</svg>`);
  }
  window.CrystalGems = { svg, url, decorCluster, ids: Object.keys(SPECS).concat(["wild", "scatter", "shard"]) };
})();
