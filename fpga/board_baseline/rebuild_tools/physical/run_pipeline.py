"""Stable3s + trained MCU/PSI offline stage dispatcher; no action by default."""
from pathlib import Path
import argparse
import json
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['synth', 'place', 'route', 'bitgen'])
    parser.add_argument('--snapshot', action='store_true')
    parser.add_argument('--manifest', type=Path, default=HERE / 'source_freeze.json')
    parser.add_argument('--gate', type=Path)
    parser.add_argument('--timeout', type=int)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if not args.stage and not args.snapshot:
        assert not args.run and not args.gate and args.timeout is None
        from source_helpers import P, NAME
        print(json.dumps({'status': 'PLAN_ONLY', 'project': str(P), 'name': NAME,
            'project_present': (P / f'td_project/{NAME}.al').is_file(), 'manifest': str(args.manifest),
            'ordered_stages': ['snapshot and source admission', 'synth and actual capture review',
                               'new-SYN verified 10-macro plan + DDR semantic-current', 'guided place and fresh ASR/clock/IO review',
                               'pure literal guided route and FINAL review', 'accepted-DB bitgen'],
            'needed_before_synth': ['completed new project', 'source_freeze.json', 'synth_admission.json'],
            'needed_before_place': ['anchor_plan.json (new-SYN identity and reviewed reference positions)',
                                   'ui_macro_anchors.adc', 'macro_anchor_admission.json'],
            'needed_before_route': ['new placed_asr_mapping.json', 'asr_literal.sdc', 'psi_literal.sdc', 'guided_route_admission.json'],
            'native_run': False, 'device': False, 'MCU_and_weights_changed': False, 'UART_included': False},
            ensure_ascii=False, indent=2))
        return
    if args.snapshot:
        assert not args.stage and not args.run and not args.gate and args.timeout is None
        cmd = [sys.executable, str(HERE / 'run_td.py'), '--snapshot', '--manifest', str(args.manifest)]
    elif args.stage in ('synth', 'bitgen'):
        assert args.gate and args.timeout is None
        cmd = [sys.executable, str(HERE / 'run_td.py'), '--stage', args.stage, '--manifest', str(args.manifest), '--gate', str(args.gate)]
        if args.run:
            cmd.append('--run')
    else:
        assert args.gate is None, 'Guided stages use their exact independently signed gate filenames'
        assert args.manifest.resolve() == (HERE / 'source_freeze.json').resolve()
        entry = 'run_guided_place.py' if args.stage == 'place' else 'run_guided_route.py'
        cmd = [sys.executable, str(HERE / 'guided_ui_macros' / entry)]
        if args.timeout is not None:
            cmd += ['--timeout', str(args.timeout)]
        if args.run:
            cmd.append('--run')
    raise SystemExit(subprocess.run(cmd).returncode)


if __name__ == '__main__':
    main()
