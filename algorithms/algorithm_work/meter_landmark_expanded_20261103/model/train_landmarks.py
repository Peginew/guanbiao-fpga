"""One bounded six-landmark candidate; partial visibility is not a zero point."""
from pathlib import Path
import argparse,hashlib,json,math,platform,sys,time
sys.dont_write_bytecode=True
import cv2
import numpy as np
import torch
from landmark_model import LandmarkNet,POINTS,targets,focal,decode,account

HERE=Path(__file__).resolve().parent;TASK=HERE.parent;ROOT=TASK.parents[1]
DATA=TASK/'data';FROZEN_DATA=ROOT/'algorithm_work/meter_cnn_training_20261102'
def cache_path(split):return DATA/'roi_cache_train.npz' if split=='train' else FROZEN_DATA/'roi_cache_validation.npz'
PLAN=dict(candidate='C4_SIX_IDENTIFIED_PRINT_HEATMAPS_EXPANDED_AB_DEF',seed=1109,steps=8000,batch_size=12,
    optimizer='Adam',learning_rate=.003,minimum_learning_rate=.00015,evaluation_interval=400,
    threads=4,initialization='Random scratch Kaimingfan_in, fuse+.05, headstd.01 bias-4.59511985',
    input='Whole128U8ROI normalized(pixel-128)/128; no predicted orGT pose/needle/psi/masks as input',
    heads=list(POINTS),output='6x64heatmaps, ROIpoint=heatpoint*2',
    visibility='visible/reliablepartial coords supervise peak; explicitlyoccluded/absent supervise no-visiblepeak; unknown ignored',
    visible_without_coordinate='Ignore heatloss, never make positivevisible point a zero-map negative',
    augmentation=dict(rotation_deg=[-15,15],scale=[.92,1.08],translation_ROIpx=[-4,4],
        gain=[.8,1.2],bias=[-12,12],noise_probability=.25,noise_sigma=[0,2],
        synthetic_occlusion=False,out_of_bounds_supervision='drop thathead mask, neverzero-mapnegative'),
    heat_sigma='max(1.25heatpixels, declared_uncertainty_ROI*scale/2)',
    fixed_point_evidence=dict(peak_min=.3,margin_min=.02,far_exclusion_heat_radius=5),
    selection='G equal-identity unconditional pointMAE/3 + known-visible FNR +2*known-invisible FPR; noPSI selection',
    point_MAE_confidence_filtered=False,step0='Random newlandmarkbranch; trained oldhub/polar remain frozen in system control',
    train_groups=['A','B','D','E','F'],train_images_predeclared=295,
    same_architecture_and_scratch_seed_as_first_candidate=True,
    old_hub_polar_integer_parameters_and_runtime_frozen=True,
    one_candidate_no_G_parameter_search=True,C_H_opened=False,hardware_actions=False)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rows(p):return[json.loads(x)for x in Path(p).read_text('utf-8-sig').splitlines()if x.strip()]
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')

def items(labels,split):
    rr=rows(labels);groups={'A','B','D','E','F'}if split=='train'else{'G'}
    assert all(r['id'].split('_')[0]in groups and r['split']in({split}if split=='train'else{'validation','development'})for r in rr)
    cache=np.load(cache_path(split));ims=dict(zip(cache['ids'].tolist(),cache['images']))
    out=[]
    for r in rr:
        ps=[];sig=[];mask=[];vknown=[];vtarget=[]
        for name in POINTS:
            p=r['points'][name];coord=bool(p['coordinate_mask']);vk=bool(p['visibility_mask'])
            vt=p.get('vis_target',p.get('visibility_target'))
            if vt is None and vk:
                assert p['visibility'] in {'visible','partial','partially_visible','occluded','absent'}
                vt=1 if p['visibility']in{'visible','partial','partially_visible'}else 0
            assert vt in {None,0,1}
            if vk and vt==0:assert p['visibility']in{'occluded','absent'}
            if coord:
                assert p['xy_roi']is not None and p['visibility']in{'visible','partial','partially_visible'}
                xy=np.asarray(p['xy_roi'],np.float64);assert np.isfinite(xy).all()and(xy>=0).all()and(xy<=127).all()
                ps.append(xy.tolist());mask.append(1.)
            else:
                ps.append(None);mask.append(float(vk and vt==0))
            sig.append(max(1.25,float(p.get('uncertainty_px')or 0)/2))
            vknown.append(vk);vtarget.append(vt)
        if not r['target_present']:
            assert all(p is None for p in ps)and all(vk and vt==0 for vk,vt in zip(vknown,vtarget))
        im=ims[r['id']];assert im.dtype==np.uint8 and im.shape==(128,128)
        out.append(dict(id=r['id'],record=r,image=im,points=ps,sigmas=sig,mask=np.asarray(mask,np.float32),
            visibility_known=vknown,visibility_target=vtarget,target_present=r['target_present']))
    assert len(out)==(295 if split=='train' else 59)
    return out

def augmented(it,rng):
    degree=float(rng.uniform(-15,15));scale=float(rng.uniform(.92,1.08))
    M=cv2.getRotationMatrix2D((63.5,63.5),degree,scale);M[:,2]+=rng.uniform(-4,4,2)
    image=cv2.warpAffine(it['image'],M,(128,128),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101).astype(np.float32)
    image=(image-128)*rng.uniform(.8,1.2)+128+rng.uniform(-12,12)
    if rng.random()<.25:image+=rng.normal(0,rng.uniform(0,2),image.shape)
    image=np.clip(np.rint(image),0,255).astype(np.uint8)
    points=[];mask=it['mask'].copy()
    for k,p in enumerate(it['points']):
        q=(np.r_[p,1]@M.T).tolist()if p is not None else None
        if q is not None and not(0<=q[0]<=127 and 0<=q[1]<=127):q=None;mask[k]=0
        points.append(q)
    heat=targets(points,np.maximum(1.25,np.asarray(it['sigmas'])*scale),mask)
    return(image.astype(np.float32)-128)[None]/128,heat,mask

def evaluate(model,data,logit_override=None):
    rows_out=[];lossnum=0.;lossden=0
    model.eval()
    with torch.inference_mode():
        for start in range(0,len(data),32):
            batch=data[start:start+32]
            x=np.stack([(it['image'].astype(np.float32)-128)[None]/128 for it in batch])
            logits=model(torch.from_numpy(x))if logit_override is None else torch.from_numpy(np.stack([logit_override[it['id']]for it in batch]))
            heat=np.stack([targets(it['points'],it['sigmas'],it['mask'])for it in batch]);mask=np.stack([it['mask']for it in batch])
            pos=max(1,int((heat==1).sum()));lossnum+=float(focal(logits,torch.from_numpy(heat),torch.from_numpy(mask)))*pos;lossden+=pos
            for it,v in zip(batch,logits.numpy()):
                decoded=decode(v);points={}
                for i,(name,p)in enumerate(zip(POINTS,decoded)):
                    # References are attached for evaluation only, never decode.
                    if it['points'][i]is not None:p['coordinate_error_ROI']=float(np.linalg.norm(np.asarray(p['roi_xy'])-it['points'][i]))
                    p['reference_coordinate_available']=it['points'][i]is not None
                    p['reference_visibility_known']=bool(it['visibility_known'][i]);p['reference_visibility_target']=it['visibility_target'][i]
                    points[name]=p
                rows_out.append(dict(id=it['id'],split=it['record']['split'],source_sha256=it['record']['source_sha256'],
                    target_present=it['target_present'],points=points,
                    query_GT_points_visibility_pose_or_pressure_used=False))
    return summarize(rows_out,lossnum/max(lossden,1)),rows_out

def summarize(predictions,loss=None):
    byhead={};maes=[];tp=fn=fp=tn=0
    for name in POINTS:
        ps=[r['points'][name]for r in predictions];err=[p['coordinate_error_ROI']for p in ps if'coordinate_error_ROI'in p]
        a=sum(p['reference_visibility_known']and p['reference_visibility_target']==1 and p['accepted']for p in ps)
        b=sum(p['reference_visibility_known']and p['reference_visibility_target']==1 and not p['accepted']for p in ps)
        c=sum(p['reference_visibility_known']and p['reference_visibility_target']==0 and p['accepted']for p in ps)
        d=sum(p['reference_visibility_known']and p['reference_visibility_target']==0 and not p['accepted']for p in ps)
        byhead[name]=dict(coordinate_count=len(err),mean_ROI_error=float(np.mean(err))if err else None,
            median_ROI_error=float(np.median(err))if err else None,within3=sum(x<=3 for x in err),
            accepted_within3=sum(p['accepted']and p.get('coordinate_error_ROI',math.inf)<=3 for p in ps),
            true_visible_accepted=a,true_visible_rejected=b,invisible_accepted=c,invisible_rejected=d)
        if err:maes.append(float(np.mean(err)))
        tp+=a;fn+=b;fp+=c;tn+=d
    mae=float(np.mean(maes))if maes else math.inf;fnr=fn/max(tp+fn,1);fpr=fp/max(fp+tn,1)
    return dict(images=len(predictions),point_mean_equal_identity_ROI=mae,
        visible_false_reject_rate=fnr,known_invisible_false_accept_rate=fpr,
        selection_score=mae/3+fnr+2*fpr,masked_focal=loss,by_identity=byhead,
        pressure_error_evaluated=False,visibility_is_evidence_not_calibrated_probability=True)

def preflight():
    torch.set_num_threads(4);torch.manual_seed(1109)
    model=LandmarkNet();cost=account(model);assert cost['parameters']==1222 and cost['nominal_MAC']==1412096
    x=torch.randn(2,1,128,128);y=torch.zeros(2,6,64,64);y[:,0,20,25]=1;m=torch.zeros(2,6);m[:,0]=1
    v=focal(model(x),y,m);v.backward();g=model.head.weight.grad
    assert g[0].abs().sum()>0 and g[1:].abs().sum()==0
    model.zero_grad();z=focal(model(x),torch.zeros_like(y),torch.ones_like(m));z.backward()
    assert model.head.bias.grad.abs().sum()>0
    zero=focal(model(x),y,torch.zeros_like(m));assert float(zero.detach())==0
    report=dict(status='SYNTHETIC_MODEL_MASK_AND_COST_PREFLIGHT',plan=PLAN,cost=cost,
        unknown_head_gradient_zero=True,known_invisible_negative_gradient_nonzero=True,
        all_unknown_loss_zero=True,data_or_G_opened=False,model_code_sha256=sha(HERE/'landmark_model.py'),trainer_sha256=sha(__file__))
    write(HERE/'preflight.json',report);write(HERE/'plan_before_training.json',PLAN)
    print(json.dumps(dict(status=report['status'],cost=cost),indent=2))

def train(args):
    args.out.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(4);cv2.setNumThreads(1);torch.manual_seed(PLAN['seed']);np.random.seed(PLAN['seed']);torch.use_deterministic_algorithms(True)
    tr=items(args.train_labels,'train');va=items(args.validation_labels,'validation');active=[it for it in tr if it['mask'].any()]
    assert not({it['record']['source_sha256']for it in tr}&{it['record']['source_sha256']for it in va})
    model=LandmarkNet();config=dict(PLAN,train_images=len(tr),train_active_images=len(active),validation_images=len(va),
        source_sha256=dict(train_labels=sha(args.train_labels),validation_labels=sha(args.validation_labels),
            train_cache=sha(cache_path('train')),validation_cache=sha(cache_path('validation')),
            model_code=sha(HERE/'landmark_model.py'),trainer=sha(__file__),
            old_frozen_hub=sha(FROZEN_DATA/'run_002/best_weights.pt')),
        actual_device='CPU',torch_version=str(torch.__version__),cost=account(model))
    write(args.out/'config.json',config)
    initial_summary,initial_rows=evaluate(model,va);torch.save(dict(state_dict=model.state_dict(),step=0,config=config),args.out/'random_initial_weights.pt')
    write(args.out/'random_validation_evaluation.json',dict(summary=initial_summary,rows=initial_rows))
    (args.out/'random_validation_predictions.jsonl').write_text(''.join(json.dumps(r)+'\n'for r in initial_rows),'utf-8')
    best=initial_summary['selection_score'];torch.save(dict(state_dict=model.state_dict(),step=0,config=config),args.out/'best_weights.pt')
    optimizer=torch.optim.Adam(model.parameters(),lr=.003);schedule=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,8000,eta_min=.00015)
    rng=np.random.default_rng(PLAN['seed']);history=[];started=time.monotonic()
    for step in range(1,8001):
        model.train();batch=[active[int(rng.integers(len(active)))]for _ in range(12)];aug=[augmented(it,rng)for it in batch]
        xx=torch.from_numpy(np.stack([a[0]for a in aug]));yy=torch.from_numpy(np.stack([a[1]for a in aug]));mm=torch.from_numpy(np.stack([a[2]for a in aug]))
        optimizer.zero_grad(set_to_none=True);loss=focal(model(xx),yy,mm)
        if not torch.isfinite(loss):raise RuntimeError('nonfinite training loss')
        loss.backward();optimizer.step();schedule.step()
        if step%400==0:
            sm,rr=evaluate(model,va);record=dict(step=step,loss=float(loss.detach()),validation=sm,elapsed_s=time.monotonic()-started)
            history.append(record);write(args.out/'history.json',history)
            write(args.out/f'validation_step_{step:04d}.json',dict(summary=sm,rows=rr))
            if sm['selection_score']<best:
                best=sm['selection_score'];torch.save(dict(state_dict=model.state_dict(),step=step,config=config),args.out/'best_weights.pt')
            print(json.dumps(record),flush=True)
    torch.save(dict(state_dict=model.state_dict(),step=8000,config=config),args.out/'last_weights.pt')
    ck=torch.load(args.out/'best_weights.pt',weights_only=True);model.load_state_dict(ck['state_dict'])
    for split,data in [('train',tr),('validation',va)]:
        sm,rr=evaluate(model,data);write(args.out/f'{split}_evaluation.json',dict(summary=sm,rows=rr))
        (args.out/f'{split}_predictions.jsonl').write_text(''.join(json.dumps(r)+'\n'for r in rr),'utf-8')
    write(args.out/'training_receipt.json',dict(status='ONE_BOUNDED_FLOAT_CANDIDATE_COMPLETED_NOT_READOUT_OR_MCU_ACCEPTANCE',
        steps=8000,best_step=ck['step'],elapsed_s=time.monotonic()-started,
        best_checkpoint_sha256=sha(args.out/'best_weights.pt'),config_sha256=sha(args.out/'config.json'),
        final_validation=load_json(args.out/'validation_evaluation.json')['summary'],C_H_opened=False,hardware_actions=False))

def load_json(p):return json.loads(Path(p).read_text('utf-8-sig'))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['preflight','train']);p.add_argument('--train-labels',type=Path)
    p.add_argument('--validation-labels',type=Path);p.add_argument('--out',type=Path,default=HERE/'run_001');a=p.parse_args()
    if a.command=='preflight':preflight()
    else:train(a)
