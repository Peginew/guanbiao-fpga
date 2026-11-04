"""Small source/receipt helpers for the independent HDMI UI TD candidate."""
from pathlib import Path
import hashlib
import json
import re

P = Path('C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_reader_shared_mapper_20261104/project')
NAME = 'reader_shared'
HERE = Path(__file__).resolve().parent
TD = Path('C:/Anlogic/TD_6.2.1_Engineer_6.2.168.116/bin/td_commands_prompt.exe')
FLOW = TD.parent.parent / 'doc/scripts/DefaultFlow.tcl'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def ref(p):
    p = Path(p).resolve()
    return {'path': str(p), 'sha256': sha(p)}


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))


def write(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def collect_inputs():
    """Snapshot project sources, IP hidden configuration, includes and assets.

    Enumerating the complete user_source tree intentionally overapproximates
    dependencies; inactive defaults are recorded as unresolved references when
    unavailable, rather than silently claiming every readmemh was resolved.
    """
    al = P / f'td_project/{NAME}.al'
    assert al.is_file(), str(al)
    al_text = al.read_text(encoding='utf-8-sig')
    paths = {al.resolve(), (P / 'td_project/base_auto_quality.sdc').resolve()}
    # TD writes literal UsedInP&R attribute values; its AL is not strict XML.
    for value in re.findall(r'<File\s+Path="([^"]+)"', al_text):
        path = (al.parent / value).resolve()
        assert path.is_file(), str(path)
        paths.add(path)
    paths.update(p.resolve() for p in (P / 'user_source').rglob('*') if p.is_file())
    basename = {}
    for p in paths:
        basename.setdefault(p.name.lower(), []).append(p)
    unresolved = set()
    include_edges = []
    seen = set()
    textual = {'.v', '.sv', '.vh', '.svh', '.vhd', '.tcl', '.sdc', '.adc', '.xml', '.txt'}
    pending = sorted(paths, reverse=True)
    asset_ext = r'(?:mem|hex|dat|dath|mif|coe|v|sv|vh|svh|sdc|adc|tcl|xml)'
    while pending:
        p = pending.pop()
        if p in seen:
            continue
        seen.add(p)
        if p.suffix.lower() not in textual or '.enc.' in p.name:
            continue
        text = p.read_text(encoding='utf-8-sig', errors='replace')
        includes = re.findall(r'`include\s+"([^"\n]+)"', text)
        literals = re.findall(r'"([^"\n]+\.' + asset_ext + r')"', text, re.I)
        for value in sorted(set(includes + literals)):
            if any(c in value for c in ['$','{','}']):
                unresolved.add((str(p), value, 'dynamic'))
                continue
            candidate = Path(value)
            options = [candidate] if candidate.is_absolute() else [p.parent / candidate, al.parent / candidate, P / candidate]
            matches = [q.resolve() for q in options if q.is_file()]
            if not matches:
                matches = basename.get(candidate.name.lower(), [])
            matches = sorted(set(matches))
            if not matches:
                unresolved.add((str(p), value, 'unresolved_literal_or_inactive_default'))
                continue
            # Hash every ambiguous basename candidate rather than guessing.
            for q in matches:
                include_edges.append({'from': str(p), 'literal': value, 'to': str(q)})
                if q not in paths:
                    paths.add(q)
                    pending.append(q)
                    basename.setdefault(q.name.lower(), []).append(q)
    return {'project': str(P), 'name': NAME, 'inputs': [ref(p) for p in sorted(paths)],
            'reference_edges': sorted(include_edges, key=lambda v:(v['from'],v['literal'],v['to'])),
            'unresolved_references': [{'from': p, 'literal': v, 'reason': why} for p,v,why in sorted(unresolved)],
            'tools': [ref(p) for p in [FLOW, HERE / 'run_td.py', HERE / 'source_helpers.py', HERE / 'mapping_helpers.py', HERE / 'run_pipeline.py', HERE / 'free_ui_place_flow.py', HERE / 'progress_mapping_hooks.py']],
            'state': 'INPUT_SNAPSHOT_ROOT_FREEZE_REVIEW_REQUIRED', 'native_run': False, 'device': False}


def validate_manifest(path):
    frozen = read(path)
    assert frozen['project'] == str(P) and frozen['name'] == NAME
    now = collect_inputs()
    for key in ['inputs', 'tools', 'reference_edges', 'unresolved_references']:
        assert now[key] == frozen[key], 'Source dependency snapshot changed: ' + key
    return frozen


def verify_ref(r):
    assert sha(r['path']) == r['sha256'], r['path']
    return Path(r['path'])


def resources(text):
    values = {}
    for key, token in {'Slice':'slice','FF':'reg','ERAM':'eram','DSP':'dsp','PLL':'pll','MCU':'mcu'}.items():
        m = re.search(r'^#' + token + r'(\*)?[ \t]+(\d+)(?:[ \t]+out of\b|[ \t]*$)', text, re.M)
        if m:
            values[key] = int(m[2])
            if key == 'Slice':
                values['Slice_is_SYN_estimate'] = bool(m[1])
    return values


def final_timing(text):
    m = re.search(r'SWNS:\s*([-\d.]+)ns, STNS:\s*([-\d.]+)ns\.\s*HWNS:\s*([-\d.]+)ns, HTNS:\s*([-\d.]+)ns', text)
    return dict(zip(['SWNS','STNS','HWNS','HTNS'], map(float, m.groups()))) if m else {}
