"""Two low-channel direct-ROI keypoint evidence candidates, reused development.

No geometric hub/needle is an input or an analysis prerequisite. Frozen automatic
ROI boxes are shared with the prior geometric baseline. Human uncertain points
supervise evidence only; pressure is never used to derive a point or angle.
"""
from pathlib import Path
import argparse, hashlib, importlib.util, json, math, time
import cv2
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[2]
DATA=HERE.parent/'data'
BASE=PROJECT/'algorithm_work/meter_read_route_audit_20261028'
ANN=PROJECT/'algorithm_work/meter_mcu_roi_bootstrap_20261029/annotations/manual_annotations_v1.json'
OUT=Path('C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/cnn')

def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
spec=importlib.util.spec_from_file_location('frozen_cap3',BASE/'evaluation/reference_cap3.py')
cap=importlib.util.module_from_spec(spec);spec.loader.exec_module(cap)

class Direct(nn.Module):
    """Low-channel encoder with high-resolution skip, direct image input.
    Keep64x64xc first activation. Encode to32x32x8,16x16x8,8x8x8;
    dilated-free 5x5 bottleneck covers125 native pixels. Upsample context only
    at final1x1 head. MCU need not materialize expanded context or concatenation.
    """
    def __init__(self,c):
        super().__init__();self.first=nn.Conv2d(1,c,5,2,2)
        self.local=nn.Sequential(nn.Conv2d(c,c,5,1,2,groups=c),nn.ReLU(),nn.Conv2d(c,c,1),nn.ReLU())
        self.downs=nn.ModuleList();cin=c
        for _ in range(3):
            self.downs.append(nn.Sequential(nn.Conv2d(cin,cin,5,2,2,groups=cin),nn.ReLU(),nn.Conv2d(cin,8,1),nn.ReLU()));cin=8
        self.context=nn.Sequential(nn.Conv2d(8,8,5,1,2,groups=8),nn.ReLU())
        self.fuse=nn.Conv2d(c+8,c,1);self.head=nn.Conv2d(c,2,1)
        nn.init.constant_(self.head.bias,-4.59511985)
    def forward(self,x,intermediates=False):
        first=self.local(F.relu(self.first(x)));x=first;ys=[first]
        for b in self.downs:x=b(x);ys.append(x)
        x=self.context(x);ys.append(x)
        x=F.relu(self.fuse(torch.cat([first,F.interpolate(x,size=(64,64),mode='nearest')],1)))
        ys.append(x);out=self.head(x)
        return (out,ys)if intermediates else out

def point(req,p):
    s=req['stride'];return [(p[0]-req['x0']-(s-1)/2)/s,(p[1]-req['y0']-(s-1)/2)/s]

def data():
    manual={r['id']:r for r in load(ANN)['records']};rows=load(BASE/'evaluation/results.json')['rows']
    items=[];manifest=[]
    for row in rows:
        ident=row['id'];a=manual.get(ident);gray=cap.native_gray(row['image_path'])
        req=row['levels']['C'].get('request');auto_ok=req is not None and req.get('in_bounds') and req.get('scale_ok')
        if a is not None and a.get('new_hub_xy_native') is not None and a.get('new_thin_tip_xy_native') is not None:
            # Unavailable live ROI stays flagged diagnostic-only, never silently
            # counted as an automatically available/readable image.
            if req is None or not req.get('in_bounds'):
                req=cap.request(row['annotation']['manual_face_bbox_xyxy_native'])
            if not req['in_bounds']:continue
            roi=cap.crop(gray,req);pts=np.array([point(req,a['new_hub_xy_native']),point(req,a['new_thin_tip_xy_native'])],np.float32)
            coarse=a['annotation_tier']=='COARSE_ONLY_PRECISION_UNKNOWN'
            items.append(dict(id=ident,roi=roi,points=pts,negative=False,auto_ok=bool(auto_ok),coarse=coarse,row=row,req=req))
            manifest.append(dict(id=ident,image_sha256=sha(row['image_path']),roi_sha256=hashlib.sha256(roi.tobytes()).hexdigest(),request=req,
                                 automatic_ROI_available=bool(auto_ok),points_roi=pts.tolist(),annotation_tier=a['annotation_tier'],negative=False,
                                 old_geometric_status=row['levels']['C']['status']))
        elif not row['gauge_present']:
            # Network-only unit rejection on a fixed image-centre window. The
            # production locator already rejected these; no end-to-end FAR claim.
            req={'x0':448,'y0':168,'stride':3,'radius':60,'in_bounds':True}
            roi=cap.crop(gray,req)
            items.append(dict(id=ident,roi=roi,points=np.full((2,2),-100,np.float32),negative=True,auto_ok=False,coarse=False,row=row,req=req))
            manifest.append(dict(id=ident,image_sha256=sha(row['image_path']),roi_sha256=hashlib.sha256(roi.tobytes()).hexdigest(),request=req,
                                 automatic_ROI_available=False,negative=True,scope='Fixed central crop, network rejection unit only'))
    DATA.mkdir(parents=True,exist_ok=True)
    (DATA/'direct_manifest.json').write_text(json.dumps(dict(scope='All reused development; no independent holdout',holdout_count=0,
          source_sha256={str(ANN):sha(ANN),str(BASE/'evaluation/results.json'):sha(BASE/'evaluation/results.json')},items=manifest),indent=2),encoding='utf-8')
    for it in items:cv2.imencode('.png',it['roi'])[1].tofile(str(DATA/(it['id']+'_roi.png')))
    return items

Y,X=np.mgrid[0:64,0:64].astype(np.float32)
def augment(rng,it):
    im=it['roi'];pts=it['points'].copy()
    angle=rng.uniform(-12,12);scale=rng.uniform(.92,1.08)
    m=cv2.getRotationMatrix2D((63.5,63.5),angle,scale);m[:,2]+=rng.uniform(-4,4,2)
    im=cv2.warpAffine(im,m,(128,128),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101).astype(np.float32)
    pts=np.c_[pts,np.ones(2)]@m.T
    im=(im-96)*rng.uniform(.6,1.7)+96+rng.uniform(-28,28)
    if rng.random()<.6:
        sx=rng.uniform(-.4,.4);sy=rng.uniform(-.4,.4)
        im*=np.clip(1+sx*(np.arange(128)[None,:]-64)/64+sy*(np.arange(128)[:,None]-64)/64,.3,1.7)
    im+=rng.normal(0,rng.uniform(0,7),im.shape)
    if rng.random()<.2:im=cv2.GaussianBlur(im,(3,3),rng.uniform(.2,.6))
    heat=np.zeros((2,64,64),np.float32)
    if not it['negative']:
        for k,(px,py)in enumerate(pts/2):
            if 1<=px<63 and 1<=py<63:
                sig=2.0 if it['coarse']else 1.25
                heat[k]=np.exp(-((X-px)**2+(Y-py)**2)/(2*sig**2))
                heat[k,int(round(py)),int(round(px))]=1
    return (np.clip(im,0,255).astype(np.float32)-128)[None]/128,heat

def loss_fn(logits,target):
    p=logits.sigmoid().clamp(1e-5,1-1e-5)
    pos=target.eq(1);neg=target.lt(1)
    a=-(p.log()*(1-p)**2*pos).sum()
    b=-((1-p).log()*p**2*(1-target)**4*neg).sum()
    return (a+b)/pos.sum().clamp(min=1)

def decode(logits):
    p=1/(1+np.exp(-np.clip(logits,-40,40)));points=[];peaks=[];margins=[]
    for v in p:
        y,x=np.unravel_index(v.argmax(),v.shape);peak=float(v[y,x]);peaks.append(peak)
        yy,xx=np.mgrid[max(0,y-1):min(64,y+2),max(0,x-1):min(64,x+2)]
        w=v[yy,xx];points.append([float((w*xx).sum()/w.sum())*2,float((w*yy).sum()/w.sum())*2])
        far=v.copy();far[(X-x)**2+(Y-y)**2<=25]=0;margins.append(peak-float(far.max()))
    return np.array(points),peaks,margins

def angular(a,b):return abs((a-b+180)%360-180)
def degrees(p):return math.degrees(math.atan2(p[1,1]-p[0,1],p[1,0]-p[0,0]))%360

def evaluate(model,items):
    rows=[]
    with torch.no_grad():
        for it in items:
            im=torch.from_numpy((it['roi'].astype(np.float32)-128)[None,None]/128)
            out=model(im)[0].numpy();p,peaks,margins=decode(out)
            # Evidence threshold is a development policy, not a calibrated prob.
            length=float(np.linalg.norm(p[1]-p[0]));center=float(np.linalg.norm(p[0]-63.5))
            valid=min(peaks)>=.3 and min(margins)>=.02 and 18<=length<=65 and center<=20
            r=dict(id=it['id'],negative=it['negative'],automatic_ROI_available=it['auto_ok'],coarse=it['coarse'],
                   hub_roi=p[0].tolist(),tip_roi=p[1].tolist(),peaks=peaks,margins=margins,valid=bool(valid),
                   angle_deg=degrees(p),endpoint_distance=length,hub_center_distance=center)
            if not it['negative']:
                r.update(hub_error_roi=float(np.linalg.norm(p[0]-it['points'][0])),tip_error_roi=float(np.linalg.norm(p[1]-it['points'][1])),
                         manual_point_angle=degrees(it['points']),angle_error_deg=angular(degrees(p),degrees(it['points'])))
                old=it['row']['levels']['C'];r['geometric_status']=old['status'];r['geometric_candidate']=old.get('geometry_candidate',False)
                if old.get('needle',{}).get('valid'):
                    na=old['needle'].get('angle_deg',old['needle'].get('angle'));r['geometric_angle_deg']=na
                    if na is not None:r['geometric_angle_error_deg']=angular(float(na),degrees(it['points']))
                cv=cv2.cvtColor(it['roi'],cv2.COLOR_GRAY2BGR)
                for k,pt in enumerate(p):cv2.circle(cv,tuple(np.rint(pt).astype(int)),3,(0,255,255)if k==0 else(255,0,255),1)
                for k,pt in enumerate(it['points']):cv2.circle(cv,tuple(np.rint(pt).astype(int)),4,(0,180,0),1)
                cv2.imwrite(str(OUT/f'c{model.first.out_channels}'/f'{it["id"]}_overlay.png'),cv2.resize(cv,(384,384),interpolation=cv2.INTER_NEAREST))
            rows.append(r)
    return rows

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--steps',type=int,default=700);ap.add_argument('--channels',type=int,nargs='+',default=[2,4]);args=ap.parse_args()
    torch.set_num_threads(4);torch.manual_seed(4929);rng=np.random.default_rng(4929);items=data()
    # Upright-only bounded-label development fit. All14 bounded frontal sources
    # train;5 coarse endpoints remain evaluation-only. No held-out claim.
    train=[r for r in items if not r['negative']and not r['coarse']]
    # Background-only crops are obtained from the left part of old training
    # images outside the gauge; no newer evaluation frame is used here.
    for it in list(train):
        gray=cap.native_gray(it['row']['image_path']);req={'x0':0,'y0':168,'stride':3,'in_bounds':True}
        # Exclude a background crop if its source overlaps the annotated face.
        b=it['row']['annotation']['manual_face_bbox_xyxy_native']
        if b[0]>=400:
            train.append(dict(id=it['id']+'_background',roi=cap.crop(gray,req),points=np.full((2,2),-100,np.float32),negative=True,coarse=False))
    OUT.mkdir(parents=True,exist_ok=True)
    for c in args.channels:
        w=OUT/f'c{c}';w.mkdir(exist_ok=True);model=Direct(c);opt=torch.optim.Adam(model.parameters(),lr=.003)
        t=time.monotonic();history=[]
        for step in range(args.steps):
            batch=[augment(rng,train[int(rng.integers(len(train)))])for _ in range(12)]
            x=torch.tensor(np.stack([v[0]for v in batch]));y=torch.tensor(np.stack([v[1]for v in batch]))
            opt.zero_grad();loss=loss_fn(model(x),y);loss.backward();opt.step()
            if step%100==0 or step+1==args.steps:
                history.append([step,float(loss.detach())]);print(f'c{c} step{step} loss{float(loss.detach()):.4f}',flush=True)
        model.eval();torch.save(dict(channels=c,state_dict=model.state_dict(),training_steps=args.steps,architecture="encoder_local_skip_upright_v4"),w/'weights.pt')
        rows=evaluate(model,items)
        def cohort(ids):
            z=[r for r in rows if not r['negative']and ids(r)];accepted=[r for r in z if r['valid']and r['automatic_ROI_available']]
            return dict(images=len(z),automatic_ROI_available=sum(r['automatic_ROI_available']for r in z),accepted=len(accepted),
                        all_evidence_angle_mae=float(np.mean([r['angle_error_deg']for r in z]))if z else None,
                        accepted_angle_mae=float(np.mean([r['angle_error_deg']for r in accepted]))if accepted else None,
                        accepted_within5deg=sum(r['angle_error_deg']<=5 for r in accepted),
                        false_accepted_over10deg=sum(r['angle_error_deg']>10 for r in accepted))
        summary=dict(old_reused_training=cohort(lambda r:r['id'].startswith('old')),newer_reused_development=cohort(lambda r:r['id'].startswith('new')),
                     network_unit_negative_false_accept=sum(r['negative']and r['valid']for r in rows),
                     independent_holdout=0)
        params=sum(p.numel()for p in model.parameters());mac=64*64*(25*c+25*c+c*c+(c+8)*c+2*c)+32*32*(25*c+c*8)+16*16*(25*8+8*8)+8*8*(25*8+8*8+25*8)
        report=dict(scope='Direct ROI PC candidate, all reused development, no MCU execution or precision-pressure validation',
                    channels=c,parameters=params,conv_MAC=mac,estimated_int8_two_activation_buffers=2*64*64*c,
                    first_layer_input_row_cache_bytes=5*128,weights_float_sha256=sha(w/'weights.pt'),history=history,
                    training_sources=[r['id']for r in train],elapsed_s=time.monotonic()-t,rows=rows,summary=summary,
                    caveat='Heatmap supervison derives from bounded human points, not masks; no pressure loss or geometric needle/axis input. Outputs can still be false; evidence score is not a calibrated correctness probability.')
        (w/'evaluation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(c,json.dumps(summary),flush=True)

if __name__=='__main__':main()
