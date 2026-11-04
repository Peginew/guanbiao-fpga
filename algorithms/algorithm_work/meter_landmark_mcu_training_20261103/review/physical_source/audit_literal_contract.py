"""Independently inspect effective literal SDC summaries and PSI17 path details.

Reads existing native reports only. A pre-route PASS is registration evidence,
not routed timing or bitgen admission. No TD, process, or device operations.
"""
from pathlib import Path
import argparse, hashlib, json, re

HERE = Path(__file__).resolve().parent
TASK = HERE.parent.parent
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
ref = lambda p: dict(path=str(Path(p).resolve()), sha256=sha(p))


def rules(text, command, token):
    result = []
    for line in text.splitlines():
        m = re.match(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(' + command + r'.*)$', line)
        if m and token in m[5]:
            result.append(dict(total=int(m[1]), active=int(m[2]), shadowed=int(m[3]), ignored=int(m[4]), command=m[5]))
    return result


def psi_paths(text):
    sections = text.split('Timing details for constraint:')
    wanted = [x for x in sections[1:] if 'return_psi_q8' in x.split('\n', 3)[1] and 'return_psi_valid' in x.split('\n', 3)[1]]
    assert len(wanted) == 1, ('PSI detailed constraint section', len(wanted))
    section = wanted[0]
    source_map = json.loads((HERE/'psi17_endpoint_precheck.json').read_text(encoding='utf-8'))
    launch_map = {x['physical'].lstrip('\\') + '.' + x['outputpin']: x['logical'].lstrip('\\') for x in source_map['registers']}
    assert len(launch_map) == 17
    out = []
    for m in re.finditer(r'^Slack\s*:\s*(-?[0-9.]+)ns\s*\nBegin Point\s*:\s*([^\n]+)\nEnd Point\s*:\s*([^\n]+)\n(.*?)(?=^Slack\s*:|\Z)', section, re.M | re.S):
        slack, begin, end, detail = float(m[1]), m[2], m[3], m[4]
        assert 'return_psi_' in begin and 'result_psi_' in end
        assert 'clock MCU_ROI_50 ' in begin and 'period=20.000000' in begin
        assert 'clock HDMI_PIXEL_CLK ' in end and 'period=13.333000' in end
        budget = re.search(r'^Budget\s*:\s*([0-9.]+)ns', detail, re.M)
        assert budget and float(budget[1]) == 7.2
        assert slack >= 0, (begin, end, slack)
        launch = re.search(r'^clk2q[^\n]*pin: ([^\n]+)', detail, re.M)
        assert launch and launch[1] in launch_map, begin
        identity = launch_map[launch[1]]
        # Packed LUT input endpoints can carry a different result-bit name;
        # do not infer logical bit correspondence from that cell name alone.
        # Source identity and actual HDMI consumer scope are audited here.
        assert re.search(r'result_psi_(?:q8_reg\[\d+\]|valid_reg)', end), end
        out.append(dict(identity=identity, source=begin, launch_output=launch[1], endpoint=end, budget_ns=7.2, slack_ns=slack))
    assert len(out) >= 17 and {x['launch_output'] for x in out} == set(launch_map)
    # ep_num=256/path_num=1 reports the worst source per endpoint. Seventeen
    # dominated endpoints do not imply seventeen different source registers.
    assert len({x['endpoint'].split()[0] for x in out}) == 17
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--route-receipt', type=Path, default=TASK/'physical/latest_literal_route.json')
    ap.add_argument('--final', action='store_true')
    a = ap.parse_args()
    route = json.loads(a.route_receipt.read_text(encoding='utf-8'))
    run = Path(route['run'])
    controls = route['controls']
    for x in controls:
        assert sha(x['path']) == x['sha256'], ('changed control', x['path'])
    qual = HERE/'literal_contract_effective_review.json'
    qualification = json.loads(qual.read_text(encoding='utf-8'))
    assert qualification['passed']
    for name, key in [('asr_literal.sdc', 'ASR_literal'), ('psi_literal.sdc', 'PSI_literal')]:
        assert sha(run/name) == qualification[key]['sha256']
    execute = (run/'execute.tcl').read_text(encoding='ascii')
    assert execute.index('read_sdc asr_literal.sdc') < execute.index('read_sdc psi_literal.sdc') < execute.index('report_clock_summary')
    assert execute.index('ACTUAL_LITERAL_CONTRACTS_PROVEN') < execute.index('\nroute\n')
    log = (run/'console.log').read_text(errors='replace')
    registered = log.index('LITERAL_SDC_REGISTERED_BEFORE_CLOCK_DISCOVERY')
    timer = log.index('start command "start_timer"')
    proved = log.index('ACTUAL_LITERAL_CONTRACTS_PROVEN')
    routed = log.index('start command "route"')
    assert registered < timer < proved < routed
    assert 'ACTUAL_CONTRACT_ROWS PSI=1 ASR=2' in log
    ex = run/('all_held_data.timing' if a.final else 'pre_contract_exception.timing')
    ig = run/('all_ignored_data.timing' if a.final else 'pre_contract_ignored.timing')
    et, it = ex.read_text(errors='replace'), ig.read_text(errors='replace')
    psi = rules(et, 'set_max_delay', 'return_psi_q8')
    asr = rules(it, 'set_false_path', 'u_hdmi_reset/release_ff[2]')
    assert len(psi) == 1 and all(psi[0][k] == v for k, v in dict(total=17, active=17, shadowed=0, ignored=0).items())
    assert 'return_psi_valid' in psi[0]['command'] and '[get_clocks {HDMI_PIXEL_CLK}]' in psi[0]['command'] and '-datapath_only 7.200' in psi[0]['command']
    assert len(asr) == 2 and all(all(x[k] == v for k, v in dict(total=6, active=6, shadowed=0, ignored=0).items()) for x in asr)
    for x in asr:
        assert x['command'] == (run/'asr_literal.sdc').read_text().strip()
    paths = psi_paths(et)
    if a.final:
        assert route['passed'] and route['global_final_timing_passed'] and route['exit_code'] == 0
        assert route['FINAL']['STNS'] == route['FINAL']['HTNS'] == 0
        assert min(route['FINAL'].values()) >= 0
        assert 'LITERAL_CONTRACT_FINAL_COMPLETE' in log and 'No multi-drive.' in log and 'No abnormal timing path.' in log
        assert sha(route['output']['path']) == route['output']['sha256']
    out = dict(passed=True, status='PASS_FINAL_EFFECTIVE_LITERAL_PSI17_ASR6' if a.final else 'PASS_ACTUAL_PREROUTE_LITERAL_REGISTRATION_ONLY',
        route_receipt=ref(a.route_receipt), run=str(run), auditor=ref(__file__), qualification=ref(qual),
        controls=controls, reports={'PSI_SMD':ref(ex), 'ASR_FP':ref(ig)}, PSI_summary=psi, ASR_summary=asr,
        PSI_endpoint_paths=paths, PSI_distinct_endpoints=17,
        PSI_worst_path_source_identities=sorted({x['identity'] for x in paths}),
        PSI_all17_logical_sources_proven_by_unique_launch_outputs=True,
        PSI_source_launch_mapping=ref(HERE/'psi17_endpoint_precheck.json'),
        actual_SDC_registered_before_first_timer=True, actual_contract_proven_before_route=True,
        effective_reset_scope_requires_independent_fresh_mapping=True, final_routed_timing=a.final,
        bitgen_admission=False, device_actions=False,
        boundary='Only effective SDC and individual PSI17 SMD path evidence. Pin/clock/capture/INIT audit and parent delivery gate remain separate.')
    dest = HERE/('literal_final_effectiveness_review.json' if a.final else 'literal_route_entry_review.json')
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(passed=True, final=a.final, PSI_paths=len(paths), min_PSI_slack_ns=min(x['slack_ns'] for x in paths), receipt=ref(dest)), ensure_ascii=False))


if __name__ == '__main__':
    main()
