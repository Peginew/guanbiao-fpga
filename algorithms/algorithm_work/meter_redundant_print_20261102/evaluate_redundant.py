"""Separate visual/automatic redundant-point experiments with exact old-first routing.

No G fitting, no neural updates, no device I/O. The visual reference arm is
explicitly annotation-assisted; the automatic arm must consume no query labels.
"""
from pathlib import Path
import csv,hashlib,json,math,sys
import numpy as np
from landmark_geometry import NAMES,CONFIG,fit_similarity,consensus
from fusion import select_reference,preflight

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
DATA=ROOT/'algorithm_work/meter_cnn_training_20261102'
MODEL=ROOT/'algorithm_work/meter_pointer_readout_20261102'
OLD=ROOT/'algorithm_work/meter_robust_readout_20261102/pose'
PREVIOUS=ROOT/'algorithm_work/meter_print_reference_control_20261102'
sys.path.insert(0,str(MODEL/'readout_psi'));import readout_adapter as numeric
sys.path.insert(0,str(PREVIOUS));import run_controls as controls


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def rows(p):return [json.loads(s) for s in Path(p).read_text('utf-8-sig').splitlines() if s.strip()]
def json_numeric(value):
    if isinstance(value,np.generic):return value.item()
    if isinstance(value,np.ndarray):return value.tolist()
    raise TypeError(type(value).__name__)
def write(p,v):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,default=json_numeric)+'\n','utf-8')
def save_rows(p,rr):Path(p).write_text(''.join(json.dumps(r,ensure_ascii=False,default=json_numeric)+'\n' for r in rr),'utf-8')


def point_to_normalized(p,record,prediction):
    r=record['roi_request'];s=r['stride']
    xy=(np.asarray(p,np.float64)-[r['x0'],r['y0']]-(s-1)/2)/s
    return (xy-np.asarray(prediction['hub_roi']))*48/r['radius']+[64,64],xy


def manual_points(annotation,record,prediction,template=False):
    assert annotation['source_sha256']==record['sha256'],record['id']
    assert set(NAMES)<=set(annotation['anchors']),(record['id'],'Missing point visibility fields')
    flag=annotation.get('point_selection_used_pressure_or_predictions',annotation.get('pressure_or_query_neural_pose_used_for_points'))
    assert flag is False,(record['id'],'point-label source is not declared')
    pp={};details={}
    for name in NAMES:
        a=annotation['anchors'].get(name,{})
        xy=a.get('native_xy');visible=a.get('visibility') in ('visible','partially_visible','partial')
        if not visible or xy is None or (template and a.get('template_usable') is False):
            details[name]=dict(available=False,visibility=a.get('visibility','unknown'),reason=a.get('reason'));continue
        q,roi=point_to_normalized(xy,record,prediction)
        inside=bool(np.all((roi>=0)&(roi<=127)))
        details[name]=dict(available=inside,visibility=a['visibility'],roi_xy=roi.tolist(),normalized_xy=q.tolist(),
            uncertainty_native_px=a.get('uncertainty_native_px'))
        if inside:pp[name]=q.tolist()
    return pp,details


def setup():
    tr={r['id']:r for r in rows(DATA/'prepared_train.jsonl')}
    pred={r['id']:r for r in rows(MODEL/'polar_angle/run_001/train_predictions.jsonl')}
    ref2=load(HERE/'annotations/reference_D002.json');ref25=load(HERE/'annotations/reference_D025.json')
    p2,d2=manual_points(ref2,tr['D_002'],pred['D_002'],template=True)
    p25,d25=manual_points(ref25,tr['D_025'],pred['D_025'],template=True)
    clean=('outer_psi_5_text_centroid','outer_psi_10_text_centroid','outer_psi_15_text_centroid','lower_striped_ball_print_centroid')
    common=[name for name in clean if name in p2 and name in p25]
    assert len(common)>=3,'At least3 clean train identities are needed for canonical reference alignment'
    f=fit_similarity([p2[k] for k in common],[p25[k] for k in common])
    assert f is not None and f['RMS']<=CONFIG['RMS_max'],'Train reference alignment failed; do not use G torepair'
    return dict(canonical_image='D_025',angle_zero='D_002',reference_points_normalized=p25,
        canonical_roll_relative_D002=float(f['rotation_deg']),
        alignment_direction='D002 -> D025; add this offset to query(D025->query) rotation',
        alignment_identities=common,alignment_RMS=f['RMS'],alignment_scale=f['scale'],
        alignment_matrix=f['matrix'].tolist(),reference_source_sha256=dict(D002=sha(HERE/'annotations/reference_D002.json'),D025=sha(HERE/'annotations/reference_D025.json')),
        clean_D002_points=d2,canonical_D025_points=d25,query_GT_or_PSI_used=False)


def point_rows_auto(row):
    points=row.get('points',row.get('anchors',{}));pp={}
    assert set(NAMES)<=set(points),(row['id'],'Missing automatic per-identity evidence')
    for name in NAMES:
        p=points.get(name,{})
        if not p.get('accepted',False):continue
        q=p.get('normalized_xy')
        assert q is not None,(row['id'],name)
        assert np.asarray(q).shape==(2,) and np.isfinite(q).all()
        pp[name]=q
    return pp


def new_poses(records,predictions,reference_setup,mode):
    reference=reference_setup['reference_points_normalized'];offset=reference_setup['canonical_roll_relative_D002']
    manual={r['id']:r for r in rows(HERE/'annotations/print_annotations.jsonl')} if mode=='visual' else None
    automatic={r['id']:r for r in rows(HERE/'automatic/predictions.jsonl')} if mode=='automatic' else None
    out=[];point_details={}
    for r in records:
        i=r['id'];p=predictions[i]
        if mode=='visual':q,details=manual_points(manual[i],r,p);point_details[i]=details
        else:
            row=automatic[i];assert row['source_sha256']==r['sha256']
            q=point_rows_auto(row);point_details[i]=row['points']
        geo=consensus(reference,q,offset)
        out.append(dict(id=i,source_sha256=r['sha256'],split=r['split'],**geo,
            reference_method=mode,query_pressure_used=False,query_needle_reference_used=False,
            query_visual_labels_used=mode=='visual',automatic_reference_inference=mode=='automatic'))
    return {r['id']:r for r in out},point_details


def evaluate(name,records,predictions,oldposes,poses,cal,oldoutputs,fuse=True):
    outputs=[];routes=[];raw_reference_false_accept=[]
    for r in records:
        i=r['id'];new=poses.get(i,dict(accepted=False));old=oldposes[i]
        if name=='old_ring':selected=old;route='OLD_REFERENCE_PRESERVED' if old['accepted'] else 'NO_ACCEPTED_REFERENCE'
        elif fuse:selected,route=select_reference(old,new)
        else:selected=new;route='FORCED_NEW_REFERENCE' if new['accepted'] else 'NO_ACCEPTED_REFERENCE'
        result=numeric.apply_prediction(predictions[i],selected,cal)
        result.update(reference_route=route,old_reference_accepted=old['accepted'],new_reference_accepted=bool(new.get('accepted')),
            old_reference_reason=old['reason'],new_reference_reason=new.get('reason'),
            old_model_permitted=predictions[i]['valid'],new_reference_identities=new.get('inlier_identities',[]))
        outputs.append(result);routes.append(dict(id=i,route=route,old_pose=old,new_pose=new))
        if not r['target_present'] and new.get('accepted'):raw_reference_false_accept.append(i)
    summary=controls.summarize(outputs,records)
    differences=controls.compare(outputs,oldoutputs)
    old_map={o['id']:o for o in oldoutputs}
    old_kept=[];old_changed=[]
    for o in outputs:
        i=o['id'];old=old_map[i]
        if old['valid']:
            equal=(o['valid'],o['psi_estimate'],o['reason'],o['source_sha256'])==(old['valid'],old['psi_estimate'],old['reason'],old['source_sha256'])
            (old_kept if equal else old_changed).append(i)
    if fuse and name!='previous_two_point':assert not old_changed,(name,old_changed)
    added=[o for o in outputs if o['id'] in differences['new_output_ids']]
    incremental=dict(images=len(added),MAE_psi=float(np.mean([o['absolute_error_psi'] for o in added])) if added else None,
        max_abs_error_psi=max([o['absolute_error_psi'] for o in added],default=None),
        correct_bands={str(t):sum(o['absolute_error_psi']<=t for o in added) for t in controls.BANDS})
    return dict(status='OFFLINE_REDUNDANT_LANDMARK_FUSION',name=name,summary=summary,rows=outputs,
        routing=routes,changes=differences,original_valid_ids_preserved=old_kept,original_valid_ids_changed=old_changed,
        new_reference_supported_negative_ids=raw_reference_false_accept,incremental_output_summary=incremental,
        labels_not_used_for_automatic_reference=True,calibration_changed=False,new_neural_weights=False,
        deployed_to_board=False)


def run():
    output=HERE/'results';output.mkdir(exist_ok=True)
    records=rows(DATA/'prepared_validation.jsonl');predictions={r['id']:r for r in rows(MODEL/'polar_angle/run_001/validation_predictions.jsonl')}
    oldposes={r['id']:r for r in rows(OLD/'candidate_B_pose.jsonl')}
    cal=load(OLD/'candidate_B_calibration_psi.json');previous=load(OLD/'candidate_B_with_old_B_readout_psi.json')
    canonical=setup();write(output/'canonical_setup.json',canonical)
    auto_setup=load(HERE/'automatic/setup.json')
    if 'canonical_roll_relative_D002' in auto_setup:
        assert abs(auto_setup['canonical_roll_relative_D002']-canonical['canonical_roll_relative_D002'])<1e-8,'Automatic/manual setup offset mismatch'
    if 'canonical_points_normalized' in auto_setup:
        for key,value in canonical['reference_points_normalized'].items():
            assert np.allclose(auto_setup['canonical_points_normalized'][key],value,rtol=0,atol=1e-8),key
    visual,vdetails=new_poses(records,predictions,canonical,'visual')
    automatic,adetails=new_poses(records,predictions,canonical,'automatic')
    save_rows(output/'visual_reference_poses.jsonl',list(visual.values()));save_rows(output/'automatic_reference_poses.jsonl',list(automatic.values()))
    reports={}
    reports['old_ring']=evaluate('old_ring',records,predictions,oldposes,oldposes,cal,previous['rows'])
    reports['visual_old_first']=evaluate('visual_old_first',records,predictions,oldposes,visual,cal,previous['rows'])
    reports['automatic_old_first']=evaluate('automatic_old_first',records,predictions,oldposes,automatic,cal,previous['rows'])
    assert all((a['valid'],a['psi_estimate'],a['reason'])==(b['valid'],b['psi_estimate'],b['reason']) for a,b in zip(reports['old_ring']['rows'],previous['rows']))
    prior=load(PREVIOUS/'results/visualref_oldcal.json')
    reports['previous_forced_two_point']=dict(name='previous_forced_two_point',summary=prior['summary'],rows=prior['rows'],
        changes=controls.compare(prior['rows'],previous['rows']),historical_diagnostic=True)
    for name,report in reports.items():write(output/(name+'.json'),report)
    front=('front_medium_soft_light','front_large_soft_light')
    summary={}
    for name,report in reports.items():
        ss=report['summary'];sc=ss['by_scene']
        summary[name]=dict(summary=ss,changes=report['changes'],
            old_valid_ids_changed=report.get('original_valid_ids_changed'),
            new_reference_supported_negative_ids=report.get('new_reference_supported_negative_ids'),
            frontal=dict(images=sum(sc[x]['gauges'] for x in front),outputs=sum(sc[x]['valid'] for x in front),
                correct_bands={str(t):sum(sc[x]['within_bands_psi'][str(t)] for x in front) for t in controls.BANDS}),
            incremental=report.get('incremental_output_summary'))
    # Per-point labels only enter the following evaluation, after automatic outputs are frozen.
    labels={r['id']:r for r in rows(HERE/'annotations/print_annotations.jsonl')};point_scores={}
    for name in NAMES:
        accepted=0;error=[];unknown_accepted=[];negative_accepted=[];visible=0;visible_found=0
        for r in records:
            i=r['id'];detail=vdetails[i][name];detected=adetails[i].get(name,{})
            present=detected.get('accepted',False)
            if detail.get('available'):
                visible+=1
                if present:
                    visible_found+=1;error.append(float(np.linalg.norm(np.asarray(detected['normalized_xy'])-detail['normalized_xy'])))
            elif present:unknown_accepted.append(i)
            if present:
                accepted+=1
                if not r['target_present']:negative_accepted.append(i)
        point_scores[name]=dict(automatic_accepted=accepted,visually_localizable_labels=visible,automatic_accepted_on_visible=visible_found,
            localization_error_normalized=dict(mean=float(np.mean(error)) if error else None,max=max(error,default=None),within3px=sum(e<=3 for e in error)),
            localization_hit_rate_within3px_over_visible=sum(e<=3 for e in error)/visible if visible else None,
            accepted_on_visual_unknown_ids=unknown_accepted,accepted_on_negative_ids=negative_accepted,
            unknown_label_does_not_prove_absence=True)
    write(output/'point_evaluation.json',point_scores)
    files=[HERE/'task_contract.json',HERE/'landmark_geometry.py',HERE/'fusion.py',Path(__file__),
        HERE/'annotations/print_annotations.jsonl',HERE/'annotations/reference_D002.json',HERE/'annotations/reference_D025.json',
        HERE/'automatic/config_frozen_before_G.json',HERE/'automatic/setup.json',HERE/'automatic/predictions.jsonl',
        MODEL/'polar_angle/run_001/validation_predictions.jsonl',OLD/'candidate_B_pose.jsonl',OLD/'candidate_B_calibration_psi.json']
    manifest=dict(status='OFFLINE_REDUNDANT_PRINT_EXPERIMENT_COMPLETE_NOT_BOARD_OR_GENERALIZATION_ACCEPTANCE',unit='psi',
        reports=summary,point_evaluation=point_scores,old_neural_and_calibration_unchanged=True,
        routing_old_accepted_is_immutable=True,automatic_did_not_use_query_point_labels=True,
        new_reference_role='Only supplement old rejected reference; never revoke old accepted reference',
        visual_is_AI_reference_diagnostic=True,automatic_only_uses_available_ROI_input=True,
        error_bands_psi=list(controls.BANDS),bands_are_user_final_tolerance=False,
        H_ABC_opened=False,new_training=False,hardware_actions=False,
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in files})
    write(output/'comparison_summary.json',manifest)
    with (output/'逐图参考保留与补充.csv').open('w',newline='',encoding='utf-8-sig') as fp:
        fields=['variant','id','scene','route','old_reference_accepted','new_reference_accepted','model_permitted','valid','psi','reference_psi','abs_error_psi','reason']
        writer=csv.DictWriter(fp,fieldnames=fields);writer.writeheader();rr={r['id']:r for r in records}
        for name,report in reports.items():
            for o in report['rows']:
                writer.writerow(dict(variant=name,id=o['id'],scene=rr[o['id']]['scene']['primary'],route=o.get('reference_route','PREVIOUS_FORCED_TWO_POINT'),
                    old_reference_accepted=o.get('old_reference_accepted'),new_reference_accepted=o.get('new_reference_accepted'),
                    model_permitted=o.get('old_model_permitted',o.get('original_model_permitted')),valid=o['valid'],psi=o['psi_estimate'],
                    reference_psi=o['psi_reference_for_scoring'],abs_error_psi=o['absolute_error_psi'],reason=o['reason']))
    write(output/'routing_preflight.json',preflight())
    for name,ss in summary.items():
        q=ss['summary'];print(name,q['valid_readings'],q['reading_mae_psi'],q['output_error_distribution_psi']['within_0_5_psi'],ss['old_valid_ids_changed'])


if __name__=='__main__':run()
