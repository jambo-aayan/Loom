# 12. Mobile-first PWA with Web Push, email action-links as universal fallback

## Status

Accepted

## Context

The user expects to use Loom mostly on their phone, day to day — not the desktop dashboard.
That reframes two earlier decisions: the mobile mockups (`Mobile.dc.html`,
`MobileApprovals.dc.html`) deliberately scoped History and Settings as "desktop-first for now,"
which was a reasonable call when mobile was assumed to be a secondary surface, but isn't once
it's the primary one. It also raises a real question the spec hadn't addressed: Loom is a web
app, not a native iOS/Android app, and the user specifically wants high-confidence signals to
reach them as an actionable phone notification — "notification pops up, I just accept" — not
something they have to remember to check a dashboard for.

We checked what's actually possible without a native app before committing to an approach.
Findings:

- **Android (Chrome)**: full Web Push support, including notification action buttons that can
  fire a background fetch via a service worker without opening the app.
- **iOS (Safari)**: push notifications only work if the site is installed to the Home Screen as
  a PWA — a plain browser tab cannot receive push at all. Even once installed, action buttons
  and background delivery are only partially supported compared to Android
  ([MagicBell: PWA iOS Limitations and Safari Support](https://www.magicbell.com/blog/pwa-ios-limitations-safari-support-complete-guide),
  [webscraft: PWA Push Notifications on iOS in 2026](https://webscraft.org/blog/pwa-pushspovischennya-na-ios-u-2026-scho-realno-pratsyuye?lang=en)).

So a native app isn't required to get real push notifications on a phone, but iOS's ceiling on
*how interactive* that notification can be is genuinely lower than Android's, and worth
designing around rather than assuming parity.

## Decision

### Mobile parity, not mobile-secondary

Every page gets a real mobile layout, not just Overview and Approvals. The five-item bottom tab
bar and the "History/Settings need their own pass" deferral from the original mobile mockups are
superseded — full mobile navigation (including a sensible way to reach History and Settings,
whether that's a sixth tab or a different pattern) is v1 scope, not a later nice-to-have.

### Installable PWA as the delivery mechanism

The Next.js frontend ships a web app manifest and service worker, making it installable to the
home screen on both Android and iOS. This is the prerequisite for push on iOS specifically, and
improves the Android experience too (action buttons, background delivery).

### Two notification channels, layered for reliability

1. **Web Push (primary).** A new per-`Strategy` **Notify threshold** (separate from `Approval
   mode`'s auto-above-threshold bar — see `CONTEXT.md`) controls which signals are worth a push.
   On Android, the notification carries Approve/Reject action buttons that hit the backend
   directly via the service worker. On iOS, where action-button support is limited, tapping the
   notification deep-links straight into that specific `Signal` in Approvals, pre-loaded — one
   tap to get there, one tap to approve, rather than a fully inline action, until real-device
   testing shows otherwise.
2. **Email with one-tap secure action links (universal fallback).** The email notification
   already specced (pending approval / kill-switch / order failed / daily loss limit) gains a
   signed, single-use, short-expiry link per signal that hits the approve/reject endpoint
   directly — no login, no app-open required. This works identically on every platform
   regardless of push permission or browser support, and is worth building on its own merits,
   not only as a fallback for iOS's rougher push support.

### Safety is unchanged by the fast path

Both channels are convenience layers over the same approval → risk/sizing → execution pipeline
already specced. A notification tap or emailed action link only ever *submits* an approval — the
server still re-runs the same risk/sizing checks before anything executes. Speed of approval
never bypasses the safety layer underneath.

## Consequences

- Adds real engineering scope beyond the original dashboard plan: a service worker, Web Push
  subscription management (VAPID keys, per-device subscriptions), and signed action-link
  generation/verification for email — none of this existed in the original spec.
- The mobile mockups need a follow-up design pass: full navigation parity (not just
  Overview/Approvals), and the specific iOS-vs-Android notification-action behavior should be
  verified against real devices before assuming the "zero-tap approve" experience holds on iOS.
- `Notify threshold` is new per-strategy configuration surface on the Strategies page, alongside
  the existing `Approval mode` / auto-above-threshold controls.
