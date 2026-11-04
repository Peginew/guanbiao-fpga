"""Replay both completed candidate checkpoints on G; no optimizer or H."""
from pathlib import Path
import hashlib,importlib.util,json,sys
import numpy as np
import torch
HERE=Path(__file__).resolve().parent;TASK=HERE.parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def module(name,p):
    sys.path.insert(0,str(p.parent));s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def main():
    torch.set_num_threads(2);checks=[]
    def check(ok,name):
        checks.append(dict(name=name,passed=bool(ok)))
        if not ok:raise AssertionError(name)
    a=module('results_aux',TASK/'keypoint_aux/train_aux.py');b=module('results_polar',TASK/'polar_angle/train_polar.py')
    arun=TASK/'keypoint_aux/run_A';brun=TASK/'polar_angle/run_001';summaries={}
    areceipt=read(arun/'training_receipt.json');acfg=read(arun/'training_config.json');ahist=read(arun/'history.json');astored=read(arun/'validation_evaluation.json')
    check(areceipt['completed_steps']==2400 and len(ahist)==12,'A_2400_steps12_evaluations')
    check(min(ahist,key=lambda r:r['validation']['validation_or_training_loss'])['step']==areceipt['best_step'],'A_min_G_loss_selection')
    check(areceipt['trainer_sha256']==sha(TASK/'keypoint_aux/train_aux.py') and areceipt['best_checkpoint_sha256']==sha(arun/'best_weights.pt'),'A_source_checkpoint_identity')
    ack=torch.load(arun/'best_weights.pt',weights_only=True);training=torch.load(arun/'best_training_aux_state.pt',weights_only=True)
    check(ack['training_only_aux_removed'] is True and len(ack['state_dict'])==24,'A_export_only1202_main_network')
    check(all(torch.equal(v,training['base_state_dict'][k])for k,v in ack['state_dict'].items()),'A_export_same_selected_training_base_weights')
    check(ack['training_steps']==areceipt['best_step'] and ack['warm_checkpoint_sha256']==a.WARM_SHA,'A_selected_step_and_warm_identity')
    am=a.base.Direct(4);am.load_state_dict(ack['state_dict']);_,val=a.items_and_sources();areplay=a.base.evaluate(am,val,torch.device('cpu'))
    adiff=0.
    for x,y in zip(areplay['rows'],astored['rows']):
        diff=float(np.abs(np.asarray(x['predicted_points_roi'])-y['predicted_points_roi']).max());adiff=max(adiff,diff)
        check(x['id']==y['id'] and diff<2e-4 and x['evidence_accepted']==y['evidence_accepted'],x['id']+'_A_replayed_checkpoint_output')
    summaries['A']=dict(checkpoint_sha256=sha(arun/'best_weights.pt'),best_step=areceipt['best_step'],parameters=1202,replayed_prediction_max_difference_roi=adiff,summary=astored['summary'])
    breceipt=read(brun/'receipt.json');bcfg=read(brun/'config.json');bhist=read(brun/'history.json');bstored=read(brun/'validation_evaluation.json')
    check(breceipt['completed_steps']==2400 and len(bhist)==12,'B_2400_steps12_evaluations')
    check(min(bhist,key=lambda r:r['validation']['selection_loss'])['step']==breceipt['best_step'],'B_min_G_focal_selection')
    check(breceipt['checkpoint_sha256']==sha(brun/'best_weights.pt') and bcfg['source_code_sha256']==sha(TASK/'polar_angle/train_polar.py'),'B_source_checkpoint_identity')
    for name,h in bcfg['source_cache_and_hub_outputs_sha256'].items():check(sha(b.PREV/name)==h,'B_exact_feature_cache_and_hub_prediction_'+name)
    bm=b.PolarNeedle();bck=torch.load(brun/'best_weights.pt',weights_only=True);bm.load_state_dict(bck['state_dict']);breplay=b.evaluate(bm,b.dataset('validation'))
    bdiff=0.;angles=[];accepted=[];negative=0
    for x,y in zip(breplay['rows'],bstored['rows']):
        diff=b.delta(x['angle_deg_image'],y['angle_deg_image']);bdiff=max(bdiff,diff)
        check(x['id']==y['id'] and diff<2e-4 and x['valid']==y['valid'],x['id']+'_B_replayed_checkpoint_output')
        if x['reference_angle_deg']is not None:
            err=b.delta(x['angle_deg_image'],x['reference_angle_deg']);angles.append(err)
            if x['valid']:accepted.append(err)
        if not x['target_present'] and x['valid']:negative+=1
    check(len(angles)==50 and len(accepted)==bstored['summary']['accepted'],'B_full50_coverage_denominator')
    check(abs(np.mean(angles)-bstored['summary']['angle_error_deg']['mean'])<2e-4 and sum(e<=10 for e in angles)==bstored['summary']['within10'],'B_angle_statistics_recomputed')
    check(sum(e>10 for e in accepted)==bstored['summary']['accepted_over10'] and negative==bstored['summary']['negative_accepted'],'B_wrong_acceptance_counts_recomputed')
    summaries['B']=dict(checkpoint_sha256=sha(brun/'best_weights.pt'),best_step=breceipt['best_step'],needle_parameters=1009,frozen_hub_parameters=1202,total_runtime_parameter_count=2211,
        replayed_prediction_max_difference_deg=bdiff,summary=bstored['summary'],endpoint='Direction reference .70R; no true terminal localization claim')
    report=dict(status='PASS_COMPLETED_CANDIDATE_RESULTS_REPRODUCED_PC_ONLY',checks=len(checks),failures=[],candidates=summaries,
        selector='G development focal losses within each fixed candidate, no G bar chooses angles and no H access',
        scope='Candidate B is promising float needle evidence, not accepted deployed MCU reading system',
        implementation_gaps=['New polar bilinear sampling, quantization, integer kernels and MCU memory/timing not yet validated',
            'Common PC static-print SIFT pose uses native720p crop→256; existing MCU only receives128x128U8ROI, so current pose cannot be assumed directly deployable',
            'Keep physical angle and pressure/reference calibration separate; no board0..0.51TEST expansion'],
        optimizer_steps_by_reviewer=0,H_or_ABC_opened=False,hardware_actions=False)
    (HERE/'candidate_results_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps(dict(status=report['status'],checks=len(checks),A=astored['summary']['angle_error_deg'],B=bstored['summary']),ensure_ascii=False))
if __name__=='__main__':main()
