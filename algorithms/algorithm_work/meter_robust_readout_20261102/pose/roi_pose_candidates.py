"""Two bounded ROI128-only static-print pose candidates. Never query GT/psi.

A: locally normalized ORB printed feature registration, multi train templates.
B: locally normalized multi-template annular matching with bounded center/scale.
All template setup uses only fixed trainROI and predicted hub/needle exclusion.
"""
from pathlib import Path
import sys,json,math,hashlib
import cv2
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
DATA=ROOT/'algorithm_work/meter_cnn_training_20261102'
OLD=ROOT/'algorithm_work/meter_pointer_readout_20261102'
sys.path.insert(0,str(DATA));from roi_adapter import load_prepared
CONFIG=dict(reference_ids=['D_002','E_002','F_002'],local_box_width=9,
    A=dict(orb_features=400,ratio=.75,min_inliers=8,min_unique=6,min_quadrants=3,min_hull_fraction=.045,max_reprojection=1.3,max_anisotropy=1.15,min_inner_print_inliers=3),
    B=dict(radial_bands=12,angular_bins=360,radius_fractions=[.4,.88],search_degrees=[-24,24],
           center_offsets_roi=[-1.5,0,1.5],scale_offsets=[.97,1.,1.03],trim_outliers_fraction=.2,min_score=.64,min_margin=.018,max_center_distance=14),
    fixed_before_validation=True,thresholds_selected_from_G=False)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def rows(p):return[json.loads(x)for x in Path(p).read_text('utf-8-sig').splitlines()if x.strip()]
def write(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n','utf-8')
def project(H,p):return cv2.perspectiveTransform(np.asarray(p,np.float32)[None],np.asarray(H,np.float64))[0]

def assets():
    rr=load_prepared(DATA/'prepared_train.jsonl')+load_prepared(DATA/'prepared_validation.jsonl')
    gray={}
    for split in['train','validation']:
        z=np.load(DATA/f'roi_cache_{split}.npz');gray.update({str(k):v for k,v in zip(z['ids'],z['images'])})
    pred={r['id']:r for r in rows(OLD/'polar_angle/run_001/train_predictions.jsonl')+rows(OLD/'polar_angle/run_001/validation_predictions.jsonl')}
    return rr,gray,pred

def normalize(gray):
    g=gray.astype(np.int16);local=cv2.boxFilter(gray,cv2.CV_16S,(9,9),normalize=True,borderType=cv2.BORDER_REPLICATE)
    return np.clip((g-local)*3+128,0,255).astype(np.uint8)

class Candidates:
    def __init__(self,records,gray,pred):
        self.rec={r['id']:r for r in records};self.gray=gray;self.pred=pred
        self.orb=cv2.ORB_create(nfeatures=400,scaleFactor=1.15,nlevels=4,edgeThreshold=5,patchSize=15,fastThreshold=5)
        self.refs={}
        for ident in CONFIG['reference_ids']:
            p=pred[ident];self.refs[ident]=self.features(gray[ident],p['hub_roi'],self.rec[ident]['roi_request']['radius'],p['angle_deg_image'])
        # Static printed-feature alignment between train templates, no pressure/GT.
        self.offsets={'D_002':0.};self.setup={}
        for ident in CONFIG['reference_ids'][1:]:
            fit=self.match(self.refs['D_002'],self.refs[ident]);self.setup[ident]=fit
            if fit['accepted']:self.offsets[ident]=fit['relative_roll_deg']
        self.templates={}
        for ident in self.offsets:
            p=pred[ident];rad=self.rec[ident]['roi_request']['radius'];q,_=self.profile(gray[ident],p['hub_roi'],rad)
            a=np.arange(360);mask=np.ones((12,360),bool)
            for angle in[p['angle_deg_image'],p['angle_deg_image']+180]:mask&=abs((a-angle+180)%360-180)[None,:]>28
            grad=abs(np.roll(q,-1,1)-np.roll(q,1,1));mask&=grad>=8
            self.templates[ident]=(q,mask)

    def features(self,gray,hub,radius,reference_angle=None):
        # Normalize center/radius with predicted values; all pixels from128ROI.
        scale=48/float(radius);A=np.array([[scale,0,64-hub[0]*scale],[0,scale,64-hub[1]*scale]],np.float64)
        g=cv2.warpAffine(normalize(gray),A,(128,128),flags=cv2.INTER_LINEAR,borderValue=128)
        yy,xx=np.mgrid[:128,:128];rr=np.hypot(xx-64,yy-64);mask=(rr>18)&(rr<44)
        if reference_angle is not None:
            angle=np.degrees(np.arctan2(yy-64,xx-64))
            for a in[reference_angle,reference_angle+180]:mask&=abs((angle-a+180)%360-180)>28
        kp,desc=self.orb.detectAndCompute(g,mask.astype(np.uint8)*255)
        return dict(gray=g,kp=kp,desc=desc,mask=mask,roi_to_normalized=np.vstack([A,[0,0,1]]))

    def match(self,ref,q):
        out=dict(accepted=False,reason='NO_RELIABLE_ROI128_STATIC_PRINT_REGISTRATION')
        if ref['desc']is None or q['desc']is None or len(q['desc'])<2:return out
        mm=[m[0]for m in cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(ref['desc'],q['desc'],k=2)if len(m)==2 and m[0].distance<.75*m[1].distance]
        back=cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(q['desc'],ref['desc'],k=1)
        mm=[m for m in mm if back[m.trainIdx][0].trainIdx==m.queryIdx]
        out['matches']=len(mm)
        if len(mm)<8:return out
        aa=np.float32([ref['kp'][m.queryIdx].pt for m in mm]);bb=np.float32([q['kp'][m.trainIdx].pt for m in mm])
        cv2.setRNGSeed(20261102);H,keep=cv2.findHomography(aa,bb,cv2.RANSAC,2.,maxIters=2000,confidence=.995)
        if H is None:return out
        keep=keep.ravel().astype(bool);aa=aa[keep];bb=bb[keep]
        hull=float(cv2.contourArea(cv2.convexHull(aa))/128**2)if len(aa)>=3 else 0.
        err=float(np.median(np.linalg.norm(project(H,aa)-bb,axis=1)))
        quad=len(set((x>64,y>64)for x,y in aa));unique=len(set((round(float(x)/2),round(float(y)/2))for x,y in aa))
        inner=sum(np.linalg.norm(a-[64,64])<35 for a in aa)
        out.update(inliers=len(aa),unique_locations=unique,quadrants=quad,hull_fraction=hull,median_reprojection_px=err,inner_print_inliers=int(inner))
        if len(aa)<8 or unique<6 or quad<3 or hull<.045 or err>1.3 or inner<3:return out
        c=project(H,[[64,64]])[0];J=np.c_[project(H,[[65,64]])[0]-c,project(H,[[64,65]])[0]-c]
        u,s,v=np.linalg.svd(J);R=u@v;anis=float(s.max()/s.min())
        if np.linalg.det(R)<0 or anis>1.15 or s.min()<.7 or s.max()>1.4:
            out['reason']='REGISTRATION_SCALE_OR_PERSPECTIVE_UNSUITABLE';return out
        angle=math.degrees(math.atan2(R[1,0],R[0,0]))
        if abs(angle)>28:return out
        out.update(accepted=True,reason='ROI128_ORB_STATIC_PRINT_REGISTERED',relative_roll_deg=angle,local_anisotropy=anis,H=H.tolist())
        return out

    def A(self,gray,hub,radius):
        q=self.features(gray,hub,radius);fits=[]
        for ident in self.offsets:
            fit=self.match(self.refs[ident],q)
            if fit['accepted']:fits.append(dict(reference_id=ident,**fit,canonical_roll_deg=fit['relative_roll_deg']+self.offsets[ident]))
        if not fits:return dict(accepted=False,reason='NO_RELIABLE_ROI128_STATIC_PRINT_REGISTRATION')
        fits.sort(key=lambda x:x['inliers'],reverse=True);best=fits[0]
        # Multiple accepted reference matches must agree, not simply win bytexture.
        if len(fits)>1 and max(abs(f['canonical_roll_deg']-best['canonical_roll_deg'])for f in fits)>3:
            return dict(accepted=False,reason='TRAIN_REFERENCE_POSE_DISAGREEMENT',fits=fits)
        H_setup=np.eye(3)if best['reference_id']=='D_002'else np.asarray(self.setup[best['reference_id']]['H'])
        H_canonical=np.asarray(best['H'])@H_setup
        return dict(accepted=True,reason='ROI128_ORB_MULTI_REFERENCE',relative_roll_deg=best['canonical_roll_deg'],
            best_reference=best['reference_id'],inliers=best['inliers'],local_anisotropy=best['local_anisotropy'],fits=fits,
            H_reference_D002_normalized128_to_query_normalized128=H_canonical.tolist(),
            query_roi_to_normalized_matrix=q['roi_to_normalized'].tolist(),
            reference_D002_roi_to_normalized_matrix=self.refs['D_002']['roi_to_normalized'].tolist(),
            normalized_image_size=[128,128],query_predicted_hub_roi=list(hub),query_locator_radius=float(radius))

    @staticmethod
    def profile(gray,hub,radius):
        a=np.arange(360)*np.pi/180;r=np.linspace(.4,.88,12)*radius
        x=hub[0]+r[:,None]*np.cos(a);y=hub[1]+r[:,None]*np.sin(a)
        outside=float(((x<0)|(x>127)|(y<0)|(y>127)).mean())
        q=cv2.remap(normalize(gray),x.astype(np.float32),y.astype(np.float32),cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=128).astype(np.float32)
        q-=q.mean(axis=1,keepdims=True);q=q/np.maximum(abs(q).mean(axis=1,keepdims=True),6)*32
        return np.clip(np.rint(q),-127,127).astype(np.int16),outside

    def B(self,gray,hub,radius):
        if np.linalg.norm(np.asarray(hub)-[63.5,63.5])>14:return dict(accepted=False,reason='PREDICTED_HUB_TOO_FAR_FROM_LOCATOR_CENTER_FOR_RING_POSE')
        shifts=np.arange(-24,25);best_scores=np.full(49,-np.inf);best_info=[None]*49
        for dx in[-1.5,0,1.5]:
            for dy in[-1.5,0,1.5]:
                for scale in[.97,1.,1.03]:
                    q,outside=self.profile(gray,np.asarray(hub)+[dx,dy],radius*scale)
                    if outside>.05:continue
                    for ident,(ref,mask)in self.templates.items():
                        reference=ref[mask].astype(np.int32)
                        # A canonical shift becomes query-template shift after the
                        # fixedtrain-only print alignment between template andD002.
                        for i,delta in enumerate(shifts):
                            local=int(round(delta-self.offsets[ident]));values=np.roll(q,-local,axis=1)[mask].astype(np.int32)
                            diff=abs(values-reference);keep=max(1,int(len(diff)*.8));score=1-float(np.partition(diff,keep-1)[:keep].mean())/128
                            if score>best_scores[i]:best_scores[i]=score;best_info[i]=dict(reference_id=ident,dx=dx,dy=dy,radius_scale=scale,outside_fraction=outside)
        i=int(best_scores.argmax());best=float(shifts[i]);far=best_scores[abs(shifts-best)>5]
        if not np.isfinite(best_scores[i]):return dict(accepted=False,reason='ROI128_RING_OUTSIDE')
        margin=float(best_scores[i]-far.max())
        valid=bool(best_scores[i]>=.64 and margin>=.018 and abs(best)<24)
        return dict(accepted=valid,reason='ROI128_LOCAL_CONTRAST_MULTI_RING_SUPPORTED'if valid else'ROI128_RING_AMBIGUOUS',
            relative_roll_deg=best,score=float(best_scores[i]),margin=margin,**best_info[i])

def main():
    write(HERE/'candidate_config.json',CONFIG)
    rr,gray,pred=assets();c=Candidates(rr,gray,pred)
    setup=dict(reference_offsets=c.offsets,reference_pair_registration=c.setup,
        reference_selection='Fixed clear train D002/E002/F002 only; noG template/threshold selection',
        reference_only_needle_sector_source='Frozen train model predictions atsetup, fixed28deg exclusions; never queryGT/psi',
        operating_inputs='ROI128U8 + predicted hub + locator radius; no native image, GTpoint, pressure orSIFT')
    write(HERE/'template_setup.json',setup)
    all_rows={k:[]for k in['A','B']}
    for split in['train','validation']:
        for r in rr:
            if r['split']!=split or r['id']not in pred:continue
            p=pred[r['id']];hub=p['hub_roi'];radius=r['roi_request']['radius']
            for name in['A','B']:
                result=getattr(c,name)(gray[r['id']],hub,radius)
                all_rows[name].append(dict(id=r['id'],split=split,source_sha256=r['sha256'],query_uses_GT_points=False,query_uses_pressure=False,
                    native_frame_used=False,method=name,**result))
        # Save aftertraining pass too; validation cannot modify frozenparams/templates.
        for name,records in all_rows.items():
            (HERE/f'candidate_{name}_pose.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in records),'utf-8')
        print(split,'complete',[(name,sum(r['accepted']for r in records if r['split']==split))for name,records in all_rows.items()],flush=True)
    # Oracle nativeSIFT is imported only AFTER inference, for external diagnostics.
    oracle={r['id']:r for r in rows(OLD/'readout/train_print_pose.jsonl')+rows(OLD/'readout/validation_print_pose.jsonl')}
    summary={}
    for name,records in all_rows.items():
        summary[name]={}
        for split in['train','validation']:
            sub=[r for r in records if r['split']==split];accept=[r for r in sub if r['accepted']];both=[r for r in accept if oracle[r['id']]['accepted']]
            err=[abs((r['relative_roll_deg']-oracle[r['id']]['relative_roll_deg']+180)%360-180)for r in both]
            summary[name][split]=dict(images=len(sub),accepted=len(accept),both_with_oracle=len(both),oracle_angle_difference_MAE_deg=float(np.mean(err))if err else None,
                oracle_difference_max_deg=max(err)if err else None,oracle_difference_over3deg=sum(x>3 for x in err))
    write(HERE/'pose_summary.json',dict(status='TWO_ROI128_POSE_CANDIDATES_PC_ONLY_NO_MCU_PORT',summary=summary,
        template_setup_sha256=sha(HERE/'template_setup.json'),config_sha256=sha(HERE/'candidate_config.json'),code_sha256=sha(__file__),
        query_inputs='OnlyU8ROI128+predictedhub+locatorscale',oracle_supplies_inference=False,H_opened=False,hardware_actions=False))
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
