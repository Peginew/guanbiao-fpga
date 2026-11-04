"""One-time reproducible unit correction; old evidence remains byte-identical."""
from pathlib import Path
import json,copy,hashlib,sys,shutil
HERE=Path(__file__).resolve().parent;OLD=HERE.parent/'readout'
FACTOR=.0689475729167
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n','utf-8')

def main():
    names=['calibration.json','print_pose.py','train_print_pose.jsonl','validation_print_pose.jsonl','baseline_run002_readout.json','candidate_A_readout.json','polar_readout.json','polar_integer_conv_readout.json']
    before={n:sha(OLD/n)for n in names}
    for n in ['print_pose.py','train_print_pose.jsonl','validation_print_pose.jsonl']:shutil.copy2(OLD/n,HERE/n)
    old=load(OLD/'calibration.json');cal=copy.deepcopy(old)
    cal['schema']='pc_meter_train_pressure_angle_calibration_psi_v1';cal['unit']='psi'
    cal['fit_status']='EXACT_PSI_UNIT_CONVERSION_OF_FROZEN_TRAIN_ONLY_FIT_NO_REFIT'
    cal['formula']='psi=slope_psi_per_degree*unwrap(angle_image-print_roll,branch_center)+intercept_psi'
    cal['slope_psi_per_degree']=cal.pop('slope_bar_per_degree')/FACTOR;cal['intercept_psi']=cal.pop('intercept_bar')/FACTOR
    cal.pop('supported_bar_interval')
    cal['train_calibration_mae_psi']=cal.pop('train_calibration_mae_bar')/FACTOR
    cal['train_calibration_max_abs_error_psi']=cal.pop('train_calibration_max_abs_error_bar')/FACTOR
    for a in cal['anchors']:a.pop('bar')
    for m in cal['fit_measurements']:m.pop('bar_reference');m['reference_psi']=m['pressure_psi']
    cal['runtime_thresholds'].pop('error_acceptance_target_bar');cal['runtime_thresholds']['legacy_equivalent_comparison_tolerance_psi']=.05/FACTOR
    cal['runtime_thresholds']['tolerance_is_user_final_accuracy_target']=False
    cal['runtime_thresholds']['tolerance_note']='Historical0.05bar converted exactly; NOT0.05psi, NOT user-approved accuracy.'
    cal['scope']='PSI-primary PC candidate only; original board calibration and existing hardware unchanged.'
    cal['parent_historical_calibration']=dict(path=str((OLD/'calibration.json').resolve()),sha256=before['calibration.json'],unit='bar',immutable_historical_only=True)
    cal['unit_conversion']=dict(psi_to_bar=FACTOR,method='Divide frozen coefficient by conversion factor; no optimizer/refit/threshold change',pressure_truth='Original USER PSI values directly')
    cal['source_files']={str(HERE/'print_pose.py'):sha(HERE/'print_pose.py'),str(HERE/'readout_adapter.py'):sha(HERE/'readout_adapter.py'),str(OLD/'calibration.json'):before['calibration.json']}
    write(HERE/'calibration.json',cal)
    sys.path.insert(0,str(HERE));import readout_adapter as m
    lookup={r['id']:r for r in m.load_prepared(m.DATA/'prepared_validation.jsonl')}
    checks=[]
    for name in names[4:]:
        original=load(OLD/name);outputs=[]
        for row in original['rows']:
            r=copy.deepcopy(row);r['unit']='psi';r['psi_estimate']=r.pop('bar_estimate')/FACTOR if r['bar_estimate']is not None else r.pop('bar_estimate')
            r.pop('bar_reference_for_scoring');r.pop('absolute_error_bar');r.pop('error_over_target')
            if r['valid']:r['reason']='PC_EMPIRICALLY_CALIBRATED_READING_PSI'
            outputs.append(r)
        summary=m.score_outputs(outputs,lookup);summary['static_pose_supported']=original['summary']['static_pose_supported']
        result=dict(status='PSI_AUTHORITATIVE_FROZEN_EQUIVALENT_PC_RESULT_NOT_BOARD_ACCEPTANCE',unit='psi',summary=summary,rows=outputs,
            source=dict(historical_bar_readout=str((OLD/name).resolve()),historical_sha256=before[name],
                prediction_source=original['source'],new_calibration_sha256=sha(HERE/'calibration.json'),
                unit_conversion_only=True,no_refit_no_model_or_permission_change=True),
            limitations=['Direct USER PSI truth is authoritative; pressure-reference precision unknown.','Historical0.05bar equivalent tolerance~0.725psi only; no user-confirmed final accuracy target.','Manual-bbox/native-HDMI SIFT PC path; not MCU deployed.','Original board calibration unchanged.','H not opened.'])
        old_ids=[r['id']for r in original['rows']if r['valid']];new_ids=[r['id']for r in outputs if r['valid']]
        assert old_ids==new_ids
        assert summary['accurate_accepted_within_tolerance']==original['summary']['accurate_accepted_within_005bar']
        assert summary['wrong_accepted_over_tolerance']==original['summary']['wrong_accepted_over_005bar']
        error=max([abs(r['psi_estimate']*FACTOR-o['bar_estimate'])for r,o in zip(outputs,original['rows'])if r['valid']]+[0])
        assert error<1e-12
        write(HERE/name,result)
        checks.append(dict(file=name,accepted_IDs_preserved=True,accepted_IDs=new_ids,
            classification_counts_preserved=True,max_value_roundtrip_error_in_historical_units=error,
            source_sha256=before[name],new_sha256=sha(HERE/name)))
    assert before=={n:sha(OLD/n)for n in names},'Historical evidence changed'
    receipt=dict(status='PASS_PSI_UNIT_CORRECTION_ONLY',unit='psi',old_bar_files_immutable=True,
        historical_sha256=before,checks=checks,legacy_equivalent_tolerance_psi=.05/FACTOR,
        tolerance_is_005psi=False,tolerance_is_user_confirmed_final_accuracy=False,
        truth_source='Original PSI pressure.value in prepared G records; no converted bar truth',
        new_models_trained=0,new_images_opened=0,H_opened=False,hardware_actions=False,
        source_sha256=dict(adapter=sha(HERE/'readout_adapter.py'),conversion_script=sha(__file__),calibration=sha(HERE/'calibration.json')))
    write(HERE/'unit_conversion_receipt.json',receipt)
    print(json.dumps({name:load(HERE/name)['summary']for name in names[4:]},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
