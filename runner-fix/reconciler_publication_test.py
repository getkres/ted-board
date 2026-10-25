"""Planner packets round-trip through the actual server validator without I/O effects."""
import reconciler_test_support
import copy
import json
import os
from pathlib import Path
import subprocess
import unittest
import reconciler as r
import reconciler_runtime as runtime

NOW=1800000000
URL='https://github.com/example/shared/pull/17'
ROOT=Path(__file__).resolve().parents[1]


def shared_pr_snapshot():
 cards=[dict(id=cid,title='Delivery '+cid,project='example',section='ted_doing',owner='ted',
             created_at=r.iso(NOW-14*3600),updated_at=r.iso(NOW-10),revision=7,messages=[],
             action_started_at=r.iso(NOW-14*3600),next_action_due=r.iso(NOW-1),
             reconciliation_stage=stage) for cid,stage in (('c-alpha','merged'),('c-beta','deployed'))]
 return dict(cards=cards,sessions={},approvals=[],mockups=[],coverage={},
             prs={URL:dict(state='MERGED',created_at=r.iso(NOW-14*3600),merged_at=r.iso(NOW-13*3600),merge_revision='merge-sha')},
             workflows={'c-alpha':dict(pr_url=URL),
                        'c-beta':dict(pr_url=URL,deployment=dict(verified=True,deployed_at=r.iso(NOW-7*3600),revision='merge-sha'))})


def validated(plan):
 packet={key:plan[key] for key in ('generated_at','items','banner','ted_queue','coverage_defects')}
 script="""import {validateReconciliationPublish} from './backend-integration/reconciliation.ts';
 const packet=JSON.parse(await new Response(Deno.stdin.readable).text());
 console.log(JSON.stringify(validateReconciliationPublish(packet,Date.parse(packet.generated_at))));"""
 result=subprocess.run([os.environ.get('DENO_BINARY','deno'),'eval','--ext=ts',script],cwd=ROOT,
                       input=json.dumps(packet),capture_output=True,text=True,check=True)
 return json.loads(result.stdout)


class PublicationTests(unittest.TestCase):
 def test_shared_pr_keeps_both_card_associations_and_independent_delivery_evidence(self):
  result=r.plan(shared_pr_snapshot(),now=NOW)
  rows=[row for row in result['items'] if row['kind']=='pr']
  self.assertEqual(len(rows),2)
  self.assertEqual(len({row['id'] for row in rows}),2)
  self.assertEqual({row['card_id']:(row['stage'],row['action_started_at'],row['next_action_due']) for row in rows},
                   {'c-alpha':('merged',r.iso(NOW-13*3600),r.iso(NOW-7*3600)),
                    'c-beta':('deployed',r.iso(NOW-7*3600),r.iso(NOW-3600))})
  self.assertNotIn('close_verified',[action['kind'] for action in result['actions']])

 def test_card_scoped_pr_identity_survives_input_order_and_another_card_unlinking(self):
  snapshot=shared_pr_snapshot()
  first={row['card_id']:row['id'] for row in r.plan(snapshot,now=NOW)['items'] if row['kind']=='pr'}
  snapshot['cards'].reverse();snapshot['workflows']=dict(reversed(list(snapshot['workflows'].items())))
  reordered={row['card_id']:row['id'] for row in r.plan(snapshot,now=NOW+120)['items'] if row['kind']=='pr'}
  self.assertEqual(reordered,first)
  del snapshot['workflows']['c-alpha']
  remaining=next(row for row in r.plan(snapshot,now=NOW+120)['items'] if row['kind']=='pr')
  self.assertEqual((remaining['card_id'],remaining['id']),('c-beta',first['c-beta']))

 def test_legacy_pr_aging_receipts_still_suppress_completed_actions(self):
  legacy_entity='pr:'+r.digest(URL)
  generations=[('merged',r.iso(NOW-13*3600),('escalate_2h','escalate_12h')),
               ('deployed',r.iso(NOW-7*3600),('escalate_2h',))]
  receipts={r.digest(kind,legacy_entity,[stage,started]) for stage,started,kinds in generations for kind in kinds}
  first=r.plan(shared_pr_snapshot(),now=NOW)
  actual={action['id'] for action in first['actions'] if action['entity'].startswith('pr:')}
  self.assertEqual(actual,receipts)
  for now in (NOW,NOW+120):
   remaining=r.plan(shared_pr_snapshot(),completed=receipts,now=now)
   self.assertFalse(any(action['entity'].startswith('pr:') for action in remaining['actions']))

 def test_initial_digest_retains_both_delivery_associations(self):
  selected,_=runtime.select_pass(r.plan(shared_pr_snapshot(),now=NOW),set())
  digest=next(action for action in selected if action['kind']=='escalation_digest')
  self.assertEqual({row['card_id'] for row in digest['payload']['items'] if row['kind']=='pr'}, {'c-alpha','c-beta'})

 def test_actual_validator_roundtrip_preserves_every_item_and_queue_reference(self):
  plan=r.plan(shared_pr_snapshot(),now=NOW)
  result=validated(plan)
  self.assertEqual(result['items'],plan['items'])
  self.assertEqual(result['ted_queue'],plan['ted_queue'])
  self.assertEqual(result.get('coverage_defects',[]),[])
  by_id={row['id']:row for row in result['items']}
  self.assertTrue(all(by_id[key]['owner']=='ted' for key in result['ted_queue']))

 def test_roundtrip_control_detects_the_previous_url_only_identity_collision(self):
  plan=copy.deepcopy(r.plan(shared_pr_snapshot(),now=NOW))
  rows=[row for row in plan['items'] if row['kind']=='pr']
  rows[1]['id']=rows[0]['id']
  result=validated(plan)
  self.assertEqual(len(result['items']),len(plan['items'])-1)
  self.assertTrue(any(defect.startswith('item_row:') for defect in result['coverage_defects']))


if __name__=='__main__':unittest.main()
