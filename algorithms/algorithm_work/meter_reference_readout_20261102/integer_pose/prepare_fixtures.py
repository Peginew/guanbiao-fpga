"""Freeze unchanged train templates and per-observation streaming matcher inputs.

This first fixture uses the PREVIOUS float/OpenCV frontend. It establishes the
integer matcher separately; pose_frontend.py is tested as a separate change.
"""
from pathlib import Path
import json,sys,time
import numpy as np
HERE=Path(__file__).resolve().parent
TASK=HERE.parent
ROOT=TASK.parents[1]
OLD=ROOT/'algorithm_work/meter_robust_readout_20261102/pose'
sys.path.insert(0,str(OLD))
from roi_pose_candidates import Candidates,assets,sha,write


def main():
    rr,gray,pred=assets();c=Candidates(rr,gray,pred)
    output=HERE/'fixtures';output.mkdir(exist_ok=True)
    names=list(c.templates)
    assert names==['D_002','E_002']
    templates={};metadata=[]
    for j,name in enumerate(names):
        ref,mask=c.templates[name]
        indices=np.flatnonzero(mask.ravel()).astype(np.uint16)
        values=ref.ravel()[indices].astype(np.int8)
        shifts=np.array([int(round(d-c.offsets[name])) for d in range(-24,25)],np.int16)
        templates[f'indices_{j}']=indices;templates[f'values_{j}']=values;templates[f'shifts_{j}']=shifts
        metadata.append(dict(id=name,count=len(indices),trim_keep=int(len(indices)*.8),offset_deg=c.offsets[name]))
    np.savez(output/'templates.npz',**templates)
    fixed={r['id']:r for r in [json.loads(s) for s in (OLD/'candidate_B_pose.jsonl').read_text('utf-8').splitlines()]}
    records=[];start=time.monotonic()
    for r in rr:
        ident=r['id']
        if ident not in pred:continue
        p=pred[ident];hub=np.asarray(p['hub_roi'],np.float64);radius=float(r['roi_request']['radius'])
        q=[];outside=[];hypotheses=[]
        for dx in [-1.5,0,1.5]:
            for dy in [-1.5,0,1.5]:
                for scale in [.97,1.,1.03]:
                    profile,fraction=c.profile(gray[ident],hub+[dx,dy],radius*scale)
                    q.append(profile.astype(np.int8));outside.append(int(round(fraction*4320)))
                    hypotheses.append([dx,dy,scale])
        np.savez_compressed(output/(ident+'.npz'),profiles=np.stack(q),outside_counts=np.array(outside,np.uint16),
            hub=hub,radius=radius,hypotheses=np.array(hypotheses,np.float64),image=gray[ident])
        records.append(dict(id=ident,split=r['split'],source_sha256=r['sha256'],fixture_sha256=sha(output/(ident+'.npz')),
            center_allowed=bool(np.linalg.norm(hub-63.5)<=14),baseline=fixed[ident]))
    write(output/'manifest.json',dict(status='OLD_FRONTEND_STREAMING_FIXTURES_NOT_FULL_INTEGER_FRONTEND',
        templates=metadata,templates_sha256=sha(output/'templates.npz'),records=records,
        gray_input='Existing hardware-shaped HDMI/manual-box proxy; not real same-frame MCU dump',
        source_code_sha256=sha(__file__),baseline_code_sha256=sha(OLD/'roi_pose_candidates.py'),
        preprocessing_uses_float_OpenCV=True,exported_S8_profiles=True,profiles_per_image=27,
        matcher_order='dx,dy,scale,template,delta; first equal-score winner retained',
        query_pressure_or_GT_used=False,labels_not_in_matcher_fixture=True,H_opened=False,hardware_actions=False,
        elapsed_seconds=time.monotonic()-start))
    print('fixtures',len(records),'template counts',metadata,'seconds',time.monotonic()-start,flush=True)


if __name__=='__main__':main()
