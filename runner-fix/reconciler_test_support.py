"""Reconstruct reviewed new-module patches for offline public tests."""
from pathlib import Path
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
TEMP=tempfile.TemporaryDirectory(prefix='ted-reconciler-offline-')
SOURCE=Path(TEMP.name)
for name in ('reconciler-core.patch','reconciler-runtime.patch','reconciler-admission.patch','reconciler-inbox-policy.patch'):
 subprocess.run(['patch','--batch','--fuzz=0','-s','-p0','-i',str(HERE/name)],cwd=SOURCE,check=True,capture_output=True)
sys.path.insert(0,str(SOURCE))
