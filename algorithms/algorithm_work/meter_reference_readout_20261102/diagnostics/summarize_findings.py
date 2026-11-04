"""Summarize frozen diagnostic output; no inference, fitting or threshold changes."""
from pathlib import Path
import argparse,csv,hashlib,json

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n','utf-8')

def main(run):
    result=load(run/'joint_failure_decomposition.json');summ=load(run/'summary.json')
    manifest=load(run/'manifest.json');joint=result['rows'];checks=[]
    assert len(joint)==59 and len(set(r['id']for r in joint))==59
    for path,digest in manifest['source_sha256'].items():
        assert sha(ROOT/path)==digest,path
    checks.append('All 16 frozen input/module/weight hashes unchanged after inference')
    for r in joint:
        b=r['baseline'];cf=r['counterfactuals']
        strict=cf['reference_needle_preserve_hub_permission']
        if strict['eligible']:
            for key in ['hub_peak_pass','hub_margin_pass','hub_center20_pass']:
                assert strict['conditions'][key]==b['conditions'][key]
        permit=cf['reference_hub_permission_only']
        if permit['eligible']:
            for key in ['hub_roi','angle_deg_image','pose_accepted','relative_roll_deg','needle_score','needle_margin']:
                assert permit[key]==b[key],(r['id'],key)
        keep=cf['reference_hub_resampled_keep_old_confidence']
        if keep['eligible']:
            for key in ['hub_peak_pass','hub_margin_pass']:
                assert keep['conditions'][key]==b['conditions'][key]
        if cf['reference_hub_resampled']['eligible']:
            assert r['reference_hub_roi']==cf['reference_hub_resampled']['hub_roi']
    checks.extend(['Strict needle-reference diagnostic preserves original three hub conditions',
        'Hub-permission-only diagnostic preserves original center, angle, needle scores and estimated pose',
        'Reference-hub resampling with old confidence preserves both original hub-confidence conditions',
        'Reference-hub predictor and pose use identical visual-reference center'])
    pose_only=[]
    for r in joint:
        b=r['baseline']
        if not b['target_present']or not b['model_permitted']or b['pose_accepted']:continue
        proposed=b['psi_unrestricted_diagnostic'];ref=b['psi_reference_for_scoring']
        pose_only.append(dict(id=r['id'],scene=b['scene'],
            all_original_model_conditions_permitted=True,
            estimated_pose_rejected=True,estimated_ring_score=b['pose_score'],estimated_ring_margin=b['pose_margin'],
            rejected_ring_candidate_roll_deg=b['relative_roll_deg'],
            candidate_calibration_angle_supported=b['conditions']['calibration_angle_pass'],
            candidate_calibration_psi_supported=b['conditions']['calibration_psi_pass'],
            candidate_psi_DIAGNOSTIC_NOT_OUTPUT=proposed,
            psi_reference_for_scoring=ref,
            candidate_abs_error_psi_DIAGNOSTIC=abs(proposed-ref)if proposed is not None and ref is not None else None,
            visual_direction_reference_available=r['full_reference_eligible'],
            visual_needle_angle_error_deg=r['baseline_angle_error_deg'],
            is_verified_pose_ground_truth=False))
    passed_candidate=[r for r in pose_only if r['candidate_calibration_angle_supported']and r['candidate_calibration_psi_supported']]
    cal_first=[r['id']for r in joint if r['baseline']['reason']=='PREDICTED_DIRECTION_OUTSIDE_TRAIN_CALIBRATION']
    changes={k:dict(eligible_gauges=v['eligible_gauges'],readings=v['valid_readings'],mae_psi=v['mae_psi'],
        output_error_over05psi=v['error_over05psi'],gained_ids=v.get('gained_output_ids',[]),lost_ids=v.get('lost_output_ids',[]))
        for k,v in summ['variants'].items()}
    findings=dict(status='FROZEN_DIAGNOSTIC_FINDINGS_NOT_MODEL_IMPROVEMENT',unit='psi',
        primary_recommendation='Develop exactly one whole-ROI static-print reference-direction candidate; keep original hub+polar and calibration frozen for controlled comparison.',
        evidence=dict(component_comparisons=changes,
            positives_nonexclusive_failures=summ['variants']['baseline']['gauges_only_nonexclusive_conditions'],
            only_pose_blocks_after_all_model_conditions=len(pose_only),
            only_pose_blocks_and_rejected_candidate_is_in_calibration_range=len(passed_candidate),
            those_in_range_ids=[r['id']for r in passed_candidate],
            first_rejection_calibration_boundary_ids=cal_first),
        interpretation=[
            'A perfect provided needle direction does not restore coverage under existing hub+pose+calibration conditions; the strict needle-only control gives20 versus21 baseline.',
            'External reliable hub evidence alone gives23; moving the center while preserving old confidence also gives23, with six gains and four losses; combined gives26, not an isolated hub-accuracy effect.',
            'Estimated pose fails24 of56 gauge images, mostly ring-margin ambiguity; original needle score fails5. Failures overlap and are not a causal ranking by count alone.',
            'Rejected ring candidates such asG042/G044 can produce large PSI errors. They must remain rejected; these results do not authorize lowering the ring margin.',
            'No query pose ground truth is available. Neither nativeSIFT nor ring candidates are treated as verified pose truth.',
            'The frozen empirical angle range rejects some endpoint observations even with visual needle references. Do not expand range or adjust thresholds usingG.',
            'Visual reference points carry declared annotation uncertainty. This diagnostic is not an independent gold-label accuracy evaluation.',
            '0.25/0.5/1psi are descriptive distributions, not a frozen user acceptance epsilon; no formal false-acceptance claim.'],
        contract_checks=checks,no_new_training=True,ABC_H_opened=False,hardware_actions=False,
        source_sha256=dict(joint=sha(run/'joint_failure_decomposition.json'),summary=sha(run/'summary.json'),
            run_manifest=sha(run/'manifest.json'),summary_driver=sha(__file__)))
    write(run/'findings.json',findings)
    with(run/'姿态支路重点复核.csv').open('w',encoding='utf-8-sig',newline='')as f:
        w=csv.DictWriter(f,fieldnames=list(pose_only[0]));w.writeheader();w.writerows(pose_only)
    print(json.dumps(dict(pose_only=len(pose_only),pose_only_in_candidate_calibration=len(passed_candidate),
        ids=[r['id']for r in passed_candidate],checks=checks),ensure_ascii=False,indent=2))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--run',type=Path,required=True);main(a.parse_args().run)
