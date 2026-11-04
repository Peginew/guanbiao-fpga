"""Visual review copies from final canonical labels; never training inputs."""
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent


def main():
    data = json.loads((HERE / 'annotations.json').read_text(encoding='utf-8'))
    out = HERE / 'annotation_previews'
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 16)
    for r in data['records']:
        with Image.open(r['path']) as src:
            im = src.convert('RGB')
        draw = ImageDraw.Draw(im)
        b = r.get('bbox_native_xyxy')
        if b:
            draw.rectangle([b[0], b[1], b[2] - 1, b[3] - 1], outline='#52ee65', width=2)
        for key, color in [('hub', '#f451df'), ('thin_terminal', '#3ee5f4')]:
            point = r['keypoints'][key]
            if point['visibility'] == 'visible' and point.get('xy'):
                x, y = point['xy']
                draw.ellipse([x - 4, y - 4, x + 4, y + 4], outline=color, width=2)
                draw.line([x - 7, y, x + 7, y], fill=color, width=1)
                draw.line([x, y - 7, x, y + 7], fill=color, width=1)
        pressure = f"{r['pressure_raw_value']} psi" if r['pressure_raw_value'] is not None else '无表盘反例'
        caption = f"{r['id']}  {pressure}  仅标注复核副本"
        draw.rectangle([0, 0, 650, 27], fill='#1b2a27')
        draw.text((8, 2), caption, font=font, fill='white')
        folder = out / r['group']
        folder.mkdir(parents=True, exist_ok=True)
        im.thumbnail((960, 540))
        im.save(folder / (r['id'] + '.jpg'), quality=90)
    note = {'kind': 'ANNOTATION_REVIEW_COPIES_ONLY_NOT_TRAINING_INPUTS', 'count': len(data['records']),
            'canonical_labels': str(HERE / 'annotations.json'), 'originals_unchanged': True,
            'colors': {'green': 'gauge bbox', 'magenta': 'mechanical hub', 'cyan': 'thin reading terminal'},
            'training_performed': False}
    (out / 'preview_manifest.json').write_text(json.dumps(note, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'previews': len(data['records']), 'output': str(out), 'training': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
