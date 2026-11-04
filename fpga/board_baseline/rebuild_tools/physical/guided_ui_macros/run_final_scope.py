"""Read-only FINAL collection, default PLAN; only after this route has passed.

First run is import-only. A missing imported dynamic SDC remains a failed
receipt. A separate explicit literal invocation may reload only absent rules,
from this same route's signed files, before the first timer. Never PNR/export,
never silently clear or duplicate an existing timing rule, never a device.
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
TASK = PHYSICAL.parent
sys.path.insert(0, str(PHYSICAL))
from source_helpers import P, read, write, ref, verify_ref, validate_manifest, final_timing
from run_td import native
from run_guided_route_actual import summary_rules, summary_ok

ROUTE = PHYSICAL / 'latest_guided_route_actual.json'
GATE = GUIDED / 'guided_route_actual_admission.json'
INVENTORY = TASK / 'review/physical_source/stable3s_placed_DATA_inventory.json'


def inputs():
    route = read(ROUTE)
    assert route['passed'] and route['exit_code'] == 0 and route['global_final_timing_passed']
    manifest = verify_ref(route['manifest'])
    validate_manifest(manifest)
    verify_ref(route['output'])
    gate = read(verify_ref(route['gate']))
    assert gate == read(GATE) and gate['passed'] and route['source_DB'] == gate['source_DB']
    assert gate['expected_PSI_path_count'] == 17
    assert read(verify_ref(gate['PSI_path_source_review']))['passed'] is True
    for key in ('ASR_mapping', 'asr_literal', 'psi_literal'):
        verify_ref(gate[key])
    inv = read(INVENTORY)
    assert inv['passed'] and inv['actual_mapped_count'] == len(inv['registers']) == 74
    assert inv['source_DB'] == route['source_DB']
    assert gate['Stable3s_DATA_actual_mapping'] == ref(INVENTORY)
    logical = [r['logical_Q'].lstrip('\\') for r in inv['registers']]
    assert len(set(logical)) == 74 and not any(any(c in n for c in '{}\n\r') for n in logical)
    qpins = [r['physical'].lstrip('\\') + '.' + r['Q_pin'] for r in inv['registers']]
    assert len(set(qpins)) == 74
    return route, gate, logical, qpins


def reports_tcl(logical, qpins):
    text = r'''
report_clock_summary -file clocks.txt
update_timing -mode final
set clocks [get_clocks *]
set f [open clocks_all.txt w]
puts $f "COUNT [llength $clocks]"
foreach clock $clocks {puts $f [list CLOCK $clock]}
close $f
report_timing_status -file actual_FINAL.ts
report_timing_summary -ep_num 32 -path_num 1 -file normal_global_FINAL.timing
report_timing_exception -ep_num 256 -path_num 1 -file all_held_SMD.timing
report_timing_ignored -ep_num 32 -path_num 1 -file all_ignored_FP.timing
report_route_status -drc
set lookup [open stable74_lookup.txt w]
'''
    for index, name in enumerate(logical):
        # Each request retains its own exact object lookup and D/Q reports.
        # An empty result is not silently reclassified as a constant endpoint.
        text += 'set s3 [get_regs {' + name + '}]\n'
        text += 'set sq [get_pins {' + qpins[index] + '}]\n'
        text += 'puts $lookup [format {ROW %d COUNT %d LOGICAL {%s} OBJECTS {%s} QCOUNT %d QOBJECTS {%s}} ' + str(index) + ' [llength $s3] {' + name + '} $s3 [llength $sq] $sq]\n'
        text += 'if {[llength $s3]==1} {\n'
        text += f' report_timing_path -to $s3 -ep_num 1 -path_num 1 -file stable_{index:02d}_D.timing\n'
        text += '}\nif {[llength $sq]==1} {\n'
        text += f' report_timing_path -from $sq -ep_num 1 -path_num 1 -file stable_{index:02d}_Q.timing\n'
        text += '}\n'
    text += 'close $lookup\n'
    for stage in range(3):
        names = ' '.join(f'u_hdmi_tx/u_hdmi2phy_wrapper/u{lane}_lane_lvds_8_1/u_serial_reset/release_ff[{stage}]' for lane in range(4))
        text += 'set sr' + str(stage) + ' [get_regs {' + names + '}]\n'
    text += r'''
report_timing_path -from $sr0 -to $sr1 -ep_num 16 -path_num 1 -file serial_stage01_DATA.timing
report_timing_path -from $sr1 -to $sr2 -ep_num 16 -path_num 1 -file serial_stage12_DATA.timing
report_timing_path -from $sr2 -ep_num 32 -path_num 1 -file serial_consumers_DATA.timing
report_timing_path -from [get_regs {u_hdmi_tx/u_hdmi2phy_wrapper/*/S_odd_even*}] -ep_num 16 -path_num 1 -file serial_odd_even_DATA.timing
puts {STABLE3S_READONLY_FINAL_SCOPE_COMPLETE}
'''
    return text


def path_rows(text):
    return [{'slack_ns': float(s), 'begin': b.strip(), 'end': e.strip()}
            for s, b, e in re.findall(r'^Slack\s*:\s*(-?[0-9.]+)ns\s*\nBegin Point\s*:\s*([^\n]+)\nEnd Point\s*:\s*([^\n]+)', text, re.M)]


def run_scope(mode):
    route, gate, logical, qpins = inputs()
    receipt_file = GUIDED / ('final_scope_' + mode.replace('-', '_') + '.json')
    assert not receipt_file.exists(), 'Retain prior read-only attempt; no implicit repetition'
    missing = []
    prior_ref = None
    if mode == 'literal':
        prior_file = GUIDED / 'final_scope_import_only.json'
        prior = read(prior_file)
        assert prior['routed_DB'] == route['output'] and prior['native_query_passed']
        assert not prior['passed'] and not prior['constraint_conflict_present']
        missing = prior['missing_literals']
        assert missing and set(missing) <= {'asr', 'psi'}
        prior_ref = ref(prior_file)
    run = P / 'td_project' / ('fchk_' + mode[:3] + '_' + datetime.datetime.now().strftime('%H%M%S_%f'))
    run.mkdir()
    body = 'import_device ph1_35p.db -package PH1P35MDG324 -speed 3\nimport_db {' + Path(route['output']['path']).as_posix() + '}\n'
    for key in missing:
        shutil.copyfile(verify_ref(gate[key + '_literal']), run / (key + '_literal.sdc'))
        body += 'read_sdc ' + key + '_literal.sdc\n'
    if mode == 'literal':
        body += 'puts {FINAL_SCOPE_SAME_LITERAL_LOADED_BEFORE_FIRST_TIMER}\n'
    body += reports_tcl(logical, qpins)
    (run / 'execute.tcl').write_text('if {[catch {\n' + body + '} err]} {puts stderr "STABLE3S_READONLY_SCOPE_FAILED: $err";exit 1}\nexit 0\n', encoding='ascii')
    controls = [ref(__file__), ref(ROUTE), ref(GATE), ref(INVENTORY), ref(run / 'execute.tcl')]
    controls += [ref(run / (key + '_literal.sdc')) for key in missing]
    if prior_ref:
        controls.append(prior_ref)
    start = time.monotonic()
    code = native(run, 300)
    log = (run / 'console.log').read_text(errors='replace')
    errors = [line for line in log.splitlines() if re.search(r'\bERROR:|\bFATAL:|STABLE3S_READONLY_SCOPE_FAILED:', line)]
    def content(name):
        p = run / name
        return p.read_text(errors='replace') if p.is_file() else ''
    commands = re.findall(r'start command "([^"\r\n]+)"', log)
    forbidden = {'place', 'route', 'fix_hold', 'bitgen', 'export_db', 'elaborate', 'optimize_rtl', 'optimize_gate', 'read_verilog'}
    readonly = not ({c.split()[0] for c in commands} & forbidden)
    registered = log.find('FINAL_SCOPE_SAME_LITERAL_LOADED_BEFORE_FIRST_TIMER')
    timer = log.find('start command "start_timer"')
    order = (0 <= registered < timer) if mode == 'literal' else not any(c.startswith('read_sdc ') for c in commands)
    timing = final_timing(content('actual_FINAL.ts'))
    timing_ok = len(timing) == 4 and timing['SWNS'] >= 0 and timing['HWNS'] >= 0 and timing['STNS'] == timing['HTNS'] == 0
    psi = summary_rules(content('all_held_SMD.timing'), 'set_max_delay', 'return_psi_q8')
    asr = summary_rules(content('all_ignored_FP.timing'), 'set_false_path', 'u_hdmi_reset/release_ff')
    psi_ok, asr_ok = summary_ok(psi, asr, gate['ASR_count'], gate['expected_PSI_path_count'])
    absent = (['psi'] if not psi else []) + (['asr'] if not asr else [])
    conflict = bool((psi and not psi_ok) or (asr and not asr_ok))
    clocks_text = content('clocks_all.txt')
    clock_count = re.search(r'^COUNT (\d+)$', clocks_text, re.M)
    clock_count = int(clock_count[1]) if clock_count else None
    lookups = []
    for line in content('stable74_lookup.txt').splitlines():
        match = re.fullmatch(r'ROW (\d+) COUNT (\d+) LOGICAL \{([^}]+)\} OBJECTS \{(.*)\} QCOUNT (\d+) QOBJECTS \{(.*)\}', line)
        if match:
            lookups.append({'index': int(match[1]), 'count': int(match[2]), 'logical': match[3], 'actual_objects': match[4],
                            'Q_count': int(match[5]), 'Q_actual_objects': match[6], 'Q_expected_pin': qpins[int(match[1])]})
    lookup_ok = len(lookups) == 74 and [r['logical'] for r in lookups] == logical and all(r['count'] == r['Q_count'] == 1 for r in lookups)
    stable = []
    for index, name in enumerate(logical):
        row = {'index': index, 'logical_Q': name, 'Q_exact_pin': qpins[index],
               'D_scope': 'get_regs may include packed other half; actual routed D-mux classification required'}
        for direction in ('D', 'Q'):
            filename = f'stable_{index:02d}_{direction}.timing'
            paths = path_rows(content(filename))
            row[direction] = {'report': ref(run / filename) if (run / filename).is_file() else None,
                              'paths': paths, 'status': 'ORDINARY_PATHS_REPORTED' if paths else 'NO_DATA_REPORTED_REQUIRES_INDEPENDENT_CLASSIFICATION'}
        stable.append(row)
    normal = path_rows(content('normal_global_FINAL.timing'))
    token = 'clock u_ph1p35_324_ddr_wrapper/u_ddr2/usr_clk '
    ddr = [r for r in normal if token in r['begin'] and token in r['end']]
    ordinary = {}
    for name in ('serial_stage01_DATA.timing', 'serial_stage12_DATA.timing', 'serial_consumers_DATA.timing', 'serial_odd_even_DATA.timing'):
        ordinary[name] = path_rows(content(name))
    all_paths = [r for item in stable for direction in ('D', 'Q') for r in item[direction]['paths']]
    all_paths += [r for rows in ordinary.values() for r in rows] + ddr
    nonnegative = bool(all_paths) and all(r['slack_ns'] >= 0 for r in all_paths)
    complete = code == 0 and not errors and 'STABLE3S_READONLY_FINAL_SCOPE_COMPLETE' in log and readonly and order
    drc = 'No multi-drive.' in log and 'No abnormal timing path.' in log
    passed = complete and psi_ok and asr_ok and timing_ok and clock_count == 18 and lookup_ok and nonnegative and bool(ddr) and drc
    rec = {'passed': passed, 'status': 'NATIVE_READONLY_COLLECTION_PASS_INDEPENDENT_DATA_REVIEW_REQUIRED' if passed else 'READONLY_SCOPE_FAIL_PRESERVED',
           'mode': mode, 'native_query_passed': complete, 'route_receipt': ref(ROUTE), 'routed_DB': route['output'],
           'sourcefreeze': route['manifest'], 'scope_runner': ref(__file__), 'run': str(run), 'exit_code': code,
           'elapsed_s': time.monotonic() - start, 'errors': errors, 'actual_commands': commands,
           'pure_literal_refs': {key: gate[key + '_literal'] for key in ('asr', 'psi')},
           'reloaded_literals': missing, 'prior_import_only_failure': prior_ref, 'missing_literals': absent,
           'PSI_logical_source_count': 17, 'expected_PSI_path_count': gate['expected_PSI_path_count'],
           'PSI_exact_Q_source_review': gate['PSI_path_source_review'],
           'constraint_conflict_present': conflict, 'PSI17_active': psi_ok, 'ASR_active': asr_ok,
           'PSI_SMD_rows': psi, 'ASR_FP_Max_Min_rows': asr, 'FINAL': timing, 'clock_count': clock_count,
           'Stable74_inventory': ref(INVENTORY), 'Stable74_actual_lookup': lookups,
           'Stable74_lookups_unique': lookup_ok, 'Stable74_D_Q': stable,
           'Stable74_all_D_Q_reports_nonempty': all(x[d]['paths'] for x in stable for d in ('D', 'Q')),
           'Stable3s74_full_DATA_independent_review_passed': False,
           'serial_ordinary_DATA': ordinary, 'DDR_normal_FINAL_paths': ddr, 'all_reported_DATA_slacks_nonnegative': nonnegative,
           'DRC_messages_passed': drc, 'no_PNR_export_or_device': readonly, 'device': False,
           'controls': controls, 'artifacts': {f.name: ref(f) for f in run.iterdir() if f.is_file() and f.suffix in {'.timing', '.ts', '.txt', '.log', '.tcl', '.sdc'}}}
    for item in controls:
        verify_ref(item)
    verify_ref(route['output'])
    validate_manifest(verify_ref(route['manifest']))
    write(receipt_file, rec)
    write(run / 'receipt.json', rec)
    print(json.dumps({k: rec[k] for k in ('passed', 'mode', 'run', 'exit_code', 'elapsed_s', 'clock_count', 'PSI17_active', 'ASR_active', 'missing_literals', 'constraint_conflict_present', 'errors')}, ensure_ascii=False))
    if not passed:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['import-only', 'literal'], default='import-only')
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if not args.run:
        route = read(ROUTE) if ROUTE.is_file() else {}
        print(json.dumps({'status': 'PLAN_ONLY', 'mode': args.mode, 'route_state': route.get('state'),
            'route_passed': route.get('passed', False), 'native_run': False, 'device': False,
            'import_only_first': True, 'no_automatic_literal_fallback': True,
            'literal_only_for_absent_signed_rules_after_preserved_import_failure': True,
            'Stable74_per_logical_lookup_and_D_Q_reports': True,
            'no_get_clocks_as_path_from_target': True, 'no_PNR_export_or_device': True}, ensure_ascii=False, indent=2))
        return
    run_scope(args.mode)


if __name__ == '__main__':
    main()
