import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(os.environ.get('TED_BOARD_ROOT', Path.home() / 'ted-ops/ted-board'))))
source = Path(os.environ.get('MOCKUP_ROUTE_SOURCE', Path.home() / 'ted-ops/ted-decisions/mockup_route.py'))
spec = importlib.util.spec_from_file_location('mockup_route_under_test', source)
route = importlib.util.module_from_spec(spec)
spec.loader.exec_module(route)


class MockupHandoff(unittest.TestCase):
    def test_new_build_card_is_up_next_until_dispatched(self):
        card = route.build_card('Test', 'Approved batch', [{'id': 'm1', 'title': 'Art'}])
        self.assertEqual(card['section'], 'up_next')

    def test_approval_preserves_existing_in_progress_build(self):
        row = dict(id=1, item_id='m1', choice='approved_batch', note='Project JSON: "Test"\nBatch JSON: "Approved batch"', created_at='2020-01-01T00:00:00Z')
        images = [{'id': 'm1', 'title': 'Art'}]
        for existing, expected in ((None, 'up_next'), ({'section': 'needs_you'}, 'up_next'), ({'section': 'ted_doing', 'live_state': 'running'}, 'ted_doing')):
            with self.subTest(expected=expected), patch.object(route, 'call', return_value={}), patch.object(route, 'pending_approval_undo', return_value=False), patch.object(route, 'approved_in_batch', return_value=images), patch.object(route, 'existing_build_card', return_value=existing), patch.object(route, 'publish_approved_card') as publish:
                route.apply(row, lambda _: None)
                self.assertEqual(publish.call_args.kwargs.get('section'), expected)

    def test_refresh_keeps_in_progress_section(self):
        image = dict(id='m1', project='Test', batch='Approved batch')
        with patch.object(route, 'existing_build_card', return_value={'section': 'ted_doing', 'live_state': 'running'}), patch.object(route, 'approved_in_batch', return_value=[image]), patch.object(route, 'publish_approved_card') as publish:
            route.refresh_existing_card(image, {})
            self.assertEqual(publish.call_args.kwargs.get('section'), 'ted_doing')

    def test_publish_serializes_requested_section(self):
        for section in ('up_next', 'ted_doing'):
            with self.subTest(section=section), patch.object(route, 'load_env', return_value={'TED_DECISIONS_WORKER_KEY': 'test'}), patch.object(route.urllib.request, 'urlopen', return_value=io.BytesIO(b'{"ok":true,"count":1}')) as send:
                route.publish_approved_card('Test', 'Batch', [], section=section)
                self.assertEqual(json.loads(send.call_args.args[0].data)['cards'][0]['section'], section)


if __name__ == '__main__':
    unittest.main()
