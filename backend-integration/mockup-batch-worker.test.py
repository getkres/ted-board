"""Exercise the private watcher with synthetic receipts and no network or real queue."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types


def forbidden(*args, **kwargs):
    raise AssertionError('Live transport or build routing must not run in this test')


def main():
    data = json.load(sys.stdin)
    # Import the actual worker while replacing every operational dependency first.
    for name, attrs in {
        'mockup_client': {'call': forbidden},
        'board_client': {'cards': forbidden},
        'live_status': {'update': forbidden},
        'sync': {'ENDPOINT': 'https://fixture.invalid/', 'load_env': forbidden},
    }.items():
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module
    spec = importlib.util.spec_from_file_location('batch_note_worker_under_test', sys.argv[1])
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    replies = []

    def call(action=None, **payload):
        if action is None:
            return {'mockups': data['mockups'], 'pins': data['pins']}
        assert action == 'ted_reply'
        replies.append(payload)
        return {'ok': True}

    worker.call = call
    worker.publish_approved_card = forbidden
    worker.existing_build_card = forbidden
    worker.refresh_existing_card = forbidden
    worker.urllib.request.urlopen = forbidden
    with tempfile.TemporaryDirectory(prefix='batch-note-worker-') as directory:
        worker.QUEUE = Path(directory) / 'design-queue.md'
        for receipt in data['receipts']:
            assert worker.apply(receipt, lambda message: None) == 'design queue'
        lines = worker.QUEUE.read_text().splitlines()
        expected = 1 if data.get('batch_only') else 2
        assert len(lines) == expected
        assert all('Mockup feedback:' in line for line in lines)
        if expected == 2:
            assert 'Image detail' in lines[0]
        assert 'Feedback scope: whole-batch' in lines[-1]
        assert data['batch_pin_id'] in lines[-1]
        assert len(replies) == expected
        assert all(reply['pin_id'] in [r['item_id'] for r in data['receipts']] for reply in replies)
    print('Actual watcher routes image and whole-batch notes to the same isolated design queue.')


if __name__ == '__main__':
    main()
