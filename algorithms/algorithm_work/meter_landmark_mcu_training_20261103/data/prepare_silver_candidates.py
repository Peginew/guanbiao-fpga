"""Train-only static-print SIFT propagation with explicit silver provenance.

This generates candidates for visual review, not final supervision. No pressure,
needle keypoint/angle, neural prediction, G image, H image, or ABC image enters
registration. One fixed D025 reference-only manual line exclusion removes its
dynamic needle/counterweight from descriptor initialization.
"""
from pathlib import Path
import cv2,hashlib,json,math
import numpy as np
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
PKG=ROOT/'algorithm_work/meter_cnn_training_20261102'
REF=ROOT/'algorithm_work/meter_redundant_print_20261102/annotations/reference_D025.json'
NAMES=['outer_psi_5_text_centroid','outer_psi_10_text_centroid','outer_psi_15_text_centroid',
       'upper_basketball_logo_centroid','middle_soccer_logo_centroid','lower_striped_ball_print_centroid']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rows(p):return [json.loads(s) for s in Path(p).read_text('utf-8-sig').splitlines() if s.strip()]
def project(H,points):return cv2.perspectiveTransform(np.asarray(points,np.float32)[None],np.asarray(H,np.float64))[0]
def readim(p):return cv2.imdecode(np.fromfile(str(p),np.uint8),1)
def roi(p,q):
    s=q['stride'];return [(float(p[0])-q['x0']-(s-1)/2)/s,(float(p[1])-q['y0']-(s-1)/2)/s]
def build():
    cv2.setNumThreads(1);cv2.setRNGSeed(20261103)
    rec=[]
    for raw in rows(PKG/'prepared_train.jsonl'):
        r={k:raw[k] for k in ('id','path','sha256','split','source_group','target_present','bbox_native_xyxy','roi_request')}
        assert r['source_group'] in ('D','E','F') and r['split']=='train'
        rec.append(r)
    assert len(rec)==177
    ref=json.loads(REF.read_text('utf-8'));reference=next(r for r in rec if r['id']=='D_025')
    sift=cv2.SIFT_create(nfeatures=3500,contrastThreshold=.006,edgeThreshold=15,sigma=1.2)
    clahe=cv2.createCLAHE(2.,(8,8))
    yy,xx=np.mgrid[:512,:512];rad=np.hypot(xx-256,yy-256)
    def features(r,reference=False):
        if r['bbox_native_xyxy'] is None:return None
        im=readim(r['path']);assert im is not None and sha(r['path'])==r['sha256']
        x0,y0,x1,y1=r['bbox_native_xyxy'];diam=max(x1-x0,y1-y0);s=480/diam
        A=np.array([[s,0,256-(x0+x1)/2*s],[0,s,256-(y0+y1)/2*s]],np.float64)
        g=cv2.warpAffine(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY),A,(512,512),flags=cv2.INTER_LINEAR,borderValue=0)
        mask=((rad>60)&(rad<218)).astype(np.uint8)*255
        for box in [[32,15,292,181],[704,40,1240,211]]:
            a=project(np.vstack([A,[0,0,1]]),[box[:2],box[2:]])
            cv2.rectangle(mask,tuple(np.floor(a[0]).astype(int)),tuple(np.ceil(a[1]).astype(int)),0,-1)
        if reference:
            # D025 raw-view endpoint coordinates were independently visualized.
            # This fixed reference-only exclusion is never recomputed from query needles.
            native=np.array([[336+110*343/512,91+(160-4)*337/503],
                             [336+350*343/512,91+(302-4)*337/503]])
            p=project(np.vstack([A,[0,0,1]]),native)
            cv2.line(mask,tuple(p[0].astype(int)),tuple(p[1].astype(int)),0,40)
        mask=cv2.erode(mask,np.ones((7,7),np.uint8))
        kp,desc=sift.detectAndCompute(clahe.apply(g),mask)
        return dict(A=A,gray=g,kp=kp,desc=desc)
    fr=features(reference,True)
    assert fr and fr['desc'] is not None
    Hra=np.vstack([fr['A'],[0,0,1]])
    refp=project(Hra,[ref['anchors'][name]['native_xy'] for name in NAMES])
    out=[];display=[]
    clean=BASE/'clean_views';overlay=BASE/'candidate_views'
    clean.mkdir(parents=True,exist_ok=True);overlay.mkdir(exist_ok=True)
    for r in rec:
        im=readim(r['path']);h,w=im.shape[:2];bbox=r['bbox_native_xyxy']
        if bbox:
            x0,y0,x1,y1=bbox;cx,cy=(x0+x1)/2,(y0+y1)/2;span=max(x1-x0,y1-y0)*1.18
            box=[max(0,math.floor(cx-span/2)),max(0,math.floor(cy-span/2)),min(w,math.ceil(cx+span/2)),min(h,math.ceil(cy+span/2))]
        else:box=[0,0,w,h]
        x0,y0,x1,y1=box;sc=min(384/(x1-x0),384/(y1-y0));ow,oh=round((x1-x0)*sc),round((y1-y0)*sc);dx,dy=(384-ow)//2,(384-oh)//2
        view=np.full((384,384,3),235,np.uint8);view[dy:dy+oh,dx:dx+ow]=cv2.resize(im[y0:y1,x0:x1],(ow,oh))
        cv2.imencode('.png',view)[1].tofile(str(clean/f'{r["id"]}.png'))
        disp={**r,'native_crop_xyxy':box,'view_transform':dict(scale_x=ow/(x1-x0),scale_y=oh/(y1-y0),offset_x=dx,offset_y=dy)}
        display.append(disp)
        result={'id':r['id'],'source_sha256':r['sha256'],'target_present':r['target_present'],'registration_accepted':False,
                'reference_id':'D_025','reference_sha256':ref['source_sha256'],'query_psi_NN_needle_used':False,
                'candidate_points':{},'candidate_is_final_label':False}
        if r['target_present']:
            fq=features(r)
            if fq and fq['desc'] is not None and len(fq['desc'])>=2:
                matches=[m[0] for m in cv2.BFMatcher().knnMatch(fr['desc'],fq['desc'],k=2) if len(m)==2 and m[0].distance<.72*m[1].distance]
                back=cv2.BFMatcher().knnMatch(fq['desc'],fr['desc'],k=1)
                matches=[m for m in matches if back[m.trainIdx][0].trainIdx==m.queryIdx]
                result['mutual_matches']=len(matches)
                if len(matches)>=10:
                    a=np.float32([fr['kp'][m.queryIdx].pt for m in matches]);b=np.float32([fq['kp'][m.trainIdx].pt for m in matches])
                    cv2.setRNGSeed(20261103);H,mask=cv2.findHomography(a,b,cv2.RANSAC,3,maxIters=4000,confidence=.995)
                    if H is not None:
                        keep=mask.ravel().astype(bool);aa=a[keep];bb=b[keep];pred=project(H,aa)
                        err=float(np.median(np.linalg.norm(pred-bb,axis=1)));hull=float(cv2.contourArea(cv2.convexHull(aa))/512**2)
                        quadrants=len(set((x>256,y>256) for x,y in aa));unique=len(set((round(float(x)/3),round(float(y)/3)) for x,y in aa))
                        c=project(H,[[256,256],[257,256],[256,257]]);J=np.c_[c[1]-c[0],c[2]-c[0]];sv=np.linalg.svd(J)[1]
                        good=len(aa)>=10 and unique>=8 and quadrants>=3 and hull>=.04 and err<=2.5 and np.linalg.det(J)>0 and sv.min()>.45 and sv.max()<2
                        result.update(inliers=len(aa),unique_locations=unique,quadrants=quadrants,hull_fraction=hull,median_reprojection_normalized_px=err,registration_accepted=bool(good))
                        if good:
                            Hnative=np.linalg.inv(np.vstack([fq['A'],[0,0,1]]))@H@Hra
                            points=project(Hnative,[ref['anchors'][name]['native_xy'] for name in NAMES])
                            result['H_reference_native_to_query_native']=Hnative.tolist()
                            for name,p in zip(NAMES,points):
                                rp=roi(p,r['roi_request']);result['candidate_points'][name]=dict(native_xy=p.astype(float).tolist(),xy_roi=rp,
                                    uncertainty_native_px=float(max(4,2.5+err/fq['A'][0,0])),method='D025_NATIVE_SIFT_RANSAC_H_SILVER_PENDING_VISUAL_REVIEW')
        vis=view.copy()
        for j,name in enumerate(NAMES):
            cp=result['candidate_points'].get(name)
            if cp:
                p=cp['native_xy'];t=disp['view_transform'];v=(round((p[0]-x0)*t['scale_x']+dx),round((p[1]-y0)*t['scale_y']+dy))
                cv2.drawMarker(vis,v,(0,180,220),cv2.MARKER_CROSS,10,1,cv2.LINE_AA);cv2.putText(vis,str(j+1),(v[0]+4,v[1]-4),cv2.FONT_HERSHEY_SIMPLEX,.4,(0,150,210),1,cv2.LINE_AA)
        cv2.imencode('.png',vis)[1].tofile(str(overlay/f'{r["id"]}.png'))
        out.append(result)
    for filename,rr in [('registration_candidates.jsonl',out),('display_index.jsonl',display)]:
        (BASE/filename).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rr),'utf-8')
    for group in ('D','E','F'):
        subset=[r for r in out if r['id'].startswith(group+'_')]
        for start in range(0,len(subset),9):
            page=np.full((1242,1152,3),255,np.uint8)
            for j,r in enumerate(subset[start:start+9]):
                tile=np.full((414,384,3),255,np.uint8);tile[30:]=readim(overlay/f'{r["id"]}.png')
                cv2.putText(tile,r['id']+(' silver' if r['registration_accepted'] else ' UNREGISTERED'),(7,22),cv2.FONT_HERSHEY_SIMPLEX,.58,(10,25,40),1,cv2.LINE_AA)
                yy,xx=divmod(j,3);page[yy*414:(yy+1)*414,xx*384:(xx+1)*384]=tile
            cv2.imencode('.png',page)[1].tofile(str(BASE/f'{group}_candidates_{start//9+1:02d}.png'))
    summary={'images':177,'train_groups_only':['D','E','F'],'registered_candidates':sum(r['registration_accepted'] for r in out),
             'not_registered_ids':[r['id'] for r in out if r['target_present'] and not r['registration_accepted']],
             'reference_D025_sha256':sha(REF),'no_query_GT_pressure_needle_NN':True,'G_H_ABC_not_read':True,
             'candidate_labels_not_training_ready':True,'source_code_sha256':sha(__file__)}
    (BASE/'candidate_generation_receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':build()
