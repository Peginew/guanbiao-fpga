"""One fixed robust hub -> same-observation polar warm-training candidate.

No network expansion, pressure loss, threshold relaxation or hardware access.
Default preflight; the explicit train mode executes the one reviewed chain.
"""
from pathlib import Path
import argparse
import json
import math
import sys
import time
import cv2
import numpy as np
import torch

HERE = Path(__file__).resolve().parent
WORK = HERE.parents[1]
SOURCE = WORK / 'meter_cnn_training_20261102'
POINTER = WORK / 'meter_pointer_readout_20261102'
sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(POINTER / 'polar_angle'))
import train_grouped_v2 as base
import train_polar as polar

HUB_WARM = SOURCE / 'run_002/best_weights.pt'
POLAR_WARM = POINTER / 'polar_angle/run_001/best_weights.pt'
HUB_SHA = 'c221678efa4762bed298828b2e8e8ba3c2a6b343c2c16efe35aec77a85c896df'
POLAR_SHA = 'd139ecdc1059829be18e23eaf5d503d5c9d59a798d2986774441f88cc1804882'
PLAN = dict(seed=1104, threads=4, hub_steps=2400, hub_batch=12, polar_steps=2400, polar_batch=24,
            lr=.0006, lr_end=.00006, evaluate_every=200, fixed_augmented_views_per_train_source=4,
            roll_opencv_deg=[-8., 8.], scale=[.96, 1.04], translation_roi_px=[-2., 2.],
            gamma=[.7, 1.5], low_frequency_shadow_slopes=[-.25, .25], shadow_gain=[.65, 1.],
            gaussian_highlight_alpha=[0., .30], highlight_sigma_roi=[12., 28.],
            light_blur_probability=.3, light_blur_kernel=3, light_blur_sigma=[.2, .65],
            photo_probability=.8, photo_attempts=4, point_patch_radius=3,
            minimum_retained_point_contrast_fraction=.30, maximum_extra_point_patch_saturation=.20,
            hub_selection='Minimum G visible bounded hub mean ROI error, including unchanged warm-start step0',
            polar_selection='Minimum G angular focal loss, including warm-start with new hub at step0',
            output_thresholds_unchanged=dict(needle_score=.3, needle_margin=.02, hub_score=.3, hub_margin=.02,
                                             hub_center_distance_roi=20, outside_fraction=.05),
            parameters=dict(hub=1202, polar=1009), pressure_unit='psi', no_opaque_occlusion=True)


def load_items():
    assert base.sha(HUB_WARM) == HUB_SHA and base.sha(POLAR_WARM) == POLAR_SHA
    adapter = base.get_adapter()
    tr = [r for r in adapter.load_prepared(SOURCE / 'prepared_train.jsonl') if r['active_for_initial_weight_updates']]
    va = adapter.load_prepared(SOURCE / 'prepared_validation.jsonl')
    assert len(tr) == 164 and len(va) == 59
    assert not ({r['sha256'] for r in tr} & {r['sha256'] for r in va})
    return base.build_items(tr, adapter, {'D', 'E', 'F'}, 'train'), base.build_items(va, adapter, {'G'}, 'validation')


def patch(im, point):
    x, y = np.rint(point).astype(int)
    radius = PLAN['point_patch_radius']
    return im[max(0, y-radius):min(128, y+radius+1), max(0, x-radius):min(128, x+radius+1)]


def point_evidence_preserved(before, after, points, masks):
    for k, point in enumerate(points):
        if point is None or not masks[k]:
            continue
        old, new = patch(before, point), patch(after, point)
        contrast = float(np.ptp(old))
        if contrast >= 4 and float(np.ptp(new)) < max(2., contrast * PLAN['minimum_retained_point_contrast_fraction']):
            return False
        sat_old = float(((old <= 1) | (old >= 254)).mean())
        sat_new = float(((new <= 1) | (new >= 254)).mean())
        if sat_new > sat_old + PLAN['maximum_extra_point_patch_saturation']:
            return False
    return True


def augmented_view(rng, item):
    matrix = np.array([[1., 0., 0.], [0., 1., 0.]])
    points = item['points']
    theta, scale = 0., 1.
    for _ in range(12):
        a, s = float(rng.uniform(*PLAN['roll_opencv_deg'])), float(rng.uniform(*PLAN['scale']))
        m = cv2.getRotationMatrix2D((63.5, 63.5), a, s)
        m[:, 2] += rng.uniform(*PLAN['translation_roi_px'], 2)
        trial = [None if p is None else (np.r_[p, 1] @ m.T).tolist() for p in item['points']]
        if all(p is None or not item['mask'][k] or (np.asarray(p) >= 0).all() and (np.asarray(p) <= 127).all() for k, p in enumerate(trial)):
            matrix, points, theta, scale = m, trial, a, s
            break
    geometric = cv2.warpAffine(item['image'], matrix, (128, 128), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
    result = geometric
    metadata = dict(affine_matrix=matrix.tolist(), opencv_roll_deg=theta, uniform_scale=scale,
                    photometric_accepted=False, photometric_failed_attempts=0, point_mask_unchanged=True)
    if rng.random() < PLAN['photo_probability']:
        yy, xx = np.mgrid[:128, :128].astype(np.float32)
        for attempt in range(PLAN['photo_attempts']):
            gamma = float(rng.uniform(*PLAN['gamma']))
            image = 255. * (geometric.astype(np.float32) / 255.) ** gamma
            ax, ay = rng.uniform(*PLAN['low_frequency_shadow_slopes'], 2)
            shadow = np.clip(float(rng.uniform(*PLAN['shadow_gain'])) + ax*(xx-63.5)/127 + ay*(yy-63.5)/127, .55, 1.)
            image *= shadow
            cx, cy = rng.uniform(0, 127, 2)
            sigma = float(rng.uniform(*PLAN['highlight_sigma_roi']))
            alpha = float(rng.uniform(*PLAN['gaussian_highlight_alpha']))
            light = alpha * np.exp(-((xx-cx)**2+(yy-cy)**2)/(2*sigma*sigma))
            # Convex soft highlight retains >=70% local contrast before blur;
            # it is not an opaque white patch or a fabricated occlusion label.
            image = image * (1-light) + 255*light
            blur = 0.
            if rng.random() < PLAN['light_blur_probability']:
                blur = float(rng.uniform(*PLAN['light_blur_sigma']))
                image = cv2.GaussianBlur(image, (3, 3), blur)
            image = np.clip(np.rint(image), 0, 255).astype(np.uint8)
            if point_evidence_preserved(geometric, image, points, item['mask']):
                result = image
                metadata.update(photometric_accepted=True, gamma=gamma, shadow_slopes=[float(ax),float(ay)],
                                highlight_center=[float(cx),float(cy)], highlight_alpha=alpha,
                                highlight_sigma=sigma, blur_sigma=blur)
                break
            metadata['photometric_failed_attempts'] += 1
    assert point_evidence_preserved(geometric, result, points, item['mask'])
    heat = base.heat_from_points(points, item['sigmas'], item['mask'])
    return result, heat, item['mask'].copy(), points, metadata


def hub_evaluate(model, items):
    model.eval()
    rows, total, denominator = [], 0., 0
    with torch.inference_mode():
        for start in range(0, len(items), 16):
            batch = items[start:start+16]
            logits = model(torch.from_numpy(np.stack([base.normalized(it['image']) for it in batch])))
            targets = torch.from_numpy(np.stack([it['heat'] for it in batch]))
            masks = torch.from_numpy(np.stack([it['mask'] for it in batch]))
            masks[:, 1] = 0
            n = max(1, int((targets.eq(1)*masks[:,:,None,None]).sum()))
            total += float(base.masked_loss(logits, targets, masks)) * n
            denominator += n
            for it, value in zip(batch, logits.numpy()):
                points, peaks, margins = base.decode(value)
                center = points[0].tolist()
                center_distance = float(np.linalg.norm(points[0] - 63.5))
                permitted = peaks[0] >= .3 and margins[0] >= .02 and center_distance <= 20
                r = dict(id=it['id'], source_group=it['record']['source_group'], split=it['record']['split'],
                         condition=it['record']['scene']['primary'], target_present=it['target_present'],
                         hub_roi=center, predicted_points_roi=[center, None], peaks=[peaks[0], None], margins=[margins[0],None],
                         hub_center_distance_roi=center_distance, hub_evidence_permitted=bool(permitted),
                         source_sha256=it['record']['sha256'], tip_head_not_used_as_new_locator=True)
                if it['mask'][0] and it['points'][0] is not None:
                    r['hub_error_roi'] = float(np.linalg.norm(points[0]-it['points'][0]))
                    r['hub_error_native'] = r['hub_error_roi'] * it['stride']
                rows.append(r)
    known = [r for r in rows if 'hub_error_roi' in r]
    summary = dict(images=len(items), hub_error_roi=base.stats([r['hub_error_roi'] for r in known]),
                   hub_error_native=base.stats([r['hub_error_native'] for r in known]), hub_masked_focal=total/max(denominator,1),
                   visible_bounded_hubs=len(known), permitted_known_hubs=sum(r['hub_evidence_permitted'] for r in known),
                   permitted_known_hubs_over4roi=sum(r['hub_evidence_permitted'] and r['hub_error_roi']>4 for r in known),
                   hub_thresholds_unchanged=True, tip_accuracy_not_claimed=True)
    summary['by_scene'] = {c: dict(hub_error_roi=base.stats([r['hub_error_roi'] for r in known if r['condition']==c]),
                                 known=sum(r['condition']==c for r in known),
                                 permitted=sum(r['hub_evidence_permitted'] for r in known if r['condition']==c))
                           for c in sorted({r['condition'] for r in rows})}
    summary['named_diagnostics'] = {r['id']:r for r in rows if r['id'] in {'G_004','G_024','G_033','G_054'}}
    return dict(summary=summary, rows=rows)


def checkpoint(model, path, step, metric, kind):
    torch.save(dict(state_dict={k:v.detach().cpu() for k,v in model.state_dict().items()}, step=step,
                    parameters=sum(p.numel() for p in model.parameters()), selection_metric=metric,
                    kind=kind, PLAN=PLAN, trainer_sha256=base.sha(__file__), unit='psi'), path)


def train_hub(out, tr, va):
    out.mkdir()
    model = base.Direct(4)
    model.load_state_dict(torch.load(HUB_WARM, weights_only=True)['state_dict'])
    baseline = hub_evaluate(model, va)
    base.write(out/'warm_validation.json', baseline)
    best, best_step = baseline['summary']['hub_error_roi']['mean'], 0
    checkpoint(model, out/'best_weights.pt', 0, best, 'hub_only_warm_robust')
    active = [it for it in tr if it['mask'][0]]
    assert len(active)==158
    optimizer = torch.optim.Adam(model.parameters(), lr=PLAN['lr'])
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, PLAN['hub_steps'], eta_min=PLAN['lr_end'])
    rng = np.random.default_rng(PLAN['seed'])
    history, stats = [], dict(views=0, photo_accepted=0, photo_failed_attempts=0)
    start = time.monotonic()
    for step in range(1, PLAN['hub_steps']+1):
        model.train()
        batch = [active[int(rng.integers(len(active)))] for _ in range(PLAN['hub_batch'])]
        augmented = [augmented_view(rng, it) for it in batch]
        x = torch.from_numpy(np.stack([base.normalized(z[0]) for z in augmented]))
        y = torch.from_numpy(np.stack([z[1] for z in augmented]))
        mask = torch.from_numpy(np.stack([z[2] for z in augmented]));mask[:,1]=0
        optimizer.zero_grad(set_to_none=True)
        loss = base.masked_loss(model(x), y, mask)
        if not torch.isfinite(loss):raise RuntimeError('Hub nonfinite loss')
        loss.backward();optimizer.step();scheduler.step()
        stats['views'] += len(augmented)
        stats['photo_accepted'] += sum(z[4]['photometric_accepted'] for z in augmented)
        stats['photo_failed_attempts'] += sum(z[4]['photometric_failed_attempts'] for z in augmented)
        if step%PLAN['evaluate_every']==0 or step==PLAN['hub_steps']:
            result = hub_evaluate(model,va);metric=result['summary']['hub_error_roi']['mean']
            if metric<best:
                best,best_step=metric,step;checkpoint(model,out/'best_weights.pt',step,best,'hub_only_warm_robust')
            history.append(dict(step=step, train_hub_focal=float(loss.detach()), validation=result['summary'], elapsed_s=time.monotonic()-start))
            base.write(out/'history.json',history)
            print(json.dumps(dict(event='HUB_VALIDATION',step=step,best_step=best_step,mean_hub_roi=metric)),flush=True)
    selected=torch.load(out/'best_weights.pt',weights_only=True);model.load_state_dict(selected['state_dict'])
    validation,training=hub_evaluate(model,va),hub_evaluate(model,tr)
    base.write(out/'validation_evaluation.json',validation);base.write(out/'train_evaluation.json',training)
    base.write(out/'receipt.json',dict(status='HUB_FLOAT_TRAINED_NOT_BOARD_ACCEPTANCE',completed_steps=PLAN['hub_steps'],best_step=best_step,
               best_mean_hub_roi=best,elapsed_s=time.monotonic()-start,augmentation=stats,parameters=1202,tip_head_used=False,
               checkpoint_sha256=base.sha(out/'best_weights.pt'),H_or_ABC_opened=False))
    return model,training,validation


def make_polar_items(hub_model, items, augment_count, split, out):
    # Every feature uses the actual hub predicted from the very same augmented
    # pixels.  Never reuse native/old-center coordinates on a different view.
    views=[]
    for ordinal,it in enumerate(items):
        for view in range(augment_count+1):
            seed=PLAN['seed']+ordinal*101+view
            if view:
                image,heat,mask,points,meta=augmented_view(np.random.default_rng(seed),it)
            else:
                image,points,meta=it['image'],it['points'],dict(identity=True)
            views.append(dict(item=it,image=image,points=points,view=view,seed=seed,metadata=meta))
    result=[];hub_model.eval()
    with torch.inference_mode():
        for start in range(0,len(views),32):
            batch=views[start:start+32]
            logits=hub_model(torch.from_numpy(np.stack([base.normalized(v['image']) for v in batch]))).numpy()
            for v,logit in zip(batch,logits):
                it=v['item'];pts,peaks,margins=base.decode(logit);center=pts[0].tolist()
                feature,outside=polar.polar_features(v['image'],center,it['record']['roi_request']['radius'])
                tip=v['points'][1] if it['mask'][1] and it['target_present'] else None
                theta=polar.angle(center,tip) if tip is not None else None
                sigma=max(2.5,math.degrees(math.atan2(float(it['record']['roi_keypoints']['thin_terminal'].get('uncertainty_roi_px')or 0),
                                max(1.,np.linalg.norm(np.array(tip)-center))))) if tip is not None else 2.5
                reference=polar.angle(v['points'][0],tip) if it['mask'][0] and v['points'][0] is not None and tip is not None else None
                h=dict(peaks=[peaks[0],None],margins=[margins[0],None])
                if reference is not None:h['hub_error_roi']=float(np.linalg.norm(np.array(center)-v['points'][0]))
                ident=it['id'] if not v['view'] else it['id']+f'_aug{v["view"]}'
                result.append(dict(id=ident,source_id=it['id'],record=it['record'],image=v['image'],feature=feature,
                                   center=center,frozen_hub=h,outside=outside,theta=theta,reference=reference,label=polar.target(theta,sigma),
                                   sigma=sigma,supervised=bool(tip is not None or not it['target_present']),view=v['view'],seed=v['seed'],metadata=v['metadata']))
    if out is not None:
        np.savez_compressed(out/(split+'_features.npz'),features=np.stack([r['feature'] for r in result]),labels=np.stack([r['label'] for r in result]),
                            centers=np.asarray([r['center'] for r in result]),ids=np.asarray([r['id'] for r in result]))
        (out/(split+'_feature_provenance.jsonl')).write_text(''.join(json.dumps(dict(id=r['id'],source_id=r['source_id'],source_sha256=r['record']['sha256'],
             view=r['view'],seed=r['seed'],same_observation_hub=r['center'],image_sha256=base.hashlib.sha256(r['image'].tobytes()).hexdigest(),
             feature_sha256=base.hashlib.sha256(r['feature'].tobytes()).hexdigest(),supervised=r['supervised'],metadata=r['metadata']),ensure_ascii=False)+'\n'for r in result),'utf-8')
    return result


def train_polar(out, hub_model, tr, va, hub_checkpoint):
    out.mkdir()
    tr_views=make_polar_items(hub_model,tr,PLAN['fixed_augmented_views_per_train_source'],'train',out)
    val=make_polar_items(hub_model,va,0,'validation',out)
    train_native=[r for r in tr_views if r['view']==0]
    active=[r for r in tr_views if r['supervised']]
    assert len(tr_views)==820 and len(active)==745 and len(val)==59
    model=polar.PolarNeedle();model.load_state_dict(torch.load(POLAR_WARM,weights_only=True)['state_dict'])
    baseline=polar.evaluate(model,val);base.write(out/'warm_with_new_hub_validation.json',baseline)
    best,best_step=baseline['summary']['selection_loss'],0
    checkpoint(model,out/'best_weights.pt',0,best,'robust_polar_same_observation')
    optimizer=torch.optim.Adam(model.parameters(),lr=PLAN['lr'])
    scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,PLAN['polar_steps'],eta_min=PLAN['lr_end'])
    rng=np.random.default_rng(PLAN['seed']+1);history=[];start=time.monotonic()
    for step in range(1,PLAN['polar_steps']+1):
        model.train();batch=[active[int(rng.integers(len(active)))]for _ in range(PLAN['polar_batch'])]
        optimizer.zero_grad(set_to_none=True)
        loss=polar.focal(model(torch.from_numpy(np.stack([r['feature']for r in batch]))),torch.from_numpy(np.stack([r['label']for r in batch])))
        if not torch.isfinite(loss):raise RuntimeError('Polar nonfinite loss')
        loss.backward();optimizer.step();scheduler.step()
        if step%PLAN['evaluate_every']==0 or step==PLAN['polar_steps']:
            result=polar.evaluate(model,val);metric=result['summary']['selection_loss']
            if metric<best:
                best,best_step=metric,step;checkpoint(model,out/'best_weights.pt',step,best,'robust_polar_same_observation')
            history.append(dict(step=step,train_loss=float(loss.detach()),validation=result['summary'],elapsed_s=time.monotonic()-start))
            base.write(out/'history.json',history)
            print(json.dumps(dict(event='POLAR_VALIDATION',step=step,best_step=best_step,validation=result['summary'])),flush=True)
    ck=torch.load(out/'best_weights.pt',weights_only=True);model.load_state_dict(ck['state_dict'])
    reports={'validation':polar.evaluate(model,val),'train':polar.evaluate(model,train_native)}
    for name,report in reports.items():
        for row in report['rows']:
            row['model_name']='robust_hub_polar_v1';row['unit']='psi';row['hub_checkpoint_sha256']=base.sha(hub_checkpoint)
            row['polar_checkpoint_sha256']=base.sha(out/'best_weights.pt');row['direction_display_independent_of_READ']=True
        base.write(out/(name+'_evaluation.json'),report)
        (out/(name+'_predictions.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in report['rows']),'utf-8')
    base.write(out/'receipt.json',dict(status='ROBUST_CHAIN_FLOAT_TRAINED_NO_MCU_OR_BOARD',completed_steps=PLAN['polar_steps'],best_step=best_step,
               elapsed_s=time.monotonic()-start,train_original_sources=164,augmented_train_views=820,angular_supervised_views=745,
               validation_images=59,parameters=1009,hub_parameters=1202,hub_checkpoint_sha256=base.sha(hub_checkpoint),
               polar_checkpoint_sha256=base.sha(out/'best_weights.pt'),train_features_sha256=base.sha(out/'train_features.npz'),
               validation=reports['validation']['summary'],H_or_ABC_opened=False,thresholds_changed=False,
               psi_pressure_is_model_input=False,integer_or_hardware_deployment=False))


def preflight():
    HERE.mkdir(parents=True,exist_ok=True);base.setup(PLAN['seed'],PLAN['threads']);tr,va=load_items()
    selected=[it for it in tr if it['id']in{'D_001','D_004','D_024','D_049','E_004','E_024','F_003','F_004','F_024'}]
    images=[];checks=0
    for it in selected:
        for view in range(3):
            image,heat,mask,points,meta=augmented_view(np.random.default_rng(1104+view),it)
            assert np.array_equal(mask,it['mask'])
            assert all(p is None or(0<=p[0]<=127 and 0<=p[1]<=127)for k,p in enumerate(points)if mask[k])
            assert heat.shape==(2,64,64)
            for k in range(2):
                if not mask[k]:assert not heat[k].any()
            canvas=cv2.cvtColor(image,cv2.COLOR_GRAY2BGR)
            for k,p in enumerate(points):
                if p is not None and mask[k]:cv2.circle(canvas,tuple(np.rint(p).astype(int)),3,(0,220,0),1)
            images.append((it['id']+f' view{view}',canvas));checks+=1
    visual=HERE/'preflight_visual';visual.mkdir(exist_ok=True)
    canvas=np.full((60+math.ceil(len(images)/4)*280,1024,3),245,np.uint8)
    cv2.putText(canvas,'TRAIN ONLY bounded light changes; green=source-visible points',(8,25),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,0,0),1)
    for i,(name,image)in enumerate(images):
        x,y=i%4*256,60+i//4*280;canvas[y:y+256,x:x+256]=cv2.resize(image,(256,256),interpolation=cv2.INTER_NEAREST)
        cv2.putText(canvas,name,(x+5,y+275),cv2.FONT_HERSHEY_SIMPLEX,.45,(0,0,0),1)
    cv2.imencode('.png',canvas)[1].tofile(str(visual/'bounded_train_augmentation.png'))
    hub=base.Direct(4);hub.load_state_dict(torch.load(HUB_WARM,weights_only=True)['state_dict'])
    example=make_polar_items(hub,selected,1,'preflight',None)
    for r in example:
        feature,_=polar.polar_features(r['image'],r['center'],r['record']['roi_request']['radius'])
        assert np.array_equal(feature,r['feature'])
    pmodel=polar.PolarNeedle();assert sum(p.numel()for p in hub.parameters())==1202 and sum(p.numel()for p in pmodel.parameters())==1009
    source={str(p):base.sha(p)for p in[Path(__file__),SOURCE/'train_grouped_v2.py',SOURCE/'roi_adapter.py',POINTER/'polar_angle/train_polar.py',
                                    SOURCE/'prepared_train.jsonl',SOURCE/'prepared_validation.jsonl',HUB_WARM,POLAR_WARM]}
    base.write(HERE/'preflight.json',dict(status='PASS_ROBUST_CHAIN_TOOL_PREFLIGHT_PENDING_REVIEW',PLAN=PLAN,source_sha256=source,
               sample_augmentation_checks=checks,same_view_center_feature_checks=len(example),mask_preserved=True,
               opaque_occlusion_generated=False,real_optimizer_steps=0,H_or_ABC_opened=False,
               selected_train_ids=[r['id']for r in selected],parameters=dict(hub=1202,polar=1009)))
    print(json.dumps(dict(status='PREFLIGHT_COMPLETE',checks=checks,source_sha256=source)),flush=True)


def run():
    out=HERE/'run_001';out.mkdir(exist_ok=False);base.setup(PLAN['seed'],PLAN['threads']);tr,va=load_items()
    base.write(out/'config.json',dict(PLAN=PLAN,trainer_sha256=base.sha(__file__),hub_warm_sha256=HUB_SHA,polar_warm_sha256=POLAR_SHA,
               source_sha256={str(p):base.sha(p)for p in[SOURCE/'prepared_train.jsonl',SOURCE/'prepared_validation.jsonl']},
               one_fixed_chain=True,G_development_only=True,H_or_ABC_opened=False,pressure_is_input=False,
               source_images_unchanged=True,no_threshold_relaxation=True))
    hub,_,_=train_hub(out/'hub',tr,va)
    train_polar(out/'polar',hub,tr,va,out/'hub/best_weights.pt')
    base.write(out/'completion.json',dict(status='COMPLETE_FLOAT_CHAIN_NOT_DEPLOYMENT',PLAN=PLAN,
               hub_receipt_sha256=base.sha(out/'hub/receipt.json'),polar_receipt_sha256=base.sha(out/'polar/receipt.json'),
               raw_axis_and_direction_for_all59_G=True,pressure_unit='psi',PSI_readout_requires_external_frozen_calibration=True,
               H_or_ABC_opened=False,hardware_actions=False))
    print(json.dumps(dict(event='CHAIN_COMPLETE',out=str(out))),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['preflight','train'],nargs='?',default='preflight');args=parser.parse_args()
    preflight()if args.mode=='preflight'else run()
