"""Candidate A: training-only weak-line auxiliary evidence + tip hard negatives.

Default preflight.  One explicitly requested, fixed 2400-step warm-start run.
Inference is the original 1202-parameter, two-heatmap Direct(4) network.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import math
import sys
import time
import cv2
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

HERE = Path(__file__).resolve().parent
WORK = HERE.parents[1]
SOURCE = WORK / 'meter_cnn_training_20261102'
sys.path.insert(0, str(SOURCE))
import train_grouped_v2 as base

WARM = SOURCE / 'run_002/best_weights.pt'
WARM_SHA = 'c221678efa4762bed298828b2e8e8ba3c2a6b343c2c16efe35aec77a85c896df'
PLAN = dict(steps=2400, batch=12, seed=1102, threads=4, learning_rate=.0008, final_learning_rate=.00008,
            evaluate_every=200, weak_line_weight=.5, hard_negative_weight=.2, hard_negative_k=16,
            weak_line_t=[.20, .95], weak_line_supervision_t=[.15, 1.], weak_line_sigma_heat=1.,
            hard_negative_exclusion='max(3 heat pixels,3*sigma_heat,uncertainty_native/(2*stride)+1); target<.05',
            selection='minimum unchanged G masked focal loss', inference_parameters=1202, training_only_aux_parameters=5)


class Auxiliary(nn.Module):
    def __init__(self):
        super().__init__()
        self.base = base.Direct(4)
        self.line_head = nn.Conv2d(4, 1, 1)
        nn.init.normal_(self.line_head.weight, std=.01)
        nn.init.constant_(self.line_head.bias, -2.2)

    def forward(self, x):
        m = self.base
        local = m.local(F.relu(m.first(x)))
        encoded = local
        for block in m.downs:
            encoded = block(encoded)
        context = m.context(encoded)
        feature = F.relu(m.fuse(torch.cat([local, F.interpolate(context, (64, 64), mode='nearest')], 1)))
        return m.head(feature), self.line_head(feature)


def eligible(item):
    r = item['record']
    tags = ' '.join(map(str, r['scene'].get('observed_tags', []))).lower()
    reason = 'bounded clear-front both-point weak direction support'
    ok = bool(r['split'] == 'train' and r['source_group'] in {'D', 'E', 'F'} and r['target_present']
              and r['scene']['primary'] in {'front_medium_soft_light', 'front_large_soft_light'}
              and all(item['mask']) and all(p is not None for p in item['points'])
              and not any(w in tags for w in ['occlu', '遮挡', 'glare', 'reflect', '反光', 'blur', '模糊', 'dark', 'dim']))
    if not ok:
        reason = 'aux ignored: not bounded, explicitly clear front with both visible endpoints'
    return ok, reason


def line_target(points, allowed):
    target, mask = np.zeros((64, 64), np.float32), np.zeros((64, 64), np.float32)
    if not allowed:
        return target, mask
    h, t = np.asarray(points, np.float64) / 2
    v = t - h
    length2 = float(v @ v)
    if length2 < 4:
        return target, mask
    along = ((base.X - h[0]) * v[0] + (base.Y - h[1]) * v[1]) / length2
    distance = np.abs((base.X - h[0]) * v[1] - (base.Y - h[1]) * v[0]) / math.sqrt(length2)
    support = (along >= PLAN['weak_line_t'][0]) & (along <= PLAN['weak_line_t'][1])
    target = np.exp(-(distance ** 2) / (2 * PLAN['weak_line_sigma_heat'] ** 2)) * support
    mask = ((along >= PLAN['weak_line_supervision_t'][0]) & (along <= PLAN['weak_line_supervision_t'][1]) & (distance <= 4.)).astype(np.float32)
    return target.astype(np.float32), mask


def augment(rng, item):
    # Same augmentation and RNG order as the frozen v2; expose transformed points
    # only so weak-line and hard-negative targets share the image transformation.
    points = item['points']
    matrix = np.array([[1., 0., 0.], [0., 1., 0.]], np.float64)
    transformed = points
    for _ in range(12):
        m = cv2.getRotationMatrix2D((63.5, 63.5), float(rng.uniform(-8, 8)), float(rng.uniform(.96, 1.04)))
        m[:, 2] += rng.uniform(-2, 2, 2)
        trial = [None if p is None else (np.r_[p, 1] @ m.T).tolist() for p in points]
        valid = all(p is None or not item['mask'][k] or (np.asarray(p) >= 0).all() and (np.asarray(p) <= 127).all()
                    for k, p in enumerate(trial))
        if valid:
            matrix, transformed = m, trial
            break
    im = cv2.warpAffine(item['image'], matrix, (128, 128), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101).astype(np.float32)
    im = (im - 96) * rng.uniform(.8, 1.2) + 96 + rng.uniform(-12, 12)
    if rng.random() < .25:
        im += rng.normal(0, rng.uniform(0, 2), im.shape)
    im = np.clip(np.rint(im), 0, 255).astype(np.uint8)
    heat = base.heat_from_points(transformed, item['sigmas'], item['mask'])
    line, line_mask = line_target(transformed, eligible(item)[0])
    tip_mask = np.zeros((64, 64), bool)
    if item['mask'][1]:
        if not item['target_present']:
            tip_mask[:] = True
        elif transformed[1] is not None:
            x, y = np.asarray(transformed[1]) / 2
            uncertainty = item['record']['keypoints']['thin_terminal']['uncertainty_px'] / (2 * item['stride'])
            radius = max(3., 3 * item['sigmas'][1], uncertainty + 1)
            tip_mask = ((base.X - x) ** 2 + (base.Y - y) ** 2 > radius ** 2) & (heat[1] < .05)
    return base.normalized(im), heat, item['mask'], line, line_mask, tip_mask, transformed


def losses(keypoints, line_logits, target, head_mask, line_target_, line_mask, negative_mask):
    main = base.masked_loss(keypoints, target, head_mask)
    weak = (F.binary_cross_entropy_with_logits(line_logits[:, 0], line_target_, reduction='none') * line_mask * (1 + 4 * line_target_)).sum() / line_mask.sum().clamp(min=1)
    penalties = []
    for z, valid in zip(keypoints[:, 1], negative_mask):
        if valid.any():
            penalties.append(F.softplus(torch.topk(z[valid], min(PLAN['hard_negative_k'], int(valid.sum()))).values).mean())
    hard = torch.stack(penalties).mean() if penalties else keypoints.sum() * 0
    return main + PLAN['weak_line_weight'] * weak + PLAN['hard_negative_weight'] * hard, main, weak, hard


def items_and_sources():
    adapter = base.get_adapter()
    train = [r for r in adapter.load_prepared(SOURCE / 'prepared_train.jsonl') if r['active_for_initial_weight_updates']]
    val = adapter.load_prepared(SOURCE / 'prepared_validation.jsonl')
    if len(train) != 164 or len(val) != 59:
        raise ValueError('Signed 164/59 dataset count changed')
    if base.sha(WARM) != WARM_SHA:
        raise ValueError('Warm-start checkpoint changed')
    return base.build_items(train, adapter, {'D', 'E', 'F'}, 'train'), base.build_items(val, adapter, {'G'}, 'validation')


def save_checkpoint(model, step, score, config, path):
    torch.save(dict(channels=4, state_dict={k: v.detach().cpu() for k, v in model.base.state_dict().items()},
                    architecture='encoder_local_skip_upright_v4', parameters=1202, training_only_aux_removed=True,
                    initialization='warm_start_run002_new_dataset_only', warm_checkpoint_sha256=WARM_SHA,
                    training_steps=step, validation_selection_loss=score, config_sha256=base.sha(config)), path)


def preflight():
    HERE.mkdir(parents=True, exist_ok=True)
    base.setup(PLAN['seed'], PLAN['threads'])
    train, val = items_and_sources()
    model = Auxiliary()
    model.base.load_state_dict(torch.load(WARM, weights_only=True)['state_dict'])
    inputs = torch.from_numpy(np.stack([base.normalized(it['image']) for it in train[::8]]))
    with torch.no_grad():
        first, line = model(inputs)
        assert torch.equal(first, model.base(inputs))
    weak_ids = [it['id'] for it in train if eligible(it)[0]]
    # Verify ordinary augmented images/endpoint targets did not change.
    for it in train[::8]:
        x = base.augment(np.random.default_rng(1102), it)
        y = augment(np.random.default_rng(1102), it)
        assert all(np.array_equal(a, b) for a, b in zip(x, y[:3]))
        if not eligible(it)[0]:
            assert not y[4].any()
        if not it['mask'][1]:
            assert not y[5].any()
    # One combined-loss backward, no optimizer update, validates gradient paths.
    example = [augment(np.random.default_rng(1102 + i), train[i]) for i in range(12)]
    values = [torch.from_numpy(np.stack([b[k] for b in example])) for k in range(6)]
    keypoints, line = model(values[0])
    loss, main, weak, hard = losses(keypoints, line, *values[1:])
    loss.backward()
    assert torch.isfinite(loss)
    assert model.base.fuse.weight.grad.count_nonzero()
    assert model.line_head.weight.grad.count_nonzero()
    # Qualifying samples only: visualize the derived weak direction tube.  This
    # is explicitly not a manually segmented pixel-perfect needle annotation.
    visual = HERE / 'aux_label_review'
    visual.mkdir(exist_ok=True)
    sheets = []
    qualified = [it for it in train if eligible(it)[0]]
    for start in range(0, len(qualified), 16):
        page = qualified[start:start + 16]
        canvas = np.full((60 + math.ceil(len(page) / 4) * 280, 1024, 3), 245, np.uint8)
        cv2.putText(canvas, 'TRAIN ONLY: derived weak line support, not true segmentation', (10, 25), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 0, 0), 1)
        for i, it in enumerate(page):
            im = cv2.cvtColor(it['image'], cv2.COLOR_GRAY2BGR)
            h, t = np.asarray(it['points'])
            cv2.line(im, tuple(np.rint(h + .2 * (t - h)).astype(int)), tuple(np.rint(h + .95 * (t - h)).astype(int)), (0, 255, 0), 1)
            x, y = (i % 4) * 256, 60 + (i // 4) * 280
            canvas[y:y + 256, x:x + 256] = cv2.resize(im, (256, 256), interpolation=cv2.INTER_NEAREST)
            cv2.putText(canvas, it['id'], (x + 8, y + 273), cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 0, 0), 1)
        name = f'aux_labels_{start // 16 + 1:02d}.png'
        cv2.imencode('.png', canvas)[1].tofile(str(visual / name))
        sheets.append(name)
    result = dict(status='PASS_AUXILIARY_TOOL_PREFLIGHT_PENDING_INDEPENDENT_REVIEW', plan=PLAN,
                  file_sha256={str(p): base.sha(p) for p in [Path(__file__), SOURCE / 'train_grouped_v2.py', SOURCE / 'roi_adapter.py', SOURCE / 'prepared_train.jsonl', SOURCE / 'prepared_validation.jsonl', WARM]},
                  train_count=len(train), validation_count=len(val), weak_line_eligible_count=len(weak_ids), weak_line_ids=weak_ids,
                  inference_parameters=sum(p.numel() for p in model.base.parameters()), training_parameters=sum(p.numel() for p in model.parameters()),
                  training_aux_only_parameters=sum(p.numel() for p in model.line_head.parameters()), auxiliary_vs_base_forward_bitexact=True,
                  unchanged_augmentation_actual_records=len(train[::8]), no_aux_on_unknown_or_noneligible=True,
                  finite_combined_loss=float(loss.detach()), focal=float(main.detach()), weak_line=float(weak.detach()), hard_negative=float(hard.detach()),
                  real_optimizer_steps=0, test_H_or_ABC_opened=False, device_operations=False, aux_label_contact_sheets=sheets,
                  weak_line_semantics='Derived direction evidence only; no challenge/side/unknown/occluded full line labels; noneligible masks zero (ignored), not negative')
    base.write(HERE / 'preflight.json', result)
    print(json.dumps(result, ensure_ascii=False), flush=True)


def train():
    out = HERE / 'run_A'
    out.mkdir(exist_ok=False)
    base.setup(PLAN['seed'], PLAN['threads'])
    train_items, val_items = items_and_sources()
    model = Auxiliary()
    model.base.load_state_dict(torch.load(WARM, weights_only=True)['state_dict'])
    config = dict(candidate='A', plan=PLAN, trainer_sha256=base.sha(__file__), base_trainer_sha256=base.sha(SOURCE / 'train_grouped_v2.py'),
                  source_sha256={str(p): base.sha(p) for p in [SOURCE / 'prepared_train.jsonl', SOURCE / 'prepared_validation.jsonl', WARM]},
                  train_ids=[it['id'] for it in train_items], validation_ids=[it['id'] for it in val_items],
                  weak_line_ids=[it['id'] for it in train_items if eligible(it)[0]],
                  head_loss='unchanged masked focal; unknown heads ignored; true no-gauge negative zero heatmaps',
                  line_semantics='Weak line from bounded clear-front two-point labels, not true pixel segmentation',
                  hard_negative_semantics='Train predictions only; uncertainty and >=3sigma exclusion; no G error mining',
                  preprocessing='same fixed prepared native-HDMI proxy ROI as run002; not actual CSI gray equivalence',
                  pressure_is_training_target=False, test_H_or_ABC_opened=False, inference_parameter_change=0,
                  actual_integer_or_MCU_cost_measured=False, resource=base.resource_estimate(model.base))
    config_path = out / 'training_config.json'
    base.write(config_path, config)
    baseline = base.evaluate(model.base, val_items, torch.device('cpu'))
    base.write(out / 'warm_start_validation_baseline.json', baseline)
    optimizer = torch.optim.Adam(model.parameters(), lr=PLAN['learning_rate'])
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, PLAN['steps'], eta_min=PLAN['final_learning_rate'])
    rng = np.random.default_rng(PLAN['seed'])
    best_score, best_step = float('inf'), 0
    history, window = [], []
    started = time.monotonic()
    print(json.dumps(dict(event='TRAIN_STARTED', candidate='A', plan=PLAN)), flush=True)
    for step in range(1, PLAN['steps'] + 1):
        model.train()
        picks = [train_items[int(rng.integers(len(train_items)))] for _ in range(PLAN['batch'])]
        examples = [augment(rng, it) for it in picks]
        tensors = [torch.from_numpy(np.stack([b[k] for b in examples])) for k in range(6)]
        optimizer.zero_grad(set_to_none=True)
        logits, line_logits = model(tensors[0])
        loss, focal, weak, hard = losses(logits, line_logits, *tensors[1:])
        if not torch.isfinite(loss):
            raise RuntimeError('Nonfinite candidate loss')
        loss.backward()
        optimizer.step()
        scheduler.step()
        window.append([float(z.detach()) for z in [loss, focal, weak, hard]])
        if step % 100 == 0:
            print(json.dumps(dict(event='STEP', step=step, loss_components=np.mean(window[-100:], axis=0).tolist(), elapsed_s=time.monotonic() - started)), flush=True)
        if step % PLAN['evaluate_every'] == 0 or step == PLAN['steps']:
            evaluation = base.evaluate(model.base, val_items, torch.device('cpu'))
            score = evaluation['summary']['validation_or_training_loss']
            history.append(dict(step=step, mean_loss_components=np.mean(window, axis=0).tolist(), validation=evaluation['summary'], elapsed_s=time.monotonic() - started))
            window.clear()
            if score < best_score:
                best_score, best_step = score, step
                save_checkpoint(model, step, score, config_path, out / 'best_weights.pt')
                torch.save(dict(aux_state_dict=model.line_head.state_dict(), base_state_dict=model.base.state_dict(), step=step), out / 'best_training_aux_state.pt')
                base.write(out / 'best_validation_during_training.json', evaluation)
            save_checkpoint(model, step, score, config_path, out / 'last_weights.pt')
            base.write(out / 'history.json', history)
            base.write(out / 'progress.json', dict(status='TRAINING', step=step, best_step=best_step, best_loss=best_score))
            print(json.dumps(dict(event='VALIDATION', step=step, best_step=best_step, validation=evaluation['summary'])), flush=True)
    selected = torch.load(out / 'best_weights.pt', weights_only=True)
    model.base.load_state_dict(selected['state_dict'])
    overlays = out / 'validation_overlays'
    overlays.mkdir()
    val_result = base.evaluate(model.base, val_items, torch.device('cpu'), overlays)
    train_result = base.evaluate(model.base, train_items, torch.device('cpu'))
    base.write(out / 'validation_evaluation.json', val_result)
    base.write(out / 'train_evaluation.json', train_result)
    base.write(out / 'training_receipt.json', dict(status='CANDIDATE_A_FLOAT_TRAINED_NOT_BOARD_ACCEPTANCE', completed_steps=PLAN['steps'], best_step=best_step,
               elapsed_s=time.monotonic() - started, config_sha256=base.sha(config_path), trainer_sha256=base.sha(__file__), warm_checkpoint_sha256=WARM_SHA,
               best_checkpoint_sha256=base.sha(out / 'best_weights.pt'), validation_before=baseline['summary'], validation_best=val_result['summary'], train_best=train_result['summary'],
               inference_parameters=1202, training_aux_removed=True, test_H_or_ABC_opened=False, new_data_capture=False,
               real_bar_accuracy_computed=False, integer_or_MCU_deployment=False, hardware_actions=False))
    base.write(out / 'progress.json', dict(status='COMPLETE_FLOAT_ONLY', completed_steps=PLAN['steps'], best_step=best_step))
    print(json.dumps(dict(event='TRAIN_COMPLETE', out=str(out), best_step=best_step, elapsed_s=time.monotonic() - started)), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['preflight', 'train'], nargs='?', default='preflight')
    args = parser.parse_args()
    preflight() if args.mode == 'preflight' else train()
