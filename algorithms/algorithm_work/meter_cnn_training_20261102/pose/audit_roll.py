"""Read-only relative printed-face roll audit; no H, no labels rewritten.

SIFT/CLAHE+homography follows the existing face.py technique, using NEW D002
as reference. Feature masks exclude dynamic needle, hub, background and OSD.
"""
from pathlib import Path
import sys,json,hashlib,math
import cv2
import numpy as np
HERE=Path(__file__).resolve().parent;TASK=HERE.parent
sys.path.insert(0,str(TASK))
from roi_adapter import load_prepared,read_native,gray_from_bgr,save_image

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n','utf-8')
def project(H,p):return cv2.perspectiveTransform(np.asarray(p,np.float32)[None],H)[0]
SIFT=cv2.SIFT_create(nfeatures=2000,contrastThreshold=.008,edgeThreshold=15,sigma=1.2)
CLAHE=cv2.createCLAHE(2.,(8,8))
Y,X=np.mgrid[:256,:256]

def patch(r):
    if not r['target_present']:return None,'negative'
    h=r['keypoints']['hub'].get('xy');t=r['keypoints']['thin_terminal'].get('xy')
    if h is None or t is None:return None,'UNKNOWN_NEEDLE_MASK_CANNOT_EXCLUDE_DYNAMIC_STRUCTURE'
    box=r['bbox_native_xyxy'];d=max(box[2]-box[0],box[3]-box[1]);cx=(box[0]+box[2])/2;cy=(box[1]+box[3])/2
    if d>600 or d<150:return None,'EXTREME_SCALE_NOT_RELIABLE_PRINT_REGISTRATION'
    scale=240/d;A=np.array([[scale,0,128-cx*scale],[0,scale,128-cy*scale]],np.float64)
    g=cv2.warpAffine(gray_from_bgr(read_native(r)),A,(256,256),flags=cv2.INTER_LINEAR,borderValue=0)
    hp=np.asarray(h)*scale+A[:,2];tp=np.asarray(t)*scale+A[:,2]
    rr=np.hypot(X-hp[0],Y-hp[1]);aa=np.degrees(np.arctan2(Y-hp[1],X-hp[0]));angle=math.degrees(math.atan2(*(tp-hp)[::-1]))
    # Printed numerals/tick annulus only; complete external shiny rim excluded.
    mask=(rr>.40*120)&(rr<.86*120)
    for a in [angle,angle+180]:mask&=abs((aa-a+180)%360-180)>22
    # Conservative native OSD rectangles. Feature masks only; input images unchanged.
    for b in [[32,15,292,181],[704,40,1240,211]]:
        a0=np.asarray(b[:2])*scale+A[:,2];a1=np.asarray(b[2:])*scale+A[:,2]
        mask&=~((X>=a0[0])&(X<a1[0])&(Y>=a0[1])&(Y<a1[1]))
    # No descriptors whose support could reach the dynamic hub/needle or background.
    eroded=cv2.erode(mask.astype(np.uint8),np.ones((7,7),np.uint8))
    kp,desc=SIFT.detectAndCompute(CLAHE.apply(g),eroded*255)
    keep=[]
    for i,k in enumerate(kp):
        radius=max(4,round(k.size))
        x,y=map(int,k.pt)
        y0,y1=max(0,y-radius),min(256,y+radius+1);x0,x1=max(0,x-radius),min(256,x+radius+1)
        if mask[y0:y1,x0:x1].all():keep.append(i)
    kp=[kp[i]for i in keep];desc=desc[keep]if desc is not None and keep else None
    return dict(gray=g,mask=mask,kp=kp,desc=desc,hub=hp),None

def infer(ref,q):
    out=dict(accepted=False,reason='INSUFFICIENT_STATIC_PRINT_SUPPORT',source_features=len(q['kp']))
    if ref['desc']is None or q['desc']is None or len(q['desc'])<2:return out
    mm=[m[0]for m in cv2.BFMatcher().knnMatch(ref['desc'],q['desc'],k=2)if len(m)==2 and m[0].distance<.72*m[1].distance]
    # Mutual matches reduce duplicate tick correspondences.
    back=cv2.BFMatcher().knnMatch(q['desc'],ref['desc'],k=1)
    mm=[m for m in mm if back[m.trainIdx][0].trainIdx==m.queryIdx]
    out['matches']=len(mm)
    if len(mm)<10:return out
    aa=np.float32([ref['kp'][m.queryIdx].pt for m in mm]);bb=np.float32([q['kp'][m.trainIdx].pt for m in mm])
    cv2.setRNGSeed(20261102);H,keep=cv2.findHomography(aa,bb,cv2.RANSAC,2.5,maxIters=3000,confidence=.995)
    if H is None:return out
    keep=keep.ravel().astype(bool);aa=aa[keep];bb=bb[keep]
    err=float(np.median(np.linalg.norm(project(H,aa)-bb,axis=1)))
    hull=float(cv2.contourArea(cv2.convexHull(aa))/(256*256))if len(aa)>=3 else 0.
    quad=len(set((int(x>ref['hub'][0]),int(y>ref['hub'][1]))for x,y in aa))
    unique=len(set((round(float(x)/3),round(float(y)/3))for x,y in aa))
    out.update(inliers=len(aa),inlier_fraction=len(aa)/len(mm),hull_fraction=hull,quadrants=quad,unique_locations=unique,reprojection_median_normalized_px=err)
    if len(aa)<10 or unique<8 or quad<3 or hull<.055 or err>1.8:return out
    c=ref['hub'];center=project(H,[c])[0];jx=project(H,[c+[1,0]])[0]-center;jy=project(H,[c+[0,1]])[0]-center
    J=np.c_[jx,jy];u,s,v=np.linalg.svd(J);R=u@v
    if np.linalg.det(R)<0:return out
    roll=math.degrees(math.atan2(R[1,0],R[0,0]));anis=float(s.max()/s.min())
    if not np.isfinite(roll)or anis>2.3 or not .35<s.min()<2.5:return out
    out.update(accepted=True,reason='STATIC_PRINT_REGISTRATION_RELATIVE_ROTATION',relative_roll_deg=roll,local_anisotropy=anis,
        perspective_or_sideview_confounded=anis>1.12,confidence='SUPPORTED_PRINT_MATCH_NOT_PHYSICAL_POSE_CALIBRATION',H_reference_to_query_normalized=H.tolist(),inlier_reference_xy=aa.tolist(),inlier_query_xy=bb.tolist())
    return out

def tile(r,q,result):
    img=cv2.cvtColor(q['gray'],cv2.COLOR_GRAY2BGR)
    img[~q['mask']]=(img[~q['mask']]*.35).astype(np.uint8)
    if result['accepted']:
        H=np.asarray(result['H_reference_to_query_normalized']);p=project(H,[[128,35],[128,221]])
        cv2.line(img,tuple(np.rint(p[0]).astype(int)),tuple(np.rint(p[1]).astype(int)),(255,255,0),1)
        for x,y in result['inlier_query_xy']:cv2.circle(img,(round(x),round(y)),2,(0,255,0),1)
        label=f'{r["id"]} rel={result["relative_roll_deg"]:+.1f}deg n={result["inliers"]}'
    else:label=f'{r["id"]} UNKNOWN n={result.get("inliers",0)}'
    pane=np.full((288,256,3),18,np.uint8);pane[:256]=img
    cv2.putText(pane,label,(3,275),cv2.FONT_HERSHEY_SIMPLEX,.38,(230,230,230),1)
    return pane

def main():
    rr=load_prepared(TASK/'prepared_train.jsonl')+load_prepared(TASK/'prepared_validation.jsonl')
    ref_record=next(r for r in rr if r['id']=='D_002');ref,_=patch(ref_record)
    save_image(HERE/'reference_D002_feature_mask.png',cv2.cvtColor(ref['gray'],cv2.COLOR_GRAY2BGR)*ref['mask'][:,:,None].astype(np.uint8))
    rows=[];tiles=[]
    for r in rr:
        q,reason=patch(r)
        result=dict(accepted=False,reason=reason)if q is None else infer(ref,q)
        rows.append(dict(id=r['id'],split=r['split'],group=r['source_group'],sha256=r['sha256'],scene=r['scene'],**result))
        if q is not None:tiles.append(tile(r,q,result))
    for i in range(math.ceil(len(tiles)/24)):
        sheet=np.full((288*4,256*6,3),12,np.uint8)
        for j,t in enumerate(tiles[i*24:(i+1)*24]):
            y,x=divmod(j,6);sheet[y*288:(y+1)*288,x*256:(x+1)*256]=t
        save_image(HERE/f'roll_contact_{i+1:02d}.png',sheet)
    (HERE/'relative_roll_records.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in rows),'utf-8')
    def summary(sub):
        a=[r for r in sub if r['accepted']];v=np.array([r['relative_roll_deg']for r in a]);near=np.array([r['relative_roll_deg']for r in a if not r['perspective_or_sideview_confounded']])
        return dict(records=len(sub),supported=len(a),relative_degrees_min=float(v.min())if len(v)else None,max=float(v.max())if len(v)else None,
            percentiles_5_50_95=np.percentile(v,[5,50,95]).tolist()if len(v)else[],beyond_absolute8_count=int((abs(v)>8).sum()),
            lower_anisotropy_count=len(near),lower_anisotropy_min=float(near.min())if len(near)else None,lower_anisotropy_max=float(near.max())if len(near)else None)
    report=dict(status='RELATIVE_ROLL_AUDIT_NOT_ABSOLUTE_POSE',reference=dict(id='D_002',split='train',sha256=ref_record['sha256'],absolute_upright_verified=False),
        method='New-data SIFT/CLAHE static-print masked mutual matches + RANSAC homography; local Jacobian polar rotation at hub',
        code_technique_reference='algorithm_work/meter_accuracy_rebuild_20261024/registration/face.py; no old images or weights imported',
        mask='Printed annulus radius.40..86 of face radius; central hub/background/rim excluded, ±22deg needle and counterweight exclusion from available direct visual labels; no bar inversion. Unknown dynamic direction skipped.',
        angle='Image-coordinate clockwise positive relative to D002, NOT certified absolute roll; perspective/yaw can confound polar angle',
        groups={g:summary([r for r in rows if r['group']==g])for g in'DEFG'},
        train=summary([r for r in rows if r['split']=='train']),validation=summary([r for r in rows if r['split']=='validation']),
        H_opened=False,canonical_changed=False,training_executed=False,
        note='Audit metadata only, not production model inputs/pose labels. Existing labels/ROIs and run001/run002 untouched.',
        input_sha={p.name:sha(p)for p in[TASK/'prepared_train.jsonl',TASK/'prepared_validation.jsonl']})
    write(HERE/'roll_audit_summary.json',report);print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
