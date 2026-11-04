"""Generate the fresh free-UI DefaultFlow editable place zone, never run TD.

Macro names must come from the new SYN inventory. No previous macro coordinates,
UI LOC assignments, packed physical identifiers or old DDR member Tcl are copied.
"""
from source_helpers import FLOW,NAME

def macro_observation(names,phase):
    assert names and len(names)==len(set(names))
    lines=['puts {STAGED_MACRO_'+phase+'_BEGIN}']
    for name in names:
        assert not any(c in name for c in '{}\r\n')
        lines+=['puts {BEGIN_STAGED_'+phase+' '+name+'}',
                'set o [get_cells {'+name+'}]',
                'if {[llength $o] != 1} {error {STAGED_MACRO_NOT_UNIQUE}}',
                'report_cells $o -attributes -connection',
                'puts {END_STAGED_'+phase+' '+name+'}']
    return '\n'.join(lines)+'\n'

def generated_flow(fresh_macro_names):
    flow=FLOW.read_text(encoding='ascii')
    a=flow.index('### Editable zone for opt_place ###')
    b=flow.index('###################################',a)
    zone='''### Editable zone for opt_place ###
  source ddr_group.tcl
  puts {STAGED_FREE_UI_NO_TEN_LOC_DDR_GROUP_LOADED}
'''+macro_observation(fresh_macro_names,'PRE')+f'''  place
  report_area -io_info -file {NAME}_phy.area
  export_db {NAME}_place.db
  export_adc -file actual.adc
  write_verilog actual_netlist.v
  update_timing -mode manhattan
  report_timing_summary -ep_num 16 -path_num 1 -file {NAME}_place.timing
  report_clock_summary -file clocks.txt
  report_clock_utilization -file clock_utilization.txt
  flow_status -file flow.status
'''+macro_observation(fresh_macro_names,'POST')
    assert 'ui_macro_anchors' not in zone and 'set_inst_assignment' not in zone
    return flow[:a]+zone+flow[b:]
