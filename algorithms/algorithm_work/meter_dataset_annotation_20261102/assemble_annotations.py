"""Merge independently prepared labels and verify image identity. Never trains."""
from pathlib import Path
from collections import Counter
import csv
import hashlib
import json
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
PARTS = ['annotator_abc', 'annotator_def', 'annotator_gh']
PSI_TO_BAR = 0.06894757293168


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def pressure_for_image(group, name, index, present, policy):
    if not present:
        return None, None, None, 'NO_VISIBLE_GAUGE_FACE_NEGATIVE'
    supplement = policy['supplement_annotations'].get(group + '/' + name)
    levels = policy['pressure_levels_descending'][group]
    if supplement and supplement.get('pressure_value') is not None:
        value = supplement['pressure_value']
        return value, levels.index(value) + 1, supplement.get('condition_index'), 'USER_FILENAME_AND_EXPLICIT_CHAT_CONFIRMATION'
    missing = {'A': {(1, 4)}, 'C': {(1, 1), (1, 2), (1, 3)}, 'E': {(4, 6), (8, 1)}}
    positions = [(rank, slot) for rank in range(1, 9) for slot in range(1, 7)
                 if (rank, slot) not in missing.get(group, set())]
    if index is not None and index < len(positions):
        rank, slot = positions[index]
        return levels[rank - 1], rank, slot, 'USER_GROUP_PRESSURE_LIST_DESCENDING_ORDER_AND_REPLACEMENT_RECONCILIATION'
    return policy['challenge_gauge_pressure_psi'], None, None, 'USER_EXPLICIT_CHALLENGE_PRESSURE_CONFIRMATION'


def main():
    policy = read(HERE / 'annotation_policy.json')
    manifest = read(HERE / 'source_manifest.json')
    inv = manifest['images']
    source_by_path = {str(Path(x['path']).resolve()): x for x in inv}
    grouped = {g: sorted([x for x in inv if x['group'] == g], key=lambda x: x['name']) for g in 'ABCDEFGH'}
    standard_order = {g: {x['name']: i for i, x in enumerate(grouped[g]) if x['name'].startswith('snapshot_')} for g in grouped}
    # Source filenames sort before supplements; these indices are capture order
    # within the retained main sequence, not file modification timestamps.
    source_ids = {str(Path(x['path']).resolve()): f'{g}_{i:03d}' for g, rows in grouped.items() for i, x in enumerate(rows, 1)}
    records = []
    errors = []
    seen = set()
    source_part_hashes = {}
    correction_paths = [HERE / 'annotator_def/root_correction_proposals.json',
                        HERE / 'annotator_abc/def_root_corrections.json']
    corrections_by_id = {}
    correction_files = {}
    for correction_path in correction_paths:
        if not correction_path.exists():
            continue
        correction_files[str(correction_path)] = hashlib.sha256(correction_path.read_bytes()).hexdigest()
        correction_document = read(correction_path)
        for correction in correction_document['corrections']:
            normalized = dict(correction, source_file=str(correction_path))
            normalized['sha256'] = correction.get('sha256') or correction.get('sourcefileSHA256')
            normalized['reason'] = correction.get('reason') or correction.get('actual_visual_basis')
            corrections_by_id.setdefault(correction['id'], []).append(normalized)
    for part in PARTS:
        p = HERE / part / 'annotation.json'
        source_part_hashes[part] = hashlib.sha256(p.read_bytes()).hexdigest()
        document = read(p)
        for raw in document['records']:
            r = dict(raw)
            path = str(Path(r.get('path') or r['image_path']).resolve())
            if path not in source_by_path or path in seen:
                errors.append({'path': path, 'error': 'UNKNOWN_OR_DUPLICATE_SOURCE'}); continue
            seen.add(path)
            src = source_by_path[path]
            if r.get('sha256') != src['sha256']:
                errors.append({'path': path, 'error': 'ANNOTATOR_SHA_MISMATCH'})
            actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            if actual != src['sha256']:
                errors.append({'path': path, 'error': 'ORIGINAL_IMAGE_CHANGED'})
            r.update(id=source_ids[path], path=path, image_path=path, image_uri=Path(path).as_uri(),
                     filename=src['name'], session_id=src['group'], group=src['group'],
                     width=src['width'], height=src['height'], sha256=src['sha256'],
                     label_coordinates='native', split='unassigned',
                     independent_reposition=policy.get('scene_repositioned_between_groups'),
                     manual_focus_setting_unchanged=policy.get('manual_focus_setting_unchanged'),
                     human_ground_truth_certified=False, training_performed=False,
                     annotation_part=part, annotation_part_sha256=source_part_hashes[part])
            if not r.get('review_status'):
                r['review_status'] = 'ai_visual_reviewed_with_explicit_uncertainty'
            points = json.loads(json.dumps(r.get('keypoints', {})))
            r['keypoints'] = points
            for correction in corrections_by_id.get(r['id'], []):
                if correction['sha256'] != src['sha256'] or correction['keypoint'] not in ('hub', 'thin_terminal'):
                    errors.append({'id': r['id'], 'error': 'INVALID_REVIEW_CORRECTION_IDENTITY'}); continue
                key = correction['keypoint']
                previous = points[key]
                points[key] = correction['new_value']
                r.setdefault('independent_review_corrections', []).append({
                    'keypoint': key, 'previous': previous, 'new': points[key],
                    'reason': correction.get('reason'), 'source_file': correction['source_file'],
                    'source_file_sha256': correction_files[correction['source_file']]})
            negative_kind = r.get('negative_kind')
            if not negative_kind and r.get('image_kind') in ('absent', 'negative', 'no_gauge', 'no_gauge_face'):
                negative_kind = 'non_gauge_face'
            present = not bool(negative_kind) and r.get('image_kind') not in ('absent', 'negative', 'no_gauge', 'no_gauge_face')
            r['target_present'] = present
            r['pressure_stable_within_capture_group'] = policy.get('pressure_stable_within_capture_group') if present else None
            if policy.get('capture_confirmation'):
                r['capture_metadata_source'] = 'USER_CAPTURE_CONFIRMATION_20261102'
            r['negative_kind'] = negative_kind
            r['image_kind_original'] = r.get('image_kind')
            r['image_kind'] = 'gauge_face' if present else 'absent'
            bbox = r.get('bbox_native_xyxy')
            if not present and bbox is not None:
                r['distractor_bbox_native_xyxy'] = bbox
                bbox = None
                r['bbox_native_xyxy'] = None
            if present:
                if bbox is None:
                    r['bbox_visibility'] = 'unknown'
                elif not (len(bbox) == 4 and 0 <= bbox[0] < bbox[2] <= 1280 and 0 <= bbox[1] < bbox[3] <= 720):
                    errors.append({'id': r['id'], 'error': 'INVALID_BBOX', 'value': bbox})
            r['bbox_coordinate_convention'] = 'half_open_xyxy_visible_raster_extent'
            for key in ['hub', 'thin_terminal']:
                v = points.get(key)
                if not v or v.get('visibility') not in ('visible', 'occluded', 'unknown', 'absent'):
                    errors.append({'id': r['id'], 'error': 'MISSING_OR_INVALID_VISIBILITY', 'key': key}); continue
                xy = v.get('xy')
                if v['visibility'] == 'visible':
                    if not (xy and len(xy) == 2 and 0 <= xy[0] < 1280 and 0 <= xy[1] < 720 and v.get('uncertainty_px', 0) > 0):
                        errors.append({'id': r['id'], 'error': 'INVALID_VISIBLE_POINT', 'key': key})
                elif xy is not None:
                    errors.append({'id': r['id'], 'error': 'INVISIBLE_POINT_HAS_COORDINATE', 'key': key})
                if not present and (v['visibility'] != 'absent' or xy is not None):
                    errors.append({'id': r['id'], 'error': 'NEGATIVE_HAS_TARGET_KEYPOINT', 'key': key})
            value, rank, slot, provenance = pressure_for_image(src['group'], src['name'], standard_order[src['group']].get(src['name']), present, policy)
            old_pressure = r.get('pressure', {})
            old_value = r.get('pressure_raw_value', old_pressure.get('value'))
            if old_value is not None and value != old_value:
                errors.append({'id': r['id'], 'error': 'PRESSURE_RECONCILIATION_CONFLICT', 'part': old_value, 'expected': value})
            r.update(pressure_raw_value=value, pressure_raw_unit='psi' if value is not None else None,
                     pressure_label_source=provenance, pressure_rank_descending=rank,
                     condition_slot=slot, pressure_bar_derived=round(value * PSI_TO_BAR, 9) if value is not None else None)
            r['pressure'] = {'value': value, 'unit': 'psi' if value is not None else None, 'source': provenance,
                             'bar_derived_not_second_measurement': r['pressure_bar_derived'], 'uncertainty_psi': None}
            if slot is not None:
                r['capture_condition_slot'] = slot
                r['capture_condition_planned'] = policy['conditions_per_pressure'][slot - 1]
            r['joint_keypoints_visible'] = all(points.get(k, {}).get('visibility') == 'visible' for k in ('hub', 'thin_terminal'))
            r['coordinate_precision_tier'] = ('not_applicable' if not present else
                'unknown_or_partial' if not r['joint_keypoints_visible'] else
                'coarse_visible_points' if points['hub'].get('uncertainty_px', 0) > 8 or points['thin_terminal'].get('uncertainty_px', 0) > 8 else
                'bounded_visible_points')
            r['label_method'] = 'AI_VISUAL_REVIEW_OF_IMAGE_ASSISTED_PROPOSALS_NO_PRESSURE_INVERSION'
            records.append(r)
    missing = sorted(set(source_by_path) - seen)
    if missing:
        errors.append({'error': 'MISSING_IMAGES', 'paths': missing})
    records.sort(key=lambda r: r['id'])
    validation = {'schema': 'annotation_integrity_v1', 'source_count': len(inv), 'record_count': len(records),
                  'all_source_images_sha256_unchanged': not any(x.get('error') == 'ORIGINAL_IMAGE_CHANGED' for x in errors),
                  'errors': errors, 'error_count': len(errors), 'training_performed': False,
                  'checked_utc': datetime.now(timezone.utc).isoformat(), 'annotation_part_sha256': source_part_hashes,
                  'independent_correction_file_sha256': correction_files,
                  'independent_correction_count': sum(len(r.get('independent_review_corrections', [])) for r in records)}
    (HERE / 'validation.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if errors:
        print(json.dumps(validation, ensure_ascii=False, indent=2)); raise SystemExit(2)
    doc = {'schema': 'meter_native_annotations_v1', 'scope': 'ANNOTATION_ONLY_NO_TRAINING',
           'source_root': manifest['source_root'], 'annotation_policy': str(HERE / 'annotation_policy.json'),
           'coordinate_system': policy['coordinate_system'], 'split_policy': 'UNASSIGNED_NO_INDEPENDENCE_CLAIM',
           'annotation_status': 'FIRST_PASS_AI_ASSISTED_VISUAL_LABELS_WITH_VISIBILITY_AND_UNCERTAINTY',
           'human_ground_truth_certified': False, 'training_performed': False, 'records': records}
    if policy.get('capture_confirmation'):
        doc['capture_confirmation'] = policy['capture_confirmation']
    (HERE / 'annotations.json').write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with (HERE / 'annotations.jsonl').open('w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    fields = ['id', 'group', 'filename', 'path', 'sha256', 'image_kind', 'negative_kind', 'pressure_psi', 'pressure_bar_derived',
              'pressure_rank_descending', 'condition_slot', 'bbox_x0', 'bbox_y0', 'bbox_x1', 'bbox_y1',
              'hub_visibility', 'hub_x', 'hub_y', 'hub_uncertainty_px', 'thin_visibility', 'thin_x', 'thin_y',
              'thin_uncertainty_px', 'review_status', 'annotation_part', 'independent_reposition',
              'manual_focus_setting_unchanged', 'pressure_stable_within_capture_group']
    with (HERE / 'annotations.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fields); writer.writeheader()
        for r in records:
            h, t = (r['keypoints'][k] for k in ('hub', 'thin_terminal'))
            b = r.get('bbox_native_xyxy') or [None] * 4
            row = {k: r.get(k) for k in fields if k in r}
            row.update(pressure_psi=r['pressure_raw_value'], bbox_x0=b[0], bbox_y0=b[1], bbox_x1=b[2], bbox_y1=b[3],
                       hub_visibility=h['visibility'], hub_x=(h.get('xy') or [None, None])[0], hub_y=(h.get('xy') or [None, None])[1],
                       hub_uncertainty_px=h.get('uncertainty_px'), thin_visibility=t['visibility'],
                       thin_x=(t.get('xy') or [None, None])[0], thin_y=(t.get('xy') or [None, None])[1], thin_uncertainty_px=t.get('uncertainty_px'))
            writer.writerow(row)
    summary = {'images': len(records), 'groups': dict(Counter(r['group'] for r in records)),
               'gauge_faces': sum(r['target_present'] for r in records), 'negative_faces': sum(not r['target_present'] for r in records),
               'bbox_visible': sum(r.get('bbox_native_xyxy') is not None for r in records),
               'hub_visibility': dict(Counter(r['keypoints']['hub']['visibility'] for r in records)),
               'thin_visibility': dict(Counter(r['keypoints']['thin_terminal']['visibility'] for r in records)),
               'joint_keypoints_visible': sum(r['joint_keypoints_visible'] for r in records),
               'coordinate_precision_tier': dict(Counter(r['coordinate_precision_tier'] for r in records)),
               'user_reported_pressure_labels': sum(r['pressure_raw_value'] is not None for r in records),
               'training_performed': False, 'raw_images_modified': False, 'validation_errors': 0,
               'label_accuracy_is_not_model_accuracy': True, 'human_ground_truth_certified': False}
    (HERE / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
