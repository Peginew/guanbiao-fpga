"""Train-only calibrated C4 W8/U7 export and exact scalar arithmetic contract.

No native images, pressure, G labels, or G activation maxima enter quantization.
The CHW NumPy implementation is an arithmetic reference; MCU activation ABI is HWC.
"""
from pathlib import Path
import argparse,hashlib,json,math,sys,time
sys.dont_write_bytecode=True
import cv2
import numpy as np
import torch
from landmark_model import LandmarkNet,LAYERS,POINTS,decode

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
DATA=HERE.parent/'data';FROZEN_DATA=ROOT/'algorithm_work/meter_cnn_training_20261102'
def cache_path(split):return DATA/'roi_cache_train.npz' if split=='train' else FROZEN_DATA/'roi_cache_validation.npz'
def label_path(split):return DATA/'train_landmarks.jsonl' if split=='train' else ROOT/'algorithm_work/meter_landmark_mcu_training_20261103/data/validation_landmarks.jsonl'
PEAK_Q15=9831;MARGIN_Q15=656
SIGMOID_Q15=np.rint(32767/(1+np.exp(-np.arange(-128,128,dtype=np.float64)/16))).astype(np.int32)
QUANT_PLAN=dict(input='U8-128 signed8, real scale1/128',weights='signed8, power2 scale, RNEeven',
    biases='signed32 at input_scale*weight_scale',activation='unsigned7_relu_or_signed8_final',
    shifts='signed power2; rightshift signed-magnitude RNEeven',final_logit_scale=1/16,
    calibration='AB+DEF295 original and4fixedtrainonlyaugmentation views each; noGscaleselection',
    calibration_seed=1110,calibration_views_per_image=4,
    augmentation=dict(roll_deg=[-15,15],scale=[.92,1.08],translation=[-4,4],gain=[.8,1.2],bias=[-12,12],noise=False),
    activation_scale='2^ceil(log2(max_positive/120)), lowerfloor2^-20',
    fuse='Fold local4/context8 branchscale into weights; no new feature rescale',
    decoder=dict(sigmoid='RNEeven(32767sigmoid(q/16))',peak_min_q15=PEAK_Q15,margin_min_q15=MARGIN_Q15,
        far_exclusion_heat_radius=5,point='ROI_Q8=RNEeven(sum_w*heat_coordinate*512/sum_w)',
        evidence_not_calibrated_probability=True),whole_application_link_or_board_verified=False)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')
def readrows(p):return[json.loads(s)for s in Path(p).read_text('utf-8-sig').splitlines()if s.strip()]
def power(x):return 2.**math.ceil(math.log2(max(float(x),2**-20)))

def rne_div(n,d):
    assert d>0
    q,r=divmod(abs(int(n)),int(d));q+=int(2*r>d or(2*r==d and q%2==1))
    return -q if n<0 else q

def rq(x,shift,relu):
    x=np.asarray(x,np.int64)
    if shift>0:
        a=np.abs(x);q=a>>shift;r=a&((1<<shift)-1);half=1<<(shift-1)
        q+=((r>half)|((r==half)&((q&1)!=0)));q=np.where(x<0,-q,q)
    elif shift<0:q=x*(1<<-shift)
    else:q=x
    return np.clip(q,0 if relu else -128,127).astype(np.int8)

def conv(x,l):
    k=l['w'].shape[-1];pad=k//2;stride=l['stride']
    a=np.pad(x.astype(np.int64),((0,0),(pad,pad),(pad,pad)))
    windows=np.lib.stride_tricks.sliding_window_view(a,(k,k),axis=(1,2))[:,::stride,::stride]
    if l['depthwise']:s=np.einsum('cyxij,cij->cyx',windows,l['w'][:,0].astype(np.int64),dtype=np.int64,optimize=True)
    else:s=np.einsum('cyxij,ocij->oyx',windows,l['w'].astype(np.int64),dtype=np.int64,optimize=True)
    s+=l['b'][:,None,None]
    assert s.min()>=-(1<<31) and s.max()<(1<<31),'MAC+bias exceeds signed32'
    return rq(s,l['shift'],l['relu'])

def forward(roi,layers,trace=False):
    assert roi.shape==(128,128) and roi.dtype==np.uint8
    out={};x=(roi.astype(np.int16)-128).astype(np.int8)[None]
    def layer(i,x):
        y=conv(x,layers[i])
        if trace:out[LAYERS[i]]=y.copy()
        return y
    x=layer(0,x);x=layer(1,x);first=layer(2,x);x=first
    for i in[3,5,7]:x=layer(i+1,layer(i,x))
    context=layer(9,x)
    # PC materializes concatenation only for clarity. The MCU fuses per pixel.
    cat=np.concatenate([first,context.repeat(8,1).repeat(8,2)],0)
    x=layer(10,cat);q=layer(11,x)
    return(q,out)if trace else q

def decode_integer(q):
    result=[];yyall,xxall=np.mgrid[:64,:64]
    for one in q:
        probs=SIGMOID_Q15[one.astype(np.int16)+128];y,x=np.unravel_index(probs.argmax(),probs.shape)
        yy,xx=np.mgrid[max(0,y-1):min(64,y+2),max(0,x-1):min(64,x+2)]
        w=probs[yy,xx].astype(np.int64);den=int(w.sum())
        pointq=[rne_div(int((w*xx).sum())*512,den),rne_div(int((w*yy).sum())*512,den)]
        far=probs.copy();far[(xxall-x)**2+(yyall-y)**2<=25]=0
        peak=int(probs[y,x]);margin=peak-int(far.max());accepted=peak>=PEAK_Q15 and margin>=MARGIN_Q15
        result.append(dict(roi_xy=[v/256 for v in pointq],roi_xy_q8=pointq,accepted=bool(accepted),
            peak=peak/32767,margin=margin/32767,peak_q15=peak,margin_q15=margin,
            visibility_evidence='sufficient'if accepted else'unknown',confidence_is_calibrated_probability=False))
    return result

def calibration_view(image,rng):
    degree=rng.uniform(-15,15);scale=rng.uniform(.92,1.08)
    M=cv2.getRotationMatrix2D((63.5,63.5),float(degree),float(scale));M[:,2]+=rng.uniform(-4,4,2)
    a=cv2.warpAffine(image,M,(128,128),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101).astype(np.float32)
    a=(a-128)*rng.uniform(.8,1.2)+128+rng.uniform(-12,12)
    return np.clip(np.rint(a),0,255).astype(np.uint8)

def quantize(model,train_images):
    maxima={n:0. for n in LAYERS};modules=dict(model.named_modules());hooks=[]
    for n in LAYERS:
        def hook(m,x,y,n=n):maxima[n]=max(maxima[n],float(y.detach().clamp(min=0).max()))
        hooks.append(modules[n].register_forward_hook(hook))
    rng=np.random.default_rng(QUANT_PLAN['calibration_seed'])
    with torch.inference_mode():
        for image in train_images:
            views=[image]+[calibration_view(image,rng)for _ in range(4)]
            a=np.stack([(v.astype(np.float32)-128)[None]/128 for v in views]);model(torch.from_numpy(a))
    for h in hooks:h.remove()
    scales={n:power(maxima[n]/120)for n in LAYERS};scales['head']=1/16
    previous=1/128;layers=[]
    for name in LAYERS:
        m=modules[name];w=m.weight.detach().numpy();b=m.bias.detach().numpy();ain=previous
        if name=='fuse':
            branch=np.r_[np.full(4,scales['local.2']),np.full(8,scales['context.0'])]
            w=w*branch[None,:,None,None];ain=1.
        ws=power(np.abs(w).max()/127);qw=np.clip(np.rint(w/ws),-127,127).astype(np.int8)
        qb=np.rint(b/(ain*ws)).astype(np.int64);assert np.abs(qb).max()<(1<<31)
        shift=round(math.log2(scales[name]/(ain*ws)));assert -31<=shift<=31
        layers.append(dict(name=name,w=qw,b=qb.astype(np.int32),shift=shift,relu=name!='head',stride=m.stride[0],
            depthwise=m.groups==m.in_channels==m.out_channels,input_scale=ain,weight_scale=ws,output_scale=scales[name]))
        previous=scales[name]
    return layers,maxima,scales

def load_layers(path):
    path=Path(path);z=np.load(path);meta=json.loads(path.with_suffix('.json').read_text('utf-8-sig'))
    return[dict(r,w=z[f'w{i}'],b=z[f'b{i}'])for i,r in enumerate(meta['layers'])]

def export_header(out,prefix,layers):
    guard=f'MROI_{prefix.upper()}_WEIGHTS_H'
    h=[f'#ifndef {guard}',f'#define {guard}','#include <stdint.h>',
        '#ifndef MROI_NN_LAYER_TYPE_DEFINED','#define MROI_NN_LAYER_TYPE_DEFINED',
        'typedef struct { const int8_t*w; const int32_t*b; uint8_t ci,co,k,stride,dw,relu; int8_t shift; } mroi_nn_layer;','#endif',
        '#ifndef LANDMARK_PEAK_Q15','#define LANDMARK_PEAK_Q15 9831','#define LANDMARK_MARGIN_Q15 656','#endif']
    for i,l in enumerate(layers):
        h.append(f'static const int8_t {prefix}_w{i}[]={{'+','.join(map(str,l['w'].reshape(-1)))+'};')
        h.append(f'static const int32_t {prefix}_b{i}[]={{'+','.join(map(str,l['b']))+'};')
    h.append(f'static const mroi_nn_layer {prefix}_layers[12]={{')
    for i,l in enumerate(layers):
        w=l['w'];ci=w.shape[0]if l['depthwise']else w.shape[1]
        h.append(f'{{{prefix}_w{i},{prefix}_b{i},{ci},{w.shape[0]},{w.shape[2]},{l["stride"]},{int(l["depthwise"])},{int(l["relu"])},{l["shift"]}}},')
    h+=['};','#endif'];(out/f'{prefix}_weights.h').write_text('\n'.join(h)+'\n','ascii')
    lut=['#ifndef MROI_SIGMOID_Q15_H','#define MROI_SIGMOID_Q15_H','#include <stdint.h>',
        'static const uint16_t mroi_sigmoid_q15[256]={'+','.join(map(str,SIGMOID_Q15))+'};','#endif']
    (out/'sigmoid_q15.h').write_text('\n'.join(lut)+'\n','ascii')

def preflight():
    checks=0
    for shift in range(-3,12):
        source=np.arange(-2049,2050,dtype=np.int64)
        for relu in[False,True]:
            expected=np.clip([rne_div(v,1<<shift)if shift>0 else int(v)*(1<<-shift)for v in source],0 if relu else-128,127)
            assert np.array_equal(rq(source,shift,relu),expected);checks+=len(source)
    q=np.full((6,64,64),-128,np.int8);q[:,20,30]=16
    p=decode_integer(q);assert all(x['accepted']and x['roi_xy_q8']==[60*256,40*256]for x in p)
    q.fill(-128);assert not any(x['accepted']for x in decode_integer(q))
    report=dict(status='INTEGER_MATH_SYNTHETIC_PREFLIGHT_PASS',checks=checks,plan=QUANT_PLAN,
        source_sha256=sha(__file__),G_or_labels_read=False,layer_trace_layout='CHW_numpy_and_HWC_export')
    write(HERE/'integer_preflight.json',report);print(json.dumps(report))

def main(args):
    args.out.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(4);cv2.setNumThreads(1);started=time.monotonic()
    ck=torch.load(args.checkpoint,weights_only=True);model=LandmarkNet(args.heads);model.load_state_dict(ck['state_dict']);model.eval()
    cache=np.load(cache_path('train'));assert len(cache['ids'])==295 and all(str(s).startswith(('A_','B_','D_','E_','F_'))for s in cache['ids'])
    layers,maxima,scales=quantize(model,cache['images'])
    metadata=dict(status='TRAIN_ONLY_QUANTIZATION_EXPORT',plan=QUANT_PLAN,checkpoint_sha256=sha(args.checkpoint),
        source_sha256=sha(__file__),model_source_sha256=sha(HERE/'landmark_model.py'),
        train_cache_sha256=sha(cache_path('train')),calibration_ids=cache['ids'].tolist(),maxima=maxima,scales=scales,
        layers=[{k:v for k,v in l.items()if k not in{'w','b'}}for l in layers],
        weight_bias_bytes=sum(l['w'].size+4*l['b'].size for l in layers),head_count=args.heads,
        activation_ABI='HWC; ndarrayreferenceCHW; weightsOIHW',memory='two16K+640row shared; nofullROIcopy; sequentialheads',
        MCU_integrated_link_and_camera_ROI_verification=False)
    archive={}
    for i,l in enumerate(layers):archive[f'w{i}']=l['w'];archive[f'b{i}']=l['b']
    np.savez(args.out/'integer_model.npz',**archive);write(args.out/'integer_model.json',metadata);export_header(args.out,args.prefix,layers)
    names=POINTS if args.heads==6 else('hub','legacy_tip_not_used')
    for split in['train','validation']:
        cache=np.load(cache_path(split));refs={r['id']:r for r in readrows(label_path(split))};output=[];qlogits=[]
        differences=[];flips=0;peaks=[];margins=[];float_accepted=integer_accepted=0
        for rid,image in zip(cache['ids'].tolist(),cache['images']):
            with torch.inference_mode():fv=model(torch.from_numpy((image.astype(np.float32)-128)[None,None]/128))[0].numpy()
            if rid=='D_002':
                q,tr=forward(image,layers,True);trace={'input_u8':image}
                for key,a in tr.items():trace[key.replace('.','_')+'_CHW']=a;trace[key.replace('.','_')+'_HWC']=a.transpose(1,2,0)
                np.savez_compressed(args.out/'D_002_layer_trace.npz',**trace)
            else:q=forward(image,layers)
            qlogits.append(q);ip=decode_integer(q);fp=decode(fv)
            for one,two in zip(ip,fp):
                differences.append(float(np.linalg.norm(np.asarray(one['roi_xy'])-two['roi_xy'])));flips+=one['accepted']!=two['accepted']
                peaks.append(abs(one['peak']-two['peak']));margins.append(abs(one['margin']-two['margin']))
                float_accepted+=two['accepted'];integer_accepted+=one['accepted']
            output.append(dict(id=rid,split=split,source_sha256=refs[rid]['source_sha256'],
                points=dict(zip(names,ip)),model_checkpoint_sha256=metadata['checkpoint_sha256'],
                integer_model_sha256=sha(args.out/'integer_model.npz'),query_GT_or_psi_used=False))
        (args.out/f'{split}_predictions.jsonl').write_text(''.join(json.dumps(r)+'\n'for r in output),'utf-8')
        np.savez_compressed(args.out/f'{split}_logits.npz',ids=cache['ids'],logits=np.stack(qlogits))
        write(args.out/f'{split}_float_integer_comparison.json',dict(images=len(output),heads_per_image=args.heads,
            point_displacement_mean=float(np.mean(differences)),point_displacement_max=float(np.max(differences)),
            float_accepted_heads=int(float_accepted),integer_accepted_heads=int(integer_accepted),evidence_acceptance_flips=int(flips),
            peak_absdifference_max=float(np.max(peaks)),margin_absdifference_max=float(np.max(margins)),
            quantization_parameters_selected_on_train_only=True,unit='ROI pixels, not pressure',full_readout_evaluated=False))
    write(args.out/'export_receipt.json',dict(status='W8_INTEGER_REFERENCE_AND_HEADERS_EXPORTED_NOT_DEPLOYMENT',elapsed_s=time.monotonic()-started,
        model=metadata,output_sha256={p.name:sha(p)for p in args.out.iterdir()if p.is_file()},C_H_opened=False,hardware_actions=False))
    print(json.dumps(dict(status='exported',prefix=args.prefix,bytes=metadata['weight_bias_bytes'],elapsed_s=time.monotonic()-started)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['preflight','export']);p.add_argument('--checkpoint',type=Path)
    p.add_argument('--heads',type=int,choices=[2,6],default=6);p.add_argument('--prefix',default='landmark');p.add_argument('--out',type=Path)
    args=p.parse_args();preflight()if args.command=='preflight'else main(args)
