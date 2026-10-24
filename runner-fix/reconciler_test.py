import reconciler_test_support
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import reconciler as r

NOW=1800000000

def card(**kw):
 return {**dict(id='c-one',title='test work',project='test',section='up_next',created_at=r.iso(NOW-100),updated_at=r.iso(NOW-100)),**kw}

def snapshot(cards=None,**kw):
 return dict(cards=[card()] if cards is None else cards,sessions={},approvals=[],mockups=[],prs={},workflows={},coverage={},**kw)

class PlannerTests(unittest.TestCase):
 def test_missing_owner_and_due_are_visible_and_stable(self):
  s=snapshot();a=r.plan(s,now=NOW);b=r.plan(s,now=NOW+120)
  self.assertEqual(a['items'][0]['owner'],'ted')
  self.assertEqual(a['items'][0]['next_action_due'],b['items'][0]['next_action_due'])
  self.assertIn('repair_metadata',[x['kind'] for x in a['actions']])
 def test_expired_lease_is_dead_even_with_live_pid(self):
  s=snapshot();s['sessions']={'c-one':dict(status='running',turn='t',pid=123,identity='identity',lease_expires_at=NOW-1,lease_token='fence',retry_count=0)}
  actions=r.plan(s,now=NOW)['actions'];retry=next(x for x in actions if x['kind']=='retry')
  self.assertEqual(retry['payload']['expected_lease_token'],'fence')
 def test_result_wins_over_lease_expiry(self):
  s=snapshot();s['sessions']={'c-one':dict(status='running',turn='t',lease_expires_at=0,result_ready=True)}
  self.assertNotIn('retry',[x['kind'] for x in r.plan(s,now=NOW)['actions']])
 def test_retry_exhaustion_dead_letters_to_ted(self):
  s=snapshot();s['sessions']={'c-one':dict(status='failed',turn='t',retry_count=2)}
  p=r.plan(s,now=NOW);self.assertIn('dead_letter',[x['kind'] for x in p['actions']]);self.assertEqual(p['items'][0]['owner'],'ted')
 def test_approval_execution_is_never_automatically_retried(self):
  s=snapshot();s['sessions']={'c-one':dict(status='running',turn='t',lease_expires_at=0,reviewing='approval')}
  self.assertNotIn('retry',[x['kind'] for x in r.plan(s,now=NOW)['actions']])
 def test_priority_explicit_then_revenue_then_age(self):
  old=card();old['created_at']=r.iso(NOW-10000)
  revenue={**card(),'id':'c-revenue','priority_class':'revenue'}
  urgent={**card(),'id':'c-urgent','explicit_ask':True}
  self.assertEqual([x['id'] for x in sorted([old,revenue,urgent],key=r.priority_key)],['c-urgent','c-revenue','c-one'])
 def test_escalation_uses_action_age_and_only_reserved_kind_reaches_sebastian(self):
  c=card(owner='ted',next_action_due=r.iso(NOW-1),action_started_at=r.iso(NOW-25*3600))
  a=r.plan(snapshot([c]),now=NOW);self.assertTrue(a['banner']);self.assertNotIn('sebastian_escalation',[x['kind'] for x in a['actions']])
  c.update(decision_kind='spend_money',owner='sebastian',section='needs_you')
  self.assertIn('sebastian_escalation',[x['kind'] for x in r.plan(snapshot([c]),now=NOW)['actions']])
 def test_heartbeat_does_not_reset_review_age(self):
  c=card(owner='ted',next_action_due=r.iso(NOW-1),action_started_at=r.iso(NOW-7*3600));c['live_status']='ted review pending';c['updated_at']=r.iso(NOW)
  p=r.plan(snapshot([c]),now=NOW);self.assertEqual(p['ted_queue'][0],'card:c-one')
  self.assertIn('review_sla',[x['kind'] for x in p['actions']])
 def test_twelfth_hour_escalation_fires_once_per_stage(self):
  c=card(owner='ted',next_action_due=r.iso(NOW-1),action_started_at=r.iso(NOW-13*3600))
  actions=r.plan(snapshot([c]),now=NOW)['actions'];self.assertTrue(any(x['kind']=='escalate_12h' for x in actions))
  ids={x['id'] for x in actions};p=r.plan(snapshot([c]),completed=ids,now=NOW+120)
  self.assertFalse(any(x['kind']=='escalate_12h' for x in p['actions']))
 def test_approved_build_id_is_deterministic_and_reuses_existing(self):
  s=snapshot(cards=[]);s['mockups']=[dict(id='m1',project='test',batch='round 1',verdict='approved',created_at=r.iso(NOW-50),status='archived')]
  p=r.plan(s,now=NOW);a=next(x for x in p['actions'] if x['kind']=='create_build')
  self.assertEqual(a['payload']['card_id'],next(x for x in r.plan(s,now=NOW+120)['actions'] if x['kind']=='create_build')['payload']['card_id'])
  s['cards']=[{**card(),'id':a['payload']['card_id']}]
  self.assertFalse(any(x['kind']=='create_build' for x in r.plan(s,now=NOW)['actions']))
 def test_pr_merge_requires_deploy_then_verify_receipts(self):
  s=snapshot();s['workflows']={'c-one':dict(pr_url='https://github.com/example/test/pull/1')};s['prs']={'https://github.com/example/test/pull/1':dict(state='MERGED',merged_at=r.iso(NOW-10),merge_revision='sha')}
  self.assertEqual(r.workflow_stage(s,'c-one'),'merged')
  s['workflows']['c-one']['deployment']={'verified':True,'deployed_at':r.iso(NOW),'revision':'sha'}
  self.assertEqual(r.workflow_stage(s,'c-one'),'deployed')
  s['workflows']['c-one']['verification']={'ok':True,'verified_at':r.iso(NOW),'revision':'sha'}
  self.assertEqual(r.workflow_stage(s,'c-one'),'verified')
 def test_receipts_for_another_revision_never_verify_new_merge(self):
  s=snapshot();s['workflows']={'c-one':dict(pr_url='https://github.com/example/test/pull/1',deployment={'verified':True,'deployed_at':r.iso(NOW-5),'revision':'old'},verification={'ok':True,'verified_at':r.iso(NOW-1),'revision':'old'})};s['prs']={'https://github.com/example/test/pull/1':dict(state='MERGED',merged_at=r.iso(NOW-10),merge_revision='new')}
  self.assertEqual(r.workflow_stage(s,'c-one',now=NOW),'merged')
 def test_consumed_veto_failure_is_never_retried(self):
  s=snapshot();s['sessions']={'c-one':dict(status='failed',turn='t',veto_outcome={'status':'uncertain'},active_turn={'veto_proposal_id':'v'})}
  self.assertNotIn('retry',[x['kind'] for x in r.plan(s,now=NOW)['actions']])
 def test_uncertain_taste_classification_cannot_remove_current_ask(self):
  c=card(section='needs_you',classification_uncertain=True)
  self.assertNotIn('route_ted',[x['kind'] for x in r.plan(snapshot([c]),now=NOW)['actions']])
 def test_verified_delivery_never_closes_and_retries_active_work_together(self):
  s=snapshot();s['workflows']={'c-one':dict(pr_url='https://github.com/example/test/pull/1',deployment={'verified':True,'deployed_at':r.iso(NOW-5),'revision':'sha'},verification={'ok':True,'verified_at':r.iso(NOW-1),'revision':'sha'})};s['prs']={'https://github.com/example/test/pull/1':dict(state='MERGED',merged_at=r.iso(NOW-10),merge_revision='sha')};s['sessions']={'c-one':dict(status='running',turn='t',lease_expires_at=NOW-1)}
  kinds=[x['kind'] for x in r.plan(s,now=NOW)['actions']]
  self.assertFalse('close_verified' in kinds and 'retry' in kinds)
 def test_transition_start_never_moves_backward(self):
  c=card(owner='ted',reconciliation_stage='pr',action_started_at=r.iso(NOW-5),next_action_due=r.iso(NOW+100))
  s=snapshot([c]);s['workflows']={'c-one':{'pr_url':'https://github.com/example/test/pull/1'}};s['prs']={'https://github.com/example/test/pull/1':{'state':'MERGED','merged_at':r.iso(NOW-10)}}
  self.assertGreaterEqual(r.stamp(r.plan(s,now=NOW)['items'][0]['action_started_at']),NOW-5)
 def test_merged_pr_age_starts_at_merge_not_initial_pr_creation(self):
  s=snapshot();s['workflows']={'c-one':{'pr_url':'https://github.com/example/test/pull/1'}};s['prs']={'https://github.com/example/test/pull/1':{'state':'MERGED','created_at':r.iso(NOW-10000),'merged_at':r.iso(NOW-10),'merge_revision':'sha'}}
  row=next(x for x in r.plan(s,now=NOW)['items'] if x['kind']=='pr')
  self.assertEqual(row['action_started_at'],r.iso(NOW-10))
 def test_final_approval_parity_and_active_undo(self):
  for row,expected in (({'verdict':'good_with_fix','status':'open'},False),({'verdict':None,'status':'picked'},True),({'verdict':'approved','verdict_change':{'undo_until':r.iso(NOW+5)}},False)):
   s=snapshot(cards=[]);s['mockups']=[dict(id='m',project='test',batch='b',created_at=r.iso(NOW),**row)]
   self.assertEqual(any(x['kind']=='create_build' for x in r.plan(s,now=NOW)['actions']),expected)
 def test_partial_observation_is_not_a_healthy_empty_feed(self):
  s=snapshot();s['coverage']={'mockups':'unavailable'}
  p=r.plan(s,now=NOW);self.assertIn('coverage_defect',[x['kind'] for x in p['actions']]);self.assertTrue(p['coverage_defects'])
 def test_priority_uses_unanswered_explicit_ask_and_launch_metadata(self):
  urgent=card();urgent['messages']=[{'who':'seb','text':'build this','at':r.iso(NOW-2)}]
  revenue={**card(),'id':'c-launch','body':'launch the client revenue page'}
  s=snapshot([revenue,urgent]);r.classify_priorities(s,{})
  self.assertEqual(sorted(s['cards'],key=r.priority_key)[0]['id'],'c-one')
  self.assertEqual(revenue['priority_class'],'launch')
  r.classify_priorities(s,{'c-one':{'priority_class':'ordinary','explicit_ask':False}})
  self.assertEqual(urgent['priority_class'],'ordinary');self.assertFalse(urgent['explicit_ask'])
 def test_overdue_ted_work_enters_ranked_queue(self):
  c=card(owner='ted',next_action_due=r.iso(NOW-1),action_started_at=r.iso(NOW-3*3600))
  self.assertIn('card:c-one',r.plan(snapshot([c]),now=NOW)['ted_queue'])
 def test_unavailable_pr_retains_merged_evidence(self):
  c=card(owner='ted',reconciliation_stage='merged',action_started_at=r.iso(NOW-10),next_action_due=r.iso(NOW+100))
  s=snapshot([c]);s['workflows']={'c-one':{'pr_url':'https://github.com/example/test/pull/1'}}
  self.assertEqual(r.plan(s,now=NOW)['items'][0]['stage'],'merged')
 def test_detached_workers_remain_visible(self):
  s=snapshot(cards=[]);s['sessions']={'deleted-card':{'status':'running','turn':'t','lease_token':'f','lease_expires_at':NOW-1,'started_at':NOW-200}}
  p=r.plan(s,now=NOW);self.assertTrue(any(x['id']=='job:deleted-card' for x in p['items']));self.assertTrue(p['ted_queue'])
 def test_reuses_watcher_build_identity(self):
  import hashlib,json
  expected='mockup-build-'+hashlib.sha256(json.dumps(['test','round'],separators=(',',':')).encode()).hexdigest()[:24]
  s=snapshot(cards=[]);s['mockups']=[dict(id='m',project='test',batch='round',verdict='approved',created_at=r.iso(NOW))]
  self.assertEqual(next(x for x in r.plan(s,now=NOW)['actions'] if x['kind']=='create_build')['payload']['card_id'],expected)
 def test_shared_policy_preserves_real_decision_and_rejects_failure(self):
  c=card(inbox_decision='pricing',decision_kind='other',section='needs_you')
  self.assertNotIn('route_ted',[x['kind'] for x in r.plan(snapshot([c]),now=NOW)['actions']])
  c['inbox_decision']=None;c['decision_kind']='spend_money'
  self.assertIn('route_ted',[x['kind'] for x in r.plan(snapshot([c]),now=NOW)['actions']])
 def test_completed_jobs_are_not_open_work_items(self):
  s=snapshot();s['sessions']={'c-one':dict(status='done',turn='t')}
  self.assertFalse(any(x['kind']=='job' for x in r.plan(s,now=NOW)['items']))
 def test_new_stage_has_a_new_stable_deadline(self):
  c=card(owner='ted',next_action_due=r.iso(NOW-50),action_started_at=r.iso(NOW-10000),reconciliation_stage='pr')
  s=snapshot([c]);s['workflows']={'c-one':{'pr_url':'https://github.com/example/test/pull/1'}};s['prs']={'https://github.com/example/test/pull/1':{'state':'MERGED','merged_at':r.iso(NOW-10)}}
  row=r.plan(s,now=NOW)['items'][0];self.assertEqual(row['action_started_at'],r.iso(NOW-10));self.assertGreater(r.stamp(row['next_action_due']),NOW)
 def test_backoff_is_bounded_and_deterministic(self):
  self.assertEqual(r.backoff('c-one',1),r.backoff('c-one',1));self.assertGreaterEqual(r.backoff('c-one',2),120);self.assertLessEqual(r.backoff('c-one',10),3600)

if __name__=='__main__':unittest.main()
