"""Independent needle-convolution integer review; float frontend/hub/decode remain."""
from pathlib import Path
import hashlib,importlib.util,json,re,sys
import numpy as np
import torch
HERE=Path(__file__).resolve().parent;TASK=HERE.parent;POLAR=TASK/'polar_angle';OUT=POLAR/'integer_reference'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def rne_integer(value,shift,relu):
    value=int(value)
    if shift>0:
        sign=-1 if value<0 else 1;a=abs(value);q,rem=divmod(a,1<<shift)
        if rem*2>(1<<shift) or rem*2==(1<<shift) and q%2:q+=1
        value=sign*q
    elif shift<0:value*=1<<-shift
    return min(127,max(0 if relu else -128,value))
def main():
    sys.path.insert(0,str(POLAR));s=importlib.util.spec_from_file_location('integer_review_source',POLAR/'quantize_polar.py');q=importlib.util.module_from_spec(s);s.loader.exec_module(q)
    p=q.p;quant=read(OUT/'quantization.json');arr=dict(np.load(OUT/'integer_weights.npz'));checks=[]
    def check(ok,name):
        checks.append(dict(name=name,passed=bool(ok)))
        if not ok:raise AssertionError(name)
    check(quant['source_checkpoint_sha256']==sha(POLAR/'run_001/best_weights.pt'),'same_selected_B_float_checkpoint')
    check(sum(arr[f'w{i}'].size+4*arr[f'b{i}'].size for i in range(4))==quant['weights_and_S32_bias_bytes']==1072,'1072_int8_weight_int32_bias_bytes')
    header=(OUT/'polar_weights_q8.h').read_text('ascii')
    for i,l in enumerate(quant['layers']):
        check(l['shift']==int(arr['shifts'][i]),l['name']+'_requant_shift_identity')
        check(list(arr[f'w{i}'].shape)==l['weight_shape'],l['name']+'_weight_shape')
        bound=np.abs(arr[f'w{i}'].astype(np.int64)).sum((1,2))*(128 if i==0 else 127)+np.abs(arr[f'b{i}'].astype(np.int64))
        check(int(bound.max())==l['worst_case_accumulator_abs_bound'] and bound.max()<2**31,l['name']+'_S32_worst_case_bound')
        for kind in('w','b'):
            encoded=re.search(r'polar_'+kind+str(i)+r'\[\]=\{([^}]*)\}',header).group(1)
            check(np.array_equal(np.array([int(n)for n in encoded.split(',')]),arr[f'{kind}{i}'].ravel()),l['name']+'_'+kind+'_header_matches_npz')
    ties=0
    for shift in list(range(1,32))+[0,-1,-8]:
        unit=1<<max(0,shift);values=set([-2**31,-1025,-3,-2,-1,0,1,2,3,1025,2**31-1])
        if shift>0:
            for base in(-5,-4,-3,-2,-1,0,1,2,3,4):
                values.update([base*unit+unit//2-1,base*unit+unit//2,base*unit+unit//2+1])
        for value in values:
            for relu in(False,True):
                check(int(q.requant(value,shift,relu))==rne_integer(value,shift,relu),f'RNE_signed_tie_{shift}_{value}_{relu}');ties+=1
    # Reproduce train-only activation scales from the exact Q6-clipped train
    # features. No G activation can alter a scale or weight.
    model=p.PolarNeedle();model.load_state_dict(torch.load(POLAR/'run_001/best_weights.pt',weights_only=True)['state_dict']);model.eval();torch.set_num_threads(2)
    tr=p.dataset('train');va=p.dataset('validation');maxima={n:0. for n in q.NAMES};handles=[]
    for name,layer in model.named_modules():
        if name in maxima:
            def hook(layer,args,out,name=name):maxima[name]=max(maxima[name],float(out.clamp(min=0).max()))
            handles.append(layer.register_forward_hook(hook))
    with torch.inference_mode():
        for start in range(0,len(tr),32):
            x=np.stack([it['feature']for it in tr[start:start+32]]);model(torch.from_numpy(np.clip(np.rint(x*64),-128,127).astype(np.float32)/64))
    for handle in handles:handle.remove()
    for l in quant['layers']:
        expected=1/16 if l['name']=='head' else 2.**np.ceil(np.log2(max(maxima[l['name']]/120,2**-20)))
        check(expected==l['output_scale'],l['name']+'_train_only_output_scale_reproduced')
    oracle_outputs=oracle_MAC=0
    for it in [va[0],va[17],va[49]]:
        x=np.clip(np.rint(it['feature']*64),-128,127).astype(np.int8)
        for i,l in enumerate(quant['layers']):
            w,b=arr[f'w{i}'],arr[f'b{i}'];got,_=q.conv(x,w,b,l);want=np.empty_like(got);k=w.shape[-1]
            # Plain Python signed integer summation and divmod rounding, no
            # einsum/sliding-window/quantizer rounding implementation reused.
            for oc in range(w.shape[0]):
                for pos in range(360):
                    acc=int(b[oc])
                    if l['depthwise']:
                        for j in range(k):acc+=int(x[oc,(pos+j-k//2)%360])*int(w[oc,0,j]);oracle_MAC+=1
                    else:
                        for ic in range(x.shape[0]):
                            for j in range(k):acc+=int(x[ic,(pos+j-k//2)%360])*int(w[oc,ic,j]);oracle_MAC+=1
                    want[oc,pos]=rne_integer(acc,l['shift'],l['relu'])
            check(np.array_equal(got,want),it['id']+'_'+l['name']+'_independent_scalar_integer_oracle');oracle_outputs+=want.size;x=want
    stored=read(OUT/'validation_evaluation.json');byid={r['id']:r for r in stored['rows']};angles=[];accepted=[];false_negativeaccept=0;clip=[0,0];total=0
    for it in va:
        feature=it['feature'];clip[0]+=int((feature*64<-128).sum());clip[1]+=int((feature*64>127).sum());total+=feature.size
        logits,_=q.forward(feature,quant['layers'],arr);theta,score,margin=p.decode(logits.astype(np.float32)/16);h=it['frozen_hub']
        permitted=score>=.3 and margin>=.02 and h['peaks'][0]>=.3 and h['margins'][0]>=.02 and np.linalg.norm(np.array(it['center'])-63.5)<=20 and it['outside']<=.05
        check(p.delta(theta,byid[it['id']]['angle_deg_image'])<1e-10 and permitted==byid[it['id']]['valid'],it['id']+'_G_integer_prediction_and_fixed_permission')
        if it['reference']is not None:
            error=p.delta(theta,it['reference']);angles.append(error)
            if permitted:accepted.append(error)
        if not it['record']['target_present']and permitted:false_negativeaccept+=1
    summary=stored['summary']
    check(len(angles)==summary['full']==50 and abs(np.mean(angles)-summary['angle_error_deg']['mean'])<1e-10,'G50_integer_angle_statistics')
    check(sum(e<=10 for e in angles)==summary['within10'] and len(accepted)==summary['accepted'] and sum(e>10 for e in accepted)==summary['accepted_over10'],'G_integer_coverage_wrong_accept_counts')
    check(clip==quant['Q6_input_clip_low_high'] and total==quant['Q6_input_elements'],'actual_Q6_input_clipping_count')
    report=dict(status='PASS_POLAR_CONVOLUTION_INTEGER_REFERENCE_ONLY',checks=len(checks),failures=[],
        artifacts_sha256={str(path.relative_to(TASK)):sha(path)for path in[POLAR/'quantize_polar.py',OUT/'integer_weights.npz',OUT/'quantization.json',OUT/'polar_weights_q8.h',OUT/'validation_evaluation.json',OUT/'validation_predictions.jsonl']},
        independent_scalar_convolution_outputs=oracle_outputs,independent_scalar_MAC=oracle_MAC,signed_RNE_edge_tie_cases=ties,
        train_only_scale_calibration_images=len(tr),G_summary=summary,Q6_input_clip_counts=clip,Q6_input_elements=total,weights_bias_bytes=1072,
        scope='Only selected needle convolution is integer. Frozen run002 hub, native-HDMI ROI/polar bilinear frontend, sigmoid/centroid decoding and native256SIFT readout pose remain floating PC.',
        missing_before_MCU=['Joint integer hub and needle with actual ROI','Fixed-point polar sampling/contrast and U8 sigmoid/centroid equivalence','128ROI-compatible static reference orientation, no native720p256SIFT assumption','Actual firmware link memory, execution timing and resource effects'],
        test_H_or_ABC_opened=False,optimizer_steps=0,hardware_actions=False)
    (HERE/'polar_integer_reference_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps({k:report[k]for k in('status','checks','independent_scalar_convolution_outputs','independent_scalar_MAC','signed_RNE_edge_tie_cases','G_summary')},ensure_ascii=False))
if __name__=='__main__':main()
