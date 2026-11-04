"""Independent limited source and actual SYN primitive audit; no TD mutations."""
from pathlib import Path
import collections,hashlib,json,re,sys
HERE=Path(__file__).resolve().parent;TASK=HERE.parents[1];ROOT=TASK.parents[1]
sys.path.insert(0,str(TASK/'physical'))
from mapping_helpers import parse
BASE=ROOT/'hardware/hdmi_ui_ref_recovery_20261103'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def ref(p):return dict(path=str(Path(p).resolve()),sha256=sha(p))
def write(p,v):Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n','utf-8')
def ports(text):
    out={}
    for direction,hi,lo,name in re.findall(r'^  (input|output|inout)\s+(?:\[(\d+):(\d+)\]\s+)?(\w+);',text,re.M):
        for i in range(min(int(hi),int(lo)),max(int(hi),int(lo))+1)if hi else [None]:
            out[name if i is None else name+'['+str(i)+']']=direction
    return out
def freq(text):return {n:float(f)for f,n in re.findall(r'^\s*clk\d+:\s+([\d.]+)\s+\d+\s+(\S+)\s*$',text,re.M)}

def main():
    checks=0;manifest=TASK/'physical/source_freeze_v2.json';m=read(manifest)
    for row in m['inputs']+m['tools']:assert sha(row['path'])==row['sha256'];checks+=1
    r=read(TASK/'physical/latest_synth.json');o=read(BASE/'physical/latest_synth.json')
    assert r['stage']=='synth' and r['exit_code']==0 and r['manifest']['sha256']==sha(manifest)
    for key in ['output','log']:
        assert sha(r[key]['path'])==r[key]['sha256'];checks+=1
    for row in r['artifacts'].values():assert sha(row['path'])==row['sha256'];checks+=1
    net=Path(r['artifacts']['actual_netlist.v']['path']);oldnet=Path(o['artifacts']['actual_netlist.v']['path'])
    assert sha(oldnet)==o['artifacts']['actual_netlist.v']['sha256']
    a,ac=parse(net);b,bc=parse(oldnet);P=Path(m['project']);OP=Path(read(BASE/'physical/source_freeze.json')['project'])
    old={p.relative_to(OP).as_posix():p for p in(OP/'user_source').rglob('*')if p.is_file()}
    new={p.relative_to(P).as_posix():p for p in(P/'user_source').rglob('*')if p.is_file()}
    added=set(new)-set(old);removed=set(old)-set(new)
    assert added=={'user_source/hdl_source/meter_pair/t06_meter_psi_return_runtime.v'} and not removed
    raw=[];functional=[];pathonly=[]
    for n in sorted(set(new)&set(old)):
        if new[n].read_bytes()==old[n].read_bytes():continue
        raw.append(n)
        nt=new[n].read_text('utf-8-sig');ot=old[n].read_text('utf-8-sig')
        nt=nt.replace(P.as_posix(),'<PROJECT>').replace(str(P),'<PROJECT>')
        ot=ot.replace(OP.as_posix(),'<PROJECT>').replace(str(OP),'<PROJECT>')
        (pathonly if nt==ot else functional).append(n)
    expected=['meter_mcu_live_roi.v','meter_mcu_roi_ahb_live.v','t06_meter_pair_link.v','t06_meter_roi_reader.v']
    assert sorted(Path(n).name for n in functional)==expected,(functional,pathonly)
    pin=P/'user_source/constraints_source/pin.adc';sdc=P/'td_project/base_auto_quality.sdc'
    assert pin.read_bytes()==(OP/'user_source/constraints_source/pin.adc').read_bytes()
    assert sdc.read_bytes()==(OP/'td_project/base_auto_quality.sdc').read_bytes()
    pp,po=ports(net.read_text()),ports(oldnet.read_text());assert pp==po and len(pp)==87;checks+=89
    # The native pad report omits10 dedicatedMIPI bits and adds4 implicit TMDS N pads.
    mipipads={n for n in pp if n.startswith(('IO_rx_clk_pad_','IO_rx_data_pad_'))}
    physical_expected=(set(pp)-mipipads)|{n+'(n)'for n in pp if n.startswith('O_tmds_')}
    assert len(mipipads)==10 and len(physical_expected)==81
    nt=(Path(r['run'])/'reader_landmark_gate.timing').read_text();ot=(Path(o['run'])/'hdmi_ui_ref_fix_gate.timing').read_text()
    assert freq(nt)==freq(ot) and len(freq(nt))==17
    clockxml=Path(r['artifacts']['clocks.txt']['path']).read_text();assert sum(map(int,re.findall(r'<clock_group[^>]* size="(\d+)"',clockxml)))==18
    pll=[n for n,c in a.items()if c['type']=='PH1P_PHY_PLL_V2'];assert len(pll)==4
    for n in pll:
        assert a[n]['params']==b[n]['params'] and {p:ac(v)for p,v in a[n]['ports'].items()}=={p:bc(v)for p,v in b[n]['ports'].items()};checks+=1
    mm=[n for n,c in a.items()if c['type']=='PH1P_PHY_MCU'];assert len(mm)==1;n=mm[0]
    assert a[n]['params']==b[n]['params']
    assert a[n]['params']['MCU_RESET_VECTOR']=='"32\'b00100000111000000000000000000000"'
    assert a[n]['params']['AHB_FREQ']=='"50.0"'
    for p in['dbg_stop','dbg_stop_at_boot','dbg_stop_on_reset']:assert a[n]['ports'][p]=="1'b0"
    mcuportdiff={p:[ac(v),bc(b[n]['ports'].get(p,''))]for p,v in a[n]['ports'].items()if ac(v)!=bc(b[n]['ports'].get(p,''))}
    assert not mcuportdiff;checks+=len(a[n]['params'])+len(a[n]['ports'])
    ui_prefixes=(r'\u_dashboard/',r'\u_hdmi_mixer/u_anlogic_logo_rom/',r'\u_mcu_bootrom/')
    ui={n:c for n,c in a.items()if c['type']=='PH1P_PHY_ERAM_V2'and n.startswith(ui_prefixes)}
    capture={n:c for n,c in a.items()if c['type']=='PH1P_PHY_ERAM_V2'and n.startswith(r'\u_meter_pair/pipeline/reader/live/capture/')}
    assert len(ui)==9 and len(capture)==12
    macro=[];totalinit=0
    for n,c in dict(ui,**capture).items():
        z=b[n];assert c['params']==z['params']
        assert {p:ac(v)for p,v in c['ports'].items()}=={p:bc(v)for p,v in z['ports'].items()}
        ini={k:v for k,v in c['params'].items()if re.fullmatch('INITP?_[0-9A-F]{2}',k)};assert len(ini)==80
        totalinit+=len(ini);checks+=len(c['params'])+len(c['ports'])
        macro.append(dict(name=n,parameters=len(c['params']),ports=len(c['ports']),INIT_literals=len(ini),
            all_parameters_and_normalized_ports_equal_previous_actual_SYN=True,
            params_sha256=hashlib.sha256(json.dumps(c['params'],sort_keys=True).encode()).hexdigest(),
            canonical_clocks={p:ac(c['ports'][p])for p in ['clka','clkb']if p in c['ports']}))
    assert totalinit==1680
    # Trace DSP removal to the obsolete bar-based scaler, never a picture path.
    dsp={n for n,c in a.items()if c['type']=='PH1P_PHY_DSPMULT_V2'};odsp={n for n,c in b.items()if c['type']=='PH1P_PHY_DSPMULT_V2'}
    assert len(dsp)==38 and len(odsp)==39 and not dsp-odsp and odsp-dsp=={r'\u_meter_pair/pipeline/reader/scale/mult0_syn_62'}
    out=dict(passed=True,status='PASS_LIMITED_ACTUAL_SYN_SOURCE_PIN_CLOCK_MCU_RAM_INIT',checks=checks,
        new_manifest=ref(manifest),new_synth=ref(TASK/'physical/latest_synth.json'),actual_netlist=ref(net),actual_DB=r['output'],
        previous_actual_netlist=ref(oldnet),audit_source=ref(__file__),parser_source=ref(TASK/'physical/mapping_helpers.py'),
        source_changes=dict(functional_modified=functional,absolute_path_only_modified=pathonly,added=sorted(added),removed=[]),
        IO=dict(actual_SYN_top_logical_port_bits=87,direction_and_names_equal_previous=True,pin_ADC=ref(pin),ADC_bytes_equal_previous=True,
            native_expected_physical_pad_count=81,dedicated_MIPI_omitted_from_pad_report=sorted(mipipads),implicit_TMDS_N_pad_count=4,
            physical_LOC_and_standard_readback='PENDING actual place/route IO report'),
        clocks=dict(actual_PLLs=4,PLL_params_and_ports_equal_previous=True,timing_enumerated=freq(nt),timing_enumerated_count=17,
            all_clock_object_count_from_native_summary=18,summary=ref(r['artifacts']['clocks.txt']['path']),
            limitation='18 total native clock objects; regular SYN timing table prints17, not allclock18-query proof'),
        MCU=dict(name=mm[0],all_params_and_canonical_ports_equal_previous=True,reset_vector='0x20E00000 physical31bit',AHB_MHz=50,dbg_stops_zero=True),
        ERAM=dict(UI_Logo_boot_count=9,UI_Logo_boot_INIT=720,ROI_capture_count=12,ROI_capture_INIT=960,
            exact_current_macros=macro,old_PASS_reused_as_current=False),
        DSP=dict(current=38,previous=39,removed=sorted(odsp-dsp),new=[]),
        current_SYN_estimate=r['resources'],place_route_FINAL_passed=False,device_or_bitgen_actions=False,
        pending=['freshly-derived placed_ASR scope','actual81IO LOC/standard readback','finalSTA/ordinaryDDR','routedcapture/INIT checks'])
    write(HERE/'synth_source_pin_clock_ram_review.json',out)
    print(json.dumps(dict(passed=True,checks=checks,receipt=str(HERE/'synth_source_pin_clock_ram_review.json'))))

if __name__=='__main__':main()
