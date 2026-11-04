"""Replay selected robust-chain weights and a bounded provenance sample."""
from pathlib import Path
import hashlib,importlib.util,json
import numpy as np
import torch
HERE=Path(__file__).resolve().parent;TASK=HERE.parent;TRAIN=TASK/'training';RUN=TRAIN/'run_001'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def rows(p):return[json.loads(x)for x in Path(p).read_text('utf-8-sig').splitlines()if x.strip()]
def main():
    s=importlib.util.spec_from_file_location('review_robust_result',TRAIN/'train_robust_chain.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);torch.set_num_threads(4)
    checks=[]
    def check(ok,name):
        checks.append(dict(name=name,passed=bool(ok)))
        if not ok:raise AssertionError(name)
    cfg=read(RUN/'config.json');tr,va=m.load_items();byid={it['id']:it for it in tr+va}
    check(cfg['trainer_sha256']==sha(TRAIN/'train_robust_chain.py')==read(HERE/'robust_chain_admission.json')['source_sha256'],'exact_signed_training_source')
    hrec=read(RUN/'hub/receipt.json');prec=read(RUN/'polar/receipt.json')
    check(hrec['completed_steps']==prec['completed_steps']==2400,'one2400_step_per_stage')
    check(hrec['checkpoint_sha256']==sha(RUN/'hub/best_weights.pt')==prec['hub_checkpoint_sha256'],'same_selected_hub_feeds_polar')
    check(prec['polar_checkpoint_sha256']==sha(RUN/'polar/best_weights.pt'),'selected_polar_identity')
    hhist=read(RUN/'hub/history.json');phist=read(RUN/'polar/history.json')
    hs=[dict(step=0,value=read(RUN/'hub/warm_validation.json')['summary']['hub_error_roi']['mean'])]+[dict(step=r['step'],value=r['validation']['hub_error_roi']['mean'])for r in hhist]
    ps=[dict(step=0,value=read(RUN/'polar/warm_with_new_hub_validation.json')['summary']['selection_loss'])]+[dict(step=r['step'],value=r['validation']['selection_loss'])for r in phist]
    check(min(hs,key=lambda r:r['value'])['step']==hrec['best_step'],'hub_best_G_mean_including_warm0')
    check(min(ps,key=lambda r:r['value'])['step']==prec['best_step'],'polar_best_G_focal_including_warm0')
    hub=m.base.Direct(4);hub.load_state_dict(torch.load(RUN/'hub/best_weights.pt',weights_only=True)['state_dict']);hub.eval()
    polar=m.polar.PolarNeedle();polar.load_state_dict(torch.load(RUN/'polar/best_weights.pt',weights_only=True)['state_dict']);polar.eval()
    hreplay=m.hub_evaluate(hub,va);hstored=read(RUN/'hub/validation_evaluation.json');hdiff=0.
    for a,b in zip(hreplay['rows'],hstored['rows']):
        diff=float(np.max(np.abs(np.asarray(a['hub_roi'])-b['hub_roi'])));hdiff=max(hdiff,diff)
        check(a['id']==b['id'] and diff<2e-4 and a['hub_evidence_permitted']==b['hub_evidence_permitted'],a['id']+'_actual_selected_hub_replay')
    provenance=rows(RUN/'polar/train_feature_provenance.jsonl');cache=np.load(RUN/'polar/train_features.npz');index={str(v):i for i,v in enumerate(cache['ids'])}
    check(len(provenance)==820 and sum(r['supervised']for r in provenance)==745,'820_same_source_views745_supervised')
    for ident in('D_001_aug1','D_049_aug4','F_003_aug1'):
        r=next(v for v in provenance if v['id']==ident);it=byid[r['source_id']]
        im,_,mask,pts,meta=m.augmented_view(np.random.default_rng(r['seed']),it)
        check(hashlib.sha256(im.tobytes()).hexdigest()==r['image_sha256'] and r['source_sha256']==it['record']['sha256'],ident+'_augmentation_reproduced_from_source_seed')
        with torch.inference_mode():out=hub(torch.from_numpy(m.base.normalized(im)[None]))[0].numpy()
        center=m.base.decode(out)[0][0]
        check(np.max(np.abs(center-r['same_observation_hub']))<2e-4,ident+'_not_old_or_unaugmented_hub')
        feature,_=m.polar.polar_features(im,r['same_observation_hub'],it['record']['roi_request']['radius'])
        check(np.array_equal(feature,cache['features'][index[ident]]) and hashlib.sha256(feature.tobytes()).hexdigest()==r['feature_sha256'],ident+'_feature_from_exact_same_frame')
    # G remains unaugmented; make the observed hub/features again and reload the
    # selected polar weights. This does not reopen or resample any held-out H.
    val=m.make_polar_items(hub,va,0,'review',None);replay=m.polar.evaluate(polar,val);stored=read(RUN/'polar/validation_evaluation.json');angle_diff=0.
    for a,b in zip(replay['rows'],stored['rows']):
        diff=m.polar.delta(a['angle_deg_image'],b['angle_deg_image']);angle_diff=max(angle_diff,diff)
        check(a['id']==b['id'] and diff<2e-3 and a['valid']==b['valid'],a['id']+'_new_hub_polar_G_replay')
    for k in('within5','within10','full','accepted','accepted_over10','negative_count','negative_accepted'):check(replay['summary'][k]==stored['summary'][k],'G_neural_statistic_'+k)
    old=read(m.POINTER/'polar_angle/run_001/validation_evaluation.json')['summary']
    report=dict(status='PASS_ROBUST_CHAIN_EXECUTION_AND_REPRODUCED_G_RESULTS_NO_READOUT_ACCEPTANCE',checks=len(checks),failures=[],
        hub_checkpoint_sha256=sha(RUN/'hub/best_weights.pt'),polar_checkpoint_sha256=sha(RUN/'polar/best_weights.pt'),trainer_sha256=sha(TRAIN/'train_robust_chain.py'),
        hub_best_step=hrec['best_step'],polar_best_step=prec['best_step'],completed_steps_per_stage=2400,
        hub_replayed_max_difference_roi=hdiff,polar_replayed_max_angle_difference_deg=angle_diff,
        hub_G=hstored['summary']['hub_error_roi'],new_polar_G=stored['summary'],old_polar_G=old,
        assessment='Hub overall mean improved, but new polar mean/median direction errors slightly worse than old B and <=10deg unchanged48/50. Increased neural permission42vs40 alone is not robustness success; requires same PSI output/new-wrong-ID comparison.',
        optimizer_steps_by_reviewer=0,H_or_ABC_opened=False,OSD_or_hardware_changed=False)
    (HERE/'robust_chain_results_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps(dict(status=report['status'],checks=len(checks),hub=report['hub_G'],new_polar=stored['summary']),ensure_ascii=False))
if __name__=='__main__':main()
