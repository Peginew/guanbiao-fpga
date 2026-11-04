"""Bounded ROI128 pose/calibration/readout and projective-math review."""
from pathlib import Path
import copy,hashlib,importlib.util,json,math,sys
import numpy as np
HERE=Path(__file__).resolve().parent;TASK=HERE.parent;POSE=TASK/'pose';PREV=TASK.parent/'meter_pointer_readout_20261102';DATA=TASK.parent/'meter_cnn_training_20261102'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def rows(p):return[json.loads(x)for x in Path(p).read_text('utf-8-sig').splitlines()if x.strip()]
def module(name,p):
    sys.path.insert(0,str(p.parent));s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def main():
    checks=[]
    def check(ok,name):
        checks.append(dict(name=name,passed=bool(ok)))
        if not ok:raise AssertionError(name)
    pose=module('independent_roi128_pose',POSE/'roi_pose_candidates.py');calmod=module('independent_roi128_cal',POSE/'calibrate_and_score.py')
    train={r['id']:r for r in rows(DATA/'prepared_train.jsonl')};val={r['id']:r for r in rows(DATA/'prepared_validation.jsonl')}
    rr,gray,pred=pose.assets();c=pose.Candidates(rr,gray,pred)
    oldposes={name:{r['id']:r for r in rows(POSE/f'candidate_{name}_pose.jsonl')}for name in('A','B')}
    # Two positive and one negative query from actual128ROI arrays. Query
    # production functions take no native image path or point/pressure labels.
    for ident in('G_005','G_010','G_050'):
        r=val[ident];h=pred[ident]['hub_roi'];radius=r['roi_request']['radius']
        for name in('A','B'):
            result=getattr(c,name)(gray[ident],h,radius);old=oldposes[name][ident]
            check(result['accepted']==old['accepted'],ident+'_'+name+'_ROI_only_runtime_replay')
            if result['accepted']:check(abs(result['relative_roll_deg']-old['relative_roll_deg'])<1e-6,ident+'_'+name+'_orientation_reproduced')
        before=copy.deepcopy(c.rec[ident]);c.rec[ident]['keypoints']={'hub':{'xy':[-999,999]},'thin_terminal':{'xy':[999,-999]}};c.rec[ident]['pressure']={'value':-999,'unit':'bad'}
        result=c.B(gray[ident],h,radius);check(result['accepted']==oldposes['B'][ident]['accepted'] and result.get('relative_roll_deg')==oldposes['B'][ident].get('relative_roll_deg'),ident+'_query_GT_mutation_cannot_change_pose')
        c.rec[ident]=before
    paths=[]
    for name in('A','B'):
        paths.append((POSE/f'candidate_{name}_calibration_psi.json',POSE/f'candidate_{name}_pose.jsonl',POSE/f'candidate_{name}_with_old_B_readout_psi.json'))
        paths.append((POSE/f'joint_new_model/candidate_{name}_calibration_psi.json',POSE/f'joint_new_model/candidate_{name}_pose.jsonl',POSE/f'joint_new_model/candidate_{name}_readout_psi.json'))
    paths.append((POSE/'baseline_ROI128_calibration_psi.json',POSE/'candidate_baseline_ROI128_pose.jsonl',POSE/'baseline_ROI128_old_B_readout_psi.json'))
    reports={}
    for cp,pp,rp in paths:
        cal=read(cp);poses={r['id']:r for r in rows(pp)};report=read(rp);obs=cal['fit_measurements']
        check(cal['fit_groups']==['D','E','F'] and cal['G_used_for_fitting']is False,cp.parent.name+'_'+cp.name+'_train_only_fit')
        for a in obs:
            r=train[a['id']];check(r['loss_mask']==[1,1]and r['pressure']['value']==a['reference_psi'] and poses[a['id']]['accepted'],cp.parent.name+'_'+a['id']+'_visual_train_psi_observation')
        xs=[a['median_reference_angle_deg']for a in cal['anchors']];ys=[a['reference_psi']for a in cal['anchors']];slope,intercept=np.polyfit(xs,ys,1)
        check(abs(slope-cal['slope_psi_per_degree'])<1e-12 and abs(intercept-cal['intercept_psi'])<1e-10,cp.name+'_fit_recomputed')
        check(len(report['rows'])==59 and {r['id']for r in report['rows']}==set(val),rp.name+'_same59_G')
        err=[];accepted=[]
        for row in report['rows']:
            if row['valid']:
                ident=row['id'];r=val[ident];check(poses[ident]['accepted'] and r['target_present'],rp.name+'_'+ident+'_accepted_pose_and_true_gauge')
                a=(row['angle_deg_image']-poses[ident]['relative_roll_deg']-cal['branch_center_deg']+180)%360-180+cal['branch_center_deg']
                value=slope*a+intercept;e=abs(value-r['pressure']['value'])
                check(abs(value-row['psi_estimate'])<1e-10 and abs(e-row['absolute_error_psi'])<1e-10,rp.name+'_'+ident+'_value_and_direct_psi_error')
                err.append(e);accepted.append(ident)
        summary=report['summary'];counts=[int(sum(e<=x for e in err))for x in(.25,.5,1.)]
        check(summary['gauge_images']==56 and summary['negative_images']==3 and summary['valid_readings']==len(err),rp.name+'_unchanged_coverage_denominators')
        check(abs(np.mean(err)-summary['reading_mae_psi'])<1e-10,rp.name+'_MAE')
        check([summary['output_error_distribution_psi'][k]for k in('within_0_25_psi','within_0_5_psi','within_1_0_psi')]==counts,rp.name+'_psi_bins_only_not_targets')
        reports[str(rp.relative_to(TASK))]=dict(valid=len(err),MAE_psi=float(np.mean(err)),within025_05_1psi=counts,accepted_IDs=accepted,source_sha256=sha(rp),calibration_sha256=sha(cp))
    # Combined queries explicitly use NEW hub prediction from their own frame;
    # fixed old train template setup does not require old-hub runtime execution.
    new={r['id']:r for r in rows(TASK/'training/run_001/polar/train_predictions.jsonl')+rows(TASK/'training/run_001/polar/validation_predictions.jsonl')}
    for name in('A','B'):
        joint=rows(POSE/f'joint_new_model/candidate_{name}_pose.jsonl')
        check(all(r['query_predicted_hub_roi']==new[r['id']]['hub_roi']for r in joint),name+'_all_joint_queries_new_same_frame_hub')
    provenance=read(POSE/'baseline_single_roi_probe_provenance.json')
    check(provenance['status']=='BASELINE_IS_PRIOR_PC_ROI128_PROBE_NOT_BOARD_BASELINE','baseline_scope_not_board_or_nativeSIFT')
    check(sha(provenance['original_script'])==provenance['original_script_sha256'] and sha(provenance['original_result_path'])==provenance['original_result_sha256'],'prior_single_template_probe_source_identity')
    original={r['id']:r for r in rows(Path(provenance['original_result_path']))}
    for r in rows(POSE/'candidate_baseline_ROI128_pose.jsonl'):
        o=original[r['id']]
        check(r['accepted']==o['accepted'] and r['relative_roll_deg']==o['relative_roll_deg'] and r['source_sha256']==o['source_sha256'],r['id']+'_baseline_frozen_pose_reused_exactly')
    before=read(POSE/'baseline_ROI128_old_B_readout_psi.json');after=read(POSE/'candidate_B_with_old_B_readout_psi.json')
    before_id={r['id']for r in before['rows']if r['valid']};after_id={r['id']for r in after['rows']if r['valid']}
    added=sorted(after_id-before_id);lost=sorted(before_id-after_id)
    check(len(before_id)==12 and len(after_id)==21 and len(added)==11 and len(lost)==2,'net9_outputs_is_11new_minus2lost')
    after_lookup={r['id']:r for r in after['rows']}
    check(all(after_lookup[i]['absolute_error_psi']<=.5 for i in added),'all11_new_outputs_within05psi_reporting_band')
    delta=dict(before_count=12,after_count=21,net_gain=9,newly_accepted_IDs=added,withdrawn_IDs=lost,
        newly_accepted_within05psi=11,all_after_within05psi=21,
        scope='Same prior neural pair and128ROI input, different pose methods/compute and separately fitted train-only calibration; not board or same-resource validation')
    # Bounded mathematical diagnostic: verify inverse line projection for both
    # native and ROI coordinate paths on three synthetic nonsingular homographies.
    projective=module('review_projective',TASK/'geometry/projective_readout.py');maxerror=0.
    record=dict(bbox_native_xyxy=[100,50,500,450],roi_request=dict(x0=128,y0=64,stride=3))
    h=np.array([120.,130.]);t=np.array([170.,80.]);expected=projective.angle(h,t)
    for H in [np.eye(3),np.array([[1.1,-.1,8],[.05,.95,-3],[0,0,1]]),np.array([[1.,.04,3],[-.03,1.02,4],[.0004,-.0003,1.]])]:
        native=[]
        for p in(h,t):
            q=H@np.r_[p,1];u=q[:2]/q[2];native.append((u-[128,128])/.6+[300,250])
        pp=dict(accepted=True,H_reference_to_query=H.tolist());a=projective.inverse_line(*native,pp,record,True)
        roi=[(p-[128,64]-1)/3 for p in native];b=projective.inverse_line(*roi,pp,record,False)
        error=max(abs((a-expected+180)%360-180),abs((b-expected+180)%360-180));maxerror=max(maxerror,error)
        check(error<1e-10,'inverse_projective_line_native_and_ROI_math')
    cost=read(POSE/'cost_and_timing.json');check(cost['status']=='ROI128_INPUT_AVAILABLE_COMPUTE_AND_MEMORY_FIT_NOT_YET_PROVEN','resource_status_not_misrepresented_as_fit')
    report=dict(status='PASS_ROI128_POSE_AND_TRAIN_ONLY_PSI_COMPARISONS_PC_ONLY',checks=len(checks),failures=[],reports=reports,
        code_sha256={str(p.relative_to(TASK)):sha(p)for p in[POSE/'roi_pose_candidates.py',POSE/'calibrate_and_score.py',POSE/'run_joint_new_model.py',TASK/'geometry/projective_readout.py']},
        inverse_projective_math_maxerror_deg=maxerror,single_vs_multi_reference_delta=delta,
        conclusions=['Both ROI128 methods use predicted hub only; combined path correctly switches all query hubs to new same-source model',
          'ROI-only methods are distinct input-scope comparisons, not nativeSIFT32-read performance improvement',
          'New model alone has no PSI coverage gain; report new accepted/wrong IDs separately before considering replacement',
          'A descriptors alone12.8KB plus image/pyramid/RANSAC; B116640bilinear samples and4.28million comparisons. MCU memory/cycles still unproven',
          'NativeH inverse-line math is a PC diagnostic, not a third production pose candidate or MCU implementation'],
        baseline_ROI128_provenance='Prior fixed single-template ROI128 PC feasibility probe; original signed script/result verified, not current board/nativeSIFT baseline',
        H_or_ABC_opened=False,optimizer_steps=0,OSD_or_hardware_changed=False)
    (HERE/'pose_readout_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps(dict(status=report['status'],checks=len(checks),reports=reports),ensure_ascii=False))
if __name__=='__main__':main()
