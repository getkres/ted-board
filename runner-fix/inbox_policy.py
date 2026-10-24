"""Shared, conservative routing policy for Sebastian's decision inbox."""
from datetime import datetime
import re

TED_LINE = 'ted review needed, this is not a sebastian decision'
FAILURE_LINE = 'worker failed, ted will review recovery from the job files'
FAILURES = re.compile(r'\bworker (?:exceeded|timed out|timeout|stopped|could not start|failed|crashed|returned no final)|'
                      r'\bno worker on this|\bapproval artifact (?:is unsafe|needs fixing|failed)', re.I)
ASK = re.compile(r'\?|\b(?:approve|approval|review|sign|choose|pick|decide|write|type|your call|your version|'
                 r'you decide|flat fee|must|please|action required|needed|pending)\b', re.I)
FYI = re.compile(r'\b(?:fyi|receipts?|confirmations?|payment completed|export completed|welcome|subscription notice)\b', re.I)
OPERATIONAL = re.compile(r'\b(?:ted review|pr \d+[^.!?\n]*review|pending ted review|worker slot|waiting for CI)\b', re.I)
RECOVERY = re.compile(r'^\s*(?:reply to (?:retry|continue)|please (?:retry|continue)|review (?:the )?(?:logs|job files|report|artifacts))\b', re.I)


def stamp(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError, OverflowError):
        return 0


def last_message(card):
    rows = [m for m in card.get('messages') or [] if isinstance(m, dict) and stamp(m.get('at'))]
    return max(rows, key=lambda m: stamp(m['at']), default={})


def current_text(card):
    last = last_message(card)
    live = str(card.get('live_status') or '')
    if live and (not last or not card.get('live_status_at') or stamp(card.get('live_status_at')) >= stamp(last.get('at'))):
        return live
    return str(last.get('text') or card.get('body') or card.get('title') or '')


def failure_kind(text):
    """Classify failure sentences only when no independent ask follows or precedes them."""
    result = None
    for sentence in re.split(r'(?<=[.!?])\s+|\n+', str(text or '')):
        if not FAILURES.search(sentence):
            if ASK.search(sentence) and not OPERATIONAL.search(sentence) and not RECOVERY.search(sentence):
                return None
            continue
        if re.search(r'could not start', sentence, re.I):
            kind = 'start_failure'
        elif re.search(r'exceeded|timed out|timeout', sentence, re.I):
            kind = 'timeout'
        elif re.search(r'without (?:a )?(?:current report|final result)|no final|stopped without', sentence, re.I):
            kind = 'no_result'
        else:
            kind = 'crash'
        result = result or kind
    return result


def linked_mockups(card, mockups):
    text = '\n'.join(str(card.get(k) or '') for k in ('title', 'body', 'live_status'))
    text += '\n' + str(last_message(card).get('text') or '')
    rows = [m for m in mockups if m.get('project') == card.get('project') and m.get('batch')]
    if card.get('batch'):
        return [m for m in rows if m['batch'].casefold() == str(card['batch']).casefold()]
    matches = [m for m in rows if re.search(r'(?<!\w)'+re.escape(str(m['batch']))+r'(?!\w)', text, re.I)
               or (m.get('id') and str(m['id']) in text)]
    return matches


def decision(card, line=None, mockups=()):
    """Return the allowed decision family only for a current, concrete ask."""
    line = current_text(card) if line is None else str(line)
    text = line
    if line.strip().lower() == 'review the pending approval on this card':
        text += '\n' + str(last_message(card).get('text') or '')
    text = re.sub(r'\bno action (?:required|needed)\b', '', text, flags=re.I)
    rows = linked_mockups(card, mockups)
    # Match the action and its object within one sentence. Background prices,
    # historical failures, and quoted UI questions do not create decisions.
    for ask in re.split(r'(?<=[.!?])\s+|\n+', text):
        if failure_kind(ask) or OPERATIONAL.search(ask):
            continue
        if not ASK.search(ask):
            continue
        if re.search(r'\b(?:write|type) (?:your|the|each)|\byours to write\b', ask, re.I) and re.search(r'\b(?:copy|headline|line|version|words)\b', ask, re.I):
            if not rows or not all(m.get('status') == 'archived' for m in rows):
                return 'copy'
            continue
        if re.search(r'\b(?:send(?:ing)? (?:the |this |an? |exact |drafted )*(?:email|draft)|send_email)\b', ask, re.I):
            return 'send_email'
        if re.search(r'\b(?:spend(?:ing)?|pay(?:ment)?|charge|flat fee|budget|billing)\b|\$\s*\d', ask, re.I):
            return 'spend_money'
        if re.search(r'\b(?:contract|legal|signature|docusign)\b', ask, re.I):
            return 'legal'
        if re.search(r'\b(?:pricing|price|prices)\b', ask, re.I):
            return 'pricing'
        if re.search(r'\b(?:gated (?:prod|production)|production (?:database|db) write|prod write)\b', ask, re.I):
            return 'prod_write'
        if re.search(r'\b(?:pick|choose|taste|mockup|design|batch)\b', ask, re.I):
            if any(m.get('status') == 'open' and not m.get('verdict') for m in rows):
                return 'approve_design'
    return None


def approval_line(kind, card):
    if kind == 'email':
        return 'approve sending the drafted email'
    if kind == 'spend':
        return 'approve the proposed spend'
    if kind == 'db' and decision(card) == 'prod_write':
        return 'approve the gated production database write'
    return None


def disposition(card, mockups=(), line=None):
    """Mechanical inbox move, or a reason to retain a real or ambiguous ask."""
    text = current_text(card) if line is None else str(line)
    if failure_kind(text):
        return 'up_next', FAILURE_LINE
    family = decision(card, text, mockups)
    if family:
        return None, 'sebastian decision: '+family
    rows = linked_mockups(card, mockups)
    if rows and all(m.get('status') == 'archived' for m in rows):
        return 'done', 'linked mockup batch is archived'
    if re.search(r'\b(?:superseded by|replaced by|obsolete|no longer needed)\b', text, re.I):
        return 'done', 'superseded work, no current decision'
    content = text+'\n'+str(card.get('title') or '')+'\n'+str(card.get('body') or '')
    without_notice = re.sub(r'\bno action (?:required|needed)\b', '', content, flags=re.I)
    if FYI.search(content) and not ASK.search(without_notice):
        return 'done', 'pure fyi, no action required'
    asks = [sentence for sentence in re.split(r'(?<=[.!?])\s+|\n+', text)
            if ASK.search(sentence) and not OPERATIONAL.search(sentence) and not RECOVERY.search(sentence)]
    if card.get('live_state') == 'running' and not asks:
        return 'up_next', 'ted review, no sebastian decision'
    return None, 'ambiguous, retain'
