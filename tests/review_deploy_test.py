import json
from pathlib import Path
import tempfile
import unittest
import deploy_review_gate as deploy
import review_gate as gate


class PodRolloutTests(unittest.TestCase):
    def test_all_businesses_receive_policy_without_execution_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); biz = root / 'biz'; company = root / 'company'
            registry={'schema_version':1,'businesses':{'ops':{'path':'ops','aliases':[],'projects':['Operations'],'whimsy':False},'studio':{'path':'studio','aliases':[],'projects':['Studio'],'whimsy':True},'personal':{'path':'private','aliases':[],'projects':['Private'],'whimsy':False,'scaffold':True}},'shared_rules':['shared/RULES.md'],'design_rules':['shared/DESIGN.md'],'whimsy_rules':['shared/WHIMSY.md']}
            (biz/'_pods').mkdir(parents=True);(biz/'_pods/review-registry.json').write_text(json.dumps(registry))
            for business, entry in registry['businesses'].items():
                relative=entry['path']
                if business == 'personal': continue
                pod = biz / relative / 'pod'; pod.mkdir(parents=True)
                (pod / 'config.json').write_text(json.dumps({'id': business, 'authority': 'read-only'}))
                (pod / 'LEAD.md').write_text('# Existing charter\n')
            template = company / 'pods/_template'; template.mkdir(parents=True)
            (template / 'LEAD.template.md').write_text('# Lead template\n')
            (template / 'config.example.json').write_text('{}')
            changes = deploy.pod_changes(biz, company)
            self.assertEqual(len([p for p in changes if p.name == 'config.json']), len(registry['businesses']))
            for business, entry in registry['businesses'].items():
                relative=entry['path']
                pod = biz / relative / 'pod'
                config = json.loads(changes[pod / 'config.json'])
                self.assertEqual(config['review_gate']['canon_check'], True)
                self.assertEqual(config['review_gate']['review'], True)
                self.assertIn('canon-checker', config['review_gate']['required_reviewers'])
                self.assertIn('review.py', changes[pod / 'LEAD.md'])
                self.assertIn('canon_check', changes[pod / 'LEAD.md'])
                if business != 'personal': self.assertEqual(config['authority'], 'read-only')
                else: self.assertEqual(config['cadence'], {})
                if entry['whimsy']:
                    self.assertIn('whimsy', config['review_gate']['required_reviewers'])
            # Planning never writes a pod or silently registers a routine.
            self.assertFalse((biz / 'private/pod/config.json').exists())
            for p, text in changes.items(): p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)
            self.assertEqual(changes, deploy.pod_changes(biz, company))


if __name__ == '__main__': unittest.main()
