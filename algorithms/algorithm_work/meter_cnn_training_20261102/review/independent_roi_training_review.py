"""Independent pre-training audit. Opens only D/E/F and G native images."""
from pathlib import Path
import ast
import hashlib
import importlib.util
import json
import math

import cv2
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

HERE = Path(__file__).resolve().parent
TASK = HERE.parent
ROOT = TASK.parents[1]
PACK = ROOT / 'algorithm_work/meter_training_dataset_20261102'
HEADS = ('hub', 'thin_terminal')
EXPECTED_MANIFEST = 'e512850e54db6cc20c4b1973db9d48c852bf8737c3846a07afcb5cf9472c9872'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows(path):
    return [json.loads(line) for line in Path(path).read_text('utf-8-sig').splitlines() if line.strip()]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    checks = []
    def check(ok, name):
        checks.append(dict(name=name, passed=bool(ok)))
        if not ok:
            raise AssertionError(name)

    check(sha(PACK / 'dataset_manifest.json') == EXPECTED_MANIFEST, 'source_partition_manifest_frozen')
    adapter = module('audit_roi_adapter', TASK / 'roi_adapter.py')
    trainer = module('audit_trainer', TASK / 'train_grouped.py')
    all_prepared = []
    pixel_checks = coordinate_heads = 0
    max_roundtrip = 0.
    for split, groups, expected_count in [('train', {'D', 'E', 'F'}, 177), ('validation', {'G'}, 59)]:
        source = rows(PACK / split / 'labels.jsonl')
        prepared = rows(TASK / f'prepared_{split}.jsonl')
        cache = np.load(TASK / f'roi_cache_{split}.npz')
        check(len(prepared) == expected_count, split + '_count')
        check([r['id'] for r in prepared] == [r['id'] for r in source], split + '_source_order_unchanged')
        check(cache['ids'].tolist() == [r['id'] for r in prepared], split + '_cache_identity_order')
        for index, (orig, r) in enumerate(zip(source, prepared)):
            ident = r['id']
            check(r['split'] == split and r['source_group'] in groups, ident + '_split_isolation')
            for field in ('id', 'path', 'sha256', 'keypoints', 'pressure', 'bbox_native_xyxy', 'head_supervision', 'loss_mask'):
                check(r[field] == orig[field], ident + '_immutable_' + field)
            check(sha(r['path']) == r['sha256'], ident + '_native_sha')
            req = r['roi_request']
            x, y, s = [req[k] for k in ('x0', 'y0', 'stride')]
            check(s in (2, 3, 4) and x % 4 == 0 and 0 <= x <= 1280 - 128*s and 0 <= y <= 720 - 128*s, ident + '_hardware_window')
            check(not r['roi_ignored_heads'], ident + '_no_silent_coordinate_loss')
            check(r['roi_preprocessing']['actual_CSI_ROI_byte_equivalence_proven'] is False, ident + '_proxy_scope_honest')
            im = cv2.imdecode(np.frombuffer(Path(r['path']).read_bytes(), np.uint8), cv2.IMREAD_COLOR)
            check(im.shape == (720, 1280, 3), ident + '_native_dimensions')
            b, g, red = [im[:, :, c].astype(np.int64) for c in range(3)]
            gray = ((77*red + 150*g + 29*b + 128) // 256).astype(np.uint8)
            # Integral-image oracle is distinct from adapter's reshape/sum axes.
            integral = cv2.integral(gray, sdepth=cv2.CV_64F).astype(np.int64)
            xx = x + np.arange(128)*s
            yy = y + np.arange(128)*s
            sums = (integral[np.ix_(yy+s, xx+s)] - integral[np.ix_(yy, xx+s)]
                    - integral[np.ix_(yy+s, xx)] + integral[np.ix_(yy, xx)])
            expected = ((sums * 7282) // 65536 if s == 3 else sums // (s*s)).astype(np.uint8)
            actual = adapter.read_roi(r)
            check(np.array_equal(actual, expected) and np.array_equal(cache['images'][index], expected), ident + '_all_roi_pixels_independent_oracle')
            pixel_checks += actual.size
            heat, mask, points = adapter.build_targets(r)
            check(heat.shape == (2, 64, 64) and np.array_equal(mask, orig['loss_mask']) and np.array_equal(mask, cache['masks'][index]), ident + '_target_shapes_masks')
            for h, key in enumerate(HEADS):
                a = orig['keypoints'][key]
                p = a['xy']
                mapped = r['roi_keypoints'][key]['xy']
                if p is not None:
                    expected_p = (np.asarray(p, np.float64) - [x, y] - (s-1)/2) / s
                    check(np.allclose(mapped, expected_p, atol=1e-12), ident + '_' + key + '_forward_coordinate')
                    restored = np.asarray(mapped)*s + [x, y] + (s-1)/2
                    err = float(np.max(np.abs(restored - p)))
                    max_roundtrip = max(max_roundtrip, err)
                    check(err < 1e-10, ident + '_' + key + '_inverse_coordinate')
                    coordinate_heads += 1
                else:
                    check(mapped is None, ident + '_' + key + '_no_fabricated_point')
                if not mask[h]:
                    check(points[h] is None and not heat[h].any(), ident + '_' + key + '_ignored_head_zero_and_masked')
                elif orig['target_present']:
                    check(points[h] is not None and (np.asarray(points[h]) >= 0).all() and (np.asarray(points[h]) <= 127).all(), ident + '_' + key + '_supervised_point_in_roi')
                    py, px = np.unravel_index(heat[h].argmax(), heat[h].shape)
                    error = float(np.linalg.norm(np.array([px, py])*2 - points[h]))
                    check(heat[h, py, px] == 1 and error <= math.sqrt(2) + 1e-5, ident + '_' + key + '_heatmap_peak_alignment')
                else:
                    check(points[h] is None and not heat[h].any(), ident + '_' + key + '_true_negative_zero_target')
            all_prepared.extend([r])
    train = [r for r in all_prepared if r['split'] == 'train']
    val = [r for r in all_prepared if r['split'] == 'validation']
    check(sum(r['active_for_initial_weight_updates'] for r in train) == 164, 'initial_training_supervision_164')
    check(not {r['sha256'] for r in train} & {r['sha256'] for r in val}, 'train_validation_SHA_disjoint')
    # Compile only the historical architecture class; never import its data code.
    source_path = ROOT / 'algorithm_work/meter_mcu_live_roi_20261029/cnn/train_direct.py'
    parsed = ast.parse(source_path.read_text('utf-8-sig'))
    direct = next(node for node in parsed.body if isinstance(node, ast.ClassDef) and node.name == 'Direct')
    namespace = dict(nn=nn, F=F, torch=torch)
    exec(compile(ast.Module(body=[direct], type_ignores=[]), str(source_path), 'exec'), namespace)
    old, new = namespace['Direct'](4), trainer.Direct(4)
    check({k: tuple(v.shape) for k, v in old.state_dict().items()} == {k: tuple(v.shape) for k, v in new.state_dict().items()}, 'existing_MCU_architecture_parameter_shapes_equal')
    check(sum(p.numel() for p in new.parameters()) == 1202, 'parameter_count_1202')
    torch.set_num_threads(2)
    old.load_state_dict(new.state_dict())
    with torch.inference_mode():
        x = torch.randn(1, 1, 128, 128)
        check(torch.equal(old(x), new(x)), 'existing_architecture_forward_bit_equal_float')
    logits = torch.zeros((2, 2, 64, 64), requires_grad=True)
    target = torch.zeros_like(logits)
    target[0, 0, 21, 32] = 1
    trainer.masked_loss(logits, target, torch.tensor([[1., 0.], [1., 1.]])).backward()
    check(logits.grad[0, 1].count_nonzero() == 0, 'unknown_head_no_gradient')
    check(logits.grad[1].count_nonzero() > 0, 'true_negative_has_gradient')
    report = dict(status='PASS_TRAINING_ADMISSION_PROXY_ROI_ONLY', checks=len(checks), failures=[],
                  file_sha256={name: sha(TASK/name) for name in ('roi_adapter.py', 'train_grouped.py', 'prepared_train.jsonl', 'prepared_validation.jsonl')},
                  source_dataset_manifest_sha256=EXPECTED_MANIFEST,
                  actual_native_images_opened=236, roi_pixels_independently_compared=pixel_checks,
                  mapped_coordinate_heads_checked=coordinate_heads, maximum_inverse_native_error_px=max_roundtrip,
                  visually_inspected_contact_sheets=['train_contact_01.png', 'train_contact_05.png', 'validation_contact_05.png'],
                  visual_scope='35 raw/label ROI pairs; no obvious coordinate-system shift, no guarantee of full canonical label precision',
                  training_script_review='scratch C4; actual D/E/F only gradients; G inference_mode selection; no H/ABC inputs; bounded coupled augmentation; masked unknown heads',
                  test_H_pixels_or_labels_opened=False, real_training_started_by_reviewer=False, device_operations=False,
                  limitations=['Annotated bbox is locator proxy, not actual detector ROI', 'HDMI RGB reconstructed gray not proved equal to actual CSI ROI',
                               'Original OSD remains visible and can contaminate image-domain evaluation', 'Known label uncertainty remains; this is transformation alignment review, not gold-label certification',
                               'Network score/acceptance policy is proxy; integer conversion, calibration and board READ remain pending'])
    HERE.mkdir(exist_ok=True)
    (HERE/'roi_training_admission.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    (HERE/'independent_check_details.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
