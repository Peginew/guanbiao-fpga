from pathlib import Path
import argparse
import csv
import json
import cv2
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', type=Path, default=Path(__file__).resolve().parents[1])
    a = ap.parse_args()
    run = a.run.resolve()
    out = run / 'visual'
    out.mkdir(exist_ok=True)
    evaluation = json.loads((run / 'validation_evaluation.json').read_text('utf-8'))
    rows = evaluation['rows']
    names = []
    for start in range(0, len(rows), 16):
        page = rows[start:start + 16]
        width, tile_h, header_h = 256, 326, 100
        height = header_h + ((len(page) + 3) // 4) * tile_h
        canvas = np.full((height, width * 4, 3), 246, np.uint8)
        cv2.putText(canvas, run.name + ' - G validation / float candidate', (14, 28), cv2.FONT_HERSHEY_SIMPLEX, .65, (25, 25, 25), 1, cv2.LINE_AA)
        cv2.putText(canvas, 'GREEN=visual label  YELLOW=pred hub  MAGENTA=pred thin tip', (14, 54), cv2.FONT_HERSHEY_SIMPLEX, .55, (25, 25, 25), 1, cv2.LINE_AA)
        cv2.putText(canvas, 'No H test / no bar accuracy / native annotation uncertainty remains', (14, 78), cv2.FONT_HERSHEY_SIMPLEX, .5, (25, 25, 25), 1, cv2.LINE_AA)
        for i, r in enumerate(page):
            image = cv2.imdecode(np.fromfile(run / 'validation_overlays' / (r['id'] + '.png'), np.uint8), cv2.IMREAD_COLOR)
            image = cv2.resize(image, (width, width), interpolation=cv2.INTER_AREA)
            x, y = (i % 4) * width, header_h + (i // 4) * tile_h
            canvas[y:y + width, x:x + width] = image
            err = r.get('angle_error_deg')
            lines = [r['id'] + '   accept=' + str(int(r['evidence_accepted'])),
                     'Angle err=' + ('unknown' if err is None else f'{err:.1f} deg'),
                     'Hub/Tip err=' + '/'.join('NA' if r.get(k) is None else f'{r[k]:.1f}' for k in ['hub_error_roi', 'thin_terminal_error_roi']) + ' ROIpx']
            for j, line in enumerate(lines):
                cv2.putText(canvas, line, (x + 6, y + width + 18 + j * 20), cv2.FONT_HERSHEY_SIMPLEX, .43, (20, 20, 20), 1, cv2.LINE_AA)
        name = f'validation_contact_{start // 16 + 1:02d}.png'
        cv2.imencode('.png', canvas)[1].tofile(str(out / name))
        names.append(name)
    with (out / 'validation_metrics.csv').open('w', encoding='utf-8-sig', newline='') as f:
        fields = ['id', 'target_present', 'evidence_accepted', 'hub_error_roi', 'thin_terminal_error_roi', 'angle_error_deg', 'angle_deg']
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    (out / 'index.html').write_text('<!doctype html><meta charset="utf-8"><title>验证集预测复核</title><style>body{font:16px sans-serif;margin:24px;background:#eee}img{max-width:100%;display:block;margin:24px 0}</style><h1>' + run.name + '：G组浮点预测复核</h1><p>绿色为辅助标注，黄色为预测轴心，紫色为预测细针端点。图片内给出角误差和固定证据阈值是否接受；不代表已通过读数或上板验收。</p>' + ''.join('<img loading="lazy" src="' + n + '">' for n in names), encoding='utf-8')
    print(json.dumps(dict(run=str(run), contact_sheets=names, images=len(rows)), ensure_ascii=False))


if __name__ == '__main__':
    main()
