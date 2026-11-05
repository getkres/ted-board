(function () {
  'use strict';
  const $ = id => document.getElementById(id), g = window.GolfGeometry, course = window.GOLF_COURSE;
  if (!g || !course || !course.features.length) { $('status').textContent = 'Course data could not load. Keep all prototype files together, and reload.'; return; }
  let mode = 'demo', watch = null, fix = null, lastError = '', selected = course.features[0], demoBearing = selected.properties.demoBearing;
  const m=window.GolfMinimap, view=window.GolfMinimapView, params=new URLSearchParams(location.search);
  let nearGreen=false, pin=null, pinFrame=null, watchGeneration=0, requestedAt=0;
  const terrainProvider=m.provider(window.GOLF_SLOPE);
  const MAX_AGE = 20000, MAX_ACCURACY = 30, MAX_RANGE = 5000;
  course.features.forEach(feature => {
    const option = document.createElement('option'); option.value = feature.properties.hole;
    option.textContent = `Hole ${feature.properties.hole} · Par ${feature.properties.par}`; $('hole').append(option);
  });
  $('data-date').textContent = `Map snapshot: ${String(course.retrieved_utc).slice(0,10)}.`;
  function stopGPS() { watchGeneration++; if (watch !== null) navigator.geolocation.clearWatch(watch); watch = null; fix = null; }
  function hideNumbers() {
    ['front','center','back'].forEach(id => $(id).textContent = '--');
    $('minimap-panel').setAttribute('hidden','');nearGreen=false;
  }
  function drawPinEditor() {
    pinFrame=view.editor($('pin-map'),selected.geometry.coordinates[0],pin || g.center(selected.geometry.coordinates[0]),!!pin);
    $('pin-status').textContent=pin ? 'Manual pin. Approximate map position only.' : 'Green center (default).';
  }
  function setPin(point) {
    const ring=selected.geometry.coordinates[0],center=g.center(ring);
    if(!point.every(Number.isFinite) || !g.contains(g.project(point,center),ring.map(p=>g.project(p,center)))) {
      $('pin-status').textContent='Tap inside the green. Pin position was kept.';return;
    }
    pin=point;drawPinEditor();render();
  }
  function render() {
    $('demo').setAttribute('aria-pressed',String(mode === 'demo')); $('gps').setAttribute('aria-pressed',String(mode === 'gps'));
    $('demo-controls').hidden = mode !== 'demo';
    let location, note;
    if (mode === 'demo') {
      location = g.demoLocation(selected.geometry.coordinates[0],Number($('distance').value),demoBearing);
      note = 'Simulated location'; $('status').textContent = 'Demo uses a fake location. Your GPS is off.';
    } else {
      if (lastError) { hideNumbers('Location unavailable'); $('status').textContent = lastError; return; }
      if (!fix) { hideNumbers('Waiting for location'); $('status').textContent = (Date.now()-requestedAt>15000 ? 'GPS is still unavailable. Check the paired phone and location permission, or activate again to retry.' : 'Waiting for a GPS fix. Keep this page open, or use Desk Demo.'); return; }
      const age = Date.now()-fix.timestamp, accuracy = fix.coords.accuracy;
      if (!Number.isFinite(fix.timestamp) || age > MAX_AGE || age < -5000) { hideNumbers('GPS fix is stale'); $('status').textContent = 'Your location is over 20 seconds old. Waiting for a fresh fix. Desk Demo is available.'; return; }
      if (!Number.isFinite(accuracy) || accuracy < 0 || accuracy > MAX_ACCURACY) { hideNumbers('GPS accuracy is too low'); $('status').textContent = 'GPS error exceeds 30 m. Move into open sky, or use Desk Demo.'; return; }
      location = [fix.coords.longitude,fix.coords.latitude]; note = `GPS ±${Math.round(accuracy/0.9144)} yd · ${Math.max(0,Math.floor(age/1000))}s ago`;
    }
    try {
      const result = g.yardages(location,selected.geometry.coordinates[0]);
      if (mode === 'gps' && result.center*0.9144 > MAX_RANGE) { hideNumbers('Away from this course'); $('status').textContent = 'You are over 5 km from this green. Choose the correct hole at Haggin Oaks, or use Desk Demo.'; return; }
      ['front','center','back'].forEach(id => $(id).textContent = Math.round(result[id]));
      if (mode === 'gps') $('status').textContent = `${note}. Horizontal yardage to the mapped green. Check the selected hole.`;
      nearGreen=m.greenMode(location,selected.geometry.coordinates[0],nearGreen);
      $('minimap-panel').toggleAttribute('hidden',!nearGreen);
      if(nearGreen) view.render($('minimap-panel'),{player:location,pin:pin || result.centerPoint,ring:selected.geometry.coordinates[0],terrain:terrainProvider.getGreen(`way/${selected.properties.osm_id}`,selected.geometry.coordinates[0]),terrainMode:$('terrain').value});
    } catch (error) { hideNumbers('Location or map error'); $('status').textContent = 'Could not calculate this yardage. Choose another hole, or reload the page.'; }
  }
  $('gps').addEventListener('click', () => {
    stopGPS(); mode = 'gps'; lastError = ''; render();
    if (!window.isSecureContext) { lastError = 'GPS needs HTTPS on a phone, or localhost on this computer. Open a secure URL, or use Desk Demo.'; render(); return; }
    if (!navigator.geolocation) { lastError = 'This browser has no GPS access. Use a browser with location support, or Desk Demo.'; render(); return; }
    requestedAt=Date.now();const generation=watchGeneration;
    try { watch = navigator.geolocation.watchPosition(position => { if(mode !== 'gps' || generation!==watchGeneration) return; fix = position; lastError = ''; render(); }, error => {
      if(mode !== 'gps' || generation!==watchGeneration) return;
      fix = null;
      lastError = error.code === 1 ? 'Location permission is blocked. Allow location for this page in your browser settings, or use Desk Demo.' : error.code === 3 ? 'GPS timed out. Move into open sky and tap Use My GPS to retry, or use Desk Demo.' : 'GPS location is unavailable. Move into open sky and tap Use My GPS to retry, or use Desk Demo.';
      render();
    }, {enableHighAccuracy:true});
    } catch(error) { lastError='GPS location is unavailable. Activate again to retry, or use Desk Demo.';render(); }
  });
  $('demo').addEventListener('click', () => { stopGPS(); mode = 'demo'; lastError = ''; render(); });
  $('hole').addEventListener('change', () => {
    selected = course.features.find(f => String(f.properties.hole) === $('hole').value);
    nearGreen=false;pin=null;drawPinEditor();
    demoBearing = selected.properties.demoBearing; $('bearing').value = Math.round(demoBearing); $('bearing-value').textContent = 'From the fairway'; render();
  });
  $('distance').addEventListener('input', () => { $('distance-value').textContent = `${$('distance').value} yd`; render(); });
  $('bearing').addEventListener('input', () => { demoBearing = Number($('bearing').value); $('bearing-value').textContent = `${demoBearing}° from north`; render(); });
  $('bearing').value = Math.round(demoBearing);
  $('green-demo').addEventListener('click',()=>{
    stopGPS();mode='demo';lastError='';selected=course.features[0];$('hole').value='1';nearGreen=false;pin=null;
    $('distance').value='20';$('distance-value').textContent='20 yd';demoBearing=225;$('bearing').value='225';$('bearing-value').textContent='225° from north';drawPinEditor();render();
  });
  function setLighting() { document.querySelector('.lens').dataset.lighting=$('lighting').value; }
  $('lighting').addEventListener('change',setLighting);
  $('terrain').addEventListener('change',render);
  if(params.get('terrain')==='heat')$('terrain').value='heat';
  $('pin-map').addEventListener('click',event=>{
    const matrix=$('pin-map').getScreenCTM();if(!matrix)return;
    const point=new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse());
    setPin(pinFrame.toGeo([point.x,point.y]));
  });
  $('pin-map').addEventListener('keydown',event=>{
    const delta={ArrowUp:[0,1],ArrowDown:[0,-1],ArrowLeft:[-1,0],ArrowRight:[1,0]}[event.key];
    if(!delta)return;event.preventDefault();setPin(g.unproject(delta,pin || g.center(selected.geometry.coordinates[0])));
  });
  $('pin-center').addEventListener('click',()=>{pin=null;drawPinEditor();render();});
  if(params.get('light')==='bright')$('lighting').value='bright';
  const lensOnly=!params.has('phone') && !document.body.classList.contains('phone-preview');
  document.body.classList.toggle('panel-only',lensOnly);
  setLighting();drawPinEditor();
  setInterval(() => { if(mode === 'gps') render(); },1000);
  function suspendGPS() { if(mode==='gps') { stopGPS();lastError='Location paused. Activate yardage to resume phone GPS.';render(); } }
  window.addEventListener('pagehide',suspendGPS);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)suspendGPS();});
  const lens=document.querySelector('.lens');
  $('yardage-panel').addEventListener('click',()=>{if(lensOnly)$('gps').click();});
  // This custom HUD owns the lens. Consume each handled key so the host cannot
  // also spatially traverse or activate it. The native Back action is untouched.
  lens.addEventListener('keydown',event=>{
    if(!lensOnly || !['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Enter'].includes(event.key))return;
    event.preventDefault();if(event.repeat)return;
    if(event.key==='ArrowLeft' || event.key==='ArrowRight') {
      const index=course.features.indexOf(selected),step=event.key==='ArrowRight'?1:-1;
      $('hole').value=course.features[(index+step+course.features.length)%course.features.length].properties.hole;
      $('hole').dispatchEvent(new Event('change'));
    } else if(event.key==='ArrowUp' || event.key==='ArrowDown') {
      $('terrain').value=event.key==='ArrowUp'?'heat':'arrows';render();
    } else $('yardage-panel').click();
  });
  if(lensOnly)$('yardage-panel').focus({preventScroll:true});
  if('serviceWorker' in navigator && window.isSecureContext && location.protocol!=='file:') {
    navigator.serviceWorker.register('./sw.js').then(()=>navigator.serviceWorker.ready).then(()=>{
      $('offline-status').textContent='Offline shell and Haggin Oaks course data are ready. Cache may be cleared by the device.';
    }).catch(()=>{$('offline-status').textContent='Offline setup failed. Keep a connection, and reload to retry.';});
  } else $('offline-status').textContent='Offline shell requires HTTPS or localhost and service worker support.';
  if(lensOnly || params.has('green')) {
    $('green-demo').click();
    if(lensOnly) {
      $('distance').value=params.get('state')==='off' ? '150' : params.get('state')==='on' ? '8' : '20';
      $('distance').dispatchEvent(new Event('input'));
    }
  } else render();
})();
