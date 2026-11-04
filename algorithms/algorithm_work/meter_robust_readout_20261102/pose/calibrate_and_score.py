"""Frozen ROI128 pose candidates -> train-only PSI fit -> G old-B readout.

No nativeSIFT angle, queryGTpoint or pressure enters runtime pose/readout.
Train visual points/pressure are used only forcalibration; G only forscoring.
"""
from pathlib import Path
import sys,json,math,hashlib
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
DATA=ROOT/'algorithm_work/meter_cnn_training_20261102';OLD=ROOT/'algorithm_work/meter_pointer_readout_20261102'
sys.path.insert(0,str(DATA));from roi_adapter import load_prepared
sys.path.insert(0,str(OLD/'readout_psi'));import readout_adapter as numeric

def rows(p):return[json.loads(x)for x in Path(p).read_text('utf-8-sig').splitlines()if x.strip()]
def write(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n','utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def calibrate(records,poses,name):
    front={'front_medium_soft_light','front_large_soft_light','front_dim','backlight_or_local_reflection'}
    measurements=[]
    for r in records:
        if r['id']not in poses or not poses[r['id']]['accepted']or r['loss_mask']!=[1,1]or not r['target_present']or r['scene']['primary']not in front:continue
        if r['pressure'].get('unit')!='psi':continue
        angle=numeric.theta(r['keypoints']['hub']['xy'],r['keypoints']['thin_terminal']['xy'])
        delta=poses[r['id']]['relative_roll_deg']
        measurements.append(dict(id=r['id'],image_angle_deg=angle,relative_print_roll_deg=delta,
            reference_angle_deg=(angle-delta)%360,reference_psi=r['pressure']['value'],source_sha256=r['sha256']))
    aa=np.radians([r['reference_angle_deg']for r in measurements]);center=math.degrees(math.atan2(np.sin(aa).mean(),np.cos(aa).mean()))%360
    for r in measurements:r['reference_angle_unwrapped_deg']=numeric.unwrap(r['reference_angle_deg'],center)
    anchors=[]
    for psi in sorted(set(r['reference_psi']for r in measurements)):
        angles=[r['reference_angle_unwrapped_deg']for r in measurements if r['reference_psi']==psi]
        anchors.append(dict(reference_psi=psi,median_reference_angle_deg=float(np.median(angles)),images=len(angles)))
    assert len(anchors)>=5,'Insufficient train-only pressure support'
    x=np.array([r['median_reference_angle_deg']for r in anchors]);y=np.array([r['reference_psi']for r in anchors])
    slope,intercept=np.polyfit(x,y,1);err=[slope*r['reference_angle_unwrapped_deg']+intercept-r['reference_psi']for r in measurements]
    return dict(schema='roi128_static_print_train_only_PSI_calibration_v1',primary_unit='psi',pose_candidate=name,
        slope_psi_per_degree=float(slope),intercept_psi=float(intercept),branch_center_deg=center,
        supported_angle_interval_deg=[float(x.min()),float(x.max())],supported_pressure_interval_psi=[float(y.min()),float(y.max())],
        anchors=anchors,fit_measurements=measurements,train_fit_MAE_psi=float(np.mean(abs(np.array(err)))),train_fit_max_abs_error_psi=float(max(abs(np.array(err)))),
        method='Linear fit toequal-pressure median ofdirect train visual needle angles minus thiscandidate ROI128print pose; no GT pose, no nativeSIFT',
        fit_groups=['D','E','F'],G_used_for_fitting=False,
        query_inputs=['U8ROI128','oldB predictedhub','locatorradius'],query_GT_points_used=False,query_pressure_used=False,
        original_point_labels_changed=False,pressure_inversion_to_keypoints=False,
        limits='Offline manual-bbox/HDMIproxy; range not expanded, noextrapolation, boundary rejections retained; noMCU/hardware deployment',
        source_sha256=dict(pose=sha(HERE/f'candidate_{name}_pose.jsonl'),train_records=sha(DATA/'prepared_train.jsonl'),code=sha(__file__)))

def main():
    train=load_prepared(DATA/'prepared_train.jsonl');validation=load_prepared(DATA/'prepared_validation.jsonl');lookup={r['id']:r for r in validation}
    predictions=rows(OLD/'polar_angle/run_001/validation_predictions.jsonl')
    summary={}
    for name in['A','B']:
        pose={r['id']:r for r in rows(HERE/f'candidate_{name}_pose.jsonl')}
        cal=calibrate(train,pose,name);write(HERE/f'candidate_{name}_calibration_psi.json',cal)
        # Pure numerical angle/valuefunctions reused; no PrintPose inference called.
        outputs=[]
        for p in predictions:
            po=pose[p['id']];out=numeric.apply_prediction(p,po,cal)
            out['pose_source']=f'ROI128_CANDIDATE_{name}_NO_NATIVE_FRAME_NO_QUERY_GT'
            outputs.append(out)
        metrics=numeric.score_outputs(outputs,lookup);metrics['static_pose_supported']=sum(p['accepted']for p in pose.values()if p['split']=='validation')
        result=dict(status='ROI128_POSE_PLUS_OLD_B_PC_READOUT_NOT_MCU_DEPLOYMENT',unit='psi',pose_candidate=name,
            summary=metrics,rows=outputs,training_calibration_MAE_psi=cal['train_fit_MAE_psi'],
            source_sha256=dict(model_predictions=sha(OLD/'polar_angle/run_001/validation_predictions.jsonl'),calibration=sha(HERE/f'candidate_{name}_calibration_psi.json'),
                pose=sha(HERE/f'candidate_{name}_pose.jsonl'),code=sha(__file__)),
            query_uses_native_frame=False,query_uses_GT_points=False,query_uses_pressure=False,
            model='FrozenoldB; pose-only comparison, no model retraining',
            accuracy_targets='0.25/0.5/1psi are distributiononly;0.7251887psi islegacycomparisonnotuserfinalacceptance',
            H_opened=False,hardware_actions=False)
        write(HERE/f'candidate_{name}_with_old_B_readout_psi.json',result)
        summary[name]=dict(metrics,train_fit_images=len(cal['fit_measurements']),train_fit_MAE_psi=cal['train_fit_MAE_psi'])
    write(HERE/'readout_comparison_summary.json',dict(status='TWO_FROZEN_ROI128_POSE_CANDIDATES_OLD_MODEL_PSI_COMPARISON',summary=summary,
        native_SIFT_inference_or_calibration_used=False,new_model_used=False,G_fitted=False,H_opened=False,hardware_actions=False))
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
