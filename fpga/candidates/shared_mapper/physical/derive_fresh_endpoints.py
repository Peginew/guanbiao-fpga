"""Host-only actual placed endpoints for this new staged-display candidate.

Produces candidate pure SDC text, not a routing admission. Native source Tco,
first-timer registration, endpoint timing and held-bundle reviews remain pending.
"""
from pathlib import Path
import json
from source_helpers import read,write,ref,verify_ref,validate_manifest
from mapping_helpers import parse,vector,derive_asr
from progress_mapping_hooks import _one_registered_q

HERE=Path(__file__).resolve().parent
OUT=HERE/'endpoints'
LIVE=r'\u_meter_pair/pipeline/reader/live/'
PIPE=r'\u_meter_pair/pipeline/'

def main():
    validate_manifest(HERE/'source_freeze.json')
    place=read(HERE/'latest_place.json');syn=read(HERE/'latest_synth.json')
    assert place['passed'] and syn['passed'] and place['exit_code']==syn['exit_code']==0
    assert place['manifest']==syn['manifest']==ref(HERE/'source_freeze.json')
    assert place['source_DB']==syn['output']
    group=read(HERE/'ddr_group_plan.json')
    assert group['member_count']==38 and group['netlist']==syn['artifacts']['actual_netlist.v']
    for x in [place['output'],place['artifacts']['actual_netlist.v'],place['artifacts']['actual.adc'],syn['artifacts']['actual_netlist.v']]:verify_ref(x)
    assert not OUT.exists(),'Preserve previous derivation; no implicit overwrite'
    assert not any((HERE/n).exists() for n in ['placed_asr_mapping.json','asr_literal.sdc','psi_literal.sdc'])
    asr=derive_asr(place['artifacts']['actual_netlist.v']['path'],place['output']['path'],
                   syn['artifacts']['actual_netlist.v']['path'],group,
                   place['artifacts']['actual.adc']['path'],HERE)
    cells,canon=parse(place['artifacts']['actual_netlist.v']['path'])
    clocks={}
    for name,cell in cells.items():
        typ,ps=cell['type'],cell['ports']
        if typ=='PH1P_PHY_PLL_V2':
            for bit,net in enumerate(reversed(vector(ps['clkc']))):
                if not net.startswith('open_n'):clocks[canon(net)]=('PLL',name,bit)
        elif typ=='PH1P_PHY_GCLK':
            assert ps['seln']=="2'b10" and ps['drct']=="2'b11"
            clocks[canon(ps['clkout'])]=('BUF',vector(ps['clkin'])[-1])
        elif typ in ['PH1P_PHY_IOCLK','PH1P_PHY_MLCLK'] and 'clkout'in ps and 'clkin'in ps:
            clocks[canon(ps['clkout'])]=('BUF',ps['clkin'])
    def root(net):
        seen=set();trail=[];net=canon(net)
        while True:
            assert net not in seen and net in clocks,('Unresolved actual clock',net,trail)
            seen.add(net);v=clocks[net];trail.append({'net':net,'driver':v})
            if v[0]=='PLL':return {'cell':v[1].lstrip('\\'),'bit':v[2],'trace':trail}
            net=canon(v[1])
    def q(logical):
        r=_one_registered_q(cells,canon,logical)
        r['clock_root']=root(r['actual_ports']['clk'])
        half=r['half'];ps=r['actual_params'];ports=r['actual_ports']
        assert ps['LATCHMODE']=='"DFF"' and ps['CLKMUX']=='"SIG"'
        assert ps['REG'+half+'_REGSET_ASYNC']=='"RESET"' and ps['ASRMUX']=='"INV"'
        r['actual_async_reset_net']=ports['asr']
        r['actual_CE_selection']=ps.get('CE'+half+'MUX')
        r['actual_D_selection']=ps.get('REG'+half+'_SD')
        return r
    def d(r):
        half=r['half'];pin='im'+half.lower()
        assert r['actual_D_selection']=='"IM'+half+'"'
        assert r['actual_CE_selection']=='"1"'
        assert pin in r['actual_ports']
        r['D_pin']=r['physical'].lstrip('\\')+'.'+pin
        r['D_net']=r['actual_ports'][pin]
        return r
    psi=[q(LIVE+f'return_psi_q8[{i}]') for i in range(16)]+[q(LIVE+'return_psi_valid')]
    held=[q(LIVE+f'progress_held_code[{i}]') for i in range(32)]
    # Map the actual output capture too; this is ordinary CORE data, not an ASR cut.
    dest=[q(LIVE+f'progress_code[{i}]') for i in range(32)]
    toggle=q(LIVE+'progress_toggle');ack=q(LIVE+'progress_ack')
    progress_sync=[d(q(LIVE+f'progress_sync[{i}]')) for i in range(2)]
    ack_sync=[d(q(LIVE+f'progress_ack_sync[{i}]')) for i in range(2)]
    cancel_src=[q(PIPE+f'first_cancel_cause[{i}]') for i in range(4)]
    cancel0=[d(q(LIVE+f'first_cancel_sync0[{i}]')) for i in range(4)]
    cancel1=[d(q(LIVE+f'first_cancel_sync1[{i}]')) for i in range(4)]
    assert canon(progress_sync[0]['D_net'])==canon(toggle['logical_Q'])
    assert canon(progress_sync[1]['D_net'])==canon(progress_sync[0]['logical_Q'])
    assert canon(ack_sync[0]['D_net'])==canon(ack['logical_Q'])
    assert canon(ack_sync[1]['D_net'])==canon(ack_sync[0]['logical_Q'])
    for s,a,b in zip(cancel_src,cancel0,cancel1):
        assert canon(a['D_net'])==canon(s['logical_Q'])
        assert canon(b['D_net'])==canon(a['logical_Q'])
    key=lambda r:(r['clock_root']['cell'],r['clock_root']['bit'])
    hclk=key(held[0]);core=key(dest[0]);assert hclk!=core
    assert all(key(r)==hclk for r in psi+held+[toggle]+ack_sync+cancel0+cancel1)
    assert all(key(r)==core for r in dest+[ack]+progress_sync+cancel_src)
    assert len({r['pin'] for r in psi})==17
    assert len({r['pin'] for r in held})==32
    OUT.mkdir()
    def data_literal(rows):
        return 'set_max_delay -from [get_pins {'+' '.join(r['pin'] for r in rows)+'}] -to [get_clocks {HDMI_PIXEL_CLK}] -datapath_only 7.200\n'
    def pair_literal(pairs):
        return ''.join('set_max_delay -from [get_pins {'+a['pin']+'}] -to [get_pins {'+b['D_pin']+'}] -datapath_only 7.200\n' for a,b in pairs)
    texts={'PSI17_exact_Q_candidate.sdc':data_literal(psi),
      'progress32_exact_Q_candidate.sdc':data_literal(held),
      'progressCtrl2_exact_QD_candidate.sdc':pair_literal([(toggle,progress_sync[0]),(ack,ack_sync[0])]),
      'diagnostic4_exact_QD_candidate.sdc':pair_literal(list(zip(cancel_src,cancel0)))}
    for name,text in texts.items():
        assert 'set_false_path' not in text and 'get_regs' not in text
        (OUT/name).write_text(text,'ascii')
    result={'status':'FRESH_PLACED_HOST_IDENTITY_AND_SERIAL_LINKS_PASS_NATIVE_PROBE_PENDING',
      'producer':ref(__file__),'place_receipt':ref(HERE/'latest_place.json'),'synth_receipt':ref(HERE/'latest_synth.json'),
      'source_DB':place['output'],'placed_netlist':place['artifacts']['actual_netlist.v'],
      'manifest':place['manifest'],'ASR':{'mapping':ref(HERE/'placed_asr_mapping.json'),'literal':ref(HERE/'asr_literal.sdc'),
         'logical_serial_FF':asr['logical_FF_count'],'actual_ASR_pins':asr['physical_ASR_count'],'only_existing_HDMI_serial12':True},
      'old_psi_get_regs_file_NOT_FOR_ROUTE':ref(HERE/'psi_literal.sdc'),
      'PSI17':psi,'progress32_sources':held,'progress32_CORE_capture':dest,
      'progress_control':{'toggle_source':toggle,'toggle_sync':progress_sync,'ack_source':ack,'ack_sync':ack_sync},
      'first_cancel_diagnostic':{'source4':cancel_src,'sync0':cancel0,'sync1':cancel1},
      'logic_counts':{'PSI_sources':17,'held_progress_sources':32,'progress_control_sources':2,
         'progress_sync_FF':4,'first_cancel_sources':4,'first_cancel_sync_FF':8},
      'all_named_sources_are_actual_registered_Q_halves':True,'sync_D_input_mux_and_serial_connections_verified':True,
      'actual_HCLK_root':held[0]['clock_root'],'actual_CORE_root':dest[0]['clock_root'],
      'candidate_literal_files':{n:ref(OUT/n) for n in texts},'added_false_paths':0,
      'clock_Tco_endpoint_hold_and_new_SDC_registration_review_pending':True,
      'ordinary_DATA_global_FINAL_pending':True,'route_admitted':False,'native_TD_run':False,'device':False}
    write(OUT/'fresh_identity.json',result)
    print(json.dumps({'status':result['status'],'logic_counts':result['logic_counts'],
       'ASR_count':asr['physical_ASR_count'],'source_DB':place['output'],
       'identity':ref(OUT/'fresh_identity.json'),'route_admitted':False,'native_TD_run':False},indent=2))

if __name__=='__main__':main()
