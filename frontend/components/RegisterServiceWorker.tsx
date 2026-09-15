"use client";

import { useEffect } from "react";
import { api } from "@/lib/api";

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
}

async function subscribeToPush(registration: ServiceWorkerRegistration) {
  if (!("PushManager" in window) || !("Notification" in window)) return;

  const { public_key } = await api.vapidPublicKey();
  if (!public_key) return; // Web Push isn't configured server-side yet.

  const permission = await Notification.requestPermission();
  if (permission !== "granted") return;

  const existing = await registration.pushManager.getSubscription();
  const subscription =
    existing ??
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(public_key),
    }));

  const json = subscription.toJSON();
  if (!json.endpoint || !json.keys) return;
  await api.pushSubscribe({
    endpoint: json.endpoint,
    p256dh: json.keys.p256dh,
    auth: json.keys.auth,
    environment: "demo",
  });
}

export function RegisterServiceWorker() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    // The service worker's approve/reject fetches go through the same-origin proxy as every
    // other call (ADR-0017) — a service worker cannot hold the API key either.
    const apiBase = "/api/loom";
    navigator.serviceWorker
      .register(`/sw.js?apiBase=${encodeURIComponent(apiBase)}`)
      .then((registration) => {
        subscribeToPush(registration).catch(() => {
          // Push is a progressive enhancement; the app works fully without it.
        });
      })
      .catch(() => {
        // Installability degrades gracefully to a normal web app; nothing user-facing to do.
      });
  }, []);
  return null;
}
