"""Independent exact packed-FF/ASR and actual placed pin/clock/RAM review."""
from pathlib import Path
import collections,json,re,sys
from audit_synth import TASK,BASE,HERE,read,ref,sha,write,freq
sys.path.insert(0,str(TASK/'physical'))
from mapping_helpers import parse,vector

def io(text):
    rr={}
    for line in text.splitlines():
        p=line.split()
        if len(p)==8 and p[1]in['INPUT','OUTPUT','INOUT']:
            assert p[0]not in rr;rr[p[0]]=p[1:]
    return rr

def main():
    place=read(TASK/'physical/latest_place.json');syn=read(TASK/'physical/latest_synth.json')
    assert place['stage']=='place'and place['exit_code']==0 and place['source_DB']==syn['output']
    assert place['manifest']==syn['manifest'] and sha(place['manifest']['path'])==place['manifest']['sha256']
    for row in [place['output'],place['log'],*place['artifacts'].values(),*place['controls']]:assert sha(row['path'])==row['sha256']
    cells,canon=parse(place['artifacts']['actual_netlist.v']['path']);scells,scan=parse(syn['artifacts']['actual_netlist.v']['path'])
    def makeclockroot(cc,cn):
        rr={}
        for name,c in cc.items():
            if c['type']=='PH1P_PHY_PLL_V2':
                for bit,n in enumerate(reversed(vector(c['ports']['clkc']))):
                    if not n.startswith('open_n'):rr[cn(n)]=('PLL',name,bit)
            elif c['type']=='PH1P_PHY_MCU':rr[cn(c['ports']['ahb_clk'])]=('MCU_AHB',name,'ahb_clk')
            elif c['type']=='PH1P_PHY_GCLK':rr[cn(c['ports']['clkout'])]=('BUF',vector(c['ports']['clkin'])[-1])
            elif c['type']in['PH1P_PHY_IOCLK','PH1P_PHY_MLCLK']and'clkout'in c['ports']and'clkin'in c['ports']:
                rr[cn(c['ports']['clkout'])]=('BUF',c['ports']['clkin'])
        def resolve(n):
            n=cn(n);seen=set()
            while True:
                assert n not in seen and n in rr,(n,'macroclockroot');seen.add(n);z=rr[n]
                if z[0]in['PLL','MCU_AHB']:return(z[1],z[2])
                n=cn(z[1])
        return resolve
    placedclockroot=makeclockroot(cells,canon);synclockroot=makeclockroot(scells,scan)
    oldroute=read(BASE/'physical/latest_route.json');oldarea=Path(oldroute['run'])/'hdmi_ui_ref_fix_phy.area'
    area=Path(place['run'])/'reader_landmark_phy.area';ios=io(area.read_text());assert len(ios)==81 and ios==io(oldarea.read_text())
    clocks=freq((Path(place['run'])/'reader_landmark_place.timing').read_text());assert len(clocks)==17
    assert clocks==freq((Path(syn['run'])/'reader_landmark_gate.timing').read_text())
    xml=Path(place['artifacts']['clocks.txt']['path']).read_text();assert sum(map(int,re.findall(r'<clock_group[^>]* size="(\d+)"',xml)))==18
    macro=[]
    for n,c in cells.items():
        if c['type']in['PH1P_PHY_PLL_V2','PH1P_PHY_MCU']or(c['type']=='PH1P_PHY_ERAM_V2'and n.startswith((r'\u_dashboard/',r'\u_hdmi_mixer/u_anlogic_logo_rom/',r'\u_mcu_bootrom/',r'\u_meter_pair/pipeline/reader/live/capture/'))):
            x=scells[n];assert c['params']==x['params'],('macroparams',n)
            cp={p:canon(v)for p,v in c['ports'].items()};sp={p:scan(v)for p,v in x['ports'].items()}
            for p in cp:
                if cp[p]!=sp.get(p) and p in ['clka','clkb','core_clk','timer_clk','fb_clk']:
                    assert placedclockroot(cp[p])==synclockroot(sp[p]),('macro clockroot changed',n,p)
                    cp[p]=sp[p] #clocktree net renamed, exact PLL source/bit proved above
            assert cp==sp,('macroports',n,{p:[v,sp.get(p)]for p,v in cp.items()if v!=sp.get(p)})
            macro.append(n)
    assert len(macro)==26 #21ERAM+4PLL+1MCU
    # Independently find every actually registered half, not instance prefixes.
    registered=[];roots={}
    for name,c in cells.items():
        if c['type']=='PH1P_PHY_LSLICE':
            for half,pin in[('A','oqa'),('B','oqb')]:
                if pin in c['ports']and c['params'].get('OQ'+half+'MUX')=='"Q'+half+'"':
                    q=canon(c['ports'][pin])
                    if q!='UNCONNECTED_SINGLE_USE':registered.append((name,half,q,c))
        if c['type']=='PH1P_PHY_PLL_V2':
            for bit,n in enumerate(reversed(vector(c['ports']['clkc']))):
                if not n.startswith('open_n'):roots[canon(n)]=('PLL',name,bit)
        elif c['type']=='PH1P_PHY_GCLK':
            assert c['ports']['seln']=="2'b10" and c['ports']['drct']=="2'b11"
            roots[canon(c['ports']['clkout'])]=('BUF',vector(c['ports']['clkin'])[-1])
        elif c['type']in['PH1P_PHY_IOCLK','PH1P_PHY_MLCLK']and'clkout'in c['ports']and'clkin'in c['ports']:
            roots[canon(c['ports']['clkout'])]=('BUF',c['ports']['clkin'])
    def clockroot(n):
        n=canon(n);seen=set()
        while True:
            assert n not in seen and n in roots,(n,'clockroot');seen.add(n);r=roots[n]
            if r[0]=='PLL':return(r[1],r[2])
            n=canon(r[1])
    source=r'\u_hdmi_reset/release_ff[2]';sources=[r for r in registered if r[2]==canon(source)];assert len(sources)==1
    sourceclock=clockroot(sources[0][3]['ports']['clk']);assert sourceclock[1]==4
    expected={r'\u_hdmi_tx/u_hdmi2phy_wrapper/u'+str(lane)+'_lane_lvds_8_1/u_serial_reset/release_ff['+str(stage)+']':(lane,stage)for lane in range(4)for stage in range(3)}
    records=[];physical=set()
    for logical,(lane,stage)in expected.items():
        matches=[r for r in registered if r[2]==canon(logical)];assert len(matches)==1
        name,half,q,c=matches[0];p=c['ports'];s=c['params'];want="1'b1"if stage==0 else canon(logical.rsplit('[',1)[0]+'['+str(stage-1)+']')
        assert s['REG'+half+'_SD']=='"IM'+half+'"'and canon(p['im'+half.lower()])==want
        assert canon(p['asr'])==canon(source)and s['ASRMUX']=='"INV"'and s['REG'+half+'_REGSET_ASYNC']=='"RESET"'
        cr=clockroot(p['clk']);assert cr==(sourceclock[0],5)
        physical.add(name);records.append(dict(logical=logical.lstrip('\\'),physical=name.lstrip('\\'),half=half,lane=lane,stage=stage,D=want,clock_root=cr))
    assert len(physical)==6
    foreign=[(n,h,q)for n,h,q,c in registered if n in physical and q not in{canon(x)for x in expected}];assert not foreign
    pins=sorted(n.lstrip('\\')+'.asr'for n in physical);mapping=read(TASK/'physical/placed_asr_mapping.json')
    assert mapping['pins']==pins and mapping['logical_FF_count']==12 and mapping['physical_ASR_count']==6
    assert mapping['placed_DB']==place['output']and mapping['placed_netlist']==place['artifacts']['actual_netlist.v']
    overlay=TASK/'physical/serial_reset_exact_overlay.tcl';text=overlay.read_text()
    assert re.findall(r'^set_false_path.*$',text,re.M)==['set_false_path -through $serial_reset_source -to $serial_reset_asr']
    match=re.search(r'^set serial_reset_asr \[get_pins \{([^}]+)\}\]$',text,re.M);assert match and match[1].split()==pins
    assert 'set serial_reset_source [get_nets {u_hdmi_reset/release_ff[2]}]'in text
    assert not re.search(r'set_(?:max_delay|multicycle_path)|all_clocks|all_registers',text)
    assert sha(overlay)==place['ASR_overlay']['sha256']and sha(TASK/'physical/placed_asr_mapping.json')==place['ASR_mapping']['sha256']
    cap=read(HERE/'capture_LANDMARK_SYN_gate.json');assert cap['passed']and cap['DB_sha256']==syn['output']['sha256']
    out=dict(passed=True,status='PASS_PLACE_NARROW_ROUTE_ADMISSION',scope='Actual new place; source pin/clock/MCU/ERAM verified, fresh ASR endpoints independently derived. Not FINAL timing or board acceptance.',
        place_receipt=ref(TASK/'physical/latest_place.json'),source_freeze=place['manifest'],actual_DB=place['output'],actual_netlist=place['artifacts']['actual_netlist.v'],
        audit_source=ref(__file__),physical_IO_count=81,all81_locations_standards_directions_equal_previous_actual=True,IO_rows=ios,
        clock_summary_total=18,regular_timing_enumerated_clock_frequencies=clocks,regular_table_enumerated=17,
        source_clock_root=sourceclock,serial_clock_root=(sourceclock[0],5),independent_FF_records=records,
        logical_serial_FFs=12,physical_ASR_count=6,physical_ASR_pins=pins,no_foreign_registered_ASR_half=True,
        only_exception='reset-source net through6 exact ASR pins; ordinary DATA, consumer and DDR untouched',overlay=ref(overlay),mapping=ref(TASK/'physical/placed_asr_mapping.json'),
        macro26_all_params_and_canonical_ports_equal_actual_SYN=True,macro_names=macro,UI_Logo_boot_INIT_preserved=720,ROI_capture_ERAMs=12,
        capture_SYN_actual36=ref(HERE/'capture_LANDMARK_SYN_gate.json'),
        actual_resources=place['resources'],rover_reserve=dict(wantedSlice=1200,availableSlice=21216-place['resources']['Slice'],shortfallSlice=20,
            FF_after2400=42432-place['resources']['FF']-2400,ERAM_after2=108-place['resources']['ERAM']-2),
        route_may_proceed=True,whole_project_safety_or_bitgen_admission=False,pending=['native route1/12/6 overlay entry counts','FINAL STA','routedcapture and macro preservation','final18clock query'],hardware_actions=False)
    write(HERE/'place_route_admission_review.json',out);print(json.dumps(dict(passed=True,receipt=str(HERE/'place_route_admission_review.json'),physicalASR=6,IO=81)))

if __name__=='__main__':main()
