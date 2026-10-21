'use strict';

const BoardStatus = {
  doingCounts(cards, jobs, loaded, now = Date.now()) {
    if (!loaded) return null;
    const byCard = new Map();
    for (const job of jobs) {
      if (!job || typeof job.card_id !== 'string') continue;
      const previous = byCard.get(job.card_id);
      if (!previous || Date.parse(job.heartbeat_at) > Date.parse(previous.heartbeat_at)) byCard.set(job.card_id, job);
    }
    const counts = {running: 0, queued: 0, stale: 0};
    for (const card of cards) {
      if (card.section !== 'ted_doing') continue;
      const job = byCard.get(card.id);
      const heartbeat = Date.parse(job?.heartbeat_at);
      const fresh = Number.isFinite(heartbeat) && now - heartbeat <= 120000;
      if (fresh && job.status === 'running' && Number.isInteger(job.pid) && job.pid > 1) counts.running++;
      else if (fresh && job.status === 'queued') counts.queued++;
      else counts.stale++;
    }
    return counts;
  },
};

if (typeof module !== 'undefined') module.exports = BoardStatus;
