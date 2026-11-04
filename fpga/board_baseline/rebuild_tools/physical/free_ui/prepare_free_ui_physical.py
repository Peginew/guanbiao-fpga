"""Fresh free-UI placed-DB ASR and exact PSI Q-half handoff; host only.

Default PLAN. --prepare never invokes TD or changes frozen tools. Every
physical pin is derived from this actual placement, not the preceding one.
Clock roots, ordinary DATA and route admission remain independent reviews.
"""
from pathlib import Path
import argparse
import json
import sys

HERE = Path(__file__).resolve().parent
PHYSICAL = HERE.parent
sys.path.insert(0, str(PHYSICAL))
from source_helpers import read, write, ref, verify_ref, validate_manifest
from mapping_helpers import derive_asr, parse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    place_file = HERE / 'latest_place.json'
    if not args.prepare:
        place = read(place_file) if place_file.is_file() else {}
        print(json.dumps({'status': 'PLAN_ONLY', 'place_passed': place.get('passed', False),
                          'native_run': False, 'device': False, 'fresh_ASR_and_exact17_Qpins_required': True}, ensure_ascii=False))
        return
    assert __debug__
    place = read(place_file)
    assert place['passed'] and place['exit_code'] == 0 and place['stage'] == 'free_ui_place'
    assert place['actual_same_SYN_only'] and place['actual_ten_LOC_ADC_not_loaded']
    manifest = verify_ref(place['manifest'])
    validate_manifest(manifest)
    syn = read(PHYSICAL / 'latest_synth.json')
    assert syn['passed'] and syn['manifest'] == place['manifest'] and place['source_DB'] == syn['output']
    group = read(PHYSICAL / 'ddr_group_plan.json')
    assert group['netlist'] == syn['artifacts']['actual_netlist.v'] and group['member_count'] == 37
    for value in (place['output'], place['artifacts']['actual_netlist.v'], place['artifacts']['actual.adc'], syn['artifacts']['actual_netlist.v']):
        verify_ref(value)
    outputs = ['placed_asr_mapping.json', 'asr_literal.sdc', 'psi_literal.sdc',
               'psi_exact_qpins.sdc', 'psi17_endpoint_precheck.json', 'fresh_physical_handoff.json']
    assert not any((HERE / name).exists() for name in outputs), 'Preserve any preceding handoff; no implicit overwrite'
    mapping = derive_asr(place['artifacts']['actual_netlist.v']['path'], place['output']['path'],
                         syn['artifacts']['actual_netlist.v']['path'], group,
                         place['artifacts']['actual.adc']['path'], HERE)
    cells, canon = parse(place['artifacts']['actual_netlist.v']['path'])
    prefix = r'\u_meter_pair/pipeline/reader/live/'
    desired = [prefix + f'return_psi_q8[{i}]' for i in range(16)] + [prefix + 'return_psi_valid']
    sources = []
    for logical in desired:
        found = []
        for name, cell in cells.items():
            if cell['type'] != 'PH1P_PHY_LSLICE':
                continue
            for half, q in (('A', 'oqa'), ('B', 'oqb')):
                if cell['params'].get('OQ' + half + 'MUX') == '"Q' + half + '"' and q in cell['ports'] and canon(cell['ports'][q]) == canon(logical):
                    found.append({'logical_Q': logical, 'physical': name, 'half': half, 'Q_pin': q,
                                  'pin': name.lstrip('\\') + '.' + q, 'clock_net': cell['ports'].get('clk'),
                                  'actual_cell_params': cell['params'], 'actual_cell_ports': cell['ports']})
        assert len(found) == 1, (logical, len(found))
        sources.extend(found)
    pins = [row['pin'] for row in sources]
    assert len(set(pins)) == len(pins) == 17
    literal = 'set_max_delay -from [get_pins {' + ' '.join(pins) + '}] -to [get_clocks {HDMI_PIXEL_CLK}] -datapath_only 7.200\n'
    (HERE / 'psi_exact_qpins.sdc').write_text(literal, encoding='ascii')
    precheck = {'passed': True, 'scope': 'Host source identity only; independent clock/Tco/DATA/FINAL review required',
                'source_DB': place['output'], 'actual_netlist': place['artifacts']['actual_netlist.v'],
                'place_receipt': ref(place_file), 'manifest': place['manifest'], 'logical_count': 17,
                'exact_Q_pin_count': 17, 'sources': sources, 'exact_Q_literal': ref(HERE / 'psi_exact_qpins.sdc'),
                'physical_pin_names_copied_from_previous_place': False, 'device': False}
    write(HERE / 'psi17_endpoint_precheck.json', precheck)
    handoff = {'status': 'FRESH_FREE_UI_HOST_HANDOFF_REQUIRES_INDEPENDENT_ROUTE_ADMISSION',
               'producer': ref(__file__), 'place_receipt': ref(place_file), 'source_DB': place['output'],
               'manifest': place['manifest'], 'ASR_count': mapping['physical_ASR_count'], 'ASR_logical_FF_count': 12,
               'ASR_mapping': ref(HERE / 'placed_asr_mapping.json'), 'asr_literal': ref(HERE / 'asr_literal.sdc'),
               'PSI17_precheck': ref(HERE / 'psi17_endpoint_precheck.json'), 'qualified_syntax_exact_Q_literal': ref(HERE / 'psi_exact_qpins.sdc'),
               'unqualified_regs_literal_NOT_FOR_ROUTE': ref(HERE / 'psi_literal.sdc'),
               'macro_actual_positions': place['artifacts']['macro_actual_positions.json'],
               'clocks': place['artifacts']['clocks.txt'], 'area': place['artifacts']['reader_landmark_s3_phy.area'],
               'old_10_macro_coordinate_equality_required': False, 'native_run': False, 'device': False}
    validate_manifest(manifest)
    write(HERE / 'fresh_physical_handoff.json', handoff)
    print(json.dumps(handoff, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
