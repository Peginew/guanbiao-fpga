"""Authoritative PSI PC readout. No training, no query GT pose dependency.

The calibration is an EXACT UNIT CONVERSION of the previously frozen train-
only angle fit. Historical bar files are immutable evidence, not current output.
"""
from pathlib import Path
import argparse,json,math,sys
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
DATA=ROOT/'algorithm_work/meter_cnn_training_20261102'
sys.path.insert(0,str(DATA));from roi_adapter import load_prepared
from print_pose import PrintPose,query_box,sha
PSI_TO_BAR=0.0689475729167
EQUIVALENT_LEGACY_TOLERANCE_PSI=.05/PSI_TO_BAR

def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def write(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n','utf-8')
def jsonl(p):return[json.loads(x)for x in Path(p).read_text('utf-8-sig').splitlines()if x.strip()]
def theta(h,t):return math.degrees(math.atan2(t[1]-h[1],t[0]-h[0]))%360
def unwrap(a,c):return(a-c+180)%360-180+c

def read_predictions(path):
    if Path(path).suffix.lower()=='.jsonl':return jsonl(path)
    q=load(path);return q['rows']if isinstance(q,dict)else q

def pose_records(records):
    train=load_prepared(DATA/'prepared_train.jsonl');ref=next(r for r in train if r['id']=='D_002')
    estimator=PrintPose(ref['path'],ref['bbox_native_xyxy'])
    return[dict(id=r['id'],source_sha256=r['sha256'],split=r['split'],**estimator.infer(r['path'],query_box(r)))for r in records]

def apply_prediction(pred,pose,cal):
    out=dict(id=pred['id'],model_name=pred.get('model_name'),valid=False,unit='psi',psi_estimate=None,
        reason='PREDICTION_NOT_PERMITTED',source_sha256=pose['source_sha256'],
        pose_source='STATIC_PRINT_PIXELS_AND_BBOX_NO_QUERY_GT_POINTS',calibrated_pressure_is_PC_only=True)
    permitted=pred.get('valid',pred.get('evidence_accepted',False));angle=pred.get('angle_deg_image',pred.get('angle_deg'))
    if angle is None and pred.get('predicted_points_roi')is not None:angle=theta(*pred['predicted_points_roi'])
    if not permitted:return out
    if angle is None or not np.isfinite(angle):out['reason']='NO_FINITE_MODEL_IMAGE_ANGLE';return out
    out['angle_deg_image']=float(angle)
    if not pose['accepted']:out['reason']=pose['reason'];return out
    a=unwrap(float(angle)-pose['relative_roll_deg'],cal['branch_center_deg'])
    out.update(print_relative_roll_deg=pose['relative_roll_deg'],reference_angle_deg=a)
    lo,hi=cal['supported_angle_interval_deg']
    if not lo<=a<=hi:out['reason']='PREDICTED_DIRECTION_OUTSIDE_TRAIN_CALIBRATION';return out
    psi=cal['slope_psi_per_degree']*a+cal['intercept_psi']
    if not cal['supported_pressure_interval_psi'][0]<=psi<=cal['supported_pressure_interval_psi'][1]:
        out['reason']='PREDICTED_VALUE_OUTSIDE_TRAIN_PRESSURE_SUPPORT';return out
    out.update(valid=True,psi_estimate=psi,reason='PC_EMPIRICALLY_CALIBRATED_READING_PSI')
    return out

def score_outputs(outputs,lookup):
    tolerance=EQUIVALENT_LEGACY_TOLERANCE_PSI
    for out in outputs:
        r=lookup[out['id']];assert out['source_sha256']==r['sha256']
        # User PSI truth, not a converted derived bar value; scoring only.
        ref=r['pressure'].get('value')if r['pressure'].get('unit')=='psi'else None
        out.update(target_present_for_scoring=r['target_present'],psi_reference_for_scoring=ref)
        out['absolute_error_psi']=abs(out['psi_estimate']-ref)if out['valid']and ref is not None else None
        out['error_over_tolerance_psi']=bool(out['valid']and(ref is None or out['absolute_error_psi']>tolerance))
    positives=[r for r in outputs if r['target_present_for_scoring']];negatives=[r for r in outputs if not r['target_present_for_scoring']]
    accepted=[r for r in positives if r['valid']];errors=np.array([r['absolute_error_psi']for r in accepted])
    eligible=[r for r in outputs if lookup[r['id']]['loss_mask']==[1,1]and lookup[r['id']]['target_present']]
    return dict(unit='psi',images=len(outputs),gauge_images=len(positives),negative_images=len(negatives),
        valid_readings=len(accepted),coverage_gauge=len(accepted)/len(positives)if positives else None,
        valid_reads_with_bounded_both_points=sum(r['valid']for r in eligible),bounded_both_point_images=len(eligible),
        reading_mae_psi=float(errors.mean())if len(errors)else None,
        reading_median_abs_error_psi=float(np.median(errors))if len(errors)else None,
        reading_max_abs_error_psi=float(errors.max())if len(errors)else None,
        accurate_accepted_within_tolerance=sum(r['absolute_error_psi']<=tolerance for r in accepted),
        wrong_accepted_over_tolerance=sum(r['error_over_tolerance_psi']for r in accepted),
        negative_false_accepts=sum(r['valid']for r in negatives),legacy_comparison_tolerance_psi=tolerance,
        output_error_distribution_psi=dict(
            within_0_25_psi=int((errors<=.25).sum()),within_0_5_psi=int((errors<=.5).sum()),within_1_0_psi=int((errors<=1.).sum()),
            bins=dict(up_to_0_25=int((errors<=.25).sum()),over_0_25_to_0_5=int(((errors>.25)&(errors<=.5)).sum()),
                      over_0_5_to_1_0=int(((errors>.5)&(errors<=1.)).sum()),over_1_0=int((errors>1.).sum())),
            changes_output_permission=False,is_user_confirmed_final_accuracy_target=False),
        tolerance_note='Exact equivalent of historical0.05bar engineering comparison only; NOT0.05psi and NOT user-confirmed final accuracy target.',
        rejections={reason:sum(r['reason']==reason for r in outputs)for reason in sorted(set(r['reason']for r in outputs if not r['valid']))})

def evaluate(predictions,out_path):
    cal=load(HERE/'calibration.json');rr=load_prepared(DATA/'prepared_validation.jsonl');lookup={r['id']:r for r in rr}
    posepath=HERE/'validation_print_pose.jsonl';poses=jsonl(posepath)if posepath.exists()else[]
    if len(poses)!=len(rr)or not all(p.get('pose_code_sha256')==sha(HERE/'print_pose.py')and p.get('query_uses_GT_keypoints')is False for p in poses):
        poses=pose_records(rr);posepath.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in poses),'utf-8')
    pp={r['id']:r for r in poses};preds=read_predictions(predictions)
    assert len({r['id']for r in preds})==len(preds)and all(r['id']in lookup for r in preds)
    outputs=[apply_prediction(p,pp[p['id']],cal)for p in preds]
    summary=score_outputs(outputs,lookup);summary['static_pose_supported']=sum(pp[r['id']]['accepted']for r in outputs)
    result=dict(status='PSI_AUTHORITATIVE_PC_PROXY_VALIDATION_ONLY_NOT_BOARD_READ_ACCEPTANCE',unit='psi',summary=summary,rows=outputs,
        source=dict(predictions=str(Path(predictions).resolve()),prediction_sha256=sha(predictions),calibration_sha256=sha(HERE/'calibration.json'),
                    validation_pose_sha256=sha(posepath),print_pose_code_sha256=sha(HERE/'print_pose.py'),adapter_sha256=sha(__file__)),
        limitations=['G development only;H not opened.','PSI is primary and user truth is read directly in PSI.','Historical comparison tolerance is NOT a user-approved final target.','SIFT pose still uses native frame unavailable tocurrentMCU.','Manual-bbox/HDMI proxy only; no hardware or calibration-range update.'])
    write(out_path,result);print(json.dumps(summary,ensure_ascii=False,indent=2));return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--predictions',required=True);ap.add_argument('--out',required=True);a=ap.parse_args();evaluate(a.predictions,a.out)

if __name__=='__main__':main()
