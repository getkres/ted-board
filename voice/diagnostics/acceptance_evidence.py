"""Conservative acceptance decisions over recorded native and loop events."""

FAILURES = {'processing_failed', 'reply_cancelled', 'playback_failed', 'audio_retry',
            'diagnostic_fixture_rejected', 'reply_timeout', 'claude_voice_failed'}


def first(rows, event, after=0, **fields):
    return next((row for row in rows if row.get('event') == event
                 and row.get('at', 0) >= after
                 and all(row.get(key) == value for key, value in fields.items())), None)


def barge_in_evidence(rows, trial_id, stimulus_started_at, stimulus_done_at, followup_started_at):
    fixture = first(rows, 'diagnostic_fixture_started', trial_id=trial_id)
    candidates = [row for row in rows if row.get('event') == 'wake_candidate'
                  and row.get('barge_in') is True
                  and stimulus_started_at <= row.get('trigger_at', row.get('at', 0)) <= stimulus_done_at + 4]
    candidate = candidates[0] if candidates else None
    trigger_id = candidate.get('trigger_id') if candidate else None
    stop = first(rows, 'playback_stopped', stop_id=trigger_id) if trigger_id else None
    confirmed = first(rows, 'wake', trigger_id=trigger_id, barge_in=True) if trigger_id else None
    interrupted = first(rows, 'diagnostic_fixture_interrupted', trial_id=trial_id)
    latency = None
    trigger_at = candidate.get('trigger_at') if candidate else None
    timing_basis = None
    if stop and candidate.get('trigger_monotonic') is not None and stop.get('stopped_monotonic') is not None:
        latency = (stop['stopped_monotonic'] - candidate['trigger_monotonic']) * 1000
        timing_basis = 'monotonic clocks'
    elif stop and trigger_at is not None and stop.get('stopped_at') is not None:
        latency = (stop['stopped_at'] - trigger_at) * 1000
        timing_basis = 'wall clocks'
    # Follow-up must traverse normal transcription, delivery, rendering, and playback.
    # Events from the stop phrase itself or the fixture cannot satisfy it.
    cursor = followup_started_at
    chain = []
    for name in ('transcribed', 'submitted', 'reply_received', 'speech_started', 'playback_done'):
        row = first(rows, name, cursor)
        if row is None:
            break
        chain.append(row)
        cursor = row['at']
    # Generic loop events also describe local queue and delivery notices. Only a
    # real assistant result between submission and reply_received proves that this
    # informational follow-up reached main Ted or the approved account 2 fallback.
    reply_event = None
    if len(chain) >= 3:
        submitted_at, received_at = chain[1]['at'], chain[2]['at']
        reply_event = next((row for row in rows
                            if submitted_at <= row.get('at', 0) <= received_at
                            and isinstance(row.get('characters'), int)
                            and row['characters'] > 0
                            and (row.get('event') == 'voice_main_reply'
                                 or (row.get('event') == 'claude_voice_reply'
                                     and row.get('account') == 2))), None)
    followup_end = chain[-1]['at'] if len(chain) == 5 else float('inf')
    local_notices = [row for row in rows
                     if followup_started_at <= row.get('at', 0) <= followup_end
                     and (row.get('event') in ('voice_action_queued', 'voice_main_delivery_uncertain')
                          or (row.get('event') == 'voice_fallback_started'
                              and row.get('action_queued') is True))]
    followup_handled = bool(len(chain) == 5 and reply_event and not local_notices)
    reply_route = ('main' if reply_event['event'] == 'voice_main_reply' else 'account2') if reply_event else None
    failures = [row for row in rows if row.get('event') in FAILURES]
    chronological = bool(fixture and candidate and fixture['at'] <= stimulus_started_at
                         and trigger_at >= fixture['at'])
    return {
        'ok': bool(chronological and latency is not None and 0 <= latency <= 300
                   and confirmed and interrupted and followup_handled and not failures),
        'fixture_started': fixture, 'candidate': candidate, 'native_stop': stop,
        'confirmation': confirmed, 'fixture_interrupted': interrupted,
        'trigger_to_native_stop_ms': round(latency, 3) if latency is not None else None,
        'stop_latency_timing_basis': timing_basis,
        'stimulus_start_to_trigger_ms': round((trigger_at - stimulus_started_at) * 1000, 3) if trigger_at else None,
        'stimulus_start_to_native_stop_ms': round((stop['stopped_at'] - stimulus_started_at) * 1000, 3) if stop and stop.get('stopped_at') else None,
        'followup_handled': followup_handled, 'followup_chain': chain,
        'followup_reply_route': reply_route, 'followup_reply_event': reply_event,
        'followup_local_notice_events': local_notices,
        'failures': failures,
    }


def self_trigger_evidence(rows, trial_id, minimum_seconds):
    start = first(rows, 'diagnostic_fixture_started', trial_id=trial_id)
    end = first(rows, 'diagnostic_fixture_completed', trial_id=trial_id)
    duration = end['at'] - start['at'] if start and end else None
    window = [row for row in rows if start and start['at'] <= row.get('at', 0)
              <= (end['at'] if end else float('inf'))]
    # Even an echo candidate that pauses and resumes is an audible self-trigger.
    self_events = [row for row in window if row.get('event') in
                   ('wake', 'playback_stop_requested', 'playback_stopped', 'diagnostic_fixture_interrupted')]
    candidates = [row for row in window if row.get('event') == 'wake_candidate']
    failures = [row for row in window if row.get('event') in FAILURES]
    return {
        'ok': bool(duration is not None and duration >= minimum_seconds and not self_events and not failures),
        'fixture_started': start, 'fixture_completed': end,
        'played_seconds': round(duration, 3) if duration is not None else None,
        'self_triggers': len(self_events), 'self_trigger_events': self_events,
        'candidate_events': candidates, 'failures': failures,
    }
