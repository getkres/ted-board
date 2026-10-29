#!/usr/bin/env python3
"""Strictly adapt worker spawns while preserving current private runtime behavior.

This module returns candidate text. It never installs or reads live state.
"""
import ast
import re


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError('unrecognized runtime surface')
    return source.replace(before, after, 1)


def adapt(source, *, managed):
    if 'from scripts import shared_admission' in source:
        raise ValueError('shared admission already present')
    source = replace_once(source, 'import uuid\n', 'import uuid\nfrom scripts import shared_admission\n')
    source = replace_once(source, 'class Store:\n', PUBLICATION_CARD_HELPERS + 'class Store:\n')
    worker = 'reconciler_worker.py' if managed else 'session_worker.py'
    # Only worker launch methods are adapted. Other subprocess calls stay intact.
    needle = "      p=subprocess.Popen([PYTHON,str(ROOT/'" + worker + "'),str(prefix)]"
    count = source.count(needle)
    if count != (1 if managed else (2 if ' def _tick_lanes(' in source and ' def tick(' in source else 1)):
        raise ValueError('unrecognized worker spawn count')
    source = source.replace("    prefix=Path(s['cwd'])/s['turn'];atomic(",
                            "    prefix=Path(s['cwd'])/s['turn']\n    atomic(")
    lines = source.splitlines(keepends=True)
    indices = [i for i, line in enumerate(lines) if line.startswith(needle)]
    for index in reversed(indices):
        # Locate this exact spawn's input preparation and exception boundary.
        start = next((i for i in range(index - 1, -1, -1) if lines[i].startswith("    prefix=Path(s['cwd'])/s['turn']")), None)
        boundary = next((i for i in range(index + 1, len(lines)) if lines[i] == '    except OSError:\n'), None)
        if start is None or boundary is None or index - start > 25 or boundary - index > 20:
            raise ValueError('unrecognized launch boundary')
        preparation = []
        for i in range(start, index):
            if lines[i].startswith('    atomic(str(prefix)') or lines[i].startswith("    Path(str(prefix)+'.result.json').unlink"):
                preparation.append(i)
        if not preparation or not any('atomic(' in lines[i] for i in preparation):
            raise ValueError('unrecognized input preparation')
        lines[index] = lines[index].replace('p=subprocess.Popen(', 'p=shared_admission.Gate().spawn(', 1).replace('],cwd=', "],lane='board',cwd=", 1)
        # Admission refusals do not consume managed launch or lifetime budgets.
        counters = []
        if managed:
            for i in range(start, index):
                if lines[i].startswith('    launches+=1;retry_launches+=retrying') or lines[i].startswith("    if automatic:s['automatic_dispatch_count']"):
                    counters.append(i)
            if len(counters) != 2:
                raise ValueError('unrecognized managed launch counters')
        successful = ['     s.pop(\'admission_deferred\',None)\n'] + [' ' + lines[i] for i in counters]
        lines[index + 1:index + 1] = successful
        boundary += len(successful)
        episode = [
            '    except shared_admission.Deferred as exc:\n',
            "     a=data['approvals'][turn['approval_id']] if turn['kind']=='review' else None\n",
            '     waiting=shared_admission.defer_turn(s,turn,exc,approval=a)\n',
            "     print('admission deferred: '+exc.diagnostic,file=sys.stderr)\n",
            "     if time.time()-waiting['since']>=15*60 and not waiting.get('alerted'):\n",
        ]
        if managed:
            episode += [
                "      self._queue_publication(data,s,'blocked','admission delayed: '+exc.diagnostic.lower(),'admission',section='up_next')\n",
                "      waiting['alerted']=True\n",
            ]
        else:
            episode += ["      guards=admission_status_kwargs(s['card_id'])\n", "      waiting['alerted']=guards is not None and bool(publish_live(s['card_id'],'blocked','admission delayed: '+exc.diagnostic.lower(),**guards))\n", "      if waiting['alerted']:s['recovery_section']='up_next'\n"]
        episode += ['     if exc.capacity:break\n', '     continue\n']
        lines[boundary:boundary] = episode
        # Keep original launch failure semantics, and clear an obsolete episode.
        lines[boundary + len(episode) + 1:boundary + len(episode) + 1] = ["     s.pop('admission_deferred',None)\n"]
        # Move filesystem input preparation inside the original launch try.
        trystart = next(i for i in range(start, index) if lines[i] == '    try:\n')
        move = [' ' + lines[i] for i in preparation]
        lines[trystart + 1:trystart + 1] = move
        for i in sorted(preparation + counters, reverse=True):
            del lines[i]
    result = ''.join(lines)
    if not managed:
        result = re.sub(r'^   overloaded=os\.getloadavg\(\)\[0\]>[^\n]+\n', '', result, flags=re.M)
        result = result.replace(' or overloaded:break', ':break')
    if managed:
        result = adapt_completion(result)
    ast.parse(result)
    return result


PUBLICATION_CARD_HELPERS = """def publication_card(card_id):
 # Read once, validate the envelope before inspecting this exact current card.
 try:
  from board_card_snapshot import fetch_cards
  from reconciler import protected_decision
  response=call(page=True)
  if not isinstance(response,dict) or response.get('ok') is False or any(response.get(key) for key in ('truncated','has_more','next_cursor')):return None
  cards=fetch_cards(call=lambda **filters:response)
  if len({c['id'] for c in cards})!=len(cards) or any(not re.fullmatch(r'[A-Za-z0-9._-]{1,64}',c['id']) for c in cards):return None
  card=next((c for c in cards if c['id']==card_id),None)
  if (card is None or 'decision_kind' not in card or card['decision_kind'] not in (None,'other')
      or card.get('inbox_decision') not in (None,'other') or card.get('classification_uncertain')
      or card.get('options') or card.get('steps')
      or any(card.get(key) is not None and not isinstance(card[key],dict) for key in ('approval','veto'))
      or protected_decision({},card)):return None
  return card
 except (OSError,RuntimeError,ValueError,TypeError,KeyError,BoardGone,BoardConflict):return None


def admission_status_kwargs(card_id):
 card=publication_card(card_id)
 if card is None or card['section'] not in ('up_next','ted_doing'):return None
 from inbox_policy import stamp as publication_stamp
 if not isinstance(card.get('updated_at'),str) or not publication_stamp(card['updated_at']):return None
 # The backend permits a guarded Ted doing handoff. Up next only receives
 # a live-status update, with no section transition or expected_section.
 result={'expected_updated_at':card['updated_at']}
 if card['section']=='ted_doing':result['section']='up_next'
 return result


"""


COMPLETION_HELPERS = """ def _completion_eligible(self,data,s,item,fallback=True):
  if (item.get('kind')!='complete' or item.get('state')!='blocked' or item.get('line')!='ted review'
      or item.get('kwargs')!={'section':'up_next'} or item.get('status')!='done'
      or s.get('status')!='done' or s.get('card_id')!=item.get('card_id')
      or not isinstance(s.get('queue'),list) or s['queue'] or s.get('pid') is not None):return False
  if not fallback:return True
  if any(s.get(key) for key in ('stop_requested','kill_requested_at','reviewing','review_context','review_session_id',
      'review_claude_lane','review_claude_config_dir','active_turn','side_effecting','veto_outcome',
      'failure_publish_pending','publication_pending','recovery_required')) or s.get('active_veto_revision') is not None:return False
  approvals=data.get('approvals')
  if not isinstance(approvals,dict):return False
  if any(not isinstance(a,dict) or (a.get('card_id')==s['card_id'] and
      (a.get('status') not in ('done','failed','rejected','superseded') or a.get('sync_status'))) for a in approvals.values()):return False
  return all(s.get(key)==item.get(key) for key in ('turn','lease_token','status'))
 def _completion_target_exists(self,cid,s):
  # A successful result may arrive before its worker wrapper exits. Never
  # consume this fallback while its old process or any group member remains.
  lease=s.get('lease')
  if (not isinstance(lease,dict) or not isinstance(s.get('lease_token'),str) or not s['lease_token']
      or not isinstance(s.get('turn'),str) or not s['turn'] or not isinstance(s.get('identity'),str) or not s['identity']
      or lease.get('token')!=s['lease_token'] or lease.get('turn')!=s['turn'] or lease.get('identity')!=s['identity']):return False
  pid=lease.get('pid')
  if type(pid) is not int or pid<=1:return False
  try:
   card=publication_card(cid)
   if card is None or card.get('section')!='up_next' or card.get('live_state')!='blocked' or card.get('live_status')!='ted review':return False
   observed=subprocess.run(['/bin/ps','-axo','pid=,pgid=,stat='],capture_output=True,text=True,timeout=5)
   if observed.returncode!=0 or not observed.stdout.strip():return False
   for line in observed.stdout.splitlines():
    fields=line.split()
    if len(fields)!=3 or not fields[0].isdigit() or not fields[1].isdigit() or not re.fullmatch(r'[A-Za-z+<=>-]+',fields[2]):return False
    if pid in (int(fields[0]),int(fields[1])) and not fields[2].startswith('Z'):return False
   return True
  except (OSError,RuntimeError,ValueError,TypeError,KeyError,subprocess.TimeoutExpired):return False
"""


def adapt_completion(source):
    """ACK only a safely completed exact target, without moving a remote card."""
    start=source.index(' def _flush_publications(self):\n')
    end=source.index(' def _publish_failure(',start)
    prefix,suffix=source[:start],source[end:]
    source=source[start:end]
    source = replace_once(source, ' def _flush_publications(self):\n', COMPLETION_HELPERS + ' def _flush_publications(self):\n')
    source = replace_once(source,
        "     if valid and item['state']=='running':\n",
        "     completion_fence_valid=all(s.get(key)==item.get(key) for key in ('turn','lease_token'))\n"
        "     if item.get('kind')=='complete':valid=valid and current==item and self._completion_eligible(data,s,item,fallback=False)\n"
        "     completion_snapshot=json.loads(json.dumps(dict(session=s,approvals=data.get('approvals')))) if valid and item.get('kind')=='complete' else None\n"
        "     if valid and item['state']=='running':\n")
    source = replace_once(source,
        "      if current.get('id')==item['id']:data['publications'].pop(cid,None)\n",
        "      if current.get('id')==item['id'] and (item.get('kind')!='complete' or not completion_fence_valid):data['publications'].pop(cid,None)\n")
    source = replace_once(source,
        "    try:confirmed=publish_live(cid,item['state'],item['line'],raise_gone=True,**item['kwargs'])\n",
        "    kwargs=item['kwargs']\n"
        "    if item.get('kind')=='admission':\n"
        "     kwargs=admission_status_kwargs(cid)\n"
        "     if kwargs is None:continue\n"
        "     with self.locked() as data:\n"
        "      s=data['sessions'].get(cid,{})\n"
        "      if data.get('publications',{}).get(cid)!=item or s.get('stop_requested') or not all(s.get(key)==item.get(key) for key in ('turn','lease_token','status')):continue\n"
        "    try:confirmed=publish_live(cid,item['state'],item['line'],raise_gone=True,**kwargs)\n")
    source = replace_once(source,
        "    if not confirmed:continue\n    with self.locked() as data:\n",
        "    if not confirmed and (completion_snapshot is None or not self._completion_eligible(completion_snapshot,completion_snapshot['session'],item) or not self._completion_target_exists(cid,completion_snapshot['session'])):continue\n"
        "    with self.locked() as data:\n")
    source = replace_once(source,
        "     if current.get('id')!=item['id']:continue\n     data['publications'].pop(cid,None)\n",
        "     if current.get('id')!=item['id']:continue\n"
        "     if item.get('kind')=='complete' and (completion_snapshot is None or current!=item\n"
        "         or s!=completion_snapshot['session'] or data.get('approvals')!=completion_snapshot['approvals']\n"
        "         or (not confirmed and not self._completion_eligible(data,s,item))):continue\n"
        "     data['publications'].pop(cid,None)\n")
    source = replace_once(source,
        "     elif item['kind'] in ('start','resume'):s.pop('recovery_section',None)\n",
        "     elif item['kind']=='admission':s['recovery_section']='up_next'\n"
        "     elif item['kind'] in ('start','resume'):s.pop('recovery_section',None)\n")
    source=prefix+source+suffix
    ast.parse(source)
    return source


COMPANY_HELPERS = '''class CompanyAdmissionDeferred(Exception):
    """The model did not start; return this exact task to its ready queue."""


def shared_admission_module():
    # Use the same installed file and default state as every other mini caller.
    # Lazy loading leaves non-model bookkeeping independent of the helper.
    import importlib.util
    name = '_ted_shared_admission'
    if name not in sys.modules:
        path = Path.home() / 'ted-ops/ted-board/scripts/shared_admission.py'
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[name] = module
    return sys.modules[name]


def model_spawn(argv, **kwargs):
    admission = shared_admission_module()
    try:
        return admission.Gate().spawn(argv, lane='launchd', **kwargs)
    except admission.Deferred as exc:
        raise CompanyAdmissionDeferred(exc.diagnostic) from None


def defer_company_task(store, task_id, token, reason):
    with store.connection(True) as db:
        task = store._owned(db, task_id, token, ('running',))
        if task['pid'] is not None:
            raise ValueError('Started model cannot be deferred')
        db.execute('DELETE FROM resources WHERE task_id=?', (task_id,))
        db.execute("UPDATE tasks SET status='ready',owner=NULL,token=NULL,lease_until=NULL,pid=NULL,host=NULL,exit_code=75,error=?,updated=? WHERE id=?",
                   ('admission deferred: ' + reason, time.time(), task_id))
        store._event(db, task_id, 'admission_deferred', reason)
    return dict(store.get(task_id), admission_deferred=True)


'''


def adapt_company(source):
    """Gate the actual model group, not the supervising company coordinator."""
    if 'def model_spawn(' in source:
        raise ValueError('company admission already present')
    source = replace_once(source, 'def stop_group(process):', COMPANY_HELPERS + 'def stop_group(process):')
    source = replace_once(source,
        'def execute(argv, cwd, timeout, stdout, stderr, env=None, on_start=None, heartbeat=None):',
        'def execute(argv, cwd, timeout, stdout, stderr, env=None, on_start=None, heartbeat=None, model_admission=False):')
    source = replace_once(source,
        '            process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,',
        '            launch = model_spawn if model_admission else subprocess.Popen\n'
        '            process = launch(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,')
    source = replace_once(source,
        'def run_task(store, task_id, owner, argv, timeout=120, env=None, validator=None, input_messages=None, stream=False):',
        'def run_task(store, task_id, owner, argv, timeout=120, env=None, validator=None, input_messages=None, stream=False, model_admission=False):')
    source = replace_once(source,
        '                       on_start=lambda pid: store.start(task_id, token, pid),\n                       heartbeat=lambda: store.renew(task_id, token, 30))',
        '                       on_start=lambda pid: store.start(task_id, token, pid),\n                       heartbeat=lambda: store.renew(task_id, token, 30), model_admission=model_admission)')
    source = replace_once(source,
        '    except Exception as exc:\n        return store.fail(task_id, token, \'failed\', 1, str(exc) + \'; evidence: \' + str(folder))',
        '    except CompanyAdmissionDeferred as exc:\n        return defer_company_task(store, task_id, token, str(exc))\n'
        '    except Exception as exc:\n        return store.fail(task_id, token, \'failed\', 1, str(exc) + \'; evidence: \' + str(folder))')
    source = replace_once(source,
        "                      validate_opus, [m['id'] for m in incoming], stream=active)",
        "                      validate_opus, [m['id'] for m in incoming], stream=active, model_admission=True)")
    source = replace_once(source,
        "        print(json.dumps(result, indent=2))\n        if isinstance(result, dict)",
        "        print(json.dumps(result, indent=2))\n        if isinstance(result, dict) and result.get('admission_deferred') is True:\n            return 75\n        if isinstance(result, dict)")
    ast.parse(source)
    return source
