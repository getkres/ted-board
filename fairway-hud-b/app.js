(function () {
  'use strict';
  const $ = id => document.getElementById(id), g = window.GolfGeometry, course = window.GOLF_COURSE;
  if (!g || !course || !course.features.length) { $('status').textContent = 'Course data could not load. Keep all prototype files together, and reload.'; return; }
  let mode = 'demo', watch = null, fix = null, lastError = '', selected = course.features[0], demoBearing = selected.properties.demoBearing;
  const m=window.GolfMinimap, view=window.GolfMinimapView, params=new URLSearchParams(location.search);
  const preferenceKey='dgc-fairway-hud-display-v1';
  let hudHidden=false, yardageOnly=false;
  let fieldLog=null, loggedMap=false;
  try {
    const saved=JSON.parse(localStorage.getItem(preferenceKey));
    hudHidden=saved?.hudHidden===true;yardageOnly=saved?.yardageOnly===true;
  } catch(error) { /* Storage may be unavailable, full, or contain invalid JSON. */ }
  function saveDisplay() {
    try { localStorage.setItem(preferenceKey,JSON.stringify({hudHidden,yardageOnly})); }
    catch(error) { /* Keep the current session usable when storage is blocked. */ }
  }
  function syncDisplay() {
    const lens=document.querySelector('.lens');
    lens.classList.toggle('hud-hidden',hudHidden);
    lens.dataset.ready='true';
    $('yardage-panel').hidden=hudHidden;
    $('toggle-hud').setAttribute('aria-pressed',String(hudHidden));
    $('toggle-hud').textContent=hudHidden?'Show HUD':'Hide HUD';
    $('yardage-only').checked=yardageOnly;
  }
  function toggleHUD() {
    hudHidden=!hudHidden;saveDisplay();render('toggle');
    if(lensOnly)document.querySelector('.lens').focus({preventScroll:true});
  }
  function toggleYardage() { yardageOnly=!yardageOnly;saveDisplay();render('toggle'); }
  let nearGreen=false, onGreen=false, pin=null, pinFrame=null, watchGeneration=0, requestedAt=0;
  const terrainProvider=m.provider(window.GOLF_SLOPE);
  const MAX_AGE = 20000, MAX_ACCURACY = 30, MAX_RANGE = 5000;
  course.features.forEach(feature => {
    const option = document.createElement('option'); option.value = feature.properties.hole;
    option.textContent = `Hole ${feature.properties.hole} · Par ${feature.properties.par}`; $('hole').append(option);
  });
  $('data-date').textContent = `Map snapshot: ${String(course.retrieved_utc).slice(0,10)}.`;
  function stopGPS() { watchGeneration++; if (watch !== null) navigator.geolocation.clearWatch(watch); watch = null; fix = null; cancelDrift(); }
  function hideNumbers() {
    ['front','center','back'].forEach(id => { $(id).textContent = '--';$(id).classList.remove('long-yardage'); });
    $('minimap-panel').setAttribute('hidden','');nearGreen=false;onGreen=false;
    logMapSwitch(false,undefined,'gps-lost');
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
  // Size and orientation have their own sticky boundary, separate from near mode.
  function onGreenMode(location,ring,previous) {
    const pts=ring.map(p=>g.project(p,location)),inside=g.contains([0,0],pts);
    if(!inside)return previous && m.edgeDistance(location,ring)<4;
    if(previous)return true;
    const clearance=Math.min(...pts.map((a,i)=>{
      const b=pts[(i+1)%pts.length],dx=b[0]-a[0],dy=b[1]-a[1];
      const t=Math.max(0,Math.min(1,-(a[0]*dx+a[1]*dy)/(dx*dx+dy*dy || 1)));
      return Math.hypot(a[0]+t*dx,a[1]+t*dy);
    }));
    return clearance>=2;
  }
  function render(reason='position') {
    if(!fix)cancelDrift();
    syncDisplay();
    $('hole-label').textContent=`HOLE ${selected.properties.hole} · PAR ${selected.properties.par} · YARDS`;
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
      ['front','center','back'].forEach(id => {
        const value=String(Math.round(result[id]));$(id).textContent=value;
        $(id).classList.toggle('long-yardage',value.length>3);
      });
      if (mode === 'gps') $('status').textContent = `${note}. Horizontal yardage to the mapped green. Check the selected hole.`;
      nearGreen=m.greenMode(location,selected.geometry.coordinates[0],nearGreen);
      onGreen=onGreenMode(location,selected.geometry.coordinates[0],onGreen);
      const showGreen=nearGreen && !yardageOnly && !hudHidden;
      $('minimap-panel').toggleAttribute('hidden',!showGreen);
      logMapSwitch(showGreen,result.center,reason);
      if(showGreen) view.render($('minimap-panel'),{player:location,ring:selected.geometry.coordinates[0],onGreen,approachBearing:selected.properties.demoBearing,terrain:terrainProvider.getGreen(`way/${selected.properties.osm_id}`,selected.geometry.coordinates[0])});
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
    nearGreen=false;onGreen=false;pin=null;drawPinEditor();
    demoBearing = selected.properties.demoBearing; $('bearing').value = Math.round(demoBearing); $('bearing-value').textContent = 'From the fairway'; render();
  });
  $('distance').addEventListener('input', () => { $('distance-value').textContent = `${$('distance').value} yd`; render(); });
  $('bearing').addEventListener('input', () => { demoBearing = Number($('bearing').value); $('bearing-value').textContent = `${demoBearing}° from north`; render(); });
  $('bearing').value = Math.round(demoBearing);
  $('green-demo').addEventListener('click',()=>{
    stopGPS();mode='demo';lastError='';selected=course.features[0];$('hole').value='1';nearGreen=false;onGreen=false;pin=null;
    $('distance').value='20';$('distance-value').textContent='20 yd';demoBearing=selected.properties.demoBearing;$('bearing').value=Math.round(demoBearing);$('bearing-value').textContent='From the fairway';drawPinEditor();render();
  });
  function setLighting() { document.querySelector('.lens').dataset.lighting=$('lighting').value; }
  $('lighting').addEventListener('change',setLighting);
  $('terrain').addEventListener('change',()=>render());
  $('toggle-hud').addEventListener('click',toggleHUD);
  $('yardage-only').addEventListener('change',toggleYardage);
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
  function fieldSample(type,direction) {
    const row={type,time:new Date().toISOString()};
    if(direction)row.direction=direction;
    if(mode==='gps' && fix) {
      if(Number.isFinite(fix.timestamp))row.fix_time=new Date(fix.timestamp).toISOString();
      row.lat=fix.coords.latitude;row.lon=fix.coords.longitude;row.accuracy=fix.coords.accuracy;
      try {
        const yards=g.yardages([row.lon,row.lat],selected.geometry.coordinates[0]);
        row.center=yards.center;
        if(type!=='switch') { row.front=yards.front;row.back=yards.back; }
      } catch(error) { /* Keep the raw fix even when yardage is unavailable. */ }
    }
    return row;
  }
  function logMapSwitch(showMap,center,reason='position') {
    if(fieldLog && showMap!==loggedMap) {
      const row=fieldSample('switch',showMap?'to-map':'to-yardage');
      row.reason=reason;
      if(Number.isFinite(center))row.center=center;
      fieldLog.append(row);
      updateFieldLog();
    }
    loggedMap=showMap;
  }
  let driftTimer=null,driftRemaining=0,fieldMessage='';
  function cancelDrift() {
    if(driftTimer==null)return;
    clearInterval(driftTimer);driftTimer=null;fieldMessage='Drift cancelled. GPS fix unavailable.';updateFieldLog();
  }
  function updateFieldLog() {
    if(!fieldLog)return;
    $('field-log-status').textContent=[`${fieldLog.count()} rows.`,driftTimer!==null?`Drift: ${driftRemaining} second${driftRemaining===1?'':'s'} remaining.`:'',fieldMessage,fieldLog.healthy()?'':'Storage unavailable. Export before leaving this page.'].filter(Boolean).join(' ');
    $('field-drift').textContent=driftTimer!==null?'Cancel Drift':'Start Drift (60 Seconds)';
  }
  if(!lensOnly && window.GolfFieldLog) {
    let storage;
    try { storage=window.localStorage; } catch(error) { /* Report storage failure below. */ }
    fieldLog=window.GolfFieldLog.createStore(storage);
    const panel=document.createElement('section');
    panel.id='field-log';panel.setAttribute('aria-label','Field log');
    panel.innerHTML='<h2>Field Log</h2><p class="control-note">Records phone GPS, accuracy in meters, and yardages. Keep this page visible during Drift. Missing GPS fields are blank.</p><div class="field-log-buttons"><button id="field-mark" type="button">Mark</button><button id="field-drift" type="button">Start Drift (60 Seconds)</button><button id="field-export" type="button">Export CSV</button><button id="field-clear" type="button">Clear</button></div><p id="field-log-status" class="control-note" role="status" aria-live="polite"></p>';
    document.querySelector('.controls').append(panel);
    $('field-mark').addEventListener('click',()=>{
      if(mode!=='gps' || !fix)fieldMessage='Use My GPS and wait for a fix before marking.';
      else { fieldLog.append(fieldSample('mark'));fieldMessage='Mark saved.'; }
      updateFieldLog();
    });
    $('field-drift').addEventListener('click',()=>{
      if(driftTimer!==null) {
        clearInterval(driftTimer);driftTimer=null;fieldMessage='Drift cancelled.';updateFieldLog();return;
      }
      if(mode!=='gps' || !fix) { fieldMessage='Use My GPS and wait for a fix before starting Drift.';updateFieldLog();return; }
      driftRemaining=60;fieldMessage='';
      driftTimer=setInterval(()=>{
        if(mode!=='gps' || !fix) { cancelDrift();return; }
        fieldLog.append(fieldSample('drift'));driftRemaining--;
        if(driftRemaining===0) { clearInterval(driftTimer);driftTimer=null;fieldMessage='Drift complete.'; }
        updateFieldLog();
      },1000);
      updateFieldLog();
    });
    $('field-clear').addEventListener('click',()=>{
      if(!window.confirm('Clear every saved field log row?'))return;
      if(driftTimer!==null) { clearInterval(driftTimer);driftTimer=null; }
      fieldLog.clear();fieldMessage='Log cleared.';updateFieldLog();
    });
    $('field-export').addEventListener('click',async()=>{
      const blob=new Blob([fieldLog.csv()],{type:'text/csv;charset=utf-8'});
      const name=`fairway-field-log-${new Date().toISOString().replace(/[:.]/g,'-')}.csv`;
      try {
        if(typeof File==='function' && navigator.share && navigator.canShare) {
          const file=new File([blob],name,{type:'text/csv'});
          if(navigator.canShare({files:[file]})) {
            await navigator.share({files:[file]});fieldMessage='CSV shared.';updateFieldLog();return;
          }
        }
      } catch(error) {
        if(error.name==='AbortError') { fieldMessage='Share cancelled.';updateFieldLog();return; }
      }
      const url=URL.createObjectURL(blob),link=document.createElement('a');
      link.href=url;link.download=name;document.body.append(link);link.click();link.remove();
      setTimeout(()=>URL.revokeObjectURL(url),60000);
      fieldMessage='CSV download requested.';updateFieldLog();
    });
    updateFieldLog();
  }
  document.body.classList.toggle('panel-only',lensOnly);
  setLighting();drawPinEditor();
  setInterval(() => { if(mode === 'gps') render(); },1000);
  function suspendGPS() { if(mode==='gps') { stopGPS();lastError='Location paused. Activate yardage to resume phone GPS.';render(); } }
  window.addEventListener('pagehide',suspendGPS);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)suspendGPS();});
  const lens=document.querySelector('.lens');
  $('yardage-panel').addEventListener('click',()=>{if(lensOnly)toggleHUD();});
  // The HUD owns the page in lens mode. The simulator can send input to body
  // after its sidebar takes focus. Accept that path without consuming keys
  // from simulator controls or the phone preview. Native Back stays untouched.
  document.addEventListener('keydown',event=>{
    if(!lensOnly || !['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Enter'].includes(event.key))return;
    if(!lens.contains(event.target) && ![document.body,document.documentElement,document].includes(event.target))return;
    event.preventDefault();if(event.repeat)return;
    if(!lens.contains(event.target))lens.focus({preventScroll:true});
    if(event.key==='ArrowLeft' || event.key==='ArrowRight') {
      const index=course.features.indexOf(selected),step=event.key==='ArrowRight'?1:-1;
      $('hole').value=course.features[(index+step+course.features.length)%course.features.length].properties.hole;
      $('hole').dispatchEvent(new Event('change'));
    } else if(event.key==='ArrowUp') toggleYardage();
    else if(event.key==='ArrowDown') $('gps').click();
    else toggleHUD();
  });
  if(lensOnly)lens.focus({preventScroll:true});
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
