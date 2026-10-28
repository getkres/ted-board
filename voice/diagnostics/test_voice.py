#!/usr/bin/env python3
"""Exercise the installed mini service, with full raw acceptance evidence.

Default e2e keeps the original acoustic request and renderer checks. Barge-in and
no-self-trigger use local speech fixtures through the explicit installed-service
fixture hook. They never call a model to manufacture long replies.
"""
import argparse
import datetime
import json
import os
import socket
import subprocess
import time
import uuid
import wave
from pathlib import Path

from acceptance_evidence import FAILURES, barge_in_evidence, first, self_trigger_evidence


class Runner:
    def __init__(self, args):
        self.args = args
        self.home = args.home.resolve()
        self.started = time.time()
        self.stimuli = []
        self.fixtures = []
        self.routes = []
        self.speaker = None
        self.marker_created = False
        self.requests = []

    def rows(self, since=None):
        rows = []
        seen = set()
        for path in sorted((self.home / 'logs').glob('events.jsonl*')):
            for line in path.read_text(errors='replace').splitlines():
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(row, dict) or not isinstance(row.get('at'), (int, float)):
                    continue
                if since is not None and row['at'] < since:
                    continue
                key = json.dumps(row, sort_keys=True)
                if key not in seen:
                    rows.append(row)
                    seen.add(key)
        return sorted(rows, key=lambda row: row['at'])

    def wait(self, predicate, seconds, since=None):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            rows = self.rows(since)
            value = predicate(rows)
            if value:
                return value
            if any(row.get('event') in FAILURES for row in rows):
                return None
            time.sleep(.1)
        return None

    def prepare(self):
        # Only read the installed route and service. Never start or restart it.
        hostname = socket.gethostname().lower()
        if 'mini' not in hostname:
            raise RuntimeError('live acceptance is allowed only on the Mac mini')
        state = subprocess.run(['launchctl', 'print', f'gui/{os.getuid()}/co.ted.voice'],
                               capture_output=True, text=True)
        if state.returncode or 'state = running' not in state.stdout:
            raise RuntimeError('installed co.ted.voice service is not running')
        self.service = {'hostname': hostname, 'launchctl': state.stdout}
        devices = json.loads(subprocess.check_output([str(self.home / 'bin/TedVoiceAudio'), '--devices']))['devices']
        self.devices = devices
        self.speaker = next((str(d['id']) for d in devices
                             if d['output'] and 'Mac mini Speakers' in d['name']), None)
        if not self.speaker:
            raise RuntimeError('Mac mini Speakers output device not found')
        all_rows = self.rows()
        self.routes = [row for row in all_rows if row.get('event') in
                       ('audio_ready', 'capture_audio_ready')][-2:]
        if (self.home / 'paused').exists():
            raise RuntimeError('voice is paused; acceptance will not change pause state')

    def say(self, text, kind):
        row = {'kind': kind, 'text': text, 'speaker': self.speaker,
               'voice': self.args.stimulus_voice,
               'dispatched_at': time.time(), 'dispatched_monotonic': time.monotonic(),
               'timing_basis': 'say process dispatch and exit; physical acoustic onset is not instrumented'}
        self.stimuli.append(row)
        result = subprocess.run(['/usr/bin/say', '-a', self.speaker, '-v', self.args.stimulus_voice,
                                 '-r', '140', text], capture_output=True, text=True, timeout=30)
        row.update(finished_at=time.time(), finished_monotonic=time.monotonic(),
                   returncode=result.returncode, stderr=result.stderr)
        if result.returncode:
            raise RuntimeError('mini speaker say stimulus failed')
        return row

    def e2e(self):
        start = time.time()
        phrase = 'Hey Ted. Reply exactly, the Jabra voice loop is working.'
        stimulus = self.say(phrase, 'end-to-end')
        self.wait(lambda rows: first(rows, 'playback_done',
                  (first(rows, 'speech_started') or {}).get('at', float('inf'))), 170, start)
        rows = self.rows(start)
        required = ['wake', 'transcribed', 'reply_received', 'speech_rendered', 'speech_started', 'playback_done']
        missing = [name for name in required if not first(rows, name)]
        main = bool(first(rows, 'voice_main_submitted') and first(rows, 'voice_main_reply'))
        account2 = any(row.get('event') == 'claude_account2_ready' and row.get('account') == 2
                       and row.get('subscription') == 'max' for row in rows)
        plan_only = any(row.get('event') == 'claude_account2_plan_only'
                        and row.get('extra_usage_enabled') is False for row in rows)
        fallback = bool(account2 and plan_only and first(rows, 'claude_voice_reply'))
        eleven = any(row.get('event') == 'speech_rendered' and row.get('renderer') == 'elevenlabs' for row in rows)
        jabra = self.jabra_verified()
        failures = [row for row in rows if row.get('event') in FAILURES]
        return {'ok': not missing and (main or fallback) and eleven and jabra and not failures,
                'main_route_verified': main, 'account2_fallback_verified': fallback,
                'main_route_available': main, 'account2_max': account2, 'plan_only': plan_only,
                'elevenlabs': eleven, 'jabra_verified': jabra, 'missing_events': missing,
                'stimulus': stimulus, 'failures': failures, 'events': rows}

    def jabra_verified(self):
        return any(row.get('event') == 'audio_ready' and 'Jabra' in row.get('input_name', '')
                   and 'Jabra' in row.get('output_name', '')
                   and row.get('output_au_device') == row.get('output_id')
                   and row.get('microphone_permission') == 3 for row in self.routes)

    def fixture(self, kind):
        trial_id = kind + '-' + uuid.uuid4().hex
        temp = self.home / 'tmp'
        temp.mkdir(parents=True, exist_ok=True)
        path = temp / (trial_id + '.wav')
        # Deliberate wake words in natural reply text exercise the echo guard.
        paragraph = ('This is a local long reply for the Jabra acceptance measurement. '
                     'The microphone keeps listening while this reply plays through the Jabra speaker. '
                     'The quoted words Hey Ted and Ted stop are part of this reply. '
                     'There is no external request in this recording. '
                     'The room should remain quiet until the full reply finishes. ')
        text = paragraph * 2
        subprocess.run(['/usr/bin/say', '-v', 'Daniel', '-r', '180', '-o', str(path),
                        '--file-format=WAVE', '--data-format=LEI16@16000', text],
                       check=True, capture_output=True, timeout=30)
        self.fixtures.append(path)
        with wave.open(str(path)) as wav:
            duration = wav.getnframes() / wav.getframerate()
        if duration < self.args.minimum_long_seconds:
            raise RuntimeError(f'fixture too short: {duration:.3f} seconds')
        marker = self.home / 'diagnostics-enabled'
        if not marker.exists():
            marker.touch(mode=0o600, exist_ok=False)
            self.marker_created = True
        directory = self.home / 'diagnostics'
        directory.mkdir(mode=0o700, exist_ok=True)
        request = directory / (trial_id + '.request.json')
        temporary = request.with_suffix('.tmp')
        temporary.write_text(json.dumps({'trial_id': trial_id, 'path': str(path), 'text': text}) + '\n')
        os.chmod(temporary, 0o600)
        start = time.time()
        temporary.replace(request)
        self.requests.append(request)
        event = self.wait(lambda rows: first(rows, 'diagnostic_fixture_started', trial_id=trial_id), 20, start)
        if not event:
            raise RuntimeError('installed service did not accept diagnostic fixture; hook may be unavailable or service busy')
        return {'trial_id': trial_id, 'path': str(path), 'text': text,
                'word_count': len(text.split()), 'duration_seconds': duration,
                'queued_at': start, 'started': event}

    def barge_in(self):
        fixture = self.fixture('barge-in')
        start = fixture['started']['at']
        # Require native playback start before the external interruption.
        native_start = self.wait(lambda rows: first(rows, 'playback_started', start), 5, start - 1)
        if not native_start:
            raise RuntimeError('fixture has no native playback_started evidence')
        time.sleep(self.args.interrupt_after)
        stimulus = self.say(self.args.interrupt_phrase, 'barge-in-stop')
        # No idle gap: this is the new request captured after the confirmed wake.
        followup = self.say('Reply exactly, the follow up was handled.', 'barge-in-followup')
        self.wait(lambda rows: first(rows, 'playback_done',
                  (first(rows, 'speech_started', followup['dispatched_at']) or {}).get('at', float('inf'))),
                  170, start)
        rows = self.rows(start - .25)
        result = barge_in_evidence(rows, fixture['trial_id'], stimulus['dispatched_at'],
                                   stimulus['finished_at'], followup['dispatched_at'])
        result.update(fixture=fixture, stimulus=stimulus, followup=followup,
                      native_fixture_start=native_start, events=rows)
        result['ok'] = result['ok'] and self.jabra_verified()
        return result

    def no_self_trigger(self):
        trials = []
        startup_error = None
        failed_to_start_trial = None
        for index in range(self.args.trials):
            try:
                fixture = self.fixture(f'no-self-{index + 1}')
            except RuntimeError as exc:
                startup_error = f'{type(exc).__name__}: {exc}'
                failed_to_start_trial = index + 1
                break
            start = fixture['started']['at']
            self.wait(lambda rows: first(rows, 'diagnostic_fixture_completed', trial_id=fixture['trial_id'])
                      or first(rows, 'diagnostic_fixture_interrupted', trial_id=fixture['trial_id']),
                      fixture['duration_seconds'] + 20, start)
            rows = self.rows(start - .25)
            result = self_trigger_evidence(rows, fixture['trial_id'], self.args.minimum_long_seconds)
            result.update(fixture=fixture, events=rows)
            trials.append(result)
            print(json.dumps({'trial': index + 1, 'ok': result['ok'],
                              'self_triggers': result['self_triggers'],
                              'played_seconds': result['played_seconds']}), flush=True)
            # Isolation prevents the preceding fixture's cooldown from affecting the next.
            if not result['ok'] and not self.args.continue_on_failure:
                break
            time.sleep(2.5)
        return {'ok': len(trials) == 10 and all(trial['ok'] for trial in trials)
                and not startup_error and self.jabra_verified(), 'required_trials': 10,
                'requested_trials': self.args.trials, 'completed_trials': len(trials),
                'failed_trials': sum(not trial['ok'] for trial in trials),
                'continue_on_failure': self.args.continue_on_failure,
                'error': startup_error, 'failed_to_start_trial': failed_to_start_trial,
                'zero_self_triggers': all(trial['self_triggers'] == 0 for trial in trials),
                'trials': trials}

    def close(self):
        for request in self.requests:
            request.unlink(missing_ok=True)
        if self.marker_created:
            (self.home / 'diagnostics-enabled').unlink(missing_ok=True)
        # Keep rendered local fixture files as reproducible evidence. They contain no
        # microphone capture, and paths and exact fixture text are in the JSON.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', default='end-to-end')
    parser.add_argument('--mode', choices=('e2e', 'barge-in', 'no-self-trigger', 'full'), default='e2e')
    parser.add_argument('--home', type=Path, default=Path.home() / 'ted-ops/voice')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--trials', type=int, default=10)
    parser.add_argument('--continue-on-failure', action='store_true',
                        help='finish all requested self-trigger trials after a failed measurement')
    parser.add_argument('--interrupt-after', type=float, default=3.5)
    parser.add_argument('--interrupt-phrase', default='Hey Ted, stop.')
    parser.add_argument('--stimulus-voice', default='Daniel',
                        help='macOS voice for external mini-speaker stimuli; fixtures stay Daniel')
    parser.add_argument('--minimum-long-seconds', type=float, default=20)
    args = parser.parse_args()
    if args.trials < 1 or args.minimum_long_seconds < 20 or args.interrupt_after < 1:
        parser.error('trials must be positive, minimum long duration at least 20 seconds, and interruption at least 1 second')
    runner = Runner(args)
    result = {'ok': False, 'mode': args.mode, 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'measurement': 'installed service, native Jabra playback stop acknowledgement, and acoustic mini speaker stimuli',
              'latency_definition': 'accepted wake candidate to native player pause; acoustic onset-to-detection reported separately',
              'limitations': ['say process dispatch is not measured physical acoustic onset',
                              'synthetic room trials do not establish natural voice accuracy in every room position'],
              'checks': {}}
    try:
        runner.prepare()
        if args.mode in ('e2e', 'full'):
            result['checks']['e2e'] = runner.e2e()
        if args.mode in ('barge-in', 'full'):
            result['checks']['barge_in'] = runner.barge_in()
        if args.mode in ('no-self-trigger', 'full'):
            result['checks']['no_self_trigger'] = runner.no_self_trigger()
            if result['checks']['no_self_trigger'].get('error'):
                result['error'] = result['checks']['no_self_trigger']['error']
        result['ok'] = bool(result['checks']) and all(check['ok'] for check in result['checks'].values())
    except Exception as exc:
        result['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        runner.close()
        result.update(routes=runner.routes, devices=getattr(runner, 'devices', []),
                      service=getattr(runner, 'service', {}), stimuli=runner.stimuli,
                      events=runner.rows(runner.started), finished_at=time.time())
        out = args.output or (args.home / ('DEBUG-1026/' + args.name + '.json') if args.mode == 'e2e'
                              else args.home / 'FULL-1027/acceptance.json')
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({'ok': result['ok'], 'mode': args.mode, 'error': result.get('error'),
                          'checks': {key: value['ok'] for key, value in result['checks'].items()},
                          'evidence': str(out)}, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
