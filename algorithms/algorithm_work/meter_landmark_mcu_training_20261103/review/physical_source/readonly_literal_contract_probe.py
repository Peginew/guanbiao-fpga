"""Official read_sdc literal registration proof; no placement/route/DB export."""
from pathlib import Path
import datetime,json,re,shutil,sys,time
from audit_synth import TASK,HERE,read,ref,sha,write
from source_helpers import P,NAME,validate_manifest,final_timing
from run_td import native

def main():
    place=read(TASK/'physical/latest_place.json');mapping=read(TASK/'physical/placed_asr_mapping.json')
    assert place['passed']and mapping['placed_DB']==place['output']and len(mapping['pins'])==6
    validate_manifest(TASK/'physical/source_freeze_v2.json');assert sha(place['output']['path'])==place['output']['sha256']
    run=P/f'td_project/{NAME}_Runs'/('readonly_literal_contract_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f'));run.mkdir()
    shutil.copyfile(place['output']['path'],run/'input_place.db')
    asr='set_false_path -through [get_nets {u_hdmi_reset/release_ff[2]}] -to [get_pins {'+' '.join(mapping['pins'])+'}]\n'
    psi='set_max_delay -from [get_regs {u_meter_pair/pipeline/reader/live/return_psi_q8[*] u_meter_pair/pipeline/reader/live/return_psi_valid}] -to [get_clocks {HDMI_PIXEL_CLK}] -datapath_only 7.200\n'
    (run/'asr_literal.sdc').write_text(asr,'ascii');(run/'psi_literal.sdc').write_text(psi,'ascii')
    body='''import_device ph1_35p.db -package PH1P35MDG324 -speed 3
import_db input_place.db
read_sdc asr_literal.sdc
read_sdc psi_literal.sdc
puts {BOTH_LITERAL_SDC_REGISTERED}
report_clock_summary -file initial_clocks.txt
set q8 [get_regs {u_meter_pair/pipeline/reader/live/return_psi_q8[*]}]
set v [get_regs {u_meter_pair/pipeline/reader/live/return_psi_valid}]
set h [get_clocks {HDMI_PIXEL_CLK}]
puts "PSI_ACTUAL_OBJECT_COUNTS q8=[llength $q8] valid=[llength $v] hdmi=[llength $h]"
if {[llength $q8]!=16 || [llength $v]!=1 || [llength $h]!=1} {error {ACTUAL_PSI_COUNTS}}
update_timing -mode manhattan
report_timing_status -file actual.ts
report_timing_summary -ep_num 16 -path_num 1 -file actual.timing
report_timing_exception -file actual_exception.timing
report_timing_ignored -ep_num 32 -path_num 1 -file ignored.timing
set ss [get_regs {u_meter_pair/pipeline/reader/live/return_psi_q8[*] u_meter_pair/pipeline/reader/live/return_psi_valid}]
set i 0
foreach src $ss {
 report_timing_path -from $src -to $h -ep_num 1 -path_num 1 -file [format {psi_%02d.timing} $i]
 incr i
}
puts {LITERAL_CONTRACT_PROBE_COMPLETE}
'''
    (run/'execute.tcl').write_text('if {[catch {\n'+body+'} err]} {puts stderr "LITERAL_PROBE_FAILED: $err";exit 1}\nexit 0\n','ascii')
    start=time.monotonic();code=native(run,90);log=(run/'console.log').read_text(errors='replace')
    commands=re.findall(r'start command "([^"\r\n]+)"',log)
    assert not({s.split()[0]for s in commands}&{'route','place','export_db','synthesize','read_verilog','fix_hold'})
    ext=(run/'actual_exception.timing').read_text()if(run/'actual_exception.timing').exists()else''
    rows=[]
    for line in ext.splitlines():
        m=re.match(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(set_.*)$',line)
        if m and ('return_psi_q8'in line or ('.asr'in line and'release_ff'in line)):
            rows.append(dict(Total=int(m[1]),Dominated=int(m[2]),Shadowed=int(m[3]),Ignored=int(m[4]),command=m[5]))
    psirows=[x for x in rows if'return_psi_q8'in x['command']];asrrows=[x for x in rows if'.asr'in x['command']]
    result=dict(status='READ_SDC_LITERAL_REGISTRATION_REAL_PROBE',run=str(run),code=code,elapsed_s=time.monotonic()-start,
        source_place=place['output'],literal_ASR=ref(run/'asr_literal.sdc'),literal_PSI=ref(run/'psi_literal.sdc'),script=ref(__file__),TCL=ref(run/'execute.tcl'),
        log=ref(run/'console.log'),exception=ref(run/'actual_exception.timing')if(run/'actual_exception.timing').exists()else None,
        actual_rules=rows,actual_timing=final_timing((run/'actual.ts').read_text())if(run/'actual.ts').exists()else{},
        both_registered_before_first_timer=(0<=log.find('BOTH_LITERAL_SDC_REGISTERED')<log.find('start command "start_timer"')),
        no_physical_mutation_or_export=True,commands=commands,device=False)
    result['passed']=code==0 and'LITERAL_CONTRACT_PROBE_COMPLETE'in log and len(psirows)==1 and len(asrrows)==1
    if result['passed']:
        x=psirows[0];result['passed']=x['Total']>=17 and x['Dominated']==x['Total']and x['Shadowed']==x['Ignored']==0
        y=asrrows[0];result['ASR_effective_count']=y['Total'];result['ASR_no_shadow_or_ignore']=y['Dominated']==y['Total']and y['Shadowed']==y['Ignored']==0
        result['passed'] &= result['ASR_no_shadow_or_ignore']and y['Total']>=6
    assert sha(place['output']['path'])==place['output']['sha256']and sha(run/'input_place.db')==place['output']['sha256']
    validate_manifest(TASK/'physical/source_freeze_v2.json');write(HERE/'readonly_literal_contract_probe.json',result)
    print(json.dumps({k:result[k]for k in ['passed','run','elapsed_s','actual_rules','actual_timing','both_registered_before_first_timer']}))
    if not result['passed']:raise SystemExit(1)

if __name__=='__main__':main()
