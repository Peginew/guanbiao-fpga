"""Synthetic C matcher/NumPy partition and fixed-template decision tests only."""
from pathlib import Path
from fractions import Fraction
import ctypes as C
import hashlib,json,math,subprocess
import numpy as np

HERE=Path(__file__).resolve().parent
class Template(C.Structure):
    _fields_=[('indices',C.POINTER(C.c_uint16)),('values',C.POINTER(C.c_int8)),
              ('local_shift',C.POINTER(C.c_int16)),('count',C.c_uint16)]
class Match(C.Structure):
    _fields_=[('sum',C.c_uint32),('keep',C.c_uint16),('profile_id',C.c_uint8),
              ('template_id',C.c_uint8),('present',C.c_uint8)]
class Result(C.Structure):
    _fields_=[('best_sum',C.c_uint32),('far_sum',C.c_uint32),
        ('margin_cross_numerator',C.c_uint32),('margin_cross_denominator',C.c_uint32),
        ('best_keep',C.c_uint16),('far_keep',C.c_uint16),('delta_deg',C.c_int16),('far_delta_deg',C.c_int16),
        ('profile_id',C.c_uint8),('template_id',C.c_uint8),('accepted',C.c_uint8),
        ('score_pass',C.c_uint8),('margin_pass',C.c_uint8),('search_interior_pass',C.c_uint8),('reason',C.c_uint8)]

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(dll):
    lib=C.CDLL(str(dll))
    for n in ['mp_context_size','mp_template_size','mp_result_size']:getattr(lib,n).restype=C.c_size_t
    lib.mp_template_init.argtypes=[C.POINTER(Template),C.POINTER(C.c_uint16),C.POINTER(C.c_int8),C.c_uint16,C.POINTER(C.c_int16)]
    lib.mp_prepare.argtypes=[C.c_void_p,C.c_uint8]
    lib.mp_push.argtypes=[C.c_void_p,C.POINTER(C.c_int8),C.c_uint16,C.c_uint8,C.POINTER(Template),C.c_uint8]
    lib.mp_finish.argtypes=[C.c_void_p,C.POINTER(Result)]
    lib.mp_get_shift.argtypes=[C.c_void_p,C.c_uint8,C.POINTER(Match)]
    lib.mp_score_ge_064.argtypes=[C.c_uint32,C.c_uint16]
    lib.mp_margin_ge_0018.argtypes=[C.c_uint32,C.c_uint16,C.c_uint32,C.c_uint16]
    assert lib.mp_template_size()==C.sizeof(Template) and lib.mp_result_size()==C.sizeof(Result)
    return lib

def prepare_templates(lib,definitions):
    ts=(Template*len(definitions))();arrays=[]
    for i,(indices,values,shifts)in enumerate(definitions):
        ind=np.ascontiguousarray(indices,dtype=np.uint16);v=np.ascontiguousarray(values,dtype=np.int8);s=np.ascontiguousarray(shifts,dtype=np.int16)
        assert lib.mp_template_init(C.byref(ts[i]),ind.ctypes.data_as(C.POINTER(C.c_uint16)),
            v.ctypes.data_as(C.POINTER(C.c_int8)),len(ind),s.ctypes.data_as(C.POINTER(C.c_int16)))==0
        arrays.append((ind,v,s))
    return ts,arrays

def reference(profiles,definitions,center=True):
    best=[None]*49
    if not center:return best,None
    for profile_id,q,outside in profiles:
        if outside>216:continue
        q=np.asarray(q).reshape(12,360)
        for ti,(indices,values,shifts)in enumerate(definitions):
            indices=np.asarray(indices,dtype=np.int64);keep=max(1,int(len(indices)*.8))
            for si in range(49):
                vals=np.roll(q,-int(shifts[si]),axis=1).ravel()[indices].astype(np.int32)
                diff=abs(vals-np.asarray(values,dtype=np.int32));total=int(np.partition(diff,keep-1)[:keep].sum())
                new=(total,keep,profile_id,ti)
                if best[si]is None or total*best[si][1]<best[si][0]*keep:best[si]=new
    if best[0]is None:return best,None
    # Scores have the original float64 mean/divide/subtract order.
    scores=np.array([1-float(v[0]/v[1])/128 for v in best]);bi=int(scores.argmax())
    far_idx=np.flatnonzero(abs(np.arange(49)-bi)>5);fi=int(far_idx[np.argmax(scores[far_idx])])
    return best,dict(best=bi,far=fi,score=float(scores[bi]),margin=float(scores[bi]-scores[fi]),
        accepted=bool(scores[bi]>=.64 and scores[bi]-scores[fi]>=.018 and abs(bi-24)<24))

def compare_case(lib,name,profiles,definitions,center=True):
    templates,keepalive=prepare_templates(lib,definitions);context=C.create_string_buffer(lib.mp_context_size())
    lib.mp_prepare(context,center)
    for profile_id,q,outside in profiles:
        q=np.ascontiguousarray(q,dtype=np.int8)
        ret=lib.mp_push(context,q.ctypes.data_as(C.POINTER(C.c_int8)),outside,profile_id,templates,len(definitions))
        assert ret==(2 if not center else 1 if outside>216 else 0),(name,ret)
    best,expected=reference(profiles,definitions,center)
    for si,ref in enumerate(best):
        actual=Match();assert lib.mp_get_shift(context,si,C.byref(actual))==0
        assert bool(actual.present)==(ref is not None),(name,si)
        if ref is not None:assert(actual.sum,actual.keep,actual.profile_id,actual.template_id)==ref,(name,si,ref)
    result=Result();assert lib.mp_finish(context,C.byref(result))==0
    if not center:assert result.accepted==0 and result.reason==1
    elif expected is None:assert result.accepted==0 and result.reason==2
    else:
        assert result.delta_deg==expected['best']-24 and result.far_delta_deg==expected['far']-24,name
        assert bool(result.accepted)==expected['accepted'],(name,result.accepted,expected)
        assert bool(result.score_pass)==(expected['score']>=.64)
        assert bool(result.margin_pass)==(expected['margin']>=.018)
    return dict(name=name,candidate_checks=49,accepted=bool(result.accepted),delta=int(result.delta_deg),
        profile=int(result.profile_id),template=int(result.template_id))

def main():
    gcc=Path('C:/Users/Edward/Desktop/mingw64/bin/gcc.exe');dll=HERE/'meter_pose_matcher.dll'
    command=[str(gcc),'-std=c99','-O2','-Wall','-Wextra','-Werror','-shared','-static-libgcc',str(HERE/'meter_pose_matcher.c'),'-o',str(dll)]
    # Build only this new host candidate, never a board firmware/project.
    cp=subprocess.run(command,capture_output=True,text=True,creationflags=0x08000000)
    (HERE/'host_compile.stdout.log').write_text(cp.stdout,'utf-8');(HERE/'host_compile.stderr.log').write_text(cp.stderr,'utf-8')
    if cp.returncode:raise RuntimeError(cp.stderr)
    lib=bind(dll);rng=np.random.default_rng(1107);cases=[];shifts=np.arange(-24,25,dtype=np.int16)
    for n in [1,2,3,5,17,63,121,1600,1634,4320]:
        counts=[n] if n<100 else [n,max(1,n-1)]
        definitions=[]
        for j,k in enumerate(counts):
            idx=rng.choice(4320,k,replace=False).astype(np.uint16)
            definitions.append((idx,rng.integers(-127,128,k,dtype=np.int8),shifts+j*2))
        profiles=[(i,rng.integers(-127,128,(12,360),dtype=np.int8),0)for i in range(3)]
        cases.append(compare_case(lib,f'random_counts_{counts}',profiles,definitions))
    original=rng.integers(-127,128,(12,360),dtype=np.int8)
    definitions=[(np.arange(n,dtype=np.uint16),original.ravel()[:n],shifts)for n in [1634,1600]]
    planted=np.roll(original,7,axis=1)
    cases.append(compare_case(lib,'planted_plus7_two_count_tie_first_profile_template',[(2,planted,0),(9,planted,0)],definitions))
    assert cases[-1]['accepted'] and cases[-1]['delta']==7 and cases[-1]['profile']==2 and cases[-1]['template']==0
    cases.append(compare_case(lib,'center14_rejected',[(0,planted,0)],definitions,False))
    cases.append(compare_case(lib,'outside217_rejected',[(0,planted,217)],definitions))
    cases.append(compare_case(lib,'outside216_accepted',[(0,planted,216)],definitions))
    assert cases[-1]['accepted']
    cases.append(compare_case(lib,'search_endpoint_plus24_rejected',[(0,np.roll(original,24,axis=1),0)],definitions))
    assert not cases[-1]['accepted']and cases[-1]['delta']==24
    zeros=np.zeros((12,360),np.int8)
    cases.append(compare_case(lib,'equal_all_shifts_pick_minus24_far_minus18',[(0,zeros,0)],[(np.arange(4320,dtype=np.uint16),zeros.ravel(),shifts)]))
    cases.append(compare_case(lib,'maximum_difference255_trim_keep3456',[(0,np.full((12,360),-128,np.int8),0)],[(np.arange(4320,dtype=np.uint16),np.full(4320,127,np.int8),shifts)]))
    score_tests=0
    for keep in [1280,1307]:
        around=math.floor(1152*keep/25)
        for total in range(around-3,around+4):
            got=bool(lib.mp_score_ge_064(total,keep));exact=25*total<=1152*keep
            original_float=1-float(total/keep)/128>=.64
            assert got==exact==original_float;score_tests+=1
    margin_tests=0
    for kb in [1280,1307]:
        for kf in [1280,1307]:
            for sb in np.linspace(0,46*kb,129,dtype=np.int64):
                center=math.floor((Fraction(288*kb*kf,125)+int(sb)*kf)/kb)
                for sf in range(max(0,center-2),center+4):
                    exact=125*(sf*kb-int(sb)*kf)>=288*kb*kf
                    original_float=(1-float(int(sb)/kb)/128)-(1-float(sf/kf)/128)>=.018
                    got=bool(lib.mp_margin_ge_0018(int(sb),kb,sf,kf))
                    assert got==exact==original_float,(sb,kb,sf,kf,got,exact,original_float)
                    margin_tests+=1
    # Generic template counts can put a rational threshold exactly on an IEEE
    # cancellation edge. Record this narrow non-frozen-template limitation.
    generic_edges=[]
    for sb in range(0,1000):
        kb=kf=125;sf=sb+288
        exact=bool(lib.mp_margin_ge_0018(sb,kb,sf,kf));fp=(1-sb/kb/128)-(1-sf/kf/128)>=.018
        if exact!=fp:generic_edges.append(dict(best_sum=sb,far_sum=sf,keep=125,exact_rational=exact,original_float64=fp))
        if len(generic_edges)==3:break
    result=dict(status='PASS_SYNTHETIC_NUMPY_TRIM_AND_FROZEN_TEMPLATE_FLOAT_THRESHOLDS',
        cases=cases,candidate_partition_winner_checks=len(cases)*49,
        frozen_template_score_boundary_checks=score_tests,frozen_template_margin_boundary_checks=margin_tests,
        context_bytes=int(lib.mp_context_size()),template_struct_host_bytes=int(lib.mp_template_size()),result_bytes=int(lib.mp_result_size()),
        compile_command=command,compile_exit=cp.returncode,compile_stderr=cp.stderr,
        generic_exact_rational_versus_float64_edge_examples=generic_edges,
        generic_edge_limit='Current frozen keep counts1280/1307 pass both exact-rational and float64 threshold tests. Arbitrary new template counts are not certified IEEE cancellation equivalent; do not replace frozen templates silently.',
        source_sha256={p.name:sha(p)for p in[HERE/'meter_pose_matcher.c',HERE/'meter_pose_matcher.h',dll,Path(__file__)]},
        original_project_compiled=False,model_training=False,real_dataset_inputs_read=False,hardware_actions=False)
    (HERE/'host_test_receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({k:result[k]for k in ['status','candidate_partition_winner_checks','frozen_template_margin_boundary_checks','context_bytes','generic_exact_rational_versus_float64_edge_examples']},indent=2))

if __name__=='__main__':main()
