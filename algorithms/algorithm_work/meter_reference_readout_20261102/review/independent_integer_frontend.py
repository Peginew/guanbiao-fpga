"""Bounded independent C frontend replay. No training, geometry port or board."""
from pathlib import Path
from fractions import Fraction
import ctypes as C, hashlib, importlib.util, json, struct, subprocess, sys
import numpy as np
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;TASK=HERE.parent;CORE=TASK/'integer_pose';ROOT=TASK.parents[1]
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
checks=[]
def need(ok,name):
    checks.append(name)
    if not ok:raise AssertionError(name)
def ptr(a,ctype):return a.ctypes.data_as(C.POINTER(ctype))
def normalized_oracle(image):
    windows=np.lib.stride_tricks.sliding_window_view(np.pad(image,4,mode='edge'),(9,9))
    mean=(windows.sum(axis=(-1,-2),dtype=np.uint32)+40)//81
    return np.clip(3*(image.astype(np.int32)-mean.astype(np.int32))+128,0,255).astype(np.uint8)
def sample_oracle(image,xq,yq):
    result=[]
    for xx,yy in zip(xq.ravel(),yq.ravel()):
        x,fx=divmod(int(xx),32);y,fy=divmod(int(yy),32)
        fetch=lambda a,b:int(image[b,a])if 0<=a<128 and 0<=b<128 else 128
        total=fetch(x,y)*(32-fx)*(32-fy)+fetch(x+1,y)*fx*(32-fy)+fetch(x,y+1)*(32-fx)*fy+fetch(x+1,y+1)*fx*fy
        result.append((total+512)//1024)
    return np.asarray(result,np.uint8).reshape(xq.shape)
def profile_oracle(sampled):
    result=np.empty_like(sampled,np.int8)
    for band,row in enumerate(sampled):
        sm=sum(int(v)for v in row);diff=[360*int(v)-sm for v in row];den=max(sum(abs(v)for v in diff),777600)
        result[band]=[min(127,max(-127,round(Fraction(d*11520,den))))for d in diff]
    return result

def main():
    completion=load(CORE/'frontend_core_completion.json')
    bound=completion['source_sha256']
    need(bool(bound),'frontend_completion_has_bound_artifacts')
    for name,h in bound.items():need(sha(CORE/name)==h,'frontend_bound_'+name)
    dll=HERE/'frontend_independent_rebuild.dll'
    command=['C:/Users/Edward/Desktop/mingw64/bin/gcc.exe','-std=c99','-O2','-Wall','-Wextra','-Werror','-shared','-static-libgcc',str(CORE/'meter_pose_frontend.c'),'-o',str(dll)]
    cp=subprocess.run(command,capture_output=True,text=True,creationflags=0x08000000)
    need(cp.returncode==0 and not cp.stderr,'independent_frontend_compile_clean')
    lib=C.CDLL(str(dll));lib.mpf_normalize_workspace_size.restype=C.c_size_t;lib.mpf_profile_workspace_size.restype=C.c_size_t
    need(lib.mpf_normalize_workspace_size()==1408 and lib.mpf_profile_workspace_size()==360,'caller_workspace_sizes')
    lib.mpf_normalize9x9_u8.argtypes=[C.POINTER(C.c_uint8),C.POINTER(C.c_uint8),C.c_void_p]
    lib.mpf_bilinear_q5_u8.argtypes=[C.POINTER(C.c_uint8),C.POINTER(C.c_int16),C.POINTER(C.c_int16),C.c_uint16,C.POINTER(C.c_uint8)]
    lib.mpf_normalize_profile_s8.argtypes=[C.POINTER(C.c_uint8),C.POINTER(C.c_int8)]
    lib.mpf_profile_q5_s8.argtypes=[C.POINTER(C.c_uint8),C.POINTER(C.c_int16),C.POINTER(C.c_int16),C.POINTER(C.c_int8),C.c_void_p]
    nw=C.create_string_buffer(1408);pw=C.create_string_buffer(360)
    rng=np.random.default_rng(1109);pixel_counts=dict(normalize=0,bilinear=0,profile=0)
    synthetic=[np.zeros((128,128),np.uint8),np.full((128,128),255,np.uint8),rng.integers(0,256,(128,128),dtype=np.uint8)]
    for i,g in enumerate(synthetic):
        expect=normalized_oracle(g);actual=np.empty_like(g)
        need(lib.mpf_normalize9x9_u8(ptr(g,C.c_uint8),ptr(actual,C.c_uint8),nw)==0 and np.array_equal(actual,expect),'synthetic_normalization_'+str(i));pixel_counts['normalize']+=g.size
        inplace=g.copy();need(lib.mpf_normalize9x9_u8(ptr(inplace,C.c_uint8),ptr(inplace,C.c_uint8),nw)==0 and np.array_equal(inplace,expect),'synthetic_inplace_'+str(i));pixel_counts['normalize']+=g.size
    spec=importlib.util.spec_from_file_location('review_fixed_geometry',CORE/'pose_frontend.py');front=importlib.util.module_from_spec(spec);spec.loader.exec_module(front)
    fixture_reports=[]
    for ident,phase in [('D_013',0),('E_002',10),('G_018',13),('G_052',26),('G_056',8)]:
        z=np.load(CORE/'frontend_fixtures'/f'{ident}.npz');g=np.ascontiguousarray(z['image'],np.uint8);norm=np.empty_like(g)
        need(lib.mpf_normalize9x9_u8(ptr(g,C.c_uint8),ptr(norm,C.c_uint8),nw)==0 and np.array_equal(norm,normalized_oracle(g)),ident+'_actual_normalize');pixel_counts['normalize']+=g.size
        dx,dy,scale=front.HYPOTHESES[phase]
        xq,yq,outside,_,_=front.geometry_q5_from_float(z['hub']+[dx,dy],float(z['radius'])*scale)
        xq=np.ascontiguousarray(xq,np.int16);yq=np.ascontiguousarray(yq,np.int16);actual=np.empty((12,360),np.uint8)
        need(lib.mpf_bilinear_q5_u8(ptr(norm,C.c_uint8),ptr(xq,C.c_int16),ptr(yq,C.c_int16),4320,ptr(actual,C.c_uint8))==0,ident+'_sampler_call')
        expected=sample_oracle(norm,xq,yq);need(np.array_equal(actual,expected),ident+'_bilinear_plain_integer_oracle');pixel_counts['bilinear']+=4320
        profile=np.empty((12,360),np.int8);exact=profile_oracle(expected)
        need(lib.mpf_normalize_profile_s8(ptr(actual,C.c_uint8),ptr(profile,C.c_int8))==0 and np.array_equal(profile,exact),ident+'_Fraction_RNE_profile');pixel_counts['profile']+=4320
        need(np.array_equal(profile,z['profiles'][phase]),ident+'_frozen_integer_fixture')
        inprof=actual.copy();need(lib.mpf_normalize_profile_s8(ptr(inprof,C.c_uint8),ptr(inprof,C.c_int8))==0 and np.array_equal(inprof.view(np.int8),exact),ident+'_profile_inplace')
        fused=np.empty((12,360),np.int8);need(lib.mpf_profile_q5_s8(ptr(norm,C.c_uint8),ptr(xq,C.c_int16),ptr(yq,C.c_int16),ptr(fused,C.c_int8),pw)==0 and np.array_equal(fused,exact),ident+'_fused_profile')
        fixture_reports.append(dict(id=ident,phase=phase,outside_count_from_float_geometry=outside))
    edgeq=np.array([-32768,-64,-33,-32,-31,-16,-1,0,1,15,16,31,32,4063,4064,4065,4095,4096,32767],np.int16)
    xx=np.ascontiguousarray(np.tile(edgeq,len(edgeq)));yy=np.ascontiguousarray(np.repeat(edgeq,len(edgeq)));g=synthetic[-1];got=np.empty(xx.size,np.uint8)
    need(lib.mpf_bilinear_q5_u8(ptr(g,C.c_uint8),ptr(xx,C.c_int16),ptr(yy,C.c_int16),len(xx),ptr(got,C.c_uint8))==0 and np.array_equal(got,sample_oracle(g,xx,yy)),'negative_border_Q5_extremes');pixel_counts['bilinear']+=len(xx)
    sampled=np.zeros((12,360),np.uint8);sampled[1]=255;sampled[2,0]=255;sampled[3]=255;sampled[3,0]=0;sampled[4,::2]=255;sampled[5:]=rng.integers(0,256,(7,360),dtype=np.uint8)
    got=np.empty((12,360),np.int8);need(lib.mpf_normalize_profile_s8(ptr(sampled,C.c_uint8),ptr(got,C.c_int8))==0 and np.array_equal(got,profile_oracle(sampled)),'constant_saturation_signed_RNE_rows');pixel_counts['profile']+=4320
    need(91800*11520<2**31 and 360*255*360<2**32,'S32_numerator_and_U32_abs_sum_bounds')
    report=load(CORE/'c_pixel_chain_verification.json')
    need(report['counts']['ROIs']==223 and report['counts']['normalize_mismatches']==0 and report['counts']['profile_mismatches']==0 and not report['pressure_output_changes'],'reported223_pixel_chain_scope')
    current=load(CORE/'c_pixel_chain_readout_psi.json');baseline=load(ROOT/'algorithm_work/meter_robust_readout_20261102/pose/candidate_B_with_old_B_readout_psi.json');old={r['id']:r for r in baseline['rows']}
    for r in current['rows']:need((r['valid'],r['psi_estimate'],r['reason'])==(old[r['id']]['valid'],old[r['id']]['psi_estimate'],old[r['id']]['reason']),r['id']+'_same_PSI')
    p=load(CORE/'frontend_verification.json');need(p['counts']['rational_vs_float32_profile_mismatches']==173 and p['counts']['rational_vs_float32_profile_max_abs_error']==1,'float32_tie_differences_preserved_not_hidden')
    obj=(CORE/'rv32_build/meter_pose_frontend.o').read_bytes();eh=struct.unpack_from('<16sHHIIIIIHHHHHH',obj)
    need(eh[0][:6]==b'\x7fELF\x01\x01' and eh[1]==1 and eh[2]==243,'frontend_actual_RISC_V32_object')
    sections=[struct.unpack_from('<IIIIIIIIII',obj,eh[6]+i*eh[11])for i in range(eh[12])]
    text=sum(s[5]for s in sections if s[2]&2 and s[2]&4);otheralloc=sum(s[5]for s in sections if s[2]&2 and not(s[2]&4))
    need(text==1320 and otheralloc==0,'frontend_actual_text1320_otheralloc0')
    result=dict(status='PASS_C_INTEGER_PIXEL_PROFILE_OPERATORS_FLOAT_GEOMETRY_PENDING',checks=len(checks),independently_compared_pixels=pixel_counts,fixtures=fixture_reports,
        source_sha256={p.name:sha(p)for p in[CORE/'meter_pose_frontend.c',CORE/'meter_pose_frontend.h',CORE/'pose_frontend.py',CORE/'frontend_core_completion.json',CORE/'c_pixel_chain_verification.json',CORE/'c_pixel_chain_readout_psi.json']},
        independent_rebuild_command=command,independent_DLL_sha256=sha(dll),same_PSI_readings=21,same_MAE_psi=current['summary']['reading_mae_psi'],
        workspaces=dict(normalize_bytes=1408,profile_temporary_bytes=360),reference_profile_tie_mismatches=dict(changed=173,total=27527040,max_abs_error=1,templates_selected_values_unchanged=True),
        actual_object_text_bytes=1320,geometry='Q5tables still generated by floating sin/cos/scale/predictedhub; originalFLOAT64 outside and hubdistance predicates retained',
        caller_memory='Normalized image16384B, optional full x/yQ5 tables17280B, profile4320B, matcher1104B, templates9898B and workspaces/code/oldCNN are not zero or proven jointly fit. Inplace C arithmetic support does not prove ownedAHB ROI writes/lifetimes are legal.',
        remaining=['Whole geometry/hub/polar/PSI C or integer port','Actual application link, scratch lifetimes, call-stack/cycles','Actual same-source ROI gray-domain evidence'],
        hardware_actions=False,training=False,H_or_ABC_opened=False)
    (HERE/'integer_frontend_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
