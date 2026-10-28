"""Contract tests for the shared content gate. No network or model calls."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import review_gate as gate
import review
from review_unit_fixtures import collect_approvals, status_module


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.biz = self.root / 'biz'
        self.job = self.root / 'job'
        self.job.mkdir()
        business = self.biz / 'ops'
        (business / 'pod').mkdir(parents=True)
        for name in ('CANON.md', 'DECISIONS.md'):
            (business / name).write_text('# Locked\nUse sourced facts.\n')
        hard = self.root / 'company/HARD-RULES.md'
        hard.parent.mkdir(parents=True)
        hard.write_text('No sends or spending.\n')
        design = self.biz / 'design/DESIGN-JOB-RULES.md'
        design.parent.mkdir(parents=True); design.write_text('Review all designs.\n')
        (design.parent / 'DESIGN-CANON.md').write_text('Use the approved design.\n')
        rubric=self.biz/'design/WHIMSY-CHECK.md'
        rubric.parent.mkdir(parents=True,exist_ok=True);rubric.write_text('Design whimsy must be at least 9.\n')
        self.config = business / 'pod/config.json'
        self.config.write_text(json.dumps({'id': 'ted-ops', 'review_gate': {
            'required_reviewers': list(gate.BASE_REVIEWERS), 'model': 'opus',
            'canon_check': True, 'review': True,
        }}))
        (self.job / 'REPORT.md').write_text('A sourced internal report.\n')
        registry={'schema_version':1,'businesses':{'ted':{'path':'ops','aliases':['Ted ops'],'projects':['Ted ops'],'whimsy':False},'library':{'path':'library','aliases':['Library'],'projects':['Library'],'whimsy':True}},'shared_rules':['../company/HARD-RULES.md'],'design_rules':['design/DESIGN-JOB-RULES.md'],'whimsy_rules':['design/DESIGN-CANON.md','design/WHIMSY-CHECK.md']}
        (self.biz/'_pods').mkdir();(self.biz/'_pods/review-registry.json').write_text(json.dumps(registry))
        self.maker = {'agent': 'codex', 'model': 'test-maker', 'session_id': 'maker-session'}

    def model(self, command, **kwargs):
        if command[1:3] == ['auth', 'status']:
            return subprocess.CompletedProcess(command,0,json.dumps({'loggedIn':True,'authMethod':'claude.ai','subscriptionType':'max'}),'')
        role = command[command.index('--append-system-prompt') + 1].split('ROLE: ')[1].split('\n')[0]
        sid = command[command.index('--session-id') + 1]
        request = json.loads((self.job / 'review-request.json').read_text())
        result = {'agent': role, 'verdict': 'pass', 'findings': [],
                  'what_changed': ['No changes required.'],
                  'items_reviewed': [x['path'] for x in request['items']]}
        if role == 'whimsy': result['score'] = getattr(self, 'whimsy_score', 9)
        return subprocess.CompletedProcess(command, 0, json.dumps({
            'type': 'result', 'session_id': sid, 'is_error': False,
            'modelUsage': {'test-reviewer': {}}, 'result': json.dumps(result),
        }), '')

    def passing(self, **kwargs):
        with patch.object(review.subprocess, 'run', side_effect=self.model):
            return review.run_review(self.job, 'ted', self.maker, biz_root=self.biz, **kwargs)

    def validate(self, **kwargs):
        return gate.validate_review(self.job, biz_root=self.biz, **kwargs)

    def test_missing_review_is_refused(self):
        with self.assertRaises(gate.ReviewBlocked): self.validate()

    def test_full_pass_has_independent_sessions_and_actual_models(self):
        self.passing()
        record = self.validate(required_paths=['REPORT.md'])
        ids = [x['session_id'] for x in record['reviewers']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertNotIn('maker-session', ids)
        self.assertTrue(all(x['model'] == 'test-reviewer' for x in record['reviewers']))

    def test_fix_and_kill_block_even_if_summary_claims_pass(self):
        for verdict in ('fix', 'kill'):
            self.passing()
            p = self.job / 'review.json'
            data = json.loads(p.read_text())
            data['reviewers'][0]['verdict'] = verdict
            p.write_text(json.dumps(data))
            with self.assertRaises(gate.ReviewBlocked): self.validate()

    def test_content_context_and_receipt_changes_invalidate_review(self):
        targets = [self.job / 'REPORT.md', self.config]
        for target in targets:
            self.passing()
            old = target.read_text()
            target.write_text(old + '\n')
            with self.assertRaises(gate.ReviewBlocked): self.validate()
            target.write_text(old)
        self.passing()
        record = json.loads((self.job / 'review.json').read_text())
        receipt = self.job / record['reviewers'][0]['evidence']['path']
        receipt.write_text('{}')
        with self.assertRaises(gate.ReviewBlocked): self.validate()

    def test_new_approval_artifact_cannot_reuse_report_review(self):
        self.passing()
        (self.job / 'draft-email.json').write_text('{"text":"new draft"}')
        with self.assertRaises(gate.ReviewBlocked): self.validate()

    def test_missing_reviewer_and_self_review_block(self):
        for mutation in ('missing', 'self', 'reused'):
            self.passing()
            p = self.job / 'review.json'; data = json.loads(p.read_text())
            if mutation == 'missing': data['reviewers'].pop()
            elif mutation == 'self': data['reviewers'][0]['session_id'] = 'maker-session'
            else: data['reviewers'][0]['session_id'] = data['reviewers'][1]['session_id']
            p.write_text(json.dumps(data))
            with self.assertRaises(gate.ReviewBlocked): self.validate()

    def test_business_mismatch_and_unknown_business_block(self):
        self.passing()
        with self.assertRaises(gate.ReviewBlocked): self.validate(project='Library')
        with self.assertRaises(gate.ReviewBlocked): gate.policy('unknown', self.biz)

    def test_reviewer_timeout_invalidates_old_pass(self):
        self.passing()
        with patch.object(review.subprocess, 'run', side_effect=subprocess.TimeoutExpired('claude', 1)):
            with self.assertRaises(gate.ReviewBlocked):
                review.run_review(self.job, 'ted', self.maker, biz_root=self.biz)
        with self.assertRaises(gate.ReviewBlocked): self.validate()

    def test_symlink_and_traversal_items_block(self):
        outside = self.root / 'outside.txt'; outside.write_text('private')
        (self.job / 'linked.txt').symlink_to(outside)
        for name in ('linked.txt', '../outside.txt'):
            with self.assertRaises(gate.ReviewBlocked):
                review.run_review(self.job, 'ted', self.maker, paths=[name], biz_root=self.biz)

    def test_upload_requires_exact_batch_and_generated_attribution(self):
        from PIL import Image
        Image.new('RGB', (10, 10), 'red').save(self.job / 'frame.png')
        upload = {'project': 'Ted ops', 'batch': 'test batch',
                  'images': [{'path': 'frame.png', 'title': 'Frame', 'sort': 0}]}
        self.passing(paths=['frame.png'], upload=upload)
        images = gate.validate_upload(self.job, 'Ted ops', 'test batch', biz_root=self.biz)
        self.assertEqual(images[-1]['title'], gate.ATTRIBUTION_TITLE)
        with self.assertRaises(gate.ReviewBlocked):
            gate.validate_upload(self.job, 'Ted ops', 'another batch', biz_root=self.biz)
        (self.job / images[-1]['path']).write_bytes(b'not attribution')
        with self.assertRaises(gate.ReviewBlocked): self.validate()

    def test_weak_pod_configuration_cannot_remove_required_reviewers(self):
        config = json.loads(self.config.read_text())
        config['review_gate']['required_reviewers'] = ['canon-checker']
        self.config.write_text(json.dumps(config))
        with self.assertRaises(gate.ReviewBlocked): self.passing()

    def test_full_pass_upload_delivers_attribution_first(self):
        import mockup_upload
        from PIL import Image
        Image.new('RGB', (10, 10), 'red').save(self.job / 'frame.png')
        upload = {'project': 'Ted ops', 'batch': 'test batch',
                  'images': [{'path': 'frame.png', 'title': 'Frame', 'sort': 0}]}
        self.passing(paths=['frame.png'], upload=upload)
        with patch.object(gate, 'BIZ_ROOT', self.biz), \
                patch.object(mockup_upload, 'UPLOAD_LOG', self.root / 'upload.log'), \
                patch.object(mockup_upload, 'call', return_value={'mockup': {'id': 'fixture'}}) as send, \
                patch('sync.load_env', return_value={'TED_DECISIONS_KEY': 'fixture'}), \
                patch.object(mockup_upload.subprocess, 'run') as notification:
            notification.return_value.returncode = 0
            self.assertEqual(mockup_upload.main(['--job-dir', str(self.job), '--project', 'Ted ops', '--batch', 'test batch']), 0)
            self.assertEqual([c.kwargs['title'] for c in send.call_args_list], [gate.ATTRIBUTION_TITLE, 'Frame'])

    def test_full_pass_allows_needs_you_and_kill_then_blocks(self):
        live_status = status_module()
        self.passing()
        (self.root / 'sessions.json').write_text(json.dumps({'sessions': {'x': {
            'cwd': str(self.job), 'project': 'Ted ops'}}}))
        card = {'id': 'x', 'project': 'Ted ops', 'section': 'ted_doing'}
        with patch.object(gate, 'BIZ_ROOT', self.biz), \
                patch.object(live_status, 'validate_card', side_effect=lambda cid: gate.validate_card(cid, self.root)), \
                patch.object(live_status.board_client, 'cards', return_value=[card]), \
                patch.object(live_status.board_client, 'resolve_rule', return_value={'outcome': 'ask', 'reason': None}), \
                patch.object(live_status, 'call', return_value={'ok': True, 'card': card}) as send:
            self.assertEqual(live_status.update('x', 'waiting_on_you', 'review this', section='needs_you'), card)
            record = json.loads((self.job / 'review.json').read_text())
            record['reviewers'][0]['verdict'] = 'kill'
            (self.job / 'review.json').write_text(json.dumps(record)); send.reset_mock()
            with self.assertRaises(gate.ReviewBlocked): live_status.update('x', 'waiting_on_you', 'review this', section='needs_you')
            send.assert_not_called()

    def test_full_pass_stages_approval_and_stale_review_hides_it(self):
        import sessions
        store = sessions.Store(self.root / 'jobs')
        store.enqueue({'id': 'x', 'title': 'Test', 'project': 'Ted ops'}, 'work', 'receipt')
        with store.locked() as data:
            s = data['sessions']['x']; s.update(status='done', queue=[])
            self.job = Path(s['cwd'])
        (self.job / 'REPORT.md').write_text('Draft for review.\n')
        (self.job / 'draft-email.json').write_text('{"text":"draft","recipient":"fixture@example.invalid"}')
        self.passing()
        with patch.object(gate, 'BIZ_ROOT', self.biz):
            collect_approvals(store)
            self.assertEqual(len(store.snapshot()[1]), 1)
            (self.job / 'draft-email.json').write_text('{"text":"changed"}')
            self.assertEqual(store.snapshot()[1], [])

    def test_whimsy_score_below_nine_blocks(self):
        target = self.biz / 'library'
        (target / 'pod').mkdir(parents=True)
        for name in ('CANON.md', 'DECISIONS.md'): (target / name).write_text('Use sourced facts.\n')
        (target / 'pod/config.json').write_text(json.dumps({'review_gate': {
            'required_reviewers': [*gate.BASE_REVIEWERS, 'whimsy'], 'model': 'opus', 'canon_check': True, 'review': True}}))
        self.whimsy_score = 8
        with patch.object(review.subprocess, 'run', side_effect=self.model):
            with self.assertRaises(gate.ReviewBlocked): review.run_review(self.job, 'library', self.maker, design=True,biz_root=self.biz)
        self.whimsy_score = 9
        with patch.object(review.subprocess, 'run', side_effect=self.model):
            review.run_review(self.job, 'library', self.maker, design=True,biz_root=self.biz)
        self.assertEqual(self.validate()['reviewers'][-1]['score'], 9)

        self.whimsy_score=4
        with patch.object(review.subprocess,'run',side_effect=self.model):
            review.run_review(self.job,'library',self.maker,biz_root=self.biz)
        self.assertEqual(self.validate()['reviewers'][-1]['score'],4)

    def test_live_maker_identity_is_read_from_execution_records(self):
        (self.job/'maker-config.json').write_text(json.dumps({'agent':'codex','model':'configured-model','events':'turn.events','project':'Ted ops'}))
        (self.job/'turn.events').write_text(json.dumps({'type':'thread.started','thread_id':'actual-session'})+'\n')
        maker,project=review.live_maker(self.job)
        self.assertEqual(maker,{'agent':'codex','model':'configured-model','session_id':'actual-session'})
        self.assertEqual(project,'Ted ops')
        (self.job/'maker-config.json').write_text(json.dumps({'agent':'claude','model':'','events':'turn.events'}))
        (self.job/'turn.events').write_text(json.dumps({'type':'system','session_id':'actual-claude','model':'actual-model'})+'\n')
        self.assertEqual(review.live_maker(self.job)[0]['model'],'actual-model')

    def test_reviewer_environment_cannot_select_paid_api_credentials(self):
        environment=review.plan_environment({'HOME':'fixture-home','PATH':'fixture-path','ANTHROPIC_API_KEY':'fixture',
            'ANTHROPIC_BASE_URL':'fixture','ANTHROPIC_AUTH_TOKEN':'fixture','CLAUDE_CODE_USE_BEDROCK':'1','CLAUDECODE':'1'})
        self.assertEqual(environment,{'HOME':'fixture-home','PATH':'fixture-path'})

    def test_a_failed_reviewer_stops_the_chain(self):
        roles=[]
        def fix(command,**kwargs):
            result=self.model(command,**kwargs)
            if '--append-system-prompt' in command:
                raw=json.loads(result.stdout);response=json.loads(raw['result'])
                roles.append(response['agent']);response.update(verdict='fix',findings=['Revise the unsupported claim.'])
                raw['result']=json.dumps(response);result.stdout=json.dumps(raw)
            return result
        with patch.object(review.subprocess,'run',side_effect=fix):
            with self.assertRaises(gate.ReviewBlocked):review.run_review(self.job,'ted',self.maker,biz_root=self.biz)
        self.assertEqual(roles,['canon-checker'])
        self.assertEqual(json.loads((self.job/'review.json').read_text())['failure_reason'],'reviewer_verdict')

    def test_unfixed_reasons_are_bound_to_the_attribution_card(self):
        from PIL import Image
        Image.new('RGB',(8,8)).save(self.job/'frame.png')
        upload={'project':'Ted ops','batch':'test','images':[{'path':'frame.png','title':'Frame','sort':0}],
                'unfixed':[{'finding':'Secondary note remains small.','reason':'The owner requested the full evidence on one card.'}]}
        self.passing(upload=upload)
        record=self.validate()
        self.assertEqual(record['unfixed'],upload['unfixed'])
        record['unfixed'][0]['reason']='Changed after review'
        (self.job/'review.json').write_text(json.dumps(record))
        with self.assertRaises(gate.ReviewBlocked):self.validate()

    def test_transport_refuses_upload_without_provenance_before_loading_secrets(self):
        import mockup_client
        with patch.object(mockup_client, 'load_env') as secrets:
            with self.assertRaises(gate.ReviewBlocked): mockup_client.call('upload', project='Ted ops', batch='test')
            secrets.assert_not_called()


if __name__ == '__main__': unittest.main()
