"""Conditional physical-only fallback: place the same SYN without ten UI LOCs.

Default PLAN performs no TD invocation. --run additionally requires an independent
admission recording root's activation decision. No old placed/routed DB is read,
and no synthesis, route, bitgen, MCU or device action is performed.
"""
if not __debug__:
    raise RuntimeError('Verification assertions must remain enabled')

import argparse
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
PHYSICAL = HERE.parent
sys.path.insert(0, str(PHYSICAL))
from source_helpers import P, NAME, read, write, ref, sha, verify_ref, validate_manifest, resources
from run_td import absolute_project, native, LIMITS, RESERVE

GUIDED_RUNNER = PHYSICAL / 'guided_ui_macros/run_guided_place.py'
spec = importlib.util.spec_from_file_location('frozen_guided_place', GUIDED_RUNNER)
guided = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guided)

MANIFEST = PHYSICAL / 'source_freeze.json'
GATE = HERE / 'free_ui_place_admission.json'
ALIAS = HERE / 'latest_place.json'
RUN_ROOT = Path('C:/Users/Edward/Desktop/FPGA/s3_free_ui_20261103')
MARKER = 'FREE_UI_MACRO_PLACE_COMPLETE'
PRESERVE_ALIASES = [PHYSICAL / 'latest_place.json', PHYSICAL / 'latest_guided_place.json',
                    PHYSICAL / 'latest_guided_route.json', PHYSICAL / 'latest_route.json']


def generated_flow(anchors):
    # Preserve the exact frozen guided placement flow and all ordinary inputs;
    # remove only the additional ten-macro LOC ADC load. PRE/POST reports remain
    # observations and impose no location or clockBound assignment.
    original = guided.generated_flow(anchors)
    removed = '  read_adc ui_macro_anchors.adc\n'
    assert original.count(removed) == 1
    result = original.replace(removed, '', 1)
    result = result.replace('GUIDED_UI_MACRO_ADC_AND_DDR_GROUP_LOADED',
                            'FREE_UI_NO_EXTRA_LOC_DDR_GROUP_LOADED')
    assert 'ui_macro_anchors.adc' not in result
    assert result.count('  place\n') == 1
    return result


def generated_settings(syn):
    cfg = (Path(syn['run']) / 'settings.cfg').read_text(encoding='ascii')
    for old, new in [('set run_type syn', 'set run_type phy'),
                     ('set start_step read_design', 'set start_step opt_place'),
                     ('set end_step opt_gate', 'set end_step opt_place')]:
        assert cfg.count(old) == 1
        cfg = cfg.replace(old, new, 1)
    cfg += '\nset parent ' + Path(syn['run']).as_posix() + '\nset sp 1\nset arr_filter false\nset drHoldFix on\n'
    cfg += 'set phyWildParams {route effort normal route fix_hold on route timing on route post_route_opt off}\n'
    return cfg


def inputs():
    syn, anchors, original_refs = guided.inputs()
    validate_manifest(MANIFEST)
    assert read(PHYSICAL / 'ddr_group_plan.json')['member_count'] == 37
    flow = generated_flow(anchors)
    settings = generated_settings(syn)
    refs = dict(original_refs)
    refs['frozen_guided_runner_sha256'] = refs.pop('runner_sha256')
    refs.update(runner_sha256=sha(__file__),
                generated_flow_sha256=hashlib.sha256(flow.encode('ascii')).hexdigest(),
                generated_settings_sha256=hashlib.sha256(settings.encode('ascii')).hexdigest())
    return syn, anchors, refs


def gate_ready(refs):
    if not GATE.is_file():
        return False
    gate = read(GATE)
    assert gate['passed'] is True and gate['stage'] == 'free_ui_place'
    assert gate['root_authorized_activation'] is True
    assert gate['only_physical_delta_is_omitting_ten_UI_LOCs'] is True
    assert gate['fresh_ASR_and_exactQ_required'] is True
    for key, value in refs.items():
        assert gate[key] == value, 'Admission mismatch: ' + key
    return True


def run_place(syn, anchors, refs, timeout):
    assert gate_ready(refs), 'Independent admission and root activation required'
    assert not ALIAS.exists(), 'One independent attempt only; preserve any prior result'
    preserved = [ref(p) for p in PRESERVE_ALIASES if p.is_file()]
    # Short ASCII CWD avoids the already evidenced long-run relative XML limit.
    run = RUN_ROOT / ('p_' + datetime.datetime.now().strftime('%m%d_%H%M%S_%f'))
    run.mkdir(parents=True)
    absolute_project(run)
    shutil.copyfile(PHYSICAL / 'ddr_group.tcl', run / 'ddr_group.tcl')
    assert not (run / 'ui_macro_anchors.adc').exists()
    (run / 'settings.cfg').write_text(generated_settings(syn), encoding='ascii')
    (run / 'DefaultFlow.tcl').write_text(generated_flow(anchors), encoding='ascii')
    (run / 'execute.tcl').write_text('if {[catch {\nsource DefaultFlow.tcl\n} err]} {puts stderr "FREE_UI_PLACE_FAILED: $err";exit 1}\nputs ' + MARKER + '\nexit 0\n', encoding='ascii')
    controls = [ref(p) for p in run.iterdir() if p.is_file()] + [ref(__file__), ref(GATE)]
    rec = {'stage': 'free_ui_place', 'state': 'RUNNING', 'passed': False, 'device': False,
           'manifest': ref(MANIFEST), 'gate': ref(GATE), 'source_DB': syn['output'],
           'run': str(run), 'controls': controls, 'preserved_aliases': preserved,
           'source_reused_no_synthesis': True, 'source_tools_unchanged': True,
           'only_physical_delta_is_omitting_ten_UI_LOCs': True,
           'macro_constraints_loaded_by_read_adc': False,
           'DDR_semantic_group_member_count': 37, 'DDR_soft_group_preserved': True,
           'DDR_semantic_admission': ref(PHYSICAL / 'ddr_semantic_admission.json'),
           'fresh_ASR_and_exactQ_required': True,
           'no_existing_physical_pins_or_clockBound_reused': True,
           'route_or_bitgen_admitted': False}
    write(run / 'receipt.json', rec)
    write(ALIAS, rec)
    start = time.monotonic()
    code = native(run, timeout)
    log = (run / 'console.log').read_text(errors='replace')
    errors = [line for line in log.splitlines() if re.search(r'\bERROR:|\bFATAL:|FREE_UI_PLACE_FAILED:', line)]
    commands = re.findall(r'start command "([^"\r\n]+)"', log)
    forbidden = {'elaborate', 'optimize_rtl', 'optimize_gate', 'route', 'bitgen', 'fix_hold'}
    native_scope = not any(c.split()[0] in forbidden for c in commands)
    no_anchor_load = not any('ui_macro_anchors.adc' in c for c in commands)
    source_imports = [c for c in commands if c.startswith('import_db ')]
    source_only = len(source_imports) == 1 and source_imports[0].split(' ', 1)[1].strip('{}"').replace('\\', '/') == Path(syn['output']['path']).as_posix()
    output = run / f'{NAME}_place.db'
    area = run / f'{NAME}_phy.area'
    values = resources(area.read_text(errors='replace')) if area.is_file() else {}
    macro_reports_complete = False
    try:
        rows, reports = guided.actual_macros(log, anchors)
        # Equal old coordinates are permitted, but deliberately not required.
        assert all(r['type'] == a['type'] for r, a in zip(rows, anchors))
        write(run / 'macro_actual_positions.json', {'macros': rows,
              'ten_old_LOCs_imposed': False, 'old_position_equality_not_required': True,
              'fresh_clockBound_and_connectivity_review_pending': True})
        (run / 'macro_reports.txt').write_text(reports, encoding='utf-8')
        macro_reports_complete = True
    except AssertionError as exc:
        errors.append(str(exc))
    validate_manifest(MANIFEST)
    assert refs == inputs()[2]
    for value in controls + preserved:
        verify_ref(value)
    complete = code == 0 and MARKER in log and not errors and output.is_file() and macro_reports_complete and native_scope and no_anchor_load and source_only
    rec.update(state='NATIVE_FREE_UI_PLACE_COMPLETE_REVIEW_PENDING' if complete else 'FAILED_OR_INCOMPLETE_PRESERVED',
               passed=complete, exit_code=code, elapsed_s=time.monotonic() - start,
               output=ref(output) if output.is_file() else None, log=ref(run / 'console.log'),
               errors=errors, resources=values, actual_commands=commands,
               actual_place_only_scope=native_scope, actual_same_SYN_only=source_only,
               actual_ten_LOC_ADC_not_loaded=no_anchor_load,
               after_rover_reserve={k: LIMITS[k] - values[k] - v for k, v in RESERVE.items()} if values else {},
               artifacts={p.name: ref(p) for p in run.iterdir() if p.is_file() and p.suffix in {'.area', '.timing', '.adc', '.v', '.txt', '.json', '.f'} and p.name not in {'receipt.json', 'owned_process.json'}})
    write(run / 'receipt.json', rec)
    write(ALIAS, rec)
    print(json.dumps({k: rec[k] for k in ('state', 'passed', 'run', 'resources', 'errors')}, ensure_ascii=False))
    if not complete:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--timeout', type=int, default=1800)
    args = parser.parse_args()
    assert args.timeout > 0
    syn, anchors, refs = inputs()
    ready = gate_ready(refs)
    if not args.run:
        print(json.dumps({'status': 'PLAN_ONLY', 'device': False, 'native_run': False,
            'source_DB': syn['output'], 'only_physical_delta': 'omit the ten UI/Logo LOC ADC load',
            'omitted_anchor_count': len(anchors), 'required_admission': str(GATE),
            'admission_ready': ready, 'expected_gate_fields': {'passed': True,
                'stage': 'free_ui_place', 'root_authorized_activation': True,
                'only_physical_delta_is_omitting_ten_UI_LOCs': True,
                'fresh_ASR_and_exactQ_required': True, **refs},
            'DDR_semantic_group_member_count': 37, 'new_alias_only': str(ALIAS),
            'short_ASCII_run_root': str(RUN_ROOT), 'all_existing_aliases_preserved': True,
            'fresh_ASR_exactQ_clockBound_macro_review_required': True,
            'no_synthesis_route_bitgen_or_device': True}, ensure_ascii=False, indent=2))
        return
    assert ready, 'Independent admission and root activation required'
    run_place(syn, anchors, refs, args.timeout)


if __name__ == '__main__':
    main()
