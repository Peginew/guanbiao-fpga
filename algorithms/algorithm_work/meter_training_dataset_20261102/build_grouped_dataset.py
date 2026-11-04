"""Organize native gauge data by capture group. Contains no training code."""
from pathlib import Path
from collections import Counter, defaultdict
import argparse
import copy
import csv
import hashlib
import json

HERE = Path(__file__).resolve().parent
ANNOTATIONS = HERE.parent / 'meter_dataset_annotation_20261102' / 'annotations.json'
EXPECTED_SOURCE_SHA = 'cb977f2b8f1b1324993982f9947314ae9a130c055cdcf90f65b5081d4ad22b7e'
GROUP_SPLITS = {**dict.fromkeys('ABC', 'reserve'), **dict.fromkeys('DEF', 'train'), 'G': 'validation', 'H': 'test'}
MAX_UNCERTAINTY_PX = 8
HEADS = ['hub', 'thin_terminal']
SCENES_ZH = {
    'front_medium_soft_light': '正面、中尺寸、柔光',
    'front_large_soft_light': '正面、大尺寸、柔光',
    'front_dim': '正面、偏暗',
    'backlight_or_local_reflection': '逆光或局部反光',
    'mild_left_view': '轻微左侧取景',
    'mild_right_view': '轻微右侧取景',
}
ISSUES_ZH = {
    'very_large': '过近或画面过大', 'frame_clipped': '盘面不完整入画',
    'defocused': '失焦或模糊', 'very_small': '画面过小',
    'severe_specular_overexposure': '严重反光或过曝', 'physical_occlusion': '工具遮挡',
    'partial_or_oversized': '过近、过大或裁切',
    'small_or_severe_lighting': '过小或强光挑战，细类尚未精确确认',
    'hub_occluded': '机械轴心被遮挡', 'thin_terminal_occluded': '细针端被遮挡',
    'too_close_out_of_focus_and_clipped': '过近、失焦且盘面裁切',
    'small_and_soft': '过远、画面小且模糊',
    'strong_exposure_but_pointer_visible': '强光但仍有可见指针证据',
    'severe_saturation': '严重过曝', 'tool_occludes_mechanical_hub': '工具遮挡轴心',
    'tool_occludes_thin_terminal': '工具遮挡细针端',
    'tool_overlaps_thin_pointer_terminal_region': '工具覆盖细针端区域',
    'low_contrast_or_unresolved_terminal': '低对比或细针端无法确认',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')


def head_policy(r, key):
    p = r['keypoints'][key]
    if not r['target_present']:
        assert p['visibility'] == 'absent' and p.get('xy') is None
        return {'loss_mask': 1, 'target': 'zero_heatmap', 'reason': 'known_no_visible_gauge_face'}
    uncertainty = p.get('uncertainty_px')
    usable = p['visibility'] == 'visible' and p.get('xy') is not None and uncertainty is not None and uncertainty <= MAX_UNCERTAINTY_PX
    return {'loss_mask': int(usable), 'target': 'visible_point_heatmap' if usable else 'ignore',
            'reason': 'visible_bounded_annotation' if usable else
            'coarse_coordinate_exceeds_initial_gate' if p['visibility'] == 'visible' else 'visibility_' + p['visibility']}


def convert(r):
    group = r['group']
    split = GROUP_SPLITS[group]
    policies = {k: head_policy(r, k) for k in HEADS}
    mask = [policies[k]['loss_mask'] for k in HEADS]
    if not r['target_present']:
        role = 'negative_no_gauge'
    elif mask == [1, 1]:
        role = 'full_keypoints'
    elif mask == [1, 0]:
        role = 'hub_only'
    elif mask == [0, 1]:
        role = 'thin_terminal_only'
    else:
        role = 'positive_no_keypoint_supervision'
    observed = r.get('condition') or []
    if isinstance(observed, str):
        observed = [observed]
    planned = r.get('capture_condition_planned')
    issue_text = [ISSUES_ZH[x] for x in observed if x in ISSUES_ZH]
    if not r['target_present']:
        empty = r.get('negative_kind') in ('empty_scene', 'no_gauge_background')
        scene_key = 'empty_background' if empty else 'non_gauge_circular_or_reflective_object'
        scene_text = '无正面表盘的背景' if empty else '圆形或反光物体反例，无可见正面表盘'
        scene_source = 'visual_annotation_broad_class_not_exact_object_identity'
    elif planned:
        scene_key, scene_text, scene_source = planned, SCENES_ZH[planned], 'capture_plan_order_reconciled_with_supplements'
    else:
        scene_key = 'challenge_with_gauge'
        scene_text = '；'.join(issue_text) or '有表挑战图，具体画质问题待细分'
        scene_source = 'visual_annotation_may_have_broad_issue_category'
    pressure = copy.deepcopy(r['pressure'])
    description = scene_text
    if r['target_present']:
        description += f"；装置示数{pressure['value']} psi；轴心{r['keypoints']['hub']['visibility']}，细针端{r['keypoints']['thin_terminal']['visibility']}"
    active = split == 'train' and any(mask)
    rec = {
        'id': r['id'], 'session_id': 'new_capture_' + group, 'source_group': group, 'split': split,
        'path': r['path'], 'filename': r['filename'], 'sha256': r['sha256'],
        'input_kind': 'native_hdmi_png_1280x720_with_original_OSD', 'width': 1280, 'height': 720,
        'target_class': 'gauge_face' if r['target_present'] else 'no_visible_gauge_face',
        'target_present': r['target_present'], 'negative_kind_observed': r.get('negative_kind'),
        'bbox_native_xyxy': r.get('bbox_native_xyxy'), 'bbox_coordinate_convention': r['bbox_coordinate_convention'],
        'keypoints': copy.deepcopy(r['keypoints']), 'label_coordinates': 'native',
        'label_method': r['label_method'], 'review_status': r['review_status'],
        'coordinate_precision_tier': r['coordinate_precision_tier'], 'head_supervision': policies,
        'loss_mask': mask, 'supervision_role': role, 'active_for_initial_weight_updates': active,
        'usable_keypoint_or_negative_supervision': bool(any(mask)),
        'pressure': pressure, 'pressure_rank_descending': r.get('pressure_rank_descending'),
        'pressure_is_direct_network_regression_target': False,
        'capture_condition_slot': r.get('condition_slot'),
        'scene': {'primary': scene_key, 'description_zh': scene_text, 'source': scene_source,
                  'planned_condition': planned, 'observed_tags': observed, 'measured_pose_or_illumination': False},
        'content_description_zh': description,
        'capture_setup': {'scene_repositioned_between_groups': r.get('independent_reposition'),
                          'manual_focus_setting_unchanged': r.get('manual_focus_setting_unchanged'),
                          'pressure_basically_stable': r.get('pressure_stable_within_capture_group')},
        'original_OSD_is_not_label_truth': True,
        'roi_preprocessing': {'status': 'NOT_PREPROCESSED', 'coordinate_transform_required': True,
                              'auto_locator_ROI_not_assumed': True},
        'annotation_provenance': {'canonical_path': str(ANNOTATIONS), 'canonical_sha256': EXPECTED_SOURCE_SHA,
                                  'canonical_id': r['id'], 'human_certified_gold': False},
    }
    if split == 'reserve':
        rec['reserve_policy'] = {'allowed_future_split': 'train', 'initial_weight_updates': False,
                                 'reason': 'capture_group_preserved_while_ABC_coarse_coordinates_are_refined'}
    return rec


def build():
    assert sha(ANNOTATIONS) == EXPECTED_SOURCE_SHA, 'Canonical annotations changed: explicit dataset revision required.'
    canonical = json.loads(ANNOTATIONS.read_text(encoding='utf-8'))
    records = [convert(r) for r in canonical['records']]
    buckets = {s: [r for r in records if r['split'] == s] for s in ('train', 'validation', 'test', 'reserve')}
    for split, rows in buckets.items():
        folder = HERE / split
        if split == 'test':
            write_rows(folder / 'labels_for_final_evaluation.jsonl', rows)
            sealed = folder / 'labels_for_final_evaluation.jsonl'
            index = [{k: r[k] for k in ('id', 'session_id', 'source_group', 'split', 'path', 'filename', 'sha256', 'input_kind', 'width', 'height')} for r in rows]
            for r in index:
                r.update(labels_path=str(sealed), labels_sha256=sha(sealed), evaluation_use='prospectively_reserved_after_annotation_QA')
            write_rows(folder / 'index.jsonl', index)
        else:
            write_rows(folder / 'labels.jsonl', rows)
        fields = ['id', 'source_group', 'split', 'filename', 'path', 'sha256']
        with (folder / 'images.csv').open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fields); writer.writeheader()
            writer.writerows({k: r[k] for k in fields} for r in rows)
    train = buckets['train']
    active = [r for r in train if r['active_for_initial_weight_updates']]
    quality_only = [r for r in train if not r['active_for_initial_weight_updates']]
    clear = [r for r in active if r['supervision_role'] == 'negative_no_gauge' or
             r['scene']['planned_condition'] in ('front_medium_soft_light', 'front_large_soft_light') and r['supervision_role'] == 'full_keypoints']
    write_rows(HERE / 'train/initial_supervision.jsonl', active)
    write_rows(HERE / 'train/front_clear_initial.jsonl', clear)
    write_rows(HERE / 'train/quality_review_only.jsonl', quality_only)
    write_rows(HERE / 'train/negative_samples.jsonl', [r for r in active if r['supervision_role'] == 'negative_no_gauge'])
    write_rows(HERE / 'train/partial_keypoints.jsonl', [r for r in active if r['supervision_role'] in ('hub_only', 'thin_terminal_only')])
    write_rows(HERE / 'train/full_keypoints.jsonl', [r for r in active if r['supervision_role'] == 'full_keypoints'])
    stats = {}
    for split, rows in buckets.items():
        stats[split] = {'images': len(rows), 'groups': sorted({r['source_group'] for r in rows}),
                        'roles': dict(Counter(r['supervision_role'] for r in rows)),
                        'pressure_psi_distribution_gauge_only': dict(Counter(str(r['pressure']['value']) for r in rows if r['target_present'])),
                        'scene_distribution': dict(Counter(r['scene']['primary'] for r in rows)),
                        'true_negative_count': sum(not r['target_present'] for r in rows),
                        'all_user_capture_setup_confirmed': all(r['capture_setup']['scene_repositioned_between_groups'] is True and r['capture_setup']['manual_focus_setting_unchanged'] is True for r in rows)}
    stats.update(total_images=len(records), first_round_training_images=len(active), front_clear_curriculum_images=len(clear),
                 training_performed=False, model_evaluation_performed=False, original_images_modified=False)
    write_json(HERE / 'split_summary.json', stats)
    files = {str(p.relative_to(HERE)): sha(p) for p in HERE.glob('*/*.jsonl') if p.parent.name in buckets}
    manifest = {
        'schema': 'meter_grouped_keypoint_dataset_v1', 'dataset_id': 'new_native_meter_20261102_grouped_v1',
        'canonical_annotations': str(ANNOTATIONS), 'canonical_annotations_sha256': EXPECTED_SOURCE_SHA,
        'group_to_split': GROUP_SPLITS, 'source_images': 'Original native PNG files referenced by absolute path',
        'split_strategy': 'Whole capture groups; quality chosen without CNN model scores; no random per-image split',
        'initial_supervision_uncertainty_gate_native_px': MAX_UNCERTAINTY_PX,
        'uncertainty_gate_is_engineering_policy_not_certified_error_bound': True,
        'head_order': HEADS, 'pressure_units': 'psi', 'pressure_is_direct_network_target': False,
        'partitions': {s: {'groups': stats[s]['groups'], 'images': stats[s]['images'],
                           'index_or_labels': str(HERE / s / ('index.jsonl' if s == 'test' else 'labels.jsonl'))} for s in buckets},
        'first_round_training_manifest': str(HERE / 'train/initial_supervision.jsonl'),
        'front_clear_optional_curriculum_manifest': str(HERE / 'train/front_clear_initial.jsonl'),
        'validation_manifest': str(HERE / 'validation/labels.jsonl'),
        'test_input_index': str(HERE / 'test/index.jsonl'),
        'training_weight_update_inputs': ['train/initial_supervision.jsonl'],
        'validation_model_selection_inputs': ['validation/labels.jsonl'],
        'test_was_viewed_for_annotation_QA': True, 'test_model_selection_use_after_split': 'prohibited',
        'test_is_unseen_human_certified_gold': False,
        'augmentation': {'generated': False, 'allowed_split': 'train', 'inherit_source_session_and_split': True,
                         'joint_image_and_point_transform_required': True, 'no_default_large_rotation_or_mirror': True},
        'preprocessing': {'status': 'ROI_ADAPTER_PENDING', 'expected_model_input': '128x128 gray U8 ROI',
                          'native_to_ROI_keypoint_transform_required': True, 'not_old_trainer_drop_in_schema': True,
                          'original_OSD_overlap_needs_ROI_review': True, 'normalization_statistics_source': 'train_only_if_estimated'},
        'reserve': {'allowed_future_use': 'training_only_after_label_refinement', 'contains_groups': ['A', 'B', 'C']},
        'training_performed': False, 'model_evaluation_performed': False, 'board_operations': False,
        'files_sha256': files,
    }
    write_json(HERE / 'dataset_manifest.json', manifest)
    write_json(HERE / 'label_dictionary.json', {
        'target_classes': ['gauge_face', 'no_visible_gauge_face'], 'network_heads': HEADS,
        'supervision_roles': ['full_keypoints', 'hub_only', 'thin_terminal_only', 'negative_no_gauge', 'positive_no_keypoint_supervision'],
        'loss_targets': {'visible_point_heatmap': 'Real visible mechanical point with accepted uncertainty',
                         'zero_heatmap': 'Known no visible gauge; valid negative supervision',
                         'ignore': 'Occluded, unknown, or coarse point; NOT a negative'},
        'scene_labels': {'planned': SCENES_ZH, 'negative': ['empty_background', 'non_gauge_circular_or_reflective_object'],
                         'challenge': 'Visual issue tags retain source uncertainty; not measured yaw/lux/focus'},
        'coordinates': 'Native1280x720; top-left origin; x right/y down; [x0,y0,x1,y1) bbox',
        'pressure': 'User-reported psi retained; derived bar is unit conversion, not an independent reference measurement',
    })
    with (HERE / 'all_assignments.csv').open('w', encoding='utf-8-sig', newline='') as f:
        fields = ['id', 'source_group', 'split', 'filename', 'path', 'sha256', 'use_in_first_round']
        writer = csv.DictWriter(f, fields); writer.writeheader()
        for r in records:
            row = {k: r[k] for k in fields if k in r}
            row['use_in_first_round'] = r['active_for_initial_weight_updates']
            writer.writerow(row)
    with (HERE / 'train_and_validation_contents.csv').open('w', encoding='utf-8-sig', newline='') as f:
        fields = ['id', 'split', 'source_group', 'filename', 'pressure_psi', 'planned_condition', 'supervision_role', 'hub_loss', 'thin_loss', 'description_zh']
        writer = csv.DictWriter(f, fields); writer.writeheader()
        for r in records:
            if r['split'] not in ('train', 'validation'):
                continue
            writer.writerow({'id': r['id'], 'split': r['split'], 'source_group': r['source_group'], 'filename': r['filename'],
                             'pressure_psi': r['pressure']['value'], 'planned_condition': r['scene']['planned_condition'],
                             'supervision_role': r['supervision_role'], 'hub_loss': r['loss_mask'][0], 'thin_loss': r['loss_mask'][1],
                             'description_zh': r['content_description_zh']})
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def validate():
    m = json.loads((HERE / 'dataset_manifest.json').read_text(encoding='utf-8'))
    errors = []
    if sha(ANNOTATIONS) != m['canonical_annotations_sha256']:
        errors.append('canonical labels changed')
    source = {r['id']: r for r in json.loads(ANNOTATIONS.read_text(encoding='utf-8'))['records']}
    all_rows = []
    for split in GROUP_SPLITS.values():
        if any(r['split'] == split for r in all_rows):
            continue
        p = HERE / split / ('labels_for_final_evaluation.jsonl' if split == 'test' else 'labels.jsonl')
        all_rows.extend(json.loads(line) for line in p.read_text(encoding='utf-8').splitlines())
    for r in all_rows:
        s = source[r['id']]
        if r['split'] != GROUP_SPLITS[s['group']] or r['path'] != s['path'] or r['sha256'] != s['sha256']:
            errors.append(r['id'] + ': identity/split mismatch')
        if r['keypoints'] != s['keypoints'] or r['bbox_native_xyxy'] != s['bbox_native_xyxy'] or r['pressure'] != s['pressure']:
            errors.append(r['id'] + ': original annotation changed')
        if r['loss_mask'] != [head_policy(s, k)['loss_mask'] for k in HEADS]:
            errors.append(r['id'] + ': head mask mismatch')
        if r['target_present'] and r['supervision_role'] == 'negative_no_gauge':
            errors.append(r['id'] + ': unreadable positive became negative')
        if not Path(r['path']).is_file() or 'annotation_previews' in r['path']:
            errors.append(r['id'] + ': source is missing or preview')
    if len(all_rows) != 472 or len({r['id'] for r in all_rows}) != 472 or len({r['sha256'] for r in all_rows}) != 472:
        errors.append('source coverage or exact duplicate failure')
    active = [json.loads(line) for line in (HERE / 'train/initial_supervision.jsonl').read_text(encoding='utf-8').splitlines()]
    if len(active) != 164 or any(r['split'] != 'train' or not any(r['loss_mask']) for r in active):
        errors.append('first round supervision failure')
    test_index = [json.loads(line) for line in (HERE / 'test/index.jsonl').read_text(encoding='utf-8').splitlines()]
    if any(k in r for r in test_index for k in ('keypoints', 'pressure', 'loss_mask', 'target_present')):
        errors.append('test input index contains supervision')
    for path, digest in m['files_sha256'].items():
        if sha(HERE / path) != digest:
            errors.append(path + ': partition hash mismatch')
    result = {'status': 'PASS_PARTITION_ONLY_ROI_ADAPTER_PENDING' if not errors else 'FAIL',
              'records': len(all_rows), 'errors': errors, 'source_annotations_sha256': sha(ANNOTATIONS),
              'training_performed': False, 'model_evaluation_performed': False, 'original_images_written': False,
              'full_source_pixel_read_required_here': False, 'source_pixel_identity_review': 'separate leakage/source audit'}
    write_json(HERE / 'partition_validation.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['build', 'validate'], default='validate', nargs='?')
    args = parser.parse_args()
    if args.mode == 'build':
        build()
    else:
        validate()
