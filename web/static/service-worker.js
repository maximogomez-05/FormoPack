const CACHE_NAME = "formopack-chofer-v5";
const APP_SHELL = [
  "/static/css/style.css?v=8",
  "/static/manifest.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((key) => key.startsWith("formopack-chofer-") && key !== CACHE_NAME).map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname === "/logout") {
    event.respondWith((async () => {
      await caches.delete("formopack-panel");
      return fetch(request);
    })());
  } else if (url.pathname === "/chofer") {
    event.respondWith(panelChofer(request));
  } else if (APP_SHELL.includes(url.pathname + url.search)) {
    event.respondWith(networkFirst(request));
  }
});

self.addEventListener("sync", (event) => {
  if (event.tag === "formopack-deliveries") {
    event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      clients.forEach((client) => client.postMessage({ type: "sync-deliveries" }));
    }));
  }
});

async function networkFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  try {
    const response = await fetch(request);
    if (response.ok) await cache.put(request, response.clone());
    return response;
  } catch (error) {
    const cached = await cache.match(request);
    if (cached) return cached;
    return new Response("Sin conexión y sin una pantalla guardada.", {
      status: 503,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }
}


async function panelChofer(request) {
  let response;
  try {
    response = await fetch(request);
  } catch (error) {
    const sesion = await self.cookieStore?.get("fp_panel");
    if (sesion && /^[a-f0-9]{32}$/.test(sesion.value)) {
      const guardado = await (await caches.open("formopack-panel")).match("/chofer");
      if (guardado?.headers.get("X-Formopack-Panel") === sesion.value) return guardado;
    }
    return new Response("Conectate para abrir tu panel de reparto.", {
      status: 503, headers: {"Content-Type":"text/plain; charset=utf-8","Cache-Control":"no-store"}
    });
  }
  const contexto = response.headers.get("X-Formopack-Panel");
  if (response.ok && !response.redirected && contexto) {
    const cache = await caches.open("formopack-panel");
    await cache.put("/chofer", response.clone());
  } else {
    await caches.delete("formopack-panel");
  }
  return response;
}

self.addEventListener("message", event => {
  if (event.data?.tipo === "guardar-panel-inicial" && event.source?.url === self.location.origin + "/chofer") {
    event.waitUntil(panelChofer(new Request(self.location.origin + "/chofer", {credentials:"same-origin"})));
  }
});
