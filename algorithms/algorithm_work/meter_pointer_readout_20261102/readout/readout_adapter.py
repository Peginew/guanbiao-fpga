"""PC-only empirical pressure calibration and common angle-to-bar evaluation.

calibrate uses only train D/E/F direct visual keypoints and user pressure.
evaluate consumes model image angles; query pose uses pixels+bbox, never GT
needle/hub/pressure. G ground truth is read only AFTER predictions are frozen.
"""
from pathlib import Path
import argparse,json,hashlib,math,sys
import numpy as np
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
DATA=ROOT/'algorithm_work/meter_cnn_training_20261102'
sys.path.insert(0,str(DATA))
from roi_adapter import load_prepared
from print_pose import PrintPose,query_box,sha
PSI_TO_BAR=0.0689475729167
ERROR_TARGET_BAR=.05

def load(path):return json.loads(Path(path).read_text('utf-8-sig'))
def write(path,data):Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf-8')
def jsonl(path):return[json.loads(x)for x in Path(path).read_text('utf-8-sig').splitlines()if x.strip()]
def theta(h,t):return math.degrees(math.atan2(t[1]-h[1],t[0]-h[0]))%360
def unwrap(a,center):return(a-center+180)%360-180+center

def pose_records(records,calibration=None):
    train=load_prepared(DATA/'prepared_train.jsonl')
    ref=next(r for r in train if r['id']=='D_002')
    estimator=PrintPose(ref['path'],ref['bbox_native_xyxy'])
    rows=[]
    for r in records:
        rows.append(dict(id=r['id'],source_sha256=r['sha256'],split=r['split'],
            **estimator.infer(r['path'],query_box(r))))
    return rows

def calibrate():
    rr=load_prepared(DATA/'prepared_train.jsonl');poses=pose_records(rr)
    pp={r['id']:r for r in poses};measurements=[]
    front={'front_medium_soft_light','front_large_soft_light','front_dim','backlight_or_local_reflection'}
    for r in rr:
        if r['scene']['primary']not in front or not r['target_present']or r['loss_mask']!=[1,1]or not pp[r['id']]['accepted']:continue
        h=r['keypoints']['hub']['xy'];t=r['keypoints']['thin_terminal']['xy']
        a=theta(h,t);roll=pp[r['id']]['relative_roll_deg'];corrected=(a-roll)%360
        psi=r['pressure']['value']
        if psi is None or r['pressure']['unit']!='psi':continue
        measurements.append(dict(id=r['id'],group=r['source_group'],native_angle_deg=a,
            print_relative_roll_deg=roll,reference_angle_deg=corrected,pressure_psi=psi,
            bar_reference=psi*PSI_TO_BAR,source_sha256=r['sha256']))
    # The tested pressure interval does not cross a360deg branch. Set branch by
    # circular train-only mean, never by validation angle or pressure.
    angles=np.array([r['reference_angle_deg']for r in measurements]);center=math.degrees(math.atan2(np.sin(np.radians(angles)).mean(),np.cos(np.radians(angles)).mean()))%360
    for r in measurements:r['reference_angle_unwrapped_deg']=unwrap(r['reference_angle_deg'],center)
    anchors=[]
    for psi in sorted(set(r['pressure_psi']for r in measurements)):
        aa=[r['reference_angle_unwrapped_deg']for r in measurements if r['pressure_psi']==psi]
        anchors.append(dict(pressure_psi=psi,bar=psi*PSI_TO_BAR,angle_deg=float(np.median(aa)),samples=len(aa)))
    if len(anchors)<5:raise ValueError('Not enough train-only pressure anchors')
    x=np.array([a['angle_deg']for a in anchors]);y=np.array([a['bar']for a in anchors])
    slope,intercept=np.polyfit(x,y,1)
    residual=np.array([slope*r['reference_angle_unwrapped_deg']+intercept-r['bar_reference']for r in measurements])
    cal=dict(schema='pc_meter_train_pressure_angle_calibration_v1',fit_status='FIT_COMPLETE_TRAIN_ONLY',
        reference_id='D_002',reference_sha256=next(r for r in rr if r['id']=='D_002')['sha256'],
        calibration_kind='EMPIRICAL_LINEAR_PRESSURE_ANGLE_FIT_NOT_DIRECT_PRINTED_DIGIT_READING',
        direction='native image +x0deg,+y clockwise; corrected image angle minus static-print relative roll',
        formula='bar=slope_bar_per_degree*unwrap(angle_image-print_roll,branch_center)+intercept_bar',
        slope_bar_per_degree=float(slope),intercept_bar=float(intercept),branch_center_deg=center,
        supported_angle_interval_deg=[float(x.min()),float(x.max())],
        supported_pressure_interval_psi=[float(y.min()/PSI_TO_BAR),float(y.max()/PSI_TO_BAR)],
        supported_bar_interval=[float(y.min()),float(y.max())],
        anchors=anchors,fit_measurements=measurements,
        train_calibration_mae_bar=float(abs(residual).mean()),train_calibration_max_abs_error_bar=float(abs(residual).max()),
        runtime_thresholds=dict(error_acceptance_target_bar=ERROR_TARGET_BAR,max_pose_anisotropy=1.15,
             min_static_print_inliers=10,extrapolation_allowed=False,unknown_pose_assumed_zero=False),
        training_groups=['D','E','F'],validation_used_for_fitting=False,
        keypoint_label_inversion_from_pressure=False,query_GT_points_used_for_pose=False,
        pressure_reference='USER descending psi list; stability basically unchanged, gauge/instrument precision unknown',
        static_scale_evidence='Current face visually has inner bar ticks and outer psi ticks; this fit uses user psi values and direct visual needle angles, not an OCR-certified printed scale calibration.',
        scope='PC offline manual-bbox/HDMI proxy only; does not expand board0..0.51bar TEST calibration',
        original_label_or_image_changes=False,H_opened=False,
        source_files={str(DATA/'prepared_train.jsonl'):sha(DATA/'prepared_train.jsonl'),
                      str(HERE/'print_pose.py'):sha(HERE/'print_pose.py'),str(__file__):sha(__file__)})
    write(HERE/'calibration.json',cal)
    (HERE/'train_print_pose.jsonl').write_text(''.join(json.dumps(p,ensure_ascii=False)+'\n'for p in poses),'utf-8')
    print(json.dumps({k:cal[k]for k in ['fit_status','slope_bar_per_degree','intercept_bar','supported_angle_interval_deg','supported_bar_interval','train_calibration_mae_bar','train_calibration_max_abs_error_bar']},indent=2))

def read_predictions(path):
    if Path(path).suffix.lower()=='.jsonl':rows=jsonl(path)
    else:
        q=load(path);rows=q['rows']if isinstance(q,dict)else q
    return rows

def apply_prediction(pred,pose,cal):
    out=dict(id=pred['id'],model_name=pred.get('model_name'),valid=False,bar_estimate=None,
        reason='PREDICTION_NOT_PERMITTED',source_sha256=pose['source_sha256'],pose_source='STATIC_PRINT_PIXELS_AND_BBOX_NO_QUERY_GT_POINTS',
        calibrated_pressure_is_PC_only=True)
    permitted=pred.get('valid',pred.get('evidence_accepted',False))
    angle=pred.get('angle_deg_image',pred.get('angle_deg'))
    if angle is None and pred.get('predicted_points_roi')is not None:
        h,t=pred['predicted_points_roi'];angle=theta(h,t)
    if not permitted:return out
    if angle is None or not np.isfinite(angle):out['reason']='NO_FINITE_MODEL_IMAGE_ANGLE';return out
    out['angle_deg_image']=float(angle)
    if not pose['accepted']:out['reason']=pose['reason'];return out
    a=unwrap(float(angle)-pose['relative_roll_deg'],cal['branch_center_deg'])
    out.update(print_relative_roll_deg=pose['relative_roll_deg'],reference_angle_deg=a)
    lo,hi=cal['supported_angle_interval_deg']
    if not lo<=a<=hi:out['reason']='PREDICTED_DIRECTION_OUTSIDE_TRAIN_CALIBRATION';return out
    bar=cal['slope_bar_per_degree']*a+cal['intercept_bar']
    if not cal['supported_bar_interval'][0]<=bar<=cal['supported_bar_interval'][1]:
        out['reason']='PREDICTED_VALUE_OUTSIDE_TRAIN_PRESSURE_SUPPORT';return out
    out.update(valid=True,bar_estimate=bar,reason='PC_EMPIRICALLY_CALIBRATED_READING')
    return out

def evaluate(path,out_path,calibration_path=None):
    calpath=Path(calibration_path)if calibration_path else HERE/'calibration.json';cal=load(calpath)
    rr=load_prepared(DATA/'prepared_validation.jsonl')
    # Cache is bound to actual pixels, static source and new no-query-GT method.
    posepath=HERE/'validation_print_pose.jsonl'
    cached=jsonl(posepath)if posepath.exists()else[]
    cached_ok=bool(cached)and len(cached)==len(rr)and all(p.get('pose_code_sha256')==sha(HERE/'print_pose.py')and p.get('query_uses_GT_keypoints')is False and p.get('query_uses_pressure')is False for p in cached)
    if not cached_ok:
        poses=pose_records(rr);posepath.write_text(''.join(json.dumps(p,ensure_ascii=False)+'\n'for p in poses),'utf-8')
    pp={r['id']:r for r in jsonl(posepath)}
    preds=read_predictions(path);assert len({r['id']for r in preds})==len(preds)
    lookup={r['id']:r for r in rr};assert all(r['id']in lookup for r in preds),'G-only evaluation; never H'
    outputs=[]
    for pred in preds:
        ident=pred['id'];out=apply_prediction(pred,pp[ident],cal);r=lookup[ident]
        assert out['source_sha256']==r['sha256']
        # Scoring section only: no value above depends on G pressure/keypoints.
        reference=r['pressure'].get('value')*PSI_TO_BAR if r['pressure'].get('value')is not None else None
        out.update(target_present_for_scoring=r['target_present'],bar_reference_for_scoring=reference)
        out['absolute_error_bar']=abs(out['bar_estimate']-reference)if out['valid']and reference is not None else None
        out['error_over_target']=bool(out['valid']and(reference is None or out['absolute_error_bar']>ERROR_TARGET_BAR))
        outputs.append(out)
    positives=[r for r in outputs if r['target_present_for_scoring']];negatives=[r for r in outputs if not r['target_present_for_scoring']]
    accepted=[r for r in positives if r['valid']];errors=np.array([r['absolute_error_bar']for r in accepted])
    eligible=[r for r in outputs if lookup[r['id']]['loss_mask']==[1,1]and lookup[r['id']]['target_present']]
    result=dict(status='PC_PROXY_VALIDATION_ONLY_NOT_BOARD_READ_ACCEPTANCE',
        summary=dict(images=len(outputs),gauge_images=len(positives),negative_images=len(negatives),
            static_pose_supported=sum(pp[r['id']]['accepted']for r in outputs),
            valid_readings=len(accepted),coverage_gauge=len(accepted)/len(positives)if positives else None,
            valid_reads_with_bounded_both_points=sum(r['valid']for r in eligible),bounded_both_point_images=len(eligible),
            reading_mae_bar=float(errors.mean())if len(errors)else None,reading_median_abs_error_bar=float(np.median(errors))if len(errors)else None,
            reading_max_abs_error_bar=float(errors.max())if len(errors)else None,
            accurate_accepted_within_005bar=sum(r['absolute_error_bar']<=ERROR_TARGET_BAR for r in accepted),
            wrong_accepted_over_005bar=sum(r['error_over_target']for r in accepted),
            negative_false_accepts=sum(r['valid']for r in negatives),
            read_error_threshold_bar=ERROR_TARGET_BAR,rejections={reason:sum(r['reason']==reason for r in outputs)for reason in sorted(set(r['reason']for r in outputs if not r['valid']))}),
        source=dict(predictions=str(Path(path).resolve()),prediction_sha256=sha(path),calibration_sha256=sha(calpath),
            validation_pose_sha256=sha(posepath),print_pose_code_sha256=sha(HERE/'print_pose.py'),adapter_sha256=sha(__file__)),
        limitations=['G is development validation, not H independent test.','Input face bbox is manually annotated proxy; no end-to-end auto-locator recall claim.','Pressure is user setting, instrument accuracy unknown.','Accepted sequence lacks actual vehicle stop/freshness/full hardware READ checks.','No-query-GT static print pose added only to PC offline readout, not yet deployed MCU.','No new board range claim; existing0..0.51bar TEST unchanged.'],rows=outputs)
    write(out_path,result);print(json.dumps(result['summary'],ensure_ascii=False,indent=2))
    return result

def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='cmd',required=True)
    sub.add_parser('calibrate');q=sub.add_parser('evaluate');q.add_argument('--predictions',required=True);q.add_argument('--out',required=True);q.add_argument('--calibration')
    a=ap.parse_args()
    if a.cmd=='calibrate':calibrate()
    else:evaluate(a.predictions,a.out,a.calibration)

if __name__=='__main__':main()
