"""Actual C matcher on all fixed same-input fixtures, with frozen PSI gates."""
from pathlib import Path
import argparse,ctypes as C,json,sys,time
import numpy as np
HERE=Path(__file__).resolve().parent;TASK=HERE.parent;ROOT=TASK.parents[1]
OLD=ROOT/'algorithm_work/meter_robust_readout_20261102/pose'
BASE=ROOT/'algorithm_work/meter_pointer_readout_20261102'
DATA=ROOT/'algorithm_work/meter_cnn_training_20261102'
sys.path.insert(0,str(BASE/'readout_psi'))
import readout_adapter as numeric


def load(path):return json.loads(Path(path).read_text('utf-8-sig'))
def rows(path):return [json.loads(s) for s in Path(path).read_text('utf-8-sig').splitlines() if s.strip()]
def write(path,v):Path(path).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')


class Template(C.Structure):
    _fields_=[('indices',C.POINTER(C.c_uint16)),('values',C.POINTER(C.c_int8)),('local_shift',C.POINTER(C.c_int16)),('count',C.c_uint16)]
class Match(C.Structure):
    _fields_=[('sum',C.c_uint32),('keep',C.c_uint16),('profile_id',C.c_uint8),('template_id',C.c_uint8),('present',C.c_uint8)]
class Context(C.Structure):
    _fields_=[('best',Match*49),('histogram',C.c_uint16*256),('accepted_profiles',C.c_uint16),('center_allowed',C.c_uint8)]
class Result(C.Structure):
    _fields_=[('best_sum',C.c_uint32),('far_sum',C.c_uint32),('margin_cross_numerator',C.c_uint32),('margin_cross_denominator',C.c_uint32),
              ('best_keep',C.c_uint16),('far_keep',C.c_uint16),('delta_deg',C.c_int16),('far_delta_deg',C.c_int16),
              ('profile_id',C.c_uint8),('template_id',C.c_uint8),('accepted',C.c_uint8),('score_pass',C.c_uint8),('margin_pass',C.c_uint8),
              ('search_interior_pass',C.c_uint8),('reason',C.c_uint8)]


def dll():
    lib=C.CDLL(str(HERE/'meter_pose_matcher.dll'))
    for name,ty in [('mp_context_size',Context),('mp_template_size',Template),('mp_result_size',Result)]:
        f=getattr(lib,name);f.restype=C.c_size_t;assert f()==C.sizeof(ty),(name,f(),C.sizeof(ty))
    lib.mp_template_init.argtypes=[C.POINTER(Template),C.POINTER(C.c_uint16),C.POINTER(C.c_int8),C.c_uint16,C.POINTER(C.c_int16)]
    lib.mp_prepare.argtypes=[C.POINTER(Context),C.c_uint8]
    lib.mp_push.argtypes=[C.POINTER(Context),C.POINTER(C.c_int8),C.c_uint16,C.c_uint8,C.POINTER(Template),C.c_uint8]
    lib.mp_finish.argtypes=[C.POINTER(Context),C.POINTER(Result)]
    return lib


def templates(lib):
    z=np.load(HERE/'fixtures/templates.npz');keep=[];tt=(Template*2)()
    for j in range(2):
        idx=np.ascontiguousarray(z[f'indices_{j}'],dtype=np.uint16);val=np.ascontiguousarray(z[f'values_{j}'],dtype=np.int8);shift=np.ascontiguousarray(z[f'shifts_{j}'],dtype=np.int16)
        keep.extend([idx,val,shift]);assert lib.mp_template_init(C.byref(tt[j]),idx.ctypes.data_as(C.POINTER(C.c_uint16)),val.ctypes.data_as(C.POINTER(C.c_int8)),len(idx),shift.ctypes.data_as(C.POINTER(C.c_int16)))==0
    return tt,keep


def run_one(lib,tt,profiles,outside,center_allowed):
    ctx=Context();lib.mp_prepare(C.byref(ctx),int(center_allowed))
    start=time.perf_counter()
    for j,(q,oc) in enumerate(zip(profiles,outside)):
        q=np.ascontiguousarray(q,dtype=np.int8)
        ret=lib.mp_push(C.byref(ctx),q.ctypes.data_as(C.POINTER(C.c_int8)),int(oc),j,tt,2)
        assert ret>=0
    result=Result();assert lib.mp_finish(C.byref(ctx),C.byref(result))==0
    return result,ctx,time.perf_counter()-start


def make_pose(r,result,z):
    names=['D_002','E_002'];reason=['ROI128_LOCAL_CONTRAST_MULTI_RING_SUPPORTED','PREDICTED_HUB_TOO_FAR_FROM_LOCATOR_CENTER_FOR_RING_POSE','ROI128_RING_OUTSIDE','ROI128_RING_AMBIGUOUS'][result.reason]
    p=dict(id=r['id'],source_sha256=r['source_sha256'],split=r['split'],accepted=bool(result.accepted),reason=reason,
           integer_matcher=True,query_uses_GT_points=False,query_uses_pressure=False,native_frame_used=False)
    if result.best_keep:
        dx,dy,scale=z['hypotheses'][result.profile_id]
        p.update(relative_roll_deg=float(result.delta_deg),score=1-result.best_sum/(128*result.best_keep),
            margin=result.far_sum/(128*result.far_keep)-result.best_sum/(128*result.best_keep),
            reference_id=names[result.template_id],dx=float(dx),dy=float(dy),radius_scale=float(scale),
            outside_fraction=float(z['outside_counts'][result.profile_id])/4320)
    return p


def numeric_result(poses):
    cal=load(OLD/'candidate_B_calibration_psi.json');lookup={r['id']:r for r in rows(DATA/'prepared_validation.jsonl')}
    pp=rows(BASE/'polar_angle/run_001/validation_predictions.jsonl')
    outputs=[numeric.apply_prediction(p,poses[p['id']],cal) for p in pp]
    for r in outputs:r['pose_source']='C_INTEGER_MATCHER_WITH_FROZEN_OLD_B_CALIBRATION'
    return dict(status='C_MATCHER_PC_SAME_INPUT_PSI_REFERENCE_NOT_MCU_DEPLOYMENT',unit='psi',summary=numeric.score_outputs(outputs,lookup),rows=outputs)


def main():
    lib=dll();tt,keep=templates(lib);manifest=load(HERE/'fixtures/manifest.json');poses=[];timings=[];diff=[];numeric=[]
    for r in manifest['records']:
        z=np.load(HERE/'fixtures'/(r['id']+'.npz'));result,ctx,elapsed=run_one(lib,tt,z['profiles'],z['outside_counts'],r['center_allowed'])
        p=make_pose(r,result,z);poses.append(p);timings.append(elapsed)
        old=r['baseline'];fields=['accepted','reason']
        if 'relative_roll_deg' in old:fields+=['relative_roll_deg','reference_id','dx','dy','radius_scale']
        bad=[key for key in fields if p.get(key)!=old.get(key)]
        if bad:diff.append(dict(id=r['id'],fields=bad,old=old,integer=p))
        for key in ('score','margin'):
            if key in old:numeric.append(abs(p[key]-old[key]))
    byid={r['id']:r for r in poses};report=numeric_result(byid)
    (HERE/'c_matcher_pose.jsonl').write_text(''.join(json.dumps(p)+'\n' for p in poses),'utf-8')
    write(HERE/'c_matcher_readout_psi.json',report)
    receipt=dict(status='PASS_C_INTEGER_MATCHER_EXACT_FROZEN_FRONTEND' if not diff and max(numeric,default=0)<1e-12 else 'FAIL_C_MATCHER_DIFFERENCE',
        records=len(poses),gate_or_winner_mismatches=diff,max_score_margin_roundoff=max(numeric,default=0),
        host_timing_seconds=dict(median=float(np.median(timings)),max=float(max(timings)),total=float(sum(timings))),
        structure_sizes=dict(context=C.sizeof(Context),template=C.sizeof(Template),result=C.sizeof(Result)),
        API_supports_one_profile_at_a_time=True,host_fixture_holds_all27_profiles=True,
        actual_MCU_memory_behavior_measured=False,frontend_still_float_OpenCV=True,full_integer_frontend_proven=False,
        MCU_linked=False,MCU_cycles_measured=False,PSI=report['summary'],H_opened=False,hardware_actions=False)
    write(HERE/'c_matcher_verification.json',receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k!='PSI'},ensure_ascii=False,indent=2))
    print('readings',report['summary']['valid_readings'],'MAE',report['summary']['reading_mae_psi'])


if __name__=='__main__':main()
