"""Grouped native-PNG to hardware-shaped 128x128 ROI adapter; no training.

The native images are HDMI captures with OSD. Annotated face boxes are a
locator proxy, not the boxes returned by the actual FPGA detector. Only the
block-mean and coordinate arithmetic are hardware matched. Never opens H.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import math
from collections import Counter
import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PACK = ROOT / 'algorithm_work/meter_training_dataset_20261102'
MANIFEST_SHA = 'e512850e54db6cc20c4b1973db9d48c852bf8737c3846a07afcb5cf9472c9872'
HEADS = ['hub', 'thin_terminal']
HW = Path('C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_reader_flash20e_20261101/project/user_source/hdl_source/meter_pair')
OSD_REGIONS = [('mode_logo', [32, 15, 292, 181]), ('diagnostics_upper_right', [704, 40, 1240, 211])]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_jsonl(path):
    return [json.loads(x) for x in Path(path).read_text('utf-8-sig').splitlines() if x.strip()]


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def load_prepared(path):
    records = read_jsonl(path)
    assert all(r['split'] in ['train', 'validation'] for r in records)
    assert not any(r['source_group'] == 'H' for r in records)
    return records


def window_policy(box):
    """Integer arithmetic of actual meter_roi_window_policy, bbox proxy input."""
    x0, y0, x1, y1 = map(int, box)
    diameter = max(x1 - x0, y1 - y0)
    stride = 2 if diameter <= 236 else 3 if diameter <= 372 else 4
    span = 128 * stride
    x = min(max(((x0 + x1 - span) // 8) * 4, 0), 1280 - span)
    y = min(max((y0 + y1 - span) // 2, 0), 720 - span)
    radius = min(62, (diameter + stride) // (2 * stride))
    image_contains = 0 <= x0 <= x1 <= 1280 and 0 <= y0 <= y1 <= 720
    crop_contains = x0 >= x and y0 >= y and x1 <= x + span and y1 <= y + span
    available = diameter >= 160 and 40 <= radius <= 62
    return dict(x0=x, y0=y, stride=stride, radius=radius, span=span,
                proxy_diameter=diameter, hardware_policy_available=available,
                hardware_policy_analysis_only=diameter > 499 or not image_contains or not crop_contains,
                policy='EXACT_WINDOW_POLICY_WITH_ANNOTATED_BBOX_PROXY')


def native_to_roi(point, req):
    s = int(req['stride'])
    return (np.asarray(point, np.float64) - [req['x0'], req['y0']] - (s - 1) / 2) / s


def roi_to_native(point, req):
    s = int(req['stride'])
    return np.asarray(point, np.float64) * s + [req['x0'], req['y0']] + (s - 1) / 2


def overlap(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def prepare_record(record, negative_box=None):
    r = copy.deepcopy(record)
    if r['split'] not in ['train', 'validation'] or r['source_group'] == 'H':
        raise ValueError('Only train and validation may be prepared')
    if r['target_present']:
        box = r['bbox_native_xyxy']
        crop_origin = 'annotated_face_bbox_proxy_not_actual_detector'
    else:
        # Session median is derived from face BOXES only, not pressure/keypoints.
        # This is a plausible false-locator window; it is not an object annotation.
        box = negative_box if negative_box is not None else [448, 168, 832, 552]
        crop_origin = 'same_session_median_face_box_negative_window_proxy'
    req = window_policy(box)
    r['roi_request'] = req
    r['roi_keypoints'] = {}
    r['loss_mask_source'] = list(r['loss_mask'])
    r['roi_ignored_heads'] = []
    for i, key in enumerate(HEADS):
        a = r['keypoints'][key]
        p = native_to_roi(a['xy'], req) if a.get('xy') is not None else None
        inside = p is not None and bool(((p >= 0) & (p <= 127)).all())
        r['roi_keypoints'][key] = dict(xy=p.tolist() if p is not None else None,
            visibility=a['visibility'], source_uncertainty_native_px=a.get('uncertainty_px'),
            uncertainty_roi_px=(float(a['uncertainty_px']) / req['stride']) if a.get('uncertainty_px') is not None else None,
            inside_roi=inside)
        if r['loss_mask'][i] and r['head_supervision'][key]['target'] == 'visible_point_heatmap' and not inside:
            r['loss_mask'][i] = 0
            r['roi_ignored_heads'].append(dict(head=key, reason='VISIBLE_SUPERVISED_POINT_OUTSIDE_HARDWARE_WINDOW_NOT_CLAMPED'))
    r['active_for_initial_weight_updates'] = bool(r['active_for_initial_weight_updates'] and any(r['loss_mask']))
    crop = [req['x0'], req['y0'], req['x0'] + req['span'], req['y0'] + req['span']]
    r['roi_preprocessing'] = dict(status='HARDWARE_SHAPED_PROXY_ROI_PREPARED',
        input_pixels='ORIGINAL_NATIVE_PNG_NOT_ANNOTATION_PREVIEW', crop_origin=crop_origin,
        roi_shape=[128, 128], head_order=HEADS, heatmap_shape=[2, 64, 64],
        native_to_roi='(native-origin-(stride-1)/2)/stride', roi_to_heatmap='roi/2',
        blockmean='s2:sum>>2; s3:(sum*7282)>>16; s4:sum>>4',
        grayscale='(77*R+150*G+29*B+128)>>8 from captured HDMI RGB',
        actual_CSI_ROI_byte_equivalence_proven=False,
        reason='HDMI source includes ISP/OSD; native RGB reconstruction is not an actual CSI gray dump',
        OSD_overlap_regions=[name for name, rect in OSD_REGIONS if overlap(crop, rect)],
        OSD_not_removed_or_used_as_label=True, coordinates_clamped=False,
        network_target_is_pressure=False, TEST_calibration_range_unchanged=True)
    return r


def read_native(record):
    p = Path(record['path'])
    im = cv2.imdecode(np.frombuffer(p.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    if im is None or im.shape != (720, 1280, 3):
        raise ValueError(f'{record["id"]}: expected native 1280x720 BGR')
    return im


def gray_from_bgr(im):
    b, g, r = [im[:, :, i].astype(np.uint32) for i in range(3)]
    return ((77 * r + 150 * g + 29 * b + 128) >> 8).astype(np.uint8)


def blockmean(gray, req):
    s, x, y = [int(req[k]) for k in ['stride', 'x0', 'y0']]
    if s not in [1, 2, 3, 4] or x % 4 or not (0 <= x <= 1280 - 128*s and 0 <= y <= 720 - 128*s):
        raise ValueError('Unsupported or incomplete hardware ROI')
    sums = gray[y:y+128*s, x:x+128*s].astype(np.uint32).reshape(128, s, 128, s).sum((1, 3))
    q = (sums * 7282) >> 16 if s == 3 else sums >> {1: 0, 2: 2, 4: 4}[s]
    return np.ascontiguousarray(q.astype(np.uint8))


def read_roi(record):
    return blockmean(gray_from_bgr(read_native(record)), record['roi_request'])


def build_targets(record):
    yy, xx = np.mgrid[:64, :64]
    heat = np.zeros((2, 64, 64), np.float32)
    mask = np.array(record['loss_mask'], np.float32)
    points = []
    for i, key in enumerate(HEADS):
        a = record['roi_keypoints'][key]
        mode = record['head_supervision'][key]['target']
        p = a['xy'] if mask[i] and mode == 'visible_point_heatmap' else None
        if p is not None:
            p = np.asarray(p, np.float64)
            if not (((p >= 0) & (p <= 127)).all()):
                raise ValueError('Supervised point outside ROI; never clamp')
            cx, cy = p / 2
            sig = max(1.25, float(a['uncertainty_roi_px']) / 2)
            heat[i] = np.exp(-((xx-cx)**2 + (yy-cy)**2)/(2*sig*sig))
            heat[i, min(63, int(round(cy))), min(63, int(round(cx)))] = 1.0
        elif mask[i] and mode != 'zero_heatmap':
            raise ValueError('Only known absent heads may use zero heatmap')
        points.append(p.tolist() if p is not None else None)
    return heat, mask, points


def save_image(path, im):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    ok, b = cv2.imencode('.png', im)
    if not ok:
        raise ValueError('PNG encode failed')
    Path(path).write_bytes(b.tobytes())


def overlay_tile(record, gray):
    raw = cv2.resize(gray, (256, 256), interpolation=cv2.INTER_NEAREST)
    overlay = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
    for i, key in enumerate(HEADS):
        a = record['roi_keypoints'][key]
        if a['xy'] is not None and a['inside_roi']:
            xy = tuple(np.rint(np.asarray(a['xy'])*2).astype(int))
            color = (0, 255, 0) if i == 0 else (0, 0, 255)
            if record['loss_mask'][i]:
                cv2.drawMarker(overlay, xy, color, cv2.MARKER_CROSS, 13, 1)
            else:
                cv2.circle(overlay, xy, 5, (128, 128, 128), 1)
    panel = np.full((288, 512, 3), 24, np.uint8)
    panel[:256, :256] = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
    panel[:256, 256:] = overlay
    caption = f'{record["id"]} s{record["roi_request"]["stride"]} masks{record["loss_mask"]} raw | labels'
    cv2.putText(panel, caption, (5, 277), cv2.FONT_HERSHEY_SIMPLEX, .43, (230, 230, 230), 1)
    return panel


def check_math():
    checks = 0
    rng = np.random.default_rng(20261102)
    max_error = 0.0
    for s in [1, 2, 3, 4]:
        req = dict(x0=128, y0=64, stride=s)
        points = rng.uniform(0, 127, (257, 2))
        restored = native_to_roi(roi_to_native(points, req), req)
        max_error = max(max_error, float(abs(restored-points).max()))
        checks += len(points)
        gray = rng.integers(0, 256, (720, 1280), dtype=np.uint8)
        got = blockmean(gray, req)
        # Separate nested-pixel oracle; supports every stride accepted by capture.
        expected = np.zeros((128, 128), np.uint8)
        for y in range(128):
            for x in range(128):
                v = sum(int(gray[64+y*s+dy, 128+x*s+dx]) for dy in range(s) for dx in range(s))
                expected[y, x] = (v*7282 >> 16) if s == 3 else v >> {1:0, 2:2, 4:4}[s]
        assert np.array_equal(got, expected)
        checks += 16384
    assert max_error < 1e-12
    return dict(roundtrip_points=1028, blockmean_pixel_checks=65536, maximum_roundtrip_error_px=max_error,
                status='PASS', independent_algorithm='explicit nested-pixel sum oracle, not reshape')


def build():
    assert sha(PACK/'dataset_manifest.json') == MANIFEST_SHA
    out = HERE/'alignment'
    out.mkdir(parents=True, exist_ok=True)
    stats = {}
    for split in ['train', 'validation']:
        records = read_jsonl(PACK/split/'labels.jsonl')
        assert all(r['split'] == split and r['source_group'] in ('DEF' if split == 'train' else 'G') for r in records)
        medians = {}
        for group in sorted({r['source_group'] for r in records}):
            boxes = [r['bbox_native_xyxy'] for r in records if r['source_group'] == group and r['target_present'] and 160 <= max(r['bbox_native_xyxy'][2]-r['bbox_native_xyxy'][0], r['bbox_native_xyxy'][3]-r['bbox_native_xyxy'][1]) <= 499]
            medians[group] = np.rint(np.median(boxes, axis=0)).astype(int).tolist()
        prepared = [prepare_record(r, medians[r['source_group']]) for r in records]
        (HERE/f'prepared_{split}.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in prepared), 'utf-8')
        rois, masks, points_out = [], [], []
        tiles = []
        max_roundtrip = 0.
        for r in prepared:
            assert sha(r['path']) == r['sha256'], r['id']
            g = read_roi(r)
            heat, mask, pts = build_targets(r)
            assert g.shape == (128, 128) and g.dtype == np.uint8 and heat.shape == (2, 64, 64)
            rois.append(g); masks.append(mask); points_out.append([p if p is not None else [np.nan,np.nan] for p in pts])
            for key in HEADS:
                p = r['roi_keypoints'][key]['xy']
                if p is not None:
                    max_roundtrip = max(max_roundtrip, float(abs(roi_to_native(p,r['roi_request'])-r['keypoints'][key]['xy']).max()))
            tile = overlay_tile(r, g)
            save_image(out/'individual'/f'{r["id"]}_raw_and_labels.png', tile)
            tiles.append(tile)
        np.savez_compressed(HERE/f'roi_cache_{split}.npz', images=np.stack(rois), masks=np.stack(masks), points=np.asarray(points_out,np.float32), ids=np.asarray([r['id']for r in prepared]))
        for page in range(math.ceil(len(tiles)/12)):
            sheet = np.full((288*4, 512*3, 3), 12, np.uint8)
            for i,tile in enumerate(tiles[page*12:(page+1)*12]):
                row,col=divmod(i,3);sheet[row*288:(row+1)*288,col*512:(col+1)*512]=tile
            save_image(out/f'{split}_contact_{page+1:02d}.png',sheet)
        stats[split] = dict(records=len(prepared), active_for_initial_weight_updates=sum(r['active_for_initial_weight_updates'] for r in prepared),
            stride_counts=dict(Counter(r['roi_request']['stride']for r in prepared)),
            available_proxy_policy=sum(r['roi_request']['hardware_policy_available']for r in prepared),
            analysis_only_proxy=sum(r['roi_request']['hardware_policy_analysis_only']for r in prepared),
            OSD_overlap_count=sum(bool(r['roi_preprocessing']['OSD_overlap_regions'])for r in prepared),
            outside_supervised_heads=[dict(id=r['id'],heads=r['roi_ignored_heads'])for r in prepared if r['roi_ignored_heads']],
            maximum_native_roundtrip_error_px=max_roundtrip,
            prepared_sha256=sha(HERE/f'prepared_{split}.jsonl'), cache_sha256=sha(HERE/f'roi_cache_{split}.npz'))
    contract = dict(schema='meter_native_roi_adapter_v1', source_manifest_sha256=MANIFEST_SHA,
        source_artifacts=[dict(path=str(HW/n), sha256=sha(HW/n))for n in ['meter_roi_window_policy.v','t06_meter_roi_capture_mcu.v']],
        capture_accepts_strides=[1,2,3,4], current_parent_policy_selects_strides=[2,3,4],
        gray_reconstruction='U8=(77R+150G+29B+128)>>8',
        blockmean='U8 sum shifted; stride3 hardware reciprocal multiply7282 then >>16',
        coordinates='roi=(native-origin-(stride-1)/2)/stride; heatmap=roi/2; inverse=native=roi*stride+origin+(stride-1)/2',
        keypoint_source='Direct visual coordinates from immutable canonical annotation; pressure not used',
        negative_crop_policy='Same-session median positive face BOX, no keypoint or pressure use. A plausible false-locator window, no guarantee object centered.',
        masks='Honor original per-head mask; visible supervised out-of-window head ignored explicitly, never clamped or converted negative',
        labels_unchanged=True, raw_sources_unchanged=True, bbox_proxy_not_actual_auto_locator=True,
        no_board_capture_equivalence_claim=True, supervised_point_selection_does_not_control_crop=True,
        hardware_policy_available_does_not_gate_training=True,
        OSD='Retained original native HDMI OSD, overlap approximate rectangles logged; no overlay preview input. Label contamination requires visual review.',
        train_augmentation_recommendation='Bounded translation/scale perturbations with joint coordinate transform; never derive crop from thin tip. Validation no random jitter.',
        validation_role='G development only; H not opened/prepared/scored', training_executed=False)
    write_json(HERE/'roi_contract.json', contract)
    report = dict(status='PASS_NUMERICAL_ALIGNMENT_VISUAL_REVIEW_PENDING', math_checks=check_math(), partitions=stats,
        roi_adapter_sha256=sha(__file__), roi_contract_sha256=sha(HERE/'roi_contract.json'),
        test_images_opened=0, test_labels_opened=False, training_executed=False,
        caveat='Numerical transform validation does not certify original manual annotation precision or actual automatic locator boxes')
    write_json(out/'alignment_report.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=['build','check'],nargs='?',default='check');args=ap.parse_args()
    if args.command=='build':build()
    else:print(json.dumps(check_math(),indent=2))
