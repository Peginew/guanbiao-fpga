"""Restore the original AVI from public Release byte-parts; standard library only."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re


def restore(manifest_path, parts_dir, output):
    manifest_path, parts_dir, output = Path(manifest_path), Path(parts_dir).resolve(), Path(output).resolve()
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    parts = manifest.get('parts', [])
    if not parts or len(parts) != manifest.get('part_count'):
        raise ValueError('Missing or inconsistent part count')
    if output.exists():
        raise FileExistsError('Output already exists; choose a new filename')
    if not re.fullmatch(r'[0-9a-f]{64}', manifest.get('whole_sha256', '')):
        raise ValueError('Invalid whole-file SHA256')
    if sum(part.get('bytes', -1) for part in parts) != manifest.get('original_bytes'):
        raise ValueError('Part sizes do not match the original byte count')
    validated = []
    for number, part in enumerate(parts, 1):
        name = part.get('name', '')
        if name != f'raw_capture.avi.part{number:04d}':
            raise ValueError('Unexpected part name or ordering')
        if not re.fullmatch(r'[0-9a-f]{64}', part.get('sha256', '')):
            raise ValueError('Invalid part SHA256')
        size = part.get('bytes')
        if not isinstance(size, int) or not 0 < size <= manifest['part_size_bytes']:
            raise ValueError('Invalid part size')
        path = (parts_dir / name).resolve()
        if not path.is_relative_to(parts_dir) or not path.is_file():
            raise ValueError(f'Missing or unsafe part: {name}')
        if path.stat().st_size != size:
            raise ValueError(f'Part size mismatch: {name}')
        validated.append((path, part))
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + '.restoring')
    if temporary.exists():
        raise FileExistsError('Temporary restore output already exists')
    whole, total = hashlib.sha256(), 0
    created = False
    try:
        with temporary.open('xb') as target:
            created = True
            for path, part in validated:
                digest, length = hashlib.sha256(), 0
                with path.open('rb') as src:
                    while True:
                        block = src.read(1024 * 1024)
                        if not block:
                            break
                        digest.update(block)
                        whole.update(block)
                        target.write(block)
                        length += len(block)
                if length != part['bytes'] or digest.hexdigest() != part['sha256']:
                    raise ValueError(f'Part checksum mismatch: {part["name"]}')
                total += length
        if total != manifest['original_bytes'] or whole.hexdigest() != manifest['whole_sha256']:
            raise ValueError('Restored whole-file checksum mismatch')
        if output.exists():
            raise FileExistsError('Output appeared during restore; no overwrite allowed')
        os.replace(temporary, output)
        return {'status': 'PASS', 'bytes': total, 'parts': len(parts), 'sha256': whole.hexdigest(),
                'video_reencoded': False, 'all_part_hashes_verified': True}
    except Exception:
        if created and temporary.exists():
            temporary.unlink()
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path(__file__).with_name('raw_video_manifest.json'))
    parser.add_argument('--parts-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('raw_capture.avi'))
    args = parser.parse_args()
    print(json.dumps(restore(args.manifest, args.parts_dir, args.output), ensure_ascii=False, indent=2))
