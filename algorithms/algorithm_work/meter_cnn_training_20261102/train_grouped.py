"""Grouped fresh-capture C4/W8 training; default synthetic smoke, no device I/O.

The immutable D/E/F training and G validation assignments are external inputs.
H test and A/B/C reserve are never opened by this trainer.  Real training is an
explicit `train` command after ROI alignment review, not an import side effect.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import math
import platform
import random
import sys
import time

import cv2
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

HERE = Path(__file__).resolve().parent
HEADS = ("hub", "thin_terminal")
SEED = 1102
DATASET_MANIFEST_SHA256 = "e512850e54db6cc20c4b1973db9d48c852bf8737c3846a07afcb5cf9472c9872"
Y, X = np.mgrid[:64, :64].astype(np.float32)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class Direct(nn.Module):
    """Exact C4 architecture/layer names used by the existing MCU math contract.

    This is a local copy of the architecture definition only.  No historical
    dataset, checkpoint, reference module, or weights are imported.
    """
    def __init__(self, c=4):
        super().__init__()
        self.first = nn.Conv2d(1, c, 5, 2, 2)
        self.local = nn.Sequential(nn.Conv2d(c, c, 5, 1, 2, groups=c), nn.ReLU(), nn.Conv2d(c, c, 1), nn.ReLU())
        self.downs = nn.ModuleList()
        cin = c
        for _ in range(3):
            self.downs.append(nn.Sequential(nn.Conv2d(cin, cin, 5, 2, 2, groups=cin), nn.ReLU(), nn.Conv2d(cin, 8, 1), nn.ReLU()))
            cin = 8
        self.context = nn.Sequential(nn.Conv2d(8, 8, 5, 1, 2, groups=8), nn.ReLU())
        self.fuse = nn.Conv2d(c + 8, c, 1)
        self.head = nn.Conv2d(c, 2, 1)
        nn.init.constant_(self.head.bias, -4.59511985)

    def forward(self, x):
        first = self.local(F.relu(self.first(x)))
        x = first
        for block in self.downs:
            x = block(x)
        x = self.context(x)
        x = F.relu(self.fuse(torch.cat([first, F.interpolate(x, size=(64, 64), mode="nearest")], 1)))
        return self.head(x)


def masked_loss(logits, target, mask):
    p = logits.sigmoid().clamp(1e-5, 1 - 1e-5)
    m = mask[:, :, None, None]
    pos = target.eq(1)
    neg = target.lt(1)
    numer = (-p.log() * (1 - p) ** 2 * pos - (1 - p).log() * p ** 2 * (1 - target) ** 4 * neg) * m
    return numer.sum() / (pos * m).sum().clamp(min=1)


def get_adapter():
    spec = importlib.util.spec_from_file_location("fresh_grouped_roi_adapter", HERE / "roi_adapter.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def normalized(im):
    return (im.astype(np.float32) - 128)[None] / 128


def heat_from_points(points, sigmas, mask):
    heat = np.zeros((2, 64, 64), np.float32)
    for k, point in enumerate(points):
        if not mask[k] or point is None:
            continue
        px, py = np.asarray(point, np.float32) / 2
        sigma = sigmas[k]
        heat[k] = np.exp(-((X - px) ** 2 + (Y - py) ** 2) / (2 * sigma ** 2))
        # The 127/2=63.5 coordinate is legal: only the discrete peak index is
        # bounded to 63.  The continuous point itself is never clamped.
        heat[k, min(63, max(0, int(round(float(py))))), min(63, max(0, int(round(float(px)))))] = 1
    return heat


def build_items(records, adapter, allowed_groups, expected_split):
    items = []
    for r in records:
        group = r.get("source_group", r["id"].split("_")[0])
        if group not in allowed_groups or r.get("split") != expected_split:
            raise ValueError(f"Wrong split/group in {r['id']}: {expected_split}/{allowed_groups}")
        im = adapter.read_roi(r)
        if im.shape != (128, 128) or im.dtype != np.uint8:
            raise ValueError(f"Invalid canonical ROI for {r['id']}")
        heat, mask, points = adapter.build_targets(r)
        mask = np.asarray(mask, np.float32)
        points = [None if p is None else np.asarray(p, np.float32).tolist() for p in points]
        stride = int(r["roi_request"]["stride"])
        sigmas = []
        for key in HEADS:
            uncertainty = r.get("keypoints", {}).get(key, {}).get("uncertainty_px")
            # Native keypoint uncertainty stays the reference.  A heatmap target
            # should not be narrower than ~1.25 heat pixels for this tiny net.
            sigmas.append(max(1.25, float(uncertainty or 0) / stride / 2))
        items.append(dict(record=r, id=r["id"], image=im, heat=np.asarray(heat, np.float32), mask=mask,
                          points=points, sigmas=sigmas, stride=stride, target_present=bool(r["target_present"])))
    return items


def augment(rng, item):
    """Train-only photometric and coupled affine augmentation, no label guessing."""
    points = item["points"]
    # Reject transformations that push a supervised visible point out of the
    # input; do not turn an out-of-crop positive into a zero/negative target.
    matrix = np.array([[1., 0., 0.], [0., 1., 0.]], np.float64)
    transformed = points
    for _ in range(12):
        m = cv2.getRotationMatrix2D((63.5, 63.5), float(rng.uniform(-8, 8)), float(rng.uniform(.96, 1.04)))
        m[:, 2] += rng.uniform(-2, 2, 2)
        trial = [None if p is None else (np.r_[p, 1] @ m.T).tolist() for p in points]
        valid = all(p is None or not item["mask"][k] or (np.asarray(p) >= 0).all() and (np.asarray(p) <= 127).all()
                    for k, p in enumerate(trial))
        if valid:
            matrix, transformed = m, trial
            break
    im = cv2.warpAffine(item["image"], matrix, (128, 128), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101).astype(np.float32)
    im = (im - 96) * rng.uniform(.8, 1.2) + 96 + rng.uniform(-12, 12)
    if rng.random() < .25:
        im += rng.normal(0, rng.uniform(0, 2), im.shape)
    im = np.clip(np.rint(im), 0, 255).astype(np.uint8)
    heat = heat_from_points(transformed, item["sigmas"], item["mask"])
    return normalized(im), heat, item["mask"]


def decode(logits):
    prob = 1 / (1 + np.exp(-np.clip(logits, -40, 40)))
    points, peaks, margins = [], [], []
    for v in prob:
        y, x = np.unravel_index(v.argmax(), v.shape)
        ya, xa = np.mgrid[max(0, y - 1):min(64, y + 2), max(0, x - 1):min(64, x + 2)]
        weights = v[ya, xa]
        denom = max(float(weights.sum()), 1e-12)
        points.append([float((weights * xa).sum() / denom) * 2, float((weights * ya).sum() / denom) * 2])
        peaks.append(float(v[y, x]))
        far = v.copy()
        far[(X - x) ** 2 + (Y - y) ** 2 <= 25] = 0
        margins.append(float(v[y, x] - far.max()))
    return np.asarray(points), peaks, margins


def angle(points):
    return math.degrees(math.atan2(points[1][1] - points[0][1], points[1][0] - points[0][0])) % 360


def angular(a, b):
    return abs((a - b + 180) % 360 - 180)


def stats(values):
    if not values:
        return dict(n=0, mean=None, median=None, p90=None)
    return dict(n=len(values), mean=float(np.mean(values)), median=float(np.median(values)), p90=float(np.percentile(values, 90)))


def evaluate(model, items, device, overlays=None):
    model.eval()
    rows, numer, denominator = [], 0., 0.
    with torch.inference_mode():
        for start in range(0, len(items), 16):
            batch = items[start:start + 16]
            x = torch.from_numpy(np.stack([normalized(it["image"]) for it in batch])).to(device)
            target = torch.from_numpy(np.stack([it["heat"] for it in batch])).to(device)
            mask = torch.from_numpy(np.stack([it["mask"] for it in batch])).to(device)
            logits = model(x)
            # Aggregate batch loss by the same focal numerator/positive count.
            den = float((target.eq(1) * mask[:, :, None, None]).sum().clamp(min=1))
            numer += float(masked_loss(logits, target, mask)) * den
            denominator += den
            values = logits.cpu().numpy()
            for it, output in zip(batch, values):
                pred, peaks, margins = decode(output)
                length = float(np.linalg.norm(pred[1] - pred[0]))
                center = float(np.linalg.norm(pred[0] - 63.5))
                accepted = min(peaks) >= .3 and min(margins) >= .02 and 18 <= length <= 65 and center <= 20
                r = dict(id=it["id"], split=it["record"]["split"], source_group=it["record"].get("source_group"),
                         target_present=it["target_present"], mask=it["mask"].tolist(), predicted_points_roi=pred.tolist(),
                         target_points_roi=it["points"], peaks=peaks, margins=margins, evidence_accepted=bool(accepted),
                         angle_deg=angle(pred), endpoint_length_roi=length, hub_center_distance_roi=center)
                for k, key in enumerate(HEADS):
                    if it["mask"][k] and it["points"][k] is not None:
                        error = float(np.linalg.norm(pred[k] - it["points"][k]))
                        r[key + "_error_roi"] = error
                        r[key + "_error_native"] = error * it["stride"]
                if all(it["mask"]) and all(p is not None for p in it["points"]):
                    r["reference_angle_deg"] = angle(it["points"])
                    r["angle_error_deg"] = angular(r["angle_deg"], r["reference_angle_deg"])
                rows.append(r)
                if overlays is not None:
                    canvas = cv2.cvtColor(it["image"], cv2.COLOR_GRAY2BGR)
                    for k, point in enumerate(it["points"]):
                        if point is not None and it["mask"][k]:
                            cv2.circle(canvas, tuple(np.rint(point).astype(int)), 4, (0, 220, 0), 1)
                    for k, point in enumerate(pred):
                        cv2.circle(canvas, tuple(np.rint(point).astype(int)), 3, (0, 255, 255) if k == 0 else (255, 0, 255), 1)
                    cv2.line(canvas, tuple(np.rint(pred[0]).astype(int)), tuple(np.rint(pred[1]).astype(int)), (255, 128, 0), 1)
                    cv2.imencode(".png", cv2.resize(canvas, (384, 384), interpolation=cv2.INTER_NEAREST))[1].tofile(str(overlays / (it["id"] + ".png")))
    full = [r for r in rows if "angle_error_deg" in r]
    accepted = [r for r in full if r["evidence_accepted"]]
    negatives = [r for r in rows if not r["target_present"]]
    summary = dict(images=len(items), validation_or_training_loss=numer / max(denominator, 1),
                   hub_error_roi=stats([r["hub_error_roi"] for r in rows if "hub_error_roi" in r]),
                   thin_terminal_error_roi=stats([r["thin_terminal_error_roi"] for r in rows if "thin_terminal_error_roi" in r]),
                   hub_error_native=stats([r["hub_error_native"] for r in rows if "hub_error_native" in r]),
                   thin_terminal_error_native=stats([r["thin_terminal_error_native"] for r in rows if "thin_terminal_error_native" in r]),
                   angle_error_deg=stats([r["angle_error_deg"] for r in full]),
                   bounded_full_point_count=len(full), both_points_within_4roi=sum(r["hub_error_roi"] <= 4 and r["thin_terminal_error_roi"] <= 4 for r in full),
                   within_5deg=sum(r["angle_error_deg"] <= 5 for r in full), within_10deg=sum(r["angle_error_deg"] <= 10 for r in full),
                   approximately_180deg_wrong_direction=sum(r["angle_error_deg"] >= 150 for r in full),
                   evidence_accepted_full_points=len(accepted), evidence_coverage=len(accepted) / len(full) if full else None,
                   accepted_angle_error_deg=stats([r["angle_error_deg"] for r in accepted]),
                   accepted_over_10deg=sum(r["angle_error_deg"] > 10 for r in accepted),
                   negative_count=len(negatives), negative_evidence_false_accepts=sum(r["evidence_accepted"] for r in negatives),
                   fixed_evidence_policy=dict(min_sigmoid_peak=.3, min_peak_margin=.02, endpoint_length_roi=[18, 65], max_hub_center_distance_roi=20),
                   pressure_error_computed=False, end_to_end_READ_or_FAR_claim=False)
    return dict(summary=summary, rows=rows)


def resource_estimate(model):
    layers, handles = [], []
    def hook(name):
        def calculate(module, args, output):
            mac = output.numel() * (module.in_channels // module.groups) * module.kernel_size[0] * module.kernel_size[1]
            layers.append(dict(name=name, weight_shape=list(module.weight.shape), activation_shape=list(output.shape), conv_MAC=mac,
                               int8_activation_bytes=output.numel(), int8_weight_bytes=module.weight.numel(), int32_bias_bytes=module.bias.numel() * 4))
        return calculate
    for name, module in model.named_modules():
        if isinstance(module, nn.Conv2d):
            handles.append(module.register_forward_hook(hook(name)))
    with torch.no_grad():
        model(torch.zeros(1, 1, 128, 128))
    for h in handles:
        h.remove()
    return dict(parameters=sum(p.numel() for p in model.parameters()), layers=layers,
                conv_MAC=sum(v["conv_MAC"] for v in layers), int8_weights_plus_int32_bias_bytes=sum(v["int8_weight_bytes"] + v["int32_bias_bytes"] for v in layers),
                largest_int8_activation_bytes=max(v["int8_activation_bytes"] for v in layers),
                two_largest_buffer_estimate_bytes=2 * max(v["int8_activation_bytes"] for v in layers),
                estimate_only_not_linker_memory_layout=True, FPGA_Slice_change_measured=False,
                integer_conversion_status="PENDING; architecture unchanged does not prove trained quantized accuracy")


def setup(seed, threads):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(threads)
    cv2.setNumThreads(1)
    torch.use_deterministic_algorithms(True)


def smoke(out, threads):
    out.mkdir(parents=True, exist_ok=True)
    setup(SEED, threads)
    model = Direct(4)
    assert sum(p.numel() for p in model.parameters()) == 1202
    logits = torch.zeros((2, 2, 64, 64), requires_grad=True)
    target = torch.zeros_like(logits)
    target[0, 0, 30, 31] = 1
    mask = torch.tensor([[1., 0.], [1., 1.]])
    masked_loss(logits, target, mask).backward()
    assert not logits.grad[0, 1].count_nonzero()
    assert logits.grad[1].count_nonzero()
    # Unknown heads have no target gradient.  A true negative head does.
    rng = np.random.default_rng(SEED)
    item = dict(image=np.full((128, 128), 128, np.uint8), points=[[63.5, 63.5], [127., 127.]],
                sigmas=[1.25, 1.25], mask=np.ones(2, np.float32))
    for _ in range(50):
        x, heat, m = augment(rng, item)
        assert x.shape == (1, 128, 128) and heat.shape == (2, 64, 64) and (heat.max((1, 2)) == 1).all()
    x = torch.randn(12, 1, 128, 128)
    y = torch.zeros(12, 2, 64, 64)
    y[:, :, 32, 32] = 1
    masks = torch.ones(12, 2)
    optimizer = torch.optim.Adam(model.parameters(), lr=.003)
    start = time.monotonic()
    for _ in range(25):
        optimizer.zero_grad(set_to_none=True)
        output = model(x)
        assert output.shape == (12, 2, 64, 64)
        loss = masked_loss(output, y, masks)
        loss.backward()
        optimizer.step()
    elapsed = time.monotonic() - start
    report = dict(status="PASS_SYNTHETIC_SMOKE_ONLY", real_images_opened=0, real_training_started=False,
                  synthetic_optimizer_steps=25, mask_unknown_gradient_zero=True, true_negative_gradient_nonzero=True,
                  border_point_continuous_coordinates_not_clamped=True, parameters=1202, threads=threads,
                  synthetic_seconds_per_step=elapsed / 25, estimated_2400_optimizer_seconds=elapsed / 25 * 2400,
                  torch_version=torch.__version__, resource_estimate=resource_estimate(model))
    write(out / "trainer_smoke.json", report)
    print(json.dumps(report, ensure_ascii=False), flush=True)


def checkpoint(model, step, config, score):
    return dict(channels=4, state_dict={k: v.detach().cpu() for k, v in model.state_dict().items()},
                architecture="encoder_local_skip_upright_v4", parameters=1202, training_steps=step,
                initialization="scratch", dataset_manifest_sha256=config["dataset_manifest_sha256"],
                prepared_train_sha256=config["prepared_train_sha256"], prepared_validation_sha256=config["prepared_validation_sha256"],
                validation_selection_loss=score, seed=config["seed"])


def train(args):
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    adapter = get_adapter()
    setup(args.seed, args.threads)
    if sha(HERE.parent / "meter_training_dataset_20261102/dataset_manifest.json") != DATASET_MANIFEST_SHA256:
        raise ValueError("Grouped source dataset manifest changed since signed partition review")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    records_train = adapter.load_prepared(args.train)
    records_val = adapter.load_prepared(args.validation)
    records_train = [r for r in records_train if r.get("active_for_initial_weight_updates")]
    if len(records_train) != 164 or len(records_val) != 59:
        raise ValueError(f"Expected signed first-round 164 train/59 validation, got {len(records_train)}/{len(records_val)}")
    train_items = build_items(records_train, adapter, {"D", "E", "F"}, "train")
    val_items = build_items(records_val, adapter, {"G"}, "validation")
    if {it["id"] for it in train_items} & {it["id"] for it in val_items}:
        raise ValueError("Train/validation overlap")
    if {it["record"]["sha256"] for it in train_items} & {it["record"]["sha256"] for it in val_items}:
        raise ValueError("Train/validation source SHA overlap")
    model = Direct(4)
    config = dict(schema="grouped_fresh_c4_training_v1", seed=args.seed, device=str(device), threads=args.threads,
                  steps=args.steps, batch_size=args.batch, eval_every=args.eval_every, initialization="scratch",
                  architecture="encoder_local_skip_upright_v4", train_groups=["D", "E", "F"], validation_groups=["G"],
                  train_ids=[it["id"] for it in train_items], validation_ids=[it["id"] for it in val_items],
                  prepared_train_sha256=sha(args.train), prepared_validation_sha256=sha(args.validation),
                  dataset_manifest_sha256=sha(HERE.parent / "meter_training_dataset_20261102/dataset_manifest.json"),
                  trainer_sha256=sha(__file__), roi_adapter_sha256=sha(HERE / "roi_adapter.py"),
                  selection_metric="minimum G validation masked focal loss; no H access",
                  optimizer="Adam lr=.003 cosine->.00015", augmentation="train-only affine +/-8deg .96..1.04 scale +/-2ROIpx; gain .8..1.2 bias +/-12; light noise",
                  labels="masked hub/thin-terminal visual keypoints; pressure not a training target",
                  predeclared_metrics=dict(all_supervised_heads="ROI and native endpoint mean/median/p90 without confidence filtering",
                                           full_point_metrics="all full labels: angle mean/median/p90, <=5deg, <=10deg, >=150deg wrong-direction count",
                                           confidence_policy="fixed legacy .3 peak, .02 margin, 18..65ROI needle length, <=20ROI hub-center distance",
                                           false_accept_proxy="accepted full labels over10deg plus accepted true-negative crops; not end-to-end FAR",
                                           unknown_positive_coordinates="predictions only, never counted correct or negative",
                                           validation_negative_denominator=3),
                  negative_semantics="only target_present=false is a true zero-heatmap negative",
                  test_H_pixels_or_labels_opened=False, reserve_ABC_pixels_opened=False, hardware_actions=False,
                  resource_estimate=resource_estimate(model), python=platform.python_version(), torch=torch.__version__)
    write(out / "training_config.json", config)
    model = model.to(device)
    start = time.monotonic()
    baseline = evaluate(model, val_items, device)
    write(out / "untrained_validation_baseline.json", baseline)
    optimizer = torch.optim.Adam(model.parameters(), lr=.003)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.steps, eta_min=.00015)
    best_loss = float("inf")
    best_step = 0
    rng = np.random.default_rng(args.seed)
    history = []
    train_loss_window = []
    print(json.dumps(dict(event="TRAIN_STARTED", train_images=len(train_items), validation_images=len(val_items), device=str(device), steps=args.steps)), flush=True)
    for step in range(1, args.steps + 1):
        model.train()
        picks = [train_items[int(rng.integers(len(train_items)))] for _ in range(args.batch)]
        batch = [augment(rng, item) for item in picks]
        x = torch.from_numpy(np.stack([b[0] for b in batch])).to(device)
        y = torch.from_numpy(np.stack([b[1] for b in batch])).to(device)
        masks = torch.from_numpy(np.stack([b[2] for b in batch])).to(device)
        optimizer.zero_grad(set_to_none=True)
        loss = masked_loss(model(x), y, masks)
        if not torch.isfinite(loss):
            raise RuntimeError(f"Nonfinite loss at step{step}")
        loss.backward()
        optimizer.step()
        scheduler.step()
        train_loss_window.append(float(loss.detach()))
        if step % 50 == 0:
            print(json.dumps(dict(event="STEP", step=step, train_loss_mean=float(np.mean(train_loss_window[-50:])), elapsed_s=time.monotonic() - start)), flush=True)
        if step % args.eval_every == 0 or step == args.steps:
            result = evaluate(model, val_items, device)
            score = result["summary"]["validation_or_training_loss"]
            entry = dict(step=step, train_loss_mean=float(np.mean(train_loss_window)), validation=result["summary"], elapsed_s=time.monotonic() - start)
            train_loss_window.clear()
            history.append(entry)
            write(out / "history.json", history)
            if score < best_loss:
                best_loss, best_step = score, step
                torch.save(checkpoint(model, step, config, score), out / "best_weights.pt")
                write(out / "best_validation_during_training.json", result)
            torch.save(checkpoint(model, step, config, score), out / "last_weights.pt")
            write(out / "progress.json", dict(status="TRAINING", step=step, planned_steps=args.steps, best_step=best_step,
                                               best_validation_loss=best_loss, elapsed_s=time.monotonic() - start))
            print(json.dumps(dict(event="VALIDATION", step=step, best_step=best_step, validation=result["summary"]), ensure_ascii=False), flush=True)
    best = torch.load(out / "best_weights.pt", weights_only=True, map_location=device)
    model.load_state_dict(best["state_dict"])
    model.eval()
    overlays = out / "validation_overlays"
    overlays.mkdir()
    final_val = evaluate(model, val_items, device, overlays)
    final_train = evaluate(model, train_items, device)
    write(out / "validation_evaluation.json", final_val)
    write(out / "train_evaluation.json", final_train)
    write(out / "training_receipt.json", dict(status="FLOAT_TRAINED_G_VALIDATED_H_UNOPENED_INTEGER_PENDING", best_step=best_step,
          completed_steps=args.steps, elapsed_s=time.monotonic() - start, config_sha256=sha(out / "training_config.json"),
          best_checkpoint_sha256=sha(out / "best_weights.pt"), last_checkpoint_sha256=sha(out / "last_weights.pt"),
          validation_baseline=baseline["summary"], validation_best=final_val["summary"], train_best=final_train["summary"],
          test_H_pixels_or_labels_opened=False, reserve_ABC_pixels_opened=False, source_images_modified=False,
          integer_quantization_or_MCU_deployment=False, pressure_accuracy_claim=False, final_READ_acceptance=False))
    write(out / "progress.json", dict(status="COMPLETE_FLOAT_ONLY", completed_steps=args.steps, best_step=best_step))
    print(json.dumps(dict(event="TRAIN_COMPLETE", out=str(out), best_step=best_step, elapsed_s=time.monotonic() - start)), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", nargs="?", choices=["smoke", "train"], default="smoke")
    parser.add_argument("--train", type=Path, default=HERE / "prepared_train.jsonl")
    parser.add_argument("--validation", type=Path, default=HERE / "prepared_validation.jsonl")
    parser.add_argument("--out", type=Path, default=HERE / "trainer_smoke")
    parser.add_argument("--steps", type=int, default=2400)
    parser.add_argument("--batch", type=int, default=12)
    parser.add_argument("--eval-every", type=int, default=200)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    if args.mode == "smoke":
        smoke(args.out, args.threads)
    else:
        train(args)


if __name__ == "__main__":
    main()
