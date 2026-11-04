"""Extract the actual native mapped capture guard; never accesses hardware."""
from pathlib import Path
from datetime import datetime
import argparse, collections, hashlib, importlib.util, json, re, tempfile, subprocess, time

BASE = Path('C:/Users/Edward/Documents/ChatGPT/嵌赛FPGA/algorithm_work/meter_mcu_live_roi_20261029')
HERE = Path(__file__).resolve().parent
WORK = Path('C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029')
C = r'\u_meter_pair/pipeline/reader/live/capture/'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
ref = lambda p: dict(path=str(Path(p).resolve()), sha256=sha(p))
norm = lambda x: re.sub(r'\s+', '', x)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--netlist', type=Path, required=True)
    ap.add_argument('--db', type=Path, required=True)
    ap.add_argument('--label', required=True)
    args = ap.parse_args()
    text = args.netlist.read_text(encoding='utf-8')
    pat = re.compile(r'^  ((?:AL_MAP_|PH1P_)[A-Za-z0-9_]+)\s*(?:#\((.*?)\)\s*)?(?://[^\n]*\n\s*)*((?:\\\S+)|(?:[A-Za-z_$][\w$]*))\s+\((.*?)\);', re.M | re.S)
    cells = []
    for m in pat.finditer(text):
        cells.append(dict(type=m[1], name=m[3], ports={k:norm(v) for k,v in re.findall(r'\.(\w+)\((.*?)\)(?:,|\s*$)', m[4], re.M)}, params=dict(re.findall(r'^\s*\.(\w+)\((.*?)\)(?:,|\s*$)', m[2] or '', re.M))))
    for m in re.finditer(r'^  buf\s+(\S+)\s+\((.*?)\);', text, re.M):
        pair = [norm(x) for x in m[2].split(',')]
        assert len(pair) == 2
        cells.append(dict(type='buf', name=m[1], ports=dict(o=pair[0], i=pair[1]), params={}))
    bad = next(c for c in cells if c['name'] == C+'bad_reg')
    diag = next(c for c in cells if c['name'] == C+'diag_first_causes_reg[7]')
    assert bad['type'] == diag['type'] == 'AL_MAP_SEQ_GSR'
    primary = [bad, diag]
    def output(c,p):
        return (c['type']=='AL_MAP_SEQ_GSR' and p=='q') or ((c['type'].startswith('AL_MAP_LUT') or c['type']=='buf') and p=='o') or (c['type']=='PH1P_PHY_LSLICE' and (p.startswith(('of','oq')) or p in ['fco','fco_f']))
    drivers = collections.defaultdict(list)
    for c in cells:
        for p,n in c['ports'].items():
            if output(c,p): drivers[n].append((c,p))
    def boundary(n):
        return n.startswith(C) and re.fullmatch(r'(gray_valid|gray_sof|gray_eol|frame_error|source_id_valid|capture_frame_allowed|source_id\[\d+\])', n[len(C):])
    visited = set(); selected = {}
    todo = [bad['ports']['d'], diag['ports']['d'], diag['ports']['ce']]
    literal = lambda n: bool(re.match(r"\d+'[bhd]", n))
    while todo:
        n = todo.pop()
        if n in visited: continue
        visited.add(n)
        if literal(n) or boundary(n): continue
        ds = drivers.get(n, [])
        if not ds: continue
        assert len(ds)==1, (n,len(ds))
        c,p = ds[0]
        if c['type']=='AL_MAP_SEQ_GSR' or p.startswith('oq'): continue
        selected[c['name']] = c
        for pin,x in c['ports'].items():
            if (c['type']=='buf' and pin=='i') or (c['type'].startswith('AL_MAP_LUT') and pin!='o') or (c['type']=='PH1P_PHY_LSLICE' and (pin.startswith('i') or pin.startswith('fci'))): todo.append(x)
    for c in primary: selected[c['name']] = c
    selected = list(selected.values())
    driven = {n for c in selected for p,n in c['ports'].items() if output(c,p)}
    nets = {n for c in selected for p,n in c['ports'].items() if p not in ['clk','sr'] and not literal(n)}
    names = {n:'n'+str(i) for i,n in enumerate(sorted(nets))}
    cuts = {}
    for n in sorted(nets-driven):
        q = n.rsplit('/',1)[-1].lstrip('\\'); value = "1'b0"
        g = re.search(r'roi_groups(?:_reg)?\[(\d+)\]',q)
        s = re.search(r'stride(?:_reg)?\[(\d+)\]',q)
        if g: value = 'g['+g[1]+']'
        elif s: value = 'st['+s[1]+']'
        elif 'owner_reg_syn_1[' in q: value = "1'b1" if '[4]' in q else "1'b0"
        elif re.match(r'(groups_seen|gx)\[',q): value = "1'b"+str((319>>int(re.search(r'\[(\d+)\]',q)[1]))&1)
        elif q in ['gray_valid','gray_eol','source_id_valid','capture_frame_allowed','creset'] or q.startswith('cr[1]'): value = "1'b1"
        elif re.match(r'(csi_source_id|source_id|id)\[',q): value = "1'b1" if int(re.search(r'\[(\d+)\]',q)[1])==0 else "1'b0"
        assert n.startswith(C), ('external functional cut',n)
        assert re.fullmatch(r'(canonical_count\[\d+\]|capture_frame_allowed|config_checked_good|cr\[1\]_syn_3|diag_first_causes\[\d+\]|frame_error|full_seen|gray_eol|gray_sof|gray_valid|groups_seen\[\d+\]|gx\[\d+\]|gy\[\d+\]|hint\[\d+\]|id\[\d+\]|output_pending\[\d+\]|owner_reg_syn_1\[\d+\]|release_seen|release_sync\[1\]_syn_3|roi_groups\[\d+\]|source_id\[\d+\]|source_id_valid|stride\[\d+\]|x0\[\d+\]|y0\[\d+\])',q),('unclassified leaf',q)
        cuts[n] = value
    run=Path(tempfile.mkdtemp(prefix='gb_ui_capture_syn_'))
    (run/'modelsim.ini').write_text('[Library]\nwork = work\n[vsim]\n',encoding='ascii')
    lines = ['`timescale 1ns/1ps','module new_gate_cone(input clk,rst_n,input[7:0]g,input[2:0]st,output bad_d,bad_q,diag_q);']
    lines += ['wire '+x+';' for x in names.values()]
    lines += ['assign '+names[n]+'='+v+'; // cut '+n for n,v in cuts.items()]
    nn = lambda n: n if literal(n) else names[n]
    for i,c in enumerate(selected):
        if c['type']=='buf': lines.append('buf b'+str(i)+'('+nn(c['ports']['o'])+','+nn(c['ports']['i'])+');'); continue
        lines.append(c['type']+' #(\n'+',\n'.join('.'+k+'('+v+')' for k,v in c['params'].items())+'\n) u'+str(i)+' (')
        lines.append(',\n'.join('.'+p+'('+('clk' if p=='clk' else 'rst_n' if p=='sr' else nn(n))+')' for p,n in c['ports'].items())+'\n);')
    lines += ['assign bad_d='+nn(bad['ports']['d'])+';','assign bad_q='+nn(bad['ports']['q'])+';','assign diag_q='+nn(diag['ports']['q'])+';']
    template = WORK/'video_roi_replay_runtime/new_mapped_bad7_20261031_032538_004143/cone.sv'
    tail = template.read_text(encoding='utf-8'); lines.append(tail[tail.index('glbl glbl();'):])
    (run/'cone.sv').write_text('\n'.join(lines),encoding='utf-8')
    config = dict(netlist=ref(args.netlist), DB=ref(args.db), generator=ref(Path(__file__)), template=ref(template), cells=selected, leaf_assignments=cuts, scope='Exact native mapped D and real bad/diag7 registers; healthy module-boundary input and reachable first-row-end FF cuts. No fullDUT force.')
    (run/'config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    print('RUNTIME',run,'CELLS',len(selected),'EXTERNAL_CUTS',[n for n in cuts if not n.startswith(C)],flush=True)
    class LocalRunner:
        @staticmethod
        def run_command(cmd,run,label,timeout):
            start=time.monotonic()
            with (run/(label+'.log')).open('wb') as log:
                proc=subprocess.run(cmd,cwd=run,stdout=log,stderr=subprocess.STDOUT,timeout=timeout,creationflags=subprocess.CREATE_NO_WINDOW)
            return dict(command=cmd,exit=proc.returncode,seconds=time.monotonic()-start,log=ref(run/(label+'.log')))
    runner=LocalRunner()
    ms=Path('C:/modeltech64_10.1c/win64');sv=Path('C:/Anlogic/TD_6.2.1_Engineer_6.2.168.116/sim_release')
    deps=[sv/'common/al_phy_glbl.v',*sorted((sv/'common').glob('al_map_*.v')),sv/'ph1p/ph1p_phy_gsr.v',sv/'ph1p/ph1p_phy_lslice.v']
    commands=[('vlib',[str(ms/'vlib.exe'),'work']),('vlog',[str(ms/'vlog.exe'),'-sv','-timescale','1ns/1ps',*map(str,deps),'cone.sv']),('vsim',[str(ms/'vsim.exe'),'-c','-modelsimini','modelsim.ini','-novopt','-t','1ps','work.tb_new_gate_cone','work.glbl','work.PH1P_PHY_GSR','-do','run -all;quit -f'])]
    steps=[]
    for label,cmd in commands:
        step=runner.run_command(cmd,run,label,45);steps.append(step);print('STEP',label,step['exit'],step['seconds'],flush=True)
        if step['exit']!=0: break
    text=(run/'vsim.log').read_text(errors='replace') if (run/'vsim.log').exists() else ''
    passed=len(steps)==3 and all(s['exit']==0 for s in steps) and 'NEW_GATE_CONE_END strides=4 terminal=4 under=4 over=4 checks=36 failures=0' in text and not re.search(r'\*\* (Error|Fatal)',text)
    rec=dict(passed=passed,run=str(run),DB_sha256=sha(args.db),source_manifest_sha256=sha(HERE.parent.parent/'physical/source_freeze_v2.json'),steps=steps,config=ref(run/'config.json'),TB=ref(run/'cone.sv'),official_models={str(p):sha(p) for p in deps},events=[x for x in text.splitlines() if any(k in x for k in ['NEW_GATE','Error','Fatal'])],scope='Native synthesis mapped guard only; final routed cone remains required',device=False)
    (run/'receipt.json').write_text(json.dumps(rec,indent=2),encoding='utf-8')
    out=HERE/('capture_'+args.label+'_gate.json');out.write_text(json.dumps(rec,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=passed,receipt=str(out),sha256=sha(out),events=rec['events']),indent=2),flush=True)
    if not passed: raise SystemExit(1)

if __name__=='__main__': main()
