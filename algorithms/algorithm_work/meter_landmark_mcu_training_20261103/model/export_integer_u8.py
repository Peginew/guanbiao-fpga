"""Single U8-hidden numerical deployment variant, without retraining or G tuning.

The original U7 exporter and all its artifacts remain immutable. Descriptor
relu=2 means U8[0,255]; relu=1 belongs to the unchanged U7 polar network.
First CNN input is signed (U8-128); every subsequent CNN input is unsigned.
"""
from pathlib import Path
import argparse,copy,hashlib,json,math,sys,time
sys.dont_write_bytecode=True
import cv2
import numpy as np
import torch
import export_integer as old
from landmark_model import LandmarkNet,LAYERS,POINTS,decode

HERE=Path(__file__).resolve().parent;DATA=old.DATA
PLAN=copy.deepcopy(old.QUANT_PLAN)
PLAN.update(activation='unsigned8_relu_or_signed8_final',activation_scale='2^ceil(log2(max_positive/240)), lowerfloor2^-20',
    descriptor_relu_2='clip0..255 uint8; all downstream CNN consumers unsigned; first input remains signed8',
    same_learned_weights_and_no_training=True,old_W8_arrays_must_remain_exact=True,
    one_fixed_numerical_variant_no_G_search=True)

def rq(x,shift,relu):
    x=np.asarray(x,np.int64)
    if shift>0:
        a=np.abs(x);q=a>>shift;r=a&((1<<shift)-1);half=1<<(shift-1)
        q+=((r>half)|((r==half)&((q&1)!=0)));q=np.where(x<0,-q,q)
    elif shift<0:q=x*(1<<-shift)
    else:q=x
    if relu==2:return np.clip(q,0,255).astype(np.uint8)
    if relu==1:return np.clip(q,0,127).astype(np.int8)
    return np.clip(q,-128,127).astype(np.int8)

def conv(x,l):
    k=l['w'].shape[-1];pad=k//2;stride=l['stride']
    # astype must preserve U8 values128..255, never reinterpret them as S8.
    a=np.pad(x.astype(np.int64),((0,0),(pad,pad),(pad,pad)))
    windows=np.lib.stride_tricks.sliding_window_view(a,(k,k),axis=(1,2))[:,::stride,::stride]
    if l['depthwise']:s=np.einsum('cyxij,cij->cyx',windows,l['w'][:,0].astype(np.int64),dtype=np.int64,optimize=True)
    else:s=np.einsum('cyxij,ocij->oyx',windows,l['w'].astype(np.int64),dtype=np.int64,optimize=True)
    s+=l['b'][:,None,None]
    assert s.min()>=-(1<<31) and s.max()<(1<<31),'S32 MAC+bias unsafe'
    return rq(s,l['shift'],l['relu'])

def forward(roi,layers,trace=False):
    assert roi.shape==(128,128) and roi.dtype==np.uint8
    out={};x=(roi.astype(np.int16)-128).astype(np.int8)[None]
    def run(i,a):
        q=conv(a,layers[i])
        if trace:out[LAYERS[i]]=q.copy()
        return q
    x=run(0,x);x=run(1,x);first=run(2,x);x=first
    for i in[3,5,7]:x=run(i+1,run(i,x))
    ctx=run(9,x);cat=np.concatenate([first,ctx.repeat(8,1).repeat(8,2)],0)
    assert cat.dtype==np.uint8
    q=run(11,run(10,cat));assert q.dtype==np.int8
    return(q,out)if trace else q

def load_layers(path):
    path=Path(path);z=np.load(path);m=json.loads(path.with_suffix('.json').read_text('utf-8-sig'))
    return[dict(r,w=z[f'w{i}'],b=z[f'b{i}'])for i,r in enumerate(m['layers'])]

def quantize(model,train_images,old_npz):
    # Use exactly the original DEF-only five views, seed and maxima. No G data.
    previous_layers,maxima,previous_scales=old.quantize(model,train_images)
    modules=dict(model.named_modules());scales={n:old.power(maxima[n]/240)for n in LAYERS};scales['head']=1/16
    previous=1/128;layers=[];bounds=[];frozen=np.load(old_npz)
    for i,name in enumerate(LAYERS):
        m=modules[name];w=m.weight.detach().numpy();b=m.bias.detach().numpy();ain=previous
        if name=='fuse':
            branch=np.r_[np.full(4,scales['local.2']),np.full(8,scales['context.0'])]
            w=w*branch[None,:,None,None];ain=1.
        ws=old.power(np.abs(w).max()/127);qw=np.clip(np.rint(w/ws),-127,127).astype(np.int8)
        # Deployment change must not silently modify even the W8 arrays.
        assert np.array_equal(qw,frozen[f'w{i}']) and np.array_equal(qw,previous_layers[i]['w'])
        qb=np.rint(b/(ain*ws)).astype(np.int64);assert np.abs(qb).max()<(1<<31)
        shift=round(math.log2(scales[name]/(ain*ws)));assert -31<=shift<=31
        bound=int((np.abs(qw.astype(np.int64)).reshape(qw.shape[0],-1).sum(1)*(128 if i==0 else 255)+np.abs(qb)).max())
        assert bound<(1<<31),f'{name} conservative S32 bound unsafe'
        bounds.append(dict(name=name,conservative_S32_abs_bound=bound,W8_unchanged=True))
        layers.append(dict(name=name,w=qw,b=qb.astype(np.int32),shift=shift,relu=0 if name=='head' else 2,
            stride=m.stride[0],depthwise=m.groups==m.in_channels==m.out_channels,input_scale=ain,weight_scale=ws,
            output_scale=scales[name],input_signed=i==0,output_unsigned=name!='head'))
        previous=scales[name]
    return layers,maxima,scales,bounds

def preflight():
    test=np.array([[[-128,-1,0,127]]],np.int8)
    one=dict(w=np.ones((1,1,1,1),np.int8),b=np.zeros(1,np.int32),shift=0,stride=1,depthwise=False,relu=2)
    assert np.array_equal(conv(test,one),np.array([[[0,0,0,127]]],np.uint8))
    test=np.array([[[0,127,128,200,255]]],np.uint8)
    assert np.array_equal(conv(test,one),test)
    signed=one.copy();signed['relu']=0
    assert np.array_equal(conv(test,signed),np.array([[[0,127,127,127,127]]],np.int8))
    for s in range(-3,12):
        a=np.arange(-4096,4097,dtype=np.int64)
        expected=np.clip([old.rne_div(v,1<<s)if s>0 else int(v)*(1<<-s)for v in a],0,255)
        assert np.array_equal(rq(a,s,2),expected)
    old.write(HERE/'u8_integer_preflight.json',dict(status='PASS_U8_UNSIGNED_CONSUMER_AND_RNE_SYNTHETIC',
        source_sha256=old.sha(__file__),plan=PLAN,values_over_127_preserved=True,
        first_input_signed=True,final_output_signed=True,no_data_or_G_opened=True))
    print('PASS U8 unsigned inputs128/200/255, signedfirst, signedlast and RNE')

def main(args):
    args.out.mkdir(parents=True,exist_ok=False);torch.set_num_threads(4);cv2.setNumThreads(1);start=time.monotonic()
    ck=torch.load(args.checkpoint,weights_only=True);model=LandmarkNet(args.heads);model.load_state_dict(ck['state_dict']);model.eval()
    cache=np.load(DATA/'roi_cache_train.npz');assert len(cache['ids'])==177 and all(str(s).startswith(('D_','E_','F_'))for s in cache['ids'])
    layers,maxima,scales,bounds=quantize(model,cache['images'],args.old_npz)
    meta=dict(status='U8_HIDDEN_SINGLE_DEPLOYMENT_NUMERICAL_VARIANT',plan=PLAN,checkpoint_sha256=old.sha(args.checkpoint),
        original_U7_integer_model_sha256=old.sha(args.old_npz),source_sha256=old.sha(__file__),
        frozen_old_exporter_sha256=old.sha(HERE/'export_integer.py'),model_source_sha256=old.sha(HERE/'landmark_model.py'),
        calibration_ids=cache['ids'].tolist(),calibration_cache_sha256=old.sha(DATA/'roi_cache_train.npz'),
        maxima=maxima,scales=scales,head_count=args.heads,W8_arrays_exactly_unchanged=True,S32_bounds=bounds,
        layers=[{k:v for k,v in l.items()if k not in{'w','b'}}for l in layers],
        weight_bias_bytes=sum(l['w'].size+4*l['b'].size for l in layers),activation_ABI='HWC uint8 hidden; CHW reference',
        arena_bytes_unchanged=32768,source_rows_unchanged=640,training_steps=0,board_or_flash_actions=False)
    archive={}
    for i,l in enumerate(layers):archive[f'w{i}']=l['w'];archive[f'b{i}']=l['b']
    np.savez(args.out/'integer_model.npz',**archive);old.write(args.out/'integer_model.json',meta)
    old.export_header(args.out,args.prefix,layers)
    p=args.out/f'{args.prefix}_weights.h';s=p.read_text('ascii');s=s.replace('#include <stdint.h>',
        '#include <stdint.h>\n/* relu=2:U8 hidden, all downstream CNN consumers unsigned; first input S8. */\n#define MROI_CNN_HIDDEN_U8 1',1);p.write_text(s,'ascii')
    names=POINTS if args.heads==6 else('hub','legacy_tip_not_used')
    ftrace={};hooks=[];modules=dict(model.named_modules())
    def attach():
        for n in LAYERS:
            def hook(m,x,y,n=n):ftrace[n]=y.detach().numpy()[0].copy()
            hooks.append(modules[n].register_forward_hook(hook))
    attach();errs={n:dict(abs_sum=0.,max_abs=0.,N=0,above127=0,saturated255=0)for n in LAYERS}
    for split in['train','validation']:
        cache=np.load(DATA/f'roi_cache_{split}.npz');refs={r['id']:r for r in old.readrows(DATA/f'prepared_{split}.jsonl')}
        output=[];qlogits=[];disps=[];flips=0;fa=ia=0;peakdiff=[];margindiff=[];headstats={n:dict(displacement=[],flips=0,float_accepted=0,integer_accepted=0)for n in names}
        for rid,image in zip(cache['ids'].tolist(),cache['images']):
            with torch.inference_mode():fv=model(torch.from_numpy((image.astype(np.float32)-128)[None,None]/128))[0].numpy()
            q,tr=forward(image,layers,True);qlogits.append(q);ip=old.decode_integer(q);fp=decode(fv)
            if split=='train':
                for l in layers:
                    n=l['name'];a=np.maximum(ftrace[n],0)if l['relu']else ftrace[n];error=np.abs(a-tr[n].astype(np.float64)*l['output_scale']);e=errs[n]
                    e['abs_sum']+=float(error.sum());e['N']+=error.size;e['max_abs']=max(e['max_abs'],float(error.max()))
                    if l['relu']:e['above127']+=int((tr[n]>127).sum());e['saturated255']+=int((tr[n]==255).sum())
            if rid=='D_002':
                arrays={'input_u8':image}
                for key,a in tr.items():arrays[key.replace('.','_')+'_CHW']=a;arrays[key.replace('.','_')+'_HWC']=a.transpose(1,2,0)
                np.savez_compressed(args.out/'D_002_layer_trace.npz',**arrays)
            for name,one,two in zip(names,ip,fp):
                d=float(np.linalg.norm(np.asarray(one['roi_xy'])-two['roi_xy']));flip=one['accepted']!=two['accepted'];disps.append(d);flips+=flip
                fa+=two['accepted'];ia+=one['accepted'];peakdiff.append(abs(one['peak']-two['peak']));margindiff.append(abs(one['margin']-two['margin']))
                h=headstats[name];h['displacement'].append(d);h['flips']+=int(flip);h['float_accepted']+=two['accepted'];h['integer_accepted']+=one['accepted']
            output.append(dict(id=rid,split=split,source_sha256=refs[rid]['sha256'],points=dict(zip(names,ip)),
                model_checkpoint_sha256=meta['checkpoint_sha256'],integer_model_sha256=old.sha(args.out/'integer_model.npz'),
                query_GT_or_psi_used=False,activation='U8_hidden_S8first_and_final'))
        (args.out/f'{split}_predictions.jsonl').write_text(''.join(json.dumps(r)+'\n'for r in output),'utf-8')
        np.savez_compressed(args.out/f'{split}_logits.npz',ids=cache['ids'],logits=np.stack(qlogits))
        for h in headstats.values():
            h['point_displacement_mean']=float(np.mean(h['displacement']));h['point_displacement_max']=float(max(h['displacement']));del h['displacement']
        old.write(args.out/f'{split}_float_integer_comparison.json',dict(images=len(output),heads_per_image=args.heads,
            point_displacement_mean=float(np.mean(disps)),point_displacement_max=max(disps),
            float_accepted_heads=int(fa),integer_accepted_heads=int(ia),evidence_acceptance_flips=int(flips),
            peak_absdifference_max=max(peakdiff),margin_absdifference_max=max(margindiff),by_head=headstats,
            scale_or_threshold_selected_on_G=False,unit='ROI pixels, not pressure',full_readout_evaluated=False))
    for h in hooks:h.remove()
    for e in errs.values():e['mean_abs']=e['abs_sum']/e['N']
    old.write(args.out/'train_layer_quantization_errors.json',dict(scope='DEF177 original views only, notG',layers=errs))
    old.write(args.out/'export_receipt.json',dict(status='U8_HIDDEN_EXPORTED_NOT_WHOLECHAIN_OR_MCU_ACCEPTANCE',
        elapsed_s=time.monotonic()-start,metadata=meta,outputs_sha256={p.name:old.sha(p)for p in args.out.iterdir()if p.is_file()},
        G_used_only_for_final_forward=True,H_ABC_opened=False,hardware_actions=False))
    print(json.dumps(dict(status='exported_U8',prefix=args.prefix,elapsed_s=time.monotonic()-start,
        weights_exactly_unchanged=True,max_S32_bound=max(b['conservative_S32_abs_bound']for b in bounds))))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['preflight','export']);p.add_argument('--checkpoint',type=Path)
    p.add_argument('--old-npz',type=Path);p.add_argument('--heads',type=int,choices=[2,6],default=6)
    p.add_argument('--prefix',default='landmark');p.add_argument('--out',type=Path);a=p.parse_args()
    preflight()if a.command=='preflight'else main(a)
