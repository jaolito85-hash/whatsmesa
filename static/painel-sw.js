// Service worker do Modo Painel (KDS).
//
// Regra de ouro: pedido NUNCA pode vir de cache. A cozinha tem que ver a fila
// de verdade, agora. Por isso:
//   - /api/...  -> sempre rede, sem cache (se a rede cair, o painel.js mostra
//                  a tarja "sem conexão" e segue tentando).
//   - resto (HTML, CSS, JS, ícones) -> rede primeiro; só cai no cache guardado
//                  quando estiver offline, pra abrir a casca do app mesmo sem net.
const CACHE = "klink-painel-v1";
const SHELL = [
  "/painel/",
  "/static/painel.css",
  "/static/painel.js",
  "/static/brand/favicon-64.png",
  "/static/brand/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // Pedidos e qualquer chamada de API: só rede, jamais cache.
  if (url.pathname.startsWith("/api/")) {
    return; // deixa o navegador buscar normalmente
  }

  // Casca do app: rede primeiro, cache como rede reserva (offline).
  event.respondWith(
    fetch(req)
      .then((resp) => {
        if (resp && resp.ok && url.origin === self.location.origin) {
          const copy = resp.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy));
        }
        return resp;
      })
      .catch(() => caches.match(req).then((hit) => hit || caches.match("/painel/"))),
  );
});
