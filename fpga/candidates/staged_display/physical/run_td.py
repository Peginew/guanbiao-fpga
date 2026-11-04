"""New Stable3s/PSI platform: explicit offline SYN or accepted-DB bitgen.

Default PLAN never starts TD. Placement and routing are delegated only to the
fresh guided entries; there is no legacy interactive CDC overlay route path.
"""
if not __debug__:
    raise RuntimeError('Verification assertions must remain enabled')

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from source_helpers import HERE, P, NAME, TD, FLOW, collect_inputs, validate_manifest, ref, read, write, sha, verify_ref, resources
from mapping_helpers import derive_ddr

LIMITS = {'Slice': 21216, 'FF': 42432, 'ERAM': 108, 'DSP': 40, 'PLL': 6, 'MCU': 1}
RESERVE = {'Slice': 1200, 'FF': 2400, 'ERAM': 2}


def native(run, timeout):
    (run / 'temp').mkdir()
    with (run / 'console.log').open('wb') as log:
        proc = subprocess.Popen([str(TD), (run / 'execute.tcl').as_posix()], cwd=run,
            stdout=log, stderr=subprocess.STDOUT,
            env={**os.environ, 'TEMP': str(run / 'temp'), 'TMP': str(run / 'temp')},
            creationflags=subprocess.CREATE_NO_WINDOW)
        write(run / 'owned_process.json', {'pid': proc.pid, 'stage': run.name, 'device': False})
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            assert proc.poll() is None
            # Only this exact process tree, never other chats' TD sessions.
            stopped = subprocess.run(['taskkill.exe', '/PID', str(proc.pid), '/T', '/F'],
                capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
            (run / 'timeout_owned_cleanup.log').write_bytes(stopped.stdout + stopped.stderr)
            proc.wait(timeout=20)
            return None


def absolute_project(run):
    al = (P / f'td_project/{NAME}.al').read_text(encoding='utf-8-sig')
    al = re.sub(r'(<Project\b[^>]*?) Path="[^"]+"', r'\1', al)
    al = re.sub(r'<File Path="([^"]+)"', lambda m: '<File Path="' + (P / 'td_project' / m[1]).resolve().as_posix() + '"', al)
    for value in re.findall(r'<File Path="([^"]+)"', al):
        assert Path(value).is_file(), value
    (run / f'{NAME}.prj').write_text(al, encoding='utf-8')


def settings():
    return f'''set ADCList {{"{(P/'user_source/constraints_source/pin.adc').as_posix()}"}}
set IpADCList {{ ddr2 {(P/'user_source/hdl_source/ph1p35_ddr/ddr2/src/adc/ddr2.adc').as_posix()} }}
set IpSDCList {{ ddr2 {(P/'user_source/hdl_source/ph1p35_ddr/ddr2/src/sdc/ddr2.sdc').as_posix()} w128_d512_fifo {(P/'user_source/ip_source/w128_d512_fifo/w128_d512_fifo.tcl').as_posix()} mcu_roi50 {(P/'user_source/ip_source/mcu_roi50/mcu_roi50.tcl').as_posix()} }}
set SDCList {{"{(P/'td_project/base_auto_quality.sdc').as_posix()}"}}
set area_option -packarea
set device_name ph1_35p.db
set package_name PH1P35MDG324
set prj_name {NAME}
set run_type syn
set speed 3
set top_model_name design_top_wrapper
set start_step read_design
set end_step opt_gate
'''


def checked_prior(stage, manifest):
    obj = read(HERE / f'latest_{stage}.json')
    assert obj['passed'] and obj['manifest']['sha256'] == sha(manifest)
    verify_ref(obj['output'])
    for value in obj.get('artifacts', {}).values():
        verify_ref(value)
    return obj


def final_reports():
    return f'''report_area -io_info -file {NAME}_phy.area
update_timing -mode final
report_timing_status -file {NAME}_phy.ts
report_timing_summary -ep_num 16 -path_num 1 -file {NAME}_pr.timing
report_timing_exception -file {NAME}_exception.timing
report_clock_summary -file clocks.txt
report_clock_utilization -file clock_utilization.txt
flow_status -file flow.status
report_route_status -drc
write_verilog actual_netlist.v
export_adc -file actual.adc
export_db {NAME}_pr.db
'''


def admission(stage, manifest, gate):
    g = read(gate)
    assert g['passed'] is True and g['stage'] == stage
    assert g['manifest_sha256'] == sha(manifest)
    if stage == 'bitgen':
        parent = checked_prior('route', manifest)
        assert g['source_db_sha256'] == parent['output']['sha256']
        for key in ('bitgen_admitted', 'global_final_timing_passed', 'physical_capacity_passed',
                    'PSI_eachsource_FINAL_independent_review_passed', 'fresh_ASR_FINAL_review_passed',
                    'IO81_clock18_capture36_macro_INIT_review_passed', 'Stable3s_ordinary_DATA_review_passed', 'Stage_progress32_FINAL_review_passed',
                    'Stage_CDC4_and_held_handshake_review_passed'):
            assert g[key] is True, key
        for value in g['independent_reviews']:
            verify_ref(value)
        assert g['independent_reviews']
        if min(parent['after_rover_reserve'].values()) < 0:
            assert g.get('rover_reserve_release_authorized') is True
        return g, parent
    return g, None


def run_stage(stage, manifest, gate):
    validate_manifest(manifest)
    _, parent = admission(stage, manifest, gate)
    alias = HERE / f'latest_{stage}.json'
    assert not alias.exists(), 'Preserve prior attempt; no implicit overwrite or retry'
    run = Path('C:/Users/Edward/Desktop/FPGA/staged_20261104') / (stage + '_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    run.mkdir(parents=True)
    absolute_project(run)
    config = settings()
    if stage == 'bitgen':
        shutil.copyfile(verify_ref(parent['output']), run / f'{NAME}_pr.db')
        config = config.replace('set run_type syn', 'set run_type phy').replace('set start_step read_design', 'set start_step bitgen').replace('set end_step opt_gate', 'set end_step bitgen')
    (run / 'settings.cfg').write_text(config, encoding='ascii')
    shutil.copyfile(FLOW, run / 'DefaultFlow.tcl')
    marker = 'STABLE3S_' + stage.upper() + '_COMPLETE'
    body = 'source DefaultFlow.tcl\n'
    if stage == 'synth':
        body += 'write_verilog actual_netlist.v\nreport_clock_summary -file clocks.txt\n'
    (run / 'execute.tcl').write_text('if {[catch {\n' + body + '} err]} {puts stderr "STABLE3S_' + stage.upper() + '_FAILED: $err";exit 1}\nputs ' + marker + '\nexit 0\n', encoding='ascii')
    controls = [ref(p) for p in run.iterdir() if p.is_file()] + [ref(gate)]
    rec = {'stage': stage, 'state': 'RUNNING', 'passed': False, 'manifest': ref(manifest),
           'gate': ref(gate), 'source_DB': parent['output'] if parent else None,
           'run': str(run), 'device': False, 'controls': controls}
    write(run / 'receipt.json', rec)
    write(alias, rec)
    start = time.monotonic()
    code = native(run, 1800 if stage == 'synth' else 300)
    log = (run / 'console.log').read_text(errors='replace')
    errors = [x for x in log.splitlines() if re.search(r'\bERROR:|\bFATAL:|STABLE3S_' + stage.upper() + '_FAILED:', x)]
    output = run / (f'{NAME}_gate.db' if stage == 'synth' else f'{NAME}.bit')
    passed = code == 0 and marker in log and not errors and output.is_file()
    commands = re.findall(r'start command "([^"\r\n]+)"', log)
    values = {}
    if stage == 'synth':
        area = run / f'{NAME}_gate.area'
        values = resources(area.read_text(errors='replace')) if area.is_file() else {}
        if passed:
            try:
                ddr = derive_ddr(run / 'actual_netlist.v', HERE)
                rec.update(ddr_group_plan=ref(HERE / 'ddr_group_plan.json'), ddr_group_tcl=ref(HERE / 'ddr_group.tcl'),
                           DDR_semantic_member_count=ddr['member_count'], DDR_semantic_independent_review_pending=True)
            except Exception as exc:
                passed = False
                errors.append('Fresh DDR derivation: ' + repr(exc))
    else:
        forbidden = {'read_verilog', 'elaborate', 'synthesize', 'optimize_rtl', 'optimize_gate', 'place', 'route', 'fix_hold'}
        passed = passed and not ({c.split()[0] for c in commands} & forbidden)
        passed = passed and output.stat().st_size > 1000000 and sha(run / f'{NAME}_pr.db') == parent['output']['sha256']
        passed = passed and f'import_db {NAME}_pr.db' in commands and (run / '.bitgen_param.f').is_file()
    validate_manifest(manifest)
    for value in controls:
        verify_ref(value)
    rec.update(state='NATIVE_COMPLETE_INDEPENDENT_REVIEW_PENDING' if passed else 'FAILED_OR_INCOMPLETE_PRESERVED',
               passed=passed, exit_code=code, elapsed_s=time.monotonic() - start, errors=errors,
               output=ref(output) if output.is_file() else None, log=ref(run / 'console.log'),
               resources=values, actual_commands=commands,
               artifacts={p.name: ref(p) for p in run.iterdir() if p.is_file() and p.suffix in {'.area', '.timing', '.ts', '.adc', '.v', '.txt', '.f'}})
    write(run / 'receipt.json', rec)
    write(alias, rec)
    print(json.dumps({k: rec[k] for k in ('stage', 'state', 'passed', 'run', 'resources', 'errors')}, ensure_ascii=False))
    if not passed:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', action='store_true')
    parser.add_argument('--manifest', type=Path, default=HERE / 'source_freeze.json')
    parser.add_argument('--stage', choices=['synth', 'bitgen'])
    parser.add_argument('--gate', type=Path)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if args.snapshot:
        assert not args.run and not args.stage and not args.gate
        assert not args.manifest.exists(), 'Choose a new manifest; retain old source snapshots'
        write(args.manifest, collect_inputs())
        print(json.dumps({'snapshot': ref(args.manifest), 'root_source_gate_required': True, 'native_run': False, 'device': False}, ensure_ascii=False))
        return
    if not args.stage:
        assert not args.run and not args.gate
        print(json.dumps({'status': 'PLAN_ONLY', 'project': str(P), 'name': NAME,
                          'manifest': str(args.manifest), 'project_present': (P / f'td_project/{NAME}.al').is_file(),
                          'entry_stages': ['synth', 'guided_place', 'guided_route', 'bitgen'],
                          'source_and_stage_gates_required': True, 'native_run': False, 'device': False}, ensure_ascii=False, indent=2))
        return
    assert args.gate, '--gate required'
    validate_manifest(args.manifest)
    admission(args.stage, args.manifest, args.gate)
    if not args.run:
        print(json.dumps({'validated': True, 'stage': args.stage, 'native_run': False, 'device': False}, ensure_ascii=False))
        return
    run_stage(args.stage, args.manifest, args.gate)


if __name__ == '__main__':
    main()
