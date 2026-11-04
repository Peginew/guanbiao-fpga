"""Train-only PSI calibration with line inverse projection, PC diagnostic.

Uses existing no-query-GT native static-print H as a comparator. This is not a
claim that native frames/H are available to the deployed MCU.
"""
from pathlib import Path
import argparse,json,math,hashlib,sys
import numpy as np

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
PREV=ROOT/'algorithm_work/meter_pointer_readout_20261102'
DATA=ROOT/'algorithm_work/meter_cnn_training_20261102'
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def rows(p):return[json.loads(x)for x in Path(p).read_text('utf-8-sig').splitlines()if x.strip()]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n','utf-8')
def angle(h,t):return math.degrees(math.atan2(t[1]-h[1],t[0]-h[0]))%360
def unwrap(a,c):return(a-c+180)%360-180+c
def native_to_query(point,record):
    x0,y0,x1,y1=record['bbox_native_xyxy'];s=240/max(x1-x0,y1-y0)
    return(np.asarray(point)-[(x0+x1)/2,(y0+y1)/2])*s+[128,128]
def roi_to_native(point,record):
    q=record['roi_request'];s=q['stride']
    return np.asarray(point)*s+[q['x0'],q['y0']]+(s-1)/2
def inverse_line(h,t,pose,record,native=False):
    if not pose['accepted'] or 'H_reference_to_query'not in pose:return None
    H=np.linalg.inv(np.asarray(pose['H_reference_to_query'],np.float64))
    points=[np.asarray(h),np.asarray(t)]
    if not native:points=[roi_to_native(p,record)for p in points]
    points=[native_to_query(p,record)for p in points]
    pp=[]
    for p in points:
        q=H@np.r_[p,1.]
        if not np.isfinite(q).all()or abs(q[2])<1e-8:return None
        pp.append(q[:2]/q[2])
    if np.linalg.norm(pp[1]-pp[0])<1e-6:return None
    return angle(*pp)
def calibrate():
    rr=rows(DATA/'prepared_train.jsonl');poses={r['id']:r for r in rows(PREV/'readout_psi/train_print_pose.jsonl')}
    front={'front_medium_soft_light','front_large_soft_light','front_dim','backlight_or_local_reflection'}
    measurements=[]
    for r in rr:
        if r['scene']['primary']not in front or not r['target_present']or r['loss_mask']!=[1,1]:continue
        a=inverse_line(r['keypoints']['hub']['xy'],r['keypoints']['thin_terminal']['xy'],poses[r['id']],r,True)
        if a is None:continue
        measurements.append(dict(id=r['id'],angle_deg=a,pressure_psi=r['pressure']['value']))
    aa=np.array([r['angle_deg']for r in measurements]);c=math.degrees(math.atan2(np.sin(np.radians(aa)).mean(),np.cos(np.radians(aa)).mean()))%360
    anchors=[]
    for value in sorted(set(r['pressure_psi']for r in measurements)):
        a=[unwrap(r['angle_deg'],c)for r in measurements if r['pressure_psi']==value]
        anchors.append(dict(psi=value,angle_deg=float(np.median(a)),n=len(a)))
    x=np.array([r['angle_deg']for r in anchors]);y=np.array([r['psi']for r in anchors]);slope,intercept=np.polyfit(x,y,1)
    errors=[abs(slope*unwrap(r['angle_deg'],c)+intercept-r['pressure_psi'])for r in measurements]
    cal=dict(unit='psi',status='TRAIN_ONLY_PROJECTIVE_LINE_CALIBRATION_PC_NATIVE_H_DIAGNOSTIC',measurements=measurements,anchors=anchors,
             slope_psi_per_degree=float(slope),intercept_psi=float(intercept),branch_center_deg=c,angle_support=[float(x.min()),float(x.max())],
             psi_support=[float(y.min()),float(y.max())],train_MAE_psi=float(np.mean(errors)),train_max_error_psi=float(max(errors)),
             G_used_for_fit=False,H_opened=False,query_GT_used_for_prediction=False,native_H_MCU_available=False)
    write(HERE/'calibration.json',cal);print(json.dumps({k:v for k,v in cal.items()if k not in ['measurements','anchors']}))
def evaluate(path,out):
    cal=load(HERE/'calibration.json');lookup={r['id']:r for r in rows(DATA/'prepared_validation.jsonl')};poses={r['id']:r for r in rows(PREV/'readout_psi/validation_print_pose.jsonl')}
    dd=load(path)if Path(path).suffix.lower()=='.json'else rows(path);preds=dd['rows']if isinstance(dd,dict)else dd
    result=[]
    for p in preds:
        r=lookup[p['id']];outrow=dict(id=p['id'],unit='psi',valid=False,psi_estimate=None,reason='MODEL_EVIDENCE_NOT_PERMITTED',source_sha256=r['sha256'])
        if p.get('valid',p.get('evidence_accepted',False)):
            theta=p.get('angle_deg_image',p.get('angle_deg'));hub=p.get('hub_roi')
            if hub is None and p.get('predicted_points_roi')is not None:hub=p['predicted_points_roi'][0]
            if theta is None and p.get('predicted_points_roi')is not None:theta=angle(*p['predicted_points_roi'])
            if hub is None or theta is None:outrow['reason']='MISSING_PREDICTED_HUB_OR_DIRECTION'
            else:
                tip=np.array(hub)+20*np.array([math.cos(math.radians(theta)),math.sin(math.radians(theta))])
                a=inverse_line(hub,tip,poses[p['id']],r)
                if a is None:outrow['reason']='NO_STATIC_PRINT_PROJECTIVE_POSE'
                else:
                    a=unwrap(a,cal['branch_center_deg']);psi=cal['slope_psi_per_degree']*a+cal['intercept_psi'];outrow.update(reference_angle_deg=a)
                    if not cal['angle_support'][0]<=a<=cal['angle_support'][1]or not cal['psi_support'][0]<=psi<=cal['psi_support'][1]:outrow['reason']='OUTSIDE_TRAIN_CALIBRATION'
                    else:outrow.update(valid=True,psi_estimate=psi,reason='PC_PROJECTIVE_LINE_READING_PSI')
        # Scoring below, after all prediction and permission decisions.
        outrow.update(target_present_for_scoring=r['target_present'],psi_reference_for_scoring=r['pressure']['value'])
        outrow['absolute_error_psi']=abs(outrow['psi_estimate']-r['pressure']['value'])if outrow['valid']and r['pressure']['value']is not None else None
        result.append(outrow)
    positives=[r for r in result if r['target_present_for_scoring']];valid=[r for r in positives if r['valid']];errs=[r['absolute_error_psi']for r in valid]
    summary=dict(unit='psi',images=len(result),gauge_images=len(positives),valid_readings=len(valid),MAE_psi=float(np.mean(errs))if errs else None,
                 within_0_25psi=sum(x<=.25 for x in errs),within_0_5psi=sum(x<=.5 for x in errs),over_0_5psi=sum(x>.5 for x in errs),
                 max_error_psi=max(errs)if errs else None,negative_outputs=sum(r['valid']and not r['target_present_for_scoring']for r in result))
    write(out,dict(status='PC_NATIVE_H_MATH_DIAGNOSTIC_NOT_ROI128_DEPLOYMENT',summary=summary,rows=result,
                   source=dict(prediction_sha256=sha(path),calibration_sha256=sha(HERE/'calibration.json')),H_opened=False));print(json.dumps(summary))
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('mode',choices=['calibrate','evaluate']);a.add_argument('--predictions');a.add_argument('--out');o=a.parse_args()
    if o.mode=='calibrate':calibrate()
    else:evaluate(o.predictions,o.out)
