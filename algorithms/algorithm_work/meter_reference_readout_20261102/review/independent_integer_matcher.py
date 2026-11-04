"""Independent host rebuild and bounded exact-rational matcher replay."""
from pathlib import Path
from fractions import Fraction
import ctypes as C, hashlib, importlib.util, json, struct, subprocess, sys
import numpy as np
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;TASK=HERE.parent;CORE=TASK/'integer_pose';ROOT=TASK.parents[1]
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def rows(p):return[json.loads(x)for x in Path(p).read_text('utf-8-sig').splitlines()if x.strip()]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
checks=[]
def need(ok,name):
    checks.append(name)
    if not ok:raise AssertionError(name)
class Template(C.Structure):
    _fields_=[('indices',C.POINTER(C.c_uint16)),('values',C.POINTER(C.c_int8)),('local_shift',C.POINTER(C.c_int16)),('count',C.c_uint16)]
class Match(C.Structure):
    _fields_=[('sum',C.c_uint32),('keep',C.c_uint16),('profile_id',C.c_uint8),('template_id',C.c_uint8),('present',C.c_uint8)]
class Context(C.Structure):
    _fields_=[('best',Match*49),('histogram',C.c_uint16*256),('accepted_profiles',C.c_uint16),('center_allowed',C.c_uint8)]
class Result(C.Structure):
    _fields_=[('best_sum',C.c_uint32),('far_sum',C.c_uint32),('margin_cross_numerator',C.c_uint32),('margin_cross_denominator',C.c_uint32),('best_keep',C.c_uint16),('far_keep',C.c_uint16),('delta_deg',C.c_int16),('far_delta_deg',C.c_int16),('profile_id',C.c_uint8),('template_id',C.c_uint8),('accepted',C.c_uint8),('score_pass',C.c_uint8),('margin_pass',C.c_uint8),('search_interior_pass',C.c_uint8),('reason',C.c_uint8)]

def main():
    completion=load(CORE/'core_completion.json')
    for p,h in completion['artifacts_sha256'].items():need(sha(CORE/p)==h,'core_bound_'+p)
    dll=HERE/'matcher_independent_rebuild.dll'
    command=['C:/Users/Edward/Desktop/mingw64/bin/gcc.exe','-std=c99','-O2','-Wall','-Wextra','-Werror','-shared','-static-libgcc',str(CORE/'meter_pose_matcher.c'),'-o',str(dll)]
    cp=subprocess.run(command,capture_output=True,text=True,creationflags=0x08000000)
    need(cp.returncode==0 and not cp.stderr,'independent_host_compile_clean')
    lib=C.CDLL(str(dll))
    for name,ty in [('mp_context_size',Context),('mp_template_size',Template),('mp_result_size',Result)]:
        getattr(lib,name).restype=C.c_size_t;need(getattr(lib,name)()==C.sizeof(ty),'ABI_'+name)
    lib.mp_template_init.argtypes=[C.POINTER(Template),C.POINTER(C.c_uint16),C.POINTER(C.c_int8),C.c_uint16,C.POINTER(C.c_int16)]
    lib.mp_prepare.argtypes=[C.POINTER(Context),C.c_uint8]
    lib.mp_push.argtypes=[C.POINTER(Context),C.POINTER(C.c_int8),C.c_uint16,C.c_uint8,C.POINTER(Template),C.c_uint8]
    lib.mp_finish.argtypes=[C.POINTER(Context),C.POINTER(Result)]
    lib.mp_score_ge_064.argtypes=[C.c_uint32,C.c_uint16]
    lib.mp_margin_ge_0018.argtypes=[C.c_uint32,C.c_uint16,C.c_uint32,C.c_uint16]
    z=np.load(CORE/'fixtures/templates.npz');templates=(Template*2)();arrays=[]
    definitions=[]
    for j in range(2):
        idx=np.ascontiguousarray(z[f'indices_{j}'],dtype=np.uint16);v=np.ascontiguousarray(z[f'values_{j}'],dtype=np.int8);s=np.ascontiguousarray(z[f'shifts_{j}'],dtype=np.int16)
        arrays.extend([idx,v,s]);definitions.append((idx,v,s))
        need(lib.mp_template_init(C.byref(templates[j]),idx.ctypes.data_as(C.POINTER(C.c_uint16)),v.ctypes.data_as(C.POINTER(C.c_int8)),len(idx),s.ctypes.data_as(C.POINTER(C.c_int16)))==0,'template_init_'+str(j))
    need([max(1,len(d[0])*4//5)for d in definitions]==[1307,1280],'frozen_keeps')
    manifest=load(CORE/'fixtures/manifest.json');byid={r['id']:r for r in manifest['records']}
    fixture_reports=[]
    for ident in ['D_002','E_002','F_003','G_004','G_018','G_024','G_040','G_052']:
        r=byid[ident];q=np.load(CORE/'fixtures'/f'{ident}.npz');context=Context();lib.mp_prepare(C.byref(context),r['center_allowed']);oracle=[None]*49
        for pi,(p,oc)in enumerate(zip(q['profiles'],q['outside_counts'])):
            p=np.ascontiguousarray(p,np.int8)
            ret=lib.mp_push(C.byref(context),p.ctypes.data_as(C.POINTER(C.c_int8)),int(oc),pi,templates,2)
            need(ret==(2 if not r['center_allowed']else 1 if oc>216 else 0),ident+'_push_'+str(pi))
            if not r['center_allowed']or oc>216:continue
            for ti,(idx,val,shift)in enumerate(definitions):
                keep=max(1,len(idx)*4//5)
                for si in range(49):
                    # Full sort is intentionally independent of the C histogram.
                    ii=idx.astype(np.int64)
                    pred=p[ii//360,(ii%360+int(shift[si]))%360].astype(np.int16)
                    sm=int(np.sort(abs(pred-val.astype(np.int16)))[:keep].sum())
                    choice=(Fraction(sm,keep),pi,ti,sm,keep)
                    if oracle[si]is None or choice[0]<oracle[si][0]:oracle[si]=choice
        for i,ref in enumerate(oracle):
            actual=context.best[i]
            need(bool(actual.present)==(ref is not None),ident+'_presence_'+str(i))
            if ref is not None:need((actual.sum,actual.keep,actual.profile_id,actual.template_id)==(ref[3],ref[4],ref[1],ref[2]),ident+'_trim_winner_'+str(i))
        result=Result();need(lib.mp_finish(C.byref(context),C.byref(result))==0,ident+'_finish')
        if not r['center_allowed']:need(result.reason==1 and not result.accepted,ident+'_center_rejection')
        elif not any(x is not None for x in oracle):need(result.reason==2 and not result.accepted,ident+'_outside_rejection')
        else:
            bi=min(range(49),key=lambda i:oracle[i][0]);far=min((i for i in range(49)if abs(i-bi)>5),key=lambda i:oracle[i][0])
            b,f=oracle[bi],oracle[far];score=1-b[0]/128;margin=(f[0]-b[0])/128
            accepted=score>=Fraction(16,25) and margin>=Fraction(9,500) and abs(bi-24)<24
            need((result.delta_deg,result.far_delta_deg,result.profile_id,result.template_id,result.accepted)==(bi-24,far-24,b[1],b[2],accepted),ident+'_exact_result')
            need((bool(result.score_pass),bool(result.margin_pass))==(score>=Fraction(16,25),margin>=Fraction(9,500)),ident+'_exact_gates')
        need(bool(result.accepted)==r['baseline']['accepted'],ident+'_frozen_float_same_permission')
        fixture_reports.append(dict(id=ident,accepted=bool(result.accepted),roll=int(result.delta_deg),reason=int(result.reason)))
    rng=np.random.default_rng(1108)
    for kb in [1280,1307]:
        for kf in [1280,1307]:
            for sb in rng.integers(0,46*kb,32):
                border=(Fraction(288*kb*kf,125)+int(sb)*kf)/kb
                for sf in range(int(border)-1,int(border)+3):
                    exact=125*(sf*kb-int(sb)*kf)>=288*kb*kf
                    fp=(1-int(sb)/kb/128)-(1-sf/kf/128)>=.018
                    need(bool(lib.mp_margin_ge_0018(int(sb),kb,sf,kf))==exact==fp,'frozen_margin_boundary')
    generic=next(e for e in load(CORE/'host_test_receipt.json')['generic_exact_rational_versus_float64_edge_examples'])
    need(bool(lib.mp_margin_ge_0018(generic['best_sum'],125,generic['far_sum'],125))==generic['exact_rational']!=generic['original_float64'],'generic125_non_equivalence_preserved')
    need(255*3456**2<2**32,'cross_product_bound_uint32')
    report=load(CORE/'c_matcher_verification.json')
    need(not report['gate_or_winner_mismatches'] and report['records']==223,'reported_all223_match')
    need(report['API_supports_one_profile_at_a_time'] and report['host_fixture_holds_all27_profiles'] and not report['actual_MCU_memory_behavior_measured'],'streaming_scope_honest')
    new=load(CORE/'c_matcher_readout_psi.json');old=load(ROOT/'algorithm_work/meter_robust_readout_20261102/pose/candidate_B_with_old_B_readout_psi.json')
    original={r['id']:r for r in old['rows']}
    for r in new['rows']:
        prior=original[r['id']]
        need((r['valid'],r['psi_estimate'],r['reason'])==(prior['valid'],prior['psi_estimate'],prior['reason']),r['id']+'_same_PSI')
    obj=(CORE/'rv32_build/meter_pose_matcher.o').read_bytes()
    eh=struct.unpack_from('<16sHHIIIIIHHHHHH',obj)
    need(eh[0][:6]==b'\x7fELF\x01\x01' and eh[1]==1 and eh[2]==243,'actual_RISC_V32_relocatable_ELF')
    sections=[struct.unpack_from('<IIIIIIIIII',obj,eh[6]+i*eh[11])for i in range(eh[12])]
    text=sum(s[5]for s in sections if s[2]&2 and s[2]&4)
    bss=sum(s[5]for s in sections if s[2]&2 and s[1]==8)
    rodata=sum(s[5]for s in sections if s[2]&2 and not(s[2]&5) and s[1]!=8)
    data=sum(s[5]for s in sections if s[2]&3==3 and not(s[2]&4) and s[1]!=8)
    need((text,rodata,data,bss)==(1548,0,0,0),'actual_ELF_allocated_section_sizes')
    undefined=[]
    for section in sections:
        if section[1]!=2:continue
        strings=sections[section[6]];table=obj[strings[4]:strings[4]+strings[5]]
        for offset in range(section[4],section[4]+section[5],section[9]):
            name,value,size,info,other,index=struct.unpack_from('<IIIBBH',obj,offset)
            if name and index==0:undefined.append(table[name:table.find(b'\0',name)].decode())
    need(undefined==['memset'],'actual_ELF_only_memset_unresolved')
    frames=[int(line.split('\t')[1])for line in(CORE/'rv32_build/meter_pose_matcher.su').read_text('utf-8').splitlines()if line.strip()]
    need(max(frames)==96,'actual_compiler_stack_file_max_frame96')
    result=dict(status='PASS_FROZEN_MATCHER_CORE_NOT_FULL_MCU_PIPELINE',checks=len(checks),fixtures=fixture_reports,
        source_sha256={p.name:sha(p)for p in[CORE/'meter_pose_matcher.c',CORE/'meter_pose_matcher.h',CORE/'verify_matcher.py',CORE/'c_matcher_verification.json',CORE/'c_matcher_readout_psi.json',CORE/'core_completion.json']},
        independent_rebuild_command=command,independent_DLL_sha256=sha(dll),context_bytes=C.sizeof(Context),
        fixed_template_keeps=[1307,1280],max_comparison_product=255*3456**2,generic125_exact_rational_not_IEEE_cancellation_equivalent=True,
        preserved_PSI=dict(valid=21,MAE_psi=new['summary']['reading_mae_psi']),
        RV32_object_scope='Independently parsed RISC-V32 relocatable ELF1548B text,zero allocated rodata/data/BSS and onlymemset unresolved; compiler stack file max single frame96B. Context/profile/templates/callers/libc are not included. Object is not full application link.',
        remaining=['Full integer frontend not proven by frozen float profile fixtures','Combined scratch lifetimes and actual ELF/link/stack fit pending','Host timing is not MCU cycle measurement','No hardware/source-frame domain validation'],
        model_training=False,board_actions=False,H_or_ABC_opened=False)
    (HERE/'integer_matcher_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
