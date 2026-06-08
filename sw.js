// ============================================================
//  Exile Eye - Service Worker (macht die App installierbar)
// ============================================================
const CACHE = "exile-eye-v1";

// Diese Dateien werden fuer schnelles Laden gecacht.
// (Die API-Aufrufe NICHT cachen - die brauchen immer frische Daten!)
const ASSETS = [
  "/",
  "/icons/icon-512.png",
  "/icons/icon-192.png",
  "/manifest.json",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(ASSETS)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  // alte Caches aufraeumen
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);

  // API-Aufrufe + Login/Callback IMMER frisch aus dem Netz (nie cachen)
  if (url.pathname.startsWith("/api/") ||
      url.pathname.startsWith("/login") ||
      url.pathname.startsWith("/callback") ||
      url.pathname.startsWith("/logout")) {
    return; // Standard-Netzwerk-Verhalten
  }

  // Statische Assets: erst Cache, dann Netz (network falls nicht im Cache)
  e.respondWith(
    caches.match(e.request).then((cached) =>
      cached || fetch(e.request).catch(() => caches.match("/"))
    )
  );
});
