const SHELL_CACHE = 'superzoshyt-shell-v28';
const RUNTIME_CACHE = 'superzoshyt-runtime-v28';
const KEEP = [SHELL_CACHE, RUNTIME_CACHE];
const SHELL_URLS = ['./index.html', './'];
// Authenticated AI APIs: always go to the network, never answer from cache.
const NO_CACHE_HOSTS = ['api.openai.com', 'auth.openai.com', 'api.groq.com'];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(SHELL_CACHE)
      .then((cache) => Promise.all(SHELL_URLS.map((u) => cache.add(u).catch(() => {}))))
      .catch(() => {})
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    try {
      const keys = await caches.keys();
      await Promise.all(keys.filter((k) => KEEP.indexOf(k) === -1).map((k) => caches.delete(k)));
    } catch (e) { }
    if (self.registration.navigationPreload) {
      try { await self.registration.navigationPreload.disable(); } catch (e) { }
    }
    await self.clients.claim();
  })());
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  let url;
  try { url = new URL(req.url); } catch (e) { return; }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return;
  if (NO_CACHE_HOSTS.indexOf(url.hostname) !== -1) return;
  // serve.py relays ChatGPT API calls under api/ on the same origin.
  if (url.origin === self.location.origin && url.pathname.indexOf(new URL('api/', self.registration.scope).pathname) === 0) return;

  
  if (req.mode === 'navigate') {
    const scopePath = new URL(self.registration.scope).pathname;
    const isShell = url.pathname === scopePath || url.pathname === scopePath + 'index.html';
    event.respondWith((async () => {
      try {
        const fresh = await fetch(req);
        // Only the app itself may refresh the shell cache (not e.g. auth/callback/).
        if (isShell && fresh.ok) {
          const cache = await caches.open(SHELL_CACHE);
          SHELL_URLS.forEach((u) => cache.put(u, fresh.clone()).catch(() => { }));
        }
        return fresh;
      } catch (err) {
        const cache = await caches.open(SHELL_CACHE);
        for (const u of SHELL_URLS) {
          const hit = await cache.match(u);
          if (hit) return hit;
        }
        return new Response('<!doctype html><meta charset="utf-8"><title>Суперзошит</title><h1>Немає з\'єднання</h1>', {
          status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' }
        });
      }
    })());
    return;
  }

  
  event.respondWith((async () => {
    const cache = await caches.open(RUNTIME_CACHE);
    const hit = await cache.match(req);
    const network = fetch(req).then((res) => {
      if (res && (res.ok || res.type === 'opaque')) cache.put(req, res.clone()).catch(() => { });
      return res;
    }).catch(() => null);
    if (hit) { network.catch(() => { }); return hit; }
    const res = await network;
    return res || new Response('', { status: 504, statusText: 'Offline' });
  })());
});
