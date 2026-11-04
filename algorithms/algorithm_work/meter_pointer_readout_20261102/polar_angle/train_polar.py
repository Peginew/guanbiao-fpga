"""Direct all-angle needle evidence from an ROI and a frozen CNN hub.

No geometric tip, true pressure, query true hub, or template registration is an
inference input.  Native point labels are used only for training/evaluation.
"""
from pathlib import Path
import argparse, hashlib, json, math, time
import cv2
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

HERE = Path(__file__).resolve().parent
PREV = HERE.parents[1] / 'meter_cnn_training_20261102'
DEGREES = np.arange(360, dtype=np.float32)
RATIOS = np.linspace(.20, .84, 8, dtype=np.float32)

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p): return json.loads(Path(p).read_text('utf-8-sig'))
def write(p, x): Path(p).write_text(json.dumps(x, ensure_ascii=False, indent=2)+'\n', 'utf-8')
def rows(p): return [json.loads(x) for x in Path(p).read_text('utf-8-sig').splitlines() if x.strip()]

class PolarNeedle(nn.Module):
    def __init__(self):
        super().__init__()
        self.first = nn.Conv1d(16, 8, 7)
        self.depthwise = nn.Conv1d(8, 8, 7, groups=8)
        self.mix = nn.Conv1d(8, 4, 1)
        self.head = nn.Conv1d(4, 1, 1)
        for m in [self.first, self.depthwise, self.mix]:
            nn.init.kaiming_uniform_(m.weight, nonlinearity='relu')
            nn.init.constant_(m.bias, .05)
        nn.init.normal_(self.head.weight, std=.01)
        nn.init.constant_(self.head.bias, -2.197224577)
    def forward(self, x):
        x = F.relu(self.first(F.pad(x, (3, 3), mode='circular')))
        x = F.relu(self.depthwise(F.pad(x, (3, 3), mode='circular')))
        x = F.relu(self.mix(x))
        return self.head(x)[:, 0]

def polar_features(gray, center, radius):
    # 24 radial positions, in 8 three-sample bands. Outer metal rim excluded.
    r = (RATIOS[:, None] + np.array([-.02, 0, .02], np.float32)) * radius
    radians = DEGREES * (np.pi/180)
    xx = center[0] + r[..., None]*np.cos(radians)
    yy = center[1] + r[..., None]*np.sin(radians)
    invalid = (xx < 0) | (xx > 127) | (yy < 0) | (yy > 127)
    samples = cv2.remap(gray, xx.reshape(24, 360).astype(np.float32),
                        yy.reshape(24, 360).astype(np.float32), cv2.INTER_LINEAR,
                        borderMode=cv2.BORDER_CONSTANT, borderValue=128)
    band = samples.reshape(8, 3, 360).astype(np.float32).mean(1)
    # A thin dark radial line has positive contrast to its angular neighbours.
    contrast = ((np.roll(band, 4, 1)+np.roll(band, -4, 1))*.5-band)/64
    return np.concatenate([(band-128)/128, np.clip(contrast, -2, 2)], 0), float(invalid.mean())

def angle(h, t): return math.degrees(math.atan2(t[1]-h[1], t[0]-h[0])) % 360
def delta(a, b): return abs((a-b+180)%360-180)
def target(theta, sigma):
    if theta is None: return np.zeros(360, np.float32)
    d = (DEGREES-theta+180)%360-180
    y = np.exp(-d*d/(2*sigma*sigma)).astype(np.float32)
    y[int(round(theta))%360] = 1
    return y
def focal(logits, labels):
    p = logits.sigmoid().clamp(1e-5, 1-1e-5)
    pos = labels.eq(1)
    return (-p.log()*(1-p)**2*pos-(1-p).log()*p**2*(1-labels)**4*~pos).sum()/pos.sum().clamp(min=1)
def statistics(v):
    return dict(n=len(v), mean=float(np.mean(v)) if v else None,
                median=float(np.median(v)) if v else None, p90=float(np.percentile(v,90)) if v else None)

def dataset(split):
    recs = rows(PREV/f'prepared_{split}.jsonl')
    old = load(PREV/'run_002'/('train_evaluation.json' if split=='train' else 'validation_evaluation.json'))
    hubs = {r['id']: r for r in old['rows']}
    cache = np.load(PREV/f'roi_cache_{split}.npz')
    ims = dict(zip(cache['ids'].tolist(), cache['images']))
    out = []
    for r in recs:
        if split=='train' and not r['active_for_initial_weight_updates']: continue
        assert r['source_group'] in ({'D','E','F'} if split=='train' else {'G'})
        h = hubs[r['id']]
        center = h['predicted_points_roi'][0]  # actual frozen CNN output, never GT
        feature, outside = polar_features(ims[r['id']], center, r['roi_request']['radius'])
        tip = r['roi_keypoints']['thin_terminal']['xy'] if r['loss_mask'][1] and r['target_present'] else None
        theta = angle(center, tip) if tip is not None else None
        sigma = max(2.5, math.degrees(math.atan2(float(r['roi_keypoints']['thin_terminal'].get('uncertainty_roi_px') or 0),
                            max(1, np.linalg.norm(np.array(tip)-center))))) if tip is not None else 2.5
        gt_hub = r['roi_keypoints']['hub']['xy'] if r['loss_mask'][0] and r['target_present'] else None
        reference = angle(gt_hub, tip) if gt_hub is not None and tip is not None else None
        out.append(dict(id=r['id'], record=r, image=ims[r['id']], feature=feature,
                        center=center, frozen_hub=h, outside=outside, theta=theta,
                        reference=reference, label=target(theta, sigma), sigma=sigma,
                        supervised=bool(tip is not None or not r['target_present'])))
    return out

def decode(v):
    p = 1/(1+np.exp(-np.clip(v, -40, 40)))
    peak = int(p.argmax())
    ind = (np.arange(peak-2, peak+3)%360).astype(int)
    local = np.arange(-2,3)
    theta = float((peak+(p[ind]*local).sum()/max(1e-9,p[ind].sum()))%360)
    far = p.copy(); far[np.abs((DEGREES-peak+180)%360-180)<=10]=0
    return theta, float(p[peak]), float(p[peak]-far.max())

def evaluate(model, items, out=None):
    model.eval(); result=[]; loss_num=0; count=0
    with torch.inference_mode():
        for start in range(0,len(items),32):
            batch=items[start:start+32]
            logits=model(torch.from_numpy(np.stack([i['feature'] for i in batch])))
            eligible=[j for j,i in enumerate(batch) if i['supervised']]
            if eligible:
                lab=torch.from_numpy(np.stack([batch[j]['label'] for j in eligible]))
                den=max(1,int(lab.eq(1).sum()));loss_num+=float(focal(logits[eligible],lab))*den;count+=den
            for it,v in zip(batch,logits.numpy()):
                theta,score,margin=decode(v); h=it['frozen_hub']
                center_ok=np.linalg.norm(np.array(it['center'])-63.5)<=20
                valid=score>=.3 and margin>=.02 and h['peaks'][0]>=.3 and h['margins'][0]>=.02 and center_ok and it['outside']<=.05
                radius=it['record']['roi_request']['radius']*.70
                end=(np.array(it['center'])+radius*np.array([math.cos(math.radians(theta)),math.sin(math.radians(theta))])).tolist()
                row=dict(id=it['id'],model_name='polar_angle_v1',angle_deg_image=theta,valid=bool(valid),score=score,margin=margin,
                         hub_roi=it['center'],direction_reference_endpoint_roi=end,
                         endpoint_semantics='Display direction radius only; not a detected tip',
                         target_present=it['record']['target_present'],reference_angle_deg=it['reference'],
                         loss_mask=it['record']['loss_mask'],source_sha256=it['record']['sha256'],split=it['record']['split'])
                if it['reference'] is not None: row['angle_error_deg']=delta(theta,it['reference'])
                if it['theta'] is not None: row['target_ray_error_deg']=delta(theta,it['theta'])
                if 'hub_error_roi' in h: row['hub_error_roi']=h['hub_error_roi']
                result.append(row)
                if out:
                    im=cv2.cvtColor(it['image'],cv2.COLOR_GRAY2BGR)
                    cv2.line(im,tuple(np.rint(it['center']).astype(int)),tuple(np.rint(end).astype(int)),(0,200,255),1)
                    if it['reference'] is not None:
                        hh=np.array(it['record']['roi_keypoints']['hub']['xy']);tt=np.array(it['record']['roi_keypoints']['thin_terminal']['xy'])
                        cv2.line(im,tuple(np.rint(hh).astype(int)),tuple(np.rint(tt).astype(int)),(0,220,0),1)
                    cv2.imencode('.png',cv2.resize(im,(384,384),interpolation=cv2.INTER_NEAREST))[1].tofile(str(out/(it['id']+'.png')))
    full=[r for r in result if 'angle_error_deg' in r]; accepted=[r for r in full if r['valid']];neg=[r for r in result if not r['target_present']]
    return dict(summary=dict(images=len(items),selection_loss=loss_num/max(count,1),angle_error_deg=statistics([r['angle_error_deg'] for r in full]),
                within5=sum(r['angle_error_deg']<=5 for r in full),within10=sum(r['angle_error_deg']<=10 for r in full),full=len(full),
                accepted=len(accepted),accepted_over10=sum(r['angle_error_deg']>10 for r in accepted),negative_count=len(neg),negative_accepted=sum(r['valid'] for r in neg)),rows=result)

def run(args):
    args.out.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(4);cv2.setNumThreads(1);torch.manual_seed(1103);np.random.seed(1103)
    torch.use_deterministic_algorithms(True)
    tr=dataset('train'); va=dataset('validation'); active=[i for i in tr if i['supervised']]
    assert len(tr)==164 and len(va)==59 and len(active)==149
    assert not ({i['record']['sha256'] for i in tr}&{i['record']['sha256'] for i in va})
    model=PolarNeedle(); assert sum(p.numel() for p in model.parameters())==1009
    config=dict(model='polar_angle_v1',parameters=1009,frozen_hub_parameters=1202,optimizer_steps=args.steps,
                train_images=164,angular_supervised_or_negative=149,validation_images=59,seed=1103,
                input='16 radial gray/contrast features x360 angles; predicted hub only',radial_bands=RATIOS.tolist(),
                label='Direction to directly visible thin terminal from frozen predicted hub; never pressure-derived',
                auxiliary_true_hub='Evaluation reference only, never input',selection='G angular focal loss only',
                frozen_hub_checkpoint_sha256=sha(PREV/'run_002/best_weights.pt'),source_code_sha256=sha(__file__),
                prepared_train_sha256=sha(PREV/'prepared_train.jsonl'),prepared_validation_sha256=sha(PREV/'prepared_validation.jsonl'),
                source_cache_and_hub_outputs_sha256={name:sha(PREV/name) for name in [
                    'roi_cache_train.npz','roi_cache_validation.npz',
                    'run_002/train_evaluation.json','run_002/validation_evaluation.json']},
                fixed_acceptance=dict(peak=.3,margin=.02,hub_peak=.3,hub_margin=.02,hub_center_distance_max=20,outside_fraction_max=.05),
                predeclared_metrics='Full points all physical angle errors; readout adapter frozen train-only calibration, 0.05bar engineering tolerance',
                preprocessing='OpenCV bilinear remap PC reference; integer remap and MCU still pending',
                cost_estimate=dict(needle_conv_MAC=355680,int8_needle_weights_S32_bias_bytes=1072,
                                  input_feature_bytes_INT8=5760,max_activation_bytes_INT8=2880,
                                  gray_samples_per_ROI=8640,bilinear_source_reads=34560,
                                  sin_cos_S16_lut_bytes=1440,incremental_FPGA_Slice_measured=False),
                test_H_opened=False,pressure_used_as_network_input=False,hardware_actions=False)
    write(args.out/'config.json',config)
    optimizer=torch.optim.Adam(model.parameters(),lr=.002)
    scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,args.steps,eta_min=.0001)
    rng=np.random.default_rng(1103);best=float('inf');history=[];start=time.monotonic()
    for step in range(1,args.steps+1):
        model.train(); batch=[active[int(rng.integers(len(active)))] for _ in range(24)]
        xs=[];ys=[]
        for it in batch:
            shift=int(rng.integers(-8,9));x=np.roll(it['feature'],shift,1).copy(); gain=float(rng.uniform(.85,1.15))
            x[:8]=np.clip(x[:8]*gain+rng.uniform(-.08,.08),-1,1); x[8:]*=gain
            xs.append(x);ys.append(np.roll(it['label'],shift))
        optimizer.zero_grad(set_to_none=True); loss=focal(model(torch.from_numpy(np.stack(xs))),torch.from_numpy(np.stack(ys)))
        if not torch.isfinite(loss): raise RuntimeError('Nonfinite loss')
        loss.backward();optimizer.step();scheduler.step()
        if step%200==0 or step==args.steps:
            ev=evaluate(model,va);score=ev['summary']['selection_loss'];entry=dict(step=step,loss=float(loss.detach()),validation=ev['summary'],elapsed_s=time.monotonic()-start)
            history.append(entry);write(args.out/'history.json',history)
            if score<best:
                best=score;torch.save(dict(state_dict=model.state_dict(),step=step,config=config),args.out/'best_weights.pt')
            print(json.dumps(entry),flush=True)
    ck=torch.load(args.out/'best_weights.pt',weights_only=True);model.load_state_dict(ck['state_dict'])
    overlays=args.out/'validation_overlays';overlays.mkdir()
    ev=evaluate(model,va,overlays); et=evaluate(model,tr)
    write(args.out/'validation_evaluation.json',ev);write(args.out/'train_evaluation.json',et)
    for name,report in [('validation',ev),('train',et)]:
        (args.out/(name+'_predictions.jsonl')).write_text(''.join(json.dumps(r)+'\n' for r in report['rows']),'utf-8')
    write(args.out/'receipt.json',dict(status='FLOAT_POLAR_CANDIDATE_TRAINED_NO_DEPLOYMENT',completed_steps=args.steps,best_step=ck['step'],
          elapsed_s=time.monotonic()-start,checkpoint_sha256=sha(args.out/'best_weights.pt'),config_sha256=sha(args.out/'config.json'),
          validation=ev['summary'],train=et['summary'],test_H_opened=False,hardware_actions=False))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--out',type=Path,default=HERE/'run_001');a.add_argument('--steps',type=int,default=2400)
    run(a.parse_args())
