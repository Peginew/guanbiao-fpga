"""One frozen TRAIN-template ROI128 printed-point NCC candidate.

No network training or native-query/GT/PSI access. G is an explicit one-pass
prediction command after TRAIN setup and synthetic preflight; no retuning loop.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,math,sys,time
sys.dont_write_bytecode=True
import cv2
import numpy as np

HERE=Path(__file__).resolve().parent;TASK=HERE.parent;ROOT=TASK.parents[1]
DATA=ROOT/'algorithm_work/meter_cnn_training_20261102'
OLD=ROOT/'algorithm_work/meter_pointer_readout_20261102/polar_angle/run_001'
NAMES=('outer_psi_5_text_centroid','outer_psi_10_text_centroid','outer_psi_15_text_centroid',
       'upper_basketball_logo_centroid','middle_soccer_logo_centroid','lower_striped_ball_print_centroid')
COMMON=NAMES[:3]+(NAMES[-1],)
BASE_CONFIG=dict(candidate='ONE_D025_STATIC_PRINT_LOCAL_NCC',template_id='D_025',zero_id='D_002',
    query_inputs=['U8ROI128','frozen_original_predicted_hub','locator_radius'],
    normalizing_center=[64.,64.],normalizing_radius=48.,
    local_contrast=dict(width=9,gain=3,border='replicate',before_canonical_warp=True),
    text_patch_width=17,logo_patch_width=13,patch_warp='bilinear around source anchor, border128',
    rotations='[-24-offset,+24-offset], outward multiplesof4degrees, offset=D002->D025 TRAINfit',
    rotation_step_deg=4,translation_radius_per_rotation=20,
    expected_position_rotates_about_C64_together_with_patch=True,
    NCC_method='Masked zero-mean NCC via 3 OpenCV TM_CCORR sums, score is NOT calibrated probability',
    logo_mask='Fixed circle radius5 in13x13 patch excludes TRAINadjacent needle corner',
    text_mask='All17x17 pixels',minimum_query_variance_per_mask_pixel=.01,
    minimum_NCC=.68,minimum_spatial_margin=.06,second_peak_exclusion_radius=6.,
    minimum_train_patch_stddev=8.,subpixel_refinement='bounded 3pointparabola +/-0.5pixel when finite neighbours',
    query_known_needle_required=False,query_manual_visibility_used=False,
    query_native_frame_used=False,query_pressure_or_GTpoints_used=False,
    template_selection='Single fixed D025 observed clean TRAINimage; D002 known contaminated logos are NEVERpatches',
    threshold_selection='Fixed before anyGprediction, no adaptation fromG labels/errors',
    geometry_or_READ_permission='ROOT consensus; these outputs are perpoint evidence only',
    full_integer_or_MCU_implementation=False)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def rows(p):return[json.loads(s)for s in Path(p).read_text('utf-8-sig').splitlines()if s.strip()]
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')
def module(name,p):
    s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m

def material(split):
    assert split in {'train','validation'}
    recs=rows(DATA/f'prepared_{split}.jsonl')
    wanted={'D','E','F'}if split=='train'else{'G'}
    assert all(r['source_group']in wanted for r in recs)
    preds={r['id']:r for r in rows(OLD/f'{split}_predictions.jsonl')}
    z=np.load(DATA/f'roi_cache_{split}.npz');images=dict(zip(z['ids'].tolist(),z['images']))
    return[dict(id=r['id'],split=split,source_sha256=r['sha256'],radius=float(r['roi_request']['radius']),
        image=images[r['id']],hub=np.asarray(preds[r['id']]['hub_roi'],np.float64),
        crop_origin=[r['roi_request']['x0'],r['roi_request']['y0']],stride=r['roi_request']['stride'])
        for r in recs if r['id']in preds]

def canonical_point(point,hub,radius):
    return(np.asarray(point,np.float64)-hub)*48./radius+64.

def native_point_to_roi(point,item):
    return(np.asarray(point,np.float64)-item['crop_origin']-(item['stride']-1)/2)/item['stride']

def local_contrast(gray):
    mean=cv2.boxFilter(gray,cv2.CV_16S,(9,9),normalize=True,borderType=cv2.BORDER_REPLICATE)
    return np.clip((gray.astype(np.int16)-mean)*3+128,0,255).astype(np.uint8)

def canonical_image(gray,hub,radius):
    scale=48./float(radius)
    m=np.array([[scale,0,64-hub[0]*scale],[0,scale,64-hub[1]*scale]],np.float64)
    return cv2.warpAffine(local_contrast(gray),m,(128,128),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=128)

def expected_point(point,delta):
    a=math.radians(delta);R=np.array([[math.cos(a),-math.sin(a)],[math.sin(a),math.cos(a)]])
    return 64+R@(np.asarray(point)-64)

def bank_degrees(offset):
    return list(range(4*math.floor((-24-offset)/4),4*math.ceil((24-offset)/4)+1,4))

def serialize_fit(fit):
    return{k:v.tolist()if isinstance(v,np.ndarray)else v for k,v in fit.items()}

def body_mask(width,is_logo):
    yy,xx=np.mgrid[:width,:width];half=width//2
    return(((xx-half)**2+(yy-half)**2<=25)if is_logo else np.ones((width,width),bool)).astype(np.float32)

def masked_ncc(region,template,mask):
    mass=float(mask.sum());td=template.astype(np.float64)
    mean=float((td*mask).sum()/mass)
    t=((td-mean)*mask).astype(np.float32)
    energy=float((t.astype(np.float64)**2).sum())
    if energy<1e-6:return np.full((region.shape[0]-template.shape[0]+1,region.shape[1]-template.shape[1]+1),-np.inf,np.float32)
    sumq=cv2.matchTemplate(region,mask,cv2.TM_CCORR).astype(np.float64)
    sumq2=cv2.matchTemplate(region*region,mask,cv2.TM_CCORR).astype(np.float64)
    numerator=cv2.matchTemplate(region,t,cv2.TM_CCORR).astype(np.float64)
    variance=sumq2-sumq*sumq/mass
    score=np.full(variance.shape,-np.inf,np.float64)
    good=variance>mass*.01
    score[good]=np.clip(numerator[good]/np.sqrt(variance[good]*energy),-1,1)
    return score.astype(np.float32)

def prepare(ref002,ref025):
    assert not(HERE/'predictions.jsonl').exists(),'Candidate already evaluated; no setup/threshold revision afterG'
    tr={r['id']:r for r in material('train')};a=load(ref002);b=load(ref025)
    assert a['id']=='D_002'and b['id']=='D_025'
    assert a['source_sha256']==tr['D_002']['source_sha256']and b['source_sha256']==tr['D_025']['source_sha256']
    def points(rec):
        it=tr[rec['id']];out={}
        for name in NAMES:
            anchor=rec['anchors'][name]
            point=anchor.get('native_xy')
            if point is not None:out[name]=canonical_point(native_point_to_roi(point,it),it['hub'],it['radius']).tolist()
        return out
    p002=points(a);p025=points(b)
    assert all(n in p002 and n in p025 for n in COMMON)
    geometry=module('ncc_train_only_geometry',TASK/'landmark_geometry.py')
    fit=geometry.fit_similarity([p002[n]for n in COMMON],[p025[n]for n in COMMON])
    offset=float(fit['rotation_deg']);degrees=bank_degrees(offset)
    gray=canonical_image(tr['D_025']['image'],tr['D_025']['hub'],tr['D_025']['radius'])
    templates={};patches=[];centers=[];widths=[];masks=[]
    for name in NAMES:
        anchor=b['anchors'][name]
        assert name in p025 and anchor.get('template_usable',True),name
        point=p025[name];width=17 if name in NAMES[:3] else 13
        mask=body_mask(width,name not in NAMES[:3])
        patch=cv2.getRectSubPix(gray,(width,width),tuple(map(float,point)))
        masked_std=float(patch[mask.astype(bool)].std())
        assert masked_std>=8.,f'UninformativeTRAINmaskedpatch:{name}'
        bank=[]
        for degree in degrees:
            # OpenCVpositive angle is counterclockwise; image angles hereCW.
            M=cv2.getRotationMatrix2D(tuple(map(float,point)),-degree,1.)
            rotated=cv2.warpAffine(gray,M,(128,128),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=128)
            bank.append(cv2.getRectSubPix(rotated,(width,width),tuple(map(float,point))).astype(np.float32))
        templates[name]=dict(width=width,center_normalized=point,TRAIN_masked_patch_stddev=masked_std,mask_pixels=int(mask.sum()))
        patches.append(np.stack(bank));centers.append(point);widths.append(width);masks.append(mask)
    np.savez(HERE/'train_templates.npz',**{f'bank_{i}':p for i,p in enumerate(patches)},
        **{f'mask_{i}':m for i,m in enumerate(masks)},canonical_image=gray,degrees=np.asarray(degrees),centers=np.asarray(centers),widths=np.asarray(widths))
    config=dict(BASE_CONFIG,rotation_bank_deg=degrees,rotation_bank_count=len(degrees),
        canonical_roll_relative_D002=offset)
    setup=dict(status='FROZEN_TRAIN_ONLY_TEMPLATE_SETUP_BEFORE_G',config=config,
        canonical_points_normalized=p025,canonical_roll_relative_D002=offset,
        reference_D002_points_normalized=p002,
        common_alignment_identities=COMMON,D002_to_D025_train_similarity=serialize_fit(fit),
        per_identity_templates=templates,
        source_sha256=dict(reference_D002=sha(ref002),reference_D025=sha(ref025),
            prepared_train=sha(DATA/'prepared_train.jsonl'),train_cache=sha(DATA/'roi_cache_train.npz'),
            train_original_hub_predictions=sha(OLD/'train_predictions.jsonl'),
            original_hub_weights=sha(DATA/'run_002/best_weights.pt'),
            original_polar_weights=sha(OLD/'best_weights.pt'),geometry_code=sha(TASK/'landmark_geometry.py'),
            code=sha(__file__),templates=sha(HERE/'train_templates.npz')),
        native_annotations_only_define_TRAIN_setup=True,query_GT_points_or_pressure_used=False,
        H_ABC_opened=False,model_training=False,hardware_actions=False)
    write(HERE/'setup.json',setup);write(HERE/'config_frozen_before_G.json',config)
    from PIL import Image,ImageDraw,ImageFont
    canvas=Image.new('RGB',(900,320),'white');draw=ImageDraw.Draw(canvas);font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',16)
    for i,name in enumerate(NAMES):
        p=cv2.getRectSubPix(gray,(widths[i],widths[i]),tuple(map(float,centers[i])))
        p=np.where(masks[i]>0,p,128).astype(np.uint8)
        canvas.paste(Image.fromarray(p).convert('RGB').resize((130,130)),(10+148*i,50))
        draw.text((10+148*i,10),name.split('_')[0]+' '+('text'if i<3 else'logo'),fill='black',font=font)
        draw.text((10+148*i,195),'mstd='+str(round(templates[name]['TRAIN_masked_patch_stddev'],1)),fill='black',font=font)
    canvas.save(HERE/'train_patch_contact.png')
    print(json.dumps(dict(setup_sha256=sha(HERE/'setup.json'),offset_D002_to_D025=offset,bank=degrees,templates=templates),indent=2))

class Locator:
    def __init__(self):
        self.setup=load(HERE/'setup.json');self.config=self.setup['config']
        assert self.setup['source_sha256']['code']==sha(__file__)
        assert self.setup['source_sha256']['templates']==sha(HERE/'train_templates.npz')
        z=np.load(HERE/'train_templates.npz');self.degrees=z['degrees'].tolist()
        self.banks=[z[f'bank_{i}']for i in range(6)];self.masks=[z[f'mask_{i}']for i in range(6)];self.centers=z['centers'];self.widths=z['widths']
    def infer(self,gray,hub,radius):
        assert gray.shape==(128,128)and gray.dtype==np.uint8
        if not np.isfinite(hub).all()or not np.isfinite(radius)or radius<=0:raise ValueError('invalidinputgeometry')
        im=canonical_image(gray,hub,radius).astype(np.float32);points={};products=0;positions=0
        for index,name in enumerate(NAMES):
            width=int(self.widths[index]);half=width//2
            scores=np.full((128,128),-np.inf,np.float32);winner=np.full((128,128),-1,np.int16)
            for bank_index,degree in enumerate(self.degrees):
                ex,ey=np.rint(expected_point(self.centers[index],degree)).astype(int)
                x0=max(half,ex-20);x1=min(127-half,ex+20)
                y0=max(half,ey-20);y1=min(127-half,ey+20)
                if x1<x0 or y1<y0:continue
                region=im[y0-half:y1+half+1,x0-half:x1+half+1]
                score=masked_ncc(region,self.banks[index][bank_index],self.masks[index])
                score=np.nan_to_num(score,nan=-np.inf,posinf=-np.inf,neginf=-np.inf)
                current=scores[y0:y1+1,x0:x1+1];better=score>current
                current[better]=score[better];winner[y0:y1+1,x0:x1+1][better]=bank_index
                positions+=score.size;products+=score.size*width*width
            iy,ix=np.unravel_index(int(scores.argmax()),scores.shape);peak=float(scores[iy,ix])
            yy,xx=np.mgrid[:128,:128];far=scores.copy();far[(xx-ix)**2+(yy-iy)**2<=6**2]=-np.inf
            second=float(far.max());margin=peak-second if np.isfinite(second)else None
            sufficient=bool(np.isfinite(peak)and peak>=.68 and margin is not None and margin>=.06)
            px=float(ix);py=float(iy)
            if np.isfinite(peak):
                for axis in [0,1]:
                    minus=(iy,ix-1)if axis==0 else(iy-1,ix)
                    plus=(iy,ix+1)if axis==0 else(iy+1,ix)
                    if min(minus+plus)<0 or max(minus+plus)>=128:continue
                    l=float(scores[minus]);rr=float(scores[plus]);den=l-2*peak+rr
                    if np.isfinite(l)and np.isfinite(rr)and den<0:
                        shift=float(np.clip(.5*(l-rr)/den,-.5,.5))
                        if axis==0:px+=shift
                        else:py+=shift
            normalized=[px,py]if np.isfinite(peak)else None
            roi=((np.asarray(normalized)-64)*radius/48+hub).tolist()if normalized is not None else None
            reason='LOCAL_NCC_IDENTITY_EVIDENCE_SUFFICIENT'if sufficient else'LOCAL_NCC_IDENTITY_EVIDENCE_INSUFFICIENT'
            points[name]=dict(accepted=sufficient,normalized_xy=normalized if sufficient else None,
                roi_xy=roi if sufficient else None,candidate_normalized_xy=normalized,candidate_roi_xy=roi,
                score=peak if np.isfinite(peak)else None,second_peak_score=second if np.isfinite(second)else None,
                margin=margin,evidence='sufficient'if sufficient else'insufficient',reason=reason,
                score_is_probability=False,physical_occlusion_diagnosed=False,
                winning_template_rotation_deg=self.degrees[int(winner[iy,ix])]if winner[iy,ix]>=0 else None)
        return dict(points=points,cost=dict(candidate_centers_evaluated=positions,nominal_patch_pixel_products=products))

def preflight():
    loc=Locator();train={r['id']:r for r in material('train')};it=train['D_025']
    result=loc.infer(it['image'],it['hub'],it['radius'])
    checks=[]
    for delta in [-24.,24.]:
        p=np.array([110.,64.]);expected=expected_point(p,delta)
        assert abs(np.linalg.norm(expected-[64,64])-46)<1e-10
        assert np.sign(expected[1]-64)==np.sign(delta)
        M=cv2.getRotationMatrix2D((64.,64.),-delta,1.)
        assert np.linalg.norm(M@np.r_[p,1]-expected)<1e-10
        checks.append(dict(delta=delta,expected_point=expected.tolist(),same_CV_patch_rotation=True))
    blank=loc.infer(np.full((128,128),128,np.uint8),it['hub'],it['radius'])
    assert not any(p['accepted']for p in blank['points'].values()),'constantimage must not supply landmarkevidence'
    hidden_name='middle_soccer_logo_centroid'
    center=(np.asarray(loc.setup['canonical_points_normalized'][hidden_name])-64)*it['radius']/48+it['hub']
    occluded=it['image'].copy();x,y=np.rint(center).astype(int)
    occluded[max(0,y-11):min(128,y+12),max(0,x-11):min(128,x+12)]=128
    masked=loc.infer(occluded,it['hub'],it['radius'])
    rng=np.random.default_rng(1108);masked_oracle=[]
    for width,is_logo in [(17,False),(13,True)]:
        mask=body_mask(width,is_logo);template=rng.integers(0,256,(width,width)).astype(np.float32)
        region=rng.integers(0,256,(width+4,width+5)).astype(np.float32)
        got=masked_ncc(region,template,mask);want=np.empty(got.shape,np.float64)
        tv=template[mask>0].astype(np.float64);tv-=tv.mean()
        for yy in range(got.shape[0]):
            for xx in range(got.shape[1]):
                qv=region[yy:yy+width,xx:xx+width][mask>0].astype(np.float64);qv-=qv.mean()
                want[yy,xx]=np.dot(qv,tv)/math.sqrt(np.dot(qv,qv)*np.dot(tv,tv))
        error=float(np.max(abs(got-want)));assert error<1e-5,error
        constant=masked_ncc(np.full_like(region,128),template,mask)
        assert not np.any(constant>=.68)
        t=(template.astype(np.float64)-template[mask>0].astype(np.float64).mean())*mask
        assert abs(t.sum())<1e-8
        masked_oracle.append(dict(width=width,mask_pixels=int(mask.sum()),windows=got.size,max_error=error,template_zero_sum=float(t.sum())))
    report=dict(status='TRAIN_SELF_AND_SYNTHETIC_POSITION_ROTATION_PREFLIGHT_ONLY',
        train_id='D_025',train_self_predictions=result,rotation_checks=checks,
        masked_NCC_direct_window_oracle=masked_oracle,
        constant_unknown_input=blank,
        artificial_train_occluder=dict(identity=hidden_name,ROI_center=center.tolist(),halfwidth=11,
            predictions=masked,visibility_is_not_inference_input=True,
            caution='A surviving point candidate underocclusion is potentiallywrong, not physicalvisibilityproof; ROOTconsensus remainsrequired'),
        source_sha256=dict(setup=sha(HERE/'setup.json'),code=sha(__file__)),
        not_an_independent_accuracy_test=True,G_opened=False,training=False)
    write(HERE/'preflight.json',report)
    print(json.dumps(dict(self_supported_identities=sum(p['accepted']for p in result['points'].values()),checks=checks),indent=2))

def predict():
    assert not(HERE/'predictions.jsonl').exists(),'OneGpass already executed; no automatic re-evaluation'
    cv2.setNumThreads(1);loc=Locator();allrows=[];times=[];costs=[]
    for split in ['train','validation']:
        for it in material(split):
            t=time.perf_counter();out=loc.infer(it['image'],it['hub'],it['radius']);elapsed=time.perf_counter()-t
            allrows.append(dict(id=it['id'],split=split,source_sha256=it['source_sha256'],
                hub_roi=it['hub'].tolist(),locator_radius=it['radius'],points=out['points'],
                PC_elapsed_s=elapsed,work=out['cost'],setup_sha256=sha(HERE/'setup.json'),
                query_uses_GT_points=False,query_uses_manual_visibility=False,query_uses_pressure=False,
                query_uses_native_frame=False))
            times.append(elapsed);costs.append(out['cost'])
    assert sum(r['split']=='validation'for r in allrows)==59
    (HERE/'predictions.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in allrows),'utf-8')
    bank_elements=sum(b.size for b in loc.banks)
    report=dict(status='ONE_FROZEN_LOCAL_NCC_PASS_NOT_PSI_OR_MCU_ACCEPTANCE',rows=len(allrows),G_rows=59,
        supported_points_G=sum(p['accepted']for r in allrows if r['split']=='validation'for p in r['points'].values()),
        cost=dict(template_bank_elements=bank_elements,FP32template_bytes=bank_elements*4,
            hypothetical_INT8_bank_bytes_NOT_IMPLEMENTED=bank_elements,
            canonical_U8_image_bytes=16384,actual_query_FP32_image_bytes=65536,
            single_identity_score_FP32_map_bytes=65536,single_identity_winner_S16_map_bytes=32768,
            maximum_candidate_centers=max(c['candidate_centers_evaluated']for c in costs),
            maximum_nominal_patch_pixel_products=max(c['nominal_patch_pixel_products']for c in costs),
            nominal_three_correlation_direct_products=3*max(c['nominal_patch_pixel_products']for c in costs),
            correlation_calls_per_bank=3,FP32mask_bytes=sum(m.nbytes for m in loc.masks),
            per_identity_mgrid_two_I64_arrays_bytes=262144,
            per_identity_far_FP32_copy_bytes=65536,
            maximum_query_region_squared_FP32_bytes=57*57*4,
            maximum_five_masked_NCC_FP64_result_arrays_bytes=5*41*41*8,
            minimum_explicit_PC_image_score_winner_far_mgrid_bytes=65536+65536+32768+65536+262144,
            actual_PC_peak_RAM_unmeasured=True,
            operation_count_note='Patchproducts field is one direct-correlation equivalent; actual maskedNCC computes3correlations plusvariance/divide/sqrt. OpenCV internal algorithm/MCUcycles are not measured.',
            PC_mean_ms=float(np.mean(times)*1000),PC_max_ms=float(max(times)*1000),
            OpenCV_internal_buffers_not_measured=True,MCU_cycles_or_link_fit_not_proven=True),
        source_sha256=dict(setup=sha(HERE/'setup.json'),config=sha(HERE/'config_frozen_before_G.json'),
            code=sha(__file__),predictions=sha(HERE/'predictions.jsonl'),templates=sha(HERE/'train_templates.npz')),
        no_G_threshold_or_template_changes=True,training=False,H_ABC_opened=False,hardware_actions=False,
        old_models_old_ring_old_calibration_changed=False)
    write(HERE/'completion.json',report);print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=['prepare','preflight','predict']);
    ap.add_argument('--reference-d002',type=Path);ap.add_argument('--reference-d025',type=Path);a=ap.parse_args()
    if a.command=='prepare':prepare(a.reference_d002,a.reference_d025)
    elif a.command=='preflight':preflight()
    else:predict()
