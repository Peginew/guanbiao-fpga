"""Independent bounded replay; writes reviewer artifacts only, never trains."""
from pathlib import Path
import argparse, hashlib, importlib.util, json, math, sys
import numpy as np
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
TASK = HERE.parent
ROOT = TASK.parents[1]
DATA = ROOT/'algorithm_work/meter_cnn_training_20261102'
OLD = ROOT/'algorithm_work/meter_pointer_readout_20261102'
PREV = ROOT/'algorithm_work/meter_robust_readout_20261102/pose'
checks = []

def load(p): return json.loads(Path(p).read_text('utf-8-sig'))
def rows(p): return [json.loads(x) for x in Path(p).read_text('utf-8-sig').splitlines() if x.strip()]
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(ok, name):
    checks.append(name)
    if not ok: raise AssertionError(name)
def near(a,b): return a is None and b is None or a is not None and b is not None and abs(a-b)<1e-9
def write(p,x): Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n','utf-8')

def metrics(values,truth):
    accepted=[r for r in values if r['valid'] and truth[r['id']]['target_present']]
    errors=[abs(r['psi_estimate']-truth[r['id']]['pressure']['value']) for r in accepted]
    return dict(valid_readings=len(accepted),mae_psi=float(np.mean(errors)) if errors else None,
                bins={str(t):sum(e<=t for e in errors) for t in [.25,.5,1.]},
                negative_outputs=sum(r['valid'] and not truth[r['id']]['target_present'] for r in values),
                ids=sorted(r['id'] for r in accepted))

def main(final=False):
    truth={r['id']:r for r in rows(DATA/'prepared_validation.jsonl')}
    require(len(truth)==59 and all(x.startswith('G_') for x in truth),'G59_only')
    require(sum(r['target_present'] for r in truth.values())==56,'fixed56_gauge_denominator')
    diag=TASK/'diagnostics/run_003'; ds=load(diag/'summary.json')
    variants={}
    for name,s in ds['variants'].items():
        rr=rows(diag/f'{name}.jsonl'); require(len(rr)==59,name+'_59rows')
        for r in rr:
            require(r['source_sha256']==truth[r['id']]['sha256'],name+'_'+r['id']+'_source')
            if not r.get('eligible',True):
                require(not r['valid'] and r['psi_estimate'] is None,name+'_'+r['id']+'_ineligible_not_read')
                continue
            c=r['conditions']
            model=all(c[k] for k in ['hub_peak_pass','hub_margin_pass','hub_center20_pass',
                'needle_peak_pass','needle_margin_pass','polar_inside_pass','finite_angle_pass'] if c[k] is not None)
            require(model==r['model_permitted'],name+'_'+r['id']+'_model_conditions')
            require(r['valid']==bool(model and c['pose_accepted'] and c['calibration_angle_pass'] and c['calibration_psi_pass']),name+'_'+r['id']+'_joint_conditions')
        eligible=[r for r in rr if r.get('eligible',True)]
        mm=metrics(eligible,truth)
        require(mm['valid_readings']==s['valid_readings'] and near(mm['mae_psi'],s['mae_psi']) and mm['bins']==s['error_distribution_psi'],name+'_independent_metrics')
        variants[name]={r['id']:r for r in rr}
    base=variants['baseline']
    old={r['id']:r for r in load(PREV/'candidate_B_with_old_B_readout_psi.json')['rows']}
    for ident,b in base.items():
        require(b['valid']==old[ident]['valid'] and near(b['psi_estimate'],old[ident]['psi_estimate']),ident+'_same_baseline')
        strict=variants['reference_needle_preserve_hub_permission'][ident]
        if strict.get('eligible',True):
            require(all(strict['conditions'][k]==b['conditions'][k] for k in ['hub_peak_pass','hub_margin_pass','hub_center20_pass']),ident+'_needle_preserves_hub')
        permit=variants['reference_hub_permission_only'][ident]
        if permit.get('eligible',True):
            require(permit['hub_roi']==b['hub_roi'] and permit['angle_deg_image']==b['angle_deg_image'] and permit['relative_roll_deg']==b['relative_roll_deg'],ident+'_hub_permission_no_geometry_change')
            require(all(permit['conditions'][k]==b['conditions'][k] for k in ['needle_peak_pass','needle_margin_pass','polar_inside_pass','pose_accepted','calibration_angle_pass','calibration_psi_pass']),ident+'_hub_permission_retains_other_conditions')
        moved=variants['reference_hub_resampled_keep_old_confidence'][ident]
        if moved.get('eligible',True):
            require(all(moved['conditions'][k]==b['conditions'][k] for k in ['hub_peak_pass','hub_margin_pass']),ident+'_moved_hub_preserves_old_confidence')

    spec=importlib.util.spec_from_file_location('supervised_reference_candidate',TASK/'reference_candidate.py')
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    import torch
    torch.set_num_threads(4)
    silver={r['id']:r for r in rows(OLD/'readout_psi/train_print_pose.jsonl')}
    active=[]; counts={g:dict(silver=0,null=0)for g in ['D','E','F']}
    for it in m.material('train'):
        r=it['record']; p=silver[it['id']]
        if not r['target_present']: it['silver_roll']=None; role='null'
        elif m.good_silver(p): it['silver_roll']=float(p['relative_roll_deg']); role='silver'
        else: continue
        counts[r['source_group']][role]+=1; active.append(it)
    require(counts==dict(D=dict(silver=28,null=3),E=dict(silver=46,null=3),F=dict(silver=18,null=3)),'actual_supervision_counts')
    positive=next(it for it in active if it['silver_roll'] is not None)
    for rot in [-24.,0.,24.]:
        x,y=m.transform(positive,rotation=rot)
        require(abs(float(y[:-1]@m.BINS)-(positive['silver_roll']-rot))<1e-3,'rotation_sign_'+str(rot))
        require(x.shape==(1,128,128) and abs(float(y.sum())-1)<1e-6,'shape_and_target_'+str(rot))
    negative=next(it for it in active if it['silver_roll'] is None)
    require(m.transform(negative,rotation=12.)[1][-1]==1,'true_negative_null')
    net=m.StaticRoll(); require(sum(p.numel()for p in net.parameters())==6226,'6226_params_not_whole_chain')
    costs=[]
    def hook(module,inputs,output):
        if isinstance(module,torch.nn.Conv2d): mac=output.numel()*module.weight[0].numel()
        else: mac=output.numel()*module.in_features
        costs.append(dict(kind=type(module).__name__,output_shape=list(output.shape),MACs=mac,output_elements=output.numel()))
    handles=[m0.register_forward_hook(hook) for m0 in net.modules() if isinstance(m0,(torch.nn.Conv2d,torch.nn.Linear))]
    net(torch.zeros(1,1,128,128))
    for h in handles:h.remove()
    result=dict(status='PASS_BOUNDED_DIAGNOSTICS_AND_CODE_ADMISSION',checks=len(checks),diagnostics_source=sha(TASK/'diagnostics/run_joint_diagnostics.py'),
        candidate_source=sha(TASK/'reference_candidate.py'),candidate_config=sha(TASK/'candidate_config_before_training.json'),
        diagnostic_summary_sha256=sha(diag/'summary.json'),supervision_counts=counts,
        candidate_parameters=6226,whole_neural_pair_plus_candidate_parameters=8437,
        candidate_convolution_and_linear_MACs=sum(r['MACs']for r in costs),layers=costs,
        cost_boundaries='MACs exclude box normalization, annulus generation, softmax/decode, PSI, old hub/polar and memory traffic. No integer C/link/stack/cycle fit proof.',
        hardware_actions=False,H_or_ABC_opened=False,training_by_reviewer=False,
        scope='Execution and diagnostic semantics only; silver is not GT and pose is not yaw. G is development. Error bins are descriptive, no user final target.')
    write(HERE/'diagnostic_and_pretraining_review.json',result)
    if final:
        run=TASK/'reference_cnn/run_001'
        receipt=load(run/'training_receipt.json'); cfg=load(run/'config.json'); history=load(run/'history.json')
        require(receipt['steps']==1600 and len(history)==8,'one_1600_step_run')
        require(sha(run/'best_weights.pt')==receipt['best_checkpoint_sha256'],'checkpoint_sha')
        require(sha(run/'config.json')==receipt['config_sha256'] and sha(run/'history.json')==receipt['history_sha256'],'training_receipt_sha')
        require(cfg['source_code_sha256']==sha(TASK/'reference_candidate.py'),'same_frozen_candidate_source')
        require(cfg['prepared_train_sha256']==sha(DATA/'prepared_train.jsonl'),'same_train_prepared')
        require(cfg['source_silver_sha256']==sha(OLD/'readout_psi/train_print_pose.jsonl'),'same_train_silver')
        labels=load(run/'silver_training_labels.json')
        require(len(labels)==101 and all(r['id'][0]in'DEF' for r in labels),'only_101_DEF_silver_or_null_labels')
        require(sum(r['weight_update']for r in labels)==80 and sum(r['internal_step_selection']for r in labels)==21,'80_update_21_internal_selection')
        ck=torch.load(run/'best_weights.pt',weights_only=True,map_location='cpu')
        require(ck['step']==min(history,key=lambda r:r['F_silver_selection_loss'])['step'],'best_chosen_only_by_F_loss')
        net.load_state_dict(ck['state_dict']);net.eval()
        poses={p['id']:p for p in rows(run/'candidate_pose.jsonl')}
        require(len(poses)==223 and sum(x.startswith('G_')for x in poses)==59,'223_poses_164_train_59_G')
        with torch.inference_mode():
            for split in ['train','validation']:
                for it in m.material(split):
                    p=poses[it['id']]
                    require(p['source_sha256']==it['record']['sha256'] and p['checkpoint_sha256']==sha(run/'best_weights.pt'),it['id']+'_candidate_source')
                    require(not p['native_frame_used'] and not p['query_uses_GT_points'] and not p['query_uses_pressure'],it['id']+'_runtime_inputs')
                    z=net(torch.from_numpy(m.preprocess(it['image'],it['hub'],it['radius'])[None]))[0].numpy()
                    q=np.exp(z-z.max());q/=q.sum();mass=float(q[:-1].sum());dist=q[:-1]/max(mass,1e-12)
                    angle=float(dist@m.BINS);std=float(np.sqrt((dist*(m.BINS-angle)**2).sum()))
                    accepted=bool(mass>=.8 and std<=5 and abs(angle)<24 and np.linalg.norm(it['hub']-63.5)<=20)
                    require(abs(angle-p['relative_roll_deg'])<1e-4 and abs(std-p['conditional_stddev_deg'])<1e-4 and accepted==p['accepted'],it['id']+'_reloaded_forward')
        cal=load(run/'calibration_psi.json'); tr=rows(DATA/'prepared_train.jsonl')
        samples=[]
        for r in tr:
            p=poses.get(r['id'])
            if p and p['accepted'] and r['loss_mask']==[1,1] and r['target_present'] and r['scene']['primary']in{'front_medium_soft_light','front_large_soft_light','front_dim','backlight_or_local_reflection'}:
                h,t=[np.asarray(r['keypoints'][k]['xy'])for k in ['hub','thin_terminal']]
                a=(math.degrees(math.atan2(*(t-h)[::-1]))-p['relative_roll_deg'])%360
                require(r['pressure']['unit']=='psi',r['id']+'_direct_PSI_cal_truth')
                samples.append((r['id'],a,r['pressure']['value']))
        center=math.degrees(math.atan2(np.mean(np.sin(np.radians([r[1]for r in samples]))),np.mean(np.cos(np.radians([r[1]for r in samples])))))%360
        unwrapped=[(i,(a-center+180)%360-180+center,p)for i,a,p in samples]
        anchors=[(float(np.median([a for i,a,p in unwrapped if p==psi])),psi)for psi in sorted({r[2]for r in samples})]
        coeff=np.polyfit([r[0]for r in anchors],[r[1]for r in anchors],1)
        require(near(center,cal['branch_center_deg']) and near(float(coeff[0]),cal['slope_psi_per_degree']) and near(float(coeff[1]),cal['intercept_psi']),'independent_train_only_cal_fit')
        require({r[0]for r in samples}=={r['id']for r in cal['fit_measurements']} and all(r[0][0]in'DEF'for r in samples),'calibration_IDs_no_G')
        out=load(run/'readout_psi.json'); pp={p['id']:p for p in rows(OLD/'polar_angle/run_001/validation_predictions.jsonl')}
        for r in out['rows']:
            ident=r['id']; pose=poses[ident]; p=pp[ident]
            a=(p['angle_deg_image']-pose['relative_roll_deg']-center+180)%360-180+center
            psi=coeff[0]*a+coeff[1];lo,hi=cal['supported_angle_interval_deg'];plo,phi=cal['supported_pressure_interval_psi']
            valid=bool(p['valid'] and pose['accepted'] and lo<=a<=hi and plo<=psi<=phi)
            require(valid==r['valid'] and (not valid or near(float(psi),r['psi_estimate'])),ident+'_independent_PSI_permission_value')
            require(r['psi_reference_for_scoring']==truth[ident]['pressure']['value'] and r['source_sha256']==truth[ident]['sha256'],ident+'_direct_user_truth')
        actual=metrics(out['rows'],truth); reported=out['summary']
        require(actual['valid_readings']==reported['valid_readings'] and near(actual['mae_psi'],reported['reading_mae_psi']),'independent_final_PSI_metrics')
        require(all(actual['bins'][str(t)]==reported['output_error_distribution_psi'][f'within_{str(t).replace(".","_")}_psi']for t in[.25,.5,1.]),'independent_final_PSI_bins')
        before=metrics(list(base.values()),truth)
        result.update(status='EXECUTION_REPLAY_PASS_CANDIDATE_FAIL_KEEP_BASELINE',checks=len(checks),
            checkpoint_sha256=sha(run/'best_weights.pt'),best_step=ck['step'],training_receipt_sha256=sha(run/'training_receipt.json'),
            candidate_pose_sha256=sha(run/'candidate_pose.jsonl'),calibration_sha256=sha(run/'calibration_psi.json'),readout_sha256=sha(run/'readout_psi.json'),
            baseline=before,candidate=actual,gained_ids=sorted(set(actual['ids'])-set(before['ids'])),lost_ids=sorted(set(before['ids'])-set(actual['ids'])),
            candidate_error_rows=[dict(id=r['id'],reference_psi=r['psi_reference_for_scoring'],estimate_psi=r['psi_estimate'],absolute_error_psi=r['absolute_error_psi'])for r in out['rows']if r['valid']],
            selection_decision='Do not adopt new referenceCNN. Preserve previous2211 + multi-referenceROI128 ring. No new G-driven training or threshold changes.',
            final_PSI_is_new_train_calibration_not_same_cal_ablation=True,
            remaining='Input-domain equivalence, static silver quality, true linked MCU memory and fixed-point/full-cycle proof retain their stated limits. No deployed accuracy claim.')
        audit=TASK/'input_audit'
        if (audit/'completion.json').exists():
            start=len(checks); ac=load(audit/'completion.json')
            for rel,h in ac['files_sha256'].items():require(sha(audit/rel)==h,'audit_SHA_'+rel)
            lookup={r['id']:r for r in tr};lookup.update(truth)
            vv=load(audit/'visual_review_24.json')['records']
            require(len(vv)==24 and all(r['id'][0]in'DEFG'for r in vv),'24_DEF_G_audit_records')
            for r in vv:require(r['source_sha256']==lookup[r['id']]['sha256'] and r['original_keypoint_loss_mask']==lookup[r['id']]['loss_mask'],r['id']+'_audit_source_mask')
            side=rows(audit/'static_print_direction_sidecar.jsonl');require(len(side)==8,'eight_visual_sidecars')
            reference=next(r['absolute_image_print_axis_angle_deg']for r in side if r['id']=='D_002')
            for r in side:
                request=lookup[r['id']]['roi_request'];points=[]
                for anchor in r['anchors'].values():
                    xy=(np.array(anchor['native_xy'])-[request['x0'],request['y0']]-(request['stride']-1)/2)/request['stride']
                    require(np.max(abs(xy-anchor['roi_xy']))<1e-10,r['id']+'_static_anchor_mapping');points.append(xy)
                d=points[0]-points[1];angle=math.degrees(math.atan2(d[1],d[0]))%360
                require(abs(angle-r['absolute_image_print_axis_angle_deg'])<1e-10,r['id']+'_static_angle')
                require(abs((angle-reference+180)%360-180-r['relative_print_axis_angle_deg'])<1e-10,r['id']+'_relative_static_angle')
                require(not r['independently_human_certified_gold'] and not r['ready_as_training_ground_truth'] and not r['uncertainty_is_certified_error_bound'],r['id']+'_not_gold')
            domain=load(audit/'input_domain_contract.json')
            for path,h in domain['source_sha256'].items():require(sha(path)==h,'domain_RTL_'+Path(path).name)
            require(not domain['current_dataset_paired_actual_boardROI_available'],'actual_domain_pair_not_proven')
            result['input_audit_review']=dict(checks=len(checks)-start,completion_sha256=sha(audit/'completion.json'),audit_records=24,manual_static_sidecars=8,
                native_to_ROI_and_relative_angles_recomputed=True,independent_visual_scope='G/F12 native/ROI panels plus8 manual-axis panel pairs viewed; not a24-image gold recertification',
                domain_equivalence_proven=False,source_stage='AWB-after RGB grayscale; no unsupported raw-sensor-domain claim',manual_sidecar_is_gold_or_training_labels=False,
                canonical_changed=False,known_board_zero_dumps_are_not_camera_black_proof=True,H_or_ABC_opened=False)
            result['checks']=len(checks)
        write(HERE/'supervision_review.json',result)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--final',action='store_true');args=ap.parse_args();main(args.final)
