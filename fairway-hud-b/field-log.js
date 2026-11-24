(function(root) {
  'use strict';
  const key='dgc-fairway-hud-field-log-v1';
  function toCSV(rows) {
    const columns=['type','time','lat','lon','accuracy','front','center','back','direction','fix_time','reason'];
    const escape=value=>/[",\r\n]/.test(value)?'"'+value.replace(/"/g,'""')+'"':value;
    return ['type,time,lat,lon,accuracy_m,front_yd,center_yd,back_yd,direction,fix_time,reason', ...rows.map(row=>columns.map(column=>{
      const value=row[column];
      if(value==null || (typeof value==='number' && !Number.isFinite(value)))return '';
      return escape((column==='lat' || column==='lon') && typeof value==='number'?value.toFixed(8):String(value));
    }).join(','))].join('\r\n');
  }
  function createStore(storage) {
    let rows=[],healthy=true,raw=null,corrupt=null;
    try {
      raw=storage.getItem(key);
      const saved=JSON.parse(raw);
      if(saved!==null && !Array.isArray(saved))throw Error('Invalid field log');
      rows=saved || [];
    } catch(error) { healthy=false;corrupt=raw; }
    function persist() {
      try {
        if(corrupt!==null) { storage.setItem(key+'-corrupt',corrupt);corrupt=null; }
        storage.setItem(key,JSON.stringify(rows));healthy=true;return true;
      }
      catch(error) { healthy=false;return false; }
    }
    return {
      append(row) { rows.push(row);return persist(); },
      clear() { rows=[];return persist(); },
      count:()=>rows.length,
      healthy:()=>healthy,
      csv:()=>toCSV(rows),
    };
  }
  const api={toCSV,createStore};
  if(typeof module==='object' && module.exports)module.exports=api;
  else root.GolfFieldLog=api;
})(typeof window==='object'?window:globalThis);
