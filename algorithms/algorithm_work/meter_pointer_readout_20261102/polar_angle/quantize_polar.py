"""W8/U7 polar convolution reference; float ROI frontend/hub/decode remain.

This is not a full MCU implementation. Calibration uses train features only.
"""
from pathlib import Path
import json,math,sys
import numpy as np
import torch
import train_polar as p

OUT=p.HERE/'integer_reference'
NAMES=['first','depthwise','mix','head']

def power(x):return 2.**math.ceil(math.log2(max(float(x),2**-20)))
def requant(x,shift,relu):
    x=np.asarray(x,np.int64)
    if shift>0:
        a=np.abs(x);b=a>>shift;r=a&((1<<shift)-1);half=1<<(shift-1)
        q=b+((r>half)|((r==half)&((b&1)!=0)));q=np.where(x<0,-q,q)
    elif shift<0:q=x*(1<<(-shift))
    else:q=x
    return np.clip(q,0 if relu else-128,127).astype(np.int8)

def conv(x,w,b,layer):
    k=w.shape[-1];z=np.pad(x.astype(np.int64),((0,0),(k//2,k//2)),mode='wrap')
    z=np.lib.stride_tricks.sliding_window_view(z,k,axis=1)
    a=np.einsum('cxi,ci->cx',z,w[:,0].astype(np.int64),optimize=True) if layer['depthwise'] else np.einsum('cxi,oci->ox',z,w.astype(np.int64),optimize=True)
    a+=b[:,None]
    assert a.min()>=-(1<<31) and a.max()<(1<<31)
    q=requant(a,layer['shift'],layer['relu'])
    return q,dict(accumulator_min=int(a.min()),accumulator_max=int(a.max()),
                  lower_saturation=int((q==(0 if layer['relu']else-128)).sum()),upper_saturation=int((q==127).sum()),elements=q.size)

def forward(feature,layers,arrays):
    q=np.clip(np.rint(feature*64),-128,127).astype(np.int8);stats=[]
    for i,l in enumerate(layers):
        q,s=conv(q,arrays[f'w{i}'],arrays[f'b{i}'],l);stats.append(s)
    return q[0],stats

def main():
    OUT.mkdir(exist_ok=False);torch.set_num_threads(4)
    ck=torch.load(p.HERE/'run_001/best_weights.pt',weights_only=True)
    model=p.PolarNeedle();model.load_state_dict(ck['state_dict']);model.eval()
    tr=p.dataset('train');va=p.dataset('validation');maxima={n:0 for n in NAMES};handles=[]
    for n,m in model.named_modules():
        if n in NAMES:
            def hook(mod,args,y,key=n):maxima[key]=max(maxima[key],float(y.detach().clamp(min=0).max()))
            handles.append(m.register_forward_hook(hook))
    with torch.inference_mode():
        for start in range(0,len(tr),32):
            # Include Q6 input clipping in train-only activation calibration.
            x=np.stack([i['feature'] for i in tr[start:start+32]])
            model(torch.from_numpy(np.clip(np.rint(x*64),-128,127).astype(np.float32)/64))
    for h in handles:h.remove()
    layers=[];arrays={};scale=1/64;mods=dict(model.named_modules())
    for i,n in enumerate(NAMES):
        m=mods[n];w=m.weight.detach().numpy();b=m.bias.detach().numpy();ws=power(abs(w).max()/127)
        outscale=1/16 if n=='head' else power(maxima[n]/120)
        wq=np.clip(np.rint(w/ws),-127,127).astype(np.int8)
        bq=np.rint(b/(scale*ws)).astype(np.int64);assert np.abs(bq).max()<(1<<31)
        shift=round(math.log2(outscale/(scale*ws)));assert -31<=shift<=31
        bound=np.abs(wq.astype(np.int64)).sum((1,2))*(128 if i==0 else 127)+np.abs(bq)
        assert bound.max()<(1<<31)
        layers.append(dict(name=n,depthwise=m.groups==m.in_channels==m.out_channels,shift=shift,relu=n!='head',
                           input_scale=scale,weight_scale=ws,output_scale=outscale,weight_shape=list(wq.shape),
                           worst_case_accumulator_abs_bound=int(bound.max())))
        arrays[f'w{i}']=wq;arrays[f'b{i}']=bq.astype(np.int32);scale=outscale
    arrays['shifts']=np.array([l['shift'] for l in layers],np.int8);np.savez(OUT/'integer_weights.npz',**arrays)
    header=['/* Polar angle CNN only. No MCU execution or fixed-point frontend claim. */','#include <stdint.h>']
    for i,l in enumerate(layers):
        header.append(f'static const int8_t polar_w{i}[]={{'+','.join(map(str,arrays[f'w{i}'].ravel()))+'};')
        header.append(f'static const int32_t polar_b{i}[]={{'+','.join(map(str,arrays[f'b{i}'].ravel()))+'};')
    (OUT/'polar_weights_q8.h').write_text('\n'.join(header)+'\n','ascii')
    results=[];aggregate=[dict(accumulator_min=0,accumulator_max=0,upper_saturation=0,lower_saturation=0,elements=0) for _ in layers]
    clipped=[0,0];total=0
    for it in va:
        x=it['feature'];clipped[0]+=int((x*64<-128).sum());clipped[1]+=int((x*64>127).sum());total+=x.size
        q,st=forward(x,layers,arrays)
        for a,s in zip(aggregate,st):
            a['accumulator_min']=min(a['accumulator_min'],s['accumulator_min']);a['accumulator_max']=max(a['accumulator_max'],s['accumulator_max'])
            for k in ['upper_saturation','lower_saturation','elements']:a[k]+=s[k]
        theta,score,margin=p.decode(q.astype(np.float32)/16)
        h=it['frozen_hub'];center_ok=np.linalg.norm(np.array(it['center'])-63.5)<=20
        valid=score>=.3 and margin>=.02 and h['peaks'][0]>=.3 and h['margins'][0]>=.02 and center_ok and it['outside']<=.05
        r=dict(id=it['id'],model_name='polar_integer_conv_float_frontend_and_hub',angle_deg_image=theta,valid=bool(valid),score=score,margin=margin,
               source_sha256=it['record']['sha256'],target_present=it['record']['target_present'])
        if it['reference']is not None:r['angle_error_deg']=p.delta(theta,it['reference'])
        results.append(r)
    full=[r for r in results if 'angle_error_deg'in r];ac=[r for r in full if r['valid']];neg=[r for r in results if not r['target_present']]
    summary=dict(angle_error_deg=p.statistics([r['angle_error_deg']for r in full]),within5=sum(r['angle_error_deg']<=5 for r in full),
                 within10=sum(r['angle_error_deg']<=10 for r in full),full=len(full),accepted=len(ac),accepted_over10=sum(r['angle_error_deg']>10 for r in ac),negative_accepted=sum(r['valid']for r in neg))
    # Signed tie-to-even check against an independent exact-rational Python oracle.
    checks=0
    for shift in range(1,8):
        for x in range(-1024,1025):
            want=min(127,max(-128,round(x/(1<<shift))))
            assert int(requant(x,shift,False))==want;checks+=1
    p.write(OUT/'quantization.json',dict(layers=layers,source_checkpoint_sha256=p.sha(p.HERE/'run_001/best_weights.pt'),
            input='Q6 signed8, saturate [-128,127]',hidden='U7, train-only power-of-two scales',output='I8 logits scale1/16',
            rounding='nearest ties to even',weights_and_S32_bias_bytes=sum(arrays[f'w{i}'].size+4*arrays[f'b{i}'].size for i in range(4)),
            train_only_calibration_images=len(tr),validation_images=len(va),Q6_input_clip_low_high=clipped,Q6_input_elements=total,
            validation_activation_stats=aggregate,RNE_exact_oracle_checks=checks,test_H_opened=False,
            scope='ONLY polar convolution integer reference; hub, bilinear polar sampling and sigmoid/centroid decode remain floating PC; no complete MCU deployment claim'))
    p.write(OUT/'validation_evaluation.json',dict(status='POLAR_INTEGER_CONV_REFERENCE_FLOAT_FRONTEND_HUB_DECODE',summary=summary,rows=results))
    (OUT/'validation_predictions.jsonl').write_text(''.join(json.dumps(r)+'\n'for r in results),'utf-8')
    print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
