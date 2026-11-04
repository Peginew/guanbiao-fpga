"""Printed-reference substitution and independent PSI calibration controls.

No network training/inference change. The NEW reference is visually supplied
from native images: a diagnostic observation, not automatic ROI128 inference.
G pressure appears only after reference/calibration/output decisions are fixed.
"""
from pathlib import Path
import argparse,csv,hashlib,json,math,sys
import numpy as np

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
DATA=ROOT/'algorithm_work/meter_cnn_training_20261102'
MODEL=ROOT/'algorithm_work/meter_pointer_readout_20261102'
PREVIOUS=ROOT/'algorithm_work/meter_robust_readout_20261102/pose'
sys.path.insert(0,str(MODEL/'readout_psi'));import readout_adapter as numeric
TOP='outer_psi_10_text_centroid';BOTTOM='lower_striped_ball_print_centroid'
BANDS=(.25,.5,1.)


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def rows(p):return [json.loads(s) for s in Path(p).read_text('utf-8-sig').splitlines() if s.strip()]
def write(p,d):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n','utf-8')
def save_rows(p,rr):Path(p).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rr),'utf-8')
def delta(a,b):return (a-b+180)%360-180


def anchor_axis(annotation,record):
    out=dict(accepted=False,reason='VISUAL_PRINT_REFERENCE_UNAVAILABLE',id=record['id'],
        source_sha256=record['sha256'],split=record['split'],
        automatic_reference_inference=False,query_needle_or_pressure_used=False,
        reference_source='AI_VISUAL_NATIVE_STATIC_PRINT_WITH_UNCERTAINTY_NOT_GOLD',
        two_points_are_not_perspective_correction=True)
    if annotation is None:return out
    assert annotation['source_sha256']==record['sha256'],record['id']
    selection_flag=annotation.get('point_selection_used_pressure_or_predictions',
        annotation.get('pressure_or_query_neural_pose_used_for_points'))
    assert selection_flag is False,record['id']
    out['annotation_reason']=annotation.get('reason')
    if not annotation.get('accepted',False):return out
    pp=[];uu=[];roi=[];visibility=[]
    for key in (TOP,BOTTOM):
        a=annotation['anchors'][key];p=a.get('native_xy');u=a.get('uncertainty_native_px')
        if p is None or u is None:return out
        visible=a.get('visibility')
        assert visible in ('visible','partially_visible','partial'),(record['id'],key,visible)
        visibility.append(visible)
        p=np.asarray(p,np.float64)
        assert p.shape==(2,) and np.isfinite(p).all() and float(u)>=0,(record['id'],key)
        assert 0<=p[0]<record['width'] and 0<=p[1]<record['height'],(record['id'],key,p)
        pp.append(p);uu.append(float(u))
        q=record['roi_request'];s=q['stride']
        roi.append((p-[q['x0'],q['y0']]-(s-1)/2)/s)
    v=pp[0]-pp[1];length=float(np.linalg.norm(v))
    if length<=sum(uu):out['reason']='PRINT_ANCHOR_BASELINE_NOT_RESOLVED';return out
    angle=float(math.degrees(math.atan2(v[1],v[0])))
    axis_unc=float(math.degrees(math.asin(min(1.,sum(uu)/length))))
    out.update(absolute_print_axis_deg=angle,anchor_baseline_native_px=length,
        declared_query_axis_sensitivity_deg=axis_unc,anchors_native=np.asarray(pp).tolist(),
        anchors_roi=np.asarray(roi).tolist(),declared_anchor_uncertainty_native_px=uu,
        anchor_visibilities=visibility,has_partially_visible_anchor=any(v!='visible' for v in visibility),
        original_native_reference_available=True)
    if not np.all((np.asarray(roi)>=0)&(np.asarray(roi)<=127)):
        out['reason']='VISUAL_PRINT_ANCHOR_OUTSIDE_ANALYSIS_ROI';return out
    out.update(accepted=True,reason='VISUALLY_SUPPORTED_STATIC_PRINT_REFERENCE')
    return out


def print_poses(train_records,dev_records,train_annotations,dev_annotations):
    ta={r['id']:r for r in train_annotations};ga={r['id']:r for r in dev_annotations}
    ref_record=next(r for r in train_records if r['id']=='D_002')
    reference=anchor_axis(ta['D_002'],ref_record)
    assert reference['accepted'],'D002 reference must be visually available before scoring'
    poses={}
    for record in train_records+dev_records:
        a=(ta if record['split']=='train' else ga).get(record['id'])
        p=anchor_axis(a,record)
        if p['accepted']:
            p['relative_roll_deg']=delta(p['absolute_print_axis_deg'],reference['absolute_print_axis_deg'])
            p['declared_relative_axis_sensitivity_deg']=0. if record['id']=='D_002' else p['declared_query_axis_sensitivity_deg']+reference['declared_query_axis_sensitivity_deg']
            p['reference_id']='D_002'
            p['interval_semantics']='Angle sensitivity to declared point uncertainty, NOT certified bound or calibrated confidence'
        poses[record['id']]=p
    return poses,reference


def fit_calibration(records,poses,allowed_ids,name):
    measurements=[]
    for r in records:
        if r['id'] not in allowed_ids or not poses[r['id']]['accepted'] or r['loss_mask']!=[1,1] or not r['target_present']:continue
        assert r['source_group'] in ('D','E','F') and r['split']=='train' and r['pressure']['unit']=='psi'
        angle=numeric.theta(r['keypoints']['hub']['xy'],r['keypoints']['thin_terminal']['xy'])
        relative=(angle-poses[r['id']]['relative_roll_deg'])%360
        measurements.append(dict(id=r['id'],source_sha256=r['sha256'],reference_psi=r['pressure']['value'],
            visual_needle_image_angle_deg=angle,print_relative_roll_deg=poses[r['id']]['relative_roll_deg'],
            relative_angle_deg=relative))
    a=np.radians([r['relative_angle_deg'] for r in measurements])
    assert len(a)>0,'No calibration observations'
    center=math.degrees(math.atan2(np.sin(a).mean(),np.cos(a).mean()))%360
    for r in measurements:r['unwrapped_angle_deg']=numeric.unwrap(r['relative_angle_deg'],center)
    anchors=[]
    for psi in sorted(set(r['reference_psi'] for r in measurements)):
        aa=[r['unwrapped_angle_deg'] for r in measurements if r['reference_psi']==psi]
        anchors.append(dict(reference_psi=psi,median_reference_angle_deg=float(np.median(aa)),images=len(aa)))
    assert len(anchors)>=5,'Insufficient training pressure support: no forced fallback or G fitting'
    x=np.array([r['median_reference_angle_deg'] for r in anchors]);y=np.array([r['reference_psi'] for r in anchors])
    k,b=np.polyfit(x,y,1);assert k>0
    errors=[abs(k*r['unwrapped_angle_deg']+b-r['reference_psi']) for r in measurements]
    return dict(schema='TRAIN_ONLY_PRINT_REFERENCE_LINEAR_PSI_FIT',name=name,primary_unit='psi',
        slope_psi_per_degree=float(k),intercept_psi=float(b),branch_center_deg=center,
        supported_angle_interval_deg=[float(x.min()),float(x.max())],supported_pressure_interval_psi=[float(y.min()),float(y.max())],
        fit_measurements=measurements,anchors=anchors,train_fit_MAE_psi=float(np.mean(errors)),train_fit_max_abs_error_psi=max(errors),
        original_fit_rule='Linear fit on equal-pressure median visual needle-minus-print angles',
        query_pressure_used=False,G_used_for_fitting=False,pressure_inversion_to_points=False,
        clamping_or_extrapolation=False,reference_is_visual_diagnostic=True,
        measurement_uncertainties='User pressure and visual needle uncertainty retained; fit not certified metrology')


def summarize(outputs,records):
    lookup={r['id']:r for r in records};summary=numeric.score_outputs(outputs,lookup)
    scene={}
    for name in sorted(set(r['scene']['primary'] for r in records)):
        selected=[o for o in outputs if lookup[o['id']]['scene']['primary']==name]
        positives=[o for o in selected if o['target_present_for_scoring']];accepted=[o for o in positives if o['valid']]
        ee=[o['absolute_error_psi'] for o in accepted]
        scene[name]=dict(images=len(selected),gauges=len(positives),valid=len(accepted),
            MAE_psi=float(np.mean(ee)) if ee else None,within_bands_psi={str(t):sum(e<=t for e in ee) for t in BANDS})
    summary['by_scene']=scene
    summary['descriptive_correct_output_coverage']={str(t):dict(correct_outputs=sum(o['valid'] and o['absolute_error_psi']<=t for o in outputs if o['target_present_for_scoring']),
        wrong_numeric_outputs=sum(o['valid'] and o['absolute_error_psi']>t for o in outputs if o['target_present_for_scoring']),
        denominator=summary['gauge_images']) for t in BANDS}
    return summary


def compare(outputs,baseline):
    bb={r['id']:r for r in baseline};nn={r['id']:r for r in outputs}
    result=dict(new_output_ids=[i for i,r in nn.items() if r['valid'] and not bb[i]['valid']],
        withdrawn_output_ids=[i for i,r in nn.items() if not r['valid'] and bb[i]['valid']],bands={})
    for t in BANDS:
        def correct(r):return r['valid'] and r['target_present_for_scoring'] and r['absolute_error_psi']<=t
        def wrong(r):return r['valid'] and (not r['target_present_for_scoring'] or r['absolute_error_psi']>t)
        result['bands'][str(t)]=dict(gained_correct_ids=[i for i,r in nn.items() if correct(r) and not correct(bb[i])],
            lost_correct_ids=[i for i,r in nn.items() if correct(bb[i]) and not correct(r)],
            new_wrong_ids=[i for i,r in nn.items() if wrong(r) and not wrong(bb[i])],
            recovered_wrong_ids=[i for i,r in nn.items() if wrong(bb[i]) and not wrong(r)])
    return result


def evaluate(predictions,poses,cal,records,name,oldposes,visualposes):
    outputs=[]
    for p in predictions:
        po=poses[p['id']];out=numeric.apply_prediction(p,po,cal)
        out.update(variant=name,reference_is_automatically_estimated=po.get('automatic_reference_inference',True),
            old_pose_accepted=oldposes[p['id']]['accepted'],old_pose_reason=oldposes[p['id']]['reason'],
            original_model_permitted=p['valid'],print_reference_accepted=visualposes[p['id']]['accepted'])
        if po.get('accepted') and p.get('angle_deg_image') is not None:
            a=numeric.unwrap(float(p['angle_deg_image'])-po['relative_roll_deg'],cal['branch_center_deg'])
            raw_psi=cal['slope_psi_per_degree']*a+cal['intercept_psi']
            lo,hi=cal['supported_angle_interval_deg'];pl,ph=cal['supported_pressure_interval_psi']
            out['calibration_diagnostic_NOT_OUTPUT']=dict(reference_angle_deg=a,raw_unpermitted_psi=raw_psi,
                angle_supported=bool(lo<=a<=hi),pressure_supported=bool(pl<=raw_psi<=ph),
                signed_distance_inside_angle_interval_deg=min(a-lo,hi-a),
                signed_distance_inside_pressure_interval_psi=min(raw_psi-pl,ph-raw_psi),
                changes_permission=False)
        if po.get('accepted') and 'declared_relative_axis_sensitivity_deg' in po:
            out['reference_only_declared_PSI_sensitivity']=abs(cal['slope_psi_per_degree'])*po['declared_relative_axis_sensitivity_deg']
            out['sensitivity_is_full_error_bound']=False
        outputs.append(out)
    return dict(name=name,summary=summarize(outputs,records),rows=outputs,
        runtime_neural_predictions_changed=False,calibration=cal['name'] if 'name' in cal else 'FROZEN_OLD_B',
        result_is_automatic_reader=False if poses is visualposes else True,
        evidence_scope='OFFLINE_VISUAL_REFERENCE_SUBSTITUTION_CONTROL_NOT_NEW_DEPLOYMENT')


def run():
    out=HERE/'results';out.mkdir(exist_ok=True)
    tr=rows(DATA/'prepared_train.jsonl');dev=rows(DATA/'prepared_validation.jsonl');allrecords=tr+dev
    ta=rows(HERE/'annotations_train/print_annotations.jsonl');ga=rows(HERE/'annotations_g/print_annotations.jsonl')
    # Supplement captures were already reconciled into condition metadata;
    # image ordinal arithmetic would silently select the wrong E observations.
    expected={r['id'] for r in tr if r['source_group'] in ('D','E','F') and r['target_present'] and r['capture_condition_slot'] in (1,2)}
    assert {r['id'] for r in ta}==expected and len(ta)==48
    assert {r['id'] for r in ga}=={r['id'] for r in dev} and len(ga)==59
    visual,reference=print_poses(tr,dev,ta,ga)
    oldposes={r['id']:r for r in rows(PREVIOUS/'candidate_B_pose.jsonl')}
    # Some quality-only train images have no model analysis; never substitute a dummy success.
    for r in allrecords:
        oldposes.setdefault(r['id'],dict(id=r['id'],source_sha256=r['sha256'],split=r['split'],accepted=False,reason='NO_ORIGINAL_MODEL_POSE'))
    oldcal=load(PREVIOUS/'candidate_B_calibration_psi.json')
    newcal=fit_calibration(tr,visual,expected,'NEW_VISUAL_REFERENCE_TRAIN48')
    common={r['id'] for r in tr if r['id'] in expected and visual[r['id']]['accepted'] and oldposes[r['id']]['accepted'] and r['loss_mask']==[1,1]}
    cm_old=fit_calibration(tr,oldposes,common,'MATCHED_TRAIN_OLD_REFERENCE')
    cm_new=fit_calibration(tr,visual,common,'MATCHED_TRAIN_VISUAL_REFERENCE')
    write(out/'reference_D002.json',reference);save_rows(out/'visual_print_poses.jsonl',[visual[r['id']] for r in allrecords])
    for name,cal in [('new_calibration_psi',newcal),('matched_old_calibration_psi',cm_old),('matched_visual_calibration_psi',cm_new)]:write(out/(name+'.json'),cal)
    predictions=rows(MODEL/'polar_angle/run_001/validation_predictions.jsonl')
    variants={}
    combos=[('oldref_oldcal',oldposes,oldcal),('visualref_oldcal',visual,oldcal),
            ('oldref_newcal',oldposes,newcal),('visualref_newcal',visual,newcal),
            ('matched_oldref_oldcal',oldposes,cm_old),('matched_visualref_oldcal',visual,cm_old),
            ('matched_oldref_newcal',oldposes,cm_new),('matched_visualref_newcal',visual,cm_new)]
    for name,poses,cal in combos:variants[name]=evaluate(predictions,poses,cal,dev,name,oldposes,visual)
    baseline=variants['oldref_oldcal'];previous=load(PREVIOUS/'candidate_B_with_old_B_readout_psi.json')
    assert all((a['id'],a['valid'],a['psi_estimate'],a['reason'])==(b['id'],b['valid'],b['psi_estimate'],b['reason']) for a,b in zip(baseline['rows'],previous['rows']))
    eligible_ids={r['id'] for r in dev if visual[r['id']]['accepted']}
    summaries={}
    for name,result in variants.items():
        result['changes_against_frozen_baseline']=compare(result['rows'],baseline['rows'])
        result['same_visual_available_subset_summary']=summarize([r.copy() for r in result['rows'] if r['id'] in eligible_ids],[r for r in dev if r['id'] in eligible_ids])
        recovered={}
        for r in result['rows']:
            if r['id'] in result['changes_against_frozen_baseline']['new_output_ids']:
                recovered.setdefault(r['old_pose_reason'],[]).append(r['id'])
        result['recovery_by_old_pose_reason']=recovered
        write(out/(name+'.json'),result)
        summaries[name]=dict(summary=result['summary'],same_visual_available_subset_summary=result['same_visual_available_subset_summary'],
            changes=result['changes_against_frozen_baseline'],recovery_by_old_pose_reason=recovered)
    # Model predictions, labels and image input remain frozen; this manifest is not deployment readiness.
    files=[HERE/'task_contract.json',HERE/'annotations_train/print_annotations.jsonl',HERE/'annotations_g/print_annotations.jsonl',
        DATA/'prepared_train.jsonl',DATA/'prepared_validation.jsonl',DATA/'run_002/best_weights.pt',
        MODEL/'polar_angle/run_001/best_weights.pt',MODEL/'polar_angle/run_001/validation_predictions.jsonl',
        PREVIOUS/'candidate_B_pose.jsonl',PREVIOUS/'candidate_B_calibration_psi.json',Path(__file__)]
    report=dict(status='OFFLINE_PRINT_REFERENCE_AND_CALIBRATION_CONTROLS_COMPLETE_NOT_AUTOMATIC_INFERENCE',unit='psi',
        variants=summaries,new_calibration_observations=len(newcal['fit_measurements']),common_calibration_observations=len(common),
        common_calibration_ids=sorted(common),new_calibration_ids=[r['id'] for r in newcal['fit_measurements']],
        visual_reference_available_G=sorted(eligible_ids),visual_reference_available_G_count=len(eligible_ids),
        total_G_images=59,total_G_gauges=56,declared_pressure_error_bands=list(BANDS),bands_are_user_final_tolerance=False,
        visual_reference_uses_native_AI_visual_annotations=True,visual_reference_is_gold_or_automatic=False,
        runtime_query_pressure_or_true_needle_used=False,reference_substitution_is_pose_value_and_pose_evidence_change=True,
        neural_permission_changed=False,missing_visual_reference_falls_back_to_old_pose=False,
        canonical_or_weights_changed=False,H_or_ABC_used=False,training=False,hardware_actions=False,
        limitations=['G is repeatedly used development, not independent test.',
            'Two static anchors provide image-axis direction, not full perspective correction.',
            'Reference source is native visual annotation, not an automatically executed ROI128 method.',
            'User PSI and existing visual needle labels have uncalibrated uncertainty.',
            'All source-frame ownership/hardware layers are outside this offline experiment.'],
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in files})
    write(out/'comparison_summary.json',report)
    fields=['id','scene','reference_psi','model_permitted','visual_reference_available','variant','valid','estimate_psi','abs_error_psi','reason','old_pose_reason']
    records={r['id']:r for r in dev}
    with (out/'逐图四格与共同标定对照.csv').open('w',newline='',encoding='utf-8-sig') as fp:
        w=csv.DictWriter(fp,fieldnames=fields);w.writeheader()
        for name,result in variants.items():
            for r in result['rows']:w.writerow(dict(id=r['id'],scene=records[r['id']]['scene']['primary'],reference_psi=r['psi_reference_for_scoring'],
                model_permitted=r['original_model_permitted'],visual_reference_available=r['print_reference_accepted'],variant=name,
                valid=r['valid'],estimate_psi=r['psi_estimate'],abs_error_psi=r['absolute_error_psi'],reason=r['reason'],old_pose_reason=r['old_pose_reason']))
    for name,result in variants.items():
        s=result['summary'];print(name,s['valid_readings'],s['reading_mae_psi'],s['output_error_distribution_psi']['within_0_5_psi'],flush=True)


if __name__=='__main__':run()
