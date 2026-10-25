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
            episode += ["      waiting['alerted']=bool(publish_live(s['card_id'],'blocked','admission delayed: '+exc.diagnostic.lower(),section='up_next'))\n"]
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
    ast.parse(result)
    return result
