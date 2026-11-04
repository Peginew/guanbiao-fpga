"""One bounded static-print roll CNN candidate. No import-time training.

Input:128 U8 ROI, unchanged frozen-model hub, locator radius. Native-frame
registration supplies TRAIN silver labels only; it is not query pose truth.
Unknown registration failures are ignored, never converted to negatives.
"""
from pathlib import Path
import argparse, hashlib, json, math, sys, time
import cv2
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT / 'algorithm_work/meter_cnn_training_20261102'
OLD = ROOT / 'algorithm_work/meter_pointer_readout_20261102'
PREVIOUS = ROOT / 'algorithm_work/meter_robust_readout_20261102/pose'
BINS = np.arange(-40, 41, 2, dtype=np.float32)
CONFIG = dict(
    candidate='STATIC_PRINT_ROLL_CNN_1', seed=1106, optimizer_steps=1600,
    train_weight_update_groups=['D','E'], internal_step_selection_group='F',
    final_development_group='G', H_opened=False, ABC_opened=False,
    labels='Train-only native static-print registration SILVER relative roll; NOT human pose ground truth',
    unknown_pose='IGNORE, not null class; PSI never provides pose/point labels',
    silver_filter=dict(accepted=True,min_inliers=12,min_unique=10,min_hull=.08,
                       max_reprojection_px=.8,max_anisotropy=1.15),
    input='128U8 ROI -> fixed9x9 local contrast -> annulus from frozen predicted hub/locator radius',
    annulus_radius_fraction=[.28,.95], local_contrast_gain=3,
    direction_bins_deg=BINS.tolist(), null_class='True no-gauge images only',
    target_sigma_deg=2.5, batch_size=16, learning_rate=.002,
    augmentation=dict(rotation_degrees=[-24,24],scale=[.97,1.03],translation_pixels=[-1.5,1.5],
                      contrast=[.8,1.2],brightness=[-10,10],
                      random_annular_sector_probability=.3,random_sector_width_degrees=[10,35]),
    selection='Minimum F silver-direction cross entropy with fixed deterministic +/-12deg views; no F pressure or G score',
    fixed_pose_permission=dict(non_null_probability_min=.8,conditional_stddev_deg_max=5.,
                               abs_roll_deg_max_exclusive=24.,hub_center_distance_max=20.,
                               roll_distribution_is_not_calibrated_probability=True),
    model_baseline='Frozen original1202 hub + original1009 needle; no hub changes, no polar rebuilding required',
    calibration='Train-only visual directions and user PSI, same original linear median-anchor procedure; coordinate change is explicit',
    experiment_budget='One1600-step run, no G-driven retraining or threshold changes',
    hardware_actions=False, deployment_status='PC candidate only; full integer/linked MCU fit pending')


def rows(path):
    return [json.loads(s) for s in Path(path).read_text('utf-8-sig').splitlines() if s.strip()]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf-8')


class StaticRoll(nn.Module):
    def __init__(self):
        super().__init__()
        self.first=nn.Conv2d(1,4,5,2,2)
        self.down=nn.ModuleList()
        cin=4
        for cout in [8,8,8]:
            self.down.append(nn.Sequential(nn.Conv2d(cin,cin,5,2,2,groups=cin),nn.ReLU(),
                                           nn.Conv2d(cin,cout,1),nn.ReLU()))
            cin=cout
        self.head=nn.Linear(8*4*4,len(BINS)+1)
        for m in self.modules():
            if isinstance(m,(nn.Conv2d,nn.Linear)):
                nn.init.kaiming_uniform_(m.weight,nonlinearity='relu')
                nn.init.zeros_(m.bias)

    def forward(self,x):
        x=F.relu(self.first(x))
        for block in self.down:x=block(x)
        return self.head(F.avg_pool2d(x,2).flatten(1))


def material(split):
    assert split in ('train','validation')
    rr=rows(DATA/f'prepared_{split}.jsonl')
    z=np.load(DATA/f'roi_cache_{split}.npz')
    images=dict(zip(z['ids'].tolist(),z['images']))
    pp={r['id']:r for r in rows(OLD/f'polar_angle/run_001/{split}_predictions.jsonl')}
    assert all(r['source_group'] in ('D','E','F') if split=='train' else r['source_group']=='G' for r in rr)
    return [dict(record=r,id=r['id'],image=images[r['id']],hub=np.asarray(pp[r['id']]['hub_roi'],np.float64),
                 radius=float(r['roi_request']['radius']),pred=pp[r['id']]) for r in rr if r['id'] in pp]


def good_silver(p):
    f=CONFIG['silver_filter']
    return p['accepted'] and p['inliers']>=f['min_inliers'] and p['unique_locations']>=f['min_unique'] \
        and p['hull_fraction']>=f['min_hull'] and p['median_reprojection_px']<=f['max_reprojection_px'] \
        and p['local_anisotropy']<=f['max_anisotropy'] and abs(p['relative_roll_deg'])<24


def preprocess(gray,hub,radius):
    local=cv2.boxFilter(gray,cv2.CV_16S,(9,9),normalize=True,borderType=cv2.BORDER_REPLICATE)
    im=np.clip((gray.astype(np.int16)-local)*3+128,0,255).astype(np.uint8)
    yy,xx=np.mgrid[:128,:128];rr=(xx-hub[0])**2+(yy-hub[1])**2
    mask=(rr>=(.28*radius)**2)&(rr<=(.95*radius)**2)
    im[~mask]=128
    return (im.astype(np.float32)-128)[None]/128


def transform(it,rng=None,rotation=0.):
    im=it['image'];hub=it['hub'].copy();radius=it['radius']
    if rng is not None:
        rotation=float(rng.uniform(-24,24));scale=float(rng.uniform(.97,1.03))
        move=rng.uniform(-1.5,1.5,2)
    else:scale=1.;move=np.zeros(2)
    M=cv2.getRotationMatrix2D((63.5,63.5),rotation,scale);M[:,2]+=move
    if rotation or scale!=1 or np.any(move):
        im=cv2.warpAffine(im,M,(128,128),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
        hub=np.r_[hub,1]@M.T;radius*=scale
    if rng is not None:
        im=np.clip(np.rint((im.astype(np.float32)-128)*rng.uniform(.8,1.2)+128+rng.uniform(-10,10)),0,255).astype(np.uint8)
    x=preprocess(im,hub,radius)
    if rng is not None and rng.random()<.3:
        # Independent random sector: neither real/silver needle nor PSI is used.
        yy,xx=np.mgrid[:128,:128];aa=np.degrees(np.arctan2(yy-hub[1],xx-hub[0]))
        a=float(rng.uniform(-180,180));width=float(rng.uniform(10,35))
        x[:,abs((aa-a+180)%360-180)<width/2]=0
    # OpenCV positive image rotation is negative in x-right/y-down angles.
    roll=None if it['silver_roll'] is None else it['silver_roll']-rotation
    return x,label(roll)


def label(roll):
    y=np.zeros(len(BINS)+1,np.float32)
    if roll is None:y[-1]=1
    else:
        y[:-1]=np.exp(-.5*((BINS-roll)/2.5)**2)
        y/=y.sum()
    return y


def decode(logits,hub):
    q=np.exp(logits-np.max(logits));q/=q.sum()
    nonnull=float(q[:-1].sum());p=q[:-1]/max(nonnull,1e-12)
    angle=float((p*BINS).sum());std=float(np.sqrt((p*(BINS-angle)**2).sum()))
    center=float(np.linalg.norm(np.asarray(hub)-63.5))
    f=CONFIG['fixed_pose_permission']
    accepted=nonnull>=f['non_null_probability_min'] and std<=f['conditional_stddev_deg_max'] \
        and abs(angle)<f['abs_roll_deg_max_exclusive'] and center<=f['hub_center_distance_max']
    return dict(accepted=bool(accepted),reason='STATIC_PRINT_CNN_ROLL_SUPPORTED' if accepted else 'STATIC_PRINT_CNN_REFERENCE_UNCERTAIN',
                relative_roll_deg=angle,non_null_score=nonnull,conditional_stddev_deg=std,hub_center_distance=center,
                score_is_calibrated_probability=False)


def loss(logits,y):
    return -(y*F.log_softmax(logits,1)).sum(1).mean()


def validation_loss(model,items):
    xx=[];yy=[]
    for it in items:
        for rot in (-12.,0.,12.):
            x,y=transform(it,rotation=rot);xx.append(x);yy.append(y)
    if not xx:raise ValueError('No F silver/true-negative validation items')
    model.eval();total=0.
    with torch.inference_mode():
        for start in range(0,len(xx),32):
            q=model(torch.from_numpy(np.stack(xx[start:start+32])))
            total+=float(loss(q,torch.from_numpy(np.stack(yy[start:start+32]))))*len(q)
    return total/len(xx)


def train(out):
    out.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(4);cv2.setNumThreads(1)
    torch.manual_seed(CONFIG['seed']);np.random.seed(CONFIG['seed']);torch.use_deterministic_algorithms(True)
    silver={r['id']:r for r in rows(OLD/'readout_psi/train_print_pose.jsonl')}
    alltrain=material('train');active=[];labels=[]
    for it in alltrain:
        r=it['record'];p=silver[it['id']]
        if not r['target_present']:it['silver_roll']=None;role='TRUE_NO_GAUGE_NULL'
        elif good_silver(p):it['silver_roll']=float(p['relative_roll_deg']);role='REGISTERED_SILVER_NOT_GOLD'
        else:continue
        active.append(it);labels.append(dict(id=it['id'],source_sha256=r['sha256'],role=role,
            silver_roll_deg=it['silver_roll'],native_registration_label_only=True,
            weight_update=r['source_group'] in ('D','E'),internal_step_selection=r['source_group']=='F',
            human_certified_ground_truth=False,pressure_used_for_label=False))
    tr=[it for it in active if it['record']['source_group'] in ('D','E')]
    va=[it for it in active if it['record']['source_group']=='F']
    model=StaticRoll();cfg=dict(CONFIG,parameters=sum(p.numel() for p in model.parameters()),
        weight_update_items=len(tr),internal_selection_items=len(va),source_code_sha256=sha(__file__),
        source_silver_sha256=sha(OLD/'readout_psi/train_print_pose.jsonl'),
        prepared_train_sha256=sha(DATA/'prepared_train.jsonl'),old_G_predictions_used_for_training=False)
    write(out/'config.json',cfg);write(out/'silver_training_labels.json',labels)
    opt=torch.optim.Adam(model.parameters(),lr=.002);sch=torch.optim.lr_scheduler.CosineAnnealingLR(opt,1600,eta_min=.0001)
    rng=np.random.default_rng(CONFIG['seed']);best=math.inf;history=[];t0=time.monotonic()
    for step in range(1,1601):
        model.train();batch=[tr[int(rng.integers(len(tr)))] for _ in range(16)]
        data=[transform(it,rng=rng) for it in batch]
        x=torch.from_numpy(np.stack([p[0] for p in data]));y=torch.from_numpy(np.stack([p[1] for p in data]))
        opt.zero_grad(set_to_none=True);v=loss(model(x),y)
        if not torch.isfinite(v):raise RuntimeError('nonfinite loss')
        v.backward();opt.step();sch.step()
        if step%200==0:
            val=validation_loss(model,va);h=dict(step=step,train_loss=float(v.detach()),F_silver_selection_loss=val,elapsed_s=time.monotonic()-t0)
            history.append(h);write(out/'history.json',history)
            if val<best:
                best=val;torch.save(dict(state_dict=model.state_dict(),step=step,config=cfg),out/'best_weights.pt')
            print(json.dumps(h),flush=True)
    write(out/'training_receipt.json',dict(status='ONE_FIXED_RUN_COMPLETED_G_NOT_EVALUATED',steps=1600,elapsed_s=time.monotonic()-t0,
        best_checkpoint_sha256=sha(out/'best_weights.pt'),config_sha256=sha(out/'config.json'),history_sha256=sha(out/'history.json'),
        H_opened=False,hardware_actions=False))


def infer(out):
    torch.set_num_threads(4);cv2.setNumThreads(1)
    ck=torch.load(out/'best_weights.pt',weights_only=True);model=StaticRoll();model.load_state_dict(ck['state_dict']);model.eval()
    pp=[]
    with torch.inference_mode():
        for split in ('train','validation'):
            for it in material(split):
                x=preprocess(it['image'],it['hub'],it['radius'])
                logits=model(torch.from_numpy(x[None]))[0].numpy()
                p=decode(logits,it['hub'])
                pp.append(dict(id=it['id'],source_sha256=it['record']['sha256'],split=split,**p,
                    native_frame_used=False,query_uses_GT_points=False,query_uses_pressure=False,
                    method='STATIC_PRINT_ROLL_CNN_1',checkpoint_sha256=sha(out/'best_weights.pt')))
    (out/'candidate_pose.jsonl').write_text(''.join(json.dumps(p)+'\n' for p in pp),'utf-8')
    return pp


def score(out):
    sys.path.insert(0,str(OLD/'readout_psi'));import readout_adapter as numeric
    sys.path.insert(0,str(PREVIOUS));import calibrate_and_score as calibrator
    poses={r['id']:r for r in rows(out/'candidate_pose.jsonl')}
    # Reuse frozen fit mathematics, but bind this new coordinate-system source.
    records=rows(DATA/'prepared_train.jsonl')
    measurements=[]
    front={'front_medium_soft_light','front_large_soft_light','front_dim','backlight_or_local_reflection'}
    for r in records:
        p=poses.get(r['id'])
        if not p or not p['accepted'] or r['loss_mask']!=[1,1] or not r['target_present'] or r['scene']['primary'] not in front:continue
        a=numeric.theta(r['keypoints']['hub']['xy'],r['keypoints']['thin_terminal']['xy'])
        measurements.append(dict(id=r['id'],reference_psi=r['pressure']['value'],
            reference_angle_deg=(a-p['relative_roll_deg'])%360,source_sha256=r['sha256']))
    angles=np.radians([m['reference_angle_deg'] for m in measurements]);center=math.degrees(math.atan2(np.sin(angles).mean(),np.cos(angles).mean()))%360
    for m in measurements:m['reference_angle_unwrapped_deg']=numeric.unwrap(m['reference_angle_deg'],center)
    anchors=[]
    for psi in sorted(set(m['reference_psi'] for m in measurements)):
        aa=[m['reference_angle_unwrapped_deg'] for m in measurements if m['reference_psi']==psi]
        anchors.append(dict(reference_psi=psi,median_reference_angle_deg=float(np.median(aa)),images=len(aa)))
    assert len(anchors)>=5,'Insufficient TRAIN calibration support; do not relax after seeing G'
    xx=np.array([a['median_reference_angle_deg'] for a in anchors]);yy=np.array([a['reference_psi'] for a in anchors])
    slope,intercept=np.polyfit(xx,yy,1)
    cal=dict(primary_unit='psi',slope_psi_per_degree=float(slope),intercept_psi=float(intercept),branch_center_deg=center,
        supported_angle_interval_deg=[float(xx.min()),float(xx.max())],supported_pressure_interval_psi=[float(yy.min()),float(yy.max())],
        anchors=anchors,fit_measurements=measurements,fit_groups=['D','E','F'],G_used_for_fitting=False,
        native_frame_at_runtime=False,coordinate_system='CNN-predicted relative roll; newly fit train-only calibration',
        fit_is_unchanged_calibration_ablation=False)
    write(out/'calibration_psi.json',cal)
    lookup={r['id']:r for r in rows(DATA/'prepared_validation.jsonl')}
    predictions=rows(OLD/'polar_angle/run_001/validation_predictions.jsonl')
    outputs=[numeric.apply_prediction(p,poses[p['id']],cal) for p in predictions]
    for r in outputs:r['pose_source']='ROI128_STATIC_REFERENCE_CNN_NO_QUERY_GT'
    summary=numeric.score_outputs(outputs,lookup)
    summary['static_pose_supported']=sum(p['accepted'] for p in poses.values() if p['split']=='validation')
    result=dict(status='SINGLE_FIXED_REFERENCE_CNN_PC_DEVELOPMENT_COMPARISON_NOT_MCU_DEPLOYMENT',unit='psi',summary=summary,rows=outputs,
        source=dict(candidate_checkpoint=sha(out/'best_weights.pt'),pose=sha(out/'candidate_pose.jsonl'),calibration=sha(out/'calibration_psi.json'),
                    frozen_hub=sha(DATA/'run_002/best_weights.pt'),frozen_needle=sha(OLD/'polar_angle/run_001/best_weights.pt')),
        old_models_changed=False,query_native_frame_used=False,query_pressure_used=False,query_GT_points_used=False,
        H_opened=False,hardware_actions=False)
    write(out/'readout_psi.json',result);print(json.dumps(summary,ensure_ascii=False,indent=2))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=['prepare','train','infer','score']);ap.add_argument('--out',type=Path,default=HERE/'reference_cnn/run_001');args=ap.parse_args()
    if args.command=='prepare':write(HERE/'candidate_config_before_training.json',dict(CONFIG,parameters=sum(p.numel() for p in StaticRoll().parameters()),source_code_sha256=sha(__file__)))
    elif args.command=='train':train(args.out)
    elif args.command=='infer':infer(args.out)
    else:score(args.out)


if __name__=='__main__':main()
