'use strict';

// The approved business patch groups current cards. It is not a visit-history diff.
const BusinessPatch = (() => {
  const text = value => typeof value === 'string' ? value.trim() : '';
  function prepare({cards, approvals = [], loaded = false, loading = false, error = '', approvalsLoaded = false, approvalsError = ''} = {}) {
    const groups = [
      {id: 'review', label: 'Review', marker: '+', caption: 'Current choices', rows: []},
      {id: 'handoff', label: 'Handoff', marker: '~', caption: 'Up next', rows: []},
      {id: 'ted', label: 'With Ted', marker: '·', caption: 'Assigned, not completed', rows: []},
      {id: 'alert', label: 'Alert', marker: '!', caption: 'Recorded blockers or unknown state', rows: []},
    ];
    const available = loaded && Array.isArray(cards), warnings = [];
    if (!available) return {available: false, loading, groups, total: 0, warnings, error: text(error)};
    if (error) warnings.push(text(error) + ' Showing the last loaded cards; this snapshot may be out of date.');
    if (approvalsError) warnings.push('Approval refresh failed. Review grouping may be out of date.');
    else if (!approvalsLoaded || !Array.isArray(approvals)) warnings.push('Approvals have not loaded. Review grouping may be incomplete.');
    if (cards.length >= 500) warnings.push('The card feed reached its 500-card limit. This snapshot may be incomplete.');
    const counts = new Map(), pending = new Set((Array.isArray(approvals) ? approvals : []).filter(a => a?.status === 'pending').map(a => a.card_id));
    let invalid = 0;
    for (const card of cards) {
      if (!card || !text(card.id) || card.id !== text(card.id)) { invalid++; continue; }
      counts.set(card.id, (counts.get(card.id) || 0) + 1);
    }
    if ([...counts.values()].some(count => count > 1)) warnings.push('Cards with duplicate IDs are omitted because their current state is ambiguous.');
    if (invalid) warnings.push(invalid + ' invalid card ' + (invalid === 1 ? 'record is' : 'records are') + ' omitted.');
    for (const card of cards) {
      if (!card || !text(card.id) || card.id !== text(card.id) || counts.get(card.id) !== 1 || ['done', 'killed'].includes(card.section)) continue;
      const approval = pending.has(card.id), blocked = card.live_state === 'blocked';
      let group, status;
      if (approval || ['needs_you', 'yours'].includes(card.section)) {
        group = groups[0]; status = approval ? 'Approval pending' : 'Needs you';
        if (blocked) status += ' · Blocked';
      } else if (blocked) { group = groups[3]; status = 'Blocked'; }
      else if (card.section === 'up_next') { group = groups[1]; status = 'Up next'; }
      else if (card.section === 'ted_doing') { group = groups[2]; status = 'Assigned to Ted'; }
      else { group = groups[3]; status = 'Unrecognized card section'; }
      group.rows.push({id: card.id, title: text(card.title) || 'Untitled card', project: text(card.project) || 'Project not recorded',
        detail: text(card.live_status) || text(card.why) || text(card.body).split('\n')[0] || 'Open this card to read the details.', status});
    }
    return {available, loading, groups, total: groups.reduce((sum, group) => sum + group.rows.length, 0), warnings};
  }
  function render(container, view, {onOpenCard} = {}) {
    const el = (tag, cls, content) => {
      const node = container.ownerDocument.createElement(tag);
      if (cls) node.className = cls;
      if (content !== undefined) node.textContent = content;
      return node;
    };
    const details = el('details', 'v3-business-patch');
    details.append(el('summary', null, 'Business patch'));
    const panel = el('section', 'bp-panel'); panel.setAttribute('aria-labelledby', 'business-patch-heading');
    const header = el('div', 'bp-header'), title = el('h2', null, 'Today’s business patch.'); title.id = 'business-patch-heading';
    header.append(title, el('p', 'bp-description', 'Current work grouped by review, handoff, and alert; no last-visit delta is available.'), el('p', 'bp-baseline', 'No recorded last-visit baseline'));
    panel.append(header);
    if (!view.available) panel.append(el('p', 'bp-warning', view.loading ? 'Loading current cards…' : view.error || 'Current cards are unavailable. Refresh to try again.'));
    else {
      if (view.warnings.length) {
        const warnings = el('div', 'bp-warnings'); warnings.setAttribute('role', 'status');
        for (const warning of view.warnings) warnings.append(el('p', null, warning));
        panel.append(warnings);
      }
      const toolbar = el('div', 'bp-toolbar'); toolbar.append(el('span', 'bp-count', view.total + ' open ' + (view.total === 1 ? 'card' : 'cards') + ' in the loaded snapshot'));
      const counts = el('div', 'bp-counts');
      for (const group of view.groups) counts.append(el('span', 'bp-count-' + group.id, group.rows.length + ' ' + group.label.toLowerCase()));
      toolbar.append(counts); panel.append(toolbar);
      const patch = el('div', 'bp-patch');
      let number = 0;
      for (const group of view.groups) {
        const section = el('section', 'bp-group bp-' + group.id), label = el('div', 'bp-label');
        const marker = el('span', 'bp-marker', group.marker); marker.setAttribute('aria-hidden', 'true');
        const heading = el('h3', null, group.label); heading.id = 'business-patch-' + group.id; section.setAttribute('aria-labelledby', heading.id);
        const description = el('div'); description.append(heading, el('p', null, group.caption)); label.append(marker, description); section.append(label);
        const rows = el('div', 'bp-rows');
        if (!group.rows.length) rows.append(el('p', 'bp-empty', 'No cards in this group.'));
        for (const card of group.rows) {
          const row = el('article', 'bp-row'); row.dataset.patchCard = card.id;
          const line = el('span', 'bp-line', String(++number).padStart(2, '0')); line.setAttribute('aria-hidden', 'true');
          const copy = el('div', 'bp-copy'); copy.append(el('p', 'bp-project', card.project), el('h4', null, card.title), el('p', 'bp-detail', card.detail), el('p', 'bp-state', card.status));
          row.append(line, copy);
          if (onOpenCard) {
            const open = el('button', 'bp-open', 'Open card'); open.type = 'button'; open.setAttribute('aria-label', 'Open card: ' + card.title);
            open.addEventListener('click', () => onOpenCard(card.id)); row.append(open);
          }
          rows.append(row);
        }
        section.append(rows); patch.append(section);
      }
      panel.append(patch);
      if (!view.total) panel.append(el('p', 'bp-empty', 'No open cards in the loaded snapshot.'));
      const foot = el('div', 'bp-footer'); foot.append(el('p', null, 'Groups describe this snapshot, not inferred changes since your last visit; completed cards are omitted.'), el('p', null, 'No completion claimed for pending handoffs.'));
      panel.append(foot);
    }
    details.append(panel); container.append(details);
  }
  return {prepare, render};
})();

if (typeof module !== 'undefined') module.exports = BusinessPatch;
