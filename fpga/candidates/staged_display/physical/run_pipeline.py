"""Prepared-only staged-display physical entry. Default emits a plan.

Source freeze and all admissions must be newly produced for reader_staged.
Placement/routing executors are deliberately not inherited from old guided
macros: their ten-LOC anchor contracts do not apply to this free-UI candidate.
"""
from pathlib import Path
import argparse, json, subprocess, sys

HERE=Path(__file__).resolve().parent

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stage',choices=['synth','place','route','bitgen'])
    ap.add_argument('--snapshot',action='store_true')
    ap.add_argument('--manifest',type=Path,default=HERE/'source_freeze.json')
    ap.add_argument('--gate',type=Path)
    ap.add_argument('--run',action='store_true')
    args=ap.parse_args()
    if not args.stage and not args.snapshot:
        from source_helpers import P,NAME
        print(json.dumps({'status':'PREPARED_PLAN_ONLY_NOT_FROZEN','project':str(P),'name':NAME,
          'ordered_stages':['new source/component freeze','new SYN and capture36/MCU/clock review',
          'fresh DDR37 semantic derivation','free UI place without10LOC',
          'fresh actual ASR12 source/packed endpoints, PSI17 exactQ and progress32 exactQ, new4 sync FF',
          'first-timer literal-contract probe and signed route admission','complete FINAL/DRC and source/bit identity'],
          'place_flow':'free_ui_place_flow.py','new_endpoint_hooks':'progress_mapping_hooks.py',
          'old_DB_aliases_gates_constraints_copied':False,'native_TD_run':False,'device':False},indent=2));return
    if args.stage in ['place','route']:
        raise SystemExit('Fresh free-UI place/route executors/admissions require root integration; no inherited old anchor runner is executed.')
    argv=[sys.executable,str(HERE/'run_td.py'),'--manifest',str(args.manifest)]
    if args.snapshot:
        assert not args.stage and not args.run and not args.gate
        argv+=['--snapshot']
    else:
        assert args.stage and args.gate
        argv+=['--stage',args.stage,'--gate',str(args.gate)]
        if args.run:argv+=['--run']
    raise SystemExit(subprocess.run(argv).returncode)

if __name__=='__main__':main()
