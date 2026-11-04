"""One authorized same-place Manhattan counterfactual; reports only, no DB export."""
from pathlib import Path
import datetime,json,re,shutil,sys,time
from audit_synth import TASK,HERE,read,ref,sha,write
sys.path.insert(0,str(TASK/'physical'))
from source_helpers import P,NAME,validate_manifest,final_timing
from run_td import absolute_project,native

def pathrow(p):
    t=p.read_text(errors='replace')if p.exists()else''
    return dict(file=ref(p)if p.exists()else None,
        slacks=[float(x)for x in re.findall(r'^Slack\s*:\s*([-0-9.]+)ns',t,re.M)],
        begin=re.findall(r'^Begin Point.*$',t,re.M),end=re.findall(r'^End Point.*$',t,re.M),
        budget=re.findall(r'^Budget.*$',t,re.M),data_path=re.findall(r'^Data Path Delay.*$',t,re.M))

def main():
    place=read(TASK/'physical/latest_place.json');assert place['passed']
    validate_manifest(TASK/'physical/source_freeze_v2.json')
    for x in[place['output'],place['ASR_overlay']]:assert sha(x['path'])==x['sha256']
    run=P/f'td_project/{NAME}_Runs'/('readonly_psi_place_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    run.mkdir();absolute_project(run);shutil.copyfile(place['output']['path'],run/'input_place.db')
    shutil.copyfile(place['ASR_overlay']['path'],run/'serial_reset_exact_overlay.tcl')
    body=f'''import_device ph1_35p.db -package PH1P35MDG324 -speed 3
import_db input_place.db
report_clock_summary -file initial_clocks.txt
source serial_reset_exact_overlay.tcl
set q8 [get_regs {{u_meter_pair/pipeline/reader/live/return_psi_q8[*]}}]
set valid [get_regs {{u_meter_pair/pipeline/reader/live/return_psi_valid}}]
set target [get_clocks {{HDMI_PIXEL_CLK}}]
puts "PSI_DIAGNOSTIC_COUNTS q8=[llength $q8] valid=[llength $valid] clock=[llength $target]"
if {{[llength $q8]!=16 || [llength $valid]!=1 || [llength $target]!=1}} {{error {{PSI17_COUNT}}}}
set sources [get_regs {{u_meter_pair/pipeline/reader/live/return_psi_q8[*] u_meter_pair/pipeline/reader/live/return_psi_valid}}]
if {{[llength $sources]!=17}} {{error {{PSI17_JOINT_COUNT}}}}
set f [open endpoints.txt w];puts $f "q8=$q8";puts $f "valid=$valid";puts $f "target=$target";close $f
update_timing -mode manhattan
report_timing_status -file before.ts
report_timing_summary -ep_num 16 -path_num 1 -file before.timing
report_timing_exception -file before_exception.timing
set index 0
foreach reg $sources {{
 report_timing_path -from $reg -to $target -ep_num 1 -path_num 1 -file [format {{before_psi_%02d.timing}} $index]
 incr index
}}
set_max_delay -from [get_regs {{u_meter_pair/pipeline/reader/live/return_psi_q8[*] u_meter_pair/pipeline/reader/live/return_psi_valid}}] -to [get_clocks {{HDMI_PIXEL_CLK}}] -datapath_only 7.200
puts {{PSI_PLACE_CORRECT_BUDGET_APPLIED}}
update_timing -mode manhattan
report_timing_status -file after.ts
report_timing_summary -ep_num 16 -path_num 1 -file after.timing
report_timing_exception -file after_exception.timing
set index 0
foreach reg $sources {{
 report_timing_path -from $reg -to $target -ep_num 1 -path_num 1 -file [format {{after_psi_%02d.timing}} $index]
 incr index
}}
puts {{PSI_PLACE_DIAGNOSTIC_COMPLETE}}
'''
    script='if {[catch {\n'+body+'} err]} {puts stderr "PSI_PLACE_DIAGNOSTIC_FAILED: $err";exit 1}\nexit 0\n'
    (run/'execute.tcl').write_text(script,'ascii');started=time.monotonic();code=native(run,90)
    log=(run/'console.log').read_text(errors='replace')
    commands=re.findall(r'start command "([^"\r\n]+)"',log)
    forbidden={'route','place','synthesize','export_db','read_verilog','fix_hold','elaborate'}
    assert not {x.split()[0]for x in commands}&forbidden
    result=dict(status='COMPLETED_MANHATTAN_ONLY_NOT_ROUTED_PROOF',returncode=code,elapsed_s=time.monotonic()-started,
        source_place=place['output'],source_place_netlist=place['artifacts']['actual_netlist.v'],source_freeze=place['manifest'],
        run=str(run),script=ref(__file__),executed_TCL=ref(run/'execute.tcl'),log=ref(run/'console.log'),
        no_physical_or_source_or_DB_mutation_commands=True,commands=commands,
        before=final_timing((run/'before.ts').read_text())if(run/'before.ts').exists()else{},after=final_timing((run/'after.ts').read_text())if(run/'after.ts').exists()else{},
        before_psi=[pathrow(run/f'before_psi_{i:02d}.timing')for i in range(17)],
        after_psi=[pathrow(run/f'after_psi_{i:02d}.timing')for i in range(17)],
        actual_routed9critical_endpoints_identified=False,device=False)
    effective=(run/'after_exception.timing').read_text()if(run/'after_exception.timing').exists()else''
    result['new_effective_PSI_rule_present']='return_psi_q8'in effective and'return_psi_valid'in effective
    result['passed']=code==0 and'PSI_PLACE_DIAGNOSTIC_COMPLETE'in log and'PSI_PLACE_DIAGNOSTIC_FAILED'not in log and result['new_effective_PSI_rule_present']
    assert sha(place['output']['path'])==place['output']['sha256']
    assert sha(run/'input_place.db')==place['output']['sha256']
    validate_manifest(TASK/'physical/source_freeze_v2.json')
    write(HERE/'readonly_psi_place_diagnostic.json',result)
    print(json.dumps({k:result[k]for k in ['passed','run','elapsed_s','before','after']}))
    if not result['passed']:raise SystemExit(1)

if __name__=='__main__':main()
