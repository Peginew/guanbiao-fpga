"""Independent, annotation-only verification; never imports the assembler or training tools."""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import ast
import csv
import hashlib
import json

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).with_name('export_independent_review.json')

def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    annotation_path = ROOT / 'annotations.json'
    initial_sha = sha(annotation_path)
    doc = read(annotation_path)
    policy = read(ROOT / 'annotation_policy.json')
    manifest = read(ROOT / 'source_manifest.json')
    validation = read(ROOT / 'validation.json')
    rows = doc['records']
    checks = []
    def check(name, ok, evidence=None):
        checks.append({'name': name, 'pass': bool(ok), 'evidence': evidence})

    low = [12, 11, 9.5, 8, 6.5, 5, 3.5, 2.5]
    high = [12, 11.5, 10, 8.5, 7, 5.5, 4, 2.5]
    schedules = {g: low if g in 'ABCDE' else high for g in 'ABCDEFGH'}
    check('two_explicit_psi_schedules', policy['pressure_levels_descending'] == schedules)
    check('descending_order', policy['pressure_capture_order'] == 'high_to_low' and all(all(a > b for a, b in zip(v, v[1:])) for v in schedules.values()))
    check('scope_and_no_training_claim', doc['training_performed'] is False and policy['training_authorized'] is False and doc['scope'] == 'ANNOTATION_ONLY_NO_TRAINING')
    check('no_independent_or_human_truth_claim', doc['human_ground_truth_certified'] is False and all(r['split'] == 'unassigned' and r['independent_reposition'] is None and r['human_ground_truth_certified'] is False for r in rows))
    check('472_unique_images_59_per_group', len(rows) == 472 and len({r['path'] for r in rows}) == 472 and Counter(r['group'] for r in rows) == {g: 59 for g in 'ABCDEFGH'})
    by_path = {str(Path(r['path']).resolve()): r for r in rows}
    raw_integrity = []
    for s in manifest['images']:
        p = Path(s['path'])
        r = by_path.get(str(p.resolve()))
        actual = sha(p)
        if r is None or actual != s['sha256'] or r['sha256'] != s['sha256']:
            raw_integrity.append(s['path'])
    check('all_472_raw_file_sha256_rechecked', not raw_integrity, {'files_rehashed': len(manifest['images']), 'mismatches': raw_integrity})
    check('integrity_export_has_no_errors', validation['error_count'] == 0 and validation['errors'] == [])

    group_info = {}
    pressure_errors = []
    for g in 'ABCDEFGH':
        gr = [r for r in rows if r['group'] == g]
        main_rows = [r for r in gr if r['condition_slot'] is not None]
        slots = Counter((r['pressure_rank_descending'], r['condition_slot']) for r in main_rows)
        expected = Counter((rank, slot) for rank in range(1, 9) for slot in range(1, 7))
        negative = [r for r in gr if not r['target_present']]
        challenge = [r for r in gr if r['target_present'] and r['condition_slot'] is None]
        group_info[g] = {'main_8x6': len(main_rows), 'unique_slots': len(slots), 'negative': len(negative), 'challenge': len(challenge)}
        if slots != expected or len(negative) != 3 or len(challenge) != 8:
            pressure_errors.append(g + ':slot_or_count')
        for r in main_rows:
            if r['pressure_raw_value'] != schedules[g][r['pressure_rank_descending'] - 1] or r['pressure_raw_unit'] != 'psi':
                pressure_errors.append(r['id'])
        for r in challenge:
            if r['pressure_raw_value'] != 2.5 or r['pressure_label_source'] != 'USER_EXPLICIT_CHALLENGE_PRESSURE_CONFIRMATION':
                pressure_errors.append(r['id'])
    check('each_group_8_ranks_6_conditions_unique_and_challenges', not pressure_errors, {'groups': group_info, 'errors': pressure_errors})

    missing = {'A': {(1,4)}, 'C': {(1,1),(1,2),(1,3)}, 'E': {(4,6),(8,1)}}
    order_errors = []
    for g in 'ABCDEFGH':
        retained = sorted([r for r in rows if r['group'] == g and r['filename'].startswith('snapshot_')], key=lambda r: r['filename'])
        expected = [(rank, slot) for rank in range(1,9) for slot in range(1,7) if (rank,slot) not in missing.get(g,set())]
        for r, slot in zip(retained[:len(expected)], expected):
            if (r['pressure_rank_descending'], r['condition_slot']) != slot:
                order_errors.append(r['id'])
    check('retained_main_capture_sequence_and_replacement_holes', not order_errors, order_errors)
    supplement_errors = []
    for k, s in policy['supplement_annotations'].items():
        g, name = k.split('/',1)
        r = next((r for r in rows if r['group'] == g and r['filename'] == name), None)
        if r is None or r['pressure_raw_value'] != s['pressure_value'] or (s['pressure_value'] is not None and r['condition_slot'] != s['condition_index']):
            supplement_errors.append(k)
    check('seven_named_supplements_with_explicit_slots_and_C_12psi', not supplement_errors, supplement_errors)
    negatives = [r for r in rows if not r['target_present']]
    check('24_negatives_have_no_target_pressure_or_points', len(negatives) == 24 and all(r['pressure_raw_value'] is None and r['pressure_raw_unit'] is None and r['pressure_bar_derived'] is None and r['bbox_native_xyxy'] is None and all(r['keypoints'][k]['visibility'] == 'absent' and r['keypoints'][k]['xy'] is None for k in ('hub','thin_terminal')) for r in negatives))
    check('psi_to_bar_is_only_unit_conversion_no_independent_measurement', all(r['pressure_bar_derived'] == (None if r['pressure_raw_value'] is None else round(r['pressure_raw_value'] * 0.06894757293168,9)) and r['pressure']['bar_derived_not_second_measurement'] == r['pressure_bar_derived'] for r in rows))
    check('single_circular_object_user_limit_retained_no_fabrication', policy['circular_distractor_note']['user_reports_one_instead_of_requested_two'] is True and policy['circular_distractor_note']['no_second_object_is_to_be_fabricated'] is True)

    parts = {}
    original_points = {}
    for part in ('annotator_abc','annotator_def','annotator_gh'):
        part_path = ROOT / part / 'annotation.json'
        parts[part] = sha(part_path)
        for r in read(part_path)['records']:
            original_points[str(Path(r.get('path') or r['image_path']).resolve())] = r
    check('exact_current_part_hashes_match_assembly_receipt', parts == validation['annotation_part_sha256'], parts)
    trace_errors = []
    point_errors = []
    visibility_counts = {k: Counter() for k in ('hub','thin_terminal')}
    for r in rows:
        raw = original_points[r['path']]
        expected_points = json.loads(json.dumps(raw['keypoints']))
        for c in r.get('independent_review_corrections', []):
            if expected_points[c['keypoint']] != c['previous'] or sha(Path(c['source_file'])) != c['source_file_sha256']:
                trace_errors.append(r['id'])
            expected_points[c['keypoint']] = c['new']
        if r['keypoints'] != expected_points or r['annotation_part_sha256'] != parts[r['annotation_part']]:
            trace_errors.append(r['id'])
        for k in ('hub','thin_terminal'):
            p = r['keypoints'][k]
            visibility_counts[k][p['visibility']] += 1
            if p['visibility'] == 'visible':
                if not(p['xy'] and len(p['xy']) == 2 and 0 <= p['xy'][0] < 1280 and 0 <= p['xy'][1] < 720 and p.get('uncertainty_px',0) > 0):
                    point_errors.append(r['id'] + ':' + k)
            elif p['visibility'] not in ('unknown','occluded','absent') or p['xy'] is not None:
                point_errors.append(r['id'] + ':' + k)
    check('all_keypoints_uncertainty_and_review_overwrites_preserve_trace', not trace_errors, {'errors':trace_errors, 'external_corrections':sum(len(r.get('independent_review_corrections',[])) for r in rows)})
    check('visibility_masks_null_and_native_point_bounds', not point_errors, {'errors':point_errors, 'visibility_counts':{k:dict(v) for k,v in visibility_counts.items()}})
    check('review_status_not_blank', all(r.get('review_status') for r in rows))
    check('H029_unresolvable_physical_tip_not_fabricated_and_H042_corrected', next(r for r in rows if r['id']=='H_029')['keypoints']['thin_terminal']['visibility']=='unknown' and next(r for r in rows if r['id']=='H_042')['keypoints']['thin_terminal']['xy']==[199,357])

    with (ROOT/'annotations.csv').open(encoding='utf-8-sig',newline='') as f:
        csv_rows = list(csv.DictReader(f))
    csv_by_id = {r['id']:r for r in csv_rows}
    csv_errors = []
    def serial(v):
        return '' if v is None else str(v)
    for r in rows:
        c = csv_by_id.get(r['id'])
        if not c or c['sha256'] != r['sha256'] or c['pressure_psi'] != serial(r['pressure_raw_value']) or not c['review_status']:
            csv_errors.append(r['id']);continue
        for key,prefix in [('hub','hub'),('thin_terminal','thin')]:
            p = r['keypoints'][key];xy=p.get('xy') or [None,None]
            if c[prefix+'_visibility'] != p['visibility'] or c[prefix+'_x'] != serial(xy[0]) or c[prefix+'_y'] != serial(xy[1]) or c[prefix+'_uncertainty_px'] != serial(p.get('uncertainty_px')):
                csv_errors.append(r['id']+':'+key)
    check('csv_is_472_matching_rows_including_nulls_and_uncertainty', len(csv_rows)==472 and not csv_errors, csv_errors)
    jsonl = [json.loads(s) for s in (ROOT/'annotations.jsonl').read_text(encoding='utf-8').splitlines()]
    check('jsonl_exact_record_equivalence', jsonl == rows)
    tree = ast.parse((ROOT/'assemble_annotations.py').read_text(encoding='utf-8'))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):imported.extend(n.name for n in node.names)
        if isinstance(node, ast.ImportFrom):imported.append(node.module)
    check('assembler_has_only_file_data_hash_csv_imports', set(imported) <= {'pathlib','collections','csv','hashlib','json','datetime'}, imported)
    check('no_pressure_or_prediction_geometry_truth_claims', policy['OSD_predictions_must_not_be_used_as_ground_truth'] is True and policy['bar_must_not_be_used_to_invert_keypoint_labels'] is True and all(r['label_method'] == 'AI_VISUAL_REVIEW_OF_IMAGE_ASSISTED_PROPOSALS_NO_PRESSURE_INVERSION' for r in rows))
    check('snapshot_unchanged_during_independent_audit', sha(annotation_path)==initial_sha)
    result = {'schema':'independent_annotation_export_semantic_review_v1','status':'PASS_EXPORT_SEMANTICS_ONLY' if all(c['pass'] for c in checks) else 'FAIL', 'reviewed_utc':datetime.now(timezone.utc).isoformat(), 'annotation_sha256':initial_sha, 'files':{n:sha(ROOT/n) for n in ['annotations.json','annotations.csv','annotations.jsonl','annotation_policy.json','source_manifest.json','validation.json','assemble_annotations.py']}, 'scope':'Export semantics, source identity, pressure provenance, visibility, uncertainty preservation and correction trace; not full geometric accuracy acceptance.', 'training_executed':False, 'source_images_modified':False, 'geometric_accuracy_full_dataset_pass_claimed':False, 'limitations':['AI-assisted labels are not human-certified gold truth.','Known pressure is user-reported psi; reference measurement uncertainty remains unknown.','Sessions and splits remain unassigned and independence unconfirmed.','H029 thin terminal explicitly UNKNOWN despite known pressure.'], 'checks':checks}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'annotation_sha256':initial_sha,'checks':len(checks),'failed':[c['name'] for c in checks if not c['pass']]},ensure_ascii=False))

if __name__=='__main__':
    main()
