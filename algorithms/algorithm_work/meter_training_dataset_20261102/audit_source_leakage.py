"""Read native images for identity/near-duplicate screening; no ML models."""
from pathlib import Path
from itertools import combinations
from collections import Counter
import hashlib
import json
import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'meter_dataset_annotation_20261102' / 'annotations.json'
SPLITS = {**dict.fromkeys('ABC', 'reserve'), **dict.fromkeys('DEF', 'train'), 'G': 'validation', 'H': 'test'}
OSD_RECTS = [(32, 14, 292, 43), (104, 82, 260, 183), (702, 38, 1208, 65),
             (702, 108, 1085, 210), (638, 590, 1280, 720)]


def main():
    records = json.loads(SOURCE.read_text(encoding='utf-8'))['records']
    items, hashes, errors = [], {}, []
    for row in records:
        raw = Path(row['path']).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != row['sha256']:
            errors.append({'id': row['id'], 'error': 'source changed'})
        hashes.setdefault(digest, []).append(row['id'])
        image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE)
        if image is None or image.shape != (720, 1280):
            errors.append({'id': row['id'], 'error': 'native decode failed'}); continue
        image = image.copy()
        # This is only a duplicate fingerprint. Originals and training inputs
        # are never written or altered, and no dial/needle labels are used.
        for x0, y0, x1, y1 in OSD_RECTS:
            image[y0:y1, x0:x1] = 128
        small = cv2.resize(image, (64, 36), interpolation=cv2.INTER_AREA)
        dct = cv2.dct(cv2.resize(image, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32))[:8, :8].reshape(-1)
        bits = dct > np.median(dct[1:])
        bits[0] = False
        fingerprint = sum(int(bit) << i for i, bit in enumerate(bits))
        items.append({'id': row['id'], 'group': row['group'], 'split': SPLITS[row['group']],
                      'sha256': digest, 'phash64_hex': f'{fingerprint:016x}', 'fingerprint_int': fingerprint,
                      'small': small.astype(np.int16)})
    pairs = Counter()
    candidates = []
    nearest = []
    for a, b in combinations(items, 2):
        if a['split'] == b['split']:
            continue
        pair = '/'.join(sorted([a['split'], b['split']]))
        pairs[pair] += 1
        distance = (a['fingerprint_int'] ^ b['fingerprint_int']).bit_count()
        if distance <= 4:
            mae = float(np.abs(a['small'] - b['small']).mean())
            entry = {'id_a': a['id'], 'id_b': b['id'], 'split_a': a['split'], 'split_b': b['split'],
                     'phash_hamming': distance, 'masked_luma_mae_0_255': round(mae, 4),
                     'high_similarity_candidate': distance <= 2 and mae <= 1.5,
                     'exact_same_sha256': a['sha256'] == b['sha256']}
            candidates.append(entry)
        if a['split'] in ('train', 'validation', 'test') and b['split'] in ('train', 'validation', 'test'):
            nearest.append((distance, a['id'], b['id']))
    duplicates = [v for v in hashes.values() if len(v) > 1]
    result = {
        'status': 'PASS_SOURCE_IDENTITY_WITH_SCREENING_LIMITS' if not errors and not duplicates else 'FAIL',
        'source_annotation_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'native_images_read_and_sha256_verified': len(items), 'source_errors': errors,
        'exact_duplicate_sets': duplicates, 'cross_partition_pairs_screened': dict(pairs),
        'phash_candidate_threshold_bits': 4, 'high_similarity_threshold': {'hamming_max': 2, 'masked_luma_mae_max': 1.5},
        'phash_candidates': sorted(candidates, key=lambda x: (x['phash_hamming'], x['masked_luma_mae_0_255'])),
        'high_similarity_candidate_count': sum(r['high_similarity_candidate'] for r in candidates),
        'nearest_active_partition_phash_pairs': [dict(distance=x[0], id_a=x[1], id_b=x[2]) for x in sorted(nearest)[:20]],
        'method': 'Full-scene 64-bit DCT perceptual hash plus 64x36 luma MAE; fixed OSD regions ignored for fingerprint only.',
        'test_pixels_used_for': 'Source identity and leakage screening only; no CNN inference, test metrics or selection.',
        'raw_images_modified': False, 'model_training_or_scoring': False,
        'limitations': ['Perceptual similarity is only a screening candidate, not proof of a copied frame.',
                       'Same gauge and pressure can be visually similar across genuine rearranged sessions.',
                       'No claim of statistical independence, a new-meter test, or exhaustive detection of all near-duplicates.'],
    }
    (HERE / 'source_leakage_audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    fingerprint_rows = [{k: v for k, v in x.items() if k not in ('fingerprint_int', 'small')} for x in items]
    (HERE / 'source_fingerprints.json').write_text(json.dumps(fingerprint_rows, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('status', 'native_images_read_and_sha256_verified', 'cross_partition_pairs_screened', 'high_similarity_candidate_count')}, ensure_ascii=False))
    print(json.dumps({'candidate_count': len(candidates)}, ensure_ascii=False))
    if errors or duplicates:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
