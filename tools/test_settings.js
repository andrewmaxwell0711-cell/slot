const path = require("path");
const settings = require(path.join(__dirname, "..", "settings.js"));
const fx = require(path.join(__dirname, "..", "fx.js"));
const assert = (c, m) => { if (!c) { throw new Error(m); } };

const store = {};
const mem = { getItem: (k) => store[k] || null, setItem: (k, v) => { store[k] = String(v); } };

// persistence
const saved = settings.save({ master: 40, sfx: false, music: true, haptics: false, reduceEffects: true }, mem);
assert(saved.master === 40, "master saved");
assert(saved.sfx === false, "sfx saved");
assert(saved.haptics === false, "haptics saved");
assert(saved.reduceEffects === true, "reduce saved");
assert(mem.getItem(settings.KEY), "wrote key");
const loaded = settings.load(mem.getItem(settings.KEY), { osReduce: false });
assert(loaded.master === 40, "master loaded");
assert(loaded.sfx === false, "sfx loaded");
assert(loaded.reduceEffects === true, "reduce loaded");

// defaults + os reduce defaulting
const fresh = settings.load("{}", { osReduce: true });
assert(fresh.reduceEffects === true, "os reduce defaults the flag");
const freshOff = settings.load("{}", { osReduce: false });
assert(freshOff.reduceEffects === false, "no os reduce stays off");
const userOn = settings.load(JSON.stringify({ reduceEffects: false }), { osReduce: true });
assert(userOn.reduceEffects === false, "explicit user value preserved");

// effectsOn respects both flags
assert(settings.effectsOn({ reduceEffects: false }, { osReduce: false }) === true, "effects on");
assert(settings.effectsOn({ reduceEffects: true }, { osReduce: false }) === false, "user reduce");
assert(settings.effectsOn({ reduceEffects: false }, { osReduce: true }) === false, "os reduce wins");

// clamp
assert(settings.clamp(120, 0, 100) === 100, "clamp hi");
assert(settings.clamp(-5, 0, 100) === 0, "clamp lo");

// anticipation: only when the bonus will actually complete, and one more is needed
assert(fx.shouldAnticipate(2, [1], 3) === true, "2 landed + last will hit");
assert(fx.shouldAnticipate(2, [0], 3) === false, "2 landed + last miss is not teased");
assert(fx.shouldAnticipate(1, [1, 1], 3) === false, "too early (only 1 landed)");
assert(fx.shouldAnticipate(0, [1, 1, 1], 3) === false, "nothing genuine landed yet");
assert(fx.shouldAnticipate(3, [0], 3) === false, "already complete");
assert(fx.shouldAnticipate(2, [0, 1], 3) === true, "will complete on a later reel");
// celebrate multiplier must never disagree with the visible count-up
assert(fx.formatCelebrateSub("149× your total bet", 0, 59777) === "", "hide multiplier at 0");
assert(fx.formatCelebrateSub("149× your total bet", 43155, 59777) === "108× your total bet", "multiplier scales with count");
assert(fx.formatCelebrateSub("149× your total bet", 59777, 59777) === "149× your total bet", "final multiplier");
assert(fx.formatCelebrateSub("Progressive jackpot — the live ticker pot", 100, 500) === "", "non-mult sub hidden mid-count");
assert(fx.formatCelebrateSub("Progressive jackpot — the live ticker pot", 500, 500) === "Progressive jackpot — the live ticker pot", "non-mult sub at end");

// table win presentation: small wins toast, big/natural overlay, themed art
assert(fx.TABLE_OVERLAY_X === 5, "overlay threshold is 5x");
assert(fx.tableWinPresentation({ payout: 0, net: 0, bet: 400 }).mode === "none", "zero is none");
assert(fx.tableWinPresentation({ payout: 400, net: 0, bet: 400 }).mode === "none", "push is none");
assert(fx.tableWinPresentation({ payout: 800, net: 400, bet: 400 }).mode === "toast", "even money is a toast");
assert(fx.tableWinPresentation({ payout: 1996, net: 1596, bet: 400 }).mode === "toast", "just under 5x is a toast");
assert(fx.tableWinPresentation({ payout: 2000, net: 1600, bet: 400 }).mode === "overlay", "5x is an overlay");
const bj = fx.tableWinPresentation({ payout: 1000, net: 600, bet: 400, natural: true, game: "blackjack", title: "BLACKJACK" });
assert(bj.mode === "overlay", "blackjack natural is an overlay even under 5x");
assert(bj.kicker === "NATURAL", "natural kicker");
assert(bj.game === "blackjack", "blackjack game id");
assert(fx.tableWinPresentation({ payout: 800, net: 400, bet: 400, game: "blackjack" }).mode === "toast", "plain blackjack even-money stays a toast");
const art = fx.tableMedallion("blackjack");
assert(art.indexOf("greentea") < 0 && art.indexOf("Green Tea") < 0, "no tea bag on blackjack");
assert(art.indexOf("/assets/chips/") >= 0 && art.indexOf("/assets/cards/") >= 0, "blackjack uses chips and cards");
assert(fx.tableMedallion("roulette").indexOf("art-wheel") >= 0, "roulette wheel art");
assert(fx.tableMedallion("keno").indexOf("art-keno-ball") >= 0, "keno ball art");
assert(fx.normalizeTableGame("", "CASINO WAR") === "war", "title maps to war");

console.log("settings and anticipation tests ok");

