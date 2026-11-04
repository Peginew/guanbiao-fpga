"""Read-only split leakage screen on native PNGs, never a recognition test.

All thresholds are prespecified below, before pair measurements.  Fingerprint
similarity is a candidate screen, not proof that one image was copied.
"""
from pathlib import Path
from collections import defaultdict, Counter
import hashlib, json, re
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parents[1]/'meter_dataset_annotation_20261102'/'annotations.json'
TRAIN=set('DEF')
HELD=set('GH')
# DCT median-hash and adjacent-column dHash each have64 bits.
MAX_PHASH_HAMMING=6
MAX_DHASH_HAMMING=6
MAX_RGB_RMSE=8.0


def digest(b):return hashlib.sha256(b).hexdigest()


def bits_to_int(a):
    n=0
    for b in np.ravel(a):n=(n<<1)|int(b)
    return n


def main():
    HERE.mkdir(parents=True,exist_ok=True)
    raw=SOURCE.read_bytes();d=json.loads(raw)
    rows=[];thumbs={};native_sha=defaultdict(list);pixel_sha=defaultdict(list)
    for r in d['records']:
        p=Path(r['image_path']);buf=p.read_bytes();sh=digest(buf)
        assert sh==r['sha256'],(r['id'],'source differs from annotation SHA')
        image=cv2.imdecode(np.frombuffer(buf,np.uint8),cv2.IMREAD_COLOR)
        assert image.shape==(720,1280,3),(r['id'],image.shape)
        gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
        small=cv2.resize(gray,(32,32),interpolation=cv2.INTER_AREA).astype(np.float32)
        dc=cv2.dct(small)[:8,:8].copy();median=float(np.median(dc.ravel()[1:]));pb=dc>median
        pb[0,0]=False # DC excluded explicitly;64th bit is a shared zero.
        adjacent=cv2.resize(gray,(9,8),interpolation=cv2.INTER_AREA)
        dh=bits_to_int(adjacent[:,1:]>adjacent[:,:-1])
        ph=bits_to_int(pb)
        color=cv2.resize(image,(64,36),interpolation=cv2.INTER_AREA)
        px=digest(image.tobytes())
        group=r['group'];rec={'id':r['id'],'group':group,'path':str(p),'sha256':sh,
                             'decoded_bgr_sha256':px,'phash64':f'{ph:016x}','dhash64':f'{dh:016x}'}
        rows.append(rec);thumbs[r['id']]=color
        native_sha[sh].append(r['id']);pixel_sha[px].append(r['id'])
    pairs=[]
    aa=[r for r in rows if r['group'] in TRAIN];bb=[r for r in rows if r['group'] in HELD]
    for a in aa:
        for b in bb:
            hp=(int(a['phash64'],16)^int(b['phash64'],16)).bit_count()
            hd=(int(a['dhash64'],16)^int(b['dhash64'],16)).bit_count()
            delta=thumbs[a['id']].astype(np.float32)-thumbs[b['id']].astype(np.float32)
            rmse=float(np.sqrt(np.mean(delta*delta)))
            candidate=(hp<=MAX_PHASH_HAMMING and hd<=MAX_DHASH_HAMMING)
            strong_screen=(candidate and rmse<=MAX_RGB_RMSE)
            pairs.append({'train_id':a['id'],'held_id':b['id'],'train_group':a['group'],'held_group':b['group'],
                          'phash_hamming':hp,'dhash_hamming':hd,'full_scene_rgb64x36_rmse':round(rmse,6),
                          'candidate_screen':candidate,'very_close_screen':strong_screen})
    pairs.sort(key=lambda q:(not q['very_close_screen'],not q['candidate_screen'],q['full_scene_rgb64x36_rmse'],q['phash_hamming']+q['dhash_hamming']))
    candidates=[p for p in pairs if p['candidate_screen']]
    strongest=[p for p in pairs if p['very_close_screen']]
    # Review up to24 candidates (lowest full-scene RMSE), plus lowest-RMSE
    # example for every one of six group-pairs, without recognition results.
    selected=[];seen=set()
    def take(p):
        key=(p['train_id'],p['held_id'])
        if key not in seen:seen.add(key);selected.append(p)
    for p in candidates[:24]:take(p)
    for g in sorted(TRAIN):
        for h in sorted(HELD):
            gp=[p for p in pairs if p['train_group']==g and p['held_group']==h]
            take(min(gp,key=lambda p:p['full_scene_rgb64x36_rmse']))
    by={r['id']:r for r in rows};font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',17)
    sheets=[]
    for k in range(0,len(selected),6):
        canvas=Image.new('RGB',(1280,1260),'#ddd');dr=ImageDraw.Draw(canvas)
        for j,p in enumerate(selected[k:k+6]):
            yy=(j//2)*420;xx=(j%2)*640
            for slot,key in [(0,'train_id'),(1,'held_id')]:
                im=Image.open(by[p[key]]['path']).convert('RGB');im.thumbnail((320,180))
                canvas.paste(im,(xx+slot*320,yy+38))
            title=f'{k+j+1}: {p["train_id"]} vs {p["held_id"]} pH{p["phash_hamming"]} dH{p["dhash_hamming"]} RMSE{p["full_scene_rgb64x36_rmse"]:.2f}'
            dr.text((xx+5,yy+5),title,font=font,fill='black')
        path=HERE/f'cross_split_pairs_{k//6+1:02}.jpg';canvas.save(path,quality=95);sheets.append(str(path))
    summary={'source_annotations':str(SOURCE),'source_annotations_sha256':digest(raw),
             'scope':'Only native PNG source identity and full-frame low-resolution fingerprints; no recognition model, score, or test-based tuning.',
             'image_count':len(rows),'group_counts':dict(Counter(r['group'] for r in rows)),
             'proposed_split':{'train':['D','E','F'],'validation':['G'],'prospective_test':['H'],'train_only_reserve':['A','B','C']},
             'source_sha_verified':len(rows),'exact_file_duplicate_sets':[v for v in native_sha.values() if len(v)>1],
             'exact_decoded_pixel_duplicate_sets':[v for v in pixel_sha.values() if len(v)>1],
             'pair_count':len(pairs),'candidate_thresholds':{'phash64_hamming_lte':MAX_PHASH_HAMMING,'dhash64_hamming_lte':MAX_DHASH_HAMMING,'very_close_additional_rgb64x36_rmse_lte':MAX_RGB_RMSE},
             'candidate_pairs':len(candidates),'very_close_pairs':len(strongest),'candidate_group_pairs':dict(Counter(f'{p["train_group"]}-{p["held_group"]}' for p in candidates)),
             'visual_review_selected_pairs':selected,'visual_review_sheets':sheets,
             'recognition_model_run':False,'training_performed':False,'source_images_modified':False,
             'limits':['Hashes may miss shifted or illuminated near-duplicates; low-resolution full-scene similarity is dominated by the background.',
                       'Same gauge and same pressure can produce similar images without copied frames.',
                       'Visual candidate inspection must precede any assertion of actual duplicate leakage.',
                       'A-H have already been viewed during annotation; prospective_test is future model evaluation holdout, not a previously unseen image source.']}
    for name,data in [('fingerprints.json',rows),('all_cross_split_pairs.json',pairs),('candidate_pairs.json',candidates),('summary.json',summary)]:
        (HERE/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:summary[k] for k in ['image_count','source_sha_verified','pair_count','candidate_pairs','very_close_pairs','candidate_group_pairs','exact_file_duplicate_sets','exact_decoded_pixel_duplicate_sets']},ensure_ascii=False))
    print(json.dumps({'selected_review_pairs':len(selected),'sheets':sheets},ensure_ascii=False))


if __name__=='__main__':main()
