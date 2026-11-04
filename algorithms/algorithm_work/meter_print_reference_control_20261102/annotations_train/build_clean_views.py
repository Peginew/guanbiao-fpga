"""Display only native face crops and IDs for metadata-masked annotation.

Selection uses pre-existing group/condition metadata. No pressure, CNN output,
keypoint, registration or readout fields are displayed or used to choose points.
"""
from pathlib import Path
import hashlib,json,math
from PIL import Image,ImageDraw,ImageFont

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SOURCE=ROOT/'algorithm_work/meter_cnn_training_20261102/prepared_train.jsonl'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    records=[json.loads(s)for s in SOURCE.read_text('utf-8-sig').splitlines()if s.strip()]
    chosen=[r for r in records if r['source_group']in{'D','E','F'}and r['target_present']and r['capture_condition_slot']in{1,2}]
    assert len(chosen)==48 and all(sum(r['source_group']==g for r in chosen)==16 for g in ['D','E','F'])
    views=HERE/'views';views.mkdir(parents=True,exist_ok=True)
    font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',24)
    exported=[]
    for r in sorted(chosen,key=lambda x:x['id']):
        path=Path(r['path']);assert sha(path)==r['sha256']
        im=Image.open(path).convert('RGB');x0,y0,x1,y1=r['bbox_native_xyxy']
        box=[max(0,math.floor(x0)-8),max(0,math.floor(y0)-8),min(im.width,math.ceil(x1)+8),min(im.height,math.ceil(y1)+8)]
        crop=im.crop(box);scale=min(512/crop.width,512/crop.height)
        size=[int(round(crop.width*scale)),int(round(crop.height*scale))]
        offset=[(512-size[0])//2,(512-size[1])//2]
        panel=Image.new('RGB',(512,512),(232,232,232))
        panel.paste(crop.resize(tuple(size),Image.Resampling.LANCZOS),tuple(offset))
        panel.save(views/(r['id']+'.png'))
        exported.append(dict(id=r['id'],source_group=r['source_group'],source_sha256=r['sha256'],
            native_image_path=str(path),native_crop_xyxy=box,display_shape=[512,512],
            resized_native_crop_size=size,display_offset=offset,
            display_to_native='native=crop_origin+(display-offset)*native_crop_size/resized_size',
            view_file='views/'+r['id']+'.png',view_sha256=sha(views/(r['id']+'.png'))))
    for group in ['D','E','F']:
        selected=[r for r in exported if r['source_group']==group]
        for start in range(0,16,4):
            page=Image.new('RGB',(1084,1164),'white');draw=ImageDraw.Draw(page)
            for j,r in enumerate(selected[start:start+4]):
                col=j%2;row=j//2;x=20+col*532;y=20+row*572
                draw.text((x,y),r['id'],font=font,fill=(0,0,0))
                page.paste(Image.open(HERE/r['view_file']),(x,y+40))
            page.save(HERE/f'{group}_page{start//4+1:02d}.png')
    manifest=dict(status='48_ID_ONLY_NATIVE_FACE_VIEWS_FOR_VISUAL_PRINT_REFERENCE_ANNOTATION',
        selection='D/E/F target_present condition_slot1or2,16pergroup; no pressure/image model score selection',
        source_prepared_sha256=sha(SOURCE),code_sha256=sha(__file__),records=exported,
        no_existing_axis_needle_registration_or_pressure_displayed=True,ABC_H_opened=False,
        original_images_modified=False)
    (HERE/'view_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps(dict(images=len(exported),pages=12,group_counts={g:sum(r['source_group']==g for r in exported)for g in ['D','E','F']})))

if __name__=='__main__':main()
