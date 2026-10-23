'use strict';

const BoardStatus = {
  workerCounts(cards, jobs, loaded, now = Date.now()) {
    if (!loaded) return null;
    const byCard = new Map();
    for (const job of jobs) {
      if (!job || typeof job.card_id !== 'string') continue;
      const previous = byCard.get(job.card_id);
      const timestamp = Date.parse(job.heartbeat_at);
      if (!previous || (Number.isFinite(timestamp) && (!Number.isFinite(Date.parse(previous.heartbeat_at)) || timestamp > Date.parse(previous.heartbeat_at)))) byCard.set(job.card_id, job);
    }
    const counts = {running: 0, queued: 0, stale: 0};
    for (const card of cards) {
      const job = byCard.get(card.id);
      const heartbeat = Date.parse(job?.heartbeat_at);
      const fresh = Number.isFinite(heartbeat) && now - heartbeat >= -15000 && now - heartbeat <= 120000;
      if (fresh && job.status === 'running' && Number.isInteger(job.pid) && job.pid > 1) counts.running++;
      else if (fresh && job.status === 'queued') counts.queued++;
      else if (card.section === 'ted_doing') counts.stale++;
    }
    return counts;
  },
  doingCounts(cards, jobs, loaded, now = Date.now()) {
    return BoardStatus.workerCounts(cards.filter(card => card.section === 'ted_doing'), jobs, loaded, now);
  },
};

if (typeof module !== 'undefined') module.exports = BoardStatus;
