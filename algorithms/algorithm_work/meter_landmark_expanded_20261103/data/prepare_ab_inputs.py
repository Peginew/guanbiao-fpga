"""Prepare only the first118 explicitly reserved A/B records; stop before C.

Reuse the frozen hardware-shaped window, grayscale and blockmean functions.
No pressure, needle/axis point labels, C/H image, or C/H point is consumed.
"""
from pathlib import Path
import importlib.util,json,hashlib
import numpy as np
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
ORIG=ROOT/'algorithm_work/meter_cnn_training_20261102'
PACK=ROOT/'algorithm_work/meter_training_dataset_20261102'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    spec=importlib.util.spec_from_file_location('frozen_roi',ORIG/'roi_adapter.py');adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
    selected=[]
    with (PACK/'reserve/labels.jsonl').open(encoding='utf-8-sig') as fp:
        # File is canonically sorted A001..A059,B001..B059,C001..C059.
        # Never advance to C or parse its points.
        for index in range(118):
            raw=json.loads(next(fp));assert raw['id']==f'{"A" if index<59 else "B"}_{index%59+1:03d}'
            selected.append({k:raw[k] for k in ('id','path','sha256','source_group','target_present','bbox_native_xyxy')})
            del raw
    median={}
    for g in ('A','B'):
        boxes=[r['bbox_native_xyxy'] for r in selected if r['source_group']==g and r['target_present'] and 160<=max(r['bbox_native_xyxy'][2]-r['bbox_native_xyxy'][0],r['bbox_native_xyxy'][3]-r['bbox_native_xyxy'][1])<=499]
        median[g]=np.rint(np.median(boxes,axis=0)).astype(int).tolist()
    prepared=[];images=[]
    for r in selected:
        assert sha(r['path'])==r['sha256']
        box=r['bbox_native_xyxy'] if r['target_present'] else median[r['source_group']]
        q=adapter.window_policy(box)
        p={**r,'split':'train','roi_request':q,'ROI_proxy':'same frozen annotatedbbox/windowpolicy, not boardautoROI',
           'reserve_promoted_by_expanded_task':True,'negative_window_session_median_bbox_only':not r['target_present']}
        images.append(adapter.read_roi(p));prepared.append(p)
    (BASE/'prepared_ab.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in prepared),'utf-8')
    np.savez_compressed(BASE/'roi_cache_ab.npz',images=np.stack(images),ids=np.asarray([r['id'] for r in prepared]))
    old=np.load(ORIG/'roi_cache_train.npz');all_images=np.concatenate([np.stack(images),old['images']]);all_ids=np.concatenate([np.asarray([r['id'] for r in prepared]),old['ids']])
    assert len(all_images)==295 and np.array_equal(all_images[118:],old['images']) and np.array_equal(all_ids[118:],old['ids'])
    np.savez_compressed(BASE/'roi_cache_train.npz',images=all_images,ids=all_ids)
    receipt={'status':'AB118_ROI_PREPARED_DEF177_PIXELS_EXACTLY_PRESERVED','AB_images':118,'combined_train_images':295,
       'source_read':'reserve JSONL exactly first118 A/B rows, stop atB059 beforeC','C_H_images_or_points_read':False,
       'old_DEF_pixel_bytes_unchanged':True,'old_DEF_cache_source_sha256':sha(ORIG/'roi_cache_train.npz'),
       'frozen_ROI_adapter_sha256':sha(ORIG/'roi_adapter.py'),'median_negative_boxes':median,
       'outputs_sha256':{f:sha(BASE/f) for f in ('prepared_ab.jsonl','roi_cache_ab.npz','roi_cache_train.npz')},
       'no_new_model_or_firmware_or_device_actions':True}
    (BASE/'input_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps(receipt,ensure_ascii=False))
if __name__=='__main__':BASE.mkdir(exist_ok=True);main()
