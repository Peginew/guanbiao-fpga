"""Whole production C reader on the59 existing G proxyROIs, no true inputs.

Prediction pass reads onlyROI/radius/id/source, then scoring reads psi labels.
No new thresholds or calibration are fitted here. H/ABC and board not opened.
"""
from pathlib import Path
import ctypes as C,hashlib,json,subprocess,sys,time
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];SRC=HERE/'source'
sys.path.insert(0,str(HERE))
from verify_numeric import Point,Needle
sys.path.insert(0,str(ROOT/'algorithm_work/meter_reference_readout_20261102/integer_pose'))
from verify_matcher import Result
class Print(C.Structure):_fields_=[('roll',C.c_int32),('sse',C.c_uint32),('accepted',C.c_uint8),('reason',C.c_uint8),('mask',C.c_uint8),('count',C.c_uint8)]
class Diagnostic(C.Structure):
    _fields_=[(x,C.c_uint32)for x in ['active','phase','words','completed','cancelled','epoch','source','job','radius','return_code','psi_word']]+[('hub',Point),('landmark',Point*6),('needle',Needle),('ring',Result),('print',Print)]+[(x,C.c_uint32)for x in ['neural_valid','reference_valid','reference_kind','read_valid']]+[('roll',C.c_int32),('stage_cycles',C.c_uint32*5)]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rows(p):return[json.loads(s)for s in Path(p).read_text('utf-8-sig').splitlines()if s.strip()]
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')
def point(p):return dict(roi_xy_q8=[p.x,p.y],roi_xy=[p.x/256,p.y/256],peak_q15=p.peak,margin_q15=p.margin,accepted=bool(p.valid))
def summary(pred,truth,key):
    out=[r for r in pred if r[key]['valid']];real=[r for r in out if truth[r['id']]['target_present']]
    for r in real:r[key]['absolute_error_psi']=abs(r[key]['psi']-truth[r['id']]['pressure']['value'])
    return dict(gauges=56,negative=3,outputs=len(out),gauge_outputs=len(real),negative_outputs=len(out)-len(real),MAE_psi=float(np.mean([r[key]['absolute_error_psi']for r in real]))if real else None,within_025psi=sum(r[key]['absolute_error_psi']<=.25 for r in real),within_05psi=sum(r[key]['absolute_error_psi']<=.5 for r in real),within_1psi=sum(r[key]['absolute_error_psi']<=1 for r in real),over_05psi_ids=[r['id']for r in real if r[key]['absolute_error_psi']>.5],gauge_rejected=56-len(real),output_ids=[r['id']for r in out])
def main():
    out=HERE/'host';out.mkdir(exist_ok=True);dll=out/'meter_landmark_reader.dll'
    names=['mroi_c4.c','mroi_decode.c','reader_numeric.c','reader_runtime.c','reader_sigmoid.c','meter_pose_frontend.c','meter_pose_matcher.c','landmark_geometry.c']
    cmd=['C:/Users/Edward/Desktop/mingw64/bin/gcc.exe','-std=c99','-O2','-shared','-Wl,--export-all-symbols','-DMROI_HOST_TEST','-Wall','-Wextra','-Werror','-ffp-contract=off','-fno-strict-aliasing','-o',str(dll),*[str(SRC/n)for n in names]]
    p=subprocess.run(cmd,capture_output=True);(out/'compile.stdout').write_bytes(p.stdout);(out/'compile.stderr').write_bytes(p.stderr);assert p.returncode==0,p.stderr.decode(errors='replace')
    lib=C.CDLL(str(dll));lib.mroi_reader_diagnostic_size.restype=C.c_uint32;assert lib.mroi_reader_diagnostic_size()==C.sizeof(Diagnostic)
    lib.mroi_reader_host_infer.argtypes=[C.POINTER(C.c_uint8),C.c_uint,C.POINTER(Diagnostic)]
    lib.reader_calibrate_psi_q8.argtypes=[C.c_int32,C.c_int32,C.POINTER(C.c_uint16)]
    data=ROOT/'algorithm_work/meter_cnn_training_20261102';records=rows(data/'prepared_validation.jsonl');assert len(records)==59 and all(r['source_group']=='G'for r in records)
    z=np.load(data/'roi_cache_validation.npz');images=dict(zip(z['ids'].tolist(),z['images']));pred=[];start=time.perf_counter()
    # Only fields allowed at deployment enter C inference.
    for r in records:
        im=np.ascontiguousarray(images[r['id']],np.uint8);d=Diagnostic();t=time.perf_counter()
        assert lib.mroi_reader_host_infer(im.ctypes.data_as(C.POINTER(C.c_uint8)),int(r['roi_request']['radius']),C.byref(d))==1
        b=C.c_uint16();bvalid=bool(d.neural_valid and d.ring.accepted and lib.reader_calibrate_psi_q8(d.needle.angle,d.ring.delta_deg*65536,C.byref(b)))
        row=dict(id=r['id'],source_sha256=r['sha256'],radius=int(r['roi_request']['radius']),hub=point(d.hub),landmarks=[point(x)for x in d.landmark],angle_deg_image=d.needle.angle/65536,needle_peak_q15=d.needle.peak,needle_margin_q15=d.needle.margin,neural_valid=bool(d.neural_valid),ring=dict(accepted=bool(d.ring.accepted),roll=d.ring.delta_deg,reason=d.ring.reason,profile_id=d.ring.profile_id,template_id=d.ring.template_id),landmark_pose=dict(accepted=bool(d.print.accepted),roll=d.print.roll/65536,reason=d.print.reason,inlier_mask=d.print.mask),selected_reference_kind=d.reference_kind,selected_roll=d.roll/65536,return_code=d.return_code,psi_word=d.psi_word,final=dict(valid=bool(d.read_valid),psi=(d.psi_word&65535)/256 if d.read_valid else None),integer_ring_only=dict(valid=bvalid,psi=b.value/256 if bvalid else None),host_seconds=time.perf_counter()-t)
        assert bool(d.psi_word>>31)==bool(d.read_valid)
        if d.ring.accepted:assert d.reference_kind==1 and d.roll==d.ring.delta_deg*65536
        pred.append(row)
    # Scoring-only labels are read after all predictions have been produced.
    truth={r['id']:r for r in records};report=dict(status='FULL_C_PROXY_ROI_REPLAY_COMPLETE_NOT_BOARD_OR_CSI_VALIDATED',unit='psi',summary={key:summary(pred,truth,key)for key in ['integer_ring_only','final']},rows=pred,seconds=time.perf_counter()-start,source_sha256={p.name:sha(p)for p in SRC.iterdir()if p.is_file()},DLL_sha256=sha(dll),input_cache_sha256=sha(data/'roi_cache_validation.npz'),whole_chain_math='W8C4hub +W8sixheads +F32polarQ5/rationalQ6 +W8polarCNN +Q20/Q30ringgeometry +integerprofile/matcher +Q8consensus +frozenF64PSIcal +UQ8result',inference_true_pressure_or_GT_used=False,H_ABC_opened=False,MCU_timing=False,hardware_actions=False)
    write(out/'validation_replay.json',report)
    (out/'validation_predictions.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in pred),'utf-8')
    print(json.dumps(report['summary'],indent=2))
if __name__=='__main__':main()
