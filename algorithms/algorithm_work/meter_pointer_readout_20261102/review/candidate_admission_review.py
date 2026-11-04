"""Small independent admissions for the two frozen readout candidates."""
from pathlib import Path
import argparse, hashlib, importlib.util, json, math, sys
import cv2
import numpy as np
import torch

HERE=Path(__file__).resolve().parent;TASK=HERE.parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def module(name,path):
    sys.path.insert(0,str(path.parent))
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def main():
    parser=argparse.ArgumentParser();parser.add_argument('route',choices=['A','B']);args=parser.parse_args();checks=[]
    def check(ok,name):
        checks.append(dict(name=name,passed=bool(ok)))
        if not ok:raise AssertionError(name)
    if args.route=='A':
        code=TASK/'keypoint_aux/train_aux.py';m=module('admit_aux',code);m.base.setup(1102,2)
        train,val=m.items_and_sources();qualified=[it for it in train if m.eligible(it)[0]]
        check(len(train)==164 and len(val)==59 and len(qualified)==47,'164_59_47_source_and_qualification_counts')
        for i,it in enumerate(train):
            allow=m.eligible(it)[0]
            if allow:
                check(it['record']['source_group'] in 'DEF' and it['record']['scene']['primary'] in ('front_medium_soft_light','front_large_soft_light') and bool(np.all(it['mask'])),it['id']+'_bounded_clear_train_only_aux')
            aug=m.augment(np.random.default_rng(2102+i),it);_,heat,mask,line,lmask,nmask,pts=aug
            check(allow or not lmask.any(),it['id']+'_noneligible_aux_ignored')
            check(bool(mask[1]) or not nmask.any(),it['id']+'_unknown_tip_no_hard_negative')
            check(not nmask.any() or bool((heat[1][nmask]<.05).all()),it['id']+'_no_target_tail_hard_negative')
            if pts[1] is not None and mask[1] and it['target_present']:
                p=np.array(pts[1])/2;unc=it['record']['keypoints']['thin_terminal']['uncertainty_px']/(2*it['stride'])
                radius=max(3.,3*it['sigmas'][1],unc+1)
                protected=(m.base.X-p[0])**2+(m.base.Y-p[1])**2<=radius**2
                check(not (nmask&protected).any(),it['id']+'_hard_negative_excludes_uncertainty_neighbourhood')
        model=m.Auxiliary();model.base.load_state_dict(torch.load(m.WARM,weights_only=True)['state_dict'])
        x=torch.from_numpy(np.stack([m.base.normalized(it['image']) for it in train[::20]]))
        with torch.inference_mode():check(torch.equal(model(x)[0],model.base(x)),'auxiliary_does_not_change_inference_forward')
        check(sum(p.numel() for p in model.base.parameters())==1202 and sum(p.numel() for p in model.line_head.parameters())==5,'1202_main_plus5_training_aux_only')
        z=torch.zeros(2,2,64,64,requires_grad=True);line=torch.zeros(2,1,64,64,requires_grad=True)
        target=torch.zeros_like(z);target[0,0,32,32]=1
        head=torch.tensor([[1.,0.],[1.,1.]])
        ltarget=torch.zeros(2,64,64);lm=torch.zeros_like(ltarget);nm=torch.zeros(2,64,64,dtype=torch.bool);nm[1]=True
        loss,*_=m.losses(z,line,target,head,ltarget,lm,nm);loss.backward()
        check(z.grad[0,1].count_nonzero()==0 and line.grad.count_nonzero()==0,'ignored_heads_and_noneligible_aux_have_zero_gradient')
        check(z.grad[1].count_nonzero()>0,'true_negative_keeps_training_gradient')
        report=dict(status='PASS_CANDIDATE_A_TRAINING_ADMISSION',checks=len(checks),failures=[],source_sha256=sha(code),plan=m.PLAN,
            warm_checkpoint_sha256=sha(m.WARM),prepared_train_sha256=sha(m.SOURCE/'prepared_train.jsonl'),prepared_validation_sha256=sha(m.SOURCE/'prepared_validation.jsonl'),
            supervision='47 bounded visible clear-front training images only; weak direction tubes not true segmentation; noneligible mask0',
            visual_review='aux_labels_01.png first16 qualified examples: line support follows thin end, no obvious body occlusion',
            optimizer_steps_by_reviewer=0,integer_or_MCU_deployment_accepted=False,test_H_or_ABC_opened=False,
            decision='One predeclared2400step candidate may run; inference aux removal and final G/bar results must still be reviewed')
        name='candidate_A_admission.json'
    else:
        code=TASK/'polar_angle/train_polar.py';m=module('admit_polar',code);torch.set_num_threads(2)
        train=m.dataset('train');val=m.dataset('validation');active=[it for it in train if it['supervised']]
        check(len(train)==164 and len(val)==59 and len(active)==149,'149_angle_or_true_negative_supervision')
        check(sum(not it['record']['target_present'] for it in active)==9,'nine_true_negatives_only')
        for it in train+val:
            r=it['record'];check(r['source_group'] in ('DEF' if r['split']=='train' else 'G'),r['id']+'_split')
            check(it['center']==it['frozen_hub']['predicted_points_roi'][0],r['id']+'_predicted_hub_only')
            check(it['feature'].shape==(16,360) and np.isfinite(it['feature']).all(),r['id']+'_feature_shape_finite')
            if r['target_present'] and not r['loss_mask'][1]:check(not it['supervised'] and not it['label'].any(),r['id']+'_unknown_tip_ignored_not_negative')
        gray=np.full((128,128),128,np.uint8);feature,outside=m.polar_features(gray,[63.5,63.5],60)
        check(not feature.any() and outside==0,'constant_gray_produces_zero_centered_features')
        for theta in (0,45,90,180,270,359):
            im=np.full((128,128),200,np.uint8);c=np.array([63.5,63.5]);rad=np.radians(theta);d=np.array([np.cos(rad),np.sin(rad)])
            cv2.line(im,tuple(np.rint(c+10*d).astype(int)),tuple(np.rint(c+55*d).astype(int)),0,1)
            x,_=m.polar_features(im,c,60);dark=int(x[:8].mean(0).argmin())
            check(m.delta(dark,theta)<=3,'polar_sampling_gray_angle_'+str(theta))
        for theta in (0,1,180,358,359):
            t=m.target(theta,2.5)
            for shift in (-8,8):check(int(np.roll(t,shift).argmax())==(theta+shift)%360,f'circular_feature_label_shift_{theta}_{shift}')
        model=m.PolarNeedle();check(sum(p.numel() for p in model.parameters())==1009,'1009_parameters')
        x=torch.randn(2,16,360)
        with torch.inference_mode():check(torch.allclose(model(torch.roll(x,37,2)),torch.roll(model(x),37,1),atol=1e-6),'circular_conv_angle_shift_equivariance')
        z=torch.zeros(2,360,requires_grad=True);target=torch.zeros_like(z);target[0,25]=1;m.focal(z,target).backward()
        check(z.grad[1].count_nonzero()>0,'true_negative_zero_angle_target_has_gradient')
        report=dict(status='PASS_CANDIDATE_B_TRAINING_ADMISSION',checks=len(checks),failures=[],source_sha256=sha(code),
            train_count=164,angular_supervised_or_negative=149,validation_count=59,parameters=1009,
            contract='All360angle evidence from actual frozen CNN hub, no geometric tip or pressure prerequisite. Unknown tip excluded, true negatives zero.',
            cost='1009 parameters,355680MAC reference; integer radial sampling and actual MCU execution pending',
            decision='One frozen2400step candidate may run; fixed score gates and actual bar evaluation still required',
            optimizer_steps_by_reviewer=0,test_H_or_ABC_opened=False,hardware_actions=False,
            endpoint_semantics='0.70R displayed endpoint is a direction reference, not actual detected tip')
        name='candidate_B_admission.json'
    (HERE/name).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
