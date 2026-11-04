"""Score already-frozen integer predictions; references never enter inference."""
from pathlib import Path
import argparse,hashlib,json,math,sys
sys.dont_write_bytecode=True
import numpy as np
from landmark_model import POINTS
from train_landmarks import summarize

def read(p):return[json.loads(s)for s in Path(p).read_text('utf-8-sig').splitlines()if s.strip()]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def score(labels,predictions,out):
    truth={r['id']:r for r in read(labels)};rr=read(predictions)
    assert len(truth)==len(rr) and set(truth)=={r['id']for r in rr}
    assert all(r['id'].startswith(('D_','E_','F_','G_'))for r in rr)
    for r in rr:
        ref=truth[r['id']];assert r['source_sha256']==ref['source_sha256']
        for name in POINTS:
            p=r['points'][name];t=ref['points'][name]
            p['reference_coordinate_available']=bool(t['coordinate_mask'])
            if t['coordinate_mask']:p['coordinate_error_ROI']=float(np.linalg.norm(np.asarray(p['roi_xy'])-t['xy_roi']))
            p['reference_visibility_known']=bool(t['visibility_mask'])
            p['reference_visibility_target']=t.get('vis_target',t.get('visibility_target'))
    result=dict(summary=summarize(rr),rows=rr,
        scope='Posthoc reference attachment for error reporting; all integer inference and acceptance frozen',
        source_sha256=dict(labels=sha(labels),predictions=sha(predictions),scoring=sha(__file__)),
        PSI_or_geometry_evaluated=False,independent_test=False)
    Path(out).write_text(json.dumps(result,indent=2)+'\n','utf-8')
    print(json.dumps(result['summary']))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--labels',type=Path,required=True)
    p.add_argument('--predictions',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();score(a.labels,a.predictions,a.out)
