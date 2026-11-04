"""Shared C4 printed-landmark heatmaps, original MCU-compatible operators."""
import math
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

POINTS=('outer_psi_5_text_centroid','outer_psi_10_text_centroid','outer_psi_15_text_centroid',
        'upper_basketball_logo_centroid','middle_soccer_logo_centroid','lower_striped_ball_print_centroid')
LAYERS=('first','local.0','local.2','downs.0.0','downs.0.2','downs.1.0','downs.1.2',
        'downs.2.0','downs.2.2','context.0','fuse','head')
Y,X=np.mgrid[:64,:64].astype(np.float32)

class LandmarkNet(nn.Module):
    def __init__(self,heads=6):
        super().__init__();c=4
        self.first=nn.Conv2d(1,c,5,2,2)
        self.local=nn.Sequential(nn.Conv2d(c,c,5,1,2,groups=c),nn.ReLU(),nn.Conv2d(c,c,1),nn.ReLU())
        self.downs=nn.ModuleList();cin=c
        for _ in range(3):
            self.downs.append(nn.Sequential(nn.Conv2d(cin,cin,5,2,2,groups=cin),nn.ReLU(),nn.Conv2d(cin,8,1),nn.ReLU()));cin=8
        self.context=nn.Sequential(nn.Conv2d(8,8,5,1,2,groups=8),nn.ReLU())
        self.fuse=nn.Conv2d(12,4,1);self.head=nn.Conv2d(4,heads,1)
        for name,layer in self.named_modules():
            if isinstance(layer,nn.Conv2d)and name!='head':
                nn.init.kaiming_uniform_(layer.weight,mode='fan_in',nonlinearity='relu');nn.init.zeros_(layer.bias)
        nn.init.constant_(self.fuse.bias,.05);nn.init.normal_(self.head.weight,std=.01)
        nn.init.constant_(self.head.bias,-4.59511985)
    def forward(self,x):
        first=self.local(F.relu(self.first(x)));x=first
        for layer in self.downs:x=layer(x)
        x=self.context(x)
        x=F.relu(self.fuse(torch.cat([first,F.interpolate(x,size=(64,64),mode='nearest')],1)))
        return self.head(x)

def targets(points,sigmas,mask):
    heat=np.zeros((6,64,64),np.float32)
    for k,p in enumerate(points):
        if not mask[k]or p is None:continue
        px,py=np.asarray(p)/2;sig=float(sigmas[k])
        heat[k]=np.exp(-((X-px)**2+(Y-py)**2)/(2*sig*sig))
        heat[k,min(63,max(0,round(float(py)))),min(63,max(0,round(float(px))))]=1
    return heat

def focal(logits,target,mask):
    p=logits.sigmoid().clamp(1e-5,1-1e-5);m=mask[:,:,None,None]
    pos=target.eq(1)
    loss=(-p.log()*(1-p)**2*pos-(1-p).log()*p**2*(1-target)**4*~pos)*m
    return loss.sum()/(pos*m).sum().clamp(min=1)

def decode(logits,q15=False):
    if q15:
        index=np.clip(logits.astype(np.int16)+128,0,255)
        lut=np.rint(32767/(1+np.exp(-np.arange(-128,128,dtype=np.float64)/16))).astype(np.int32)
        values=lut[index].astype(np.float64)
        scale=32767.
    else:values=1/(1+np.exp(-np.clip(logits,-40,40)));scale=1.
    result=[]
    for v in values:
        y,x=np.unravel_index(v.argmax(),v.shape)
        yy,xx=np.mgrid[max(0,y-1):min(64,y+2),max(0,x-1):min(64,x+2)]
        w=v[yy,xx];den=max(float(w.sum()),1e-12)
        point=[float((w*xx).sum()/den)*2,float((w*yy).sum()/den)*2]
        far=v.copy();far[(X-x)**2+(Y-y)**2<=25]=0
        peak=float(v[y,x]/scale);margin=float((v[y,x]-far.max())/scale)
        accepted=peak>=.3 and margin>=.02
        result.append(dict(roi_xy=point,accepted=bool(accepted),peak=peak,margin=margin,
            visibility_evidence='sufficient'if accepted else'unknown',
            confidence_is_calibrated_probability=False))
    return result

def account(model):
    rows=[];handles=[]
    for name,m in model.named_modules():
        if isinstance(m,nn.Conv2d):
            def hook(layer,ins,out,name=name):
                rows.append(dict(name=name,input_shape=list(ins[0].shape),output_shape=list(out.shape),
                    weights=layer.weight.numel(),biases=layer.bias.numel(),
                    MAC=out.numel()*(layer.in_channels//layer.groups)*layer.kernel_size[0]**2))
            handles.append(m.register_forward_hook(hook))
    with torch.inference_mode():model(torch.zeros(1,1,128,128))
    for h in handles:h.remove()
    return dict(parameters=sum(p.numel()for p in model.parameters()),nominal_MAC=sum(r['MAC']for r in rows),
        planned_W8_S32bias_bytes=sum(r['weights']+4*r['biases']for r in rows),layers=rows,
        largest_single_activation_U7_bytes=16384,naive_six_head_maps_bytes=24576,
        planned_one_head_decode_map_bytes=4096,shared_two_arena_bytes=32768,source_row_cache_bytes=640,
        no_new_full_RAW_ROI_snapshot=True,all_arrays_and_code_link_fit_pending=True,
        quant_contract='InputU8-128/Sin1/128, W8/S32bias, signedshiftRNE-even, U7ReLU, S8lastlogits1/16, fusedbranchscales foldedintoW')
