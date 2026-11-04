"""Printed-face geometry only. Does not search an axle,needle or indicated value."""
from pathlib import Path
import hashlib,time
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
LANDMARKS=[('orange',97,73),('yellow',95,133),('zero',68,116),('02',60,100),
           ('04',62,77),('06',85,63),('08',107,63),('10',125,77),('12',129,100),('14',119,123)]
CONFIG=dict(ratio=.72,min_inliers=8,min_hull_fraction=.06,max_reprojection_px=2.,min_patches=5,patch_corr=.50)

def gray(im):return cv2.cvtColor(im,cv2.COLOR_BGR2GRAY) if im.ndim==3 else im
def project(H,points):return cv2.perspectiveTransform(np.asarray(points,np.float32)[None],np.asarray(H,dtype=np.float64))[0]
def correlation(a,b):
    a=a.astype(float).ravel();b=b.astype(float).ravel();a-=a.mean();b-=b.mean()
    return float(a@b/(np.linalg.norm(a)*np.linalg.norm(b)+1e-9))

class FaceRegistrar:
    def __init__(self):
        path=ROOT/'data/reference05.png';self.reference_sha256=hashlib.sha256(path.read_bytes()).hexdigest()
        ref=cv2.imdecode(np.fromfile(path,np.uint8),1)
        # Existing disclosed reference05 face calibration; canonical192 origin unchanged.
        scale=159/(30.5*3)
        self.reference_to_source=np.array([[scale,0,641-scale*95.5],[0,scale,427-scale*95.5],[0,0,1.]])
        self.reference=cv2.warpPerspective(ref,np.linalg.inv(self.reference_to_source),(192,192),flags=cv2.INTER_LINEAR)
        self.refgray=gray(self.reference)
        yy,xx=np.indices((192,192));r=np.hypot(xx-95,yy-97);a=np.degrees(np.arctan2(yy-97,xx-95))%360
        self.mask=(r>20)&(r<79)
        # Exclude the two needle/counterweight sectors of reference05 using a disclosed
        # reference-only mask. No online needle computation occurs in identity matching.
        for angle in (232.5,52.5):self.mask&=np.abs((a-angle+180)%360-180)>15
        self.sift=cv2.SIFT_create(nfeatures=4000,contrastThreshold=.008,edgeThreshold=15,sigma=1.2)
        self.clahe=cv2.createCLAHE(clipLimit=2.,tileGridSize=(8,8))
        self.kp,self.desc=self.sift.detectAndCompute(self.clahe.apply(self.refgray),np.uint8(self.mask)*255)

    def infer(self,image,bbox):
        started=time.perf_counter();h,w=image.shape[:2];x0,y0,x1,y1=map(float,bbox)
        padx=(x1-x0)*.14;pady=(y1-y0)*.14
        x0=max(0,int(x0-padx));y0=max(0,int(y0-pady));x1=min(w,int(x1+padx+1));y1=min(h,int(y1+pady+1))
        out=dict(accepted=False,reason='NO_VERIFIED_PRINTED_REGISTRATION',reference_sha256=self.reference_sha256,
                 reads_axle_or_needle=False,physical_pose_calibrated=False)
        if x1-x0<30 or y1-y0<30:return out
        crop=gray(image[y0:y1,x0:x1]);kp,desc=self.sift.detectAndCompute(self.clahe.apply(crop),None)
        out.update(reference_features=len(self.kp),source_features=len(kp))
        if desc is None or len(desc)<2:return out
        matches=[pair[0]for pair in cv2.BFMatcher().knnMatch(self.desc,desc,k=2)if len(pair)==2 and pair[0].distance<CONFIG['ratio']*pair[1].distance]
        out['matches']=len(matches)
        if len(matches)<CONFIG['min_inliers']:return out
        aa=np.float32([self.kp[m.queryIdx].pt for m in matches]);bb=np.float32([kp[m.trainIdx].pt for m in matches])+[x0,y0]
        cv2.setRNGSeed(1024);H,keep=cv2.findHomography(aa,bb,cv2.RANSAC,3.,maxIters=3000,confidence=.995)
        if H is None:return out
        keep=keep.ravel().astype(bool);n=int(keep.sum())
        if n<4:return out
        hull=float(cv2.contourArea(cv2.convexHull(aa[keep]))/192**2)
        err=float(np.median(np.linalg.norm(project(H,aa[keep])-bb[keep],axis=1)))
        out.update(inliers=n,hull_fraction=hull,median_reprojection_px=err,diagnostic_H192_to_source=H.tolist())
        if n<CONFIG['min_inliers'] or hull<CONFIG['min_hull_fraction'] or err>CONFIG['max_reprojection_px']:return out
        corners=project(H,[[4,4],[187,4],[187,187],[4,187]])
        if not np.isfinite(corners).all()or not cv2.isContourConvex(corners)or cv2.contourArea(corners,oriented=True)<400:return out
        patch=cv2.warpPerspective(image,np.linalg.inv(H),(192,192),flags=cv2.INTER_LINEAR,borderValue=(255,255,255))
        gg=gray(patch);support=[]
        for name,x,y in LANDMARKS:
            sl=np.s_[y-8:y+9,x-8:x+9];c=correlation(gg[sl],self.refgray[sl]);support.append(dict(name=name,correlation=c))
        count=sum(v['correlation']>=CONFIG['patch_corr']for v in support)
        out.update(supported_patches=count,patches=support)
        if count<CONFIG['min_patches']:return out
        theta=np.arange(180)*np.pi/90;circle=project(H,np.c_[95.5+91.5*np.cos(theta),95.5+91.5*np.sin(theta)])
        full=bool(np.all(circle[:,0]>=0)and np.all(circle[:,0]<=w-1)and np.all(circle[:,1]>=0)and np.all(circle[:,1]<=h-1))
        ellipse=cv2.fitEllipse(circle.reshape(-1,1,2));ratio=float(min(ellipse[1])/max(ellipse[1]))
        out.update(accepted=True,reason='PRINTED_FACE_REGISTERED',H192_to_source=H.tolist(),quad=corners.tolist(),
                   contour=circle.tolist(),pose_ratio=ratio,full_face_inside_image=full,
                   elapsed_ms=(time.perf_counter()-started)*1000)
        return out

    def rectify(self,image,result):
        if not result.get('accepted'):raise ValueError('Verified registration required')
        return cv2.warpPerspective(image,np.linalg.inv(np.asarray(result['H192_to_source'])),(192,192),flags=cv2.INTER_LINEAR,borderValue=(255,255,255))
