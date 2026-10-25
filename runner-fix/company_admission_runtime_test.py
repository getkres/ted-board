#!/usr/bin/env python3
"""Test company admission against a disposable coordinator, never the live ledger."""
import argparse
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

SOURCE = None


class CompanyAdmissionTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('candidate_company',SOURCE)
        self.api=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.api)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.store=self.api.Store(self.root/'state/company.sqlite3')
        self.task=dict(id='T1',title='Synthetic',prompt='Synthetic',model='codex',cwd=str(self.root),resources=['fixture:shared'],checks=[])
        self.store.create(self.task)
        from scripts import shared_admission
        self.admission=shared_admission
        self.gate=shared_admission.Gate(self.root/'budget',sample=lambda:dict(
            cores=18,load=0,available_bytes=1024**3,total_bytes=64*1024**3))
        self.marker=self.root/'ran'

    def run_task(self,code,timeout=5,**kwargs):
        with mock.patch.object(self.api,'shared_admission_module',return_value=self.admission),mock.patch.object(self.admission,'Gate',return_value=self.gate):
            return self.api.run_task(self.store,'T1','fixture',[sys.executable,'-c',code],timeout,**kwargs)

    def test_refused_model_is_ready_and_releases_only_its_unstarted_claim(self):
        before=self.store.get('T1')['spec']
        result=self.run_task('from pathlib import Path; Path("ran").touch()',model_admission=True)
        self.assertEqual((result['status'],result['exit_code']),('ready',75))
        self.assertTrue(result['admission_deferred'])
        self.assertEqual(result['spec'],before)
        self.assertIsNone(result['owner']);self.assertIsNone(result['token']);self.assertIsNone(result['pid'])
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.store.inbox('ted'),[])
        # The exact task remains claimable; no duplicate task or automatic retry.
        self.assertEqual(self.store.claim('T1','next',30)['status'],'claimed')

    def test_admitted_model_reservation_is_actual_model_pid_and_keeps_arguments(self):
        self.gate.sample=lambda:dict(cores=18,load=0,available_bytes=32*1024**3,total_bytes=64*1024**3)
        literal='literal $(no-substitution)'
        code='from pathlib import Path; import json,os,sys; Path("ran").write_text(str(os.getpid())); Path("literal").write_text(sys.argv[1]); print(json.dumps({"result":"ok"}))'
        with mock.patch.object(self.api,'shared_admission_module',return_value=self.admission),mock.patch.object(self.admission,'Gate',return_value=self.gate):
            result=self.api.run_task(self.store,'T1','fixture',[sys.executable,'-c',code,literal],5,model_admission=True)
        self.assertEqual(result['status'],'verifying')
        leases=json.loads((self.root/'budget/leases.json').read_text())['leases']
        self.assertEqual(len(leases),1)
        self.assertEqual(leases[0]['pgid'],int(self.marker.read_text()))
        self.assertEqual(result['pid'],leases[0]['pgid'])
        self.assertEqual((self.root/'literal').read_text(),literal)

    def test_admitted_timeout_keeps_existing_group_cleanup_and_status(self):
        self.gate.sample=lambda:dict(cores=18,load=0,available_bytes=32*1024**3,total_bytes=64*1024**3)
        code='import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",\'import time; from pathlib import Path; time.sleep(.8); Path("escaped").touch()\']);time.sleep(10)'
        result=self.run_task(code,timeout=.15,model_admission=True)
        self.assertEqual((result['status'],result['exit_code']),('timed_out',124))
        time.sleep(.9)
        self.assertFalse((self.root/'escaped').exists())

    def test_started_or_stale_task_cannot_release_a_claim_through_deferral(self):
        claim=self.store.claim('T1','fixture',30)
        self.store.start('T1',claim['token'],pid=12345)
        with self.assertRaises(ValueError):self.api.defer_company_task(self.store,'T1',claim['token'],'LoadCapacity')
        with self.assertRaises(ValueError):self.api.defer_company_task(self.store,'T1','stale','LoadCapacity')
        self.assertEqual(self.store.get('T1')['pid'],12345)

    def test_cli_reports_temporary_deferral_as_75(self):
        with mock.patch.object(self.api.sys,'argv',['company.py','--db',str(self.store.path),'run-opus','T1']),mock.patch.object(self.api,'run_opus',return_value=dict(status='ready',admission_deferred=True,exit_code=75)),mock.patch('sys.stdout',new=io.StringIO()):
            self.assertEqual(self.api.main(),75)

    def test_non_model_local_checks_remain_outside_model_budget(self):
        result=self.run_task('print("{}")')
        self.assertEqual(result['status'],'verifying')
        self.assertFalse((self.root/'budget').exists())


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--company-source',required=True,type=Path)
    parser.add_argument('--helper-root',required=True,type=Path)
    args,remaining=parser.parse_known_args()
    SOURCE=args.company_source.resolve();sys.path.insert(0,str(args.helper_root.resolve()))
    unittest.main(argv=[sys.argv[0],*remaining])
