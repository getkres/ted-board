/* Local tangent-plane geometry. No altitude or plays-like adjustments. */
(function (root) {
  'use strict';
  const R = 6371008.8;
  const radians = Math.PI / 180;
  function project(point, origin) {
    return [(point[0] - origin[0]) * radians * R * Math.cos(origin[1] * radians),
      (point[1] - origin[1]) * radians * R];
  }
  function unproject(point, origin) {
    return [origin[0] + point[0] / (radians * R * Math.cos(origin[1] * radians)),
      origin[1] + point[1] / (radians * R)];
  }
  function ringOf(ring) {
    if (!Array.isArray(ring) || ring.length < 4 || ring.some(p => !Array.isArray(p) || p.length < 2 || !p.slice(0, 2).every(Number.isFinite))) {
      throw new Error('A valid green polygon is required.');
    }
    const last = ring[ring.length - 1], first = ring[0];
    return last[0] === first[0] && last[1] === first[1] ? ring.slice(0, -1) : ring;
  }
  function contains(point, ring) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const a = ring[j], b = ring[i];
      const cross = (point[0] - a[0]) * (b[1] - a[1]) - (point[1] - a[1]) * (b[0] - a[0]);
      if (Math.abs(cross) < 1e-7 && point[0] >= Math.min(a[0], b[0]) - 1e-7 && point[0] <= Math.max(a[0], b[0]) + 1e-7 && point[1] >= Math.min(a[1], b[1]) - 1e-7 && point[1] <= Math.max(a[1], b[1]) + 1e-7) return true;
      if ((a[1] > point[1]) !== (b[1] > point[1]) && point[0] < (b[0] - a[0]) * (point[1] - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
    }
    return inside;
  }
  function center(ring) {
    const clean = ringOf(ring), origin = clean[0], pts = clean.map(p => project(p, origin));
    let area = 0, x = 0, y = 0;
    pts.forEach((a, i) => {
      const b = pts[(i + 1) % pts.length], cross = a[0] * b[1] - b[0] * a[1];
      area += cross; x += (a[0] + b[0]) * cross; y += (a[1] + b[1]) * cross;
    });
    if (Math.abs(area) < 0.01) throw new Error('The green polygon has no usable area.');
    const c = [x / (3 * area), y / (3 * area)];
    if (!contains(c, pts)) throw new Error('This green needs a manually verified center.');
    return unproject(c, origin);
  }
  const cross = (a, b) => a[0] * b[1] - a[1] * b[0];
  function yardages(location, ring) {
    if (!Array.isArray(location) || location.length < 2 || !location.slice(0, 2).every(Number.isFinite) || Math.abs(location[1]) > 90 || Math.abs(location[0]) > 180) throw new Error('Invalid GPS location.');
    const c = center(ring), pts = ringOf(ring).map(p => project(p, c)), p = project(location, c);
    const length = Math.hypot(...p), d = length > 1e-6 ? [-p[0] / length, -p[1] / length] : [0, 1];
    const hits = [];
    pts.forEach((a, i) => {
      const b = pts[(i + 1) % pts.length], edge = [b[0] - a[0], b[1] - a[1]], delta = [a[0] - p[0], a[1] - p[1]], divisor = cross(d, edge);
      if (Math.abs(divisor) < 1e-9) return;
      const t = cross(delta, edge) / divisor, u = cross(delta, d) / divisor;
      if (t >= -1e-6 && u >= -1e-8 && u <= 1 + 1e-8) hits.push(Math.max(0, t));
    });
    if (!hits.length) throw new Error('No green boundary found along the center line.');
    const onGreen = contains(p, pts);
    return {front: (onGreen ? 0 : Math.min(...hits)) / 0.9144, center: length / 0.9144,
      back: Math.max(...hits) / 0.9144, onGreen, centerPoint: c};
  }
  function demoLocation(ring, yards, bearingDegrees = 180) {
    const c = center(ring), angle = bearingDegrees * radians, meters = yards * 0.9144;
    return unproject([Math.sin(angle) * meters, Math.cos(angle) * meters], c);
  }
  const api = {project, unproject, contains, center, yardages, demoLocation};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.GolfGeometry = api;
})(typeof window !== 'undefined' ? window : this);
