"""One final new-network C59 pass plus shared-C 2x2 calibration control.

No H access, training, calibration fit or G threshold tuning. Old-network raw
predictions come from frozen dd8a C59; old-domain reconstruction must match.
"""
from pathlib import Path
import argparse,ctypes as C,hashlib,json,subprocess,sys,time
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];SRC=HERE/'source'
sys.path.insert(0,str(HERE))
from host_replay import Diagnostic,Point,Needle,Result,Print,point,summary
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def rows(p):return[json.loads(s)for s in Path(p).read_text('utf-8-sig').splitlines()if s.strip()]
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')
def cal(lib,raw,domain,ring_only=False):
    q=C.c_uint16();roll=raw['ring']['roll']if ring_only else raw['selected_roll']
    has_ref=raw['ring']['accepted']if ring_only else bool(raw['selected_reference_kind'])
    valid=bool(raw['neural_valid']and has_ref and lib.reader_calibrate_psi_q8_domain(round(raw['angle_deg_image']*65536),round(roll*65536),domain,C.byref(q)))
    return dict(valid=valid,psi=q.value/256 if valid else None)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run',action='store_true');ap.add_argument('--frozen-elf-sha');args=ap.parse_args()
    if not args.run:print('NO_RUN: prepare only; supervisor must freeze finalELF first');return
    elf=HERE/'build/meter_landmark_reader.elf';receipt=load(HERE/'build/build_receipt.json')
    if not args.frozen_elf_sha or sha(elf)!=args.frozen_elf_sha or receipt['ELF']['sha256']!=args.frozen_elf_sha:raise ValueError('FinalELF not frozen')
    for n,want in receipt['source_sha256'].items():
        if sha(SRC/n)!=want:raise ValueError(f'Compiled source drift: {n}')
    if sha(SRC/'landmark_weights_q8.h')!=sha(HERE.parent/'model/landmark_integer/landmark_weights.h'):raise ValueError('New model export not actually linked')
    marker=HERE/'G_DEV_C_REPLAY_ONCE.json'
    if marker.exists():raise ValueError('One finalC59 attempt already exists; no automatic retry')
    out=HERE/'host_matrix';out.mkdir(exist_ok=False)
    names=['mroi_c4.c','mroi_decode.c','reader_numeric.c','reader_runtime.c','reader_sigmoid.c','meter_pose_frontend.c','meter_pose_matcher.c','landmark_geometry.c']
    dll=out/'reader_matrix.dll';cmd=['C:/Users/Edward/Desktop/mingw64/bin/gcc.exe','-std=c99','-O2','-shared','-Wl,--export-all-symbols','-DMROI_HOST_TEST','-Wall','-Wextra','-Werror','-ffp-contract=off','-fno-strict-aliasing','-o',str(dll),*[str(SRC/n)for n in names]]
    p=subprocess.run(cmd,capture_output=True);(out/'compile.stdout').write_bytes(p.stdout);(out/'compile.stderr').write_bytes(p.stderr);assert p.returncode==0,p.stderr.decode(errors='replace')
    lib=C.CDLL(str(dll));lib.mroi_reader_diagnostic_size.restype=C.c_uint32;assert lib.mroi_reader_diagnostic_size()==C.sizeof(Diagnostic)
    lib.mroi_reader_host_infer.argtypes=[C.POINTER(C.c_uint8),C.c_uint,C.POINTER(Diagnostic)]
    lib.reader_calibrate_psi_q8_domain.argtypes=[C.c_int32,C.c_int32,C.c_int,C.POINTER(C.c_uint16)]
    with marker.open('x',encoding='utf-8')as f:json.dump(dict(status='RUNNING',ELF_sha256=args.frozen_elf_sha),f)
    try:
        data=ROOT/'algorithm_work/meter_cnn_training_20261102';records=rows(data/'prepared_validation.jsonl');assert len(records)==59 and all(r['source_group']=='G'for r in records)
        z=np.load(data/'roi_cache_validation.npz');images=dict(zip(z['ids'].tolist(),z['images']));pred=[];started=time.perf_counter()
        old_path=ROOT/'algorithm_work/meter_landmark_mcu_training_20261103/firmware/host/validation_replay.json';old={r['id']:r for r in load(old_path)['rows']}
        for r in records:
            im=np.ascontiguousarray(images[r['id']],np.uint8);d=Diagnostic()
            assert lib.mroi_reader_host_infer(im.ctypes.data_as(C.POINTER(C.c_uint8)),int(r['roi_request']['radius']),C.byref(d))==1
            n=dict(id=r['id'],source_sha256=r['sha256'],radius=int(r['roi_request']['radius']),hub=point(d.hub),landmarks=[point(x)for x in d.landmark],angle_deg_image=d.needle.angle/65536,needle_peak_q15=d.needle.peak,needle_margin_q15=d.needle.margin,neural_valid=bool(d.neural_valid),ring=dict(accepted=bool(d.ring.accepted),roll=d.ring.delta_deg,reason=d.ring.reason,profile_id=d.ring.profile_id,template_id=d.ring.template_id),landmark_pose=dict(accepted=bool(d.print.accepted),roll=d.print.roll/65536,reason=d.print.reason,inlier_mask=d.print.mask),selected_reference_kind=d.reference_kind,selected_roll=d.roll/65536,return_code=d.return_code,psi_word=d.psi_word)
            o=old[n['id']];assert o['source_sha256']==n['source_sha256']
            # Frozen oldhub/polar/ring must be independent of newprint weights.
            for key in ['hub','angle_deg_image','neural_valid','ring']:assert n[key]==o[key],(n['id'],key)
            n['old_network_old_domain']=cal(lib,o,0);n['old_network_corrected_domain']=cal(lib,o,1)
            n['new_network_old_domain']=cal(lib,n,0);n['new_network_corrected_domain']=cal(lib,n,1)
            n['ring_only_old_domain']=cal(lib,n,0,True);n['ring_only_corrected_domain']=cal(lib,n,1,True)
            assert n['old_network_old_domain']['valid']==o['final']['valid'] and n['old_network_old_domain']['psi']==o['final']['psi']
            assert n['new_network_corrected_domain']['valid']==bool(d.read_valid)
            assert n['new_network_corrected_domain']['psi']==((d.psi_word&65535)/256 if d.read_valid else None)
            pred.append(n)
        (out/'predictions_before_scoring.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in pred),'utf-8')
        truth={r['id']:r for r in records};arms=['old_network_old_domain','old_network_corrected_domain','new_network_old_domain','new_network_corrected_domain','ring_only_old_domain','ring_only_corrected_domain']
        summaries={key:summary(pred,truth,key)for key in arms}
        changes={}
        for a,b in [('old_network_old_domain','new_network_old_domain'),('new_network_old_domain','new_network_corrected_domain'),('old_network_old_domain','old_network_corrected_domain')]:
            added=[r['id']for r in pred if r[b]['valid']and not r[a]['valid']];lost=[r['id']for r in pred if r[a]['valid']and not r[b]['valid']]
            changes[a+'__to__'+b]=dict(added=added,withdrawn=lost,new_over05psi=[r['id']for r in pred if r['id']in added and truth[r['id']]['target_present']and r[b]['absolute_error_psi']>.5])
        report=dict(status='EXPANDED_FINAL_NEW_C_CODE_G59_ONCE_COMPLETED',unit='psi',primary_network_comparison='old_network_old_domain versus new_network_old_domain',production='new_network_corrected_domain',summary=summaries,changes=changes,rows=pred,old_raw_source=str(old_path),old_raw_sha256=sha(old_path),old_network_inference_reused_not_reexecuted=True,old_domain_all59_exactly_reconstructed=True,ELF_sha256=args.frozen_elf_sha,DLL_sha256=sha(dll),source_sha256=receipt['source_sha256'],seconds=time.perf_counter()-started,pressure_inference_input=False,C_group_opened=False,H_rerun=False,hardware_actions=False)
        write(out/'validation_matrix.json',report);write(marker,dict(status='COMPLETED',ELF_sha256=args.frozen_elf_sha,report_sha256=sha(out/'validation_matrix.json')));print(json.dumps(summaries,indent=2))
    except Exception as exc:write(marker,dict(status='FAILED_NO_AUTOMATIC_RETRY',ELF_sha256=args.frozen_elf_sha,error=str(exc)));raise
if __name__=='__main__':main()
