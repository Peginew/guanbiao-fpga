"""Synthetic forward accounting only: no training, data/G, compiler or device use."""
from pathlib import Path
import csv,hashlib,importlib.util,json,sys
sys.dont_write_bytecode=True
import cv2
import numpy as np
import torch
from torch import nn

HERE=Path(__file__).resolve().parent;TASK=HERE.parent;ROOT=TASK.parents[1]
FLASH=Path('C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_flash_final_20261031/mcu_boot/flash_tcm20e_candidate_20261101_040529_172170')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def write(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n','utf-8')

def import_path(name,p):
    sp=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(sp);sys.modules[name]=m;sp.loader.exec_module(m);return m

def hooks(model,input_shape):
    layers=[];handles=[]
    def hook(name):
        def record(m,ins,out):
            x=ins[0];n=out.numel();mac=0;valid=0
            if isinstance(m,nn.Conv2d):
                mac=n*(m.in_channels//m.groups)*m.kernel_size[0]*m.kernel_size[1]
                counts=[]
                for size_in,size_out,k,stride,pad,dilation in zip(x.shape[-2:],out.shape[-2:],m.kernel_size,m.stride,m.padding,m.dilation):
                    counts.append(sum(0<=i*stride-pad+j*dilation<size_in for i in range(size_out)for j in range(k)))
                valid=int(x.shape[0]*m.out_channels*(m.in_channels//m.groups)*counts[0]*counts[1])
            elif isinstance(m,nn.Linear):mac=n*m.in_features;valid=mac
            weights=m.weight.numel() if getattr(m,'weight',None)is not None else 0
            bias=m.bias.numel() if getattr(m,'bias',None)is not None else 0
            layers.append(dict(name=name,kind=type(m).__name__,input_shape=list(x.shape),output_shape=list(out.shape),
                parameters=weights+bias,weight_elements=weights,bias_elements=bias,
                nominal_MAC=mac,nonpadding_MAC=valid,output_elements=n,
                output_FP32_bytes=n*4,planned_output_INT8_bytes=n,
                planned_weights_INT8_bias_S32_bytes=weights+bias*4))
        return record
    for name,m in model.named_modules():
        if not list(m.children()):handles.append(m.register_forward_hook(hook(name)))
    model.eval()
    with torch.inference_mode():out=model(torch.zeros(input_shape,dtype=torch.float32))
    for h in handles:h.remove()
    return dict(layers=layers,output_shape=list(out.shape),parameters=sum(p.numel()for p in model.parameters()),
        nominal_MAC=sum(r['nominal_MAC']for r in layers),nonpadding_MAC=sum(r['nonpadding_MAC']for r in layers),
        FP32_weight_and_bias_bytes=sum(p.numel()*p.element_size()for p in model.parameters()),
        planned_weights_INT8_bias_S32_bytes=sum(r['planned_weights_INT8_bias_S32_bytes']for r in layers),
        largest_layer_output_INT8_bytes=max(r['planned_output_INT8_bytes']for r in layers),
        largest_layer_output_FP32_bytes=max(r['output_FP32_bytes']for r in layers),
        MAC_definition='One multiply-accumulate; excludes bias/activation/normalization/pooling/preprocessing/decode; not CPU cycles')

def streaming_mean(gray):
    """Arithmetic/storage prototype of replicate-border 9line U8+U16-column mean."""
    height,width=gray.shape;ring=np.stack([gray[min(height-1,max(0,y))]for y in range(-4,5)])
    vertical=ring.sum(0,dtype=np.uint16);output=np.empty_like(gray,dtype=np.int16);head=0
    for y in range(height):
        total=sum(int(vertical[min(width-1,max(0,x))])for x in range(-4,5))
        for x in range(width):
            output[y,x]=(total+40)//81
            total-=int(vertical[min(width-1,max(0,x-4))]);total+=int(vertical[min(width-1,max(0,x+5))])
        if y+1<height:
            incoming=gray[min(height-1,y+5)]
            for x in range(width):vertical[x]=int(vertical[x])-int(ring[head,x])+int(incoming[x])
            ring[head]=incoming;head=(head+1)%9
    return output

def main():
    torch.set_num_threads(4);cv2.setNumThreads(1);torch.manual_seed(1106)
    source=TASK/'reference_candidate.py';candidate=import_path('cost_static_roll_source',source)
    report=hooks(candidate.StaticRoll(),(1,1,128,128))
    hub_source=ROOT/'algorithm_work/meter_cnn_training_20261102/train_grouped_v2.py'
    polar_source=ROOT/'algorithm_work/meter_pointer_readout_20261102/polar_angle/train_polar.py'
    hub=hooks(import_path('cost_frozen_hub',hub_source).Direct(4),(1,1,128,128))
    polar=hooks(import_path('cost_frozen_polar',polar_source).PolarNeedle(),(1,16,360))
    # The Conv1d polar layers need explicit MAC accounting because Conv2d/Linear
    # hooks above intentionally only handle the new candidate's actual operators.
    assert polar['parameters']==1009
    polar['nominal_MAC']=355680
    polar['planned_weights_INT8_bias_S32_bytes']=1072
    polar['MAC_source']='Frozen previous train_polar.py config cost_estimate, not Conv2d hooks'
    rng=np.random.default_rng(1106)
    synthetic=[np.full((128,128),128,np.uint8),np.tile(np.arange(128,dtype=np.uint8)*2,(128,1)),rng.integers(0,256,(128,128),dtype=np.uint8)]
    for gray in synthetic:
        expected=cv2.boxFilter(gray,cv2.CV_16S,(9,9),normalize=True,borderType=cv2.BORDER_REPLICATE)
        actual=streaming_mean(gray);assert np.array_equal(actual,expected)
    preprocessing=dict(status='SYNTHETIC_INTEGER_MEAN_STORAGE_PROTOTYPE_ONLY_NOT_INTEGRATED',
        input_pixels=16384,local_box=[9,9],border='replicate',
        maximum_vertical_9pixel_sum=9*255,maximum_window_81pixel_sum=81*255,
        mean_rounding='(nonnegative_sum+40)//81 equals CV16S rounding for odd divisor81',
        synthetic_cv2_mean_bitexact_pixels=3*128*128,
        proposed_source_rowring_U8_bytes=9*128,proposed_vertical_columns_U16_bytes=128*2,
        proposed_normalizer_buffers_bytes=9*128+128*2,
        first_5line_INT8_convolution_cache_bytes=5*128,
        source_rows_plus_normalizer_plus_first_conv_cache_bytes=9*128+128*2+5*128,
        proposed_summed_add_sub_ops=9*128+128*9+2*127*128+2*127*128,
        per_image_constant_divisions_by81=16384,
        annulus_and_contrast_pixels=16384,
        full_normalized_U8_buffer_if_not_streamed=16384,
        preprocessing_output_INT8_exact_scale_and_annulus_fixedpoint='PENDING',
        pool2x2=dict(output_elements=128,additions=384,division_by4=128),
        existing_scratch_reuse='Potential sequential lifetime reuse of two16KiB arrays; not newly allocated32KiB pernetwork. Must preserve owned ROI readability and retain model result metadata.',
        preserved_source_dependency='ExistingMCU feeds rows from owned ROI without16KiB raw snapshot; new sequential pose/needle must either reread same owned ROI or explicitly budget snapshot. Lifecycle/C code not changed.')
    actual=load(FLASH/'candidate.json');elf=FLASH/'mroi_flash_tcm20e.elf'
    assert sha(elf)=='fea81904b304dce91ba6b868a86be1d1ad38f1b19cda78edf866ebc29ba52661'
    assert sha(FLASH/'mroi_flash_tcm20e.map')==actual['map']['sha256']
    symbols={}
    for line in (FLASH/'symbols.stdout').read_text('utf-8-sig').splitlines():
        fields=line.split()
        if len(fields)==3:symbols[fields[2]]=int(fields[0],16)
    gap=symbols['__StackLimit']-symbols['_end'];assert gap==actual['static_to_stack_gap']==1404
    baseline=dict(ELF_path=str(elf),ELF_sha256=sha(elf),map_sha256=sha(FLASH/'mroi_flash_tcm20e.map'),
        TCM_bytes=49152,TCM_origin='0x08000000',TCM_end_exclusive='0x0800c000',
        runtime_image_VMA='0x08000040',runtime_code_rodata_bytes=11688,BSS_bytes=33948,
        a_address=hex(symbols['a']),b_address=hex(symbols['b']),scratch_a_bytes=16384,scratch_b_bytes=16384,
        row_cache_address=hex(symbols['rows']),row_cache_bytes=640,
        BSS_end=hex(symbols['_end']),stack_start=hex(symbols['__StackLimit']),stack_top=hex(symbols['_sp']),
        fixed_stack_bytes=2048,static_to_stack_gap_bytes=gap,
        raw_flash_payload_bytes=12264,Flash_LMA_copied_to_TCM=True,
        baseline_network_note='ExistingFEA819 older1202-point/geometry app, not new1009polar orStaticRoll; current rodata is copied toTCM.',
        new_static_weights_only_append_shortfall_bytes=max(report['planned_weights_INT8_bias_S32_bytes']-gap,0),
        new_static_plus_polar_weights_only_append_shortfall_bytes=max(report['planned_weights_INT8_bias_S32_bytes']+1072-gap,0),
        cannot_claim_fit='EvenINT8StaticRollweights alone exceed existingTCM gap; code/quantization tables/polar activations/stack are additional. Savings from replacement, Flash-resident weights or scratch reuse require actualC link and lifecycle proof.')
    toolpaths={
        'RISC_V_GCC':'C:/Anlogic/FD_2026.2/toolchain/gcc/riscv/ph1p35/bin/riscv64-unknown-elf-gcc.exe',
        'RISC_V_NM':'C:/Anlogic/FD_2026.2/toolchain/gcc/riscv/ph1p35/bin/riscv64-unknown-elf-nm.exe',
        'RISC_V_SIZE':'C:/Anlogic/FD_2026.2/toolchain/gcc/riscv/ph1p35/bin/riscv64-unknown-elf-size.exe',
        'HOST_GCC':'C:/Users/Edward/Desktop/mingw64/bin/gcc.exe'}
    old_cost=load(ROOT/'algorithm_work/meter_robust_readout_20261102/pose/cost_and_timing.json')
    result=dict(status='SYNTHETIC_LAYER_ACCOUNTING_COMPLETE_WHOLE_MCU_LINK_FIT_PENDING',
        candidate_code_sha256=sha(source),driver_sha256=sha(__file__),
        synthetic_forward_only=True,training=False,train_G_H_ABC_pixels_opened=False,compile_or_device_actions=False,
        StaticRoll=report,existing_hub=hub,existing_polar=polar,preprocessing=preprocessing,current_actual_TCM_baseline=baseline,
        combined_network_parameters=report['parameters']+hub['parameters']+polar['parameters'],
        combined_nominal_learned_MAC=report['nominal_MAC']+hub['nominal_MAC']+polar['nominal_MAC'],
        combined_planned_INT8_weights_S32bias_bytes=report['planned_weights_INT8_bias_S32_bytes']+hub['planned_weights_INT8_bias_S32_bytes']+1072,
        replaced_multiring_cost=old_cost['B_cost_estimate'],
        replaced_cost_note='Different operation types; no runtime/speedup ratio or MCU cycle claim fromMAC versusabs-difference counts.',
        tools={k:dict(path=v,exists=Path(v).is_file())for k,v in toolpaths.items()},
        pending=['Quantize all new operators and reproduce floating behavior with fixed arithmetic.',
            'Plan owned-ROI rereads and actual sequential buffer lifetime, preserving original capture ownership.',
            'Replace oldC branches or placeweights appropriately, then actuallylink fullhub+polar+pose+preprocessing+PSI app within48KiB.',
            'Measure actual stack watermark, cycles and video concurrency after link; no static fit/latency acceptance here.'])
    write(HERE/'static_roll_cost.json',result)
    with(HERE/'逐层成本.csv').open('w',encoding='utf-8-sig',newline='')as f:
        w=csv.DictWriter(f,fieldnames=list(report['layers'][0]));w.writeheader();w.writerows(report['layers'])
    print(json.dumps(dict(parameters=report['parameters'],nominal_MAC=report['nominal_MAC'],nonpadding_MAC=report['nonpadding_MAC'],
        INT8weights_S32bias=report['planned_weights_INT8_bias_S32_bytes'],combined_parameters=result['combined_network_parameters'],
        actual_TCM_gap=gap,weights_only_append_shortfall=baseline['new_static_weights_only_append_shortfall_bytes']),indent=2))

if __name__=='__main__':main()
