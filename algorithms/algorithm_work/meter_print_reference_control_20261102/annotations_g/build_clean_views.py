"""Build pressure/prediction-free raw-image views for fixed print-anchor audit."""
from pathlib import Path
import json, hashlib
import cv2
import numpy as np

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PREP = ROOT / 'algorithm_work/meter_cnn_training_20261102/prepared_validation.jsonl'
SIZE = 384

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    out = BASE / 'clean_views'
    out.mkdir(parents=True, exist_ok=True)
    records = []
    tiles = []
    for line in PREP.read_text(encoding='utf-8').splitlines():
        # Only these display/identity fields are consumed. No pressure, keypoint,
        # neural prediction, SIFT, or ring-pose fields enter this script.
        raw = json.loads(line)
        r = {k: raw.get(k) for k in ('id','path','sha256','bbox_native_xyxy','roi_request')}
        del raw
        p = Path(r['path'])
        im = cv2.imdecode(np.fromfile(str(p), dtype=np.uint8), cv2.IMREAD_COLOR)
        assert im is not None and sha(p) == r['sha256']
        h,w = im.shape[:2]
        bbox = r['bbox_native_xyxy']
        if bbox:
            x0,y0,x1,y1 = bbox
            cx,cy = (x0+x1)/2,(y0+y1)/2
            span = max(x1-x0,y1-y0)*1.18
            x0,y0 = int(np.floor(cx-span/2)),int(np.floor(cy-span/2))
            x1,y1 = int(np.ceil(cx+span/2)),int(np.ceil(cy+span/2))
            x0,y0,x1,y1 = max(0,x0),max(0,y0),min(w,x1),min(h,y1)
        else:
            x0,y0,x1,y1 = 0,0,w,h
        crop = im[y0:y1,x0:x1]
        scale = min(SIZE/crop.shape[1],SIZE/crop.shape[0])
        ow,oh = round(crop.shape[1]*scale),round(crop.shape[0]*scale)
        dx,dy = (SIZE-ow)//2,(SIZE-oh)//2
        view = np.full((SIZE,SIZE,3),235,np.uint8)
        view[dy:dy+oh,dx:dx+ow] = cv2.resize(crop,(ow,oh),interpolation=cv2.INTER_LINEAR)
        target = out / (r['id']+'.png')
        cv2.imencode('.png',view)[1].tofile(str(target))
        tile = np.full((SIZE+30,SIZE,3),255,np.uint8)
        tile[30:] = view
        cv2.putText(tile,r['id'],(10,22),cv2.FONT_HERSHEY_SIMPLEX,.65,(0,0,0),1,cv2.LINE_AA)
        tiles.append(tile)
        records.append({**r,'native_size_wh':[w,h], 'view_size_wh':[SIZE,SIZE],
                        'native_crop_xyxy':[x0,y0,x1,y1],
                        'view_transform':{'scale_x':ow/(x1-x0),'scale_y':oh/(y1-y0),'offset_x':dx,'offset_y':dy},
                        'clean_view':str(target),'clean_view_sha256':sha(target)})
    for page in range(0,len(tiles),9):
        canvas = np.full(((SIZE+30)*3,SIZE*3,3),255,np.uint8)
        for j,tile in enumerate(tiles[page:page+9]):
            yy,xx = divmod(j,3)
            canvas[yy*(SIZE+30):(yy+1)*(SIZE+30),xx*SIZE:(xx+1)*SIZE] = tile
        cv2.imencode('.png',canvas)[1].tofile(str(BASE/f'clean_contact_{page//9+1:02d}.png'))
    (BASE/'display_index.jsonl').write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in records)+'\n',encoding='utf-8')
    print(json.dumps({'records':len(records),'pages':(len(records)+8)//9,'source_fields_used':['id','path','sha256','bbox_native_xyxy','roi_request'],'no_pressure_or_predictions_used':True}))

if __name__ == '__main__': main()
