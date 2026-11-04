"""Frozen ROI128 readout failure decomposition and visual-reference diagnostics.

No training, threshold search, nativeSIFT, A/B/C/H inputs, or device access.
References below are bounded AI visual annotations, not certified ground truth.
Replacing the hub resamples BOTH the polar network and the frozen ring pose.
These counterfactuals diagnose dependencies; they are not deployable outputs.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import importlib.util
import json
import math
import sys
import time

sys.dont_write_bytecode = True
import cv2
import numpy as np
import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DATA = ROOT / 'algorithm_work/meter_cnn_training_20261102'
OLD = ROOT / 'algorithm_work/meter_pointer_readout_20261102'
POSE = ROOT / 'algorithm_work/meter_robust_readout_20261102/pose'
EXPECTED_HUB = 'c221678efa4762bed298828b2e8e8ba3c2a6b343c2c16efe35aec77a85c896df'
EXPECTED_POLAR = 'd139ecdc1059829be18e23eaf5d503d5c9d59a798d2986774441f88cc1804882'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(p):
    return json.loads(Path(p).read_text('utf-8-sig'))


def rows(p):
    return [json.loads(x) for x in Path(p).read_text('utf-8-sig').splitlines() if x.strip()]


def write(p, value):
    Path(p).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def write_rows(p, value):
    Path(p).write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in value), 'utf-8')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def finite(x):
    return x is not None and math.isfinite(float(x))


def delta(a, b):
    return abs((a - b + 180) % 360 - 180)


def angle(h, t):
    return math.degrees(math.atan2(t[1] - h[1], t[0] - h[0])) % 360


def bounded_point(record, key, index):
    p = record['roi_keypoints'][key]
    u = record['keypoints'][key].get('uncertainty_px')
    return bool(record['target_present'] and record['loss_mask'][index] == 1 and
                p.get('visibility') == 'visible' and p.get('inside_roi') and
                p.get('xy') is not None and u is not None and 0 <= u <= 8)


def annotate_gates(record, prediction, hub_evidence, pose, cal, outside, reference_mode=None):
    """Evaluate every available subcondition, even after an earlier condition fails."""
    center = prediction['hub_roi']
    theta = prediction['angle_deg_image']
    hub_distance = float(np.linalg.norm(np.asarray(center) - [63.5, 63.5]))
    manual_hub = reference_mode in {'reference_hub', 'both_reference', 'hub_permission_only'}
    manual_direction = reference_mode in {'direction_supplies_evidence', 'both_reference', 'needle_reference_keep_hub'}
    entire_model_external = reference_mode in {'direction_supplies_evidence', 'both_reference'}
    hp = hub_evidence['peaks'][0] if not manual_hub else None
    hm = hub_evidence['margins'][0] if not manual_hub else None
    npk = prediction.get('score') if not manual_direction else None
    nm = prediction.get('margin') if not manual_direction else None
    model_conditions = dict(
        hub_peak_pass=None if manual_hub or entire_model_external else hp >= .3,
        hub_margin_pass=None if manual_hub or entire_model_external else hm >= .02,
        hub_center20_pass=None if entire_model_external else hub_distance <= 20,
        needle_peak_pass=None if manual_direction else npk >= .3,
        needle_margin_pass=None if manual_direction else nm >= .02,
        polar_inside_pass=None if manual_direction else outside <= .05,
        finite_angle_pass=finite(theta))
    # Manual bounded evidence replaces only the explicitly named model stage.
    model_permitted = all(v for v in model_conditions.values() if v is not None)
    roll = pose.get('relative_roll_deg')
    reference_angle = (theta - roll - cal['branch_center_deg'] + 180) % 360 - 180 + cal['branch_center_deg'] if finite(theta) and finite(roll) else None
    psi_unrestricted = cal['slope_psi_per_degree'] * reference_angle + cal['intercept_psi'] if reference_angle is not None else None
    lo, hi = cal['supported_angle_interval_deg']
    plo, phi = cal['supported_pressure_interval_psi']
    conditions = dict(**model_conditions,
        pose_center14_pass=hub_distance <= 14,
        pose_score_pass=pose['score'] >= .64 if finite(pose.get('score')) else None,
        pose_margin_pass=pose['margin'] >= .018 if finite(pose.get('margin')) else None,
        pose_search_interior_pass=abs(roll) < 24 if finite(roll) else None,
        pose_accepted=bool(pose['accepted']),
        calibration_angle_pass=lo <= reference_angle <= hi if reference_angle is not None else None,
        calibration_psi_pass=plo <= psi_unrestricted <= phi if psi_unrestricted is not None else None)
    valid = bool(model_permitted and conditions['pose_accepted'] and
                 conditions['calibration_angle_pass'] and conditions['calibration_psi_pass'])
    if not model_permitted:
        reason = 'PREDICTION_NOT_PERMITTED'
    elif not pose['accepted']:
        reason = pose['reason']
    elif not conditions['calibration_angle_pass']:
        reason = 'PREDICTED_DIRECTION_OUTSIDE_TRAIN_CALIBRATION'
    elif not conditions['calibration_psi_pass']:
        reason = 'PREDICTED_VALUE_OUTSIDE_TRAIN_PRESSURE_SUPPORT'
    else:
        reason = 'PC_EMPIRICALLY_CALIBRATED_READING_PSI'
    ref_psi = record['pressure'].get('value') if record['pressure'].get('unit') == 'psi' else None
    error = abs(psi_unrestricted - ref_psi) if valid and ref_psi is not None else None
    return dict(id=record['id'], source_sha256=record['sha256'], target_present=record['target_present'],
        scene=record['scene']['primary'], conditions=conditions, model_permitted=bool(model_permitted),
        hub_roi=center, hub_score=hp, hub_margin=hm, hub_center_distance_roi=hub_distance,
        angle_deg_image=theta, needle_score=npk, needle_margin=nm, polar_outside_fraction=outside,
        pose_accepted=bool(pose['accepted']), pose_reason=pose['reason'], pose_score=pose.get('score'),
        pose_margin=pose.get('margin'), relative_roll_deg=roll,
        reference_angle_deg=reference_angle,
        angle_below_supported_deg=max(lo-reference_angle, 0) if reference_angle is not None else None,
        angle_above_supported_deg=max(reference_angle-hi, 0) if reference_angle is not None else None,
        psi_unrestricted_diagnostic=psi_unrestricted, valid=valid,
        psi_estimate=psi_unrestricted if valid else None, psi_reference_for_scoring=ref_psi,
        absolute_error_psi=error, reason=reason,
        all_failed_conditions=[k for k,v in conditions.items() if v is False],
        unavailable_conditions=[k for k,v in conditions.items() if v is None],
        reference_mode=reference_mode, pose_is_ground_truth=False,
        unrestricted_psi_is_not_a_permitted_reading=True)


def summarize(values, denominator=56):
    sub = [r for r in values if r.get('eligible', True)]
    pos = [r for r in sub if r['target_present']]
    accept = [r for r in pos if r['valid']]
    errors = [r['absolute_error_psi'] for r in accept if r['absolute_error_psi'] is not None]
    keys = sorted(set(k for r in sub for k in r.get('conditions', {})))
    return dict(images=len(values), eligible_images=len(sub), eligible_gauges=len(pos),
        valid_readings=len(accept), fixed_all_gauge_denominator=denominator,
        coverage_all56=len(accept)/denominator if denominator else None,
        coverage_eligible=len(accept)/len(pos) if pos else None,
        mae_psi=float(np.mean(errors)) if errors else None,
        max_abs_error_psi=max(errors) if errors else None,
        error_distribution_psi={str(t):sum(x<=t for x in errors) for t in [.25,.5,1.]},
        error_over05psi=sum(x>.5 for x in errors),
        eligible_negative_count=sum(not r['target_present'] for r in sub),
        negative_outputs=sum(not r['target_present'] and r['valid'] for r in sub),
        rejection_first_reasons={k:sum(r['reason']==k for r in sub if not r['valid'])
            for k in sorted(set(r['reason'] for r in sub if not r['valid']))},
        nonexclusive_conditions={k:dict(failed=sum(r['conditions'].get(k) is False for r in sub),
                passed=sum(r['conditions'].get(k) is True for r in sub),
                unavailable=sum(r['conditions'].get(k) is None for r in sub)) for k in keys},
        metrics_are_PC_diagnostics_not_board_acceptance=True,
        error_bins_are_descriptive_not_user_accuracy_target=True)


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(4)
    cv2.setNumThreads(1)
    torch.set_grad_enabled(False)
    started = time.monotonic()
    weights = OLD/'polar_angle/run_001/best_weights.pt'
    assert sha(DATA/'run_002/best_weights.pt') == EXPECTED_HUB
    assert sha(weights) == EXPECTED_POLAR
    sys.path.insert(0, str(DATA))
    polar = module('diagnostic_frozen_polar', OLD/'polar_angle/train_polar.py')
    posemod = module('diagnostic_frozen_pose', POSE/'roi_pose_candidates.py')
    recs, gray, predictions = posemod.assets()
    assert all(r['source_group'] in {'D','E','F','G'} for r in recs)
    query = [r for r in recs if r['source_group']=='G']
    assert len(query)==59
    estimator = posemod.Candidates(recs, gray, predictions)
    frozen_setup = load(POSE/'template_setup.json')
    assert estimator.offsets == frozen_setup['reference_offsets']
    pose_by_id = {r['id']:r for r in rows(POSE/'candidate_B_pose.jsonl')}
    cal = load(POSE/'candidate_B_calibration_psi.json')
    original_readout = {r['id']:r for r in load(POSE/'candidate_B_with_old_B_readout_psi.json')['rows']}
    hubs = {r['id']:r for r in load(DATA/'run_002/validation_evaluation.json')['rows']}
    model = polar.PolarNeedle()
    model.load_state_dict(torch.load(weights, map_location='cpu', weights_only=True)['state_dict'])
    model.eval()
    assert sum(p.numel() for p in model.parameters())==1009
    policy = dict(input='Frozen proxy ROI128 U8 from existing cache, not nativeSIFT/actualCSI proof',
        hub_checkpoint_sha256=EXPECTED_HUB, polar_checkpoint_sha256=EXPECTED_POLAR,
        thresholds=dict(hub_peak=.3,hub_margin=.02,hub_center20=20,
            needle_peak=.3,needle_margin=.02,polar_outside_max=.05,pose_center14=14,
            pose_peak=.64,pose_margin=.018,pose_roll_strict_interior=24),
        visual_reference_rule='Existing visible in-ROI loss_mask1 heads; declared native uncertainty<=8px; no pressure inversion',
        calibration='Frozen existing candidateB train-only fit, no refitting or extrapolation',
        uncertainty='AI annotations bounded by declaration, not certified gold; PSI reference accuracy unknown',
        diagnosis_limits=['Manual source replacing model evidence is not model recognition.',
            'Hub reference changes frozen polar feature distribution; not a strict oracle upper bound.',
            'Ring pose remains estimated and is not ground truth.',
            '0.25/0.5/1psi distributions are not final accuracy targets.',
            'Reference-only negatives are ineligible, not successful negative rejection.'],
        training=False, native_SIFT_used=False, ABC_or_H_opened=False, device_actions=False)
    write(out/'frozen_contract.json',policy)
    policy['reference_controls']={
        'reference_needle_preserve_hub_permission':'Replace needle peak/margin/polar sampling-domain evidence only; retain original hub peak/margin/center20.',
        'reference_hub_permission_only':'Skip original hub peak/margin only; original center, polar samples, polar permission and pose unchanged.',
        'reference_hub_resampled_keep_old_confidence':'New reference center resamples polar+pose, but retain original hub peak/margin as diagnostic control; these scores are not new-center confidence.',
        'reference_direction_supplies_model_evidence':'Manual double-point direction replaces ENTIRE model permission, not needle-only; existing pose remains estimated.'}
    write(out/'frozen_contract.json',policy)
    variants = {k:[] for k in ['baseline','reference_direction_keep_model_gates',
        'reference_direction_supplies_model_evidence','reference_hub_resampled',
        'reference_hub_and_direction','reference_needle_preserve_hub_permission',
        'reference_hub_permission_only','reference_hub_resampled_keep_old_confidence']}
    records = []
    for r in query:
        ident=r['id']; p=dict(predictions[ident]); h=hubs[ident]; po=pose_by_id[ident]
        feature,outside=polar.polar_features(gray[ident],p['hub_roi'],r['roi_request']['radius'])
        fresh_angle,fresh_score,fresh_margin=polar.decode(model(torch.from_numpy(feature[None])).numpy()[0])
        assert delta(fresh_angle,p['angle_deg_image'])<1e-4
        assert abs(fresh_score-p['score'])<1e-5 and abs(fresh_margin-p['margin'])<1e-5
        base=annotate_gates(r,p,h,po,cal,outside)
        assert base['model_permitted']==p['valid']
        expected=original_readout[ident]
        assert base['valid']==expected['valid'] and base['reason']==expected['reason']
        if base['valid']:assert abs(base['psi_estimate']-expected['psi_estimate'])<1e-12
        variants['baseline'].append(dict(base,eligible=True))
        h_ok=bounded_point(r,'hub',0);t_ok=bounded_point(r,'thin_terminal',1);full=h_ok and t_ok
        rh=r['roi_keypoints']['hub']['xy'] if h_ok else None
        rt=r['roi_keypoints']['thin_terminal']['xy'] if t_ok else None
        ref_angle=angle(rh,rt) if full else None
        ref_info=dict(id=ident,source_sha256=r['sha256'],scene=r['scene']['primary'],
            hub_reference_eligible=h_ok,full_reference_eligible=full,
            reference_hub_roi=rh,reference_thin_terminal_roi=rt,reference_angle_deg_image=ref_angle,
            reference_hub_uncertainty_native_px=r['keypoints']['hub'].get('uncertainty_px'),
            reference_tip_uncertainty_native_px=r['keypoints']['thin_terminal'].get('uncertainty_px'),
            baseline_hub_error_roi=float(np.linalg.norm(np.asarray(p['hub_roi'])-rh)) if h_ok else None,
            baseline_angle_error_deg=delta(p['angle_deg_image'],ref_angle) if full else None)
        for name,mode in [('reference_direction_keep_model_gates',None),
                          ('reference_direction_supplies_model_evidence','direction_supplies_evidence'),
                          ('reference_needle_preserve_hub_permission','needle_reference_keep_hub')]:
            if full:
                rp=dict(p,angle_deg_image=ref_angle)
                result=annotate_gates(r,rp,h,po,cal,outside,mode)
                variants[name].append(dict(result,eligible=True))
            else:
                variants[name].append(dict(base,eligible=False,valid=False,psi_estimate=None,
                    absolute_error_psi=None,reason='NO_BOUNDED_VISIBLE_FULL_REFERENCE'))
        if h_ok:
            control=annotate_gates(r,p,h,po,cal,outside,'hub_permission_only')
            variants['reference_hub_permission_only'].append(dict(control,eligible=True))
            f2,o2=polar.polar_features(gray[ident],rh,r['roi_request']['radius'])
            a2,s2,m2=polar.decode(model(torch.from_numpy(f2[None])).numpy()[0])
            po2=dict(id=ident,split='validation',source_sha256=r['sha256'],
                query_uses_visual_reference_hub_for_DIAGNOSIS=True,
                query_pressure_used=False,native_SIFT_used=False,
                **estimator.B(gray[ident],rh,r['roi_request']['radius']))
            rp=dict(p,hub_roi=list(rh),angle_deg_image=a2,score=s2,margin=m2)
            result=annotate_gates(r,rp,h,po2,cal,o2,'reference_hub')
            variants['reference_hub_resampled'].append(dict(result,eligible=True,
                frozen_polar_input_distribution_changed=True,pose_detail=po2))
            control=annotate_gates(r,rp,h,po2,cal,o2,'reference_hub_keep_old_confidence')
            variants['reference_hub_resampled_keep_old_confidence'].append(dict(control,eligible=True,
                frozen_polar_input_distribution_changed=True,original_hub_score_used_only_as_control=True,pose_detail=po2))
            ref_info.update(resampled_polar_input_sha256=hashlib.sha256(f2.tobytes()).hexdigest(),
                original_polar_input_sha256=hashlib.sha256(feature.tobytes()).hexdigest(),
                reference_hub_polar_angle_deg=a2,reference_hub_polar_score=s2,
                reference_hub_polar_margin=m2,reference_hub_pose_accepted=po2['accepted'],
                reference_hub_angle_error_deg=delta(a2,ref_angle) if full else None)
            if full:
                rr=dict(rp,angle_deg_image=ref_angle)
                result=annotate_gates(r,rr,h,po2,cal,o2,'both_reference')
                variants['reference_hub_and_direction'].append(dict(result,eligible=True,pose_detail=po2))
            else:
                variants['reference_hub_and_direction'].append(dict(base,eligible=False,valid=False,
                    psi_estimate=None,absolute_error_psi=None,reason='NO_BOUNDED_VISIBLE_FULL_REFERENCE'))
        else:
            for name in ['reference_hub_resampled','reference_hub_and_direction',
                         'reference_hub_permission_only','reference_hub_resampled_keep_old_confidence']:
                variants[name].append(dict(base,eligible=False,valid=False,psi_estimate=None,
                    absolute_error_psi=None,reason='NO_BOUNDED_VISIBLE_HUB_REFERENCE'))
        records.append(ref_info)
    for name,values in variants.items():write_rows(out/f'{name}.jsonl',values)
    joint=[]
    reference={r['id']:r for r in records}
    maps={k:{r['id']:r for r in v}for k,v in variants.items()}
    for r in query:
        ident=r['id'];entry=dict(reference[ident],psi_reference_for_scoring=r['pressure'].get('value'),
            baseline=maps['baseline'][ident],counterfactuals={k:maps[k][ident]for k in variants if k!='baseline'})
        joint.append(entry)
    write(out/'joint_failure_decomposition.json',dict(status='FROZEN_READOUT_ALL_CONDITIONS_AND_REFERENCE_DIAGNOSTICS',
        unit='psi',images=59,gauges=56,negatives=3,rows=joint))
    csvrows=[]
    for row in joint:
        flat={k:v for k,v in row.items() if k not in {'baseline','counterfactuals'}}
        for name,value in [('baseline',row['baseline']),*row['counterfactuals'].items()]:
            for k,v in value.items():
                if k in {'conditions','pose_detail'}:continue
                flat[f'{name}.{k}']=json.dumps(v,ensure_ascii=False)if isinstance(v,(list,dict))else v
            for k,v in value['conditions'].items():flat[f'{name}.condition.{k}']=v
        csvrows.append(flat)
    fields=list(dict.fromkeys(k for r in csvrows for k in r))
    with(out/'逐图联合失败分解.csv').open('w',encoding='utf-8-sig',newline='')as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(csvrows)
    summaries={name:summarize(values)for name,values in variants.items()}
    summaries['baseline']['gauges_only_nonexclusive_conditions']=summarize([r for r in variants['baseline']if r['target_present']])['nonexclusive_conditions']
    # Comparisons always use the same eligible subset; no subset selection by outcome.
    for name,values in variants.items():
        if name=='baseline':continue
        eligible={r['id']for r in values if r['eligible']}
        summaries[name]['baseline_same_reference_subset']=summarize([r for r in variants['baseline']if r['id']in eligible])
        summaries[name]['gained_output_ids']=[r['id']for r in values if r['eligible']and r['valid']and not maps['baseline'][r['id']]['valid']]
        summaries[name]['lost_output_ids']=[r['id']for r in values if r['eligible']and not r['valid']and maps['baseline'][r['id']]['valid']]
    summary=dict(status='COMPLETED_REFERENCE_DIAGNOSIS_NOT_MODEL_IMPROVEMENT',unit='psi',
        variants=summaries,by_scene={scene:{name:summarize([r for r in values if r['scene']==scene],
            denominator=sum(r['target_present']for r in variants['baseline']if r['scene']==scene))for name,values in variants.items()}
            for scene in sorted(set(r['scene']for r in variants['baseline']))},
        elapsed_s=time.monotonic()-started,training=False,ABC_or_H_opened=False,device_actions=False)
    write(out/'summary.json',summary)
    inputs=[DATA/'prepared_train.jsonl',DATA/'prepared_validation.jsonl',DATA/'roi_cache_train.npz',DATA/'roi_cache_validation.npz',
        DATA/'run_002/best_weights.pt',DATA/'run_002/validation_evaluation.json',weights,
        OLD/'polar_angle/run_001/train_predictions.jsonl',OLD/'polar_angle/run_001/validation_predictions.jsonl',
        OLD/'polar_angle/train_polar.py',POSE/'roi_pose_candidates.py',POSE/'candidate_config.json',POSE/'template_setup.json',
        POSE/'candidate_B_pose.jsonl',POSE/'candidate_B_calibration_psi.json',POSE/'candidate_B_with_old_B_readout_psi.json']
    manifest=dict(source_sha256={str(p.relative_to(ROOT)).replace('\\','/'):sha(p)for p in inputs},
        driver_sha256=sha(__file__),outputs_sha256={p.name:sha(p)for p in out.iterdir()if p.is_file()},
        original_inputs_written=False,model_training_performed=False,forbidden_groups_not_loaded=['A','B','C','H'])
    write(out/'manifest.json',manifest)
    print(json.dumps({k:{q:v for q,v in x.items()if q in ['valid_readings','eligible_gauges','mae_psi','error_over05psi','gained_output_ids','lost_output_ids']}
        for k,x in summaries.items()},ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    run(p.parse_args().out)
