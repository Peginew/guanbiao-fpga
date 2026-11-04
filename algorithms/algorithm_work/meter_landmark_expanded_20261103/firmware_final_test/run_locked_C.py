"""Prepare-only until an explicit FINAL_FROZEN manifest and --run.

One selected full C reader, one C prediction pass. No training/selection,
native point supervision, C print landmarks or pressure-based model inputs.
"""
from pathlib import Path
import argparse,ctypes as C,hashlib,importlib.util,json,sys,traceback
from datetime import datetime,timezone

HERE=Path(__file__).resolve().parent
TASK=HERE.parent
ONCE=HERE/'C_TEST_ONCE.json'
CANONICAL_SHA='cb977f2b8f1b1324993982f9947314ae9a130c055cdcf90f65b5081d4ad22b7e'
BANDS=(.25,.5,1.)

class Point(C.Structure):
    _fields_=[('x',C.c_int32),('y',C.c_int32),('peak',C.c_uint16),('margin',C.c_uint16),('valid',C.c_uint8)]
class Needle(C.Structure):
    _fields_=[('angle',C.c_int32),('peak',C.c_uint16),('margin',C.c_uint16),('outside',C.c_uint16),('valid',C.c_uint8)]
class Ring(C.Structure):
    _fields_=[(x,C.c_uint32)for x in ['best_sum','far_sum','margin_numerator','margin_denominator']]+[(x,C.c_uint16)for x in ['best_keep','far_keep']]+[('delta_deg',C.c_int16),('far_delta_deg',C.c_int16)]+[(x,C.c_uint8)for x in ['profile_id','template_id','accepted','score_pass','margin_pass','interior_pass','reason']]
class Print(C.Structure):
    _fields_=[('roll',C.c_int32),('sse',C.c_uint32)]+[(x,C.c_uint8)for x in ['accepted','reason','mask','count']]
class Diagnostic(C.Structure):
    _fields_=[(x,C.c_uint32)for x in ['active','phase','words','completed','cancelled','epoch','source','job','radius','return_code','psi_word']]+[('hub',Point),('landmark',Point*6),('needle',Needle),('ring',Ring),('print',Print)]+[(x,C.c_uint32)for x in ['neural_valid','reference_valid','reference_kind','read_valid']]+[('roll',C.c_int32),('stage_cycles',C.c_uint32*5)]

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path):return json.loads(Path(path).read_text('utf-8-sig'))
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf-8')
def now():return datetime.now(timezone.utc).isoformat()
def no_run(reason):print(json.dumps(dict(status='NO_RUN',reason=reason,C_images_read=False,C_labels_read=False)));return 0

def check_artifact(item):
    p=Path(item['path']).resolve();expected=item['sha256']
    if len(expected)!=64 or digest(p)!=expected:raise ValueError(f'Frozen artifact mismatch: {p}')
    return p

def gate(manifest_path,run_requested):
    # This function never opens canonical annotations, test indexes or PNGs.
    if manifest_path is None:return None,'No --manifest supplied'
    m=load(manifest_path)
    if m.get('status')!='FINAL_FROZEN':return None,'Manifest is not FINAL_FROZEN'
    if not run_requested:return None,'Prepared only: --run was not supplied'
    if m.get('permission_to_run_C_once')is not True:return None,'No explicit one-time C authorization'
    if m.get('selected_variant')!='FINAL_U7_TRAIN_CORRECTED':return None,'FinalU7/TRAINcorrected candidate must be selected'
    if m.get('selected_point_model')not in ['PRIOR_B857','EXPANDED_ABDEF']:return None,'Exactly one globally selected point model must be fixed before C'
    if m.get('harness_sha256')!=digest(__file__):return None,'Harness not frozen by manifest'
    if m.get('fixed_metrics',{}).get('bands_psi')!=list(BANDS):return None,'Descriptive metric contract differs'
    if m.get('fixed_metrics',{}).get('pressure_used_only_for_scoring')is not True:return None,'Pressure boundary not accepted'
    if m.get('canonical',{}).get('sha256')!=CANONICAL_SHA:return None,'Canonical identity must remain the signed version'
    if m.get('C_expected_count')!=59:return None,'Original whole C group must be retained'
    if m.get('C_prior_annotation_QA_exposure_acknowledged')is not True:return None,'Prior C annotation-QA exposure must be declared; this is not blind human-gold testing'
    for name in ['ELF','DLL','build_receipt','roi_adapter']:
        check_artifact(m[name])
    for name in ['selection_policy_before_G','selection_decision_before_C']:
        check_artifact(m[name])
    artifacts=m.get('frozen_model_and_calibration_artifacts',[])
    if len(artifacts)<4:return None,'Freeze model, quantized weights and calibration source identities first'
    for item in artifacts:check_artifact(item)
    receipt=load(m['build_receipt']['path'])
    if receipt['ELF']['sha256']!=m['ELF']['sha256']:return None,'ELF not bound to actual build receipt'
    source=Path(m['compiled_source_directory']).resolve()
    for name,want in receipt['source_sha256'].items():
        if digest(source/name)!=want:return None,f'Compiled source drift: {name}'
    if ONCE.exists():return None,'C once-only marker exists; do not select/retry from C'
    return m,None

def point(p):return dict(roi_xy_q8=[p.x,p.y],peak_q15=p.peak,margin_q15=p.margin,evidence_sufficient=bool(p.valid))
def infer_one(lib,roi,radius):
    import numpy as np
    im=np.ascontiguousarray(roi,np.uint8);d=Diagnostic()
    if lib.mroi_reader_host_infer(im.ctypes.data_as(C.POINTER(C.c_uint8)),int(radius),C.byref(d))!=1:
        raise ValueError('Frozen C reader rejected its host invocation')
    q=C.c_uint16();ring_read=bool(d.neural_valid and d.ring.accepted and lib.reader_calibrate_psi_q8(d.needle.angle,d.ring.delta_deg*65536,C.byref(q)))
    if bool(d.psi_word>>31)!=bool(d.read_valid):raise ValueError('Same-source PSI valid mismatch')
    if d.ring.accepted and (d.reference_kind!=1 or d.roll!=d.ring.delta_deg*65536):raise ValueError('Old-reference-first route changed')
    return dict(hub=point(d.hub),landmarks=[point(p)for p in d.landmark],angle_deg_image=d.needle.angle/65536,neural_valid=bool(d.neural_valid),ring=dict(accepted=bool(d.ring.accepted),roll_deg=d.ring.delta_deg,reason=d.ring.reason),landmark_pose=dict(accepted=bool(d.print.accepted),roll_deg=d.print.roll/65536,reason=d.print.reason,inlier_mask=d.print.mask),selected_reference_kind=d.reference_kind,return_code=d.return_code,psi_word=d.psi_word,integer_ring_only=dict(valid=ring_read,psi=q.value/256 if ring_read else None),trained_sixpoint_fusion=dict(valid=bool(d.read_valid),psi=(d.psi_word&65535)/256 if d.read_valid else None))

def summarize(pred,truth,key):
    gauges=[p for p in pred if truth[p['id']]['target_present']]
    neg=[p for p in pred if not truth[p['id']]['target_present']]
    valid=[p for p in gauges if p[key]['valid']]
    evaluable=[]
    for p in valid:
        pressure=truth[p['id']].get('pressure',{})
        if pressure.get('value')is None:continue
        if pressure.get('unit')!='psi':raise ValueError('Final test labels must be PSI directly')
        evaluable.append((p,abs(p[key]['psi']-float(pressure['value']))))
    return dict(total_rows=len(pred),gauges=len(gauges),negative=len(neg),gauge_outputs=len(valid),gauge_rejected=len(gauges)-len(valid),negative_outputs=sum(p[key]['valid']for p in neg),pressure_evaluable_outputs=len(evaluable),output_without_known_pressure=len(valid)-len(evaluable),MAE_psi=sum(e for _,e in evaluable)/len(evaluable)if evaluable else None,error_bands=[dict(absolute_error_max_psi=b,count=sum(e<=b for _,e in evaluable),over_ids=[p['id']for p,e in evaluable if e>b])for b in BANDS],output_ids=[p['id']for p in valid],all_gauges_are_denominator=True)

def execute(m,manifest_path):
    # Reserve the one permitted evaluation before opening any C data. A failed
    # attempt remains visible for supervisor adjudication; no automatic retry.
    marker=dict(status='RUNNING',started_UTC=now(),manifest_sha256=digest(manifest_path),selected_variant=m['selected_variant'],selected_point_model=m['selected_point_model'],C_open_started=False)
    with ONCE.open('x',encoding='utf-8')as f:json.dump(marker,f,ensure_ascii=False,indent=2)
    out=Path(m['output_directory']).resolve();out.mkdir(parents=True,exist_ok=False)
    try:
        import numpy as np
        spec=importlib.util.spec_from_file_location('frozen_C_roi_arithmetic',m['roi_adapter']['path'])
        adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
        lib=C.CDLL(str(Path(m['DLL']['path']).resolve()))
        lib.mroi_reader_diagnostic_size.restype=C.c_uint32
        if lib.mroi_reader_diagnostic_size()!=C.sizeof(Diagnostic):raise ValueError('Frozen C diagnostic ABI differs')
        lib.mroi_reader_host_infer.argtypes=[C.POINTER(C.c_uint8),C.c_uint,C.POINTER(Diagnostic)]
        lib.reader_calibrate_psi_q8.argtypes=[C.c_int32,C.c_int32,C.POINTER(C.c_uint16)]
        # This is the first canonical/C-label access; none exists in gate().
        marker['C_open_started']=True;write(ONCE,marker)
        canonical_path=check_artifact(m['canonical']);canonical=load(canonical_path)
        held=[r for r in canonical['records']if r['group']=='C']
        if len(held)!=59 or len({r['id']for r in held})!=59:raise ValueError('C group was changed or incomplete')
        # Same predeclared negative-window proxy as train/G: session median
        # FACE BOXES, not psi, hub, thin-tip, print-point or learned prediction.
        boxes=[r['bbox_native_xyxy']for r in held if r['target_present']and r.get('bbox_native_xyxy')and 160<=max(r['bbox_native_xyxy'][2]-r['bbox_native_xyxy'][0],r['bbox_native_xyxy'][3]-r['bbox_native_xyxy'][1])<=499]
        if not boxes:raise ValueError('No boxes support the frozen negative proxy policy')
        negative_box=np.rint(np.median(boxes,axis=0)).astype(int).tolist()
        pred=[];roi_log=[]
        for r in held:
            clean=dict(id=r['id'],path=r['path'],sha256=r['sha256'])
            box=r['bbox_native_xyxy']if r['target_present']else negative_box
            request=adapter.window_policy(box)
            # Model sees only ROI bytes and actual locator-proxy radius. Labels
            # never enter the C function or alter any permission/choice.
            if digest(clean['path'])!=clean['sha256']:raise ValueError(f'Native PNG drift: {clean["id"]}')
            native=adapter.read_native(clean);roi=adapter.blockmean(adapter.gray_from_bgr(native),request)
            row=dict(id=clean['id'],source_sha256=clean['sha256'],ROI_request=request,**infer_one(lib,roi,request['radius']))
            pred.append(row);roi_log.append(dict(id=clean['id'],ROI_sha256=hashlib.sha256(roi.tobytes()).hexdigest(),request=request))
        # Persist complete predictions before inspecting pressure for scoring.
        (out/'predictions_before_scoring.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in pred),'utf-8')
        truth={r['id']:r for r in held}
        summaries={key:summarize(pred,truth,key)for key in ['integer_ring_only','trained_sixpoint_fusion']}
        added=[p for p in pred if p['trained_sixpoint_fusion']['valid']and not p['integer_ring_only']['valid']]
        lost=[p['id']for p in pred if p['integer_ring_only']['valid']and not p['trained_sixpoint_fusion']['valid']]
        if lost:raise ValueError(f'Old-first same-C outputs were withdrawn: {lost}')
        changes=[]
        for p in added:
            t=truth[p['id']];v=t.get('pressure',{}).get('value')
            changes.append(dict(id=p['id'],target_present=t['target_present'],psi=p['trained_sixpoint_fusion']['psi'],absolute_error_psi=abs(float(v)-p['trained_sixpoint_fusion']['psi'])if t['target_present']and v is not None else None))
        report=dict(status='FINAL_FROZEN_C_ONCE_EVALUATION_COMPLETED',unit='psi',selected_variant=m['selected_variant'],selected_point_model=m['selected_point_model'],manifest_sha256=digest(manifest_path),harness_sha256=digest(__file__),ELF_sha256=m['ELF']['sha256'],DLL_sha256=m['DLL']['sha256'],summary=summaries,new_fusion_outputs=changes,withdrawn_old_integer_outputs=lost,ROI_log=roi_log,rows=pred,data_boundary=dict(C_read_only_after_FINAL_FROZEN=True,C_used_for_training_selection_threshold_calibration=False,C_prior_annotation_QA_exposure=True,blind_human_gold_test=False,canonical_document_parsed_only_to_select_C=True,ABH_images_opened=False,ABH_rows_selected_for_execution=False,H_inference_rerun=False,H_scores_changed=False,pressure_input_to_model=False,native_keypoints_used=False,C_print_point_labels_required=False,ROI_bbox='manualcanonicalfaceboxproxy,notactualFPGAautolocalizer',negative_proxy='sameCsessionmedianfaceboxeswithdiameter160..499',execution_scope='FrozenC128ROIconsumer,nophysicalMMIO/clientorMCUcycletest',actual_CSI_ROI_equivalence_proven=False,industrial_FAR_proven=False,metric_bands_are_descriptive_not_user_tolerances=True),hardware_actions=False)
        write(out/'final_C_evaluation.json',report)
        marker.update(status='COMPLETED',completed_UTC=now(),report_path=str(out/'final_C_evaluation.json'),report_sha256=digest(out/'final_C_evaluation.json'));write(ONCE,marker)
        print(json.dumps(dict(status=marker['status'],report=marker['report_path'],summary=summaries),ensure_ascii=False,indent=2))
    except Exception as exc:
        marker.update(status='FAILED_NO_AUTOMATIC_RETRY',failed_UTC=now(),error=str(exc));write(ONCE,marker)
        (out/'failure_traceback.txt').write_text(traceback.format_exc(),'utf-8');raise

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--manifest',type=Path);ap.add_argument('--run',action='store_true');args=ap.parse_args()
    m,reason=gate(args.manifest,args.run)
    if m is None:return no_run(reason)
    execute(m,args.manifest);return 0
if __name__=='__main__':raise SystemExit(main())
