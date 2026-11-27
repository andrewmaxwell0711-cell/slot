# Crystal Casino — Google Play readiness

This note is the launch checklist for an Android build of Crystal Casino, a **social casino** (virtual coins only). It is written for Play Console reviewers and for the engineering work still required before a production track. It is not legal advice.

**Current distribution:** the game is live on the web at `https://slot-yqoa.onrender.com`. This document is shipped on the `staging/launch-essentials` branch and must not be treated as a production Play submission until the pre-launch checklist below is signed off.

Exact simulated-gambling sentence (use verbatim in the age gate, footer, shop, store listing, and in-app legal pages):

> Practice or success at social casino gaming does not imply future success at real money gambling.

Also state, in the same surfaces: coins have no real-world value and cannot be redeemed; the age gate is **18+**.

---

## 1. Data Safety form (Play Console → App content)

Complete the Data Safety form for every track other than a purely internal test. The privacy policy URL must be a stable, public `https` page: **`https://<production-host>/privacy`**. Terms: **`https://<production-host>/terms`**.

Declare that the app **collects** user data (even if a user only plays as a guest). Do **not** declare “no data collected.”

| Data type (Play category) | Collected? | Shared with third parties? | Required / optional | Purpose |
| --- | --- | --- | --- | --- |
| Name | Yes, if the player signs in with Google | Shared with Google only to perform sign-in; stored by us | Optional (guest play works without it) | Account management, in-app profile display |
| Email address | Yes, if signed in with Google | Same as name | Optional | Account management, identifying the account |
| User IDs | Yes (guest cookie id and/or internal player id; Google `sub`) | Hosting provider as needed to run the service | App functionality | Account and game progress |
| Photos (profile photo / avatar URL) | Yes, if Google provides a profile photo | Same as name | Optional | In-app profile display |
| Gameplay (game progress: coins, XP/VIP, trophies, themes, missions, bonus timers, tutorial, settled-round stats for leaderboards) | Yes | Hosting provider only | App functionality | Run the social casino, leaderboards, missions |
| Purchase history (web: Stripe Checkout session id, pack, coin amount, time; Android: Play purchase token / order id once Billing is implemented) | Yes, if the player buys a coin pack | Stripe (web only) or Google Play (Android only) as the payment processor | Optional (purchases are never required; free daily/hourly coins are provided) | Fulfil virtual coin packs once, support, fraud prevention |
| Crash logs / diagnostics | Yes, if an error occurs (and via Sentry when `SENTRY_DSN` / `SENTRY_PUBLIC_DSN` is configured) | Error-reporting provider if configured | App functionality | Stability and bug fixing |
| Device or other IDs | Incidental technical identifiers may appear in logs or Play/Google sign-in | Processors above | App functionality | Sign-in, crash diagnosis |

**Security practices to declare (if and only if they are true of the shipped Android build):**

- Data is encrypted in transit (HTTPS / TLS).
- Users can request deletion of their signed-in account from the in-app profile; this removes Google profile fields and game progress. (Confirm the production Android build exposes the same control.)
- Independent security review: **not** claimed unless a review has actually been completed.

**Do not declare:**

- Selling personal data, or sharing for advertising / cross-context ads (we do not).
- Financial info collected by us as a bank-style balance — coins have no cash value. Play may still require “Purchase history” as above.
- Approximate or precise location, contacts, SMS, files, health, or microphone unless a later build adds them (the current product does not).

Update the form if Sentry, Google sign-in, or billing processors change. SDK declarations must include Google Play Billing (Android), Google Sign-In, and Sentry if those are compiled in.

---

## 2. IARC questionnaire (simulated gambling)

All apps on Google Play need an IARC content rating. Complete the Play Console questionnaire **accurately**. Misrepresenting gambling-like content can get the app removed.

Answer the **simulated gambling / gambling** questions as follows for Crystal Casino as it exists today:

- The app includes **casino games** (slots, table games such as baccarat, keno, roulette, blackjack, and similar) played with **virtual coins**.
- This is **simulated gambling**, not real-money gambling.
- Players **cannot** win real money, real-world prizes, or anything that can be cashed out or redeemed for value.
- Virtual coins **have no real-world monetary value** and **cannot be redeemed**.
- Optional coin packs only add more virtual coins for entertainment; purchasing is **not required** to play (free starting, daily and hourly coins).
- There is **no** user-to-user trading or transfer of coins for value.
- The app is for adults: we enforce an **18+** age gate in-app even if a regional IARC rating would be lower.

Do **not** mark the app as real-money gambling. Do not say there is no gambling-like content.

If paid coin packs, new games, or real-world prizes are ever added, **submit a new questionnaire** before shipping. Real-world prizes or redeemable value would change the product’s legal character and are out of scope for this social casino.

---

## 3. Content rating expectation

IARC issues **regional** ratings from the same questionnaire. Typical outcomes for simulated gambling (no real-money payouts) are:

| Region / authority (examples) | Expected band | Notes |
| --- | --- | --- |
| IARC generic | Often **12+** when simulated gambling is declared | Still show the in-app **18+** gate; the store rating and our gate can differ. |
| ESRB (for example US/Canada) | Often **Teen** for simulated gambling | Confirm the official certificate after the questionnaire. |
| PEGI / European authorities | Commonly a mid-teen rating when only simulated gambling is present | Confirm the certificate. |
| Australia (ACB / Australian classification used in IARC) | Simulated gambling may be rated **higher** than 12+ (the Australian scheme has treated this content strictly, including **R18+** in store listings) | Australia is a launch market for this project; expect a mature rating and keep the 18+ gate. |

**Treat the Play-issued certificate as authoritative.** The table above is an expectation, not a self-rating. After the questionnaire returns ratings, put those exact marks on the store listing and in this document.

The official store listing, screenshots, and short/full descriptions must also include the simulated-gambling sentence, that coins have no real-world value and cannot be redeemed, and that the app is 18+.

---

## 4. Closed Testing track plan

For **personal Play developer accounts created after 13 November 2023**, Google requires a closed test before production access: **at least 12 testers opted in continuously for at least 14 days**, then an application for production access from the Play Console dashboard.

Recommended path:

1. **Internal testing** (optional, up to 100 users): short smoke of sign-in, first-time tutorial, age gate, a spin, a table game, a Play Billing test purchase, and account deletion.
2. **Closed testing:** create the closed track, attach a signed Android App Bundle that uses **Play Billing for coin packs** (not Stripe), list **12+ testers** (plus a few reserves), and keep them opted in for **14+ continuous days**. Testers should use the same core flows and include at least one Australian locale.
3. Collect feedback: crashes (Sentry or Play Vitals), billing errors, age gate and disclosure wording, tutorial skip/complete, deletion.
4. When the 12×14-day bar is met, apply for **production** access and answer Play’s questions honestly (features exercised, differences from expected production use, policy compliance).
5. Do not promote a web-only Stripe build to the Play production track.

Organisation Play accounts may have different test obligations; still run a closed test before production.

---

## 5. Payments: Play Billing on Android, Stripe on the web only

**Policy:** Google Play requires that digital goods sold **inside** an Android app distributed on Play use **Google Play Billing**. Stripe Checkout (or any other web payment) must **not** be used to sell coin packs inside that Android app.

| Surface | How coin packs are sold | Verification |
| --- | --- | --- |
| Web (`slot-yqoa.onrender.com` and future web hosts) | Stripe Checkout, **test keys only** in the current environment (`sk_test_`). Live Stripe keys are refused by the server. | Existing webhook + `processed_sessions` idempotency keyed by Checkout session id. |
| Android app on Google Play | **Google Play Billing only.** Do not offer a Stripe, web, or alternative checkout for coins in the Play build. | Server-side verification of the **purchase token** with the **Google Play Developer API**, then credit coins once. |

### Implementation plan (Android billing — not built on this branch)

1. Play Console: create the app, set up a **license tester** list, and define in-app products that map 1:1 to the existing packs (`pack_5`, `pack_10`, `pack_20`, `pack_50`) with the same coin amounts. Prices are set in Play Console, not copied from Stripe at runtime.
2. Backend: add a `PLAY_PACKAGE_NAME` and a Play Developer API service account (JSON key in an env var or secret manager — **never commit the key**). Endpoint e.g. `POST /api/play/acknowledge` with `{ product_id, purchase_token, order_id }`.
3. Verify each token with `purchases.products.get` (package name, product id, token). Reject mismatches, cancelled/refunded purchases, and products that are not in the catalogue.
4. Credit coins **once** using the same ledger used for Stripe, with a new idempotency key (`play:<purchase_token>` or `order_id`) in `processed_sessions` (or a sibling table). Never credit on the client alone.
5. Acknowledge the purchase after a successful credit. Handle `already credited` as success so retries are safe.
6. Hide Stripe UI when the client identifies as the Play Android app (`store=play` or a signed Play Integrity signal). Keep Stripe routes available for the web origin only.
7. Test with license testers, refunds, and duplicate-token delivery (see `test_v11.py` purchase races for the pattern).
8. Update the Data Safety form and this document when Billing ships.

Until that work is done, **do not** ship an Android production build that sells coins.

---

## 6. Other Play policy notes

- **Real-money gambling policy:** this app is a social casino without cash-out. Keep it that way. Do not add redeemable prizes, cash withdrawals, or “convertible” coins.
- **Deceptive behaviour / dark patterns:** do not stage near misses, celebrate net losses, or invent purchase urgency. The first-time tutorial is skippable and remembered.
- **User-generated content:** not applicable today.
- **Ads:** none today. If ads are added, they must match the content rating and be declared.
- **App access:** reviewers need a way to enter the app (the 18+ gate is allowed; provide a test account if sign-in is required for any path). Guest play should remain available.
- **Privacy policy and terms** must stay reachable at `/privacy` and `/terms` on the production host, and linked from the store listing, the age gate, the footer and the profile.

---

## 7. Pre-launch checklist (sign-off)

- [ ] `/privacy` and `/terms` are served over HTTPS on the intended production host and match this product.
- [ ] Age gate, footer, shop, and Play store listing all include the exact simulated-gambling sentence, the no-value/no-redemption wording, and 18+.
- [ ] Data Safety form filled to match Section 1.
- [ ] IARC questionnaire submitted; official ratings recorded (especially Australia).
- [ ] Android coin packs use Play Billing with server-side token verification; Stripe is web-only.
- [ ] Sentry DSN (and optional public DSN) provided via environment variables only, never committed.
- [ ] Closed test: 12+ testers opted in for 14 continuous days (personal accounts) and production access approved if required.
- [ ] Account deletion tested on the Android build.
- [ ] No production push of a branch that still uses test-only Stripe for Play in-app goods.
- [ ] Free-plan Postgres expiry / hosting plan reviewed so player data is not lost mid-test.
