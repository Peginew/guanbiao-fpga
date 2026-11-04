"""Export visual points only; no pressure/calibration/prediction processing."""
from pathlib import Path
import hashlib,json,math
from PIL import Image,ImageDraw,ImageFont

HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n','utf-8')

def main():
    manifest= json.loads((HERE/'view_manifest.json').read_text('utf-8-sig'))
    picks=json.loads((HERE/'visual_picks.json').read_text('utf-8-sig'))['records']
    assert set(picks)=={r['id']for r in manifest['records']}and len(picks)==48
    output=[];keys=['outer_psi_10_text_centroid','lower_striped_ball_print_centroid']
    for rec in manifest['records']:
        ident=rec['id'];v=picks[ident];anchors={};box=rec['native_crop_xyxy'];size=rec['resized_native_crop_size'];off=rec['display_offset']
        for i,key in enumerate(keys):
            view=v[i]
            native=[box[0]+(view[0]-off[0])*(box[2]-box[0])/size[0],
                    box[1]+(view[1]-off[1])*(box[3]-box[1])/size[1]]if view is not None else None
            anchors[key]=dict(native_xy=native,view_xy=view,visibility=v[2+i],uncertainty_native_px=v[4+i],
                reason='Center supported by visible printed glyph/contour; larger uncertainty for partial visibility'if view is not None else'Insufficient visual evidence; hidden center not inferred')
        accepted=all(a['native_xy']is not None for a in anchors.values())
        output.append(dict(id=ident,source_sha256=rec['source_sha256'],anchors=anchors,accepted=accepted,
            reason='Two visually supported named static print centers'if accepted else'At least one static print center not reliably visible',
            reference_id='D_002',axis_semantics='bottom striped-ball center TO top outer10text center',
            angle_convention='Image xright/ydown; atan2(top_y-bottom_y,top_x-bottom_x), clockwise positive',
            method='AI_VISUAL_NATIVE_CROP_METADATA_MASKED_NOT_GENUINELY_BLIND',
            point_selection_used_pressure_or_predictions=False,
            uncertainty_is_certified_error_bound=False,human_certified_gold=False,
            use='Visual-reference substitution diagnostic only; not deployed inference/training gold',
            view_file=rec['view_file'],view_sha256=rec['view_sha256']))
    ref=next(r for r in output if r['id']=='D_002')
    def axis(row):
        a=row['anchors'];t=a[keys[0]]['native_xy'];b=a[keys[1]]['native_xy']
        return math.degrees(math.atan2(t[1]-b[1],t[0]-b[0]))%360
    refangle=axis(ref)
    for row in output:
        row['absolute_image_print_axis_angle_deg']=axis(row)if row['accepted']else None
        row['relative_print_roll_deg']=(axis(row)-refangle+180)%360-180 if row['accepted']else None
    (HERE/'print_annotations.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in output),'utf-8')
    write(HERE/'reference_D002.json',ref)
    qa=HERE/'qa';qa.mkdir(exist_ok=True)
    font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',24)
    for group in ['D','E','F']:
        selected=[r for r in output if r['id'].startswith(group+'_')]
        for start in range(0,16,4):
            page=Image.new('RGB',(1084,1164),'white');draw=ImageDraw.Draw(page)
            for j,r in enumerate(selected[start:start+4]):
                col=j%2;rr=j//2;x=20+col*532;y=20+rr*572
                im=Image.open(HERE/r['view_file']).convert('RGB');d=ImageDraw.Draw(im)
                for key,color in zip(keys,[(255,0,255),(0,255,255)]):
                    pt=r['anchors'][key]['view_xy']
                    if pt is not None:
                        px,py=pt;d.line((px-7,py,px+7,py),fill=color,width=1);d.line((px,py-7,px,py+7),fill=color,width=1)
                draw.text((x,y),r['id'],font=font,fill='black');page.paste(im,(x,y+40))
            page.save(qa/f'{group}_page{start//4+1:02d}.png')
    summary=dict(status='AI_VISUAL_TRAIN_PRINT_SIDECAR_COMPLETE_NOT_GOLD_OR_AUTOMATIC_RESULT',images=48,
        accepted=sum(r['accepted']for r in output),rejected=sum(not r['accepted']for r in output),
        groups={g:dict(images=16,accepted=sum(r['accepted']for r in output if r['id'].startswith(g+'_')))for g in ['D','E','F']},
        source_sha256=dict(view_manifest=sha(HERE/'view_manifest.json'),picks=sha(HERE/'visual_picks.json'),
            exporter=sha(__file__),annotations=sha(HERE/'print_annotations.jsonl'),reference=sha(HERE/'reference_D002.json')),
        reference_id='D_002',pressure_or_prediction_metadata_displayed=False,history_exposure_not_blind=True,
        original_images_or_canonical_modified=False,ABC_H_opened=False,model_training=False,calibration_fit_performed=False,
        coordinate_transform='Native crop/resize mapping, no angle/pressure inversion')
    write(HERE/'completion.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
