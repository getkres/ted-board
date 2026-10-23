#!/usr/bin/env python3
"""Mechanical inbox maintenance. Uses only existing board move and archive APIs."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path.home() / 'ted-ops/ted-board'
DAY = 86400
WORKERS = {'ted', 'worker', 'codex', 'claude'}
HUMANS = {'seb', 'sebastian'}
TERMINAL = {'done', 'killed'}
VERDICTS = {'approved', 'needs_work', 'scrapped'}
REPORT = re.compile(r'\b(finished|opened\s+(?:a\s+)?pr\b|uploaded|applied|merged|(?:is|now|went)\s+live)\b', re.I)
FYI = re.compile(r'\b(receipts?|confirmations?|export completed|welcome (?:to|emails?)|subscription (?:notices?|confirmations?))\b', re.I)
REQUEST = re.compile(r'\?|\b(approval (?:needed|required|pending)|awaiting (?:your|a decision)|waiting (?:on|for) you|'
                     r'please\b|must\b|verify\b|(?:payment|charge) failed|outstanding balance|cancellation required|renewal required|choose\b|pick (?:one|a|the|your)|your (?:pick|decision|approval|call)|'
                     r'approve (?:each|the|this)|tap yes|tell me|update your|action required|'
                     r'needs? (?:your |an? )?(?:approval|decision|signature)|pending approval)\b', re.I)
SENSITIVE = re.compile(r'\b(contract|contracts|docusign|signature|spend|spending|send_email|send email|'
                       r'draft[ _-]email|spend\.json|apply[ ._-]?sql|database gate|database sql|production (?:db|database)|'
                       r'approve (?:the )?(?:charge|payment)|flat fee|\$\s*\d)\b|\$\s*\d', re.I)
NEGATED_REPORT = re.compile(r'\b(?:not|never|isn.t|hasn.t|wasn.t|haven.t)\s+(?:\w+\s+){0,3}'
                            r'(?:finished|opened|uploaded|applied|merged|live)\b|'
                            r'\b(?:will|plan to|going to)\s+(?:\w+\s+){0,2}(?:upload|finish|apply|merge|open)\b', re.I)
STUDY = re.compile(r'\b(reference locks?|inventor(?:y|ies)|side[ -]by[ -]sides?|just to look|just[ -]looking)\b', re.I)


def stamp(value):
    try:
        if not isinstance(value, str):
            return 0
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError, OverflowError):
        return 0


def clean(value, limit=160):
    text = str(value or '').replace(chr(0x2014), ',')
    text = re.sub(r'https?://\S+', '[link]', text)
    text = re.sub(r'(?i)\b(?:api[_-]?key|key|token|password|secret)\s*[:=]\s*[^\s,;]+', '[redacted]', text)
    return re.sub(r'\s+', ' ', text).strip()[:limit]


def latest(card):
    messages = card.get('messages') or []
    if not isinstance(messages, list) or any(not isinstance(m, dict) or not stamp(m.get('at')) for m in messages):
        return None
    return max(messages, key=lambda m: stamp(m.get('at')), default={})


def activity(card):
    times = [stamp(card.get('updated_at')), stamp(card.get('created_at')),
             stamp(card.get('live_status_at')), stamp((card.get('answer') or {}).get('created_at'))]
    times.extend(stamp(m.get('at')) for m in card.get('messages', []) if isinstance(m, dict))
    return max(times, default=0)


def recent_human(messages, now):
    return any(str(m.get('who', '')).lower() in HUMANS and
               (not stamp(m.get('at')) or now-stamp(m['at']) < 2*DAY) for m in messages)


def protection(card, now):
    if card.get('decision_kind'):
        return 'decision kind requires review'
    if any(card.get(k) for k in ('pending_approval', 'approval_pending', 'pending_decision', 'veto_pending')):
        return 'pending approval'
    approval = card.get('approval') or {}
    if isinstance(approval, dict) and approval.get('status') in ('pending', 'queued', 'cleared'):
        return 'pending approval'
    if isinstance(card.get('veto'), dict) and card['veto'].get('status') not in ('sent', 'cancelled', 'failed'):
        return 'pending veto approval'
    if card.get('amount_cents') is not None:
        return 'money decision'
    if recent_human(card.get('messages') or [], now):
        return 'sebastian replied within 48 hours'
    answer = card.get('answer') or {}
    if answer and (not stamp(answer.get('created_at')) or now-stamp(answer['created_at']) < 2*DAY):
        return 'recent or undated sebastian answer'
    if str(card.get('created_by', '')).lower() in WORKERS and (
            card.get('needs_you') or card.get('initial_section') == 'needs_you'):
        created = stamp(card.get('created_at'))
        if not created or now-created < 7*DAY:
            return 'ted created needs_you within seven days or creation time is unknown'
    content = '\n'.join(str(card.get(k) or '') for k in ('title', 'body'))
    last = latest(card)
    content += '\n' + str((last or {}).get('text') or '')
    if SENSITIVE.search(content):
        return 'possible spend, send, sql, or contract approval'
    if card.get('options') and not answer:
        return 'unanswered choices'
    if card.get('steps') and not answer:
        return 'pending guided steps'
    content = re.sub(r'\bno action (?:required|needed)\b', '', content, flags=re.I)
    if REQUEST.search(content):
        return 'explicit action or judgment requested'
    return None


def classify_card(card, now):
    reason = protection(card, now)
    if reason:
        return None, reason
    last = latest(card)
    if last == {} and FYI.search(str(card.get('title', ''))+' '+str(card.get('body', ''))):
        return 'done', 'pure fyi, no action required'
    if not last or str(last.get('who', '')).lower() not in WORKERS:
        return None, 'no dated latest worker message'
    text = str(last.get('text') or '')
    if NEGATED_REPORT.search(text):
        return None, 'unfinished or future work, ted judgment required'
    if REPORT.search(text):
        return 'up_next', 'Ted review'
    if FYI.search(text):
        return 'done', 'pure fyi, no action required'
    return None, 'ambiguous, ted judgment required'


def base_title(value):
    value = re.sub(r'\b(?:v\d+(?:\.\d+)*|final|restart)\b', ' ', value, flags=re.I)
    return re.sub(r'[^\w]+', ' ', value.lower()).strip()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def review_row(card, now, suggested, reason):
    last = latest(card) or {}
    return dict(id=clean(card.get('id')), project=clean(card.get('project')),
                title=clean(card.get('title')), age_hours=round(max(0, now-activity(card))/3600, 1),
                last_message=clean(last.get('text') or card.get('body')), suggested_move=suggested, reason=reason)


def linked_cards(rows, cards):
    project, batch = rows[0]['project'], rows[0]['batch']
    ids = {r['id'] for r in rows}
    return [c for c in cards if c.get('project') == project and c.get('section') not in TERMINAL and
            (c.get('batch') == batch or batch.lower() in (str(c.get('title', ''))+'\n'+str(c.get('body', ''))).lower()
             or any(mid in str(c.get('body', '')) for mid in ids))]


def batch_reason(rows, pins, cards, now):
    attached = [p for p in pins if p.get('mockup_id') in {r['id'] for r in rows}]
    if any(not stamp(p.get('created_at')) or any(not stamp(m.get('at')) for m in p.get('thread', [])) for p in attached):
        return 'undated mockup activity', attached
    if any(not p.get('resolved') for p in attached):
        return 'unresolved mockup feedback', attached
    if any(recent_human(p.get('thread') or [], now) for p in attached):
        return 'sebastian replied within 48 hours', attached
    if any(r.get('verdict_change') and (not stamp(r['verdict_change'].get('at')) or
            now-stamp(r['verdict_change']['at']) < 2*DAY) for r in rows):
        return 'recent or undated sebastian verdict', attached
    for c in linked_cards(rows, cards):
        if 'build approved:' in c.get('title', '').lower() or c.get('build_pending'):
            return 'build is pending', attached
        reason = protection(c, now)
        if reason:
            return reason, attached
    if any(r.get('build_pending') or r.get('detail_error') for r in rows):
        return 'build or image detail pending', attached
    if any(not stamp(r.get('created_at')) for r in rows):
        return 'unknown batch creation time', attached
    return None, attached


def plan(cards, mockups, pins, now):
    actions, review = [], []
    for c in cards:
        if c.get('section') != 'needs_you':
            continue
        target, reason = classify_card(c, now)
        if target:
            actions.append(dict(kind='move', card_id=c['id'], project=c['project'],
                                **{'from': 'needs_you'}, to=target, reason=reason, basis=digest(c)))
        else:
            review.append(review_row(c, now, 'keep', reason))
    groups = defaultdict(list)
    for row in mockups:
        if row.get('status') != 'archived' and row.get('project') and row.get('batch'):
            groups[(row['project'], row['batch'])].append(row)
    for (project, batch), rows in sorted(groups.items()):
        blocked, attached = batch_reason(rows, pins, cards, now)
        reason = None
        if not blocked:
            newest = max(stamp(r['created_at']) for r in rows)
            newer = [name for (proj, name), other in groups.items() if proj == project and name != batch
                     and base_title(name) and base_title(name) == base_title(batch)
                     and all(stamp(r.get('created_at')) for r in other)
                     and min(stamp(r['created_at']) for r in other) > newest
                     and not any(r.get('detail_error') for r in other)]
            if newer:
                reason = 'superseded by '+sorted(newer)[0]
            elif all(r.get('verdict') in VERDICTS or (not r.get('verdict') and r.get('status') == 'picked') for r in rows):
                reason = 'every image has a verdict, and no build is pending'
            elif STUDY.search(batch):
                touched = [stamp(r.get('created_at')) for r in rows]
                touched.extend(stamp((r.get('verdict_change') or {}).get('at')) for r in rows)
                touched.extend(stamp(p.get('created_at')) for p in attached)
                touched.extend(stamp(m.get('at')) for p in attached for m in p.get('thread', []))
                if now-max(touched) >= 7*DAY:
                    reason = 'just-looking study untouched for seven days'
        if reason:
            actions.append(dict(kind='archive', card_id='batch:'+project+':'+batch,
                                project=project, batch=batch, **{'from': 'mockups'}, to='archived',
                                reason=reason, basis=digest([rows, attached])))
        else:
            times = [stamp(r.get('created_at')) for r in rows]
            review.append(dict(id=clean('batch:'+batch), project=clean(project), title=clean(batch),
                               age_hours=round(max(0, now-max(times))/3600, 1),
                               last_message=clean(blocked or 'no mechanical archive rule applies'),
                               suggested_move='keep', reason=blocked or 'ted judgment required'))
    return dict(actions=actions, review=sorted(review, key=lambda r: (-r['age_hours'], r['id'])))


def fetch_cards():
    from board_client import cards
    result = cards()
    if not isinstance(result, list) or len(result) >= 500:
        raise RuntimeError('Card snapshot incomplete')
    return result


def fetch_mockups():
    from mockup_client import call
    result = call()
    if not isinstance(result, dict) or not isinstance(result.get('mockups'), list) or not isinstance(result.get('pins'), list):
        raise RuntimeError('Mockup snapshot incomplete')
    return result


def move_card(card_id, value, note):
    from board_client import call
    return call('move', page=True, card_id=card_id, value=value, note=note)


def archive_batch(project, batch):
    from mockup_client import call
    return call('archive', project=project, batch=batch)


def snapshot():
    cards, payload = fetch_cards(), fetch_mockups()
    return cards, payload['mockups'], payload['pins']


def journal(root, action, outcome, now):
    row = {k: clean(action[k], 300) for k in ('card_id', 'project', 'from', 'to', 'reason')}
    if action.get('batch'):
        row['batch'] = clean(action['batch'], 300)
    row.update(at=datetime.fromtimestamp(now, timezone.utc).isoformat(), outcome=outcome)
    path = root / 'steward-log.jsonl'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, 'a') as stream:
        stream.write(json.dumps(row, sort_keys=True)+'\n')
        stream.flush()
        os.fsync(stream.fileno())


def write_overflow(root, cards, now):
    ranked = sorted((review_row(c, now, 'keep', classify_card(c, now)[1]) for c in cards
                     if c.get('section') == 'needs_you'), key=lambda r: (-r['age_hours'], r['id']))
    excess = max(0, len(ranked)-12)
    payload = dict(at=datetime.fromtimestamp(now, timezone.utc).isoformat(), needs_you=len(ranked),
                   cap=12, excess_count=excess, extras=ranked[:excess], ranked=ranked if excess else [])
    path = root / 'steward-overflow.json'
    temp = path.with_suffix('.json.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(payload, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)
    return len(ranked), excess


def run_once(root=ROOT, dry_run=False, now=None):
    root = Path(root)
    fixed_now = now
    now = time.time() if now is None else now
    cards, mockups, pins = snapshot()
    proposed = plan(cards, mockups, pins, now)
    counts = dict(dry_run=dry_run, planned_moves=sum(a['kind'] == 'move' for a in proposed['actions']),
                  planned_archives=sum(a['kind'] == 'archive' for a in proposed['actions']),
                  moved=0, archived_batches=0, archived_images=0, deferred=0, failed=0,
                  needs_you_before=sum(c.get('section') == 'needs_you' for c in cards))
    counts['actions'] = [{k: clean(v, 300) for k, v in a.items() if k != 'basis'} for a in proposed['actions']]
    if dry_run:
        remaining = counts['needs_you_before']-counts['planned_moves']
        counts.update(needs_you_after=remaining, overflow=max(0, remaining-12))
        return counts
    root.mkdir(parents=True, exist_ok=True)
    for action in proposed['actions']:
        current_cards, current_mockups, current_pins = snapshot()
        current = plan(current_cards, current_mockups, current_pins, time.time() if fixed_now is None else fixed_now)
        if action not in current['actions']:
            journal(root, action, 'deferred, state changed', now)
            counts['deferred'] += 1
            continue
        journal(root, action, 'attempt', now)
        try:
            if action['kind'] == 'move':
                result = move_card(action['card_id'], action['to'], action['reason'])
            else:
                result = archive_batch(action['project'], action['batch'])
            if not isinstance(result, dict) or result.get('ok') is not True:
                raise RuntimeError('Action not confirmed')
        except Exception:
            journal(root, action, 'uncertain, refresh before retry', now)
            counts['failed'] += 1
            continue
        journal(root, action, 'applied', now)
        if action['kind'] == 'move':
            counts['moved'] += 1
        else:
            counts['archived_batches'] += 1
            counts['archived_images'] += int(result.get('archived', 0))
    cards = fetch_cards()
    counts['needs_you_after'], counts['overflow'] = write_overflow(root, cards, now)
    return counts


def require_mini():
    result = subprocess.run(['/usr/sbin/scutil', '--get', 'ComputerName'], capture_output=True, text=True, check=True)
    if 'mini' not in result.stdout.lower():
        raise RuntimeError('Mini required')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args(argv)
    require_mini()
    args.root.mkdir(parents=True, exist_ok=True)
    with (args.root / '.steward.lock').open('a') as lock:
        os.chmod(lock.name, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('steward already running')
            return 0
        result = run_once(args.root, args.dry_run)
    print(json.dumps(result, sort_keys=True))
    return 1 if result['failed'] else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        print('steward failed, check private inputs and connectivity', file=sys.stderr)
        sys.exit(1)
