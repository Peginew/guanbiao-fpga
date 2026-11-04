"""Required changed-ABI and actual PSI transport component simulation."""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import shutil
import tempfile
import datetime

HERE=Path(__file__).resolve().parent
HDL=Path('C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_reader_landmark_20261103/project/user_source/hdl_source')
SIM=Path('C:/modeltech64_10.1c/win64/vsim.exe')

def main():
    base=HERE/'rtl/simulation'
    out=base/('run_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    out.mkdir(parents=True)
    run=Path(tempfile.mkdtemp(prefix='gb_psi_'))
    lib=Path('C:/Anlogic/TD_6.2.1_Engineer_6.2.168.116/sim_release')
    sources=[lib/'common/al_phy_glbl.v',lib/'ph1p/ph1p_phy_gsr.v']+sorted((lib/'common').glob('al_map_*.v'))+[lib/'ph1p/ph1p_logic_eram.v']
    sources+=sorted((HDL/'meter_pair').glob('*.v'))+[HDL/'t06_reset_release.v',HDL/'ui/t06_ui_barq16_psi100.v',HERE/'rtl/tb_psi_runtime.sv',HERE/'rtl/tb_psi_ahb.sv',HERE/'rtl/tb_reader_psi.sv']
    local=[]
    for n,p in enumerate(sources):
        q=run/(str(n)+'_'+p.name);shutil.copyfile(p,q);local.append(q.name)
    (run/'modelsim.ini').write_text('[Library]\nwork = work\n[vsim]\n',encoding='ascii')
    logs=[];codes=[]
    for j,top in enumerate(['tb_psi_runtime','tb_psi_ahb','tb_reader_psi']):
        do='onerror {quit -code 1 -f}\nonbreak {quit -code 2 -f}\n'
        if j==0:do+='vlib work\n'+'\n'.join('vlog -sv '+p for p in local)+'\n'
        do+='vsim -novopt work.'+top+' work.glbl work.PH1P_PHY_GSR\nrun -all\nquit -code 0 -f\n'
        name=top+'.do';(run/name).write_text(do,encoding='ascii')
        p=subprocess.run([str(SIM),'-modelsimini','modelsim.ini','-c','-do',name],cwd=run,
                         env=dict(os.environ,MODELSIM='modelsim.ini'),capture_output=True,timeout=60,creationflags=0x08000000)
        logs.append((p.stdout+p.stderr).decode(errors='replace'));codes.append(p.returncode)
    log='\n'.join(logs);(out/'console.log').write_text(log,encoding='utf-8')
    matches=re.findall(r'PASS (PSI_RUNTIME|PSI_AHB|READER_PSI) checks=(\d+)',log)
    ok=len(matches)==3 and not re.search(r'\bFAIL\b|\*\* (?:Error|Fatal):',log)
    receipt=dict(status='PASS_CHANGED_ABI_AND_SCALAR_UNITS'if ok else'FAIL_PRESERVED',
                 exit_codes=codes,checks=dict(matches),scratch=str(run),same_source_commit=True if ok else None,
                 sources={str(x):hashlib.sha256(x.read_bytes()).hexdigest()for x in sources},
                 scope='Actual bridge and reader/formatter; reader completed-liveROI frontier explicitly driven, not real camera/MCU or board acceptance',hardware_actions=False)
    (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (base/'latest.json').write_text(json.dumps({'receipt':str(out/'receipt.json'),'status':receipt['status']},indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False));print(log[-2500:])
    if not ok:raise SystemExit(1)

if __name__=='__main__':main()
