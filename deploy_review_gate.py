#!/usr/bin/env python3
"""Plan a local review-gate rollout. Ted runs --apply after reviewing the PR.

Private worker sources, integration patches, business registry data, and business records are not published.
The patch manifest pins their hashes, and the backup supports local rollback.
This tool never deploys an Edge Function, changes a database, or adds a schedule.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import review_gate as gate

ROOT = Path(__file__).resolve().parent
BLOCK_START = '<!-- hard-review-gate:start -->'
BLOCK_END = '<!-- hard-review-gate:end -->'
POD_INSTRUCTIONS = '''
## Mandatory review before delivery

Run `canon_check` and the full review step for every post, ad, mockup, brief,
email, report, copy piece, spend proposal, and SQL approval artifact. Maker
self-critique does not count. Every required reviewer is a fresh Claude run
with a session ID different from the maker and every other reviewer.
The business registry and rollout patches stay in a private local bundle.

Create a job directory and save the exact deliverables there. Run:

```sh
python3 ~/ted-ops/ted-board/review.py --job-dir JOB --business BUSINESS --from-session REPORT.md OTHER_ITEMS
```

The --from-session path requires a board worker job. A standalone or scheduled
pod runner must instead use --maker-agent AGENT --maker-model ACTUAL_MODEL
--maker-session-id ACTUAL_SESSION after the maker finishes, using the native
execution result or verified run metadata. Missing identity blocks delivery;
never invent it. No new scheduled routine is registered by these instructions.
Use the business ID in this config's review_gate.business field. Add --design
for visual work. For a mockup batch, pass --upload-manifest with project, batch,
and images containing path, title, and integer sort. review.py appends the
generated Who made and checked this card. Upload the entire reviewed manifest.

The config maps canon-checker, creative-director, audience-panel, compliance,
and, where required, whimsy to independent runs. They read this business's
CANON.md, DECISIONS.md, shared hard rules, and applicable design rules.
Audience-panel reviews comprehension and credibility, including internal
reports. It never invents predicted rates. Whimsy must score at least 9/10
for design, as required by DESIGN-JOB-RULES.md. Other work records the score
and applicability without a numeric pass threshold.

Fix or kill blocks delivery. Revise locally, record what changed, and run fresh
reviews on the final bytes. If the rerun fails, stop locally. Never weaken a
policy, self-grade, reuse sessions, forward failed content, or move it to
needs_you. Any file or canon change invalidates the pass. Keep the existing
panel rounds and ledger checks in addition to this gate.

For the pod pulse, copy the exact status.json into JOB/pod-status.json before
review. After a pass, add review_job_dir to the live status.json, pointing at
JOB. The publisher verifies every other status field against the reviewed
snapshot. Include any report, ledger excerpt, or needs draft being forwarded
among the job items. No unreviewed needs.jsonl item may be forwarded to HQ.

This review grants no publishing, send, spend, database, scheduling, or product
authority. Preserve every existing approval and read-only restriction.
Each full pass consumes four sequential native Claude account runs, or five
where whimsy applies. A failed reviewer stops the chain. The timeout ceiling is 40 or 50 minutes. Fixed worker failures are
kept local without model review. The pod pulse publishes reviewed rows only. If none pass, publication is
held and the old remote snapshot remains. Stage status reviews before rollout.
Native authentication does not prove paid extra usage is disabled; Ted must
confirm account billing controls and the proposed strict quorum before rollout. No new schedule or send is authorized.
'''


def add_block(text):
    block = BLOCK_START + '\n' + POD_INSTRUCTIONS.strip() + '\n' + BLOCK_END
    if BLOCK_START in text:
        before, remainder = text.split(BLOCK_START, 1)
        _, after = remainder.split(BLOCK_END, 1)
        return before + block + after
    return text.rstrip() + '\n\n' + block + '\n'


def settings(business,whimsy=False):
    roles = list(gate.BASE_REVIEWERS)
    if whimsy: roles.append('whimsy')
    return {'business': business, 'canon_check': True, 'review': True,
            'required_reviewers': roles, 'model': 'claude-opus-5-5', 'effort':'high',
            'command': 'python3 ~/ted-ops/ted-board/review.py',
            'record': 'review.json', 'whimsy_minimum_design': 9 if whimsy else None}


def pod_changes(biz_root, company_root,registry=None):
    changes = {}
    registry=gate.validate_registry(registry) if registry is not None else gate.load_registry(biz_root)
    for business, entry in registry['businesses'].items():
        relative=entry['path']
        pod = Path(biz_root) / relative / 'pod'; config_path = pod / 'config.json'
        if config_path.exists(): config = gate.load_json(config_path)
        elif entry.get('scaffold') is True:
            config = {'id': business, 'name': entry.get('name',business.title()), 'status': 'draft',
                      'status_note':'Unscheduled, read-only scaffold.','kind':'needs Ted','mrr_usd':None,
                      'business':'needs Ted','platforms':[],
                      'kpi':'needs Ted',
                      'authority': 'Read-only and drafts only. No sends, spending, or scheduled routines.',
                      'approval': 'Existing approval rules apply. No new execution authority.',
                      'slack':'No outgoing messages.','cadence': {}, 'pool': [],
                      'fatigue_trigger':'needs Ted','creative':{'cycle_days':None,'cap_per_cycle':0,'compliance':'needs Ted','competitors':[],'pipeline':'needs Ted'},
                      'report_to':'needs Ted','extra_rules':['Business facts and platform scope need Ted. No new execution authority.'],
                      'files':{'knowledge':str(pod/'KNOWLEDGE.md'),'playbook':str(pod/'LEAD.md'),
                               'ledger_dir':str(pod/'ledger'),'status_file':str(pod/'status.json'),'needs_file':str(pod/'needs.jsonl')}}
        else: raise gate.blocked()
        config['review_gate'] = settings(business,entry['whimsy'])
        changes[config_path] = json.dumps(config, indent=2, ensure_ascii=True) + '\n'
        if entry.get('scaffold') is True:
            scaffold={
                'KNOWLEDGE.md':'# Desk knowledge\n\nRead ../CANON.md, ../DECISIONS.md, and existing owner instructions. No new execution authority.\n',
                'PANEL.md':'# Desk audience\n\nDraft operator check only. Customer personas, audience evidence, and business rules need Ted. Never present simulated reactions as research.\n',
                'CANON.md':'# Canon pointer\n\nRead ../CANON.md and its current cited sources.\n',
                'needs.jsonl':'',
                'status.json':json.dumps({'name':entry.get('name',business.title()),'health':'amber','health_note':'Draft scaffold. Business state needs Ted.','shipped':[],'testing':[]},indent=2)+'\n',
                'ledger/README.md':'# Desk ledger\n\nStore dated, reviewed output here. This scaffold registers no routine.\n',
            }
            for name,text in scaffold.items():
                changes[pod/name]=(pod/name).read_text() if (pod/name).exists() else text
        lead = pod / 'LEAD.md'
        changes[lead] = add_block(lead.read_text() if lead.exists() else '# Desk\n\nUnscheduled, read-only scaffold.\n')
    # Rendering a pod later must preserve the same mandatory review step.
    template = Path(company_root) / 'pods/_template'
    for name in ('LEAD.template.md', 'PANEL.template.md'):
        p = template / name
        if p.exists(): changes[p] = add_block(p.read_text())
    example = template / 'config.example.json'
    if example.exists():
        config = gate.load_json(example); config['review_gate'] = settings('ted')
        config['review_gate']['business'] = 'REPLACE_WITH_REGISTERED_BUSINESS_ID'
        changes[example] = json.dumps(config, indent=2, ensure_ascii=True) + '\n'
    return changes


def worker_changes(board_root,bundle):
    bundle=Path(bundle)
    manifest = gate.load_json(bundle / 'worker-manifest.json')
    changes = {}
    for name, hashes in manifest['files'].items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:raise gate.blocked()
        source = Path(board_root) / name
        current = gate.digest(source)
        if current not in (hashes['before'], hashes['after']): raise gate.blocked()
    # Apply only in a throwaway staging directory, then return exact new bytes.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp)
        for name, hashes in manifest['files'].items():
            source = Path(board_root) / name
            if gate.digest(source) == hashes['after']:
                changes[source] = source.read_bytes()
            else:
                (staged / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, staged / name)
        # Files already applied are omitted from their patch sections.
        patch_text = (bundle / 'workers.patch').read_text()
        sections = patch_text.split('diff --git ')[1:]
        pending = ''.join('diff --git ' + section for section in sections
                          if (staged / section.splitlines()[0].split()[0][2:]).exists())
        if pending:
            result = subprocess.run(['git', 'apply', '-'], input=pending,
                                    text=True, cwd=staged, capture_output=True)
            if result.returncode: raise gate.blocked()
        for name, hashes in manifest['files'].items():
            if (staged / name).exists(): changes[Path(board_root) / name] = (staged / name).read_bytes()
            if hashlib.sha256(changes[Path(board_root) / name]).hexdigest() != hashes['after']: raise gate.blocked()
    return changes


def apply_changes(changes, backup):
    backup = Path(backup)
    if backup.exists(): raise gate.blocked()
    backup.mkdir(parents=True, mode=0o700)
    index = []
    for number, (target, content) in enumerate(changes.items()):
        saved = backup / str(number)
        existed = target.exists()
        if existed: shutil.copy2(target, saved)
        index.append({'target': str(target), 'saved': str(saved), 'existed': existed})
    (backup / 'rollback.json').write_text(json.dumps(index, indent=2))
    try:
        for target, content in changes.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            mode = target.stat().st_mode & 0o777 if target.exists() else 0o600
            temporary = target.with_name(target.name + '.review-tmp')
            temporary.write_bytes(content if isinstance(content, bytes) else content.encode())
            temporary.chmod(mode); temporary.replace(target)
    except BaseException:
        rollback(backup); raise


def rollback(backup):
    index = json.loads((Path(backup) / 'rollback.json').read_text())
    for row in reversed(index):
        target = Path(row['target'])
        if row['existed']: shutil.copy2(row['saved'], target)
        elif target.exists(): target.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board-root', type=Path, default=Path.home() / 'ted-ops/ted-board')
    parser.add_argument('--biz-root', type=Path, default=gate.BIZ_ROOT)
    parser.add_argument('--company-root', type=Path, default=Path.home() / 'kres/company')
    parser.add_argument('--bundle',type=Path,help='Private, reviewed rollout bundle')
    parser.add_argument('--apply', action='store_true'); parser.add_argument('--backup', type=Path)
    parser.add_argument('--rollback', type=Path)
    args = parser.parse_args(argv)
    if args.rollback: rollback(args.rollback); print('Local rollout restored from backup.'); return 0
    try:
        if args.bundle is None:raise gate.blocked()
        registry=gate.load_json(args.bundle/'review-registry.json')
        changes = worker_changes(args.board_root,args.bundle)
        changes.update(pod_changes(args.biz_root, args.company_root,registry))
        changes[args.biz_root/'_pods/review-registry.json']=json.dumps(registry,indent=2)+'\n'
        for name in ('review_gate.py', 'review.py'):
            changes[args.board_root / name] = (ROOT / name).read_bytes()
        if args.apply:
            if not args.backup: raise gate.blocked()
            apply_changes(changes, args.backup)
            print('Local rollout applied. No database, service, or schedule was changed.')
        else: print(f"Dry run prepared {len(changes)} file updates across {len(registry['businesses'])} business entries. Nothing applied.")
        return 0
    except (OSError, ValueError, KeyError):
        print('Rollout blocked: source drift or invalid configuration. Nothing approved for deployment.', file=sys.stderr); return 1


if __name__ == '__main__': sys.exit(main())
