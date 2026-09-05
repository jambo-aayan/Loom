// Installable-to-home-screen shell caching (M1, story 60) plus Web Push approve/reject
// (M3, ticket #39) and the iOS deep-link fallback for platforms with no notification
// action buttons (M3, ticket #40).
const CACHE = "loom-shell-v1";
const API_BASE = new URL(self.location.href).searchParams.get("apiBase") || "http://localhost:8000";

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(["/", "/manifest.json"])));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});

self.addEventListener("push", (event) => {
  if (!event.data) return;
  const payload = event.data.json();
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      data: { signal_id: payload.signal_id },
      actions: payload.actions,
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const signalId = event.notification.data && event.notification.data.signal_id;
  if (!signalId) return;

  if (event.action === "approve" || event.action === "reject") {
    event.waitUntil(
      fetch(`${API_BASE}/signals/${signalId}/${event.action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      }),
    );
    return;
  }

  // No action button was tapped — either the user tapped the notification body, or the
  // platform doesn't support action buttons at all (iOS Web Push). Deep-link into the
  // Approvals page with the signal highlighted instead (ticket #40).
  const url = `/approvals?signal=${signalId}`;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ("focus" in client) {
          if ("navigate" in client) client.navigate(url);
          return client.focus();
        }
      }
      return self.clients.openWindow(url);
    }),
  );
});
