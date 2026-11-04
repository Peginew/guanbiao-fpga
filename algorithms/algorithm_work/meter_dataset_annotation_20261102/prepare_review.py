"""Prepare annotation review artifacts; no training and no source-image writes."""
from pathlib import Path
import json
import argparse
from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = Path(__file__).resolve().parent
ROOT = Path('D:/资料归档/FPGA采集素材/hdmi_capture_20261018/data_base')


def group_records(group):
    inventory = json.loads((HERE / 'inventory_review/inventory.json').read_text(encoding='utf-8'))
    rows = sorted((x for x in inventory['images'] if x['group'] == group), key=lambda x: x['name'])
    return [dict(x, id=f'{group}_{i:03d}') for i, x in enumerate(rows, 1)]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--groups', nargs='+', default=['G', 'H'])
    args = p.parse_args()
    out = HERE / 'root_gh'
    out.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 16)
    for group in args.groups:
        rows = group_records(group)
        (out / f'{group}_index.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        for page in range((len(rows) + 11) // 12):
            canvas = Image.new('RGB', (1536, 750), '#202020')
            draw = ImageDraw.Draw(canvas)
            for j, row in enumerate(rows[page * 12:page * 12 + 12]):
                with Image.open(row['path']) as src:
                    thumb = ImageOps.contain(src.convert('RGB'), (384, 216))
                x, y = j % 4 * 384, j // 4 * 250
                canvas.paste(thumb, (x, y + 34))
                draw.text((x + 4, y + 4), row['id'] + ' ' + row['name'][:21], font=font, fill='white')
            canvas.save(out / f'{group}_page_{page + 1}.jpg', quality=93)
    print(json.dumps({'groups': args.groups, 'output': str(out), 'training': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
