"""One offline route from the newly reviewed guided placement; default PLAN.

Only --run executes TD, after guided_route_admission.json binds the exact
place, fresh ASR mapping, pure SDC files and reviews. This entry never edits
old aliases, original RTL/tools, MCU firmware, models, or a device.
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
from source_helpers import P, NAME, read, write, ref, sha, verify_ref, validate_manifest, resources, final_timing
from run_td import absolute_project, native, final_reports, LIMITS, RESERVE

PLACE = PHYSICAL / 'latest_guided_place.json'
GATE = GUIDED / 'guided_route_actual_admission.json'
ALIAS = PHYSICAL / 'latest_guided_route_actual.json'
MARKER = 'GUIDED_LITERAL_CONTRACT_FINAL_COMPLETE'


def base_inputs():
    place = read(PLACE)
    assert place['passed'] and place['stage'] == 'place' and place['ten_macro_positions_match']
    manifest = verify_ref(place['manifest'])
    validate_manifest(manifest)
    verify_ref(place['output'])
    for value in place['controls']:
        verify_ref(value)
    for value in place['artifacts'].values():
        verify_ref(value)
    return place, manifest


def admission(place, manifest):
    if not GATE.is_file():
        return None
    gate = read(GATE)
    assert gate['passed'] is True and gate['stage'] == 'guided_route_actual'
    assert gate['place_receipt'] == ref(PLACE)
    assert gate['source_DB'] == place['output']
    assert gate['manifest'] == ref(manifest)
    assert gate['runner_sha256'] == sha(__file__)
    assert type(gate['expected_PSI_path_count']) is int and gate['expected_PSI_path_count'] == 17
    assert read(verify_ref(gate['PSI_path_source_review']))['passed'] is True
    for key in ('place_receipt', 'source_DB', 'manifest', 'ASR_mapping', 'asr_literal', 'psi_literal'):
        verify_ref(gate[key])
    assert gate['clock_macro_reviews']
    for value in gate['clock_macro_reviews']:
        verify_ref(value)
    mapping = read(verify_ref(gate['ASR_mapping']))
    assert mapping['derived'] is True
    assert mapping['placed_DB'] == place['output']
    assert mapping['placed_netlist'] == place['artifacts']['actual_netlist.v']
    count = gate['ASR_count']
    assert type(count) is int and 1 <= count <= 12
    assert mapping['logical_FF_count'] == 12 and mapping['physical_ASR_count'] == count
    assert len(mapping['pins']) == len(set(mapping['pins'])) == count
    assert mapping['nonserial_registered_consumers'] == []
    assert mapping['old_physical_pins_copied'] is False
    # The independently signed files are declarations, never interactive Tcl.
    asr = verify_ref(gate['asr_literal']).read_text(encoding='ascii').strip()
    psi = verify_ref(gate['psi_literal']).read_text(encoding='ascii').strip()
    assert asr.startswith('set_false_path ') and len(asr.splitlines()) == 1
    assert psi.startswith('set_max_delay ') and len(psi.splitlines()) == 1
    assert '-from [get_pins {' in psi, 'Only independently qualified exact PSI Q-half sources are admitted'
    assert '-datapath_only 7.200' in psi and 'return_psi_valid' in psi and 'return_psi_q8' in psi
    assert all(pin in asr for pin in mapping['pins']) and '.asr' in asr
    return gate


def verify_tcl(count, psi_paths):
    return r'''
report_timing_exception -ep_num 256 -path_num 1 -file pre_contract_exception.timing
report_timing_ignored -ep_num 32 -path_num 1 -file pre_contract_ignored.timing
set f [open pre_contract_exception.timing r];set psi_text [read $f];close $f
set psi_rows 0
set check_mode {}
foreach line [split $psi_text "\n"] {
 if {[string trim $line]=={Max Check}} {set check_mode Max}
 if {[string trim $line]=={Min Check}} {set check_mode Min}
 if {[regexp {^\s*@@PSI@@\s+@@PSI@@\s+0\s+0\s+set_max_delay} $line] && $check_mode=={Max} && [string first return_psi_q8 $line]>=0 && [string first return_psi_valid $line]>=0 && [string first {-datapath_only 7.200} $line]>=0} {incr psi_rows}
}
set f [open pre_contract_ignored.timing r];set asr_text [read $f];close $f
set asr_max 0
set asr_min 0
set check_mode {}
foreach line [split $asr_text "\n"] {
 if {[string trim $line]=={Max Check}} {set check_mode Max}
 if {[string trim $line]=={Min Check}} {set check_mode Min}
 if {[regexp {^\s*@@N@@\s+@@N@@\s+0\s+0\s+set_false_path} $line] && [string first u_hdmi_reset/release_ff $line]>=0 && [string first .asr $line]>=0} {
  if {$check_mode=={Max}} {incr asr_max}
  if {$check_mode=={Min}} {incr asr_min}
 }
}
puts "ACTUAL_GUIDED_CONTRACT_ROWS PSI=$psi_rows ASR_MAX=$asr_max ASR_MIN=$asr_min ASR_COUNT=@@N@@"
if {$psi_rows!=1 || $asr_max!=1 || $asr_min!=1} {error {ACTUAL_GUIDED_SDC_CONTRACT_NOT_ACTIVE}}
puts {ACTUAL_GUIDED_LITERAL_CONTRACTS_PROVEN}
'''.replace('@@N@@', str(count)).replace('@@PSI@@', str(psi_paths))


def route_body(count, pins, psi_paths):
    text = r'''import_device ph1_35p.db -package PH1P35MDG324 -speed 3
import_db input_place.db
read_sdc asr_literal.sdc
read_sdc psi_literal.sdc
puts {GUIDED_LITERAL_SDC_REGISTERED_BEFORE_CLOCK_DISCOVERY}
report_clock_summary -file initial_clocks.txt
set nq8 [llength [get_regs {u_meter_pair/pipeline/reader/live/return_psi_q8[*]}]]
set nvalid [llength [get_regs {u_meter_pair/pipeline/reader/live/return_psi_valid}]]
set nhdmi [llength [get_clocks {HDMI_PIXEL_CLK}]]
set nasr [llength [get_pins {@@PINS@@}]]
if {$nq8!=16 || $nvalid!=1 || $nhdmi!=1 || $nasr!=@@N@@} {error {ACTUAL_GUIDED_PSI_ASR_OBJECT_COUNT}}
update_timing -mode manhattan
'''.replace('@@PINS@@', ' '.join(pins)).replace('@@N@@', str(count))
    text += verify_tcl(count, psi_paths)
    text += r'''
set_param route effort normal
set_param route fix_hold on
set_param route timing on
set_param route post_route_opt off
commit_param -step route
route
update_timing -mode final
report_timing_status -file before_hold.ts
set f [open before_hold.ts r];set ts [read $f];close $f
if {![regexp {HWNS:\s*(-?[0-9.]+)ns} $ts -> h]} {error {HOLD_STATUS_UNPARSED}}
if {$h < 0.0} {fix_hold;update_timing -mode final}
'''
    text += final_reports()
    text += r'''
report_timing_exception -ep_num 256 -path_num 1 -file all_held_data.timing
report_timing_ignored -ep_num 32 -path_num 1 -file all_ignored_data.timing
report_clock_intersection -file clock_intersection.txt
puts {GUIDED_LITERAL_CONTRACT_FINAL_COMPLETE}
'''
    return text


def summary_rules(text, kind, token):
    out = []
    mode = None
    for line in text.splitlines():
        if line.strip() in ('Max Check', 'Min Check'):
            mode = line.strip().split()[0]
        match = re.match(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(' + kind + r'.*)$', line)
        if match and token in match[5]:
            out.append(dict(zip(('total', 'active', 'shadowed', 'ignored', 'command'),
                                [int(x) for x in match.groups()[:4]] + [match[5]]), check=mode))
    return out


def summary_ok(psi, asr, count, psi_paths):
    psi_ok = len(psi) == 1 and psi[0]['check'] == 'Max' and all(
        psi[0][key] == value for key, value in {'total': psi_paths, 'active': psi_paths, 'shadowed': 0, 'ignored': 0}.items())
    asr_ok = len(asr) == 2 and {x['check'] for x in asr} == {'Max', 'Min'} and all(
        all(row[key] == value for key, value in {'total': count, 'active': count, 'shadowed': 0, 'ignored': 0}.items()) for row in asr)
    return psi_ok, asr_ok


def run_route(place, manifest, gate, timeout):
    assert not ALIAS.exists(), 'Preserve previous guided route; no automatic retry'
    count = gate['ASR_count']
    psi_paths = gate['expected_PSI_path_count']
    mapping = read(verify_ref(gate['ASR_mapping']))
    original_aliases = [ref(p) for p in (PHYSICAL / 'latest_place.json', PHYSICAL / 'latest_route.json') if p.exists()]
    run = P / f'td_project/{NAME}_Runs' / ('guided_route_actual_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    run.mkdir(parents=True)
    absolute_project(run)
    shutil.copyfile(verify_ref(place['output']), run / 'input_place.db')
    shutil.copyfile(verify_ref(gate['asr_literal']), run / 'asr_literal.sdc')
    shutil.copyfile(verify_ref(gate['psi_literal']), run / 'psi_literal.sdc')
    script = 'if {[catch {\n' + route_body(count, mapping['pins'], psi_paths) + '} err]} {puts stderr "GUIDED_ROUTE_FAILED: $err";exit 1}\nexit 0\n'
    (run / 'execute.tcl').write_text(script, encoding='ascii')
    controls = [ref(p) for p in run.iterdir() if p.is_file()] + [ref(__file__), ref(GATE), ref(PLACE), gate['ASR_mapping'], gate['PSI_path_source_review']] + gate['clock_macro_reviews']
    rec = {'stage': 'route', 'state': 'RUNNING', 'passed': False, 'device': False,
           'manifest': ref(manifest), 'source_DB': place['output'], 'gate': ref(GATE), 'run': str(run),
           'place_receipt': ref(PLACE), 'controls': controls, 'ASR_count': count,
           'PSI_logical_source_count': 17, 'expected_PSI_path_count': psi_paths, 'PSI_path_source_review': gate['PSI_path_source_review'],
           'original_aliases_preserved': original_aliases,
           'PSI_eachsource_FINAL_independent_review_passed': False,
           'bitgen_admitted': False, 'pure_read_sdc_before_first_timer_required': True}
    write(run / 'receipt.json', rec)
    write(ALIAS, rec)
    start = time.monotonic()
    code = native(run, timeout)
    log = (run / 'console.log').read_text(errors='replace')
    errors = [x for x in log.splitlines() if re.search(r'\bERROR:|\bFATAL:|GUIDED_ROUTE_FAILED:', x)]
    def file_text(name):
        path = run / name
        return path.read_text(errors='replace') if path.is_file() else ''
    values = resources(file_text(f'{NAME}_phy.area'))
    timing = final_timing(file_text(f'{NAME}_phy.ts'))
    timing_ok = len(timing) == 4 and timing['SWNS'] >= 0 and timing['HWNS'] >= 0 and timing['STNS'] == 0 and timing['HTNS'] == 0
    capacity = all(key in values and values[key] <= limit for key, limit in LIMITS.items())
    psi = summary_rules(file_text('all_held_data.timing'), 'set_max_delay', 'return_psi_q8')
    asr = summary_rules(file_text('all_ignored_data.timing'), 'set_false_path', 'u_hdmi_reset/release_ff')
    psi_ok, asr_ok = summary_ok(psi, asr, count, psi_paths)
    pre_psi = summary_rules(file_text('pre_contract_exception.timing'), 'set_max_delay', 'return_psi_q8')
    pre_asr = summary_rules(file_text('pre_contract_ignored.timing'), 'set_false_path', 'u_hdmi_reset/release_ff')
    pre_psi_ok, pre_asr_ok = summary_ok(pre_psi, pre_asr, count, psi_paths)
    registered = log.find('GUIDED_LITERAL_SDC_REGISTERED_BEFORE_CLOCK_DISCOVERY')
    first_timer = log.find('start command "start_timer"')
    proven = log.find('ACTUAL_GUIDED_LITERAL_CONTRACTS_PROVEN')
    routed = log.find('start command "route"')
    order = 0 <= registered < first_timer < proven < routed
    drc = 'No multi-drive.' in log and 'No abnormal timing path.' in log
    commands = re.findall(r'start command "([^"\r\n]+)"', log)
    no_other_stages = not any(x.split()[0] in {'elaborate', 'optimize_rtl', 'optimize_gate', 'place', 'bitgen'} for x in commands)
    output = run / f'{NAME}_pr.db'
    passed = (code == 0 and not errors and output.is_file() and MARKER in log and timing_ok and capacity and
              psi_ok and asr_ok and pre_psi_ok and pre_asr_ok and order and drc and no_other_stages)
    validate_manifest(manifest)
    assert admission(place, manifest) == gate
    for value in controls + original_aliases:
        verify_ref(value)
    rec.update({'state': 'ACTUAL_GUIDED_FINAL_PASS_INDEPENDENT_REVIEW_PENDING' if passed else 'FAILED_OR_INCOMPLETE_PRESERVED',
                'passed': passed, 'exit_code': code, 'elapsed_s': time.monotonic() - start,
                'output': ref(output) if output.is_file() else None, 'log': ref(run / 'console.log'),
                'resources': values, 'FINAL': timing, 'errors': errors,
                'global_final_timing_passed': timing_ok, 'physical_capacity_passed': capacity,
                'literal_contracts_before_first_timer_and_pre_route': order,
                'PSI_pre_summary': pre_psi, 'ASR_pre_summary': pre_asr,
                'PSI_final_summary': psi, 'ASR_final_summary': asr,
                'PSI_summary_active_passed': psi_ok, 'ASR_summary_active_passed': asr_ok,
                'DRC_messages_passed': drc, 'actual_route_only_scope': no_other_stages,
                'actual_commands': commands,
                'after_rover_reserve': {k: LIMITS[k] - values[k] - v for k, v in RESERVE.items()} if values else {},
                'artifacts': {p.name: ref(p) for p in run.iterdir() if p.is_file() and p.suffix in {'.area', '.timing', '.ts', '.adc', '.v', '.txt', '.sdc'}}})
    write(run / 'receipt.json', rec)
    write(ALIAS, rec)
    print(json.dumps({k: rec[k] for k in ('state', 'passed', 'run', 'resources', 'FINAL', 'PSI_summary_active_passed', 'ASR_summary_active_passed', 'errors')}, ensure_ascii=False))
    if not passed:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--timeout', type=int, default=7200)
    args = parser.parse_args()
    assert args.timeout > 0
    place, manifest = base_inputs()
    gate = admission(place, manifest)
    if not args.run:
        print(json.dumps({'status': 'PLAN_ONLY', 'device': False, 'native_run': False,
                         'source_DB': place['output'], 'place_receipt': ref(PLACE),
                         'required_admission': str(GATE), 'admission_ready': gate is not None,
                         'ASR_count': gate['ASR_count'] if gate else 'PENDING_FRESH_MAPPING',
                         'runner_sha256': sha(__file__), 'timeout_seconds': args.timeout,
                         'pure_read_sdc_before_first_timer': True,
                         'PSI_logical_source_count': 17, 'expected_PSI_path_count': gate['expected_PSI_path_count'] if gate else 'PENDING_SIGNED_PATH_REVIEW',
                         'pre_route_required': 'PSI signed-path-count/active-same/0/0 and ASR Max+Min fresh-n/n/0/0',
                         'route': {'effort': 'normal', 'timing': 'on', 'fix_hold': 'on', 'post_route_opt': 'off'},
                         'new_alias_only': str(ALIAS), 'PSI_eachsource_FINAL_independent_review_pending': True,
                         'no_bitgen_or_device': True}, ensure_ascii=False, indent=2))
        return
    assert gate is not None, 'Fresh guided route admission required'
    run_route(place, manifest, gate, args.timeout)


if __name__ == '__main__':
    main()
