"""Run PR 36's unchanged scope and lifecycle tests with an admitted runner fixture."""
import importlib.util
import os
from pathlib import Path
import sys
import unittest

root=Path(os.environ['TED_RUNTIME_SOURCE'])
os.environ['TED_STEWARD_RUNTIME']=str(root)
source=Path(os.environ.get('TED_PR36_TEST_SOURCE',Path(__file__).parent/'inbox-steward/steward_test.py'))
spec=importlib.util.spec_from_file_location('pr36_tests',source)
review=importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)
original_card=review.card


def admitted_card(cid='worker',text=None,**kw):
    # PR 44 intentionally narrows the old default completed-report fixture.
    # Explicit text and protection cases retain PR 36's original inputs.
    if text is None:
        text='[ted-runner-failure:v1:crash] worker run finished with a crash; ted owns recovery from the job files. no automatic retry remains.'
        row=original_card(cid,text=text,**kw)
        row['messages'][0]['runner_failure']=True
    else:
        row=original_card(cid,text=text,**kw)
    row.setdefault('decision_kind',None)
    return row


review.card=admitted_card
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls)
                         for cls in (review.ScopeAndAvailability,review.StructuralBoundary))
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
