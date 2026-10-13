// Service worker da Kontiq: abre depressa e funciona com rede fraca.
// - Ficheiros da aplicação (/assets/…): cache primeiro (têm o hash no nome).
// - Páginas: rede primeiro; sem rede, a última versão guardada.
// - API (/api/…): nunca guardada — os dados são sempre os do servidor.
const CACHE = 'kontiq-v1'

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(['/', '/manifest.webmanifest', '/icones/icone-192.png'])).then(() => self.skipWaiting()))
})

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()))
})

self.addEventListener('fetch', (e) => {
  const req = e.request
  const url = new URL(req.url)
  if (req.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api/')) return
  if (url.pathname.startsWith('/assets/') || url.pathname.startsWith('/icones/')) {
    e.respondWith(caches.match(req).then((r) => r || fetch(req).then((res) => {
      const copia = res.clone()
      if (res.ok) caches.open(CACHE).then((c) => c.put(req, copia))
      return res
    })))
    return
  }
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).then((res) => {
      const copia = res.clone()
      if (res.ok) caches.open(CACHE).then((c) => c.put('/', copia))
      return res
    }).catch(() => caches.match('/')))
  }
})
