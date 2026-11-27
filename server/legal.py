"""Privacy policy, terms, and the required simulated-gambling disclosure.

These strings are the source of truth for /privacy, /terms, the age gate,
the shop, the footer, and the Google Play store-copy checklist. Coins have
no cash value. Do not mention the internal house pool in public legal copy.
"""

from __future__ import annotations

# Exact sentence required for Google Play / simulated-gambling disclosure.
SIMULATED_GAMBLING = (
    "Practice or success at social casino gaming does not imply future success "
    "at real money gambling."
)

AGE_LIMIT = 18

COINS_NO_VALUE = (
    "Coins are for entertainment only, have no monetary value and cannot be "
    "redeemed for cash or prizes."
)

RESPONSIBLE_PLAY = (
    "Play for fun. This is a social casino, not real-money gambling. "
    "If you need a break, step away. 18+ only."
)

PRIVACY_URL = "/privacy"
TERMS_URL = "/terms"


def disclosure_block() -> str:
    """Shop, footer and store-listing paragraph."""
    return (
        f"{COINS_NO_VALUE} Coins have no real-world value and cannot be redeemed. "
        f"{SIMULATED_GAMBLING} "
        f"Crystal Casino is a social casino for entertainment. "
        f"18+ only. You must be {AGE_LIMIT} or older to play."
    )


def privacy_html() -> str:
    return f"""
<h1>Privacy Policy</h1>
<p class="legal-updated">Last updated: 28 November 2026. Applies to the Crystal Casino social casino (web and any future Android app).</p>
<p>Crystal Casino is a <strong>social casino for entertainment only</strong>. {COINS_NO_VALUE} {SIMULATED_GAMBLING} You must be {AGE_LIMIT} or older to play.</p>

<h2>Who we are</h2>
<p>This policy describes how the operator of Crystal Casino (“we”) collects and uses information when you play as a guest or sign in. We do not sell your personal information. Coins have no cash value. There is no cash-out, withdrawal or redemption of coins for money or prizes.</p>

<h2>Information we collect</h2>
<h3>Google account details (if you sign in)</h3>
<p>When you choose Google sign-in, we store the name, email address and profile photo (avatar) that Google provides after you consent, so we can identify your account and show your profile.</p>
<h3>Game progress</h3>
<p>For guests and signed-in players we store game progress needed to run the social casino: a player identifier, virtual coin balance, experience and VIP tier, trophies and cabinet themes, daily missions, bonus claim times, tutorial completion, and a history of settled rounds used for leaderboards and missions. Guests are identified by a cookie on your device.</p>
<h3>Purchase records</h3>
<p>If you buy a virtual coin pack on the web, we store a record of that purchase (the Stripe Checkout session identifier, the pack, the coin amount and the time) so we can credit coins once and handle support questions. On a future Android app, coin packs will be sold through Google Play Billing and we will store the Play purchase token and order identifiers for the same purpose. Purchase records are not a cash wallet and cannot be withdrawn.</p>
<h3>Technical and crash information</h3>
<p>We log technical events such as error messages, device or browser type, and the page or action that failed, so we can fix bugs. If crash reporting is enabled, a processor such as Sentry may receive this diagnostic information. We do not use this to serve advertising.</p>

<h2>How we use information</h2>
<ul>
  <li>To operate the game, keep your progress, and credit free bonuses or purchased coin packs.</li>
  <li>To sign you in, display your profile, and honour a request to delete your account.</li>
  <li>To keep the ledger accurate (for example, making sure a purchase or daily bonus is only granted once).</li>
  <li>To diagnose crashes and improve stability.</li>
  <li>To meet legal obligations and prevent abuse.</li>
</ul>
<p>We do not use your data to offer real-money gambling, and we do not cash out or transfer coins between players.</p>

<h2>Cookies and sessions</h2>
<p>We use a guest cookie (<code>fr_player</code>) so your device can keep its progress, and — after you sign in — HttpOnly session and readable CSRF cookies (<code>cc_session</code>, <code>cc_csrf</code>) to keep you signed in securely.</p>

<h2>Sharing</h2>
<p>We share data with service providers only as needed to run the product:</p>
<ul>
  <li>Google, for sign-in (if you use it).</li>
  <li>Stripe, for web coin-pack checkout in test or live payments we may enable later on the web only. Stripe is not used inside the Android app.</li>
  <li>Google Play, for in-app coin packs on Android (planned; not used on the web).</li>
  <li>Our hosting provider, and an error-reporting provider if configured.</li>
</ul>
<p>We do not sell personal information or share it for cross-context advertising.</p>

<h2>Retention and account deletion</h2>
<p>We keep account and progress data while your account or guest profile is active. You can delete your signed-in account at any time from the in-app profile (“Delete my account”). Deletion permanently removes your Google profile fields and game progress from our player records. We may retain limited purchase or security logs for a short period where we must, for fraud prevention or legal compliance, and then delete or irreversibly anonymise them.</p>

<h2>International processing</h2>
<p>Our hosting and providers may process data outside your country, including Australia and the United States, with appropriate safeguards used by those providers.</p>

<h2>Your choices</h2>
<p>You can play as a guest without a Google account. You can skip the first-time tutorial, decline sign-in, and stop playing at any time. You can request deletion from the profile screen. For privacy questions, use the in-app profile or the contact path published with the official store listing when the Android app is submitted.</p>

<h2>Children</h2>
<p>Crystal Casino is for adults. You must be {AGE_LIMIT} or older. We do not knowingly collect personal information from children.</p>

<p><a href="/terms">Terms of Use</a> · <a href="/">Back to Crystal Casino</a></p>
"""


def terms_html() -> str:
    return f"""
<h1>Terms of Use</h1>
<p class="legal-updated">Last updated: 28 November 2026. Applies to the Crystal Casino social casino (web and any future Android app).</p>

<h2>Social casino only</h2>
<p>Crystal Casino is a social casino for entertainment. {COINS_NO_VALUE} {SIMULATED_GAMBLING}</p>
<p>There is no real-money gambling, no betting with cash, and no way to withdraw, cash out, transfer or redeem coins for money, goods or prizes of monetary value. Optional coin packs only add more virtual coins for play inside the app.</p>

<h2>Age requirement</h2>
<p>You must be {AGE_LIMIT} years of age or older. We show an age gate before play. If you are not {AGE_LIMIT} or older, you must leave and must not use the service.</p>

<h2>Accounts and guests</h2>
<p>You may play as a guest or sign in with Google. You are responsible for activity on your account. You may delete your signed-in account from the profile screen; this removes your account and stored progress as described in the <a href="/privacy">Privacy Policy</a>.</p>

<h2>Virtual coins and purchases</h2>
<p>Starting coins and free daily or hourly bonuses are provided so that purchasing is never required to play. Coin packs bought on the <strong>web</strong> are processed by Stripe. Coin packs sold <strong>inside an Android app distributed on Google Play</strong> must use Google Play Billing; Stripe will not be used for those in-app Android purchases. All purchases of coins are final virtual items for entertainment, subject to the store’s refund rules, and have no cash value.</p>

<h2>Fair play and outcomes</h2>
<p>Game outcomes (spins, cards, draws and tables) are decided on our servers. You agree not to attack, cheat, interfere with, or misuse the service, and not to attempt to extract cash value from coins.</p>

<h2>Availability</h2>
<p>The service is provided as-is for entertainment, may change, and may be interrupted for maintenance or policy reasons. We may add, change or retire games, bonuses or features.</p>

<h2>Disclaimers</h2>
<p>{SIMULATED_GAMBLING} We do not warrant that you will win virtual coins or enjoy any particular result. To the extent allowed by law, we are not liable for lost virtual progress or entertainment value.</p>

<h2>Governing notes</h2>
<p>If a part of these terms is unenforceable, the rest still applies. The Privacy Policy is part of these terms. We may update these terms; the date above will change, and continued use after an update means you accept the revised terms.</p>

<p><a href="/privacy">Privacy Policy</a> · <a href="/">Back to Crystal Casino</a></p>
"""
