"""Actual guided-place admission. Pure file parsing; no TD or device calls."""
from pathlib import Path
import json,re,sys
from audit_synth import TASK,HERE,read,ref,sha,write,freq
from audit_place import io
from audit_route import clockresolver
from mapping_helpers import parse,derive_asr

GUIDED=TASK/'physical/guided_ui_macros'


def main():
    place_path=TASK/'physical/latest_guided_place.json'
    place=read(place_path);syn=read(TASK/'physical/latest_synth.json')
    assert place['passed']and place['stage']=='place'and place['exit_code']==0
    assert place['source_DB']==syn['output']and place['manifest']==syn['manifest']
    for x in [place['manifest'],place['source_DB'],place['output'],place['log'],*place['artifacts'].values(),*place['controls']]:
        assert sha(x['path'])==x['sha256'],('changed artifact',x['path'])
    run=Path(place['run'])
    cells,canon=parse(place['artifacts']['actual_netlist.v']['path'])
    scells,scanon=parse(syn['artifacts']['actual_netlist.v']['path'])
    root=clockresolver(cells,canon);sroot=clockresolver(scells,scanon)
    prior=read(HERE/'place_route_admission_review.json');assert prior['passed']
    ios=io((run/'reader_landmark_phy.area').read_text());assert len(ios)==81 and ios==prior['IO_rows']
    clocks=freq((run/'reader_landmark_place.timing').read_text())
    assert len(clocks)==17 and clocks==prior['regular_timing_enumerated_clock_frequencies']
    xml=(run/'clocks.txt').read_text()
    groups=re.findall(r'<clock_group name="([^"]+)" size="(\d+)"',xml)
    assert sum(int(n)for _,n in groups)==18
    # Full primitive parameter/INIT and canonical port preservation against
    # this candidate's actual synthesis, including clock-tree root identity.
    macro=[]
    for name in prior['macro_names']:
        c,s=cells[name],scells[name]
        assert c['type']==s['type']and c['params']==s['params'],('macro parameters',name)
        ports={k:canon(v)for k,v in c['ports'].items()};sp={k:scanon(v)for k,v in s['ports'].items()}
        clock_roots={}
        for k in ports:
            if k in ['clka','clkb','core_clk','timer_clk','fb_clk']:
                if ports[k]!=sp.get(k):
                    assert root(ports[k])==sroot(sp[k]),('clock root',name,k)
                    clock_roots[k]=root(ports[k]);ports[k]=sp[k]
                elif ports[k] not in ["1'b0","1'b1"]and not ports[k].startswith('open_n'):
                    clock_roots[k]=dict(unchanged_canonical_clock_net=ports[k])
        assert ports==sp,('macro ports',name)
        macro.append(dict(name=name,type=c['type'],all_params_INIT_and_data_ports_equal_actual_SYN=True,clock_roots=clock_roots))
    assert len(macro)==26
    # Directly parse native post-place macro reports, rather than trusting
    # matches_anchor booleans copied into the runner's summary.
    plan=read(GUIDED/'anchor_plan.json');report=(run/'macro_reports.txt').read_text()
    blocks={x.splitlines()[0]:x for x in report.split('BEGIN_GUIDED_POST ')[1:]}
    anchors=[]
    for a in plan['anchors']:
        name=a['name'];b=blocks[name]
        grid=re.search(r'Grid\s*\|\s*col=(\d+) row=(\d+)',b)
        offset=re.search(r'Offset\s*\|\s*(\d+)',b)
        assert grid and offset and tuple(map(int,grid.groups()))==(a['col'],a['row'])and int(offset[1])==a['offset']
        assert re.search(r'IsPlaced\s*\|\s*True',b)and re.search(r'IsFixed\s*\|\s*True',b)
        assert re.search(r'HadBound\s*\|\s*False',b),'No old implicit clockBound may be assumed/copied.'
        c,s=cells['\\'+name],scells['\\'+name]
        assert c['type']==a['type']==s['type']and c['params']==s['params']
        cp={k:canon(v)for k,v in c['ports'].items()};sp={k:scanon(v)for k,v in s['ports'].items()}
        for k in ['clka','clkb']:
            if k in cp and cp[k]!=sp[k]:assert root(cp[k])==sroot(sp[k]);cp[k]=sp[k]
        assert cp==sp,('anchor full ports',name)
        roots={}
        if c['type']=='PH1P_PHY_ERAM_V2':
            for k in ['clka','clkb']:
                if k in c['ports']:
                    n=canon(c['ports'][k])
                    if n not in ["1'b0","1'b1"]and not n.startswith('open_n'):roots[k]=root(n)
            assert roots and all(z[1]==4 for z in roots.values()),('UI memory clock must remain HDMI PLL bit4',name,roots)
        else:
            assert c['type']=='PH1P_PHY_DSPSIOU_V2'
            assert all(v in ["1'b0","1'b1"]or v.startswith('open_n')for k,v in cp.items()if k=='clk'),('DSP is not clockless',name)
            assert all(str(v)=='"0"'for k,v in c['params'].items()if k.endswith('REG')),('DSP internal registers',name)
        anchors.append(dict(name=name,type=c['type'],col=a['col'],row=a['row'],offset=a['offset'],native_postplace_placed_and_fixed=True,
            HadBound=False,clock_roots=roots,full_params_and_ports_preserved=True))
    assert len(anchors)==10
    log=Path(place['log']['path']).read_text(errors='replace')
    assert not re.search(r'\bERROR:|\bFATAL:',log)
    assert 'start command "place"'in log and 'start command "legalize_phy_inst"'in log
    # Freshly derive serial FF/ASR packing from THIS placement. This helper
    # writes a legacy interactive overlay as data; it is never executed.
    mapping=derive_asr(Path(place['artifacts']['actual_netlist.v']['path']),Path(place['output']['path']),
        Path(syn['artifacts']['actual_netlist.v']['path']),read(TASK/'physical/ddr_group_plan.json'),run/'actual.adc',GUIDED)
    assert mapping['logical_FF_count']==12 and mapping['physical_ASR_count']==len(mapping['pins'])and not mapping['nonserial_registered_consumers']
    regs=[]
    for name,c in cells.items():
        if c['type']!='PH1P_PHY_LSLICE':continue
        for half,pin in [('A','oqa'),('B','oqb')]:
            if pin in c['ports']and c['params'].get('OQ'+half+'MUX')=='"Q'+half+'"':
                q=canon(c['ports'][pin])
                if q!='UNCONNECTED_SINGLE_USE':regs.append((name,half,q,c,pin))
    # Independently repeat the semantic registered-half selection and no-
    # foreign-consumer scope, rather than copying helper records as proof.
    source=r'\u_hdmi_reset/release_ff[2]';src=[x for x in regs if x[2]==canon(source)]
    assert len(src)==1 and root(src[0][3]['ports']['clk'])[1]==4
    expected={r'\u_hdmi_tx/u_hdmi2phy_wrapper/u'+str(lane)+'_lane_lvds_8_1/u_serial_reset/release_ff['+str(stage)+']':stage for lane in range(4)for stage in range(3)}
    selected=set();wants={canon(x)for x in expected};serial=[]
    for logical,stage in expected.items():
        matches=[x for x in regs if x[2]==canon(logical)];assert len(matches)==1
        name,half,q,c,pin=matches[0];p=c['ports'];params=c['params']
        want="1'b1"if stage==0 else canon(logical.rsplit('[',1)[0]+'['+str(stage-1)+']')
        assert params['REG'+half+'_SD']=='"IM'+half+'"'and canon(p['im'+half.lower()])==want
        assert canon(p['asr'])==canon(source)and params['ASRMUX']=='"INV"'and params['REG'+half+'_REGSET_ASYNC']=='"RESET"'
        assert root(p['clk'])==(root(src[0][3]['ports']['clk'])[0],5)
        selected.add(name);serial.append(dict(logical=logical,physical=name,half=half,clock_root=root(p['clk'])))
    assert not[x for x in regs if x[0]in selected and x[2]not in wants]
    pins=sorted(n.lstrip('\\')+'.asr'for n in selected);assert pins==mapping['pins']
    asr='set_false_path -through [get_nets {u_hdmi_reset/release_ff[2]}] -to [get_pins {'+' '.join(pins)+'}]\n'
    psi='set_max_delay -from [get_regs {u_meter_pair/pipeline/reader/live/return_psi_q8[*] u_meter_pair/pipeline/reader/live/return_psi_valid}] -to [get_clocks {HDMI_PIXEL_CLK}] -datapath_only 7.200\n'
    (GUIDED/'asr_literal.sdc').write_text(asr,encoding='ascii')
    (GUIDED/'psi_literal.sdc').write_text(psi,encoding='ascii')
    assert sha(GUIDED/'psi_literal.sdc')=='799e8df18f8dbe7298a65f5840d93eac128e298e7510f2d9bf6437402fa7ef6c'
    psi_rows=[]
    for logical in [r'\u_meter_pair/pipeline/reader/live/return_psi_q8['+str(i)+']'for i in range(16)]+[r'\u_meter_pair/pipeline/reader/live/return_psi_valid']:
        match=[x for x in regs if x[2]==canon(logical)];assert len(match)==1
        name,half,q,c,pin=match[0];cr=root(c['ports']['clk'])
        assert cr[1]==0 and 'u_mcu_clocks/'in cr[0]
        psi_rows.append(dict(logical=logical,physical=name,half=half,outputpin=pin,clockroot=cr))
    write(GUIDED/'psi17_endpoint_precheck.json',dict(status='ACTUAL_GUIDED_PLACE17_PSI_SOURCES',source_DB=place['output'],source_netlist=place['artifacts']['actual_netlist.v'],registers=psi_rows))
    clock_path=GUIDED/'clock_macro_postplace_review.json'
    write(clock_path,dict(passed=True,status='PASS_ACTUAL_GUIDED_CLOCK_MACRO_PIN_REVIEW',place_receipt=ref(place_path),source_DB=place['output'],manifest=place['manifest'],auditor=ref(__file__),
        physical_IO_count=81,IO_rows=ios,clock_summary_total=18,clock_summary_groups=groups,regular_clock_frequencies=clocks,
        macro26=macro,UI_Logo_boot_INIT=720,ROI_capture_ERAMs=12,anchors10=anchors,actual_macro_report=ref(run/'macro_reports.txt'),
        clockBound_scope='Ten native reports show HadBound=False; no old implicit clockBound copied. ERAM actual clock roots are the unchanged HDMI PLL bit4, DSPs have no active clock/registers; actual place+legalize succeeds.',
        fresh_ASR_registered12=serial,physical_ASR_pins=pins,PSI_source17=ref(GUIDED/'psi17_endpoint_precheck.json'),
        resources=place['resources'],after_car_reserve=place['after_rover_reserve'],device=False,FINAL_timing_or_bitgen_admission=False))
    gate=dict(passed=True,stage='guided_route',place_receipt=ref(place_path),source_DB=place['output'],manifest=place['manifest'],
        ASR_mapping=ref(GUIDED/'placed_asr_mapping.json'),asr_literal=ref(GUIDED/'asr_literal.sdc'),psi_literal=ref(GUIDED/'psi_literal.sdc'),
        ASR_count=len(pins),clock_macro_reviews=[ref(clock_path)],psi_source_precheck=ref(GUIDED/'psi17_endpoint_precheck.json'),
        source_synthesis_reused=True,legacy_interactive_overlay_must_not_execute=True,
        required_route_entry='read_sdc both pure literals before first timer; force actual PSI17/17/0/0 and ASR Max+Min n/n/0/0 before routing',
        FINAL_timing_and_routed_capture_pending=True,bitgen_admission=False,device=False,auditor=ref(__file__))
    write(GUIDED/'guided_route_admission.json',gate)
    print(json.dumps(dict(passed=True,ASR_count=len(pins),IO=81,clock_objects=18,PSI_sources=17,gate=ref(GUIDED/'guided_route_admission.json')),ensure_ascii=False))


if __name__=='__main__':main()
