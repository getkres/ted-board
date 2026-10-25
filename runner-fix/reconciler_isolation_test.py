"""Private baseline byte equality and flag-off behavior, with no real transports."""
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(os.environ['RECONCILER_CANDIDATE']).resolve()
BASE = Path(os.environ.get('RECONCILER_BASELINE', ROOT / 'legacy-baseline')).resolve()
sys.path.append(str(ROOT))
BLOCK = re.compile(rb'^[ \t]*(?:#|//) BEGIN RECONCILER ROUTE\n.*?^[ \t]*(?:#|//) END RECONCILER ROUTE\n', re.M | re.S)


def load(path, name, deps):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, deps), patch.dict(os.environ, {'TED_RECONCILER_ENABLED': 'false'}):
        spec.loader.exec_module(module)
    return module


class LegacyIsolation(unittest.TestCase):
    def setUp(self):
        lanes=patch.dict(os.environ,{'TED_CLAUDE_LANES_CONFIG':str(ROOT/'offline-unconfigured-lanes.json')})
        lanes.start();self.addCleanup(lanes.stop)

    def test_removing_one_guard_restores_every_legacy_source_byte(self):
        names = ('sessions.py', 'session_worker.py', 'live_status.py', 'board_live.py',
                 'jobs_heartbeat.py', 'job_watchdog.py', 'card.py', 'inbox_steward.py', 'handler.ts')
        for name in names:
            with self.subTest(name=name):
                target = ROOT / 'backend/handler.ts' if name == 'handler.ts' else ROOT / name
                raw = target.read_bytes()
                self.assertEqual(len(BLOCK.findall(raw)), 1)
                stripped=BLOCK.sub(b'',raw)
                stripped=re.sub(rb'^// BEGIN RECONCILER SUPPORT\n.*?^// END RECONCILER SUPPORT\n',b'',stripped,flags=re.M|re.S)
                self.assertEqual(stripped, (BASE / name).read_bytes())

    def sessions(self, path, name):
        client = types.SimpleNamespace(BoardConflict=RuntimeError, BoardGone=LookupError,
                                       call=lambda *a, **k: (_ for _ in ()).throw(AssertionError('network forbidden')))
        live = types.SimpleNamespace(instructions=lambda _: 'fixture', publish_live=lambda *a, **k: True)
        with patch.dict(sys.path_importer_cache, {}):
            return load(path, name, {'board_client': client, 'live_status': live})

    def test_flag_off_enqueue_payload_is_byte_identical_and_defaults_to_claude(self):
        modules = [self.sessions(BASE / 'sessions.py', 'before'), self.sessions(ROOT / 'sessions.py', 'after')]
        payloads = []
        for module in modules:
            with tempfile.TemporaryDirectory() as temp, patch.object(module.time, 'time', return_value=1234), \
                    patch.object(module.uuid, 'uuid4', return_value=types.SimpleNamespace(hex='fixture')):
                store = module.Store(temp)
                store.enqueue(dict(id='fixture', title='Fixture task'), 'work', 'receipt')
                raw = json.dumps(store.read(), sort_keys=True).replace(str(Path(temp).resolve()), 'ROOT').encode()
                payloads.append(raw)
                self.assertEqual(store.read()['sessions']['fixture']['engine'], 'claude')
        self.assertEqual(payloads[0], payloads[1])

    def test_flag_off_live_section_move_payload_is_byte_identical(self):
        payloads = []
        for path in (BASE / 'live_status.py', ROOT / 'live_status.py'):
            client = types.SimpleNamespace(BoardGone=LookupError, cards=lambda: [dict(id='fixture', project='Fixture', section='ted_doing')], call=lambda action, **body: payloads.append(json.dumps([action, body], sort_keys=True).encode()) or dict(ok=True, card=dict(id='fixture')))
            module = load(path, 'status_' + str(len(payloads)), {'board_client': client})
            module.update('fixture', 'done', 'finished', section='done')
        self.assertEqual(payloads[0], payloads[1])
        self.assertEqual(json.loads(payloads[0])[1]['section'], 'done')

    def test_flag_off_missing_capacity_keeps_legacy_64_and_separate_2_8_caps(self):
        original_read=Path.read_text
        def missing_capacity(path,*args,**kwargs):
            if path.name=='capacity.json':raise FileNotFoundError()
            return original_read(path,*args,**kwargs)
        for path in (BASE / 'sessions.py', ROOT / 'sessions.py'):
            module = self.sessions(path, 'caps_' + path.parent.name)
            for engine, amount, expected in (('codex', 65, 64), ('claude', 4, 2), ('sonnet', 10, 8)):
                with self.subTest(path=path.name, engine=engine), tempfile.TemporaryDirectory() as temp, patch.object(Path,'read_text',missing_capacity):
                    store = module.Store(temp)
                    for n in range(amount):
                        cid = 'work' + str(n)
                        store.enqueue(dict(id=cid, title='Fixture'), 'work', cid, engine=engine)
                    with patch.object(module.os, 'getloadavg', return_value=(0, 0, 0)), \
                            patch.object(module, 'identity', return_value='fixture'), \
                            patch.object(module.subprocess, 'Popen', return_value=types.SimpleNamespace(pid=98765)):
                        store.tick()
                    self.assertEqual(sum(s['status'] == 'running' for s in store.read()['sessions'].values()), expected)

    def test_flag_off_load_guard_is_unchanged_and_bad_config_does_not_activate(self):
        import reconciler_gate
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'enable.json';path.write_text('{')
            with patch.object(reconciler_gate,'CONFIG_PATH',path),patch.dict(os.environ,{'TED_RECONCILER_ENABLED':'true'}):
                module=self.sessions(ROOT/'sessions.py','invalid_config_legacy')
            store=module.Store(Path(temp)/'jobs')
            store.enqueue(dict(id='fixture',title='fixture'),'work','receipt',engine='codex')
            with patch.object(module.os,'cpu_count',return_value=8),patch.object(module.os,'getloadavg',return_value=(25,0,0)),patch.object(module.subprocess,'Popen',side_effect=AssertionError('load guard must prevent a launch')):
                store.tick()
            self.assertEqual(store.read()['sessions']['fixture']['status'],'queued')


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    unittest.main()
