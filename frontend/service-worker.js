const CACHE_NAME = "travel-planner-shell-v1.0.0";
const APP_SHELL = [
  "/",
  "/index.html",
  "/css/style.css?v=1.0.0",
  "/js/app.js?v=1.0.0",
  "/js/workshop.js?v=1.0.0",
  "/css/rail.css?v=1.0.0",
  "/js/rail.js?v=1.0.0",
  "/site.webmanifest",
  "/assets/app-icon.svg",
  "/assets/echarts.min.js",
  "/assets/china.json",
  "/assets/province_map.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(
    APP_SHELL.map((url) => new Request(url, {cache: "reload"}))
  )));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match("/index.html")));
    return;
  }

  // Styles and application code must be current as a pair. Cache-first used
  // to render the new workshop with an old stylesheet until a second reload.
  if (url.pathname.endsWith(".css") || url.pathname.startsWith("/js/") || (url.pathname.startsWith("/rail/") && url.pathname.endsWith(".js"))) {
    event.respondWith(fetch(request, {cache: "no-cache"}).then((response) => {
      if (response.ok) {
        const copy = response.clone();
        event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)));
      }
      return response;
    }).catch(() => caches.match(request)));
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => {
      const refreshed = fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => cached);
      return cached || refreshed;
    })
  );
});
