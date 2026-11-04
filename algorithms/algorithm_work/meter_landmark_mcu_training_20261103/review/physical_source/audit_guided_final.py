"""Read existing actual guided-route artifacts; never runs TD or a device."""
from pathlib import Path
import json,re
from audit_synth import TASK,HERE,BASE,read,ref,sha,write,freq
from audit_place import io
from audit_route import clockresolver
from mapping_helpers import parse,vector

GUIDED=TASK/'physical/guided_ui_macros'


def routed_clockresolver(cells,canon):
    # Routing inserts dedicated SCLK distribution, including PLL feedback.
    # Collapse only actual, explicitly connected SCLK buffers, preserving
    # the upstream PLL bit identity rather than ignoring changed clock nets.
    edges={};drivers={}
    for name,c in cells.items():
        typ,p=c['type'],c['ports']
        if typ=='PH1P_PHY_PLL_V2':
            for bit,n in enumerate(reversed(vector(p['clkc']))):
                if not n.startswith('open_n'):drivers[canon(n)]=(name,bit)
        elif typ=='PH1P_PHY_MCU':drivers[canon(p['ahb_clk'])]=(name,'ahb_clk')
        elif typ=='PH1P_PHY_MIPIIO_RX':
            assert 'o_fabric_div4_8_clk'in p
            drivers[canon(p['o_fabric_div4_8_clk'])]=(name,'o_fabric_div4_8_clk')
        elif typ=='PH1P_PHY_GCLK':
            assert p['seln']=="2'b10"and p['drct']=="2'b11"
            edges[canon(p['clkout'])]=canon(vector(p['clkin'])[-1])
        elif typ in['PH1P_PHY_IOCLK','PH1P_PHY_MLCLK','PH1P_PHY_SCLK_V2']and'clkout'in p and'clkin'in p:
            if typ=='PH1P_PHY_SCLK_V2':assert c['params'].get('BYPASS')=='"DISABLE"'
            edges[canon(p['clkout'])]=canon(p['clkin'])
    def resolve(n):
        n=canon(n);seen=set()
        while n in edges:
            assert n not in seen;seen.add(n);n=edges[n]
        assert n in drivers,('unresolved actual clock',n)
        return drivers[n]
    return resolve


def summaries(text,command,token):
    rows=[];check=None
    for line in text.splitlines():
        if line.strip()in['Max Check','Min Check']:check=line.strip().split()[0]
        m=re.match(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+('+command+r'.*)$',line)
        if m and token in m[5]:rows.append(dict(check=check,total=int(m[1]),active=int(m[2]),shadowed=int(m[3]),ignored=int(m[4]),command=m[5]))
    return rows


def main():
    receipt=TASK/'physical/latest_guided_route.json';route=read(receipt)
    assert route['stage']=='route'and route['passed']and route['exit_code']==0 and route['global_final_timing_passed']
    place=read(TASK/'physical/latest_guided_place.json');review=read(GUIDED/'clock_macro_postplace_review.json');gate=read(GUIDED/'guided_route_admission.json')
    assert review['passed']and gate['passed']and route['source_DB']==place['output']and route['manifest']==place['manifest']
    assert route['gate']==ref(GUIDED/'guided_route_admission.json')and route['place_receipt']==ref(TASK/'physical/latest_guided_place.json')
    for x in [route['manifest'],route['source_DB'],route['output'],route['log'],*route['controls'],*route['artifacts'].values()]:assert sha(x['path'])==x['sha256']
    run=Path(route['run']);log=Path(route['log']['path']).read_text(errors='replace')
    assert not re.search(r'\bERROR:|\bFATAL:|GUIDED_ROUTE_FAILED:',log)
    assert 'GUIDED_LITERAL_CONTRACT_FINAL_COMPLETE'in log and'No multi-drive.'in log and'No abnormal timing path.'in log
    assert log.index('GUIDED_LITERAL_SDC_REGISTERED_BEFORE_CLOCK_DISCOVERY')<log.index('start command "start_timer"')<log.index('ACTUAL_GUIDED_LITERAL_CONTRACTS_PROVEN')<log.index('start command "route"')
    for name,key in [('asr_literal.sdc','asr_literal'),('psi_literal.sdc','psi_literal')]:assert sha(run/name)==gate[key]['sha256']
    final=route['FINAL'];assert set(final)=={'SWNS','STNS','HWNS','HTNS'}and min(final.values())>=0 and final['STNS']==final['HTNS']==0
    cells,canon=parse(route['artifacts']['actual_netlist.v']['path']);pcells,pcanon=parse(place['artifacts']['actual_netlist.v']['path'])
    cr=routed_clockresolver(cells,canon);pr=routed_clockresolver(pcells,pcanon)
    ios=io((run/'reader_landmark_phy.area').read_text());assert len(ios)==81 and ios==review['IO_rows']
    clocks=freq((run/'reader_landmark_pr.timing').read_text());assert clocks==review['regular_clock_frequencies']
    xml=(run/'clocks.txt').read_text();assert sum(int(n)for n in re.findall(r'<clock_group[^>]* size="(\d+)"',xml))==18
    macros=[];clock_aliases=[]
    for row in review['macro26']:
        n=row['name'];c,p=cells[n],pcells[n];assert c['type']==p['type']and c['params']==p['params']
        cp={k:canon(v)for k,v in c['ports'].items()};pp={k:pcanon(v)for k,v in p['ports'].items()}
        for k in cp:
            if cp[k]!=pp.get(k)and k in['clka','clkb','core_clk','timer_clk','fb_clk','fbclk','refclk']:
                assert cr(cp[k])==pr(pp[k])
                clock_aliases.append(dict(macro=n,pin=k,routed_net=cp[k],place_net=pp[k],same_actual_root=cr(cp[k])))
                cp[k]=pp[k]
        assert cp==pp,('routed macro',n);macros.append(n)
    assert len(macros)==26
    mcu=[(n,c)for n,c in cells.items()if c['type']=='PH1P_PHY_MCU'];assert len(mcu)==1
    mcu_name,mcu_cell=mcu[0];vector_bits=re.fullmatch(r'"32\'b([01]{32})"',mcu_cell['params']['MCU_RESET_VECTOR'])
    assert vector_bits and int(vector_bits[1],2)==0x20E00000 and mcu_cell['params']['AHB_FREQ']=='"50.0"'
    dbg={k:mcu_cell['ports'][k]for k in['dbg_stop','dbg_stop_at_boot','dbg_stop_on_reset']};assert all(v=="1'b0"for v in dbg.values())
    # The two clockless DSP anchors are outside macro26 and get separate
    # parameter/full-port preservation checks.
    for row in review['anchors10']:
        n='\\'+row['name'];c,p=cells[n],pcells[n];assert c['type']==p['type']and c['params']==p['params']
        if c['type']=='PH1P_PHY_DSPSIOU_V2':assert {k:canon(v)for k,v in c['ports'].items()}=={k:pcanon(v)for k,v in p['ports'].items()}
    registered=[]
    for n,c in cells.items():
        if c['type']!='PH1P_PHY_LSLICE':continue
        for h,pin in[('A','oqa'),('B','oqb')]:
            if pin in c['ports']and c['params'].get('OQ'+h+'MUX')=='"Q'+h+'"':
                q=canon(c['ports'][pin])
                if q!='UNCONNECTED_SINGLE_USE':registered.append((n,h,q,c,pin))
    mapping=read(GUIDED/'placed_asr_mapping.json');wanted={canon(x['logical'])for x in review['fresh_ASR_registered12']};chosen=set();serial=[]
    source=r'\u_hdmi_reset/release_ff[2]';src=[x for x in registered if x[2]==canon(source)];assert len(src)==1
    assert cr(src[0][3]['ports']['clk'])[1]==4
    for row in review['fresh_ASR_registered12']:
        x=[z for z in registered if z[2]==canon(row['logical'])];assert len(x)==1
        n,h,q,c,pin=x[0];assert n==row['physical']and h==row['half']
        stage=int(re.search(r'\[(\d+)\]$',row['logical'])[1]);prev="1'b1"if stage==0 else canon(row['logical'].rsplit('[',1)[0]+'['+str(stage-1)+']')
        assert c['params']['REG'+h+'_SD']=='"IM'+h+'"'and canon(c['ports']['im'+h.lower()])==prev
        assert c['params']['ASRMUX']=='"INV"'and c['params']['REG'+h+'_REGSET_ASYNC']=='"RESET"'and canon(c['ports']['asr'])==canon(source)
        assert cr(c['ports']['clk'])==(cr(src[0][3]['ports']['clk'])[0],5)
        chosen.add(n);serial.append(dict(logical=row['logical'],physical=n,half=h))
    assert len(serial)==12 and len(chosen)==gate['ASR_count']
    assert not[x for x in registered if x[0]in chosen and x[2]not in wanted]
    assert sorted(n.lstrip('\\')+'.asr'for n in chosen)==mapping['pins']
    psi_pre=read(GUIDED/'psi17_endpoint_precheck.json');launch={};psi_actual=[]
    for row in psi_pre['registers']:
        x=[z for z in registered if z[2]==canon(row['logical'])];assert len(x)==1
        n,h,q,c,pin=x[0];assert n==row['physical']and h==row['half']and cr(c['ports']['clk'])==tuple(row['clockroot'])
        launch[n.lstrip('\\')+'.'+pin]=row['logical'];psi_actual.append(dict(logical=row['logical'],physical=n,half=h,outputpin=pin))
    assert len(launch)==17
    ex=(run/'all_held_data.timing').read_text(errors='replace');ig=(run/'all_ignored_data.timing').read_text(errors='replace')
    psi=summaries(ex,'set_max_delay','return_psi_q8');asr=summaries(ig,'set_false_path','u_hdmi_reset/release_ff[2]')
    assert len(psi)==1 and psi[0]['check']=='Max'and all(psi[0][k]==v for k,v in dict(total=17,active=17,shadowed=0,ignored=0).items())
    assert len(asr)==2 and{x['check']for x in asr}=={'Max','Min'}
    assert all(all(x[k]==v for k,v in dict(total=gate['ASR_count'],active=gate['ASR_count'],shadowed=0,ignored=0).items())for x in asr)
    assert all(x['command']==(GUIDED/'asr_literal.sdc').read_text().strip()for x in asr)
    sections=[x for x in ex.split('Timing details for constraint:')[1:]if'return_psi_q8'in x.split('\n',3)[1]];assert len(sections)==1
    paths=[]
    for m in re.finditer(r'^Slack\s*:\s*(-?[0-9.]+)ns\s*\nBegin Point\s*:\s*([^\n]+)\nEnd Point\s*:\s*([^\n]+)\n(.*?)(?=^Slack\s*:|\Z)',sections[0],re.M|re.S):
        slack,begin,end,detail=float(m[1]),m[2],m[3],m[4]
        assert slack>=0 and'clock MCU_ROI_50 'in begin and'clock HDMI_PIXEL_CLK 'in end
        assert re.search(r'^Budget\s*:\s*7\.200ns',detail,re.M)
        q=re.search(r'^clk2q[^\n]*pin: ([^\n]+)',detail,re.M);assert q and q[1]in launch
        paths.append(dict(logical_source=launch[q[1]],launch_pin=q[1],begin=begin,endpoint=end,slack_ns=slack,budget_ns=7.2))
    assert len(paths)>=17 and {x['launch_pin']for x in paths}==set(launch)and len({x['endpoint'].split()[0]for x in paths})==17
    cap=read(HERE/'capture_final_gate.json');assert cap['passed']and cap['ROUTED_DB']==route['output']and cap['checks']==36
    scope_path=HERE/'guided_native_scope_review.json';scope=read(scope_path)
    assert scope['passed']and scope['routed_DB']==route['output']and scope['clock_count']==18
    out=dict(passed=True,status='PASS_GUIDED_ACTUAL_FINAL_INDEPENDENT_PHYSICAL_REVIEW',route=ref(receipt),source_DB=route['output'],manifest=route['manifest'],auditor=ref(__file__),
        place_review=ref(GUIDED/'clock_macro_postplace_review.json'),fresh_ASR_mapping=ref(GUIDED/'placed_asr_mapping.json'),physical_IO_count=81,all81_rows_preserved=True,
        clock_count=18,clock_frequencies=clocks,native_ordinary_scope=ref(scope_path),serial_registered12=serial,physical_ASR_count=len(chosen),no_foreign_ASR_half=True,
        PSI_actual_sources17=psi_actual,PSI_SMD_summary=psi,PSI_final_paths17=paths,ASR_Max_Min_summary=asr,
        macro26_params_ports_INIT_preserved=macros,routed_clock_distribution_aliases=clock_aliases,UI_Logo_boot_INIT_preserved=720,ROI_capture_ERAMs_preserved=12,clockless_DSP2_preserved=True,
        actual_MCU=dict(name=mcu_name,reset_vector_hex='0x20E00000',AHB_FREQ_MHz=50.0,debug_stop_ports=dbg),
        actual_capture36=ref(HERE/'capture_final_gate.json'),FINAL=final,DRC_passed=True,resources=route['resources'],after_car_reserve=route['after_rover_reserve'],
        bitgen_from_this_accepted_DB_recommended=True,board_or_Flash_download_admission=False,device_actions=False,
        limitations=['Resource car Slice reserve is26short atplace; report actual routed value, do not conceal it.',
            'Physical-only bitgen recommendation; MCU firmware/model/ABI delivery pairing remains parent-owned.',
            'No claim of new real-board camera/axis/needle/PSI accuracy.'])
    write(HERE/'guided_final_physical_review.json',out)
    print(json.dumps(dict(passed=True,gate=ref(HERE/'guided_final_physical_review.json'),PSI_min_slack_ns=min(x['slack_ns']for x in paths),FINAL=final),ensure_ascii=False))


if __name__=='__main__':main()
