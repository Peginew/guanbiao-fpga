"""Independent reference/calibration replay; no model execution or training."""
from pathlib import Path
import csv, hashlib, json, math, sys
import numpy as np
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;TASK=HERE.parent;ROOT=TASK.parents[1]
DATA=ROOT/'algorithm_work/meter_cnn_training_20261102';PREV=ROOT/'algorithm_work/meter_robust_readout_20261102/pose';OLD=ROOT/'algorithm_work/meter_pointer_readout_20261102'
TOP='outer_psi_10_text_centroid';BOTTOM='lower_striped_ball_print_centroid';BANDS=[.25,.5,1.]
checks=[]
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def rows(p):return[json.loads(x)for x in Path(p).read_text('utf-8-sig').splitlines()if x.strip()]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,name):
    checks.append(name)
    if not ok:raise AssertionError(name)
def close(a,b):return a is None and b is None or a is not None and b is not None and abs(a-b)<1e-9
def wrap(a,c=0.):return(a-c+180)%360-180+c
def metric(rr,truth):
    acc=[r for r in rr if r['valid'] and truth[r['id']]['target_present']]
    err=[abs(r['psi_estimate']-truth[r['id']]['pressure']['value'])for r in acc]
    return dict(valid_readings=len(acc),MAE_psi=float(np.mean(err))if err else None,
        median_psi=float(np.median(err))if err else None,max_psi=max(err)if err else None,
        bins={str(t):sum(e<=t for e in err)for t in BANDS},negative_outputs=sum(r['valid']and not truth[r['id']]['target_present']for r in rr),
        gauge_denominator=sum(truth[r['id']]['target_present']for r in rr),ids=sorted(r['id']for r in acc))

def main():
    tr=rows(DATA/'prepared_train.jsonl');dev=rows(DATA/'prepared_validation.jsonl');lookup={r['id']:r for r in tr+dev};gt={r['id']:r for r in dev}
    need(all(r['source_group']in'DEF'for r in tr)and all(r['source_group']=='G'for r in dev),'DEF_train_G_development_only')
    need(len(dev)==59 and sum(r['target_present']for r in dev)==56,'fixed59_and56_denominators')
    report=load(TASK/'results/comparison_summary.json')
    for rel,h in report['source_sha256'].items():need(sha(ROOT/rel)==h,'bound_source_'+rel)
    need(sha(DATA/'run_002/best_weights.pt')=='c221678efa4762bed298828b2e8e8ba3c2a6b343c2c16efe35aec77a85c896df','frozen1202_hub')
    need(sha(OLD/'polar_angle/run_001/best_weights.pt')=='d139ecdc1059829be18e23eaf5d503d5c9d59a798d2986774441f88cc1804882','frozen1009_needle')
    ta=rows(TASK/'annotations_train/print_annotations.jsonl');ga=rows(TASK/'annotations_g/print_annotations.jsonl');ann={r['id']:r for r in ta+ga}
    selected={r['id']for r in tr if r['target_present'] and r['capture_condition_slot']in[1,2]}
    need(len(selected)==48 and {r['id']for r in ta}==selected,'48_selected_corrected_metadata_not_ID_arithmetic')
    need({r['id']for r in ga}==set(gt),'G59_sidecars_complete')
    manifests={r['id']:r for r in load(TASK/'annotations_train/view_manifest.json')['records']}
    manifests.update({r['id']:r for r in rows(TASK/'annotations_g/display_index.jsonl')})
    absolute={};visual={};native_available=[];partial=[]
    for ident,a in ann.items():
        r=lookup[ident];need(a['source_sha256']==r['sha256'],ident+'_annotation_source')
        flag=a.get('point_selection_used_pressure_or_predictions',a.get('pressure_or_query_neural_pose_used_for_points'))
        need(flag is False,ident+'_no_pressure_or_prediction_point_selection')
        m=manifests[ident];points=[];usable=a['accepted']
        for key in[TOP,BOTTOM]:
            point=a['anchors'][key]
            if point['native_xy']is None:usable=False;continue
            p=np.asarray(point['native_xy'],np.float64);v=np.asarray(point.get('view_xy',point.get('manually_read_view_xy')),np.float64)
            if ident[0]=='G':
                t=m['view_transform'];expected=np.array(m['native_crop_xyxy'][:2])+(v-[t['offset_x'],t['offset_y']])/[t['scale_x'],t['scale_y']]
            else:
                size=np.asarray(m['native_crop_xyxy'][2:])-m['native_crop_xyxy'][:2]
                expected=np.array(m['native_crop_xyxy'][:2])+(v-m['display_offset'])*size/m['resized_native_crop_size']
            need(np.max(abs(p-expected))<1e-8,ident+'_'+key+'_view_mapping')
            q=r['roi_request'];roi=(p-[q['x0'],q['y0']]-(q['stride']-1)/2)/q['stride']
            if point.get('roi_xy')is not None:need(np.max(abs(roi-point['roi_xy']))<1e-9,ident+'_'+key+'_ROI_mapping')
            points.append((p,roi,float(point['uncertainty_native_px']),point['visibility']))
            if a['accepted']:need(point['visibility']in['visible','partially_visible','partial'],ident+'_'+key+'_visible_support')
        if usable:
            need(len(points)==2,ident+'_two_real_points')
            vector=points[0][0]-points[1][0];length=np.linalg.norm(vector);u=points[0][2]+points[1][2]
            need(length>u,ident+'_resolved_axis')
            absolute[ident]=math.degrees(math.atan2(vector[1],vector[0]));native_available.append(ident)
            visual[ident]=all(np.all((p[1]>=0)&(p[1]<=127))for p in points)
            if any(p[3]!='visible'for p in points):partial.append(ident)
        else:visual[ident]=False
    need(visual['D_002'],'train_D002_zero_reference_visible')
    reference=absolute['D_002'];newposes={r['id']:r for r in rows(TASK/'results/visual_print_poses.jsonl')}
    need(len(newposes)==236,'236_pose_rows_missing_labels_not_dropped')
    for ident,r in lookup.items():
        expected=visual.get(ident,False);p=newposes[ident]
        need(p['accepted']==expected,ident+'_reference_permission')
        if expected:need(abs(wrap(p['relative_roll_deg']-wrap(absolute[ident]-reference)))<1e-9,ident+'_relative_bottom_to_top_direction')
    need(sum(visual.get(r['id'],False)for r in dev)==46,'G46_visual_reference_available')
    oldposes={r['id']:r for r in rows(PREV/'candidate_B_pose.jsonl')};oldcal=load(PREV/'candidate_B_calibration_psi.json')
    common={r['id']for r in tr if r['id']in selected and visual.get(r['id'],False)and oldposes.get(r['id'],{}).get('accepted')and r['loss_mask']==[1,1]}
    need(len(common)==31 and sorted(common)==report['common_calibration_ids'],'same31_DEF_calibration_observations')
    def fit(posemap,allowed,filename):
        measurements=[]
        for r in tr:
            ident=r['id'];po=posemap.get(ident,{})
            if ident not in allowed or not po.get('accepted')or r['loss_mask']!=[1,1]or not r['target_present']:continue
            need(r['pressure']['unit']=='psi',ident+'_direct_user_PSI_calibration')
            h,t=[np.asarray(r['keypoints'][k]['xy'])for k in['hub','thin_terminal']];d=t-h
            angle=(math.degrees(math.atan2(d[1],d[0]))-po['relative_roll_deg'])%360
            measurements.append((ident,angle,r['pressure']['value']))
        aa=np.radians([x[1]for x in measurements]);center=math.degrees(math.atan2(np.sin(aa).mean(),np.cos(aa).mean()))%360
        anchors=[(float(np.median([wrap(a,center)for i,a,p in measurements if p==psi])),psi)for psi in sorted({x[2]for x in measurements})]
        x=np.array([a for a,p in anchors]);y=np.array([p for a,p in anchors]);coeff=np.linalg.lstsq(np.column_stack([x,np.ones_like(x)]),y,rcond=None)[0]
        cal=load(TASK/'results'/filename)
        need(close(center,cal['branch_center_deg'])and close(float(coeff[0]),cal['slope_psi_per_degree'])and close(float(coeff[1]),cal['intercept_psi']),filename+'_independent_linear_fit')
        need({x[0]for x in measurements}=={x['id']for x in cal['fit_measurements']},filename+'_exact_DEF_IDs')
        need(np.allclose([x.min(),x.max()],cal['supported_angle_interval_deg'],atol=1e-9)and[min(y),max(y)]==cal['supported_pressure_interval_psi'],filename+'_unexpanded_support')
        return cal
    newcal=fit(newposes,selected,'new_calibration_psi.json');cm_old=fit(oldposes,common,'matched_old_calibration_psi.json');cm_new=fit(newposes,common,'matched_visual_calibration_psi.json')
    predictions={r['id']:r for r in rows(OLD/'polar_angle/run_001/validation_predictions.jsonl')}
    combos={'oldref_oldcal':(oldposes,oldcal),'visualref_oldcal':(newposes,oldcal),'oldref_newcal':(oldposes,newcal),'visualref_newcal':(newposes,newcal),
        'matched_oldref_oldcal':(oldposes,cm_old),'matched_visualref_oldcal':(newposes,cm_old),'matched_oldref_newcal':(oldposes,cm_new),'matched_visualref_newcal':(newposes,cm_new)}
    results={};numbers={};available={i for i in gt if visual.get(i,False)}
    for name,(poses,cal)in combos.items():
        result=load(TASK/'results'/f'{name}.json');rr=result['rows'];need(len(rr)==59 and {r['id']for r in rr}==set(gt),name+'_all59')
        for out in rr:
            ident=out['id'];p=predictions[ident];pose=poses[ident]
            if not p['valid']:valid=False;reason='PREDICTION_NOT_PERMITTED';psi=None
            elif not pose['accepted']:valid=False;reason=pose['reason'];psi=None
            else:
                angle=wrap(p['angle_deg_image']-pose['relative_roll_deg'],cal['branch_center_deg']);psi=cal['slope_psi_per_degree']*angle+cal['intercept_psi'];lo,hi=cal['supported_angle_interval_deg'];pl,ph=cal['supported_pressure_interval_psi']
                valid=bool(lo<=angle<=hi and pl<=psi<=ph);reason='PC_EMPIRICALLY_CALIBRATED_READING_PSI'if valid else'PREDICTED_DIRECTION_OUTSIDE_TRAIN_CALIBRATION'if not lo<=angle<=hi else'PREDICTED_VALUE_OUTSIDE_TRAIN_PRESSURE_SUPPORT'
            need(out['original_model_permitted']==p['valid']and out['valid']==valid and out['reason']==reason,ident+'_'+name+'_same_CNN_joint_permission')
            need(not valid or close(psi,out['psi_estimate']),ident+'_'+name+'_unclamped_PSI')
            need(out['psi_reference_for_scoring']==gt[ident]['pressure']['value']and out['source_sha256']==gt[ident]['sha256'],ident+'_'+name+'_PSI_truth_source')
        mm=metric(rr,gt);s=result['summary']
        need(mm['valid_readings']==s['valid_readings']and close(mm['MAE_psi'],s['reading_mae_psi'])and close(mm['max_psi'],s['reading_max_abs_error_psi']),name+'_independent_metrics')
        need(mm['gauge_denominator']==56 and mm['negative_outputs']==s['negative_false_accepts'],name+'_denominators_and_negatives')
        need(all(mm['bins'][str(t)]==s['descriptive_correct_output_coverage'][str(t)]['correct_outputs']for t in BANDS),name+'_PSI_bins')
        vv=metric([r for r in rr if r['id']in available],gt);vs=result['same_visual_available_subset_summary']
        need(vv['gauge_denominator']==46 and vv['valid_readings']==vs['valid_readings']and close(vv['MAE_psi'],vs['reading_mae_psi']),name+'_same_V46_subset')
        front=[r for r in rr if gt[r['id']]['scene']['primary']in['front_medium_soft_light','front_large_soft_light']]
        mm['front16']=metric(front,gt);results[name]=result;numbers[name]=mm
    original={r['id']:r for r in load(PREV/'candidate_B_with_old_B_readout_psi.json')['rows']}
    for r in results['oldref_oldcal']['rows']:need((r['valid'],r['psi_estimate'],r['reason'])==(original[r['id']]['valid'],original[r['id']]['psi_estimate'],original[r['id']]['reason']),r['id']+'_exact_frozen_baseline')
    baseline={r['id']:r for r in results['oldref_oldcal']['rows']}
    for name,result in results.items():
        nn={r['id']:r for r in result['rows']};d=result['changes_against_frozen_baseline']
        need(set(d['new_output_ids'])=={i for i in nn if nn[i]['valid']and not baseline[i]['valid']}and set(d['withdrawn_output_ids'])=={i for i in nn if baseline[i]['valid']and not nn[i]['valid']},name+'_gain_loss_IDs')
        for t in BANDS:
            good=lambda r:r['valid']and r['target_present_for_scoring']and r['absolute_error_psi']<=t
            bad=lambda r:r['valid']and(not r['target_present_for_scoring']or r['absolute_error_psi']>t)
            expected=dict(gained_correct_ids={i for i in nn if good(nn[i])and not good(baseline[i])},lost_correct_ids={i for i in nn if good(baseline[i])and not good(nn[i])},new_wrong_ids={i for i in nn if bad(nn[i])and not bad(baseline[i])},recovered_wrong_ids={i for i in nn if bad(baseline[i])and not bad(nn[i])})
            need(all(set(d['bands'][str(t)][key])==ids for key,ids in expected.items()),name+'_all_bin_ID_deltas_'+str(t))
    csvrows=list(csv.DictReader((TASK/'results/逐图四格与共同标定对照.csv').open(encoding='utf-8-sig',newline='')))
    need(len(csvrows)==8*59 and len({(r['variant'],r['id'])for r in csvrows})==8*59,'CSV472_unique_rows')
    answer=dict(status='PASS_OFFLINE_CONTROL_REPLAY_NO_AUTOMATIC_READER_ADOPTION',checks=len(checks),unit='psi',source_sha256={str(p.relative_to(TASK)):sha(p)for p in[TASK/'task_contract.json',TASK/'run_controls.py',TASK/'annotations_train/print_annotations.jsonl',TASK/'annotations_g/print_annotations.jsonl',TASK/'results/comparison_summary.json']},
        calibration_observations=dict(new_visual=43,matched=31),G_available_reference=46,numbers=numbers,
        judgement=['Visual reference + oldcal adds11 and withdraws5:27 outputs24within0.5psi versus old21allwithin0.5; three new over0.5 errors remain.',
            'All five withdrawals are fixed-anchor occlusion inG013..G018; missing anchors cannot be force-filled. A single double-anchor set is not a universal reference method.',
            'Frontal16 improves valid9to10 but within0.5 remains9; the basic frontal reading problem is not solved.',
            'New calibration raises matched-set MAE and counts over0.5psi while some tighter-bin counts improve; no robust overall replacement benefit is established, so retain old calibration.',
            'AI native static centroids are diagnostic observations, not pose gold or automatic128ROI inference. No new runtime reader is accepted.'],
        visibility_scope=dict(partially_visible_annotation_IDs=sorted(partial),manual_visual_review='Independent first9G clean page and six-image challenge detail plusG056 point overlay viewed; not a full107-image gold audit'),
        uncertainty='Declared point sensitivities are not certified errors; source view mapping is checked as documented. Two-point relative direction is not perspective correction/yaw.',
        no_fallback_in_primary=True,no_new_training=True,H_or_ABC_opened=False,canonical_or_weights_modified=False,hardware_actions=False)
    (HERE/'supervision_review.json').write_text(json.dumps(answer,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({k:v for k,v in answer.items()if k not in['numbers','visibility_scope']},ensure_ascii=False))
    for k,v in numbers.items():print(k,v['valid_readings'],v['MAE_psi'],v['bins'],'front',v['front16']['valid_readings'],v['front16']['bins'])
if __name__=='__main__':main()
