"""PSI-only correction audit; preserve old bar evidence, predictions and models."""
from pathlib import Path
from html.parser import HTMLParser
import csv,hashlib,importlib.util,json,sys
import numpy as np

HERE=Path(__file__).resolve().parent;TASK=HERE.parent;OLD=TASK/'readout';NEW=TASK/'readout_psi';COMP=TASK/'comparison'
FACTOR=.0689475729167
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def rows(p):return[json.loads(x)for x in Path(p).read_text('utf-8-sig').splitlines()if x.strip()]
class Plain(HTMLParser):
    def __init__(self):super().__init__();self.data=[];self.headers=[];self.in_th=False
    def handle_starttag(self,tag,attrs):
        if tag=='th':self.in_th=True
    def handle_endtag(self,tag):
        if tag=='th':self.in_th=False
    def handle_data(self,data):
        self.data.append(data)
        if self.in_th:self.headers.append(data)
def main():
    checks=[]
    def check(ok,name):
        checks.append(dict(name=name,passed=bool(ok)))
        if not ok:raise AssertionError(name)
    historical_review=load(HERE/'readout_calibration_review.json');receipt=load(NEW/'unit_conversion_receipt.json')
    model_review=load(HERE/'candidate_results_review.json');integer_review=load(HERE/'polar_integer_reference_review.json')
    check(sha(TASK/'keypoint_aux/run_A/best_weights.pt')==model_review['candidates']['A']['checkpoint_sha256'],'candidate_A_weights_unchanged_during_unit_correction')
    check(sha(TASK/'polar_angle/run_001/best_weights.pt')==model_review['candidates']['B']['checkpoint_sha256'],'candidate_B_weights_unchanged_during_unit_correction')
    integer_hashes={k.replace('\\','/'):v for k,v in integer_review['artifacts_sha256'].items()}
    check(sha(TASK/'polar_angle/integer_reference/integer_weights.npz')==integer_hashes['polar_angle/integer_reference/integer_weights.npz'],'integer_weights_unchanged_during_unit_correction')
    check(historical_review['calibration_sha256']==sha(OLD/'calibration.json'),'old_bar_calibration_remains_exact')
    for name,h in receipt['historical_sha256'].items():check(sha(OLD/name)==h,'historical_bytes_unchanged_'+name)
    for name,r in historical_review['reports'].items():check(sha(OLD/name)==r['sha256'],'independently_signed_historical_report_preserved_'+name)
    oldcal=load(OLD/'calibration.json');cal=load(NEW/'calibration.json');tolerance=.05/FACTOR
    check(cal['unit']=='psi' and cal['fit_status']=='EXACT_PSI_UNIT_CONVERSION_OF_FROZEN_TRAIN_ONLY_FIT_NO_REFIT','psi_authoritative_no_refit')
    check(cal['slope_psi_per_degree']==oldcal['slope_bar_per_degree']/FACTOR and cal['intercept_psi']==oldcal['intercept_bar']/FACTOR,'slope_intercept_exact_unit_factor')
    check(cal['supported_pressure_interval_psi']==oldcal['supported_pressure_interval_psi'] and cal['supported_angle_interval_deg']==oldcal['supported_angle_interval_deg'],'calibration_support_unchanged')
    check(cal['runtime_thresholds']['legacy_equivalent_comparison_tolerance_psi']==tolerance and cal['runtime_thresholds']['tolerance_is_user_final_accuracy_target']is False,'legacy_07251886888psi_not005psi_or_user_target')
    prev=TASK.parent/'meter_cnn_training_20261102';lookup={r['id']:r for r in rows(prev/'prepared_validation.jsonl')}
    sys.path.insert(0,str(NEW));s=importlib.util.spec_from_file_location('psi_audit_adapter',NEW/'readout_adapter.py');adapter=importlib.util.module_from_spec(s);s.loader.exec_module(adapter)
    pose={r['id']:r for r in rows(NEW/'validation_print_pose.jsonl')};summary={}
    for name in('baseline_run002_readout.json','candidate_A_readout.json','polar_readout.json','polar_integer_conv_readout.json'):
        before=load(OLD/name);after=load(NEW/name);a=after['rows'];b=before['rows'];outsum=after['summary']
        check(after['unit']=='psi' and outsum['unit']=='psi',name+'_psi_primary')
        check([r['id']for r in a]==[r['id']for r in b] and [r['id']for r in a if r['valid']]==[r['id']for r in b if r['valid']],name+'_every_output_ID_and_permission_unchanged')
        for row,original in zip(a,b):
            ref=lookup[row['id']]['pressure']['value'];check(row['psi_reference_for_scoring']==ref,name+'_'+row['id']+'_direct_user_psi_truth')
            check(row['source_sha256']==original['source_sha256'],name+'_'+row['id']+'_same_input_identity')
            for field in('angle_deg_image','print_relative_roll_deg','reference_angle_deg'):
                if field in original:check(row[field]==original[field],name+'_'+row['id']+'_'+field+'_unchanged')
            if row['valid']:
                check(abs(row['psi_estimate']*FACTOR-original['bar_estimate'])<1e-12,name+'_'+row['id']+'_value_unit_equivalence')
                check(abs(row['absolute_error_psi']-abs(row['psi_estimate']-ref))<1e-12,name+'_'+row['id']+'_psi_error_directly_recomputed')
        accepted=[r for r in a if r['valid']and r['target_present_for_scoring']];errors=np.array([abs(r['psi_estimate']-lookup[r['id']]['pressure']['value'])for r in accepted])
        check(abs(outsum['reading_mae_psi']-float(errors.mean()))<1e-12 and abs(outsum['reading_mae_psi']*FACTOR-before['summary']['reading_mae_bar'])<1e-12,name+'_MAE_direct_and_unit_factor')
        check(outsum['valid_readings']==len(accepted) and outsum['gauge_images']==56 and outsum['negative_images']==3,name+'_unchanged_denominators')
        check(outsum['accurate_accepted_within_tolerance']==int((errors<=tolerance).sum())==before['summary']['accurate_accepted_within_005bar'],name+'_legacy_count_unchanged')
        distribution=outsum['output_error_distribution_psi'];counts=[int((errors<=x).sum())for x in(.25,.5,1.)]
        check([distribution[k]for k in('within_0_25_psi','within_0_5_psi','within_1_0_psi')]==counts,name+'_report_only_error_distribution')
        check(distribution['changes_output_permission']is False and distribution['is_user_confirmed_final_accuracy_target']is False,name+'_bins_not_acceptance_gate')
        source=before['source']['predictions'];original_preds=adapter.read_predictions(source)
        rerun=[adapter.apply_prediction(p,pose[p['id']],cal)for p in original_preds]
        check([r['id']for r in rerun if r['valid']]==[r['id']for r in a if r['valid']],name+'_new_psi_apply_same_permission')
        d={r['id']:r for r in a}
        check(all(abs(r['psi_estimate']-d[r['id']]['psi_estimate'])<1e-12 for r in rerun if r['valid']),name+'_psi_formula_replay')
        summary[name]=dict(valid=len(accepted),mae_psi=float(errors.mean()),within025_05_1psi=counts,legacy_tolerance_within=int((errors<=tolerance).sum()),legacy_over=int((errors>tolerance).sum()),sha256=sha(NEW/name))
    current=load(COMP/'summary.json');check(current['unit']=='psi','current_comparison_summary_is_psi')
    parser=Plain();parser.feed((COMP/'index.html').read_text('utf-8'));text=' '.join(parser.data);header=' '.join(parser.headers)
    check('psi'in header.lower() and 'MAE' in header and not any('bar'in h.lower()for h in parser.headers),'current_table_units_psi_not_bar')
    check('0.25'in text and '0.5'in text and '1.0'in text,'current_page_displays_explicit_psi_error_distribution')
    check('不是'in text or '不代表'in text or '并非'in text,'current_page_has_scope_or_target_qualification')
    with (COMP/'逐图对照.csv').open(encoding='utf-8-sig',newline='')as f:
        csvrows=list(csv.DictReader(f))
    check(len(csvrows)==59 and any('psi'in k.lower()for k in csvrows[0]),'current_CSV59_psi_fields')
    snapshot=load(COMP/'history_bar_display/snapshot_manifest.json')
    check(snapshot['status']=='IMMUTABLE_HISTORICAL_BAR_DISPLAY_SNAPSHOT','archive_explicitly_marked_historical_bar')
    for name,info in snapshot['files'].items():check(sha(COMP/'history_bar_display'/name)==info['sha256'],'archived_original_bytes_'+name)
    check((COMP/'history_bar_display/index.html').is_file()and(COMP/'history_bar_display/summary.json').is_file(),'old_bar_comparison_kept_in_history')
    oldpage=(COMP/'history_bar_display/index.html').read_bytes();check(hashlib.sha256(oldpage).hexdigest()=='58c36f161964ca920b03d0de46e759de08fd5a60787d8e8d187e215791ddef5e','old_bar_HTML_original_SHA_preserved')
    report=dict(status='PASS_PSI_PRIMARY_UNIT_CORRECTION_ONLY',checks=len(checks),failures=[],primary_unit='psi',
        correction='Authoritative truth directly uses user PSI. Frozen calibration coefficients and numerical outputs converted exactly; no new fit, model or output-permission change.',
        legacy_equivalent_comparison_tolerance_psi=tolerance,legacy_tolerance_is_005psi=False,legacy_tolerance_is_user_final_accuracy_requirement=False,
        report_only_distribution_psi=[.25,.5,1.],distribution_changes_model_permission=False,results=summary,
        new_artifact_sha256={str(path.relative_to(TASK)):sha(path)for path in[NEW/'calibration.json',NEW/'readout_adapter.py',NEW/'unit_conversion_receipt.json',COMP/'index.html',COMP/'summary.json',COMP/'逐图对照.csv',COMP/'comparison_manifest.json']},
        old_bar_evidence_and_review_preserved=True,no_new_model_training=True,test_H_or_ABC_opened=False,hardware_actions=False)
    (HERE/'psi_unit_correction_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps(dict(status=report['status'],checks=len(checks),results=summary),ensure_ascii=False))
if __name__=='__main__':main()
