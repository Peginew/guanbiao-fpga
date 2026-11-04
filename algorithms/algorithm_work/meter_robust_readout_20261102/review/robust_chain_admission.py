"""Necessary independent checks for one robust hub/polar training chain."""
from pathlib import Path
import hashlib,importlib.util,json,sys
import cv2
import numpy as np
import torch
HERE=Path(__file__).resolve().parent;TASK=HERE.parent;CODE=TASK/'training/train_robust_chain.py'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    spec=importlib.util.spec_from_file_location('review_robust_chain',CODE);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.base.setup(m.PLAN['seed'],2);tr,va=m.load_items();checks=[]
    def check(ok,name):
        checks.append(dict(name=name,passed=bool(ok)))
        if not ok:raise AssertionError(name)
    check(len(tr)==164 and len(va)==59 and sum(bool(it['mask'][0])for it in tr)==158,'164_train59_G158_hub_supervised')
    check(all(it['record']['source_group']in'DEF'for it in tr) and all(it['record']['source_group']=='G'for it in va),'strict_source_groups')
    selected=[next(it for it in tr if it['id']==ident)for ident in('D_001','D_004','D_049','E_024','F_003','F_004')]
    augmented=0
    for it in selected:
        for seed in range(1104,1114):
            image,heat,mask,points,meta=m.augmented_view(np.random.default_rng(seed),it)
            check(np.array_equal(mask,it['mask']),it['id']+f'_{seed}_source_mask_preserved')
            matrix=np.array(meta['affine_matrix']);geometric=cv2.warpAffine(it['image'],matrix,(128,128),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
            check(m.point_evidence_preserved(geometric,image,points,mask),it['id']+f'_{seed}_bounded_photo_preserves_declared_evidence')
            for h,point in enumerate(points):
                if point is not None:
                    expected=np.r_[it['points'][h],1]@matrix.T
                    check(np.max(np.abs(expected-point))<1e-9,it['id']+f'_{seed}_{h}_same_affine_point')
                if not mask[h]:check(not heat[h].any(),it['id']+f'_{seed}_{h}_unknown_not_fabricated')
            augmented+=1
    # Force photometric attempts to fail to verify the fallback keeps exactly
    # the already selected geometric frame/points, not raw untransformed pixels.
    saved_prob=m.PLAN['photo_probability'];saved_check=m.point_evidence_preserved;calls=[0]
    def fail_photo(*args):calls[0]+=1;return calls[0]>m.PLAN['photo_attempts']
    m.PLAN['photo_probability']=1.;m.point_evidence_preserved=fail_photo
    image,_,_,_,meta=m.augmented_view(np.random.default_rng(2204),selected[0])
    m.PLAN['photo_probability']=saved_prob;m.point_evidence_preserved=saved_check
    expected=cv2.warpAffine(selected[0]['image'],np.array(meta['affine_matrix']),(128,128),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
    check(np.array_equal(image,expected) and meta['photometric_failed_attempts']==4 and not meta['photometric_accepted'],'failed_photo_falls_back_same_geometric_observation')
    hub=m.base.Direct(4);hub.load_state_dict(torch.load(m.HUB_WARM,weights_only=True)['state_dict']);hub.eval()
    views=m.make_polar_items(hub,selected,1,'review',None)
    for view in views:
        with torch.inference_mode():logits=hub(torch.from_numpy(m.base.normalized(view['image'])[None]))[0].numpy()
        points,_,_=m.base.decode(logits)
        check(np.max(np.abs(points[0]-view['center']))<2e-4,view['id']+'_actual_hub_from_same_augmented_pixels')
        feature,_=m.polar.polar_features(view['image'],view['center'],view['record']['roi_request']['radius'])
        check(np.array_equal(feature,view['feature']),view['id']+'_polar_from_same_view_and_predicted_center')
        if view['record']['target_present'] and not view['record']['loss_mask'][1]:check(not view['supervised'],view['id']+'_unknown_thin_not_zero_negative')
    check(m.PLAN['parameters']=={'hub':1202,'polar':1009},'inference_architectures_unchanged')
    check(m.PLAN['hub_steps']==m.PLAN['polar_steps']==2400,'one_frozen2400_step_per_stage')
    check(m.PLAN['output_thresholds_unchanged']==dict(needle_score=.3,needle_margin=.02,hub_score=.3,hub_margin=.02,hub_center_distance_roi=20,outside_fraction=.05),'all_old_output_thresholds_unchanged')
    z=torch.zeros(2,2,64,64,requires_grad=True);target=torch.zeros_like(z);target[0,0,32,32]=1
    m.base.masked_loss(z,target,torch.tensor([[1.,0.],[1.,0.]])).backward()
    check(not z.grad[:,1].count_nonzero() and z.grad[1,0].count_nonzero()>0,'hub_only_stage_no_tip_supervision_true_negative_retained')
    report=dict(status='PASS_SINGLE_ROBUST_CHAIN_TRAINING_ADMISSION',checks=len(checks),failures=[],source_sha256=sha(CODE),PLAN=m.PLAN,
        actual_bounded_augmentation_views=augmented,same_observation_predictions_checked=len(views),
        visual_review='27 displayed train views: bounded gamma/shadows/soft highlight/light blur, source-unknownF003 tip remains ignored; no synthetic opaque patch',
        declared_limits=['Patch contrast checks are evidence-preservation heuristics, not certified visibility annotation',
                         'Locator radius held fixed under small affine scale perturbation: simulates bounded scale mismatch; not an exactly transformed detector radius',
                         'G is repeated development selection, no new independent test or all-environment claim',
                         'Final quality permission and display eligibility remain separate; actual new accepted errors must be reported'],
        optimizer_steps=0,test_H_or_ABC_opened=False,hardware_actions=False,
        next_action='One fixed hub warm-training run then one fixed polar warm-training run; allow step0 baseline to remain selected if training degrades')
    (HERE/'robust_chain_admission.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps(dict(status=report['status'],checks=len(checks),source_sha256=report['source_sha256']),ensure_ascii=False))
if __name__=='__main__':main()
