"""Fail-closed content review contracts shared by local worker entry points.

This is an operational gate, not a security boundary against processes with
arbitrary access to the worker's filesystem or production credentials.
"""
import hashlib
import io
import json
import re
from pathlib import Path
import textwrap

BIZ_ROOT = Path.home() / 'biz'
BASE_REVIEWERS = ('canon-checker', 'creative-director', 'audience-panel', 'compliance')
ATTRIBUTION_TITLE = 'Who made and checked this'
ATTRIBUTION_PATH = 'review-attribution.png'
APPROVAL_PATHS = ('draft-email.json', 'spend.json', 'apply.sql', 'backup.sql', 'rollback.sql')
AUTO_PATHS = ('BRIEF.md', 'review-brief.json', 'maker-config.json', 'REPORT.md', 'final-answer.txt', 'card-request.json', 'card-sync.json', 'veto-request.json', *APPROVAL_PATHS)


class ReviewBlocked(ValueError):
    """A safe, fixed diagnostic. Do not add artifact or model output to it."""


def blocked():
    return ReviewBlocked('content review missing, failed, or stale; run review.py')


def load_registry(biz_root=None):
    root=Path(biz_root) if biz_root is not None else BIZ_ROOT
    return validate_registry(load_json(root/'_pods/review-registry.json'))


def validate_registry(data):
    entries=data.get('businesses')
    if data.get('schema_version')!=1 or not isinstance(entries,dict) or not entries:raise blocked()
    for key,entry in entries.items():
        if not isinstance(key,str) or not key or not isinstance(entry,dict):raise blocked()
        relative=Path(entry.get('path',''))
        if not relative.parts or relative.is_absolute() or '..' in relative.parts:raise blocked()
        if type(entry.get('whimsy')) is not bool:raise blocked()
        for field in ('aliases','projects'):
            if not isinstance(entry.get(field),list) or any(not isinstance(x,str) or not x.strip() for x in entry[field]):raise blocked()
    for name in ('shared_rules','design_rules','whimsy_rules'):
        if not isinstance(data.get(name),list) or not data[name] or any(not isinstance(x,str) or not x for x in data[name]):raise blocked()
    return data


def business_id(value,biz_root=None):
    value=str(value).strip().lower()
    entries=load_registry(biz_root)['businesses']
    matches=[key for key,entry in entries.items() if value in {key.lower(),*(x.lower() for x in entry['aliases'])}]
    if len(matches)!=1:raise blocked()
    return matches[0]


def load_json(path):
    try:
        path = Path(path)
        if path.is_symlink() or path.stat().st_size > 2_000_000: raise blocked()
        value = json.loads(path.read_text())
        if not isinstance(value, dict): raise blocked()
        return value
    except (OSError, ValueError, TypeError): raise blocked() from None


def digest(path):
    try:
        with Path(path).open('rb') as source:
            result = hashlib.sha256()
            for chunk in iter(lambda: source.read(1024 * 1024), b''): result.update(chunk)
        return result.hexdigest()
    except OSError: raise blocked() from None


def local_file(job_dir, name):
    try:
        base = Path(job_dir).resolve()
        relative = Path(name)
        if relative.is_absolute() or not relative.parts or '..' in relative.parts: raise blocked()
        target = base / relative
        if any((base / Path(*relative.parts[:i])).is_symlink() for i in range(1, len(relative.parts) + 1)):
            raise blocked()
        if not target.is_file() or not target.resolve().is_relative_to(base): raise blocked()
        return target
    except (OSError, TypeError, ValueError): raise blocked() from None


def policy(business, biz_root=None, design=False):
    business = business_id(business,biz_root)
    root = Path(biz_root) if biz_root is not None else BIZ_ROOT
    registry=load_registry(root);entry=registry['businesses'][business]
    directory = root / entry['path']
    config_path = directory / 'pod/config.json'
    config = load_json(config_path)
    settings = config.get('review_gate', {})
    roles = settings.get('required_reviewers')
    minimum = set(BASE_REVIEWERS)
    if entry['whimsy']: minimum.add('whimsy')
    if (not isinstance(roles, list) or not all(isinstance(x, str) for x in roles)
            or len(roles) != len(set(roles)) or set(roles) != minimum
            or settings.get('canon_check') is not True or settings.get('review') is not True
            or not isinstance(settings.get('model'), str) or not settings['model'].strip()):
        raise blocked()
    # Compliance and the panel are conservative mandatory defaults, including
    # internal reports and placeholder canons. Classification cannot weaken them.
    sources = [root/'_pods/review-registry.json',directory/'CANON.md',directory/'DECISIONS.md',config_path]
    source_names=list(registry['shared_rules'])
    if design:
        source_names+=registry['design_rules']
        if entry['whimsy']:source_names+=registry['whimsy_rules']
    sources += [Path(name).expanduser() if Path(name).expanduser().is_absolute() else root/name for name in source_names]
    if any(not p.is_file() for p in sources): raise blocked()
    return {'business': business, 'reviewers': roles, 'model': settings['model'], 'effort': settings.get('effort','high'),
            'sources': sources}


def context_items(config):
    return [{'path': str(p.resolve()), 'sha256': digest(p)} for p in config['sources']]


def item_records(job_dir, paths):
    return [{'path': str(Path(name)), 'sha256': digest(local_file(job_dir, name))}
            for name in sorted(set(paths))]


def attribution_bytes(record):
    from PIL import Image, ImageDraw, ImageFont
    maker = record['maker']
    lines = [ATTRIBUTION_TITLE, '', 'Maker: ' + maker['agent'] + ' / ' + maker['model'],
             'Session: ' + maker['session_id'], '']
    for reviewer in record['reviewers']:
        lines += [reviewer['agent'] + ' / ' + reviewer['model'] + ': ' + reviewer['verdict'],
                  'Session: ' + reviewer['session_id']]
        if reviewer.get('score') is not None: lines.append('Whimsy: ' + str(reviewer['score']) + '/10')
        lines += ['Finding: ' + str(x) for x in reviewer['findings']] or ['Findings: none.']
        lines += ['Changed: ' + str(x) for x in reviewer['what_changed']] or ['Changes: none.']
        lines.append('')
    lines.append('Items deliberately left unfixed:')
    for entry in record.get('unfixed',[]):
        lines += ['Finding: '+entry['finding'],'Reason: '+entry['reason']]
    if not record.get('unfixed'):lines.append('None declared.')
    wrapped = [piece for line in lines for piece in (textwrap.wrap(line, 90) or [''])]
    try: font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 20)
    except OSError:
        try: font = ImageFont.truetype('DejaVuSans.ttf', 20)
        except OSError: font = ImageFont.load_default()
    canvas = Image.new('RGB', (1100, max(260, 28 * len(wrapped) + 60)), 'white')
    draw = ImageDraw.Draw(canvas)
    for index, line in enumerate(wrapped):
        try: draw.text((30, 30 + index * 28), line, fill='black', font=font)
        except UnicodeEncodeError: draw.text((30, 30 + index * 28), line.encode('ascii', 'backslashreplace').decode(), fill='black', font=font)
    out = io.BytesIO(); canvas.save(out, format='PNG')
    return out.getvalue()


def check_project(business,project,biz_root=None):
    if project is None:return
    entry=load_registry(biz_root)['businesses'][business]
    allowed={business.lower(),*(x.lower() for x in entry['aliases']),*(x.lower() for x in entry['projects'])}
    if str(project).strip().lower() not in allowed:raise blocked()


def session_project(session):
    project = session.get('project') if isinstance(session, dict) else None
    if not isinstance(project, str) or not project.strip(): raise blocked()
    return project


def validate_review(job_dir, required_paths=(), project=None, biz_root=None):
    try:
        job_dir = Path(job_dir)
        record = load_json(job_dir / 'review.json')
        request = load_json(job_dir / 'review-request.json')
        if record.get('schema_version') != 1 or record.get('status') != 'pass': raise blocked()
        business = business_id(request['business'],biz_root)
        if record['business'] != business or record['request_sha256'] != digest(job_dir / 'review-request.json'):
            raise blocked()
        check_project(business, project,biz_root)
        config = policy(business, biz_root, request['design'])
        if record['context'] != context_items(config): raise blocked()
        maker = record['maker']
        if record.get('authentication',{}).get('auth_method')!='claude.ai':raise blocked()
        if maker != request['maker'] or any(not isinstance(maker.get(k), str) or not maker[k].strip()
                                             for k in ('agent', 'model', 'session_id')): raise blocked()
        items = record['items']
        if not items or len({x['path'] for x in items}) != len(items): raise blocked()
        names = {x['path'] for x in items}
        required = set(required_paths) | {name for name in AUTO_PATHS if (job_dir / name).exists()}
        if not required <= names or items != item_records(job_dir, names): raise blocked()
        original_names = {x['path'] for x in request['items']}
        if request['items'] != item_records(job_dir, original_names): raise blocked()
        if names != original_names | ({ATTRIBUTION_PATH} if request.get('upload') else set()): raise blocked()
        reviewers = record['reviewers']
        if len(reviewers) != len(config['reviewers']) or {x['agent'] for x in reviewers} != set(config['reviewers']):
            raise blocked()
        sessions = {maker['session_id']}
        for reviewer in reviewers:
            sid = reviewer['session_id']
            if not isinstance(sid, str) or not sid.strip() or sid in sessions: raise blocked()
            sessions.add(sid)
            if reviewer['verdict'] != 'pass' or not reviewer['model']: raise blocked()
            for name in ('findings', 'what_changed'):
                if not isinstance(reviewer[name], list) or any(not isinstance(x, str) for x in reviewer[name]):
                    raise blocked()
                if any(chr(8212) in value for value in reviewer[name]): raise blocked()
            if set(reviewer['items_reviewed']) != original_names: raise blocked()
            evidence = local_file(job_dir, reviewer['evidence']['path'])
            if digest(evidence) != reviewer['evidence']['sha256']: raise blocked()
            raw = load_json(evidence)
            result = raw.get('structured_output') or json.loads(raw['result'])
            if (raw.get('type') != 'result' or raw.get('is_error') is not False
                    or raw.get('session_id') != sid or reviewer['model'] not in raw.get('modelUsage', {})):
                raise blocked()
            for key in ('agent', 'verdict', 'findings', 'what_changed', 'items_reviewed'):
                if result[key] != reviewer[key]: raise blocked()
            if reviewer['agent'] == 'whimsy':
                score = reviewer.get('score')
                minimum = 9 if request['design'] else 0
                if type(score) not in (int, float) or not minimum <= score <= 10 or score != result.get('score'):
                    raise blocked()
        if request.get('upload'):
            if record.get('unfixed')!=request['upload'].get('unfixed',[]):raise blocked()
            if (not isinstance(record['unfixed'],list) or any(not isinstance(x,dict) or set(x)!={'finding','reason'}
                    or any(not isinstance(x[k],str) or not x[k].strip() or chr(8212) in x[k] for k in x) for x in record['unfixed'])):raise blocked()
            if local_file(job_dir, ATTRIBUTION_PATH).read_bytes() != attribution_bytes(record): raise blocked()
            upload = record['upload']
            if upload['project'] != request['upload']['project'] or upload['batch'] != request['upload']['batch']:
                raise blocked()
            expected = request['upload']['images']
            last_sort = max(row['sort'] for row in expected) + 1
            if upload['images'] != expected + [{'path': ATTRIBUTION_PATH, 'title': ATTRIBUTION_TITLE, 'sort': last_sort}]:
                raise blocked()
        return record
    except (OSError, KeyError, TypeError, ValueError, AttributeError): raise blocked() from None


def validate_upload(job_dir, project, batch, paths=None, biz_root=None):
    record = validate_review(job_dir, project=project, biz_root=biz_root)
    upload = record.get('upload', {})
    if upload.get('project') != project or upload.get('batch') != batch: raise blocked()
    images = upload.get('images', [])
    if not images or images[-1]['title'] != ATTRIBUTION_TITLE: raise blocked()
    if paths and [Path(p).resolve() for p in paths] != [local_file(job_dir, x['path']).resolve() for x in images]:
        raise blocked()
    return images


def validate_card(card_id, jobs_root=None):
    root = Path(jobs_root) if jobs_root is not None else Path(__file__).resolve().parent / 'jobs'
    data = load_json(root / 'sessions.json')
    try: session = data['sessions'][card_id]
    except (KeyError, TypeError): raise blocked() from None
    job = Path(session['cwd']).resolve()
    if not job.is_relative_to(root.resolve()): raise blocked()
    return validate_review(job, required_paths=['REPORT.md'], project=session_project(session))


def validate_payload(job_dir, filename, payload, project=None):
    validate_review(job_dir, required_paths=[filename], project=project)
    if load_json(local_file(job_dir, filename)) != payload: raise blocked()


def validate_pod(pod_dir, project):
    status = load_json(Path(pod_dir) / 'status.json')
    job = status.pop('review_job_dir', None)
    if not isinstance(job, str): raise blocked()
    validate_payload(job, 'pod-status.json', status, project=project)


RUNNER_NOTICES = frozenset((
    'Ted review: the approval artifact is unsafe, unreadable, or over 60 KB. Ted will repair the packet.',
    'Ted review: a worker failed. Ted owns bounded recovery from the job files.',
    'Ted review: a worker failed. Ted owns recovery from the job files. Timeout and missing-result work gets one automatic retry, then holds for Ted.',
    'Ted recovery: the card reached its lifetime automatic dispatch limit.',
    'The approved artifact changed. Execution refused. Reply to prepare a fresh approval.',
    'Ted review: a prepared packet needs operational review. It is not a Sebastian decision.',
    'Job stop queued for the reconciler.',
    'Job stop requested.',
    'Job is already stopped, or process identity changed.',
))
APPROVAL_NOTICE = re.compile(r'Approval needed: (?:Apply database SQL after a fresh safety review|Send the exact drafted email|Execute the exact proposed spend)\. Review the exact content on this card\.')


def runner_notice(text):
    """Fixed runner text carries no model output, so it needs no content review."""
    if not isinstance(text, str): return False
    if text in RUNNER_NOTICES or APPROVAL_NOTICE.fullmatch(text): return True
    try:
        templates = json.loads((Path(__file__).resolve().parent / 'runner_failure_templates.json').read_text())
        failures = list(templates['failures'].values())
        recoveries = [''] + list(templates.get('recovery', {}).values())
        return any(text == failure + recovery for failure in failures for recovery in recoveries)
    except (OSError, ValueError, AttributeError, KeyError, TypeError):
        return False


def validate_reply(card_id, text, jobs_root=None):
    if runner_notice(text): return
    root = Path(jobs_root) if jobs_root is not None else Path(__file__).resolve().parent / 'jobs'
    validate_card(card_id, root)
    try:
        session = load_json(root / 'sessions.json')['sessions'][card_id]
        validate_review(session['cwd'], required_paths=['final-answer.txt', 'REPORT.md'])
        final = local_file(session['cwd'], 'final-answer.txt').read_text().replace(chr(8212), '-')[:2000]
        if text != final: raise blocked()
    except (OSError, KeyError): raise blocked() from None


def validate_mockup_payload(action, payload, proof):
    """The transport also checks provenance and exact encoded image bytes."""
    try:
        job = Path(proof['_review_job_dir'])
        source = Path(proof['_review_source']).resolve()
        project, batch = proof['_review_project'], proof['_review_batch']
        rows = validate_upload(job, project, batch)
        row = next(row for row in rows if local_file(job, row['path']).resolve() == source)
        from mockup_upload import prepare, UPLOAD_LOG
        encoded = prepare(source)
        keys = ('full', 'full_width', 'full_height') if action == 'attach_full' else tuple(encoded)
        if action == 'upload':
            if any(payload.get(key) != value for key, value in
                   {'project': project, 'batch': batch, 'title': row['title'], 'sort': row['sort']}.items()): raise blocked()
        else:
            receipts = [json.loads(line) for line in UPLOAD_LOG.read_text().splitlines() if line.strip()]
            if not any(r.get('mockup_id') == payload.get('mockup_id') and r.get('project') == project
                       and r.get('batch') == batch and r.get('source') == str(source)
                       and r.get('sha256') == digest(source) for r in receipts): raise blocked()
            if payload.get('replace_preview'): keys = tuple(encoded)
        if any(payload.get(key) != encoded[key] for key in keys): raise blocked()
    except (OSError, ValueError, KeyError, TypeError, StopIteration): raise blocked() from None


def card_job(card_id, jobs_root=None):
    root = Path(jobs_root) if jobs_root is not None else Path(__file__).resolve().parent / 'jobs'
    try:
        session=load_json(root/'sessions.json')['sessions'][card_id]
        if not Path(session['cwd']).resolve().is_relative_to(root.resolve()):raise blocked()
        return session
    except (KeyError,TypeError):raise blocked() from None


def validate_card_payload(card_id,filename,payload,jobs_root=None):
    session=card_job(card_id,jobs_root)
    validate_payload(session['cwd'],filename,payload,project=session_project(session))


def validate_approval_payload(approval,jobs_root=None):
    try:
        session=card_job(approval['card_id'],jobs_root)
        validate_review(session['cwd'],project=session_project(session))
        from sessions import artifact
        current=artifact(session['cwd'],approval['kind'])
        summaries={'db':'Apply database SQL after a fresh safety review','email':'Send the exact drafted email','spend':'Execute the exact proposed spend'}
        if (not current or approval['digest']!=current['digest'] or approval['content']!=current['content']
                or approval['summary']!=summaries[approval['kind']]):raise blocked()
    except (KeyError,TypeError,OSError):raise blocked() from None
