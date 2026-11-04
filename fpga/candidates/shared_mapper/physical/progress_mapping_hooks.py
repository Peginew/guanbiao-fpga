"""Fresh placed-netlist identity hooks for held progress32 and two2FF chains.

This is host structural derivation only. Output candidates must undergo new
clock roots, Tco, consumer/data, handshake and native literal-effect review.
No old SDC or physical identifier is accepted as the new constraints.
"""
from pathlib import Path
import json
from source_helpers import ref,write
from mapping_helpers import parse

def _one_registered_q(cells,canon,logical):
    rows=[]
    for name,cell in cells.items():
        if cell['type']!='PH1P_PHY_LSLICE':continue
        for half,q in [('A','oqa'),('B','oqb')]:
            if cell['params'].get('OQ'+half+'MUX')=='"Q'+half+'"' and q in cell['ports'] and canon(cell['ports'][q])==canon(logical):
                rows.append({'logical_Q':logical,'physical':name,'half':half,'Q_pin':q,
                  'pin':name.lstrip('\\')+'.'+q,'D_net':cell['ports'].get('im'+half.lower()),
                  'actual_params':cell['params'],'actual_ports':cell['ports']})
    assert len(rows)==1,(logical,len(rows))
    return rows[0]

def derive_progress(netlist,placed_db,output,held_prefix,sync_prefix,ack_sync_prefix):
    """Call only on the fresh accepted placement with independently checked names."""
    cells,canon=parse(netlist)
    held=[_one_registered_q(cells,canon,held_prefix+f'[{i}]') for i in range(32)]
    sync=[_one_registered_q(cells,canon,prefix+f'[{i}]') for prefix in [sync_prefix,ack_sync_prefix] for i in range(2)]
    assert len({r['pin'] for r in held})==32
    assert len({r['pin'] for r in sync})==4
    for row0,row1 in [sync[:2],sync[2:]]:
        assert canon(row1['D_net'])==canon(row0['logical_Q']),('Not a serial2FF chain',row0,row1)
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    pins=[r['pin'] for r in held]
    candidate='set_max_delay -from [get_pins {'+' '.join(pins)+'}] -to [get_clocks {HDMI_PIXEL_CLK}] -datapath_only 7.200\n'
    (out/'progress32_exact_Q_candidate.sdc').write_text(candidate,'ascii')
    proof={'status':'FRESH_PROGRESS_STRUCTURAL_IDENTITY_ONLY_REQUIRES_INDEPENDENT_REVIEW',
      'placed_DB':ref(placed_db),'placed_netlist':ref(netlist),'held_logic_bits':32,
      'held_Q_pin_count':32,'new_synchronizer_logic_FF_count':4,
      'held_sources':held,'sync_stages':sync,'actual_serial2FF_links_checked':True,
      'candidate_literal':ref(out/'progress32_exact_Q_candidate.sdc'),
      'clock_Tco_held_handshake_reviewed':False,'native_SDC_effective':False,
      'constraints_admitted_for_route':False,'old_physical_pins_copied':False,'device':False}
    write(out/'progress32_endpoint_precheck.json',proof)
    return proof

def native_probe_contract():
    return '''# Append after qualified pure read_sdc files and BEFORE first timer.
report_timing_exception -ep_num 256 -path_num 1 -file pre_contract_exception.timing
report_timing_ignored -ep_num 64 -path_num 1 -file pre_contract_ignored.timing
# Root must parse separate Max/Min SMD rows: PSI17/17 and progress32/32,
# and derive reset ASR plus exact first-stage CDC exceptions from this DB.
# Do not route/export merely because a marker or get_regs count was nonzero.
'''

if __name__=='__main__':
    print(json.dumps({'status':'HOOKS_PREPARED_NO_NETLIST_NO_TD','held_bits':32,
      'new_sync_logic_FF':4,'actual_derivation_required':True,'device':False}))
