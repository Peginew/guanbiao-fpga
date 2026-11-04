"""AI visual annotations assisted by bounded OpenCV proposals; never trains."""
from pathlib import Path
from datetime import datetime, timezone
import json, math, hashlib
import numpy as np
import cv2
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
ROWS = json.loads((ROOT / 'proposals.json').read_text(encoding='utf-8'))
NEGATIVE = {'A_048':'empty_scene','A_049':'circular_non_gauge','A_050':'circular_non_gauge',
            'B_049':'empty_scene','B_050':'circular_non_gauge','B_051':'circular_non_gauge',
            'C_046':'empty_scene','C_047':'circular_non_gauge','C_059':'circular_non_gauge'}
# These direction priors were independently read from the visible thin shaft in
# the contact crops. They do not use pressure values, calibration, or FPGA OSD.
ANGLES = {
'A':[-70,-67,-70,-64,-63,-72,-79,-80,-81,-77,-80,-95,-96,-94,-94,-91,-93,-116,-116,-113,-107,-111,-105,-143,-142,-141,-142,-143,-141,-166,-163,-164,-163,-164,-162,-179,-179,-177,-179,-179,-178,167,166,175,176,174,178,None,None,None,174,174,174,178,180,180,175,180,-66],
'B':[-62,-60,-62,-60,-61,-60,-77,-74,-76,-75,-73,-73,-94,-92,-93,-92,-92,-90,-113,-115,-119,-114,-114,-112,-140,-139,-140,-140,-141,-140,-162,-159,-160,-160,-161,-159,-177,-175,-175,-175,-178,-172,166,174,173,174,168,174,None,None,None,173,174,176,176,180,180,180,180],
'C':[-66,-70,-69,-86,-86,-86,-86,-85,-85,-104,-103,-105,-102,-102,-104,-127,-127,-129,-123,-116,-114,-145,-145,-145,-145,-143,-145,-164,-163,-164,-164,-164,-161,173,176,180,178,180,180,169,172,171,168,162,166,None,None,165,165,165,165,165,165,165,165,-63,-64,-67,None]
}
assert all(len(v)==59 for v in ANGLES.values())
BIG = {'A_051':([43,0,914,720],[480,420],[190,443]),
       'B_052':([112,0,1056,720],[565,350],[247,376]),
       'C_048':([123,0,1051,720],[568,451],[233,527])}
SMALL = {'A_052','B_053','C_049'}
HUB_OCCLUDED = {'A_055','A_056','B_056','B_057','C_052','C_053'}
TIP_OCCLUDED = {'A_057','A_058','B_058','B_059','C_054','C_055'}
HUB_UNRESOLVED_GLARE = {'A_053','C_050','C_051'}
SUPPLEMENTS = {'A_059':12.0,'C_056':12.0,'C_057':12.0,'C_058':12.0}
MANUAL = {
 'A_009':([518,168,762,410],[638,286],[659,222]),
 'A_012':([496,195,752,450],[620,319],[612,224]),
 'A_018':([553,230,805,485],[675,354],[632,273]),
 'A_028':([564,173,904,480],[745,322],[671,258]),
 'A_034':([466,164,778,466],[624,313],[526,279]),
 'A_047':([507,220,797,515],[642,364],[553,366]),
 'A_057':([487,144,789,448],[635,285],[528,295]),
 'B_011':([495,144,792,422],[646,278],[673,185]),
 'B_018':([390,138,675,419],[520,274],[518,178]),
 'B_023':([454,144,747,425],[598,278],[553,188]),
 'B_029':([471,143,774,433],[623,281],[550,217]),
 'B_035':([489,146,791,427],[646,283],[550,245]),
 'B_041':([462,159,774,460],[616,307],[512,298]),
 'B_042':([426,154,742,442],[565,294],[477,277]),
 'B_048':([393,234,700,512],[529,368],[441,378]),
 'C_031':([317,129,601,411],[453,267],[350,241]),
 'C_033':([312,122,644,432],[455,271],[362,234]),
 'C_039':([287,128,593,426],[422,271],[332,264]),
 'C_045':([374,139,655,405],[489,270],[412,290]),
}
PRESSURES = [12.,11.,9.5,8.,6.5,5.,3.5,2.5]
CONDITIONS = ['frontal_standard','frontal_close','low_light','backlit','left_oblique','right_oblique']

def pressure_slot(ident):
    g,n=ident.split('_');n=int(n)
    if g=='A':
        if n<=5:return 0,[0,1,2,4,5][n-1]
        if n<=47:return 1+(n-6)//6,(n-6)%6
        if n==59:return 0,3
    if g=='B' and n<=48:return (n-1)//6,(n-1)%6
    if g=='C':
        if n<=3:return 0,n+2
        if n<=45:return 1+(n-4)//6,(n-4)%6
        if n in (56,57,58):return 0,{56:0,57:2,58:1}[n]
    return None

def kp(xy, visibility='visible', uncertainty=5, method='ai_visual_review_with_opencv_assistance'):
    return {'xy':None if xy is None else [round(float(xy[0]),1),round(float(xy[1]),1)],
            'visibility':visibility,'uncertainty_px':None if xy is None else uncertainty,
            'annotation_source':method}

def rim_radius(gray, c):
    x,y,r=c
    if r>250:return r
    gx=cv2.Sobel(gray.astype(np.float32),cv2.CV_32F,1,0,ksize=3)
    gy=cv2.Sobel(gray.astype(np.float32),cv2.CV_32F,0,1,ksize=3)
    theta=np.linspace(0,2*np.pi,160,endpoint=False);co=np.cos(theta);si=np.sin(theta)
    values=[]
    for rr in np.arange(r*.92,r*1.22+1,1):
        xx=np.rint(x+rr*co).astype(int);yy=np.rint(y+rr*si).astype(int)
        valid=(xx>2)&(xx<1277)&(yy>40)&(yy<580)&~((xx>700)&(yy<210))
        ix=np.clip(xx,0,1279);iy=np.clip(yy,0,719)
        v=np.abs(gx[iy,ix]*co+gy[iy,ix]*si)[valid]
        score=float(np.minimum(v,400).mean()) if len(v)>55 else 0
        values.append((rr,score))
    peak=max(v[1] for v in values)
    good=[rr for rr,s in values if s>=peak*.80]
    return float(max(good)) if good else r

def hub_proposal(gray, c):
    x,y,r=c
    margin=max(20,int(r*.19));x0=max(0,int(x)-margin);y0=max(0,int(y)-margin)
    patch=gray[y0:min(720,int(y)+margin+1),x0:min(1280,int(x)+margin+1)]
    if patch.size==0:return [x,y],False
    patch=cv2.GaussianBlur(patch,(3,3),.6)
    rings=cv2.HoughCircles(patch,cv2.HOUGH_GRADIENT,dp=1,minDist=10,
                          param1=80,param2=10,minRadius=max(4,int(r*.04)),maxRadius=max(6,int(r*.13)))
    if rings is not None:
        candidates=[]
        for xx,yy,rr in rings[0]:
            xx+=x0;yy+=y0;dist=math.hypot(xx-x,yy-y)
            if dist<r*.17:candidates.append((dist,float(xx),float(yy)))
        if candidates:
            _,xx,yy=min(candidates);return [xx,yy],True
    return [x,y],False

def pointer_proposal(gray, hub, radius, prior):
    g=cv2.GaussianBlur(gray.astype(np.float32),(3,3),.6)
    hx,hy=hub;rr=np.arange(radius*.22,radius*.78,.8)
    best=None
    for angle in np.arange(prior-9,prior+9.01,.25):
        t=math.radians(angle);co=math.cos(t);si=math.sin(t)
        xs=hx+rr*co;ys=hy+rr*si
        def sample(x,y):
            return cv2.remap(g,x.astype(np.float32)[None,:],y.astype(np.float32)[None,:],cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)[0]
        center=sample(xs,ys);off=max(3.0,radius*.026)
        sides=(sample(xs-off*si,ys+off*co)+sample(xs+off*si,ys-off*co))/2
        contrast=sides-center
        score=float(np.clip(contrast,-25,95).mean())
        if best is None or score>best[0]:best=(score,angle)
    score,angle=best;t=math.radians(angle);co=math.cos(t);si=math.sin(t)
    # The long reading end usually terminates near the inner tick annulus.
    # Its precise end is visually reviewed in overlays, not certified by score.
    rr=np.arange(radius*.48,radius*.88,.5)
    xs=hx+rr*co;ys=hy+rr*si;off=max(3.0,radius*.022)
    def samp(x,y):return cv2.remap(g,x.astype(np.float32)[None,:],y.astype(np.float32)[None,:],cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)[0]
    contrast=(samp(xs-off*si,ys+off*co)+samp(xs+off*si,ys-off*co))/2-samp(xs,ys)
    good=np.where(contrast>max(12,score*.45))[0]
    length=float(rr[good[-1]]) if len(good) else radius*.72
    length=min(length,radius*.82)
    return [hx+length*co,hy+length*si],score,angle

records=[]
for row in ROWS:
    ident=row['id'];im=np.array(Image.open(row['path']).convert('RGB'));gray=cv2.cvtColor(im,cv2.COLOR_RGB2GRAY)
    record={'id':ident,'image_path':row['path'],'sha256':hashlib.sha256(Path(row['path']).read_bytes()).hexdigest(),
            'width':1280,'height':720,'image_kind':'gauge_front','negative_kind':None,
            'bbox_native_xyxy':None,'bbox_coordinate_convention':'half_open_xyxy',
            'bbox_annotation_source':'ai_visual_review_of_opencv_proposal_not_user_GT',
            'bbox_uncertainty_px':8,'keypoints':{},'condition':[],
            'review_status':'ai_visual_reviewed_with_uncertainty','human_ground_truth_certified':False,
            'pressure':{'value':None,'unit':None,'source':'unknown','capture_order':'descending_high_to_low_user_statement'},
            'notes':[],'training_performed':False}
    if ident in NEGATIVE:
        record.update(image_kind='negative',negative_kind=NEGATIVE[ident],bbox_uncertainty_px=None)
        record['keypoints']={'hub':kp(None,'absent'),'thin_terminal':kp(None,'absent')}
        record['notes'].append('Visually reviewed non-gauge image; mirror/back-facing round article is not a readable front dial.')
    else:
        c=row['proposal_circle'];x,y,r=c;r=rim_radius(gray,c)
        record['bbox_native_xyxy']=[max(0,int(math.floor(x-r))),max(0,int(math.floor(y-r))),min(1280,int(math.ceil(x+r))+1),min(720,int(math.ceil(y+r))+1)]
        hub,found=hub_proposal(gray,c)
        # If the ring is not separately resolvable, it remains a coarse visual
        # center annotation, with explicitly larger uncertainty.
        record['keypoints']['hub']=kp(hub,uncertainty=15)
        record['hub_proposal_ring_found']=found
        prior=ANGLES[row['group']][int(ident[-3:])-1]
        tip,score,angle=pointer_proposal(gray,hub,r,prior)
        record['keypoints']['thin_terminal']=kp(tip,uncertainty=12)
        record['keypoints']['hub']['precision_status']='coarse_AI_visual_reviewed_CV_proposal'
        record['keypoints']['thin_terminal']['precision_status']='coarse_AI_visual_reviewed_CV_proposal'
        record['pointer_proposal']={'contrast_score_not_probability':round(score,2),'angle_deg_image_clockwise':round(angle%360,2),'manual_visual_direction_prior_deg':prior}
        if score<9:
            record['keypoints']['thin_terminal']=kp(None,'unknown')
            record['condition'].append('low_contrast_or_unresolved_terminal');record['notes'].append('Do not infer thin terminal from pressure or counterweight.')
        if ident in BIG:
            bb,h,t=BIG[ident];record['bbox_native_xyxy']=bb;record['bbox_uncertainty_px']=18
            record['keypoints']={'hub':kp(h,uncertainty=12),'thin_terminal':kp(t,uncertainty=15)}
            record['condition']+=['very_large','frame_clipped','defocused']
        if ident in MANUAL:
            bb,h,t=MANUAL[ident];record['bbox_native_xyxy']=bb;record['bbox_uncertainty_px']=8
            record['keypoints']={'hub':kp(h,uncertainty=6,method='AI_manual_visual_native_image_correction'),
                                 'thin_terminal':kp(t,uncertainty=8,method='AI_manual_visual_native_image_correction')}
            record['notes'].append('Corrected on native image after rejecting a displaced circle/screw/text proposal.')
        if ident in SMALL:
            record['condition']+=['very_small','defocused'];record['bbox_uncertainty_px']=12
            record['keypoints']={'hub':kp(None,'unknown'),'thin_terminal':kp(None,'unknown')}
            record['notes'].append('Dial is present but the exact axis and terminal are not resolved at this scale.')
        if ident in HUB_OCCLUDED:
            record['keypoints']['hub']=kp(None,'occluded');record['condition'].append('physical_occlusion')
        if ident in HUB_UNRESOLVED_GLARE:
            record['keypoints']['hub']=kp(None,'unknown');record['condition'].append('severe_specular_overexposure')
        if ident in TIP_OCCLUDED:
            record['keypoints']['thin_terminal']=kp(None,'occluded');record['condition'].append('physical_occlusion')
        tipxy=record['keypoints']['thin_terminal']['xy']
        if tipxy and tipxy[0]>=704 and ((48<=tipxy[1]<64) or (112<=tipxy[1]<128) or (144<=tipxy[1]<160) or (176<=tipxy[1]<208)):
            record['keypoints']['thin_terminal']=kp(None,'occluded');record['condition'].append('OSD_occludes_terminal')
        # Existing colored FPGA rectangles/lines and telemetry are input-image
        # contamination; they were never read as object geometry or truth.
        record['notes'].append('FPGA OSD is present; its rectangles, needle overlays, coordinates and numerical readings are not annotation truth.')
        if ident in SUPPLEMENTS:
            record['pressure']={'value':SUPPLEMENTS[ident],'unit':'psi','source':'user_filename_or_explicit_chat_confirmation','capture_order':'supplement_not_inserted_into_monotone_sequence'}
        slot=pressure_slot(ident)
        if slot is not None:
            rank,ci=slot;record['pressure']={'value':PRESSURES[rank],'unit':'psi','source':'user_explicit_pressure_list_and_descending_sequence_with_supplement_replacement','capture_order':'descending_high_to_low'}
            record['pressure_rank']=rank+1;record['capture_condition']=CONDITIONS[ci]
            record['condition'].append(CONDITIONS[ci])
        else:
            record['pressure']={'value':2.5,'unit':'psi','source':'user_explicit_challenge_confirmation','capture_order':'challenge_after_pressure_sequence'}
            record['pressure_rank']=8;record['capture_condition']='challenge'
        record['pressure_psi']=record['pressure']['value']
        record['condition'].append('FPGA_OSD_present')
        record['bbox_frame_clipped']=record['bbox_native_xyxy'][0]==0 or record['bbox_native_xyxy'][1]==0 or record['bbox_native_xyxy'][2]==1280 or record['bbox_native_xyxy'][3]==720
    records.append(record)

annotation={'schema_version':'1.0-ai-visual-review','created_utc':datetime.now(timezone.utc).isoformat(),
            'scope':'A B C current images only; no training; all coordinates native1280x720',
            'coordinate_policy':'AI visual annotation plus bounded CV assistance, not independent human exact ground truth; uncertainty is mandatory.',
            'records':records}
(ROOT/'annotation.json').write_text(json.dumps(annotation,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
ov=ROOT/'overlays';ov.mkdir(exist_ok=True)
for rec in records:
    im=Image.open(rec['image_path']).convert('RGB');d=ImageDraw.Draw(im)
    bb=rec['bbox_native_xyxy']
    if bb:d.rectangle((bb[0],bb[1],bb[2]-1,bb[3]-1),outline='#00ff00',width=2)
    for name,color in [('hub','#ff00ff'),('thin_terminal','#00ffff')]:
        xy=rec['keypoints'][name]['xy']
        if xy:
            x,y=xy;d.ellipse((x-5,y-5,x+5,y+5),outline=color,width=2)
    h=rec['keypoints']['hub']['xy'];t=rec['keypoints']['thin_terminal']['xy']
    if h and t:d.line(tuple(h+t),fill='#ffff00',width=2)
    d.rectangle((0,700,620,719),fill='black');d.text((4,703),rec['id']+' AI annotation / uncertainty / not trained',fill='white')
    im.save(ov/(rec['id']+'.jpg'),quality=93)
for g in 'ABC':
    subset=[r for r in records if r['id'].startswith(g+'_')]
    for start in range(0,len(subset),16):
        sheet=Image.new('RGB',(1280,1408),'#222');d=ImageDraw.Draw(sheet)
        for j,rec in enumerate(subset[start:start+16]):
            im=Image.open(ov/(rec['id']+'.jpg')).convert('RGB');bb=rec['bbox_native_xyxy']
            if bb:
                x0,y0,x1,y1=bb;side=max(x1-x0,y1-y0)*1.1;cx=(x0+x1)/2;cy=(y0+y1)/2
                crop=(max(0,int(cx-side/2)),max(0,int(cy-side/2)),min(1280,int(cx+side/2)),min(720,int(cy+side/2)))
            else:crop=(0,0,1280,720)
            im=im.crop(crop);im.thumbnail((320,320));px=(j%4)*320;py=(j//4)*352
            sheet.paste(im,(px,py+32));d.text((px+3,py+3),rec['id']+' '+str(bb),fill='white')
            d.text((px+3,py+17),'H:'+rec['keypoints']['hub']['visibility']+' T:'+rec['keypoints']['thin_terminal']['visibility'],fill='white')
        sheet.save(ROOT/f'review_{g}_{start+1:03d}.jpg',quality=94)
summary={'images':len(records),'positive':sum(r['image_kind']=='gauge_front' for r in records),'negative':sum(r['image_kind']=='negative' for r in records),
         'visible_hub':sum(r['keypoints']['hub']['xy'] is not None for r in records),
         'visible_thin_terminal':sum(r['keypoints']['thin_terminal']['xy'] is not None for r in records),
         'user_pressure_labels':sum(r['pressure']['value'] is not None for r in records),'trained':False,'original_images_modified':False,
         'annotation_scope':'AI visual review with explicit uncertainty; root independent overlay review still required.'}
(ROOT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary))
