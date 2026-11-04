"""Static-print relative orientation without query GT keypoints or pressure."""
from pathlib import Path
import json,hashlib,math
import cv2
import numpy as np

SIZE=256
OSD=[[32,15,292,181],[704,40,1240,211]]

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def project(H,p):return cv2.perspectiveTransform(np.asarray(p,np.float32)[None],np.asarray(H,np.float64))[0]

class PrintPose:
    def __init__(self,reference_path,reference_box):
        self.reference_path=str(reference_path);self.reference_box=list(reference_box)
        self.sift=cv2.SIFT_create(nfeatures=2500,contrastThreshold=.008,edgeThreshold=15,sigma=1.2)
        self.clahe=cv2.createCLAHE(2.,(8,8))
        self.reference=self.features(reference_path,reference_box,reference=True)

    def features(self,path,box,reference=False):
        im=cv2.imdecode(np.frombuffer(Path(path).read_bytes(),np.uint8),cv2.IMREAD_GRAYSCALE)
        if im is None or im.shape!=(720,1280):raise ValueError('native1280x720 required')
        x0,y0,x1,y1=map(float,box);diameter=max(x1-x0,y1-y0)
        if diameter<140 or diameter>650:return None
        scale=240/diameter;A=np.array([[scale,0,128-(x0+x1)/2*scale],[0,scale,128-(y0+y1)/2*scale]],np.float64)
        gray=cv2.warpAffine(im,A,(256,256),flags=cv2.INTER_LINEAR,borderValue=0)
        yy,xx=np.mgrid[:256,:256];radius=np.hypot(xx-128,yy-128)
        mask=(radius>.38*120)&(radius<.86*120)
        if reference:
            # Fixed one-time manual reference exclusion, NOT a query needle estimate.
            # D002 thin needle points roughly281deg, counterweight101deg.
            angles=np.degrees(np.arctan2(yy-128,xx-128))
            for a in [281,101]:mask&=abs((angles-a+180)%360-180)>24
        for rect in OSD:
            a=np.array(rect[:2])*scale+A[:,2];b=np.array(rect[2:])*scale+A[:,2]
            mask&=~((xx>=a[0])&(xx<b[0])&(yy>=a[1])&(yy<b[1]))
        kp,desc=self.sift.detectAndCompute(self.clahe.apply(gray),cv2.erode(mask.astype(np.uint8),np.ones((7,7),np.uint8))*255)
        keep=[]
        for i,k in enumerate(kp):
            x,y=map(int,k.pt);r=max(4,round(k.size))
            if mask[max(0,y-r):min(256,y+r+1),max(0,x-r):min(256,x+r+1)].all():keep.append(i)
        return dict(gray=gray,mask=mask,kp=[kp[i]for i in keep],desc=desc[keep]if desc is not None and keep else None)

    def infer(self,path,box):
        q=self.features(path,box);r=self.reference
        out=dict(accepted=False,reason='NO_STATIC_PRINT_POSE',query_uses_GT_keypoints=False,query_uses_pressure=False,reference_sha256=sha(self.reference_path),pose_code_sha256=sha(__file__))
        if q is None or q['desc']is None or r is None or r['desc']is None or len(q['desc'])<2:return out
        mm=[m[0]for m in cv2.BFMatcher().knnMatch(r['desc'],q['desc'],k=2)if len(m)==2 and m[0].distance<.72*m[1].distance]
        back=cv2.BFMatcher().knnMatch(q['desc'],r['desc'],k=1)
        mm=[m for m in mm if back[m.trainIdx][0].trainIdx==m.queryIdx]
        out.update(matches=len(mm),query_features=len(q['kp']))
        if len(mm)<10:return out
        aa=np.float32([r['kp'][m.queryIdx].pt for m in mm]);bb=np.float32([q['kp'][m.trainIdx].pt for m in mm])
        cv2.setRNGSeed(20261102);H,keep=cv2.findHomography(aa,bb,cv2.RANSAC,2.5,maxIters=3000,confidence=.995)
        if H is None:return out
        keep=keep.ravel().astype(bool);aa=aa[keep];bb=bb[keep]
        hull=float(cv2.contourArea(cv2.convexHull(aa))/256**2)if len(aa)>=3 else 0.
        err=float(np.median(np.linalg.norm(project(H,aa)-bb,axis=1)))
        quadrants=len(set((x>128,y>128)for x,y in aa));unique=len(set((round(float(x)/3),round(float(y)/3))for x,y in aa))
        out.update(inliers=len(aa),hull_fraction=hull,quadrants=quadrants,unique_locations=unique,median_reprojection_px=err)
        if len(aa)<10 or unique<8 or quadrants<3 or hull<.055 or err>1.8:return out
        c=project(H,[[128,128]])[0];jx=project(H,[[129,128]])[0]-c;jy=project(H,[[128,129]])[0]-c
        J=np.c_[jx,jy];u,s,v=np.linalg.svd(J);R=u@v
        if np.linalg.det(R)<0 or s.min()<.35 or s.max()>2.5:return out
        anis=float(s.max()/s.min());angle=math.degrees(math.atan2(R[1,0],R[0,0]))
        out.update(relative_roll_deg=angle,local_anisotropy=anis,H_reference_to_query=H.tolist())
        if anis>1.15:
            out['reason']='PRINT_POSE_HAS_EXCESSIVE_ANISOTROPY_FOR_ROLL_ONLY_READOUT';return out
        out.update(accepted=True,reason='STATIC_PRINT_RELATIVE_POSE_SUPPORTED',
                   absolute_upright=False,physical_yaw_pitch_calibrated=False)
        return out

def query_box(record):
    # A manual face bbox is an explicitly disclosed locator proxy, not label-free detector success.
    if record.get('bbox_native_xyxy')is not None:return record['bbox_native_xyxy']
    q=record['roi_request'];span=128*q['stride']
    return [q['x0'],q['y0'],q['x0']+span,q['y0']+span]

