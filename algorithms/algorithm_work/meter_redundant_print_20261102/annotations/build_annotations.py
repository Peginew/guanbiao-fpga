"""Six fixed static-print identities; AI visual diagnostic sidecars, not gold.

Only identity, raw-image display geometry, old frozen individual print points,
and ROI requests are consumed. Pressure, NN predictions, and pose results are
not used to locate/accept the points. Prior result exposure is disclosed.
"""
from pathlib import Path
import json,hashlib,sys
import cv2
import numpy as np

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
OLD=ROOT/'algorithm_work/meter_print_reference_control_20261102'
NAMES=['outer_psi_5_text_centroid','outer_psi_10_text_centroid','outer_psi_15_text_centroid',
       'upper_basketball_logo_centroid','middle_soccer_logo_centroid','lower_striped_ball_print_centroid']

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def readrows(p):return [json.loads(s) for s in Path(p).read_text('utf-8-sig').splitlines() if s.strip()]
def save(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n','utf-8')
def roi(p,q):
    if p is None:return None
    s=q['stride'];return [(p[0]-q['x0']-(s-1)/2)/s,(p[1]-q['y0']-(s-1)/2)/s]
def pnative(p,d):
    if p is None:return None
    t=d['view_transform'];x0,y0,_,_=d['native_crop_xyxy']
    return [x0+(p[0]-t['offset_x'])/t['scale_x'],y0+(p[1]-t['offset_y'])/t['scale_y']]
def anchor(p,vis,u,q,reason,template=False,view=None):
    rp=roi(p,q)
    return {'native_xy':p,'roi_xy':rp,'visibility':vis,'uncertainty_native_px':u,
            'uncertainty_is_certified_bound':False,'reason':reason,'template_usable':template,
            'within_roi_pixel_center_bounds':bool(rp is not None and all(0<=v<=127 for v in rp)),
            'manually_read_view_xy':list(view) if view is not None else None}
def refs():
    mm=json.loads((OLD/'annotations_train/view_manifest.json').read_text('utf-8'))
    geom={r['id']:r for r in mm['records'] if r['id'] in ('D_002','D_025')}
    q={}
    for item in readrows(ROOT/'algorithm_work/meter_cnn_training_20261102/prepared_train.jsonl'):
        if item['id'] in geom:q[item['id']]=item['roi_request']
    coordinates={
       'D_002':[(86,224),(226,82),(416,166),(246,201),(266,313),(269,359)],
       'D_025':[(84,227),(222,77),(407,154),(250,196),(267,302),(273,352)]}
    for id,pp in coordinates.items():
        g=geom[id];x0,y0,x1,y1=g['native_crop_xyxy'];ow,oh=g['resized_native_crop_size'];dx,dy=g['display_offset']
        aa={}
        for name,point in zip(NAMES,pp):
            native=[x0+(point[0]-dx)*(x1-x0)/ow,y0+(point[1]-dy)*(y1-y0)/oh]
            contaminated=id=='D_002' and name in (NAMES[3],NAMES[4])
            why='Point center is visible in static printed structure; template context still requires finite crop review.'
            if contaminated:why='Visible printed circular contour supports an uncertain center, but needle/counterweight occludes part and contaminates a template patch; excluded from template and D025-toD002 alignment.'
            aa[name]=anchor(native,'partial' if contaminated else 'visible',6 if contaminated else 4 if id=='D_002' else 3,q[id],why,not contaminated,point)
        r={'id':id,'source_sha256':g['source_sha256'],'anchors':aa,'roi_request':q[id],
           'semantic_names_frozen':NAMES,'annotation_kind':'AI visual diagnostic, not blind human gold or automatic runtime output',
           'point_selection_used_pressure_or_predictions':False,'prior_results_seen':True,
           'view_provenance':g,'reference_role':'PUBLIC_ZERO_PRINT_AXIS_ONLY' if id=='D_002' else 'SOLE_TRAIN_TEMPLATE_SOURCE',
           'D025_to_D002_alignment_names':[NAMES[i] for i in (0,1,2,5)],
           'original_or_canonical_modified':False,'ready_as_training_label':False}
        save(BASE/f'reference_{id.replace("_","")}.json',r)
    print('reference_D002.json and reference_D025.json written; six fixed identities, no G fitting')

if __name__=='__main__':
    BASE.mkdir(exist_ok=True)
    refs()
