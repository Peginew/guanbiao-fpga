"""Integer sample/profile frontend reference for frozen multireference ringB.

Local9x9 normalization, Q5bilinear gather and rational S8 radialprofile math
areinteger. Currentcoordinate generation, hubdistance andoutside predicates
still reproduce FLOAT64/FLOAT32 geometry, explicitly not allintegergeometry.
Only known236D/E/F/G proxyROIs are opened; no device/learning/thresholdchanges.
"""
from pathlib import Path
import argparse,json,hashlib,time,sys
import cv2
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
DATA=ROOT/'algorithm_work/meter_cnn_training_20261102'
sys.path.insert(0,str(DATA));from roi_adapter import load_prepared

N_ANGLES=360;N_BANDS=12
HYPOTHESES=np.asarray([(dx,dy,scale)for dx in[-1.5,0,1.5]for dy in[-1.5,0,1.5]for scale in[.97,1.,1.03]],np.float64)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def write(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n','utf-8')

def normalize_local_u8(gray):
    """Exact integer nearest sum/81, replicateborder; sameCV16S box9 math."""
    g=np.asarray(gray,np.uint8)
    if g.shape!=(128,128):raise ValueError('requires128x128U8')
    pad=np.pad(g,4,mode='edge').astype(np.uint32)
    integ=np.pad(pad,((1,0),(1,0)),mode='constant').cumsum(0,dtype=np.uint32).cumsum(1,dtype=np.uint32)
    sums=integ[9:,9:]-integ[:-9,9:]-integ[9:,:-9]+integ[:-9,:-9]
    mean=((sums+40)//81).astype(np.int16)  # Odd81 denominator cannot tieat.5.
    return np.clip((g.astype(np.int16)-mean)*3+128,0,255).astype(np.uint8)

def geometry_q5_from_float(hub,radius):
    """LIMITED stage: float trig/radii/center -> Q5map, notintegergeometry.

    Remap pixels useFLOAT32 coordinates quantizedbyRNE to1/32pixel, likeCV.
    outside_count intentionally preserves oldFLOAT64 prequantization predicate.
    """
    angles=np.arange(360)*np.pi/180;r=np.linspace(.4,.88,12)*float(radius)
    x=float(hub[0])+r[:,None]*np.cos(angles);y=float(hub[1])+r[:,None]*np.sin(angles)
    outside=int(((x<0)|(x>127)|(y<0)|(y>127)).sum())
    xf=x.astype(np.float32);yf=y.astype(np.float32)
    xq=np.rint(xf*np.float32(32)).astype(np.int16);yq=np.rint(yf*np.float32(32)).astype(np.int16)
    return xq,yq,outside,xf,yf

def bilinear_q5_u8(gray,xq,yq,border=128):
    """Integer bilinear, 10fractionbits: CVU8 remap usespositive half-up."""
    xx=np.asarray(xq,np.int32);yy=np.asarray(yq,np.int32)
    x=xx//32;y=yy//32;fx=xx&31;fy=yy&31
    def fetch(x,y):
        valid=(x>=0)&(x<128)&(y>=0)&(y<128)
        return np.where(valid,gray[np.clip(y,0,127),np.clip(x,0,127)],border).astype(np.int32)
    a=fetch(x,y);b=fetch(x+1,y);c=fetch(x,y+1);d=fetch(x+1,y+1)
    total=a*(32-fx)*(32-fy)+b*fx*(32-fy)+c*(32-fx)*fy+d*fx*fy
    return ((total+512)>>10).astype(np.uint8)

def round_ratio_even(numerator,denominator):
    n=np.asarray(numerator,np.int64);d=np.asarray(denominator,np.int64)
    a=abs(n);q=a//d;r=a%d
    q=q+((2*r>d)|((2*r==d)&((q&1)!=0)))
    return np.where(n<0,-q,q)

def normalize_profile_s8(sampled):
    """Rationalexact rowdemean / max(meanabs,6) *32, RNE, saturation[-127,127].

    d=360*pixel-row_sum, A=sum(abs(d)), denominator=max(A,6*360²).
    result=RNE(d*360*32/denominator). Allspecified bounds fit S32.
    Python usesS64 intermediate solely toprevent accidentalNumPy promotionwrap.
    """
    u=np.asarray(sampled,np.uint8)
    if u.shape!=(12,360):raise ValueError('requires12x360U8samples')
    s=u.astype(np.int32).sum(axis=1,dtype=np.int32,keepdims=True)
    d=u.astype(np.int32)*360-s
    a=abs(d).sum(axis=1,dtype=np.int32,keepdims=True)
    denominator=np.maximum(a,6*360*360)
    numerator=d.astype(np.int64)*(360*32)
    q=round_ratio_even(numerator,denominator)
    return np.clip(q,-127,127).astype(np.int8)

def old_float_profile(sampled):
    q=sampled.astype(np.float32);q-=q.mean(axis=1,keepdims=True)
    q=q/np.maximum(abs(q).mean(axis=1,keepdims=True),6)*32
    return np.clip(np.rint(q),-127,127).astype(np.int8)

def profile(gray,hub,radius,normalized=None):
    g=normalize_local_u8(gray)if normalized is None else normalized
    xq,yq,outside,_,_=geometry_q5_from_float(hub,radius)
    return normalize_profile_s8(bilinear_q5_u8(g,xq,yq)),outside

def all_profiles(gray,hub,radius):
    g=normalize_local_u8(gray);q=[];outside=[]
    for dx,dy,scale in HYPOTHESES:
        p,oc=profile(gray,np.asarray(hub,np.float64)+[dx,dy],radius*scale,normalized=g)
        q.append(p);outside.append(oc)
    return np.stack(q),np.asarray(outside,np.uint16)

def synthetic_math_checks():
    rng=np.random.default_rng(1102);checks=0;maxerr=0;examples=[]
    for kind in['zero','full','ramp','random']:
        g=np.zeros((128,128),np.uint8)if kind=='zero'else np.full((128,128),255,np.uint8)if kind=='full'else np.arange(16384,dtype=np.uint16).reshape(128,128).astype(np.uint8)if kind=='ramp'else rng.integers(0,256,(128,128),np.uint8)
        g2=normalize_local_u8(g);cv=np.clip((g.astype(np.int16)-cv2.boxFilter(g,cv2.CV_16S,(9,9),normalize=True,borderType=cv2.BORDER_REPLICATE))*3+128,0,255).astype(np.uint8)
        assert np.array_equal(g2,cv);checks+=g.size
        # IntegerQ5 grid includesnegative/outside/boundary exactly.
        xq=rng.integers(-64,4160,(12,360),dtype=np.int16);yq=rng.integers(-64,4160,(12,360),dtype=np.int16)
        got=bilinear_q5_u8(g2,xq,yq);want=cv2.remap(g2,xq.astype(np.float32)/32,yq.astype(np.float32)/32,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=128)
        err=abs(got.astype(int)-want.astype(int));maxerr=max(maxerr,int(err.max()));checks+=got.size
        if np.any(err):examples.append(dict(kind=kind,mismatches=int((err!=0).sum())))
    assert maxerr==0,examples
    # RNEsignedties + nearzero, both saturationends retained.
    assert round_ratio_even(np.array([-7,-5,-3,-1,1,3,5,7]),2).tolist()==[-4,-2,-2,0,0,2,2,4]
    return dict(status='PASS',pixel_checks=checks,bilinear_max_cv_error=maxerr,RNE_signed_ties=True)

def validate_and_export():
    start=time.monotonic();synthetic=synthetic_math_checks()
    rr=load_prepared(DATA/'prepared_train.jsonl')+load_prepared(DATA/'prepared_validation.jsonl');rmap={r['id']:r for r in rr}
    gray={}
    for split in['train','validation']:
        z=np.load(DATA/f'roi_cache_{split}.npz');gray.update({str(k):g for k,g in zip(z['ids'],z['images'])})
    baseline=load(HERE/'fixtures/manifest.json');bymeta={r['id']:r for r in baseline['records']}
    output=HERE/'frontend_fixtures';output.mkdir(exist_ok=True)
    totals=dict(normalize_pixels=0,normalize_mismatches=0,q5coordinate_components=0,q5coordinate_mismatches=0,
        bilinear_samples=0,bilinear_pixel_mismatches=0,profile_S8_elements=0,rational_vs_float32_profile_mismatches=0,
        rational_vs_float32_profile_max_abs_error=0,outside_predicate_mismatches=0)
    records=[];examples=[]
    for r in rr:
        ident=r['id'];g=gray[ident];gn=normalize_local_u8(g)
        cvlocal=cv2.boxFilter(g,cv2.CV_16S,(9,9),normalize=True,borderType=cv2.BORDER_REPLICATE)
        wantnorm=np.clip((g.astype(np.int16)-cvlocal)*3+128,0,255).astype(np.uint8)
        totals['normalize_pixels']+=g.size;totals['normalize_mismatches']+=int((gn!=wantnorm).sum())
        real=ident in bymeta
        if real:
            old=np.load(HERE/'fixtures'/(ident+'.npz'));hub=old['hub'];radius=float(old['radius'])
            assert np.array_equal(old['image'],g)
        else:
            #13quality-only images have no oldB model hub; only arithmetic tests.
            hub=np.array([63.5,63.5]);radius=float(r['roi_request']['radius'])
        qs=[];ocs=[];old_diffs=0;maxdiff=0
        for j,(dx,dy,scale)in enumerate(HYPOTHESES):
            xq,yq,oc,xf,yf=geometry_q5_from_float(hub+[dx,dy],radius*scale)
            map1,map2=cv2.convertMaps(xf,yf,cv2.CV_16SC2)
            cvx=map1[:,:,0].astype(np.int32)*32+(map2&31);cvy=map1[:,:,1].astype(np.int32)*32+(map2>>5)
            totals['q5coordinate_components']+=2*xq.size
            totals['q5coordinate_mismatches']+=int((xq!=cvx).sum()+(yq!=cvy).sum())
            raw=bilinear_q5_u8(gn,xq,yq)
            cvraw=cv2.remap(wantnorm,xf,yf,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=128)
            totals['bilinear_samples']+=raw.size;totals['bilinear_pixel_mismatches']+=int((raw!=cvraw).sum())
            got=normalize_profile_s8(raw);wanted=old_float_profile(cvraw)
            err=abs(got.astype(np.int16)-wanted.astype(np.int16));n=int((err!=0).sum());m=int(err.max())
            totals['profile_S8_elements']+=got.size;totals['rational_vs_float32_profile_mismatches']+=n
            totals['rational_vs_float32_profile_max_abs_error']=max(totals['rational_vs_float32_profile_max_abs_error'],m)
            old_diffs+=n;maxdiff=max(maxdiff,m)
            if real:
                assert np.array_equal(wanted,old['profiles'][j]),'Floatoracle didnot reproducefrozenfixture'
                totals['outside_predicate_mismatches']+=int(oc!=int(old['outside_counts'][j]))
            if n and len(examples)<12:
                band,angle=np.argwhere(err!=0)[0];examples.append(dict(id=ident,profile=j,band=int(band),angle=int(angle),rational_value=int(got[band,angle]),old_float32_value=int(wanted[band,angle])))
            qs.append(got);ocs.append(oc)
        np.savez_compressed(output/(ident+'.npz'),profiles=np.stack(qs),outside_counts=np.asarray(ocs,np.uint16),
            hub=hub,radius=radius,hypotheses=HYPOTHESES,image=g,normalized_image=gn,
            real_model_hub=np.asarray(real))
        records.append(dict(id=ident,split=r['split'],source_sha256=r['sha256'],fixture_sha256=sha(output/(ident+'.npz')),
            actual_model_hub_available=real,synthetic_hub_for_arithmetic_only=not real,
            center_allowed=bool(np.linalg.norm(hub-63.5)<=14),profile_difference_count=old_diffs,profile_max_difference=maxdiff))
    # Template sampling uses sameintegerfrontend; frozen maskindices and local-
    # shift maps arekept unchanged. No reference re-selection orthreshold tuning.
    oldt=np.load(HERE/'fixtures/templates.npz');t={};template_diff=[]
    for j,ident in enumerate(['D_002','E_002']):
        zz=np.load(HERE/'fixtures'/(ident+'.npz'));ref,oc=profile(zz['image'],zz['hub'],float(zz['radius']))
        indices=oldt[f'indices_{j}'];values=ref.ravel()[indices].astype(np.int8)
        t[f'indices_{j}']=indices;t[f'values_{j}']=values;t[f'shifts_{j}']=oldt[f'shifts_{j}']
        template_diff.append(dict(id=ident,selected_elements=len(indices),integer_vs_old_changed=int((values!=oldt[f'values_{j}']).sum()),
            max_abs_difference=int(abs(values.astype(np.int16)-oldt[f'values_{j}'].astype(np.int16)).max()),outside_count=oc))
    np.savez(output/'templates.npz',**t)
    hard_fields=['normalize_mismatches','q5coordinate_mismatches','bilinear_pixel_mismatches','outside_predicate_mismatches']
    assert all(totals[k]==0 for k in hard_fields),totals
    assert totals['rational_vs_float32_profile_max_abs_error']<=1,totals
    manifest=dict(status='INTEGER_PIXEL_PROFILE_FRONTEND_FLOAT_GEOMETRY_LIMITED',records=records,profiles_per_image=27,
        arithmetic_only_records=13,actual_model_hub_records=len(baseline['records']),template_changes=template_diff,
        same_template_indices_shifts_and_thresholds=True,geometry_generated_with_float=True,full_integer_geometry_proven=False,
        source_files_sha256={str(p):sha(p)for p in[Path(__file__),HERE/'fixtures/manifest.json',HERE/'fixtures/templates.npz',DATA/'roi_cache_train.npz',DATA/'roi_cache_validation.npz']},
        output_templates_sha256=sha(output/'templates.npz'),H_opened=False,hardware_actions=False)
    write(HERE/'frontend_fixture_manifest.json',manifest)
    report=dict(status='PASS_INTEGER_PIXEL_PROFILE_MATH_WITH_EXPLICIT_FLOAT32_TIE_DIFFERENCES',synthetic=synthetic,counts=totals,
        first_profile_rounding_differences=examples,template_differences=template_diff,
        fixed_math=dict(local_mean='nearest(sum/81)=(sum+40)//81',local_contrast='satU8(3*(pixel-localmean)+128)',
            Q5_pixel_coordinates='RNE(float32map*32), stillfromfloatgeometry',bilinear='(weighted4pixelSum+512)>>10 (positivehalfup)',
            radial_profile='d=360*u-sum; A=sum(abs(d)); RNEeven(d*11520/max(A,777600)); sat[-127,127]',
            maximum_profile_numerator_bound=1057536000,profile_intermediate_S32_mathematically_sufficient=True),
        remaining_float=['sin/cos','radialfractionandscalegeometry','predictedhubcoordinates','outsidepredicate','hubdistancepredicate'],
        not_yet_C_frontend_or_MCU=True,not_board_pixel_domain_equivalence=True,
        no_new_optimization_or_threshold_changes=True,G_not_used_to_tune=True,H_opened=False,hardware_actions=False,
        elapsed_seconds=time.monotonic()-start,frontend_code_sha256=sha(__file__),fixture_manifest_sha256=sha(HERE/'frontend_fixture_manifest.json'))
    write(HERE/'frontend_verification.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=['check','validate'],nargs='?',default='check');a=ap.parse_args()
    if a.command=='check':print(json.dumps(synthetic_math_checks(),indent=2))
    else:validate_and_export()
