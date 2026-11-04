"""Derive semantic DDR grouping and exact packed serial reset endpoints.

No previous synthesized cell identifiers or physical ASR counts are copied.
These functions only inspect actual exported netlists and emit review inputs.
"""
from pathlib import Path
import collections
import re
from source_helpers import ref, write


def parse(path):
    text = Path(path).read_text(encoding='utf-8')
    pattern = re.compile(r'^  ((?:AL_MAP_|PH1P_)[A-Za-z0-9_]+)\s*(?:#\((.*?)\)\s*)?(?://[^\n]*\n\s*)*((?:\\\S+)|(?:[A-Za-z_$][\w$]*))\s+\((.*?)\);', re.M|re.S)
    norm = lambda value: re.sub(r'\s+', '', value)
    cells = {}
    for m in pattern.finditer(text):
        cells[m[3]] = {'type':m[1], 'ports':{k:norm(v) for k,v in re.findall(r'\.(\w+)\((.*?)\)(?:,|\s*$)', m[4], re.M)},
                       'params':dict(re.findall(r'^\s*\.(\w+)\((.*?)\)(?:,|\s*$)', m[2] or '', re.M))}
    aliases = {}
    for m in re.finditer(r'^  buf\s+\S+\s+\((.*?)\);', text, re.M):
        parts = [norm(s) for s in m[1].split(',')]
        assert len(parts) == 2
        aliases[parts[0]] = parts[1]
    counts = collections.Counter(re.findall(r'\bopen_n\d+\b', text))
    assert not counts or set(counts.values()) == {1}, 'Only globally single-use opens may normalize'
    def canon(net):
        seen = set()
        while net in aliases and net not in seen:
            seen.add(net)
            net = aliases[net]
        return re.sub(r'\bopen_n\d+\b', 'UNCONNECTED_SINGLE_USE', net)
    return cells, canon


def derive_ddr(netlist, output):
    cells, canon = parse(netlist)
    page = r'\u_ph1p35_324_ddr_wrapper/u_ddr2/ph1p_ddrmc_wrapper/ph1p_ddrmc_top/u_alc_mc_top/page_ctrl[2]$u_page_ctrl/'
    nets = [page+'cmdRow[1]', page+'txn_fifo_rptr_nxt[0]']
    drivers, loads = collections.defaultdict(list), collections.defaultdict(list)
    def is_output(cell, pin):
        return cell['type']=='AL_MAP_SEQ_GSR' and pin=='q' or cell['type'].startswith('AL_MAP_LUT') and pin=='o'
    for name, cell in cells.items():
        for pin, net in cell['ports'].items():
            (drivers if is_output(cell,pin) else loads)[canon(net)].append((name,pin))
    members = set()
    net_records = []
    for net in nets:
        ds, ls = drivers[canon(net)], loads[canon(net)]
        assert len(ds)==1, (net,ds)
        members.update(name for name,pin in ds+ls)
        net_records.append({'net':net.lstrip('\\'),'drivers':ds,'loads':ls})
    endpoint = page+'cas_fifo_empty_reg'
    assert cells[endpoint]['type']=='AL_MAP_SEQ_GSR'
    target = canon(cells[endpoint]['ports']['d'])
    todo = collections.deque([(canon(nets[0]),[])])
    seen = set()
    path = None
    while todo:
        net, history = todo.popleft()
        if net==target:
            path=history
            break
        if net in seen or len(history)>=8:
            continue
        seen.add(net)
        for name,pin in sorted(loads[net]):
            cell=cells[name]
            if cell['type'].startswith('AL_MAP_LUT'):
                todo.append((canon(cell['ports']['o']),history+[name]))
    assert path is not None, 'Semantic DDR path not found within eight LUTs'
    members.update(path)
    members.add(endpoint)
    assert all(cells[n]['type']=='AL_MAP_SEQ_GSR' or cells[n]['type'].startswith('AL_MAP_LUT') for n in members)
    clocks={canon(cells[n]['ports']['clk']) for n in members if cells[n]['type']=='AL_MAP_SEQ_GSR'}
    assert len(clocks)==1, clocks
    names=sorted(n.lstrip('\\') for n in members)
    plan={'derived':True,'netlist':ref(netlist),'nets':net_records,'semantic_path':[n.lstrip('\\') for n in path],
          'members':names,'member_count':len(names),'sequential_clock':list(clocks),'bound':{'origin':[3,41],'width':8,'height':8,'mode':'soft','exclusive':False},
          'old_member_names_copied':False,'device':False}
    output=Path(output)
    write(output/'ddr_group_plan.json',plan)
    query='set ddr_group_member_names {'+' '.join(names)+'}\n'
    query+='foreach member $ddr_group_member_names {\n set o [get_cells $member]\n if {[llength $o] != 1} {error "DDR_MEMBER_NOT_UNIQUE: $member"}\n report_cells $o -attributes -connection\n}\n'
    query+='create_bound {ddr_critical_group} -mode soft -width 8 -height 8 -origin {3 41}\n'
    query+='add_cells_to_bound -bound {ddr_critical_group} -cells $ddr_group_member_names\nputs {UI_DDR_SEMANTIC_GROUP_APPLIED}\n'
    (output/'ddr_group.tcl').write_text(query,encoding='ascii')
    return plan


def vector(expr):
    items=expr[1:-1].split(',') if expr.startswith('{') and expr.endswith('}') else [expr]
    result=[]
    for item in items:
        m=re.fullmatch(r'(.+)\[(\d+):(\d+)\]',item)
        literal=re.fullmatch(r"(\d+)'b([01xz]+)",item)
        if m:
            hi,lo=int(m[2]),int(m[3])
            result.extend(m[1]+'['+str(i)+']' for i in range(hi,lo+(-1 if hi>=lo else 1),-1 if hi>=lo else 1))
        elif literal:
            assert len(literal[2])==int(literal[1])
            result.extend("1'b"+bit for bit in literal[2])
        else:
            result.append(item)
    return result


def derive_asr(netlist, placed_db, syn_netlist, group, adc_file, output):
    cells,canon=parse(netlist)
    registered=[]
    outputs=collections.defaultdict(list)
    for name,cell in cells.items():
        if cell['type']!='PH1P_PHY_LSLICE':
            continue
        for half,pin in [('A','oqa'),('B','oqb')]:
            if pin not in cell['ports']:
                continue
            q=canon(cell['ports'][pin])
            outputs[q].append((name,pin))
            if q!='UNCONNECTED_SINGLE_USE' and cell['params'].get('OQ'+half+'MUX')=='"Q'+half+'"':
                registered.append({'cell':name,'half':half,'output':q,'ports':cell['ports'],'params':cell['params']})
        for pin in ['ofa','ofb','fco','fco_f']:
            if pin in cell['ports']:
                outputs[canon(cell['ports'][pin])].append((name,pin))
    clocks={}
    for name,cell in cells.items():
        typ,ps=cell['type'],cell['ports']
        if typ=='PH1P_PHY_PLL_V2':
            for bit,net in enumerate(reversed(vector(ps['clkc']))):
                if not net.startswith('open_n'):
                    clocks[canon(net)]=('PLL',name,bit)
        elif typ=='PH1P_PHY_GCLK':
            assert ps['seln']=="2'b10" and ps['drct']=="2'b11"
            clocks[canon(ps['clkout'])]=('BUF',vector(ps['clkin'])[-1])
        elif typ in ['PH1P_PHY_IOCLK','PH1P_PHY_MLCLK'] and 'clkout' in ps and 'clkin' in ps:
            clocks[canon(ps['clkout'])]=('BUF',ps['clkin'])
    def root(net):
        seen=set()
        net=canon(net)
        while True:
            assert net not in seen and net in clocks, ('clock root',net)
            seen.add(net)
            v=clocks[net]
            if v[0]=='PLL':
                return {'cell':v[1].lstrip('\\'),'bit':v[2]}
            net=canon(v[1])
    source=r'\u_hdmi_reset/release_ff[2]'
    sr=[r for r in registered if r['output']==canon(source)]
    assert len(sr)==1
    parent=root(sr[0]['ports']['clk'])
    assert parent['bit']==4
    expected={r'\u_hdmi_tx/u_hdmi2phy_wrapper/u'+str(lane)+'_lane_lvds_8_1/u_serial_reset/release_ff['+str(stage)+']':(lane,stage) for lane in range(4) for stage in range(3)}
    chosen=set()
    records=[]
    for logical,(lane,stage) in expected.items():
        rows=[r for r in registered if r['output']==canon(logical)]
        assert len(rows)==1, (logical,rows)
        r=rows[0]
        half,ps,ports=r['half'],r['params'],r['ports']
        assert ps['REG'+half+'_SD']=='"IM'+half+'"'
        want="1'b1" if stage==0 else canon(logical.rsplit('[',1)[0]+'['+str(stage-1)+']')
        assert canon(ports['im'+half.lower()])==want
        assert canon(ports['asr'])==canon(source) and ps['ASRMUX']=='"INV"' and ps['REG'+half+'_REGSET_ASYNC']=='"RESET"'
        cr=root(ports['clk'])
        assert cr['cell']==parent['cell'] and cr['bit']==5
        chosen.add(r['cell'])
        records.append({'logical':logical.lstrip('\\'),'lane':lane,'stage':stage,'physical':r['cell'].lstrip('\\'),'half':half,'D':want,'clock_root':cr})
    foreign=[r for r in registered if r['cell'] in chosen and r['output'] not in {canon(n) for n in expected}]
    assert not foreign, 'Selected ASR also controls nonserial registered consumers'
    pins=sorted(n.lstrip('\\')+'.asr' for n in chosen)
    syn,sc=parse(syn_netlist)
    packed=[]
    for logical in group['members']:
        old=syn['\\'+logical]
        q=old['ports']['q' if old['type']=='AL_MAP_SEQ_GSR' else 'o']
        matches=outputs.get(canon(q),[])
        if not matches and old['type'].startswith('AL_MAP_LUT'):
            receivers=[c for c in syn.values() if c['type']=='AL_MAP_SEQ_GSR' and sc(c['ports']['d'])==sc(q)]
            matches=[v for c in receivers for v in outputs.get(canon(c['ports']['q']),[])]
        assert len(matches)==1, ('DDR packed mapping',logical,matches)
        packed.append({'logical':logical,'packed_cell':matches[0][0].lstrip('\\'),'pin':matches[0][1]})
    adc=Path(adc_file).read_text()
    adc_members=re.findall(r'add_cells_to_bound\s+-bound\s+\{\s*ddr_critical_group\s*\}\s+-cells\s+\{\s*([^}]+?)\s*\}',adc)
    assert set(adc_members)==set(group['members'])
    assert re.search(r'create_bound\s+\{\s*ddr_critical_group\s*\}\s+-mode soft\s+-width 8\s+-height 8\s+-origin\s+\{\s*3 41\s*\}',adc)
    result={'derived':True,'placed_DB':ref(placed_db),'placed_netlist':ref(netlist),'logical_FF_count':12,
            'physical_ASR_count':len(pins),'pins':pins,'records':records,'source':source.lstrip('\\'),'parent_clock':parent,
            'nonserial_registered_consumers':[],'DDR_packed_mapping':packed,'old_physical_pins_copied':False,'device':False}
    output=Path(output)
    write(output/'placed_asr_mapping.json',result)
    asr='set_false_path -through [get_nets {'+source.lstrip('\\')+'}] -to [get_pins {'+' '.join(pins)+'}]\n'
    psi='set_max_delay -from [get_regs {u_meter_pair/pipeline/reader/live/return_psi_q8[*] u_meter_pair/pipeline/reader/live/return_psi_valid}] -to [get_clocks {HDMI_PIXEL_CLK}] -datapath_only 7.200\n'
    (output/'asr_literal.sdc').write_text(asr,encoding='ascii')
    (output/'psi_literal.sdc').write_text(psi,encoding='ascii')
    return result
