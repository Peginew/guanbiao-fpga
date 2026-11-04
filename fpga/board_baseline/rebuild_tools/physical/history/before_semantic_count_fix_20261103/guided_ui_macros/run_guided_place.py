"""One independent offline placement from the frozen SYN database.

Default invocation only validates and prints a plan. --run additionally needs
the independently signed macro_anchor_admission.json. No synthesis, route,
bitgen, MCU, device, original project, or original latest_place mutation.
"""
if not __debug__:
    raise RuntimeError('Verification assertions must remain enabled')

import argparse
import datetime
import json
from pathlib import Path
import re
import shutil
import sys
import time

GUIDED = Path(__file__).resolve().parent
PHYSICAL = GUIDED.parent
sys.path.insert(0, str(PHYSICAL))
from source_helpers import P, NAME, FLOW, validate_manifest, read, write, ref, sha, verify_ref, resources
from run_td import absolute_project, checked_prior, native, LIMITS, RESERVE

MANIFEST = PHYSICAL / 'source_freeze.json'
PLAN = GUIDED / 'anchor_plan.json'
ADC = GUIDED / 'ui_macro_anchors.adc'
GATE = GUIDED / 'macro_anchor_admission.json'
ALIAS = PHYSICAL / 'latest_guided_place.json'
MARKER = 'GUIDED_UI_MACRO_PLACE_COMPLETE'


def inputs():
    validate_manifest(MANIFEST)
    syn = checked_prior('synth', MANIFEST)
    plan = read(PLAN)
    assert plan['SYN'] == syn['output']
    verify_ref(plan['anchors_ADC'])
    assert Path(plan['anchors_ADC']['path']).resolve() == ADC.resolve()
    for key in ('source_comparison', 'source_positions_log', 'reference_routed_DB'):
        verify_ref(plan[key])
    for value in plan['netlists'].values():
        verify_ref(value)
    anchors = plan['anchors']
    assert len(anchors) == len({a['name'] for a in anchors}) == 10
    assert sum(a['type'] == 'PH1P_PHY_ERAM_V2' for a in anchors) == 8
    assert sum(a['type'] == 'PH1P_PHY_DSPSIOU_V2' for a in anchors) == 2
    assert all(a['is_placed'] is True for a in anchors)
    assert all(not any(c in a['name'] for c in '{}\n\r') for a in anchors)
    expected = ['set_inst_assignment {' + a['name'] + '} {location = x' +
                str(a['col']) + 'y' + str(a['row']) + 'z' + str(a['offset']) + ';}'
                for a in anchors]
    assert ADC.read_text(encoding='ascii').splitlines() == expected
    refs = {
        'manifest_sha256': sha(MANIFEST), 'source_db_sha256': syn['output']['sha256'],
        'anchor_plan_sha256': sha(PLAN), 'anchor_adc_sha256': sha(ADC),
        'ddr_group_plan_sha256': sha(PHYSICAL / 'ddr_group_plan.json'),
        'ddr_group_tcl_sha256': sha(PHYSICAL / 'ddr_group.tcl'),
        'runner_sha256': sha(__file__),
    }
    return syn, anchors, refs


def gate_ready(refs):
    if not GATE.is_file():
        return False
    gate = read(GATE)
    assert gate['passed'] is True and gate['stage'] == 'guided_place'
    for key, value in refs.items():
        assert gate[key] == value, 'Admission mismatch: ' + key
    return True


def macro_tcl(anchors, phase):
    lines = ['puts {GUIDED_MACRO_' + phase + '_BEGIN}']
    for a in anchors:
        name = a['name']
        lines += ['puts {BEGIN_GUIDED_' + phase + ' ' + name + '}',
                  'set o [get_cells {' + name + '}]',
                  'if {[llength $o] != 1} {error {GUIDED_MACRO_NOT_UNIQUE}}',
                  'report_cells $o -attributes -connection',
                  'puts {END_GUIDED_' + phase + ' ' + name + '}']
    lines += ['puts {GUIDED_MACRO_' + phase + '_END}']
    return '\n'.join(lines) + '\n'


def generated_flow(anchors):
    flow = FLOW.read_text(encoding='ascii')
    a = flow.index('### Editable zone for opt_place ###')
    b = flow.index('###################################', a)
    zone = '''### Editable zone for opt_place ###
  read_adc ui_macro_anchors.adc
  source ddr_group.tcl
  puts {GUIDED_UI_MACRO_ADC_AND_DDR_GROUP_LOADED}
''' + macro_tcl(anchors, 'PRE') + '''  place
  report_area -io_info -file reader_landmark_s3_phy.area
  export_db reader_landmark_s3_place.db
  export_adc -file actual.adc
  write_verilog actual_netlist.v
  update_timing -mode manhattan
  report_timing_summary -ep_num 16 -path_num 1 -file reader_landmark_s3_place.timing
  report_clock_summary -file clocks.txt
  report_clock_utilization -file clock_utilization.txt
  flow_status -file flow.status
''' + macro_tcl(anchors, 'POST')
    return flow[:a] + zone + flow[b:]


def actual_macros(log, anchors):
    rows = []
    blocks = []
    for a in anchors:
        name = a['name']
        start = 'BEGIN_GUIDED_POST ' + name
        end = 'END_GUIDED_POST ' + name
        assert log.count(start) == 1 and log.count(end) == 1
        block = log.split(start, 1)[1].split(end, 1)[0]
        grid = re.search(r'\bGrid\s*\|\s*col=(\d+)\s+row=(\d+)', block)
        offset = re.search(r'\bOffset\s*\|\s*(\d+)', block)
        model = re.search(r'\bModel\s*\|\s*(\S+)', block)
        placed = re.search(r'\bIsPlaced\s*\|\s*True\b', block)
        assert grid and offset and model and placed, 'Incomplete macro report: ' + name
        got = {'name': name, 'col': int(grid[1]), 'row': int(grid[2]),
               'offset': int(offset[1]), 'type': model[1], 'is_placed': True}
        got['matches_anchor'] = all(got[k] == a[k] for k in a)
        rows.append(got)
        blocks.append(start + '\n' + block + end + '\n')
    return rows, '\n'.join(blocks)


def run_place(syn, anchors, refs, timeout):
    assert gate_ready(refs), 'Independent macro anchor admission required'
    assert not ALIAS.exists(), 'Preserve the previous guided placement; no implicit retry'
    original_alias = ref(PHYSICAL / 'latest_place.json') if (PHYSICAL / 'latest_place.json').exists() else None
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    run = P / f'td_project/{NAME}_Runs' / ('guided_ui_place_' + stamp)
    run.mkdir(parents=True)
    absolute_project(run)
    shutil.copyfile(ADC, run / 'ui_macro_anchors.adc')
    shutil.copyfile(PHYSICAL / 'ddr_group.tcl', run / 'ddr_group.tcl')
    cfg = (Path(syn['run']) / 'settings.cfg').read_text(encoding='ascii')
    cfg = cfg.replace('set run_type syn', 'set run_type phy')
    cfg = cfg.replace('set start_step read_design', 'set start_step opt_place')
    cfg = cfg.replace('set end_step opt_gate', 'set end_step opt_place')
    cfg += '\nset parent ' + Path(syn['run']).as_posix() + '\nset sp 1\nset arr_filter false\nset drHoldFix on\n'
    cfg += 'set phyWildParams {route effort normal route fix_hold on route timing on route post_route_opt off}\n'
    (run / 'settings.cfg').write_text(cfg, encoding='ascii')
    (run / 'DefaultFlow.tcl').write_text(generated_flow(anchors), encoding='ascii')
    (run / 'execute.tcl').write_text('if {[catch {\nsource DefaultFlow.tcl\n} err]} {puts stderr "GUIDED_PLACE_FAILED: $err";exit 1}\nputs ' + MARKER + '\nexit 0\n', encoding='ascii')
    controls = [ref(p) for p in run.iterdir() if p.is_file()] + [ref(__file__), ref(PLAN), ref(GATE)]
    rec = {'stage': 'place', 'state': 'RUNNING', 'passed': False, 'device': False,
           'manifest': ref(MANIFEST), 'gate': ref(GATE), 'anchor_plan': ref(PLAN),
           'source_DB': syn['output'], 'run': str(run), 'controls': controls,
           'original_latest_place': original_alias, 'source_reused_no_synthesis': True,
           'source_tools_unchanged': True, 'macro_constraints_loaded_by_read_adc': True,
           'DDR_soft38_group_preserved': True, 'fresh_ASR_review_required': True,
           'clockBound_and_macro_review_required': True, 'route_or_bitgen_admitted': False}
    write(run / 'receipt.json', rec)
    write(ALIAS, rec)
    start = time.monotonic()
    code = native(run, timeout)
    log = (run / 'console.log').read_text(errors='replace')
    errors = [line for line in log.splitlines() if re.search(r'\bERROR:|\bFATAL:|GUIDED_PLACE_FAILED:', line)]
    commands = re.findall(r'start command "([^"\r\n]+)"', log)
    forbidden = {'elaborate', 'optimize_rtl', 'optimize_gate', 'route', 'bitgen', 'fix_hold'}
    native_scope = not any(command.split()[0] in forbidden for command in commands)
    output = run / f'{NAME}_place.db'
    area = run / f'{NAME}_phy.area'
    values = resources(area.read_text(errors='replace')) if area.is_file() else {}
    macro_ok = False
    try:
        rows, reports = actual_macros(log, anchors)
        write(run / 'macro_actual_positions.json', {'anchors': rows, 'all_match': all(r['matches_anchor'] for r in rows),
              'clockBound_review_pending': True, 'two_DSPs_are_combinational_clockless': True})
        (run / 'macro_reports.txt').write_text(reports, encoding='utf-8')
        macro_ok = all(r['matches_anchor'] for r in rows)
    except AssertionError as exc:
        errors.append(str(exc))
    validate_manifest(MANIFEST)
    assert refs == inputs()[2]
    for value in controls:
        verify_ref(value)
    if original_alias is not None:
        verify_ref(original_alias)
    complete = code == 0 and MARKER in log and not errors and output.is_file() and macro_ok and native_scope
    rec.update({'state': 'NATIVE_GUIDED_PLACE_COMPLETE_REVIEW_PENDING' if complete else 'FAILED_OR_INCOMPLETE_PRESERVED',
                'passed': complete, 'exit_code': code, 'elapsed_s': time.monotonic() - start,
                'output': ref(output) if output.is_file() else None, 'log': ref(run / 'console.log'),
                'errors': errors, 'resources': values, 'ten_macro_positions_match': macro_ok,
                'actual_commands': commands, 'actual_place_only_scope': native_scope,
                'after_rover_reserve': {k: LIMITS[k] - values[k] - v for k, v in RESERVE.items()} if values else {},
                'artifacts': {p.name: ref(p) for p in run.iterdir() if p.is_file() and p.suffix in {'.area', '.timing', '.adc', '.v', '.txt', '.json', '.f'} and p.name not in {'receipt.json', 'owned_process.json'}}})
    write(run / 'receipt.json', rec)
    write(ALIAS, rec)
    print(json.dumps({k: rec[k] for k in ('state', 'passed', 'run', 'resources', 'ten_macro_positions_match', 'errors')}, ensure_ascii=False))
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
                         'source_DB': syn['output'], 'anchors': len(anchors),
                         'anchor_constraints': ref(ADC), 'required_admission': str(GATE),
                         'admission_ready': ready, 'expected_gate_fields': {'passed': True, 'stage': 'guided_place', **refs},
                         'new_alias_only': str(ALIAS), 'original_latest_place_preserved': True,
                         'fresh_ASR_and_clockBound_review_after_place': True,
                         'no_route_or_bitgen': True}, ensure_ascii=False, indent=2))
        return
    assert ready, 'Independent macro anchor admission required'
    run_place(syn, anchors, refs, args.timeout)


if __name__ == '__main__':
    main()
