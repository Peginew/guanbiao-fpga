"""Review train-only bar calibration and common G scoring; never train or read H."""
from pathlib import Path
import hashlib,importlib.util,json,math,sys
import numpy as np
HERE=Path(__file__).resolve().parent;TASK=HERE.parent;READ=TASK/'readout';PREV=TASK.parent/'meter_cnn_training_20261102'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def rows(p):return[json.loads(x)for x in Path(p).read_text('utf-8-sig').splitlines()if x.strip()]
def main():
    sys.path.insert(0,str(READ));s=importlib.util.spec_from_file_location('review_readout',READ/'readout_adapter.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    checks=[]
    def check(ok,name):
        checks.append(dict(name=name,passed=bool(ok)))
        if not ok:raise AssertionError(name)
    cal=load(READ/'calibration.json');contract=load(READ/'readout_contract.json')
    train={r['id']:r for r in rows(PREV/'prepared_train.jsonl')};val={r['id']:r for r in rows(PREV/'prepared_validation.jsonl')}
    tpose={r['id']:r for r in rows(READ/'train_print_pose.jsonl')};vpose={r['id']:r for r in rows(READ/'validation_print_pose.jsonl')}
    check(set(train)==set(tpose) and set(val)==set(vpose),'pose_cache_train177_validation59_only')
    measurements=cal['fit_measurements'];check(len(measurements)==72 and len(cal['anchors'])==14,'72_train_observations14_anchors')
    for a in measurements:
        r=train[a['id']];p=tpose[a['id']]
        check(r['source_group']in'DEF' and r['split']=='train' and r['loss_mask']==[1,1],a['id']+'_train_only_bounded_fit')
        check(r['sha256']==a['source_sha256'] and r['pressure']['value']==a['pressure_psi'],a['id']+'_native_pressure_source')
        h,t=[r['keypoints'][k]['xy']for k in('hub','thin_terminal')]
        theta=math.degrees(math.atan2(t[1]-h[1],t[0]-h[0]))%360
        corrected=(theta-p['relative_roll_deg'])%360
        check(abs(theta-a['native_angle_deg'])<1e-10 and abs(corrected-a['reference_angle_deg'])<1e-10,a['id']+'_direct_visual_angle_not_pressure_inversion')
    x=np.array([a['angle_deg']for a in cal['anchors']]);y=np.array([a['bar']for a in cal['anchors']]);slope,intercept=np.polyfit(x,y,1)
    check(abs(slope-cal['slope_bar_per_degree'])<1e-14 and abs(intercept-cal['intercept_bar'])<1e-12,'independent_anchor_linear_fit')
    check(contract['pressure_threshold_bar']==m.ERROR_TARGET_BAR==.05,'predeclared005bar_engineering_band')
    # Query production pose receives image path and bbox only. Reproduce two
    # cached G cases through this interface, without passing either keypoint.
    ref=train['D_002'];est=m.PrintPose(ref['path'],ref['bbox_native_xyxy'])
    for ident in('G_001','G_018'):
        r=val[ident];p=est.infer(r['path'],r['bbox_native_xyxy'])
        check(p['accepted']==vpose[ident]['accepted'] and abs(p['relative_roll_deg']-vpose[ident]['relative_roll_deg'])<1e-5,ident+'_pose_reproduced_without_query_GT')
    dummy=dict(id='G_001',valid=True,angle_deg_image=280.,pressure=999,keypoints={'hub':[0,0],'thin_terminal':[127,127]})
    alternate=dict(dummy,pressure=-999,keypoints={'hub':[127,0],'thin_terminal':[0,127]})
    check(m.apply_prediction(dummy,vpose['G_001'],cal)==m.apply_prediction(alternate,vpose['G_001'],cal),'GT_pressure_points_mutation_cannot_change_output')
    reports={}
    files=[READ/'baseline_run002_readout.json',READ/'oracle_visual_angle_diagnostic_readout.json']
    if (READ/'polar_readout.json').exists():files.append(READ/'polar_readout.json')
    if (READ/'polar_integer_conv_readout.json').exists():files.append(READ/'polar_integer_conv_readout.json')
    files+=sorted(READ.glob('candidate_*_readout.json'))
    for path in files:
        report=load(path);rr=report['rows'];summary=report['summary']
        check(len(rr)==59 and {r['id']for r in rr}==set(val),path.name+'_same59_G_inputs')
        check(report['source']['calibration_sha256']==sha(READ/'calibration.json') and report['source']['validation_pose_sha256']==sha(READ/'validation_print_pose.jsonl'),path.name+'_same_frozen_calibration_pose')
        for r in rr:
            record=val[r['id']];check(r['source_sha256']==record['sha256'],path.name+'_'+r['id']+'_source')
            if r['valid']:
                a=(r['angle_deg_image']-vpose[r['id']]['relative_roll_deg']-cal['branch_center_deg']+180)%360-180+cal['branch_center_deg']
                bar=slope*a+intercept
                check(abs(bar-r['bar_estimate'])<1e-12,path.name+'_'+r['id']+'_bar_formula')
        positives=[r for r in rr if val[r['id']]['target_present']];negatives=[r for r in rr if not val[r['id']]['target_present']]
        accepted=[r for r in positives if r['valid']]
        errors=[abs(r['bar_estimate']-val[r['id']]['pressure']['value']*m.PSI_TO_BAR)for r in accepted]
        check(len(positives)==56 and len(negatives)==3,path.name+'_correct_pressure_negative_denominators')
        check(summary['valid_readings']==len(accepted) and summary['wrong_accepted_over_005bar']==sum(e>.05 for e in errors),path.name+'_accepted_error_counts')
        check(summary['reading_mae_bar']is None if not errors else abs(summary['reading_mae_bar']-np.mean(errors))<1e-12,path.name+'_mae')
        reports[path.name]=dict(sha256=sha(path),accepted=len(accepted),positive_count=56,coverage=len(accepted)/56,mean_absolute_error_bar=float(np.mean(errors))if errors else None,wrong_over005bar=sum(e>.05 for e in errors),negative_false_accepts=sum(r['valid']for r in negatives),oracle='oracle' in path.name)
    report=dict(status='PASS_TRAIN_ONLY_CALIBRATION_AND_G_SCORING_PROXY_ONLY',checks=len(checks),failures=[],
        calibration_sha256=sha(READ/'calibration.json'),print_pose_sha256=sha(READ/'print_pose.py'),adapter_sha256=sha(READ/'readout_adapter.py'),reports=reports,
        guarantees='Train pressure never inverted to needle labels; G pressure not used by prediction/pose/acceptance; oracle outputs explicitly separated; same calibration across candidates',
        limitations=['Offline PC annotated-bbox and HDMI gray proxies only; no actual MCU/Slice implementation claim',
                    'D002 reference mask is fixed setup; query needs no true hub/needle, but physical pose remains uncalibrated',
                    'G repeatedly used development validation; H unopened; negative sample count3 cannot certify FAR',
                    'Empirical psi-to-bar fit does not change board existing0..0.51TEST calibration; pressure instrument precision unknown'],
        H_or_ABC_opened=False,optimizer_steps=0,hardware_actions=False)
    (HERE/'readout_calibration_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
