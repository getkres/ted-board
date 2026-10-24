'use strict';

const AgingWip = (() => {
  const HOUR = 3600000;
  const STALE_AFTER = 300000;
  const CLOSED = new Set(['done', 'closed', 'completed', 'killed', 'cancelled', 'archived', 'rejected']);
  const text = value => typeof value === 'string' ? value.trim() : '';
  const list = value => Array.isArray(value) ? value : [];
  const timestamp = value => {
    if (typeof value !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(value)) return null;
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : null;
  };
  const duration = value => {
    const minutes = Math.max(0, Math.floor(value / 60000));
    if (minutes < 60) return minutes + 'm';
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return hours + 'h' + (minutes % 60 ? ' ' + minutes % 60 + 'm' : '');
    return Math.floor(hours / 24) + 'd' + (hours % 24 ? ' ' + hours % 24 + 'h' : '');
  };
  const oldest = (a, b) => (b.ageMs ?? Infinity) - (a.ageMs ?? Infinity) || a.id.localeCompare(b.id);
  function normalize(raw, index, now) {
    raw = raw && typeof raw === 'object' ? raw : {};
    const defects = [];
    const owner = /^(ted|sebastian|external|worker:[^\s:][^\s]*)$/.test(text(raw.owner)) ? text(raw.owner) : 'unknown';
    if (owner === 'unknown') defects.push('Missing or invalid owner');
    const dueAt = timestamp(raw.next_action_due);
    if (dueAt === null) defects.push('Missing or invalid deadline');
    const startedAt = timestamp(raw.action_started_at);
    const ageMs = startedAt === null || startedAt > now + 15000 ? null : Math.max(0, now - startedAt);
    if (ageMs === null) defects.push('Missing or invalid action start');
    const status = text(raw.status) || 'open';
    if (!['open', 'dead_letter'].includes(status)) defects.push('Unknown open status');
    if (!text(raw.id)) defects.push('Missing item ID');
    const overdue = dueAt !== null && dueAt <= now;
    return {
      id: text(raw.id) || 'missing-id:' + index,
      kind: text(raw.kind) || 'unknown',
      card_id: text(raw.card_id) || null,
      owner,
      summary: text(raw.summary) || text(raw.title) || text(raw.id) || 'Unidentified work item',
      stage: text(raw.stage) || 'Unknown stage',
      status,
      priority: [0, 1, 2].includes(raw.priority) ? raw.priority : null,
      startedAt: ageMs === null ? null : startedAt,
      dueAt,
      ageMs,
      ageLabel: ageMs === null ? 'Unknown action age' : duration(ageMs),
      overdue,
      dueLabel: dueAt === null ? 'Unknown deadline' : overdue ? 'Overdue by ' + duration(now - dueAt) : 'Due in ' + duration(dueAt - now),
      reviewOverdue: ageMs !== null && ageMs >= 6 * HOUR,
      reviewLabel: ageMs === null ? 'Review age unknown' : ageMs >= 6 * HOUR ? 'Review overdue by ' + duration(ageMs - 6 * HOUR) : 'Review due in ' + duration(6 * HOUR - ageMs),
      defects,
    };
  }
  function fallback(cards, jobs, approvals) {
    const rows = [];
    for (const card of list(cards)) {
      if (!card || !['needs_you', 'ted_doing', 'up_next'].includes(card.section)) continue;
      rows.push({...card, id: 'card:' + card.id, card_id: card.id, kind: 'card', summary: card.title, stage: card.section, status: 'open'});
    }
    for (const job of list(jobs)) {
      if (!job || job.lane_summary === true || job.id === 'fresh-ted-health' || !['running', 'queued', 'waiting_approval', 'untracked', 'dead_letter'].includes(job.status)) continue;
      const startedDate = typeof job.started_at === 'number' ? new Date(job.started_at * 1000) : null;
      const started = startedDate ? Number.isFinite(startedDate.getTime()) ? startedDate.toISOString() : null : job.started_at;
      rows.push({...job, id: 'job:' + job.id, owner: job.owner || (job.id ? 'worker:' + job.id : null), kind: 'job', summary: job.title, action_started_at: job.action_started_at || started, stage: job.status, status: job.status === 'dead_letter' ? 'dead_letter' : 'open'});
    }
    for (const approval of list(approvals)) {
      if (!approval || !['pending', 'approved', 'pending_review'].includes(approval.status)) continue;
      rows.push({...approval, id: 'approval:' + approval.id, kind: 'approval', stage: approval.status, status: 'open'});
    }
    return rows;
  }
  function prepare({reconciliation = null, cards = [], jobs = [], approvals = [], loaded = false, error = '', now = Date.now()} = {}) {
    const available = Boolean(reconciliation && Array.isArray(reconciliation.items));
    const generatedAt = timestamp(reconciliation?.generated_at);
    const stale = !available || generatedAt === null || generatedAt > now + 15000 || now - generatedAt > STALE_AFTER;
    const warnings = [];
    if (error) warnings.push('Jobs refresh failed: ' + error + ' Displayed work may be out of date.');
    else if (!loaded) warnings.push('Reconciliation is loading. Work coverage is not yet known.');
    if (!available) warnings.push('Reconciliation is unavailable. Showing known open cards, workers, and approvals only. Full work coverage is unknown.');
    else if (stale) warnings.push(generatedAt === null || generatedAt > now + 15000 ? 'Reconciliation timestamp is missing or invalid. Work coverage is unknown.' : 'Reconciliation is stale. Displayed work may be incomplete or out of date.');
    const coverage = reconciliation?.coverage_defects;
    if (Array.isArray(coverage) && coverage.length) {
      const sources = coverage.map(text).filter(Boolean);
      const names = sources.length > 2 ? sources.slice(0, -1).join(', ') + ', and ' + sources[sources.length - 1] : sources.join(' and ');
      warnings.push('Incomplete reconciliation coverage' + (names ? ': ' + names : '') + '. Work may be missing.');
    } else if (coverage !== undefined && !Array.isArray(coverage)) warnings.push('Reconciliation coverage metadata is invalid. Work coverage is unknown.');
    const source = available ? reconciliation.items : fallback(cards, jobs, approvals);
    const items = source.filter(raw => !CLOSED.has(text(raw?.status))).map((raw, index) => normalize(raw, index, now));
    items.sort((a, b) => a.owner.localeCompare(b.owner) || oldest(a, b));
    const defectCount = items.filter(row => row.defects.length).length;
    if (defectCount) warnings.push(defectCount + (defectCount === 1 ? ' item has' : ' items have') + ' metadata defects. Missing owner, deadline, or action age needs Ted review.');
    let queue;
    if (available && Array.isArray(reconciliation.ted_queue)) {
      const byId = new Map(items.map(row => [row.id, row]));
      queue = reconciliation.ted_queue.map((raw, index) => {
        const id = typeof raw === 'string' ? raw : text(raw?.id);
        if (byId.has(id)) return byId.get(id);
        if (typeof raw === 'string' || !raw || typeof raw !== 'object') {
          warnings.push('Ted queue item ' + (id || index + 1) + ' is missing from the work ledger. Coverage is incomplete.');
          return normalize({id, summary: 'Missing queue item: ' + (id || index + 1)}, index, now);
        }
        return normalize(raw, index, now);
      }).filter(row => !CLOSED.has(row.status));
    } else {
      queue = items.filter(row => row.owner === 'ted' || row.status === 'dead_letter');
      warnings.push('Ted review queue is unavailable. Showing known Ted work and dead letters; review coverage is unknown.');
    }
    const seen = new Set();
    const tedQueue = queue.filter(row => !seen.has(row.id) && seen.add(row.id)).sort(oldest);
    const bannerValue = reconciliation?.banner;
    let banner = typeof bannerValue === 'string' ? bannerValue : bannerValue && typeof bannerValue === 'object' && bannerValue.active !== false ? text(bannerValue.message) || text(bannerValue.text) : '';
    const escalated = items.filter(row => row.ageMs !== null && row.ageMs >= 12 * HOUR);
    if (!banner && (bannerValue === true || escalated.length)) banner = 'Ted follow-up needed: ' + (escalated.length || 'one or more') + ' open ' + (escalated.length === 1 ? 'item has' : 'items have') + ' waited at least 12 hours.';
    if (banner && (stale || error)) banner += ' Reconciliation is ' + (error ? 'not refreshing' : 'stale') + '; check Jobs for coverage defects.';
    return {available, stale, generatedAt, items, tedQueue, warnings, banner};
  }
  function render(container, view, {onOpenCard} = {}) {
    const doc = container.ownerDocument;
    const el = (tag, className, content) => {
      const node = doc.createElement(tag);
      if (className) node.className = className;
      if (content !== undefined) node.textContent = content;
      return node;
    };
    const section = el('section', 'aging-wip');
    section.setAttribute('aria-labelledby', 'aging-wip-heading');
    const header = el('div', 'aging-heading');
    const heading = el('h3', null, 'Open work by owner');
    heading.id = 'aging-wip-heading';
    header.append(heading, el('p', 'aging-meta', view.generatedAt === null ? 'Reconciliation time unknown' : 'Reconciled ' + new Date(view.generatedAt).toLocaleString()));
    section.append(header);
    if (view.warnings.length) {
      const warnings = el('div', 'aging-warnings');
      warnings.setAttribute('role', 'status');
      for (const warning of view.warnings) warnings.append(el('p', null, warning));
      section.append(warnings);
    }
    if (!view.items.length) section.append(el('p', 'aging-empty', view.available && !view.warnings.length ? 'No open work in the current reconciliation.' : 'No work rows are available. Coverage has not been confirmed.'));
    else {
      const table = el('table', 'aging-table');
      table.append(el('caption', 'sr-only', 'Open work grouped by owner, oldest action first'));
      const head = el('thead'), headRow = el('tr');
      for (const label of ['Work', 'Owner', 'Action age', 'Next action', 'Stage']) {
        const th = el('th', null, label); th.scope = 'col'; headRow.append(th);
      }
      head.append(headRow); table.append(head);
      const body = el('tbody');
      for (const row of view.items) {
        const tr = el('tr', row.overdue ? 'aging-overdue' : '');
        tr.dataset.agingId = row.id;
        const summary = el('th'); summary.scope = 'row'; summary.dataset.label = 'Work';
        summary.append(el('span', 'aging-summary', row.summary), el('span', 'aging-kind', row.kind + ' · ' + (row.status === 'dead_letter' ? 'Dead letter' : 'Open')));
        if (row.defects.length) summary.append(el('span', 'aging-defect', 'Metadata defect: ' + row.defects.join('; ') + '.'));
        if (row.card_id && onOpenCard) {
          const open = el('button', 'quiet aging-open', 'Open card'); open.type = 'button';
          open.setAttribute('aria-label', 'Open card: ' + row.summary);
          open.addEventListener('click', () => onOpenCard(row.card_id)); summary.append(open);
        }
        tr.append(summary);
        for (const [label, value] of [['Owner', row.owner === 'unknown' ? 'Unknown owner' : row.owner], ['Action age', row.ageLabel]]) {
          const td = el('td', null, value); td.dataset.label = label; tr.append(td);
        }
        const due = el('td', row.overdue ? 'aging-due-overdue' : '', row.dueLabel); due.dataset.label = 'Next action';
        if (row.dueAt !== null) {const time = el('time', 'aging-date', new Date(row.dueAt).toLocaleString()); time.dateTime = new Date(row.dueAt).toISOString(); due.append(time);}
        const stage = el('td', null, row.stage); stage.dataset.label = 'Stage'; tr.append(due, stage); body.append(tr);
      }
      table.append(body); section.append(table);
    }
    const reviews = el('section', 'aging-reviews'); reviews.setAttribute('aria-labelledby', 'aging-review-heading');
    const reviewHeading = el('h3', null, 'Ted review queue'); reviewHeading.id = 'aging-review-heading';
    reviews.append(reviewHeading, el('p', 'aging-meta', 'Oldest action first. Review SLA: 6 hours.'));
    const queue = el('ol', 'aging-review-list');
    for (const row of view.tedQueue) {
      const entry = el('li', row.reviewOverdue ? 'aging-review-overdue' : '');
      entry.dataset.reviewId = row.id;
      entry.append(el('span', 'aging-summary', row.summary), el('span', 'aging-meta', row.ageLabel + ' · ' + row.reviewLabel));
      if (row.status === 'dead_letter') entry.append(el('span', 'aging-defect', 'Dead letter: Ted review required.'));
      if (row.defects.length) entry.append(el('span', 'aging-defect', 'Metadata defect: ' + row.defects.join('; ') + '.'));
      queue.append(entry);
    }
    if (view.tedQueue.length) reviews.append(queue);
    else reviews.append(el('p', 'aging-empty', view.available && !view.stale && !view.warnings.length ? 'No items in the current Ted review queue.' : 'No review rows are available. Review coverage has not been confirmed.'));
    section.append(reviews); container.append(section);
  }
  return {prepare, render};
})();

if (typeof module !== 'undefined') module.exports = AgingWip;
