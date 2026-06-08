const CACHE_NAME = 'zenhanzi-v3';
const urlsToCache = [
  './',
  './index.html',
  './style.css',
  './app.js',
  './data/vocabulary.json',
  './manifest.json'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(urlsToCache))
  );
  self.skipWaiting();
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request).then(response => {
      if (response) return response;
      return fetch(event.request).then(fetchRes => {
        if (!fetchRes || fetchRes.status !== 200) return fetchRes;
        const resClone = fetchRes.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(event.request, resClone));
        return fetchRes;
      });
    }).catch(() => caches.match('./index.html'))
  );
});