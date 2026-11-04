"""Check this UI candidate's final routed capture cone. No TD/device actions."""
from pathlib import Path
import argparse,hashlib,json,re,shutil,subprocess,sys,tempfile,time

HERE=Path(__file__).resolve().parent
TASK=HERE.parent.parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
ref=lambda p:dict(path=str(Path(p).resolve()),sha256=sha(p))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--route-receipt',type=Path,default=TASK/'physical/latest_route.json')
    ap.add_argument('--run',action='store_true')
    a=ap.parse_args()
    route=json.loads(a.route_receipt.read_text(encoding='utf-8'))
    if not a.run:
        print(json.dumps(dict(route_state=route.get('state'),route_passed=route.get('passed'),actual_simulation=False,device=False)))
        return
    assert route['stage']=='route' and route['passed'] and route['global_final_timing_passed']
    freeze=TASK/'physical/source_freeze_v2.json'
    assert sha(freeze)==route['manifest']['sha256']
    db=Path(route['output']['path']);net=Path(route['artifacts']['actual_netlist.v']['path'])
    assert sha(db)==route['output']['sha256'] and sha(net)==route['artifacts']['actual_netlist.v']['sha256']
    syn=TASK/'review/physical_source/capture_LANDMARK_SYN_gate.json'
    sg=json.loads(syn.read_text(encoding='utf-8'))
    assert sg['passed'] and sg['source_manifest_sha256']==sha(freeze)
    run=Path(tempfile.mkdtemp(prefix='gb_ui_ref_capture_final_'))
    shutil.copy2(net,run/'actual_netlist.v')
    (run/'modelsim.ini').write_text('[Library]\nwork = work\n[vsim]\n',encoding='ascii')
    extractor=HERE/'extract_routed_capture.py'
    ms=Path('C:/modeltech64_10.1c/win64')
    sim=Path('C:/Anlogic/TD_6.2.1_Engineer_6.2.168.116/sim_release')
    models=[sim/'common/al_phy_glbl.v',sim/'ph1p/ph1p_phy_gsr.v',sim/'ph1p/ph1p_phy_lslice.v']
    commands=[('extract',[sys.executable,'-X','utf8',str(extractor),str(run),str(db)]),
      ('vlib',[str(ms/'vlib.exe'),'work']),
      ('vlog',[str(ms/'vlog.exe'),'-sv',*map(str,models),'cb33_guard_cone.sv']),
      ('vsim',[str(ms/'vsim.exe'),'-c','-modelsimini','modelsim.ini','-novopt','-t','1ps',
        'work.tb_cb33_routed_cone','work.glbl','work.PH1P_PHY_GSR','-do',
        'onbreak {quit -code 3};onerror {quit -code 4};run -all;quit -code 0'])]
    steps=[]
    for label,cmd in commands:
        begin=time.monotonic()
        with(run/(label+'.log')).open('wb')as f:
            p=subprocess.run(cmd,cwd=run,stdout=f,stderr=subprocess.STDOUT,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
        step=dict(command=cmd,exit_code=p.returncode,elapsed_s=time.monotonic()-begin,log=ref(run/(label+'.log')))
        steps.append(step);print(json.dumps(dict(step=label,exit_code=p.returncode,elapsed_s=step['elapsed_s'])),flush=True)
        if p.returncode:break
    text=(run/'vsim.log').read_text(encoding='utf-8',errors='replace')if(run/'vsim.log').exists()else''
    cfg=json.loads((run/'cb33_guard_config.json').read_text(encoding='utf-8'))if(run/'cb33_guard_config.json').exists()else None
    passed=len(steps)==4 and all(s['exit_code']==0 for s in steps) and 'CB33_ROUTED_GUARD_END' in text and 'checks=36 failures=0' in text and not re.search(r'\*\* (Error|Fatal)',text)
    assert sha(db)==route['output']['sha256'] and sha(net)==route['artifacts']['actual_netlist.v']['sha256']
    rec=dict(passed=passed,status='PASS_ACTUAL_UIREF_RECOVERY_ROUTED_CAPTURE_PRIMITIVES36'if passed else'FAIL_PRESERVED',
      route_receipt=ref(a.route_receipt),ROUTED_DB=route['output'],actual_netlist=ref(net),source_freeze=ref(freeze),
      SYN_capture_reference=ref(syn),frontier_reference=ref(TASK/'review/physical_source/frontier_inspection.json'),
      extractor=ref(extractor),run=str(run),steps=steps,official_models={str(p):sha(p)for p in models},
      config=ref(run/'cb33_guard_config.json')if cfg else None,TB=ref(run/'cb33_guard_cone.sv')if cfg else None,
      actual_cell_count=len(cfg['selected'])if cfg else None,checks=36 if passed else None,
      functional_cuts=cfg['cuts']if cfg else None,external_functional_cuts=[n for n in cfg['cuts']if not n.startswith('\\u_meter_pair/pipeline/reader/live/capture/')]if cfg else None,
      events=[s for s in text.splitlines()if any(x in s for x in ['GUARD_END','mismatch','Error','Fatal'])],
      scope='Actual packed PH1P badD/Q and diag7 with explicit same-candidate register frontier, four strides and terminal/short/long counts. Not a full frame/CNN/board proof.',
      source_modified=False,route_rerun=False,device=False)
    (HERE/'capture_final_gate.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=passed,run=str(run),gate=str(HERE/'capture_final_gate.json'),sha256=sha(HERE/'capture_final_gate.json')),ensure_ascii=False))
    if not passed:raise SystemExit(1)

if __name__=='__main__':main()
