"""Fresh staged-display route body and runner; default PLAN, no native action."""
if not __debug__:
    raise RuntimeError('Verification assertions must remain enabled')

from pathlib import Path
import argparse,datetime,json,re,shutil,time
from source_helpers import NAME,read,write,ref,sha,verify_ref,validate_manifest,resources,final_timing
from run_td import absolute_project,native,final_reports,LIMITS,RESERVE

HERE=Path(__file__).resolve().parent
PLACE=HERE/'latest_place.json'
GATE=HERE/'route_admission.json'
ALIAS=HERE/'latest_route.json'
EXPECTED=HERE/'expected_rules.json'
MARKER='STAGED_LITERAL_CONTRACT_FINAL_COMPLETE'
LITERALS=['asr_literal.sdc','PSI17_exact_Q_candidate.sdc','progress32_exact_Q_candidate.sdc',
          'progressCtrl2_exact_QD_candidate.sdc','diagnostic4_exact_QD_candidate.sdc']

def brace(value):
    assert '\n' not in value and '\r' not in value and '\\' not in value
    assert value.count('{')==value.count('}')
    return '{'+value+'}'

def verify_tcl(expected):
    """Compare every exact command and its four actual summary counts."""
    assert len(expected['exact_SMD_rules'])==8
    assert sorted(r['counts'][0] for r in expected['exact_SMD_rules'])==[1,1,1,1,1,1,17,32]
    assert all(r['mode']=='Max' and r['counts']==[r['counts'][0],r['counts'][0],0,0] for r in expected['exact_SMD_rules'])
    assert len(expected['replaced_logical_rules'])==4 and len(expected['ASR_rules'])==2
    text=r'''
proc staged_summary_rows {path} {
 set f [open $path r];set raw [read $f];close $f
 set table [dict create];set mode {}
 foreach line [split $raw "\n"] {
  set head [string trim $line]
  if {$head eq {Max Check}} {set mode Max}
  if {$head eq {Min Check}} {set mode Min}
  if {[regexp {^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(set_(?:max_delay|false_path).*)$} $line -> total active shadow ignored cmd]} {
   dict lappend table [list $mode [string trim $cmd]] [list $total $active $shadow $ignored]
  }
 }
 return $table
}
proc staged_require_row {table mode counts command label} {
 set key [list $mode $command]
 if {![dict exists $table $key]} {error "STAGED_RULE_MISSING $label $mode"}
 set rows [dict get $table $key]
 if {[llength $rows]!=1 || [lindex $rows 0] ne $counts} {error "STAGED_RULE_COUNTS $label expected=$counts actual=$rows"}
}
proc staged_verify_tables {exception_file ignored_file phase} {
 set smd [staged_summary_rows $exception_file]
 set asr [staged_summary_rows $ignored_file]
'''
    for group,var in [('exact_SMD_rules','smd'),('replaced_logical_rules','smd'),('ASR_rules','asr')]:
        for i,row in enumerate(expected[group]):
            text+=' staged_require_row $'+var+' '+brace(row['mode'])+' '+brace(' '.join(map(str,row['counts'])))+' '+brace(row['command'])+' '+brace(group+'_'+str(i))+'\n'
    return text+' puts "STAGED_TABLES_PROVEN_$phase"\n}\n'

def route_body(expected):
    text='import_device ph1_35p.db -package PH1P35MDG324 -speed 3\nimport_db input_place.db\n'
    text+=''.join('read_sdc '+name+'\n' for name in LITERALS)
    text+='puts {STAGED_LITERAL_REGISTERED_BEFORE_FIRST_TIMER}\n'
    text+=verify_tcl(expected)
    text+='''report_clock_summary -file initial_clocks.txt
update_timing -mode manhattan
report_timing_exception -ep_num 256 -path_num 1 -file pre_contract_exception.timing
report_timing_ignored -ep_num 64 -path_num 1 -file pre_contract_ignored.timing
staged_verify_tables pre_contract_exception.timing pre_contract_ignored.timing PRE
set_param route effort normal
set_param route fix_hold on
set_param route timing on
set_param route post_route_opt off
commit_param -step route
route
update_timing -mode final
report_timing_status -file before_hold.ts
set f [open before_hold.ts r];set ts [read $f];close $f
if {![regexp {HWNS:\\s*(-?[0-9.]+)ns} $ts -> h]} {error {HOLD_STATUS_UNPARSED}}
if {$h < 0.0} {fix_hold;update_timing -mode final}
'''
    text+=final_reports()
    text+='''report_timing_exception -ep_num 256 -path_num 1 -file all_held_data.timing
report_timing_ignored -ep_num 64 -path_num 1 -file all_ignored_data.timing
staged_verify_tables all_held_data.timing all_ignored_data.timing FINAL
report_clock_intersection -file clock_intersection.txt
puts {STAGED_LITERAL_CONTRACT_FINAL_COMPLETE}
'''
    return text

def summary_rows(text):
    result=[];mode=None
    for line in text.splitlines():
        if line.strip() in ['Max Check','Min Check']:mode=line.strip().split()[0]
        m=re.match(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(set_(?:max_delay|false_path).*)$',line)
        if m:result.append({'mode':mode,'counts':[int(x) for x in m.groups()[:4]],'command':m[5].strip()})
    return result

def verify_summary(exception,ignored,expected):
    smd=summary_rows(exception);asr=summary_rows(ignored);checked=[]
    for group,rows in [('exact_SMD_rules',smd),('replaced_logical_rules',smd),('ASR_rules',asr)]:
        for want in expected[group]:
            found=[r for r in rows if (r['mode'],r['command'])==(want['mode'],want['command'])]
            checked.append({'group':group,'expected':want,'actual':found,'passed':len(found)==1 and found[0]['counts']==want['counts']})
    return all(r['passed'] for r in checked),checked

def overflow_result(log):
    rows=re.findall(r'over\s+cnt\s*=\s*(\d+)\([^)]*\),\s*over\s*=\s*(\d+),\s*worst\s*=\s*(\d+)',log)
    return bool(rows) and tuple(map(int,rows[-1]))==(0,0,0),tuple(map(int,rows[-1])) if rows else None

def inputs():
    manifest=HERE/'source_freeze.json';validate_manifest(manifest)
    place=read(PLACE)
    assert place['passed'] and place['exit_code']==0 and place['manifest']==ref(manifest)
    assert place['actual_place_only_scope'] and place['actual_same_SYN_only'] and place['actual_ten_LOC_ADC_not_loaded']
    verify_ref(place['output'])
    for value in place['artifacts'].values():verify_ref(value)
    expected=read(EXPECTED);assert expected['source_DB']==place['output']
    probe=read(verify_ref(expected['probe']))
    assert probe['completed'] and probe['exit_code']==0 and probe['source_DB']==place['output']
    assert probe['route'] is False and probe['export_DB'] is False
    assert verify_summary(verify_ref(probe['artifacts']['pre_contract_exception.timing']).read_text(),
                          verify_ref(probe['artifacts']['pre_contract_ignored.timing']).read_text(),expected)[0]
    identity=HERE/'endpoints/fresh_identity.json'
    assert read(identity)['source_DB']==place['output']
    literal_paths={n:HERE/n if n=='asr_literal.sdc' else HERE/'endpoints'/n for n in LITERALS}
    for name,path in literal_paths.items():
        matches=[r for r in probe['controls'] if Path(r['path']).name==name]
        assert len(matches)==1 and matches[0]['sha256']==sha(path),(name,matches)
        text=path.read_text('ascii').strip()
        assert text.startswith('set_false_path ' if name=='asr_literal.sdc' else 'set_max_delay ')
        assert name=='asr_literal.sdc' or ('get_regs' not in text and 'set_false_path' not in text)
    refs={'manifest':ref(manifest),'place_receipt':ref(PLACE),'source_DB':place['output'],
      'expected_rules':ref(EXPECTED),'native_probe':expected['probe'],'endpoint_identity':ref(identity),
      'ASR_mapping':ref(HERE/'placed_asr_mapping.json'),'runner_sha256':sha(__file__),
      'literal_files':{n:ref(p) for n,p in literal_paths.items()}}
    return place,expected,refs

def admission(refs):
    if not GATE.exists():return None
    gate=read(GATE)
    assert gate['passed'] is True and gate['stage']=='staged_literal_route'
    for k,v in refs.items():assert gate[k]==v,('Route admission mismatch',k)
    assert gate['pure_literal_before_first_timer'] is True
    assert gate['source_and_physical_entities_review_passed'] is True
    assert gate['held_control_CDC_review_passed'] is True
    review=read(verify_ref(gate['probe_effective_review']));assert review['passed'] is True
    assert gate['independent_reviews']
    for r in gate['independent_reviews']:verify_ref(r)
    return gate

def run_route(place,expected,refs,gate,timeout):
    assert not ALIAS.exists(),'Preserve previous route attempt; no implicit retry'
    run=Path('C:/Users/Edward/Desktop/FPGA/staged_20261104')/('route_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    run.mkdir(parents=True);absolute_project(run)
    shutil.copyfile(verify_ref(place['output']),run/'input_place.db')
    for name,value in refs['literal_files'].items():shutil.copyfile(verify_ref(value),run/name)
    script='if {[catch {\n'+route_body(expected)+'} err]} {puts stderr "STAGED_ROUTE_FAILED: $err";exit 1}\nexit 0\n'
    (run/'execute.tcl').write_text(script,'ascii')
    controls=[ref(p) for p in run.iterdir() if p.is_file()]+[ref(__file__),ref(GATE),ref(PLACE),refs['expected_rules'],refs['endpoint_identity'],refs['ASR_mapping'],gate['probe_effective_review']]+gate['independent_reviews']
    rec={'stage':'route','state':'RUNNING','passed':False,'device':False,
      'manifest':refs['manifest'],'source_DB':place['output'],'place_receipt':ref(PLACE),
      'gate':ref(GATE),'run':str(run),'controls':controls,'expected_rules':refs['expected_rules'],
      'bitgen_admitted':False,'eachsource_FINAL_independent_review_passed':False,
      'pure_literal_before_first_timer_required':True,'source_functionality_changed':False}
    write(run/'receipt.json',rec);write(ALIAS,rec)
    start=time.monotonic();code=native(run,timeout)
    log=(run/'console.log').read_text(errors='replace')
    errors=[s for s in log.splitlines() if re.search(r'\bERROR:|\bFATAL:|STAGED_ROUTE_FAILED:',s)]
    def txt(name):
        p=run/name
        return p.read_text(errors='replace') if p.exists() else ''
    values=resources(txt(f'{NAME}_phy.area'));timing=final_timing(txt(f'{NAME}_phy.ts'))
    timing_ok=len(timing)==4 and timing['SWNS']>=0 and timing['HWNS']>=0 and timing['STNS']==timing['HTNS']==0
    capacity=all(k in values and values[k]<=v for k,v in LIMITS.items()) and values.get('Slice_is_SYN_estimate') is False
    pre_ok,pre_checks=verify_summary(txt('pre_contract_exception.timing'),txt('pre_contract_ignored.timing'),expected)
    final_ok,final_checks=verify_summary(txt('all_held_data.timing'),txt('all_ignored_data.timing'),expected)
    registered=log.find('STAGED_LITERAL_REGISTERED_BEFORE_FIRST_TIMER')
    timer=log.find('start command "start_timer"');proven=log.find('STAGED_TABLES_PROVEN_PRE');routed=log.find('start command "route"')
    order=0<=registered<timer<proven<routed
    commands=re.findall(r'start command "([^"\r\n]+)"',log)
    forbidden={'read_verilog','elaborate','synthesize','optimize_rtl','optimize_gate','place','bitgen'}
    scope=not any(c.split()[0] in forbidden for c in commands)
    imports=[c for c in commands if c.startswith('import_db ')]
    source_only=imports==['import_db input_place.db'] and sha(run/'input_place.db')==place['output']['sha256']
    drc='No multi-drive.' in log and 'No abnormal timing path.' in log
    zero_overflow,last_overflow=overflow_result(log)
    output=run/f'{NAME}_pr.db'
    bindings_ok=True
    try:
        validate_manifest(HERE/'source_freeze.json')
        assert inputs()[2]==refs
        assert admission(refs)==gate
        for value in controls:verify_ref(value)
    except (AssertionError,KeyError,ValueError,OSError) as exc:
        bindings_ok=False;errors.append('Post-route identity check: '+repr(exc))
    passed=code==0 and not errors and output.exists() and MARKER in log and timing_ok and capacity and pre_ok and final_ok and order and scope and source_only and drc and zero_overflow and bindings_ok
    rec.update(state='ACTUAL_STAGED_ROUTE_FINAL_PASS_INDEPENDENT_REVIEW_PENDING' if passed else 'FAILED_OR_INCOMPLETE_PRESERVED',
      passed=passed,exit_code=code,elapsed_s=time.monotonic()-start,errors=errors,
      output=ref(output) if output.exists() else None,log=ref(run/'console.log'),
      resources=values,FINAL=timing,global_final_timing_passed=timing_ok,physical_capacity_passed=capacity,
      pre_rule_tables_passed=pre_ok,final_rule_tables_passed=final_ok,pre_rule_checks=pre_checks,final_rule_checks=final_checks,
      literal_contracts_before_first_timer_and_pre_route=order,DRC_messages_passed=drc,
      actual_zero_overflow_last_table=zero_overflow,last_overflow_counts=last_overflow,
      actual_route_only_scope=scope,actual_same_source_DB=source_only,actual_commands=commands,
      after_rover_reserve={k:LIMITS[k]-values[k]-v for k,v in RESERVE.items()} if all(k in values for k in RESERVE) else {},
      artifacts={p.name:ref(p) for p in run.iterdir() if p.is_file() and p.suffix in {'.area','.timing','.ts','.adc','.v','.txt','.sdc'}})
    write(run/'receipt.json',rec);write(ALIAS,rec)
    print(json.dumps({k:rec[k] for k in ['state','passed','run','resources','FINAL','pre_rule_tables_passed','final_rule_tables_passed','last_overflow_counts','errors']},ensure_ascii=False))
    if not passed:raise SystemExit(1)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run',action='store_true');ap.add_argument('--timeout',type=int,default=7200)
    args=ap.parse_args();assert args.timeout>0
    place,expected,refs=inputs();gate=admission(refs)
    if not args.run:
        print(json.dumps({'status':'PLAN_ONLY','source_DB':place['output'],'admission_ready':gate is not None,
          'expected_gate':{'passed':True,'stage':'staged_literal_route',**refs,'pure_literal_before_first_timer':True,
          'source_and_physical_entities_review_passed':True,'held_control_CDC_review_passed':True,
          'probe_effective_review':'ROOT_BINDS_ACTUAL_INDEPENDENT_PASS','independent_reviews':[]},
          'timeout':args.timeout,'native_run':False,'device':False},ensure_ascii=False,indent=2));return
    assert gate is not None
    run_route(place,expected,refs,gate,args.timeout)

if __name__=='__main__':main()
