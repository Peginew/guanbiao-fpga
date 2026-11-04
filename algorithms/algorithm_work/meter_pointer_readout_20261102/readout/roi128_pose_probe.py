"""One bounded feasibility probe, ROI128 only; not SIFT or production pose.

Inputs: existingU8 ROI, model-predicted hub, locator-derived radius. No query
native image, GT keypoint/pressure or SIFT result participates in the search.
"""
from pathlib import Path
import json,sys,math,hashlib
import cv2
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
DATA=ROOT/'algorithm_work/meter_cnn_training_20261102'
POLAR=HERE.parent/'polar_angle/run_001'
sys.path.insert(0,str(DATA));from roi_adapter import load_prepared

def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def rows(p):return[json.loads(x)for x in Path(p).read_text('utf-8-sig').splitlines()if x.strip()]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def profile(gray,hub,radius):
    # PC floating bilinear probe only; fixed-point gather not implemented here.
    angles=np.arange(360)*np.pi/180;r=np.linspace(.4,.88,12)*radius
    x=hub[0]+r[:,None]*np.cos(angles);y=hub[1]+r[:,None]*np.sin(angles)
    outside=float(((x<0)|(x>127)|(y<0)|(y>127)).mean())
    q=cv2.remap(gray,x.astype(np.float32),y.astype(np.float32),cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=0).astype(np.float32)
    q=q-q.mean(axis=1,keepdims=True);q=q/np.maximum(abs(q).mean(axis=1,keepdims=True),6)*32
    return np.clip(np.rint(q),-127,127).astype(np.int16),outside

def main():
    train=load_prepared(DATA/'prepared_train.jsonl');validation=load_prepared(DATA/'prepared_validation.jsonl')
    rr=train+validation;rec={r['id']:r for r in rr}
    gray={}
    for split in['train','validation']:
        z=np.load(DATA/f'roi_cache_{split}.npz')
        gray.update({str(k):g for k,g in zip(z['ids'],z['images'])})
    pred={r['id']:r for r in rows(POLAR/'train_predictions.jsonl')+rows(POLAR/'validation_predictions.jsonl')}
    ref_record=rec['D_002'];ref,_=profile(gray['D_002'],pred['D_002']['hub_roi'],ref_record['roi_request']['radius'])
    # Reference-only setup mask; known D002 needle orientation is manually fixed.
    a=np.arange(360);mask=np.ones((12,360),bool)
    for angle in[281,101]:mask&=abs((a-angle+180)%360-180)[None,:]>24
    grad=abs(np.roll(ref,-1,1)-np.roll(ref,1,1))
    mask&=grad>=8
    reference=ref[mask].astype(np.int32)
    results=[]
    shifts=np.arange(-24,25)
    for r in rr:
        ident=r['id']
        if ident not in pred:continue  # No model hub output for13quality-review-only train frames.
        p=pred[ident]
        q,outside=profile(gray[ident],p['hub_roi'],r['roi_request']['radius'])
        scores=[]
        for shift in shifts:
            values=np.roll(q,-int(shift),axis=1)[mask].astype(np.int32)
            diff=np.abs(values-reference);keep=max(1,int(len(diff)*.8))
            # Trim largest20% residuals to reduce dynamic-needle/reflection influence.
            scores.append(1-float(np.partition(diff,keep-1)[:keep].mean())/128)
        scores=np.array(scores);i=int(scores.argmax());best=float(shifts[i]);far=scores[abs(shifts-best)>5]
        margin=float(scores[i]-far.max())if len(far)else 0.
        valid=bool(scores[i]>=.60 and margin>=.015 and outside<=.05 and abs(best)<24)
        results.append(dict(id=ident,split=r['split'],relative_roll_deg=best,accepted=valid,
            correlation_proxy_score=float(scores[i]),margin=margin,outside_fraction=outside,
            predicted_hub_roi=p['hub_roi'],known_frame_radius=r['roi_request']['radius'],
            source_sha256=r['sha256'],query_uses_GT_points=False,query_uses_pressure=False,
            reads_native_image=False,method='ROI128_ANNULAR_TRIMMED_SAD_PROBE_NOT_SIFT'))
    # Existing SIFT is an external PC comparator only; never an input to this probe.
    sift={r['id']:r for r in rows(HERE/'train_print_pose.jsonl')+rows(HERE/'validation_print_pose.jsonl')}
    for r in results:
        s=sift[r['id']]
        r['SIFT_supported_for_diagnostic_only']=s['accepted']
        r['relative_angle_error_to_PC_SIFT_comparator']=abs((r['relative_roll_deg']-s['relative_roll_deg']+180)%360-180)if s['accepted']else None
    def stat(split):
        a=[r for r in results if r['split']==split];accepted=[r for r in a if r['accepted']]
        both=[r for r in accepted if r['SIFT_supported_for_diagnostic_only']];err=[r['relative_angle_error_to_PC_SIFT_comparator']for r in both]
        return dict(images=len(a),accepted=len(accepted),accepted_also_SIFT_supported=len(both),
            mean_difference_to_PC_SIFT_deg=float(np.mean(err))if err else None,
            median_difference_to_PC_SIFT_deg=float(np.median(err))if err else None,
            max_difference_to_PC_SIFT_deg=float(max(err))if err else None,
            disagreement_over3deg=sum(x>3 for x in err))
    summary=dict(status='BOUNDED_ROI128_POSE_FEASIBILITY_PROBE_NOT_ACCEPTED_PRODUCTION_REPLACEMENT',
        reference_id='D_002',search_degrees=[-24,24],radial_bands=12,angular_bins=360,
        source_inputs='Only128x128U8 ROI + predicted hub + locator box radius; no native image/GT/pressure',
        thresholds_fixed_before_probe=dict(min_score=.60,min_margin=.015,max_outside_fraction=.05),
        train=stat('train'),validation=stat('validation'),
        excluded_without_model_hub=[r['id']for r in rr if r['id']not in pred],
        cost_estimate=dict(radial_samples=4320,bilinear_source_reads=17280,angular_search_candidates=49,
            comparison_absolute_differences=49*int(mask.sum()),reference_profile_INT8_bytes=4320,
            query_profile_INT8_bytes=4320,selected_template_elements=int(mask.sum()),
            sin_cos_LUT_S16_bytes=1440,possible_B_feature_reuse=True,
            peak_additional_memory_not_linked=True,MCU_cycles_not_measured=True,
            int8_fixed_point_kernel_implemented=False),
        deployment_note='ROI exists in bridge; hub comes fromfrozenCNN, radius fromdescriptor. SIFT native256 path is not available tocurrentMCU. Must validate integer gather/profile andactualTCM linkmap beforeclaimingfit.',
        calibration_or_signed_PC_results_modified=False,H_opened=False,
        source_sha256={str(p):sha(p)for p in[Path(__file__),POLAR/'train_predictions.jsonl',POLAR/'validation_predictions.jsonl',DATA/'roi_cache_train.npz',DATA/'roi_cache_validation.npz']})
    (HERE/'roi128_pose_probe_records.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in results),'utf-8')
    (HERE/'roi128_pose_probe_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
