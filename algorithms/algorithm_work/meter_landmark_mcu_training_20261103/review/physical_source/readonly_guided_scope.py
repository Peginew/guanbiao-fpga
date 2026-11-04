"""One necessary, read-only FINAL clock/ordinary-path query of accepted DB.

No place/route/export/bitgen/device calls. Default only describes readiness.
"""
from pathlib import Path
import argparse,datetime,json,re,shutil,sys,time
from audit_synth import TASK,HERE,BASE,read,ref,sha,write
sys.path.insert(0,str(TASK/'physical'))
from run_td import P,NAME,absolute_project,native
from source_helpers import final_timing


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',action='store_true');ap.add_argument('--existing-run',type=Path);a=ap.parse_args()
    rp=TASK/'physical/latest_guided_route.json';route=read(rp)
    if a.existing_run:
        finish_existing(route,rp,a.existing_run,None);return
    if not a.run:
        print(json.dumps(dict(route_state=route['state'],route_passed=route['passed'],native_query=False,device=False)));return
    assert route['passed']and route['global_final_timing_passed']and route['exit_code']==0
    assert sha(route['output']['path'])==route['output']['sha256']
    run=P/f'td_project/{NAME}_Runs'/('guided_final_scope_readonly_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    run.mkdir();absolute_project(run);shutil.copyfile(route['output']['path'],run/'actual.db')
    tcl='''import_device ph1_35p.db -package PH1P35MDG324 -speed 3
import_db actual.db
report_clock_summary -file initial_clocks.txt
update_timing -mode final
set cc [get_clocks *]
set f [open clocks_all.txt w];puts $f [list CLOCKS [llength $cc] $cc];close $f
if {[llength $cc]!=18} {error {GUIDED_CLOCKS_NOT18}}
'''
    for stage in range(3):
        pattern=' '.join('u_hdmi_tx/u_hdmi2phy_wrapper/u'+str(lane)+'_lane_lvds_8_1/u_serial_reset/release_ff['+str(stage)+']'for lane in range(4))
        tcl+='set sr'+str(stage)+' [get_regs {'+pattern+'}]\nif {[llength $sr'+str(stage)+']!=4} {error {GUIDED_SERIAL_STAGE_COUNT}}\n'
    tcl+='''report_timing_path -from $sr0 -to $sr1 -ep_num 16 -path_num 1 -file serial_stage01_DATA.timing
report_timing_path -from $sr1 -to $sr2 -ep_num 16 -path_num 1 -file serial_stage12_DATA.timing
report_timing_path -from $sr2 -ep_num 32 -path_num 1 -file serial_release_consumers.timing
report_timing_path -from [get_regs {u_hdmi_tx/u_hdmi2phy_wrapper/*/S_odd_even*}] -ep_num 16 -path_num 1 -file serial_odd_even.timing
set r0 [get_regs {u_meter_pair/reference_control/switch_sync0[0] u_meter_pair/reference_control/switch_sync0[1]}]
set r1 [get_regs {u_meter_pair/reference_control/switch_sync1[0] u_meter_pair/reference_control/switch_sync1[1]}]
if {[llength $r0]!=2||[llength $r1]!=2} {error {GUIDED_REF_STAGE_COUNT}}
report_timing_path -from $r0 -to $r1 -ep_num 16 -path_num 1 -file REF_stage01_DATA.timing
report_timing_path -from $r1 -ep_num 32 -path_num 1 -file REF_consumers.timing
report_timing_path -from [get_clocks {u_ph1p35_324_ddr_wrapper/u_ddr2/usr_clk}] -to [get_clocks {u_ph1p35_324_ddr_wrapper/u_ddr2/usr_clk}] -ep_num 32 -path_num 1 -file DDR_ordinary_DATA.timing
report_timing_status -file actual_FINAL.ts
report_timing_ignored -ep_num 32 -path_num 1 -file actual_ignored.timing
report_route_status -drc
puts {GUIDED_READONLY_FINAL_SCOPE_COMPLETE}
'''
    (run/'execute.tcl').write_text('if {[catch {\n'+tcl+'} err]} {puts stderr "GUIDED_READONLY_SCOPE_FAILED: $err";exit 1}\nexit 0\n',encoding='ascii')
    started=time.monotonic();code=native(run,180);log=(run/'console.log').read_text(errors='replace')
    assert code==0 and not re.search(r'\bERROR:|\bFATAL:|GUIDED_READONLY_SCOPE_FAILED:',log),log[-3000:]
    assert 'GUIDED_READONLY_FINAL_SCOPE_COMPLETE'in log and'No multi-drive.'in log and'No abnormal timing path.'in log
    finish_existing(route,rp,run,time.monotonic()-started)


def finish_existing(route,rp,run,elapsed):
    """Host-only completion; no repeated TD call after unsupported DDR query."""
    assert route['passed']and route['global_final_timing_passed']and route['exit_code']==0
    log=(run/'console.log').read_text(errors='replace')
    assert 'GUIDED_READONLY_FINAL_SCOPE_COMPLETE'in log and not re.search(r'\bERROR:|\bFATAL:|GUIDED_READONLY_SCOPE_FAILED:',log)
    assert 'No multi-drive.'in log and'No abnormal timing path.'in log
    commands=re.findall(r'start command "([^"\r\n]+)"',log)
    assert not any(x.split()[0]in{'place','route','fix_hold','bitgen','export_db','read_sdc'}for x in commands)
    clocks=(run/'clocks_all.txt').read_text().strip();m=re.fullmatch(r'CLOCKS 18 \{([^}]+)\}',clocks);assert m
    names=m[1].split();assert len(names)==len(set(names))==18
    old=read(BASE/'review/final_physical/native_scope_review.json')
    oldtext=Path(old['files']['clocks_all.txt']['path']).read_text().strip();oldm=re.fullmatch(r'CLOCKS 18 \{([^}]+)\}',oldtext)
    assert oldm and set(names)==set(oldm[1].split()),('clock identities',names)
    status=final_timing((run/'actual_FINAL.ts').read_text());assert len(status)==4 and min(status.values())>=0 and status['STNS']==status['HTNS']==0
    paths={}
    checks={'serial_stage01_DATA.timing':'/u_serial_reset/','serial_stage12_DATA.timing':'/u_serial_reset/',
        'serial_release_consumers.timing':'u_hdmi_tx/','serial_odd_even.timing':'S_odd_even',
        'REF_stage01_DATA.timing':'reference_control/','REF_consumers.timing':'reference_control/'}
    for name,token in checks.items():
        text=(run/name).read_text(errors='replace')
        blocks=re.findall(r'^Slack\s*:\s*(-?[0-9.]+)ns\s*\nBegin Point\s*:\s*([^\n]+)\nEnd Point\s*:\s*([^\n]+)',text,re.M)
        assert blocks and all(float(x[0])>=0 for x in blocks),('empty/negative ordinary path',name)
        assert all(token in x[1]for x in blocks),('wrong filter source',name,blocks[:1])
        if name.startswith('serial_stage'):assert all('/u_serial_reset/'in x[2]for x in blocks)
        paths[name]=dict(actual_paths=len(blocks),minimum_slack_ns=min(float(x[0])for x in blocks),report=ref(run/name))
    # report_timing_path does not accept clock handles as -from targets in
    # this TD version. Preserve that unsupported query, and use the existing
    # same-DB GLOBAL FINAL ordinary-path report; never treat no file as PASS.
    ddr_report=Path(route['run'])/'reader_landmark_pr.timing'
    ddr_text=ddr_report.read_text(errors='replace')
    ddr_all=re.findall(r'^Slack\s*:\s*(-?[0-9.]+)ns\s*\nBegin Point\s*:\s*([^\n]+)\nEnd Point\s*:\s*([^\n]+)',ddr_text,re.M)
    ddr=[x for x in ddr_all if 'clock u_ph1p35_324_ddr_wrapper/u_ddr2/usr_clk 'in x[1]and'clock u_ph1p35_324_ddr_wrapper/u_ddr2/usr_clk 'in x[2]]
    assert ddr and all(float(x[0])>=0 and'period=7.500000'in x[1]and'period=7.500000'in x[2]for x in ddr)
    paths['DDR_ordinary_actual_FINAL']=dict(actual_paths=len(ddr),minimum_slack_ns=min(float(x[0])for x in ddr),report=ref(ddr_report),
        scope='Normal (not SMD) same usr_clk 7.5ns clock paths from complete native FINAL report')
    assert sha(route['output']['path'])==route['output']['sha256']and sha(run/'actual.db')==route['output']['sha256']
    out=dict(passed=True,status='PASS_ACTUAL_GUIDED_FINAL_ALL18_CLOCKS_AND_ORDINARY_DATA',route=ref(rp),routed_DB=route['output'],auditor=ref(__file__),run=str(run),
        actual_readonly_elapsed_s=elapsed,host_only_analysis_of_existing_native_reports=elapsed is None,
        unsupported_get_clocks_from_query_preserved=True,DDR_evidence_from_existing_same_DB_global_FINAL=True,
        clock_count=18,clock_identities=names,clock_identity_reference_only=old['files']['clocks_all.txt'],
        ordinary_data_and_consumers=paths,FINAL=status,DRC_passed=True,execute=ref(run/'execute.tcl'),log=ref(run/'console.log'),
        no_constraint_or_DB_modification=True,no_route_or_device_actions=True)
    write(HERE/'guided_native_scope_review.json',out)
    print(json.dumps(dict(passed=True,clock_count=18,ordinary_reports=len(paths),review=ref(HERE/'guided_native_scope_review.json')),ensure_ascii=False))


if __name__=='__main__':main()
