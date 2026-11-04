"""Six finite, actual merged-source ModelSim suites; no TD/device calls.

Old benches are stimulus templates only. Every DUT file comes from the new
Stable3s+PSI engineering tree, hashed before/after real compilation/simulation.
"""
from pathlib import Path
import argparse,datetime,hashlib,json,os,re,shutil,subprocess,tempfile,time

TASK=Path(__file__).resolve().parent.parent
ROOT=Path('C:/Users/Edward/Documents/ChatGPT/嵌赛FPGA')
HDL=Path('C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_reader_staged_display_20261104/project/user_source/hdl_source')
LIB=Path('C:/Anlogic/TD_6.2.1_Engineer_6.2.168.116/sim_release')
SIM=Path('C:/modeltech64_10.1c/win64/vsim.exe')
STABLE=ROOT/'hardware/hdmi_ui_ref_stable3s_20261103/tests'
PSI=ROOT/'algorithm_work/meter_landmark_mcu_training_20261103/rtl'
SPECS=[('helper','tb_ref_stable3s_helper','REF_STABLE3S_HELPER',STABLE/'tb_ref_stable3s_helper.sv'),
       ('parameters','tb_ref_stable3s_parameters','REF_STABLE3S_PARAMETERS',STABLE/'tb_ref_stable3s_parameters.sv'),
       ('link','tb_ref_stable3s_link','REF_STABLE3S_LINK',STABLE/'tb_ref_stable3s_link.sv'),
       ('psi_runtime','tb_psi_runtime','PSI_RUNTIME',PSI/'tb_psi_runtime.sv'),
       ('psi_ahb','tb_psi_ahb','PSI_AHB',TASK/'simulation/tb_psi_ahb.sv'),
       ('reader_psi','tb_reader_psi','READER_PSI',PSI/'tb_reader_psi.sv')]
SPECS += [('staged_reader','tb_staged_reader','STAGED_READER',TASK/'simulation/tb_staged_reader.sv'),('staged_link','tb_staged_link','STAGED_LINK',TASK/'simulation/tb_staged_link.sv')]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
ref=lambda p:dict(path=str(Path(p).resolve()),sha256=sha(p))


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',action='store_true');args=ap.parse_args()
    if not args.run:
        print(json.dumps(dict(status='PLAN_ONLY',HDL=str(HDL),suites=[x[0]for x in SPECS],TD_or_device=False)));return
    assert (HDL/'meter_pair/t06_meter_psi_return_runtime.v').is_file()
    assert sha(HDL/'meter_pair/meter_ref_display_control.v')=='0a2cc864b68152c7ab17fe8a5cc4241a1583d01bd12f16d515c0d62cba7b7e2c'
    sources=[LIB/'common/al_phy_glbl.v',LIB/'ph1p/ph1p_phy_gsr.v']+sorted((LIB/'common').glob('al_map_*.v'))+[LIB/'ph1p/ph1p_logic_eram.v']
    sources+=sorted((HDL/'meter_pair').glob('*.v'))+[HDL/'t06_reset_release.v']
    sources+=[HDL/'ui'/n for n in['t06_ui_bin32_bcd.v','t06_ui_barq16_psi100.v','t06_ui_pressure_display.v']]
    sources+=[x[3]for x in SPECS]
    assert len(sources)==len(set(sources))and all(p.is_file()for p in sources)
    assets=[p for p in(HDL/'meter_pair').iterdir()if p.suffix.lower()in['.hex','.mem']]
    snapshot=[ref(p)for p in sources+assets]
    production_snapshot=[ref(p)for p in HDL.rglob('*')if p.is_file()]
    archive=TASK/'tests'/('components_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f'));archive.mkdir(parents=True)
    scratch=Path(tempfile.mkdtemp(prefix='gb_landmark_s3_components_'))
    local=[]
    for i,p in enumerate(sources):
        dest=scratch/(f'{i:03d}_'+p.name);shutil.copyfile(p,dest);local.append(dest.name)
    for p in assets:shutil.copyfile(p,scratch/p.name)
    (scratch/'modelsim.ini').write_text('[Library]\nwork = work\n[vsim]\n',encoding='ascii')
    results=[];started=time.monotonic()
    for i,(name,top,marker,tb)in enumerate(SPECS):
        do='onerror {quit -code 1 -f}\nonbreak {quit -code 2 -f}\n'
        if i==0:do+='vlib work\n'+'\n'.join('vlog -sv '+p for p in local)+'\n'
        do+='vsim -novopt -t 1ps work.'+top+' work.glbl work.PH1P_PHY_GSR\nrun -all\nquit -code 0 -f\n'
        (scratch/(name+'.do')).write_text(do,encoding='ascii')
        t=time.monotonic()
        process=subprocess.run([str(SIM),'-modelsimini','modelsim.ini','-c','-do',name+'.do'],cwd=scratch,
            env=dict(os.environ,MODELSIM='modelsim.ini'),capture_output=True,timeout=120,creationflags=subprocess.CREATE_NO_WINDOW)
        log=(process.stdout+process.stderr).decode(errors='replace');lp=archive/(name+'.log');lp.write_text(log,encoding='utf-8')
        m=re.search(r'PASS '+re.escape(marker)+r' checks=(\d+)',log)
        passed=process.returncode==0 and bool(m)and not re.search(r'\bFAIL(?:_|\b)|\*\* (?:Error|Fatal):',log)
        result=dict(name=name,top=top,passed=passed,exit_code=process.returncode,checks=int(m[1])if m else None,
            elapsed_s=time.monotonic()-t,log=ref(lp),bench=ref(tb),do_file=ref(scratch/(name+'.do')))
        results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
        if not passed:break
    source_unchanged=all(sha(x['path'])==x['sha256']for x in snapshot)
    production_unchanged=all(sha(x['path'])==x['sha256']for x in production_snapshot)
    passed=len(results)==len(SPECS)and all(x['passed']for x in results)and source_unchanged and production_unchanged
    out=dict(passed=passed,status='PASS_ACTUAL_MERGED_STABLE3S_AND_PSI_COMPONENTS'if passed else'FAIL_PRESERVED',
        runner=ref(__file__),HDL=str(HDL),scratch=str(scratch),sources=snapshot,suite_results=results,
        total_checks=sum(x['checks']or 0 for x in results),elapsed_s=time.monotonic()-started,
        actual_new_DUT_sources=True,inputs_unchanged=source_unchanged,new_production_hdl_unchanged=production_unchanged,
        boundary='Actual merged helper/link/production pressure+sevenseg and PSI/bridge/reader are compiled. Locator/reader outputs or completed live-ROI are explicit force frontiers. Abstract millisecond boundaries plus real75000-cycle divider/9375 scanner do not prove physical3seconds, camera/CNN/MCU runtime or board accuracy.',
        TD_or_device_actions=False)
    rp=archive/'receipt.json';rp.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    latest=TASK/'tests/latest_components.json';latest.write_text(json.dumps(dict(passed=passed,receipt=ref(rp)),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=passed,total_checks=out['total_checks'],receipt=ref(rp)),ensure_ascii=False))
    if not passed:raise SystemExit(1)


if __name__=='__main__':main()
