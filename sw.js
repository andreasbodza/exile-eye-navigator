// ============================================================
//  Exile Eye - Service Worker (macht die App installierbar)
// ============================================================
// WICHTIG: Bei jeder neuen App-Version diese Zahl hochzaehlen (v1 -> v2 -> ...).
// Das raeumt alte Caches auf und erzwingt frische Dateien.
const CACHE = "exile-eye-v2";

// Diese Dateien werden fuer schnelles Laden gecacht.
// (HTML/Seiten NICHT vorab cachen - die holen wir immer frisch, siehe fetch)
const ASSETS = [
  "/icons/icon-512.png",
  "/icons/icon-192.png",
  "/manifest.json",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(ASSETS)).catch(() => {})
  );
  self.skipWaiting();   // neue Version sofort uebernehmen
});

// Auf "Aktualisieren"-Klick aus der App reagieren (wartenden SW aktivieren)
self.addEventListener("message", (e) => {
  if (e.data && e.data.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  // alte Caches (andere Versionsnummer) aufraeumen
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);

  // Nur GET-Anfragen behandeln (POST etc. immer durchreichen)
  if (req.method !== "GET") return;

  // API-Aufrufe + Login/Callback IMMER frisch aus dem Netz (nie cachen)
  if (url.pathname.startsWith("/api/") ||
      url.pathname.startsWith("/login") ||
      url.pathname.startsWith("/callback") ||
      url.pathname.startsWith("/logout")) {
    return; // Standard-Netzwerk-Verhalten
  }

  // HTML-Seiten / Navigation -> NETWORK-FIRST:
  // immer die frische Seite holen, Cache nur als Offline-Notfall.
  // So sieht man Updates SOFORT nach dem Hochladen (kein haengender Cache).
  const isHTML = req.mode === "navigate" ||
                 (req.headers.get("accept") || "").includes("text/html");
  if (isHTML) {
    e.respondWith(
      fetch(req)
        .then((res) => {
          // frische Seite zusaetzlich als Offline-Fallback ablegen
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
          return res;
        })
        .catch(() => caches.match(req).then((c) => c || caches.match("/")))
    );
    return;
  }

  // Bilder/Icons/Manifest -> CACHE-FIRST (aendern sich selten, laedt schnell)
  e.respondWith(
    caches.match(req).then((cached) =>
      cached || fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
        return res;
      }).catch(() => cached)
    )
  );
});
