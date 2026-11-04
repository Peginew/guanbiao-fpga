"""Necessary sign, source and geometry checks before the one bounded run."""
import math
import cv2
import numpy as np
import torch
import reference_candidate as c


def run():
    checks=[]
    for a in [-90.,-24.,-8.,0.,8.,24.,90.]:
        M=cv2.getRotationMatrix2D((63.5,63.5),a,1)
        hub=np.array([63.5,63.5]);point=np.array([63.5,20.])
        h=np.r_[hub,1]@M.T;p=np.r_[point,1]@M.T
        old=math.degrees(math.atan2(*(point-hub)[::-1]))
        new=math.degrees(math.atan2(*(p-h)[::-1]))
        error=abs((new-old+a+180)%360-180)
        assert error<1e-10
        checks.append(dict(test='opencv_rotation_sign',augmentation=a,image_angle_delta=new-old,error=error))
    train=c.material('train')
    silver={r['id']:r for r in c.rows(c.OLD/'readout_psi/train_print_pose.jsonl')}
    counts={g:dict(registered_silver=0,true_negative=0,ignored_positive=0) for g in ['D','E','F']}
    for it in train:
        r=it['record'];group=r['source_group'];p=silver[it['id']]
        assert p['source_sha256']==r['sha256'] and p['split']=='train'
        role='true_negative' if not r['target_present'] else 'registered_silver' if c.good_silver(p) else 'ignored_positive'
        counts[group][role]+=1
    model=c.StaticRoll();q=model(torch.zeros(2,1,128,128))
    assert tuple(q.shape)==(2,len(c.BINS)+1) and torch.isfinite(q).all()
    # Target/geometry coupling works without pressure and without real needle.
    it=dict(image=np.full((128,128),128,np.uint8),hub=np.array([63.5,63.5]),radius=48,silver_roll=7.)
    for a in [-12.,0.,12.]:
        x,y=c.transform(it,rotation=a)
        expected=7-a
        moment=float((y[:-1]*c.BINS).sum()/y[:-1].sum())
        assert abs(moment-expected)<.001
        assert np.max(abs(x))==0 and y[-1]==0
        checks.append(dict(test='silver_target_rotation',augmentation=a,expected=expected,actual=moment))
    # An uncertain/unmatched positive is absent from supervision, not a null.
    assert c.good_silver(dict(accepted=False)) is False
    y=c.label(None);assert y[-1]==1 and np.count_nonzero(y)==1
    report=dict(status='PASS_PRE_TRAINING_MATH_AND_INPUT_BINDINGS_ONLY',checks=checks,training_source_counts=counts,
        input_records=len(train),model_parameters=sum(p.numel() for p in model.parameters()),
        source_code_sha256=c.sha(c.HERE/'reference_candidate.py'),
        no_G_inference=True,no_H_opened=True,no_training=True,hardware_actions=False)
    c.write(c.HERE/'candidate_preflight.json',report)
    print(report['status'],report['training_source_counts'],report['model_parameters'])


if __name__=='__main__':run()
