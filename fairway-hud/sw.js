'use strict';
// Scope both fetches and cleanup to this app, even on a shared Pages origin.
const PREFIX='dgc-fairway-hud-'+encodeURIComponent(new URL(self.registration.scope).pathname)+'-';
const CACHE=PREFIX+'2026-11-05-8a6da6c9cfa97a0b';
const FILES=['./','index.html','style.css','course-data.js','course.geojson','geometry.js','minimap.js','slope-data.js','minimap-view.js','app.js','icon.svg','terrain-notice.html','.well-known/meta-wearables-manifest.json'];
const URLS=FILES.map(file=>new URL(file,self.registration.scope).href);
self.addEventListener('install',event=>{
  event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(URLS)));
});
self.addEventListener('activate',event=>{
  event.waitUntil((async()=>{
    const names=await caches.keys();
    await Promise.all(names.filter(name=>name.startsWith(PREFIX) && name!==CACHE).map(name=>caches.delete(name)));
    await self.clients.claim();
  })());
});
self.addEventListener('fetch',event=>{
  const request=event.request,url=new URL(request.url);
  // Only known static files are cached. Never cache arbitrary origin data.
  const canonical=url.origin+url.pathname;
  if(request.method!=='GET' || !URLS.includes(canonical))return;
  event.respondWith((async()=>{
    const cache=await caches.open(CACHE),cached=await cache.match(canonical);
    // Keep the complete installed release together while an updated worker waits.
    if(cached)return cached;
    return fetch(request);
  })());
});
