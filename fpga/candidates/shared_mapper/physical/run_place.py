"""One fresh-SYN, free-UI placement; default PLAN and no TD invocation.

Requires a newly signed place_admission.json binding this runner, the current
SYN/freeze, its actual macro inventory and its freshly derived DDR38 group.
No old layout, hard UI LOC, route, bitgen or device operation is performed.
"""
if not __debug__:
    raise RuntimeError('Verification assertions must remain enabled')

from pathlib import Path
import argparse, datetime, json, re, shutil, time
from source_helpers import P,NAME,read,write,ref,sha,verify_ref,validate_manifest,resources
from mapping_helpers import parse
from run_td import absolute_project,native,LIMITS,RESERVE
from free_ui_place_flow import generated_flow

HERE=Path(__file__).resolve().parent
MANIFEST=HERE/'source_freeze.json'
SYN=HERE/'latest_synth.json'
MACROS=HERE/'macro_names.json'
GATE=HERE/'place_admission.json'
ALIAS=HERE/'latest_place.json'
RUN_ROOT=Path('C:/Users/Edward/Desktop/FPGA/shared_mapper_20261104')
MARKER='STAGED_FREE_UI_PLACE_COMPLETE'
HARD_MACRO_TYPES={'PH1P_PHY_ERAM_V2','PH1P_PHY_DSPSIOU_V2',
                  'PH1P_PHY_DSPMULT_V2','PH1P_PHY_DSPTADD',
                  'PH1P_PHY_PLL_V2','PH1P_PHY_MCU','PH1P_PHY_MIPIIO_RX'}

def synth_inputs():
    validate_manifest(MANIFEST)
    syn=read(SYN)
    assert syn['passed'] is True and syn['stage']=='synth' and syn['exit_code']==0
    assert syn['manifest']==ref(MANIFEST)
    verify_ref(syn['output'])
    for value in syn['artifacts'].values():verify_ref(value)
    group=read(HERE/'ddr_group_plan.json')
    assert group['derived'] is True and group['old_member_names_copied'] is False
    assert group['netlist']==syn['artifacts']['actual_netlist.v']
    assert group['member_count']==len(group['members'])==38
    assert len(set(group['members']))==38
    tcl=(HERE/'ddr_group.tcl').read_text('ascii')
    assert 'ui_macro_anchors' not in tcl
    assert not re.search(r'\blocation\s*=|\bset_clock_assignment\b',tcl)
    assert all(n in tcl for n in group['members'])
    return syn,group

def fresh_inventory(syn):
    cells,_=parse(verify_ref(syn['artifacts']['actual_netlist.v']))
    return [{'name':n.lstrip('\\'),'type':c['type']} for n,c in sorted(cells.items())
            if c['type'] in HARD_MACRO_TYPES]

def prepare_inventory():
    syn,_=synth_inputs()
    assert not MACROS.exists(),'Preserve existing inventory; no implicit replacement'
    rows=fresh_inventory(syn)
    assert rows and len({r['name'] for r in rows})==len(rows)
    write(MACROS,{'status':'FRESH_SYN_HARD_MACRO_NAMES_ONLY_NO_COORDINATES',
      'source_DB':syn['output'],'netlist':syn['artifacts']['actual_netlist.v'],
      'macros':rows,'physical_coordinates_copied':False,'native_run':False,'device':False})
    return rows

def inputs():
    syn,group=synth_inputs()
    inventory=read(MACROS)
    assert inventory['source_DB']==syn['output']
    assert inventory['netlist']==syn['artifacts']['actual_netlist.v']
    assert inventory['physical_coordinates_copied'] is False
    rows=inventory['macros']
    actual={r['name']:r['type'] for r in fresh_inventory(syn)}
    assert rows and len(rows)==len({r['name'] for r in rows})
    for row in rows:
        assert set(row)=={'name','type'} and actual[row['name']]==row['type']
        assert not any(c in row['name'] for c in '{}\r\n')
    refs={'manifest':ref(MANIFEST),'synth_receipt':ref(SYN),'source_DB':syn['output'],
      'ddr_group_plan':ref(HERE/'ddr_group_plan.json'),'ddr_group_tcl':ref(HERE/'ddr_group.tcl'),
      'macro_inventory':ref(MACROS),'runner_sha256':sha(__file__),
      'flow_generator':ref(HERE/'free_ui_place_flow.py')}
    return syn,rows,refs

def admitted(refs):
    if not GATE.exists():return False
    gate=read(GATE)
    assert gate['passed'] is True and gate['stage']=='staged_free_ui_place'
    assert gate['free_UI_no_ten_LOC'] is True
    assert gate['DDR_semantic_member_count']==38
    assert gate['fresh_ASR_PSI17_progress32_CDC4_review_required'] is True
    for k,v in refs.items():assert gate[k]==v,('Place admission mismatch',k)
    for value in gate.get('independent_reviews',[]):verify_ref(value)
    return True

def settings(syn):
    cfg=(Path(syn['run'])/'settings.cfg').read_text('ascii')
    for old,new in [('set run_type syn','set run_type phy'),
                    ('set start_step read_design','set start_step opt_place'),
                    ('set end_step opt_gate','set end_step opt_place')]:
        assert cfg.count(old)==1
        cfg=cfg.replace(old,new,1)
    cfg+='\nset parent '+Path(syn['run']).as_posix()+'\nset sp 1\nset arr_filter false\nset drHoldFix on\n'
    cfg+='set phyWildParams {route effort normal route fix_hold on route timing on route post_route_opt off}\n'
    return cfg

def macro_reports(log,rows):
    result=[];raw=[]
    for row in rows:
        name=row['name'];start='BEGIN_STAGED_POST '+name;end='END_STAGED_POST '+name
        assert log.count(start)==1 and log.count(end)==1,('Missing macro report',name)
        block=log.split(start,1)[1].split(end,1)[0]
        model=re.search(r'\bModel\s*\|\s*(\S+)',block)
        placed=re.search(r'\bIsPlaced\s*\|\s*True\b',block)
        assert model and model[1]==row['type'] and placed,('Incomplete/unplaced macro report',name)
        grid=re.search(r'\bGrid\s*\|\s*col=(\d+)\s+row=(\d+)',block)
        offset=re.search(r'\bOffset\s*\|\s*(\d+)',block)
        item={**row,'is_placed':True,'grid_available':bool(grid),'offset_available':bool(offset)}
        if grid:item.update(col=int(grid[1]),row=int(grid[2]))
        if offset:item['offset']=int(offset[1])
        result.append(item);raw.append(start+'\n'+block+end+'\n')
    return result,'\n'.join(raw)

def run_place(syn,rows,refs,timeout):
    assert admitted(refs),'New independently signed place admission required'
    assert not ALIAS.exists(),'Preserve previous attempt; no implicit retry'
    run=RUN_ROOT/('place_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    run.mkdir(parents=True)
    absolute_project(run)
    (run/'settings.cfg').write_text(settings(syn),'ascii')
    (run/'DefaultFlow.tcl').write_text(generated_flow([r['name'] for r in rows]),'ascii')
    shutil.copyfile(HERE/'ddr_group.tcl',run/'ddr_group.tcl')
    (run/'execute.tcl').write_text('if {[catch {\nsource DefaultFlow.tcl\n} err]} {puts stderr "STAGED_FREE_UI_PLACE_FAILED: $err";exit 1}\nputs {'+MARKER+'}\nexit 0\n','ascii')
    controls=[ref(p) for p in run.iterdir() if p.is_file()]+[ref(GATE)]
    record={'stage':'staged_free_ui_place','state':'RUNNING','passed':False,
      'manifest':refs['manifest'],'source_DB':syn['output'],'synth_receipt':refs['synth_receipt'],
      'gate':ref(GATE),'run':str(run),'controls':controls,'macro_inventory':refs['macro_inventory'],
      'actual_ten_LOC_ADC_not_loaded':False,'fresh_physical_endpoints_required':True,
      'route_or_bitgen_admitted':False,'device':False}
    write(run/'receipt.json',record);write(ALIAS,record)
    start=time.monotonic();code=native(run,timeout)
    log=(run/'console.log').read_text(errors='replace')
    errors=[line for line in log.splitlines() if re.search(r'\bERROR:|\bFATAL:|STAGED_FREE_UI_PLACE_FAILED:',line)]
    commands=re.findall(r'start command "([^"\r\n]+)"',log)
    forbidden={'read_verilog','elaborate','synthesize','optimize_rtl','optimize_gate','route','bitgen','fix_hold'}
    only_place=not any(c.split()[0] in forbidden for c in commands)
    imports=[c for c in commands if c.startswith('import_db ')]
    source_only=len(imports)==1 and imports[0].split(' ',1)[1].strip('{}"').replace('\\','/')==Path(syn['output']['path']).as_posix()
    no_LOC=not any('ui_macro_anchors' in c or c.startswith('set_inst_assignment ') for c in commands)
    output=run/f'{NAME}_place.db';area=run/f'{NAME}_phy.area'
    values=resources(area.read_text(errors='replace')) if area.exists() else {}
    macros_complete=False
    try:
        actual,raw=macro_reports(log,rows)
        write(run/'macro_actual_positions.json',{'macros':actual,'ten_old_LOCs_imposed':False,
          'source_inventory':refs['macro_inventory'],'source_DB':syn['output']})
        (run/'macro_reports.txt').write_text(raw,'utf-8');macros_complete=True
        validate_manifest(MANIFEST)
        assert inputs()[2]==refs
        for value in controls:verify_ref(value)
    except (AssertionError,KeyError,ValueError,OSError) as exc:
        errors.append('Post-place verification: '+repr(exc))
    capacity=bool(values) and all(values[k]<=LIMITS[k] for k in values if k in LIMITS)
    passed=code==0 and MARKER in log and not errors and output.exists() and macros_complete and only_place and source_only and no_LOC and capacity
    record.update(state='NATIVE_FREE_UI_PLACE_COMPLETE_INDEPENDENT_REVIEW_PENDING' if passed else 'FAILED_OR_INCOMPLETE_PRESERVED',
      passed=passed,exit_code=code,elapsed_s=time.monotonic()-start,errors=errors,
      output=ref(output) if output.exists() else None,log=ref(run/'console.log'),
      resources=values,capacity_passed=capacity,
      after_rover_reserve={k:LIMITS[k]-values[k]-v for k,v in RESERVE.items()} if values else {},
      actual_commands=commands,actual_place_only_scope=only_place,actual_same_SYN_only=source_only,
      actual_ten_LOC_ADC_not_loaded=no_LOC,macro_reports_complete=macros_complete,
      artifacts={p.name:ref(p) for p in run.iterdir() if p.is_file() and p.suffix in {'.area','.timing','.adc','.v','.txt','.json','.f'} and p.name not in {'receipt.json','owned_process.json'}})
    write(run/'receipt.json',record);write(ALIAS,record)
    print(json.dumps({k:record[k] for k in ['stage','state','passed','run','resources','errors']},ensure_ascii=False))
    if not passed:raise SystemExit(1)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--prepare-inventory',action='store_true')
    ap.add_argument('--timeout',type=int,default=1800)
    ap.add_argument('--run',action='store_true')
    args=ap.parse_args();assert args.timeout>0
    if args.prepare_inventory:
        assert not args.run
        rows=prepare_inventory()
        print(json.dumps({'status':'FRESH_SYN_INVENTORY_PREPARED_HOST_ONLY','macros':len(rows),'inventory':ref(MACROS),'native_run':False,'device':False}));return
    if not MACROS.exists() and not args.run:
        syn,_=synth_inputs()
        print(json.dumps({'status':'PLAN_ONLY_NEEDS_FRESH_INVENTORY','source_DB':syn['output'],
          'next':'--prepare-inventory (host only) or root supplies same-SYN macro_names.json',
          'native_run':False,'device':False},indent=2));return
    syn,rows,refs=inputs();ready=admitted(refs)
    if not args.run:
        print(json.dumps({'status':'PLAN_ONLY','macro_count':len(rows),'admission_ready':ready,
          'expected_gate':{'passed':True,'stage':'staged_free_ui_place','free_UI_no_ten_LOC':True,
          'DDR_semantic_member_count':38,'fresh_ASR_PSI17_progress32_CDC4_review_required':True,**refs},
          'native_run':False,'device':False},ensure_ascii=False,indent=2));return
    assert ready
    run_place(syn,rows,refs,args.timeout)

if __name__=='__main__':main()
