"""Host-only new-SYN macro identity inventory; no TD execution.

Default PLAN. --prepare reads this candidate's successful exported SYN and
the accepted d882 reference. It never copies old DDR/ASR endpoint names.
The emitted anchor plan still needs independent root admission before place.
"""
import argparse
import json
from pathlib import Path
import re
import sys

GUIDED = Path(__file__).resolve().parent
PHYSICAL = GUIDED.parent
sys.path.insert(0, str(PHYSICAL))
from source_helpers import read, write, ref, sha, verify_ref, validate_manifest
from mapping_helpers import parse

REFERENCE = PHYSICAL.parents[1] / 'meter_landmark_mcu_training_20261103' / 'physical'
MANIFEST = PHYSICAL / 'source_freeze.json'


def normalized(cell, canon):
    return {'type': cell['type'],
            'params': {k: re.sub(r'\s+', '', v) for k, v in cell['params'].items()},
            'ports': {k: canon(v) for k, v in cell['ports'].items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    if not args.prepare:
        print(json.dumps({'status': 'PLAN_ONLY', 'native_run': False, 'device': False,
            'new_syn_required': str(PHYSICAL / 'latest_synth.json'),
            'reference': str(REFERENCE / 'latest_guided_route.json'),
            'identity_policy': 'new SYN vs d882 SYN: same name, type, all params/INIT and full canonical ports',
            'positions': '10 hard macro anchors of accepted d882 parent placement; no old clockBound copying',
            'DDR': 'run_td derives semantic38 from this actual SYN; validate its source binding',
            'ASR': 'not generated at SYN; must derive from this candidate actual place',
            'outputs_require_independent_macro_anchor_admission': True}, ensure_ascii=False, indent=2))
        return
    assert __debug__, 'Assertions must remain enabled'
    validate_manifest(MANIFEST)
    syn = read(PHYSICAL / 'latest_synth.json')
    assert syn['passed'] and syn['stage'] == 'synth' and syn['manifest'] == ref(MANIFEST)
    verify_ref(syn['output'])
    new_syn = verify_ref(syn['artifacts']['actual_netlist.v'])
    group = read(verify_ref(syn['ddr_group_plan']))
    verify_ref(syn['ddr_group_tcl'])
    assert group['netlist'] == ref(new_syn) and group['member_count'] == 38 and group['derived']
    assert group['old_member_names_copied'] is False
    assert group['bound'] == {'origin': [3, 41], 'width': 8, 'height': 8, 'mode': 'soft', 'exclusive': False}

    rs = read(REFERENCE / 'latest_synth.json')
    rp = read(REFERENCE / 'latest_guided_place.json')
    rr = read(REFERENCE / 'latest_guided_route.json')
    assert rs['passed'] and rp['passed'] and rr['passed'] and rr['global_final_timing_passed']
    assert rr['source_DB'] == rp['output'] and rp['source_DB'] == rs['output']
    for item in (rs['output'], rp['output'], rr['output']):
        verify_ref(item)
    old_syn = verify_ref(rs['artifacts']['actual_netlist.v'])
    old_route = verify_ref(rr['artifacts']['actual_netlist.v'])
    original_plan = read(verify_ref(rp['anchor_plan']))
    actual_positions = read(verify_ref(rp['artifacts']['macro_actual_positions.json']))
    assert actual_positions['all_match'] and rp['ten_macro_positions_match']
    anchors = [{k: a[k] for k in ('name', 'col', 'row', 'offset', 'type', 'is_placed')}
               for a in actual_positions['anchors']]
    assert anchors == original_plan['anchors'] and len(anchors) == 10
    assert sum(a['type'] == 'PH1P_PHY_ERAM_V2' for a in anchors) == 8
    assert sum(a['type'] == 'PH1P_PHY_DSPSIOU_V2' for a in anchors) == 2
    verify_ref(rp['log'])
    # Also require the reference route's effective anchor file to be the one
    # which produced its parent placement. No new old-DB probe is necessary.
    anchor_ref = next(x for x in rp['controls'] if Path(x['path']).name == 'ui_macro_anchors.adc')
    verify_ref(anchor_ref)

    new, nc = parse(new_syn)
    old, oc = parse(old_syn)
    routed, rc = parse(old_route)
    rows = []
    for a in anchors:
        name = '\\' + a['name']
        assert name in old and name in new and name in routed, name
        o, n, r = normalized(old[name], oc), normalized(new[name], nc), normalized(routed[name], rc)
        row = {'name': a['name'], 'same_type': o['type'] == n['type'] == r['type'] == a['type'],
               'all_SYN_params_INIT_equal': o['params'] == n['params'],
               'all_SYN_ports_equal': o['ports'] == n['ports'],
               'reference_route_params_preserved': r['params'] == o['params'],
               'reference_SYN': o, 'new_SYN': n,
               'reference_route_params': r['params'], 'position': a}
        row['passed'] = all(row[k] for k in ('same_type', 'all_SYN_params_INIT_equal', 'all_SYN_ports_equal', 'reference_route_params_preserved'))
        rows.append(row)
    targets = [GUIDED / n for n in ('source_comparison.json', 'anchor_plan.json', 'ui_macro_anchors.adc', 'query_new_syn_macros.tcl')]
    assert not any(p.exists() for p in targets), 'Preserve previous inventory; no implicit overwrite'
    comparison = {'passed': all(r['passed'] for r in rows), 'producer': ref(__file__),
        'candidate_manifest': ref(MANIFEST), 'candidate_SYN': syn['output'],
        'reference_SYN_DB': rs['output'], 'reference_routed_DB': rr['output'],
        'netlists': {'reference_syn': ref(old_syn), 'new_syn': ref(new_syn), 'reference_route': ref(old_route)},
        'reference_actual_positions': rp['artifacts']['macro_actual_positions.json'],
        'reference_parent_anchor_ADC': anchor_ref, 'actual_new_DDR38': syn['ddr_group_plan'],
        'macros': rows, 'native_run': False, 'device': False}
    write(GUIDED / 'source_comparison.json', comparison)
    assert comparison['passed'], 'Macro identity mismatch retained; do not emit anchor ADC or place'
    adc = ''.join('set_inst_assignment {' + a['name'] + '} {location = x' + str(a['col']) +
                  'y' + str(a['row']) + 'z' + str(a['offset']) + ';}\n' for a in anchors)
    (GUIDED / 'ui_macro_anchors.adc').write_text(adc, encoding='ascii')
    plan = {'status': 'NEW_SYN_IDENTITY_VERIFIED_TEN_MACRO_PLAN_ROOT_ADMISSION_REQUIRED',
        'source_comparison': ref(GUIDED / 'source_comparison.json'),
        'source_positions_log': rp['log'], 'reference_routed_DB': rr['output'],
        'reference_parent_place_DB': rp['output'], 'netlists': comparison['netlists'],
        'SYN': syn['output'], 'anchors_ADC': ref(GUIDED / 'ui_macro_anchors.adc'),
        'anchors': anchors, 'clockBound': 'Do not copy reference clockBound. Review actual new placement.',
        'positions_scope': 'Accepted d882 hard anchor parent placement; route kept same physical macros and did not run place.',
        'fresh_ASR_required_after_new_place': True, 'device': False}
    write(GUIDED / 'anchor_plan.json', plan)
    query = 'import_device ph1_35p.db -package PH1P35MDG324 -speed 3\nimport_db {' + Path(syn['output']['path']).as_posix() + '}\n'
    for a in anchors:
        query += 'puts {SYN_MACRO ' + a['name'] + '}\nset o [get_cells {' + a['name'] + '}]\n'
        query += 'if {[llength $o]!=1} {error {SYN_MACRO_NOT_UNIQUE}}\nreport_cells $o -attributes -connection\n'
    query += 'puts {SYN_MACRO_READONLY_INVENTORY_COMPLETE}\nexit 0\n'
    (GUIDED / 'query_new_syn_macros.tcl').write_text(query, encoding='ascii')
    print(json.dumps({'status': 'HOST_INVENTORY_COMPLETE_REQUIRES_INDEPENDENT_ADMISSION',
        'comparison': ref(GUIDED / 'source_comparison.json'), 'plan': ref(GUIDED / 'anchor_plan.json'),
        'anchor_ADC': ref(GUIDED / 'ui_macro_anchors.adc'), 'native_run': False, 'device': False}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
