"""Mock a satisfied review prerequisite for legacy upload unit tests.

Those tests isolate transport recovery and supersession. Real fail-closed and
full-pass contracts are exercised separately in review_gate_test.py.
"""
from contextlib import contextmanager
import json
from pathlib import Path
from unittest.mock import patch
import mockup_upload


def artifact_prerequisite(directory, **kwargs):
    """A satisfied gate for tests that isolate artifact serialization."""
    return {'items': [{'path': p.name, 'sha256': mockup_upload.digest(p)}
                      for p in Path(directory).iterdir() if p.is_file()]}


@contextmanager
def upload_prerequisite(job, images, title='Test'):
    rows = [{'path': p.name, 'title': title if i == 0 else title + ': ' + p.stem, 'sort': i}
            for i, p in enumerate(images)]
    receipt = Path(job) / 'unit-upload-receipts.jsonl'
    receipt.write_text('\n'.join(json.dumps({'mockup_id': 'same-row', 'project': 'Ted ops',
        'batch': 'test', 'source': str(p.resolve()), 'sha256': mockup_upload.digest(p)}) for p in images))
    with patch.object(mockup_upload, 'validate_upload', return_value=rows), \
            patch.object(mockup_upload, 'UPLOAD_LOG', receipt):
        yield


def status_module():
    """The module whose update() is live: reconciler_status when routed."""
    import sys
    import live_status
    return sys.modules[live_status.update.__module__]


def collect_approvals(store):
    """Collect on the live path. The reconciler only stages with reconcile=True."""
    import inspect
    if 'reconcile' in inspect.signature(store.collect_approvals).parameters:
        return store.collect_approvals(reconcile=True)
    return store.collect_approvals()
