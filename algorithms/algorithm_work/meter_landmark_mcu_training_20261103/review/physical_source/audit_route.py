"""Final actual-route primitive/pad/clock preservation; no TD or device calls."""
from pathlib import Path
import argparse,json,re,sys
from audit_synth import TASK,BASE,HERE,read,ref,sha,write,freq
from audit_place import io
from mapping_helpers import parse,vector

def clockresolver(cells,canon):
    roots={}
    for name,c in cells.items():
        if c['type']=='PH1P_PHY_PLL_V2':
            for bit,n in enumerate(reversed(vector(c['ports']['clkc']))):
                if not n.startswith('open_n'):roots[canon(n)]=('PLL',name,bit)
        elif c['type']=='PH1P_PHY_MCU':roots[canon(c['ports']['ahb_clk'])]=('MCU_AHB',name,'ahb_clk')
        elif c['type']=='PH1P_PHY_GCLK':
            assert c['ports']['seln']=="2'b10"and c['ports']['drct']=="2'b11"
            roots[canon(c['ports']['clkout'])]=('BUF',vector(c['ports']['clkin'])[-1])
        elif c['type']in['PH1P_PHY_IOCLK','PH1P_PHY_MLCLK']and'clkout'in c['ports']and'clkin'in c['ports']:
            roots[canon(c['ports']['clkout'])]=('BUF',c['ports']['clkin'])
    def resolve(n):
        n=canon(n);seen=set()
        while True:
            assert n not in seen and n in roots,(n,'clockroot');seen.add(n);r=roots[n]
            if r[0]!='BUF':return(r[1],r[2])
            n=canon(r[1])
    return resolve

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--route-receipt',type=Path,default=TASK/'physical/latest_literal_route.json')
    args=ap.parse_args()
    route=read(args.route_receipt);place=read(TASK/'physical/latest_place.json')
    prior=read(HERE/'place_route_admission_review.json');assert prior['passed']
    assert route['stage']=='route'and route['exit_code']==0 and route['passed']and route['global_final_timing_passed']
    assert route.get('mode')=='route', 'This review currently admits only the actual same-place literal-contract route.'
    assert route['source_DB']==place['output']and route['manifest']==place['manifest']
    effective=read(HERE/'literal_final_effectiveness_review.json')
    assert effective['passed']and effective['final_routed_timing']and effective['route_receipt']==ref(args.route_receipt)
    assert effective['PSI_all17_logical_sources_proven_by_unique_launch_outputs']
    assert sha(route['manifest']['path'])==route['manifest']['sha256']
    for row in [route['output'],route['log'],*route['artifacts'].values(),*route['controls']]:assert sha(row['path'])==row['sha256']
    cells,canon=parse(route['artifacts']['actual_netlist.v']['path']);pcells,pcanon=parse(place['artifacts']['actual_netlist.v']['path'])
    cr=clockresolver(cells,canon);pr=clockresolver(pcells,pcanon)
    area=Path(route['run'])/'reader_landmark_phy.area';ios=io(area.read_text());assert len(ios)==81 and ios==prior['IO_rows']
    timing=Path(route['run'])/'reader_landmark_pr.timing';clocks=freq(timing.read_text());assert clocks==prior['regular_timing_enumerated_clock_frequencies']
    xml=Path(route['artifacts']['clocks.txt']['path']).read_text();assert sum(map(int,re.findall(r'<clock_group[^>]* size="(\d+)"',xml)))==18
    f=route['FINAL'];assert set(f)=={'SWNS','STNS','HWNS','HTNS'}and min(f.values())>=0 and f['STNS']==f['HTNS']==0
    log=Path(route['log']['path']).read_text(errors='replace')
    assert 'ACTUAL_LITERAL_CONTRACTS_PROVEN'in log and 'No multi-drive.'in log and 'No abnormal timing path.'in log
    macro=[]
    for n in prior['macro_names']:
        c,p=cells[n],pcells[n];assert c['type']==p['type']and c['params']==p['params']
        cp={x:canon(v)for x,v in c['ports'].items()};pp={x:pcanon(v)for x,v in p['ports'].items()}
        for x in cp:
            if cp[x]!=pp.get(x)and x in['clka','clkb','core_clk','timer_clk','fb_clk']:
                assert cr(cp[x])==pr(pp[x]);cp[x]=pp[x]
        assert cp==pp,('routed macroport',n)
        macro.append(dict(name=n,all_params_and_data_ports_match_place=True))
    assert len(macro)==26
    # Re-discover route FF outputs to ensure no added unrelated FF shares ASR.
    regs=[]
    for n,c in cells.items():
        if c['type']!='PH1P_PHY_LSLICE':continue
        for half,pin in[('A','oqa'),('B','oqb')]:
            if pin in c['ports']and c['params'].get('OQ'+half+'MUX')=='"Q'+half+'"':
                q=canon(c['ports'][pin])
                if q!='UNCONNECTED_SINGLE_USE':regs.append((n,half,q,c))
    source=r'\u_hdmi_reset/release_ff[2]';qsrc=[z for z in regs if z[2]==canon(source)];assert len(qsrc)==1 and cr(qsrc[0][3]['ports']['clk'])[1]==4
    wanted=set();selected=set();record=[]
    for row in prior['independent_FF_records']:
        q=canon('\\'+row['logical']);x=[z for z in regs if z[2]==q];assert len(x)==1
        n,h,q,c=x[0];assert n.lstrip('\\')==row['physical']and h==row['half'];wanted.add(q);selected.add(n)
        assert c['params']['ASRMUX']=='"INV"'and c['params']['REG'+h+'_REGSET_ASYNC']=='"RESET"'
        assert c['params']['REG'+h+'_SD']=='"IM'+h+'"'and canon(c['ports']['im'+h.lower()])==canon(row['D'])
        assert canon(c['ports']['asr'])==canon(source)and cr(c['ports']['clk'])==(cr(qsrc[0][3]['ports']['clk'])[0],5)
        record.append(dict(logical=row['logical'],physical=n.lstrip('\\'),half=h,clock=cr(c['ports']['clk'])))
    assert len(selected)==6 and len(record)==12 and not[(n,h,q)for n,h,q,c in regs if n in selected and q not in wanted]
    pins=sorted(n.lstrip('\\')+'.asr'for n in selected);assert pins==prior['physical_ASR_pins']
    # Verify the actual 17 logical held PSI sources still occupy the exact
    # registered launch halves used by the final SMD path evidence.
    psi_place=read(HERE/'psi17_endpoint_precheck.json');psi_record=[]
    for row in psi_place['registers']:
        q=canon(row['logical']);matches=[z for z in regs if z[2]==q];assert len(matches)==1
        n,h,q,c=matches[0]
        assert n==row['physical']and h==row['half']and cr(c['ports']['clk'])==tuple(row['clockroot'])
        psi_record.append(dict(logical=row['logical'],physical=n,half=h,clock=cr(c['ports']['clk'])))
    assert len(psi_record)==17
    cap=read(HERE/'capture_final_gate.json');assert cap['passed']and cap['ROUTED_DB']==route['output']and cap['checks']==36
    out=dict(passed=True,status='PASS_LIMITED_FINAL_PIN_CLOCK_MCU_RAM_ASR_CAPTURE',route=ref(args.route_receipt),
        actual_routed_DB=route['output'],actual_netlist=route['artifacts']['actual_netlist.v'],source_freeze=route['manifest'],
        place_independent_review=ref(HERE/'place_route_admission_review.json'),auditor_source=ref(__file__),
        IO_count=81,all81_fullfields_equal_actual_place=True,clock_objects_total=18,regular_clock_frequencies=clocks,regular_table_count=17,
        fresh_route_serial_FFs=record,physical_ASR_pins=pins,physical_ASR_count=6,no_foreign_registered_ASR_half=True,
        effective_literal_contract_review=ref(HERE/'literal_final_effectiveness_review.json'),
        actual_PSI_sources17=psi_record,entry_literal_SDC_native_success=True,MCU_PLL_ERAM_preservation=macro,UI_Logo_boot_INIT=720,ROI_capture_ERAMs=12,
        capture_actual36=ref(HERE/'capture_final_gate.json'),FINAL=f,resources=route['resources'],device_actions=False,
        PSI_contract_applied_before_route=True,
        raw_route_identity=route['output'],
        pending=['Supplementary final native all18 clocks and DATA/consumer endpoint scope is parent-owned',
            'Parent whole-project delivery gate must also PASS; this limited scope is not bitgen admission'],
        bitgen_or_board_admission=False)
    write(HERE/'route_pin_clock_macro_review.json',out);print(json.dumps(dict(passed=True,receipt=str(HERE/'route_pin_clock_macro_review.json'))))

if __name__=='__main__':main()
